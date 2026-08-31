"""Bounded OpenAI-compatible tool agent with a deterministic capability router."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import json
from typing import Any

from .client import OpenAICompatibleClient, ProviderError
from .router import CapabilityRouter, Route
from .tools import NativeTools


SYSTEM_PROMPT = """You are Silvergun, a concise Binary Ninja reverse-engineering partner.
A live BinaryView context header is supplied with each request. Treat it as authoritative host context.
Use supplied tools before making binary-specific claims and cite their evidence in your answer. Clearly
separate PROVEN host facts from INFERRED interpretations and HYPOTHESES. When an address is supplied, use it as a host
address with the 0x prefix; do not invent a different format or ask whether the binary is loaded when
binary_view_attached is true. Omit the address when asking for the current function. State evidence and
uncertainty. Use semantic_search or query_binary for stripped-binary triage, get_verification for trust
checks, code_map for relationships, and notebook tools for durable findings. Never claim that a mutation
occurred unless a tool reports it. Do not reveal hidden reasoning; return only a short, useful analyst
answer with concrete next actions when appropriate."""

ROUTE_GUIDANCE = {
    "triage": "Triage locally first; return a ranked shortlist with the exact matching evidence for each function.",
    "verify": "Verify before interpreting; label every statement PROVEN, INFERRED, or HYPOTHESIS and cite a host source.",
    "map": "Build the relationship map before explaining control flow; distinguish observed edges from behavioral guesses.",
    "notebook": "Use the notebook as durable context and record only concise findings with evidence and confidence.",
    "vulnerabilities": "Treat detector hits as leads only; report the matched operation, reachability question, and missing proof.",
    "investigate": "Decompose the objective into bounded, evidence-producing sub-investigations and synthesize only after tool results.",
}


@dataclass(frozen=True)
class AgentResult:
    answer: str
    intent: str
    rounds: int


class LeanAgent:
    """A small agent loop with a hard tool-round budget and no planning model call."""

    def __init__(self, client: OpenAICompatibleClient, settings) -> None:
        self.client = client
        self.settings = settings
        self.router = CapabilityRouter()

    def run(self, request: str, native: NativeTools) -> AgentResult:
        route = self.router.route(request, native.capabilities)
        tools = native.definitions(route.tools)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": self._request_message(request, route, native.context_hint(), native.notebook_context())},
        ]
        executed: set[str] = set()
        for round_number in range(1, self.settings.max_steps + 1):
            completion = self.client.chat(self.settings.model, messages, tools)
            if not completion.tool_calls:
                answer = completion.content.strip() or "The model returned no answer."
                return AgentResult(answer, route.intent, round_number)
            calls = [_normalized_tool_call(call, round_number, index) for index, call in enumerate(completion.tool_calls, start=1)]
            messages.append({"role": "assistant", "content": completion.content or "", "tool_calls": calls})
            for call in calls[:6]:
                call_id = str(call["id"])
                try:
                    name, arguments = _tool_call(call)
                    signature = f"{name}:{json.dumps(arguments, sort_keys=True, separators=(',', ':'))}"
                    if signature in executed:
                        result = "Skipped duplicate tool call. Use the previous result."
                    else:
                        executed.add(signature)
                        result = self._execute(name, arguments, native)
                except (TypeError, ValueError, json.JSONDecodeError) as error:
                    # A single malformed provider tool call must not abort the
                    # entire user request. Return a concise correction so the
                    # model can continue with a valid call or a direct answer.
                    result = f"Tool request rejected: {error}. Continue with a valid tool call or answer directly."
                messages.append({"role": "tool", "tool_call_id": call_id, "content": result})
        final = self.client.chat(self.settings.model, messages, ())
        answer = final.content.strip() or "Tool budget reached. Review the collected tool results."
        return AgentResult(answer, route.intent, self.settings.max_steps)

    def _execute(self, name: str, arguments: dict[str, Any], native: NativeTools) -> str:
        try:
            if name == "fanout_investigate":
                return self._fanout(arguments, native)
            return native.execute(name, arguments)
        except (ProviderError, KeyError, ValueError, TypeError) as error:
            return f"Tool error: {error}"
        except Exception as error:
            return f"Unexpected tool error: {error}"

    def _fanout(self, arguments: dict[str, Any], native: NativeTools) -> str:
        raw_addresses = arguments.get("addresses", [])
        if not isinstance(raw_addresses, list):
            return "addresses must be a list."
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
    def _request_message(request: str, route: Route, context_hint: str, notebook_context: str = "") -> str:
        extension_section = ""
        if route.external:
            cards = "\n".join(capability.card() for capability in route.external)
            extension_section = f"\n\nRelevant installed-plugin capabilities:\n{cards}"
        guidance = ROUTE_GUIDANCE.get(route.intent, "Gather the smallest relevant evidence before answering and state uncertainty explicitly.")
        case_section = f"\n\nRestored local case-file context (treat as leads and re-verify):\n{notebook_context}" if notebook_context and not notebook_context.startswith("No notebook") else ""
        return f"BinaryView context: {context_hint}\n\nRequest: {request}\nRouted intent: {route.intent}.\nOperational directive: {guidance}{case_section}{extension_section}"


def _tool_call(call: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    function = call.get("function")
    if not isinstance(function, dict):
        raise ValueError("provider supplied malformed tool call")
    name = function.get("name")
    if not isinstance(name, str):
        raise ValueError("tool call had no name")
    raw = function.get("arguments", "{}")
    arguments = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(arguments, dict):
        raise ValueError("tool arguments must be an object")
    return name, arguments


def _normalized_tool_call(call: dict[str, Any], round_number: int, index: int) -> dict[str, Any]:
    """Give incomplete compatible-provider calls a transcript-safe identifier."""
    normalized = dict(call)
    normalized["id"] = str(call.get("id") or f"call_{round_number}_{index}")
    return normalized
