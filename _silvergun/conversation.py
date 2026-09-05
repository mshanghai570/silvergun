"""Conversation-layer presentation for Silvergun investigations.

The investigation engine owns routing, planning, execution, and evidence.  This
module owns only user-facing conversation state and prose so internal activity
cannot accidentally become the canonical answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class ConversationState:
    """Small per-conversation context used for follow-up investigations."""

    last_request: str = ""
    last_answer: str = ""
    last_intent: str = ""
    history: list[tuple[str, str]] = field(default_factory=list)

    def remember(self, request: str, answer: str, intent: str) -> None:
        self.last_request = request
        self.last_answer = answer
        self.last_intent = intent
        self.history.append((request, answer))
        del self.history[:-6]

    def context_for_follow_up(self) -> str:
        if not self.last_answer:
            return ""
        return f"Previous Silvergun answer (use as context, not as fresh evidence):\n{self.last_answer[:8000]}"


def acknowledgement(request: str, intent: str, capabilities: Iterable[str]) -> str:
    """Create a request-specific acknowledgement from the selected route.

    This is intentionally deterministic and capability-aware: it is a
    conversational hand-off, not an execution status message or a claim about
    evidence that has not yet been collected.
    """
    text = " ".join(request.split()).strip()
    subject = _subject(text)
    tools = tuple(dict.fromkeys(capabilities))
    tool_set = set(tools)

    if "bn_search_strings" in tool_set:
        action = f"search the binary's strings for {subject}"
    elif "bn_search_symbols" in tool_set or "bn_find_functions" in tool_set:
        action = f"search the binary for functions and symbols related to {subject}"
    elif "semantic_search" in tool_set or "query_binary" in tool_set:
        action = f"rank the binary's functions for {subject}"
    elif intent in {"map", "continue"} or "get_xrefs" in tool_set or "bn_find_cross_references" in tool_set:
        action = f"trace the relevant callers and callees for {subject}"
    else:
        action = f"investigate {subject}"

    if "get_xrefs" in tool_set or "bn_find_cross_references" in tool_set or intent in {"category", "investigate", "map"}:
        detail = " Then I’ll trace the strongest matches through their callers and callees and distinguish direct Binary Ninja evidence from interpretation."
    else:
        detail = " I’ll ground the answer in the evidence collected from the binary and call out uncertainty."
    return f"Sure — I’ll {action}.{detail}"


def _subject(request: str) -> str:
    lowered = request.lower()
    for marker in ("related to ", "for ", "about ", "matching ", "around "):
        if marker in lowered:
            index = lowered.rfind(marker)
            candidate = request[index + len(marker):].strip(" .?!")
            if candidate:
                return candidate[:100]
    return "your request" if not request else request[:100].rstrip(" .?!")


__all__ = ["ConversationState", "acknowledgement"]
