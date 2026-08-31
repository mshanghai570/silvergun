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
Use supplied tools before making binary-specific claims. State evidence and uncertainty.
Never claim that a mutation occurred unless a tool reports it. Do not reveal hidden reasoning;
return only a short, useful analyst answer with concrete next actions when appropriate."""


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
            {"role": "user", "content": self._request_message(request, route)},
        ]
        executed: set[str] = set()
        for round_number in range(1, self.settings.max_steps + 1):
            completion = self.client.chat(self.settings.model, messages, tools)
            if not completion.tool_calls:
                answer = completion.content.strip() or "The model returned no answer."
                return AgentResult(answer, route.intent, round_number)
            messages.append({"role": "assistant", "content": completion.content or "", "tool_calls": list(completion.tool_calls)})
            for call in completion.tool_calls[:6]:
                name, arguments = _tool_call(call)
                call_id = str(call.get("id", "call_missing_id"))
                signature = f"{name}:{json.dumps(arguments, sort_keys=True, separators=(',', ':'))}"
                if signature in executed:
                    result = "Skipped duplicate tool call. Use the previous result."
                else:
                    executed.add(signature)
                    result = self._execute(name, arguments, native)
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
    def _request_message(request: str, route: Route) -> str:
        extension_section = ""
        if route.external:
            cards = "\n".join(capability.card() for capability in route.external)
            extension_section = f"\n\nRelevant installed-plugin capabilities:\n{cards}"
        return f"Request: {request}\nRouted intent: {route.intent}.{extension_section}"


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
