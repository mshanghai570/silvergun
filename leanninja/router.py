"""Deterministic, compact capability selection for Lean Ninja."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Sequence


@dataclass(frozen=True)
class ExternalCapability:
    """A compact card for an installed plugin command."""

    identifier: str
    name: str
    description: str
    mutation_risk: bool = True

    def card(self) -> str:
        risk = "may modify analysis" if self.mutation_risk else "read-only"
        return f"{self.identifier}: {self.name} — {self.description[:180]} ({risk})"


@dataclass(frozen=True)
class Route:
    intent: str
    tools: tuple[str, ...]
    external: tuple[ExternalCapability, ...]


# The first tool is always a compact snapshot; the rest are intent-specific.
INTENTS: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("patch", ("patch", "fix", "nop", "modify", "instrument"), ("get_function_context", "apply_patch")),
    ("explain", ("explain", "understand", "what does", "walk through"), ("get_function_context", "get_xrefs")),
    ("rename", ("rename", "name this", "better name", "symbol name"), ("get_function_context", "rename_function")),
    ("types", ("type", "signature", "prototype", "parameter", "return type", "struct"), ("get_function_context", "get_type_evidence", "apply_function_type")),
    ("xrefs", ("xref", "cross reference", "caller", "callee", "call graph"), ("get_function_context", "get_xrefs")),
    ("annotate", ("annotate", "comment", "document", "tag"), ("get_function_context", "annotate_function")),
    ("vulnerabilities", ("vulnerability", "vulnerable", "exploit", "overflow", "use after", "uaf", "taint", "security"), ("get_function_context", "get_xrefs", "review_vulnerabilities")),
    ("investigate", ("investigate", "audit", "review", "find all", "multiple functions"), ("find_functions", "fanout_investigate")),
    ("plugins", ("plugin", "extension", "capability", "command"), ("get_function_context", "search_capabilities", "invoke_external_command")),
)


class CapabilityRouter:
    """Routes by local keyword scoring rather than a separate LLM call."""

    def __init__(self, max_external: int = 4) -> None:
        self._max_external = max(1, max_external)

    def route(self, request: str, capabilities: Sequence[ExternalCapability]) -> Route:
        normalized = re.sub(r"\s+", " ", request.lower()).strip()
        best_intent = "general"
        selected = ("get_function_context", "search_capabilities")
        best_score = 0
        for intent, terms, tools in INTENTS:
            score = sum(1 for term in terms if term in normalized)
            if score > best_score:
                best_intent, selected, best_score = intent, tools, score
        external = self._rank_external(normalized, capabilities)
        if external and "invoke_external_command" not in selected:
            selected = (*selected, "invoke_external_command")
        return Route(best_intent, tuple(dict.fromkeys(selected)), external)

    def _rank_external(self, request: str, capabilities: Iterable[ExternalCapability]) -> tuple[ExternalCapability, ...]:
        generic = {"plugin", "plugins", "extension", "extensions", "capability", "capabilities", "command", "commands", "other", "another", "available", "using", "use"}
        tokens = set(re.findall(r"[a-z0-9_]{3,}", request)) - generic
        if not tokens:
            return ()
        ranked: list[tuple[int, ExternalCapability]] = []
        for capability in capabilities:
            haystack = f"{capability.name} {capability.description}".lower()
            score = sum(1 for token in tokens if token in haystack)
            if score:
                ranked.append((score, capability))
        ranked.sort(key=lambda item: (-item[0], item[1].name.lower()))
        return tuple(item[1] for item in ranked[: self._max_external])


def capability_digest(capabilities: Sequence[ExternalCapability], *, limit: int = 1200) -> str:
    """Produce a capped catalog only for explicit capability discovery."""
    cards = [capability.card() for capability in capabilities]
    text = "\n".join(cards)
    return text[:limit] + ("\n…" if len(text) > limit else "")
