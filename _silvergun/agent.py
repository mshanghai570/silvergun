"""Bounded OpenAI-compatible tool agent with a deterministic capability router."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import json
from typing import Any

from .adapters import AdapterRegistry
from .client import OpenAICompatibleClient, ProviderError
from .capability_registry import CapabilityRegistry, plan_from_route
from .contracts import PlanValidationError, normalize_result
from .router import CapabilityRouter, Route
from .tools import NativeTools
from .events import (
    emit_round_started, emit_round_evidence, emit_tool_started, 
    emit_tool_result, emit_tool_failed, emit_investigation_complete,
    emit_final_synthesis, get_event_emitter, reset_event_emitter, EventFormatter, InvestigationEvent
)


SYSTEM_PROMPT = """You are Silvergun, a concise Binary Ninja reverse-engineering partner.
A live BinaryView context header is supplied with each request. Treat it as authoritative host context.
Use supplied tools before making binary-specific claims and cite their evidence in your answer. Clearly
separate PROVEN host facts from INFERRED interpretations and HYPOTHESES. When an address is supplied, use it as a host
address with the 0x prefix; do not invent a different format or ask whether the binary is loaded when
binary_view_attached is true. Omit the address when asking for the current function. State evidence and
uncertainty. Use semantic_search or query_binary for stripped-binary triage, get_verification for trust
checks, code_map for relationships, and notebook tools for durable findings. Never claim that a mutation
occurred unless a tool reports it. Do not reveal hidden reasoning; return only a short, useful analyst
answer with concrete next actions when appropriate. Treat the user's request as a goal to
complete, not a question to summarize: decompose it into evidence-gathering steps, and when
the goal includes a mutation (patch, rename, type, annotation) propose it with the matching
tool — every mutation asks the user for approval before anything is written. When a request is
about specific text content (strings, URLs, passwords, secrets) prefer bn_search_strings; when
it is about symbols or function names prefer bn_search_symbols or bn_find_functions; then use
get_xrefs to see who uses the matches. For semantic categories, use canonical BoolHunter values
such as Purchases, Authentication & Security, or Network & Communication; notebook_record is the
durable-finding tool. Do not repeat a tool call that returned the same data;
move to the next step or answer."""

ROUTE_GUIDANCE = {
    "search": "Treat this as a provider-neutral search. If the user names a plugin, use search_capabilities to resolve that exact installed capability, then invoke_external_command when it is available and approved. Also compare the plugin result with Binary Ninja's native search tools and Silvergun's local semantic/query tools when the request asks to find functions. BoolHunter is only one optional provider; never assume it is the right or only searcher. If one provider returns zero results, try the other relevant providers before concluding that nothing matched.",
    "triage": "Triage locally first; return a ranked shortlist with the exact matching evidence for each function.",
    "verify": "Verify before interpreting; label every statement PROVEN, INFERRED, or HYPOTHESIS and cite a host source.",
    "map": "Build the relationship map before explaining control flow; distinguish observed edges from behavioral guesses.",
    "notebook": "Use the notebook as durable context and record only concise findings with evidence and confidence.",
    "vulnerabilities": "Treat detector hits as leads only; report the matched operation, reachability question, and missing proof.",
    "investigate": "Decompose the objective into bounded, evidence-producing sub-investigations and synthesize only after tool results.",
    "boolean": "Use BoolHunter to find boolean functions matching the request. Analyze candidates for evidence-based scoring.",
    "category": "Search the category with semantic_search, query_binary, and Binary Ninja evidence, then use BoolHunter's category tool as an additional signal. Use canonical labels such as Purchases, Authentication & Security, or Network & Communication. Return the actual matching functions, addresses, evidence, provider counts, and confidence; zero results from one provider are not proof that the category is absent.",
    "batch_scan": "Use BoolHunter batch_scan to analyze multiple functions efficiently.",
    "strings": "Use bn_search_strings to locate string evidence, then find_functions or get_xrefs to see who references the matches.",
    "symbols": "Use bn_search_symbols or bn_find_functions to locate name-based evidence, then get_xrefs for call context.",
    "continue": "Restore the case file with notebook_context first, then re-verify the recorded leads with fresh evidence before acting on them.",
}

MUTATION_TOOLS = frozenset({"apply_patch", "rename_function", "apply_function_type", "annotate_function", "invoke_external_command"})
MAX_CAPABILITY_EXECUTIONS = 24
EVIDENCE_TOOLS = frozenset({
    "get_function_context", "get_xrefs", "get_type_evidence", "review_vulnerabilities",
    "semantic_search", "query_binary", "get_verification", "code_map", "bn_analyze",
    "bn_decompile", "bn_find_cross_references", "bn_search_strings", "bn_search_symbols",
    "bn_find_functions", "boolhunter_quick_scan", "boolhunter_analyze", "boolhunter_batch_scan",
    "boolhunter_find_category", "fanout_investigate", "search_capabilities", "invoke_external_command",
})
TOOL_ALIASES = {
    "search_strings": "bn_search_strings",
    "search_symbols": "bn_search_symbols",
    "find_category": "boolhunter_find_category",
    "notebook_add": "notebook_record",
    "notebook_save": "notebook_record",
}


@dataclass(frozen=True)
class AgentResult:
    answer: str
    intent: str
    rounds: int


class LeanAgent:
    """A small agent loop with a hard tool-round budget and no planning model call."""

    def __init__(self, client: OpenAICompatibleClient, settings, adapter_registry: AdapterRegistry | None = None, on_event=None, cancel_event=None) -> None:
        self.client = client
        self.settings = settings
        self.router = CapabilityRouter()
        self.adapter_registry = adapter_registry
        self.on_event = on_event
        self.cancel_event = cancel_event

    def run(self, request: str, native: NativeTools, conversation_context: str = "") -> AgentResult:
        # Reset event emitter for new investigation
        reset_event_emitter()
        
        capabilities = native.capabilities
        if self.adapter_registry:
            capabilities = list(capabilities) + self.adapter_registry.capabilities()
        route = self.router.route(request, capabilities)

        native_schemas = native.definitions(route.tools)
        schema_index = {
            str(schema.get("function", {}).get("name", "")): schema
            for schema in native_schemas
            if isinstance(schema, dict)
        }
        registry = CapabilityRegistry(schema_index, self.adapter_registry, route.external)
        try:
            plan = plan_from_route(request, route.intent, route.tools, registry)
        except PlanValidationError as error:
            self._emit("[PLANNER] Replanning from currently available capabilities", "The initial plan was invalid, so I am rebuilding it from the active capability registry.")
            valid_tools = tuple(tool for tool in route.tools if registry.get(tool) and registry.get(tool).available)
            plan = plan_from_route(request, route.intent, valid_tools, registry)

        selected_tools = tuple(step.capability_id for step in plan.steps)
        self._emit(f"[PLANNER] Validated {len(selected_tools)} capabilities for {plan.intent}", f"I mapped this to a focused {plan.intent} investigation using currently available capabilities.")

        tools = native.definitions(selected_tools)
        if self.adapter_registry:
            for tool_name in selected_tools:
                schema = self.adapter_registry.get_tool_schema(tool_name)
                if schema:
                    tools.append(schema)
        
        # Set up event forwarding from global emitter to agent's on_event
        emitter = get_event_emitter()
        emitter.add_listener(self._forward_event)
        
        try:
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": self._request_message(request, route, native.context_hint(), native.notebook_context(), registry, plan, conversation_context)},
            ]
            executed: set[str] = set()
            tool_call_counts: dict[str, int] = {}
            evidence_collected = False
            evidence_sequence = 0
            capability_executions = 0
            
            for round_number in range(1, self.settings.max_steps + 1):
                if self.cancel_event is not None and self.cancel_event.is_set():
                    self._emit("INVESTIGATION / CANCELLED", "Investigation cancelled before the next capability ran.")
                    return AgentResult("Investigation cancelled before the next capability ran.", route.intent, round_number - 1)
                if capability_executions >= MAX_CAPABILITY_EXECUTIONS:
                    self._emit("INVESTIGATION / EXECUTION BUDGET REACHED", "The capability execution budget was reached; I am synthesizing the evidence collected so far.")
                    break
                emit_round_started(round_number, self.settings.max_steps)
                
                completion = self.client.chat(self.settings.model, messages, tools)
                if not completion.tool_calls:
                    answer = completion.content.strip() or "The model returned no answer."
                    self._emit("[FINAL] Evidence collected; preparing the answer", "I have enough evidence — writing up the final answer now.")
                    emit_investigation_complete(route.intent, f"Investigation completed in {round_number} rounds")
                    return AgentResult(answer, route.intent, round_number)
                
                calls = []
                call_ids: set[str] = set()
                for index, call in enumerate(completion.tool_calls, start=1):
                    normalized_call = _normalized_tool_call(call, round_number, index)
                    call_id = str(normalized_call["id"])
                    if call_id in call_ids:
                        normalized_call["id"] = f"{call_id}_{round_number}_{index}"
                    call_ids.add(str(normalized_call["id"]))
                    calls.append(normalized_call)
                messages.append({"role": "assistant", "content": completion.content or "", "tool_calls": calls})
                
                for call in calls[:6]:
                    call_id = str(call["id"])
                    name = "unknown_tool"
                    try:
                        name, arguments = _tool_call(call)
                        signature = f"{name}:{json.dumps(arguments, sort_keys=True, separators=(',', ':'))}"
                        if signature in executed:
                            result = "Skipped duplicate tool call. Use the previous result."
                            emit_tool_result(name, f"Skipped duplicate call: {signature[:50]}...")
                        elif name in MUTATION_TOOLS and not evidence_collected:
                            result = (
                                "Mutation blocked until Silvergun collects relevant Binary Ninja evidence. "
                                "First call get_function_context (and get_xrefs or another relevant read-only tool), "
                                "then propose the exact mutation with its evidence and wait for approval."
                            )
                            emit_tool_failed(name, "Mutation requested before evidence", result)
                        else:
                            executed.add(signature)
                            tool_call_counts[name] = tool_call_counts.get(name, 0) + 1
                            capability_executions += 1
                            result = self._execute(name, arguments, native)
                            spec = registry.get(name)
                            if spec is not None:
                                normalized_result = normalize_result(spec, hex(id(native.bv)), result, sequence=evidence_sequence)
                                evidence_sequence += 1
                                if normalized_result.evidence:
                                    emit_tool_result(name, f"Normalized {len(normalized_result.evidence)} structured evidence items", {"evidence_count": len(normalized_result.evidence), "capability_id": name})
                                if not normalized_result.success:
                                    emit_tool_failed(name, normalized_result.failure.display() if normalized_result.failure else "Capability failed", normalized_result.summary)
                            if name in EVIDENCE_TOOLS and not result.startswith(("Tool error:", "Unexpected tool error:")):
                                evidence_collected = True
                            if tool_call_counts[name] >= 2:
                                # Break the repeat-exploration loop: give the model a
                                # corrective signal instead of burning another round.
                                result = (
                                    f"{result}\n\n[Silvergun guardrail] This is call #{tool_call_counts[name]} to {name}. "
                                    "If it targeted the same data as before, repeating it will not produce new evidence. "
                                    "Pick specific functions from the results already gathered and inspect them with get_function_context or get_xrefs, "
                                    "apply the requested mutation with its dedicated tool when the goal needs one, or produce the final answer now."
                                )
                            emit_tool_result(name, f"Completed {name}", {"length": len(result)})
                        
                    except (TypeError, ValueError, json.JSONDecodeError) as error:
                        result = f"Tool request rejected: {error}. Continue with a valid tool call or answer directly."
                        emit_tool_failed(name, f"Request rejected: {error}", str(error))
                    messages.append({"role": "tool", "tool_call_id": call_id, "content": result})
            
            final = self.client.chat(self.settings.model, messages, ())
            answer = final.content.strip() or "Tool budget reached. Review the collected tool results."
            self._emit("[FINAL] Capability budget reached; synthesizing collected evidence", "That was the last capability round — wrapping up with what I've gathered.")
            emit_investigation_complete(route.intent, f"Tool budget reached after {self.settings.max_steps} rounds")
            emit_final_synthesis(answer, route.intent)
            return AgentResult(answer, route.intent, self.settings.max_steps)
        finally:
            # Clean up event listener
            emitter.remove_listener(self._forward_event)
    
    def _forward_event(self, event: InvestigationEvent) -> None:
        """Forward events from the global emitter to the agent's on_event callback.

        Investigation events are observability output.  They must never be
        mistaken for Silvergun's canonical conversational answer.
        """
        if self.on_event:
            self.on_event(EventFormatter.format_event(event), None)

    def _emit(self, message: str, narration: str | None = None) -> None:
        if self.on_event is not None:
            self.on_event(message, None)

    def _execute(self, name: str, arguments: dict[str, Any], native: NativeTools) -> str:
        try:
            if name == "fanout_investigate":
                return self._fanout(arguments, native)
            if self._is_adapter_tool(name):
                return self._execute_adapter_tool(name, arguments)
            return native.execute(name, arguments)
        except (ProviderError, KeyError, ValueError, TypeError) as error:
            return f"Tool error: {error}"
        except Exception as error:
            return f"Unexpected tool error: {error}"

    def _is_adapter_tool(self, name: str) -> bool:
        if not self.adapter_registry:
            return False
        return self.adapter_registry.is_available(name)

    def _execute_adapter_tool(self, name: str, arguments: dict[str, Any]) -> str:
        if not self.adapter_registry:
            return json.dumps({"error": "Adapter registry not available"})
        return self.adapter_registry.execute(name, arguments)

    def _fanout(self, arguments: dict[str, Any], native: NativeTools) -> str:
        raw_addresses = arguments.get("addresses", [])
        if not isinstance(raw_addresses, list):
            return "addresses must be a list."
        emit_tool_started("fanout_investigate", f"Preparing parallel reviews for up to {len(raw_addresses)} function(s)")
        focus = str(arguments.get("focus", "Review this function."))[:800]
        snapshots = native.snapshots([str(address) for address in raw_addresses])
        if not snapshots:
            return "No functions could be resolved for independent review."
        workers = min(max(1, self.settings.parallel_jobs), len(snapshots))
        results: dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="silvergun-review") as pool:
            futures = {pool.submit(self._review_snapshot, snapshot, focus): snapshot["address"] for snapshot in snapshots}
            for future in as_completed(futures):
                address = futures[future]
                try:
                    results[address] = future.result()
                except Exception as error:
                    results[address] = f"Review failed: {error}"
        ordered = [{"address": snapshot["address"], "review": results[snapshot["address"]]} for snapshot in snapshots]
        return json.dumps({"focus": focus, "parallel_reviews": ordered}, separators=(",", ":"))

    def _review_snapshot(self, snapshot: dict[str, Any], focus: str) -> str:
        prompt = (
            "Answer in at most 220 words. Perform a read-only independent review. "
            "List evidence, likely interpretation, and any uncertainty. Do not call tools.\n\n"
            f"Focus: {focus}\n\nFunction snapshot:\n{json.dumps(snapshot, separators=(',', ':'))}"
        )
        completion = self.client.chat(self.settings.model, [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}], (), max_tokens=500)
        return completion.content.strip() or "No review returned."

    @staticmethod
    def _request_message(request: str, route: Route, context_hint: str, notebook_context: str = "", registry: CapabilityRegistry | None = None, plan=None, conversation_context: str = "") -> str:
        extension_section = ""
        if route.external:
            cards = "\n".join(capability.card() for capability in route.external)
            extension_section = f"\n\nRelevant installed-plugin capabilities:\n{cards}"
        capability_section = ""
        if registry is not None and plan is not None:
            cards = "\n".join(registry.get(step.capability_id).card() for step in plan.steps if registry.get(step.capability_id))
            steps = " → ".join(step.capability_id for step in plan.steps)
            capability_section = f"\n\nValidated capability plan (use only these available capabilities):\n{steps}\n{cards}"
        guidance = ROUTE_GUIDANCE.get(route.intent, "Gather the smallest relevant evidence before answering and state uncertainty explicitly.")
        case_section = f"\n\nRestored local case-file context (treat as leads and re-verify):\n{notebook_context}" if notebook_context and not notebook_context.startswith("No notebook") else ""
        conversation_section = f"\n\nConversation context (use only to understand this follow-up; re-verify with tools):\n{conversation_context[:8000]}" if conversation_context else ""
        return f"BinaryView context: {context_hint}\n\nRequest: {request}\nRouted intent: {route.intent}.\nOperational directive: {guidance}{capability_section}{case_section}{extension_section}{conversation_section}"


def _tool_call(call: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    function = call.get("function")
    if not isinstance(function, dict):
        raise ValueError("provider supplied malformed tool call")
    name = function.get("name")
    if not isinstance(name, str):
        raise ValueError("tool call had no name")
    name = TOOL_ALIASES.get(name.strip(), name.strip())
    raw = function.get("arguments", "{}")
    arguments = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(arguments, dict):
        raise ValueError("tool arguments must be an object")
    if name == "bn_search_strings" and "query" not in arguments and "pattern" in arguments:
        arguments = dict(arguments)
        arguments["query"] = arguments.pop("pattern")
    return name, arguments


def _normalized_tool_call(call: dict[str, Any], round_number: int, index: int) -> dict[str, Any]:
    normalized = dict(call)
    normalized["id"] = str(call.get("id") or f"call_{round_number}_{index}")
    return normalized
