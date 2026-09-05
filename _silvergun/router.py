"""Deterministic, compact capability selection for Silvergun."""

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
    status: str = "CALLABLE"
    adapter: str = "plugin_command"

    def card(self) -> str:
        risk = "may modify analysis" if self.mutation_risk else "read-only"
        return f"{self.identifier}: {self.name} — {self.description[:180]} ({risk}; {self.status})"


@dataclass(frozen=True)
class Route:
    intent: str
    tools: tuple[str, ...]
    external: tuple[ExternalCapability, ...]


# Discovery terms that should prioritize search/analysis over mutation
DISCOVERY_TERMS = ("find", "search", "locate", "identify", "discover", "analyze", "audit", "review", "investigate", "scan", "detect")

# Mutation terms that indicate the user wants to modify
MUTATION_TERMS = ("patch", "fix", "nop", "modify", "instrument", "rename", "apply", "change", "bypass")

def _has_term(text: str, term: str) -> bool:
    term = term.strip().lower()
    return bool(term) and re.search(r"(?<![a-z0-9_])" + re.escape(term) + r"(?![a-z0-9_])", text) is not None


def _has_discovery_intent(text: str) -> bool:
    return any(_has_term(text, term) for term in DISCOVERY_TERMS)


def _has_mutation_intent(text: str) -> bool:
    return any(_has_term(text, term) for term in MUTATION_TERMS)


# The first tool is always a compact snapshot; the rest are intent-specific.
INTENTS: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("search", ("search", "locate", "identify", "discover", "look for", "functions for", "functions related", "plugin type", "find a plugin", "plugin that", "plugin which", "all plugins", "any plugin", "using a plugin"), ("get_function_context", "find_functions", "semantic_search", "query_binary", "get_xrefs", "search_capabilities", "invoke_external_command", "bn_search_strings", "bn_search_symbols", "bn_find_functions", "bn_find_cross_references", "boolhunter_quick_scan", "boolhunter_find_category", "boolhunter_analyze")),
    # Discovery intents (higher priority when discovery terms present)
    ("triage", ("semantic", "meaning", "stripped", "likely", "triage", "bnql", "query"), ("semantic_search", "query_binary", "get_verification")),
    ("continue", ("continue", "resume", "unresolved", "case file", "next evidence", "pick up", "where was i"), ("notebook_context", "notebook_search", "get_function_context", "get_xrefs", "semantic_search")),
    ("investigate", ("investigate", "audit", "review", "find all", "multiple functions", "analyze", "scan", "detect"), ("find_functions", "fanout_investigate", "boolhunter_quick_scan", "boolhunter_find_category")),
    ("category", ("category", "find functions related to", "find all", "purchase", "auth", "login", "logout", "network", "payment", "security", "validation", "storage", "premium", "unlock", "entitlement", "subscription", "license", "in-app", "iap"), ("semantic_search", "boolhunter_find_category")),
    ("boolean", ("boolean", "is_", "has_", "can_", "check_", "validate_", "enabled", "disabled", "is_active", "is_valid", "security check", "authentication check", "permission check"), ("boolhunter_quick_scan", "boolhunter_analyze", "get_function_context")),
    ("vulnerabilities", ("vulnerability", "vulnerabilities", "vuln", "vulnerable", "exploit", "overflow", "use after", "uaf", "taint", "security"), ("get_function_context", "get_xrefs", "review_vulnerabilities", "boolhunter_quick_scan")),
    ("strings", ("string", "strings", "url", "urls", "http", "https", "ascii", "password", "passwords", "secret", "secrets", "email", "domain", "hostname", "token", "apikey", "api key"), ("bn_search_strings", "find_functions", "get_xrefs")),
    ("symbols", ("symbol", "symbols", "imports", "import table", "exports", "exported", "function named", "functions named", "name search"), ("bn_search_symbols", "bn_find_functions", "find_functions", "semantic_search")),
    ("verify", ("verify", "evidence", "proven", "prove", "source", "grounded"), ("get_function_context", "get_xrefs", "get_verification")),
    ("map", ("code map", "map", "relationship", "execution path", "call graph"), ("get_function_context", "code_map", "boolhunter_batch_scan")),
    ("explain", ("explain", "understand", "what does", "walk through"), ("get_function_context", "get_xrefs")),
    ("annotate", ("annotate", "comment", "document", "tag"), ("get_function_context", "annotate_function")),
    ("types", ("type", "signature", "prototype", "parameter", "return type", "struct"), ("get_function_context", "get_type_evidence", "apply_function_type")),
    ("xrefs", ("xref", "cross reference", "caller", "callers", "callee", "callees", "call graph"), ("get_function_context", "get_xrefs")),
    # Mutation intents (lower priority when discovery terms also present)
    ("patch", ("patch", "fix", "nop", "modify", "instrument"), ("get_function_context", "apply_patch")),
    ("rename", ("rename", "name this", "better name", "symbol name"), ("get_function_context", "rename_function")),
    ("plugins", ("plugin", "extension", "capability", "command"), ("get_function_context", "search_capabilities", "invoke_external_command")),
    ("batch_scan", ("batch scan", "scan multiple", "scan all functions", "scan many", "analyze many"), ("boolhunter_batch_scan", "boolhunter_quick_scan")),
    ("binaryninja", ("binary ninja", "bn " , "native", "built-in", "internal"), ("bn_analyze", "bn_decompile", "bn_find_cross_references", "bn_search_strings", "bn_search_symbols", "bn_find_functions", "bn_get_metadata")),
    ("metadata", ("binary info", "binary metadata", "file info", "information about the currently opened binary", "information about the binary", "currently opened binary", "architecture", "platform", "entry point"), ("bn_get_metadata",)),
)


# Verb-to-tool mapping so compound goals ("find X and patch it") still receive
# the requested mutation capability alongside the discovery slice.
_MUTATION_VERB_TOOLS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("patch", "fix", "nop", "modify", "instrument", "bypass", "change", "apply"), ("apply_patch",)),
    (("rename",), ("rename_function",)),
    (("signature", "prototype", "parameter type", "return type"), ("apply_function_type",)),
    (("comment", "annotate", "tag", "document"), ("annotate_function",)),
)


def _mutation_tools(text: str) -> tuple[str, ...]:
    """Map mutation verbs in the request to concrete approval-gated tools."""
    tools: list[str] = []
    for verbs, mapped in _MUTATION_VERB_TOOLS:
        if any(_has_term(text, verb) for verb in verbs):
            tools.extend(mapped)
    return tuple(tools) or ("apply_patch",)


class CapabilityRouter:
    """Routes by local keyword scoring rather than a separate LLM call."""

    def __init__(self, max_external: int = 4) -> None:
        self._max_external = max(1, max_external)

    def route(self, request: str, capabilities: Sequence[ExternalCapability]) -> Route:
        normalized = re.sub(r"\s+", " ", request.lower()).strip()
        
        # Detect compound intent: discovery + mutation
        has_discovery = _has_discovery_intent(normalized)
        has_mutation = _has_mutation_intent(normalized)
        explicit_provider_search = any(_has_term(normalized, term) for term in ("all plugins", "any plugin", "find a plugin", "plugin that", "plugin which", "plugin type"))
        generic_function_search = normalized in ("search functions", "search for functions", "locate functions")
        named_plugin_request = bool(re.search(r"(?:use|using|with)\s+(?!(?:a|the)\s+)[a-z0-9][a-z0-9 _-]{2,}\s+plugin", normalized))
        explicit_smart_patch = any(_has_term(normalized, term) for term in ("smart patch", "precise patch", "patch this function"))
        explicit_xrefs = any(_has_term(normalized, term) for term in ("callers and callees", "caller and callee", "cross reference", "cross-reference"))
        
        best_intent = "general"
        selected = ("get_function_context", "search_capabilities")
        best_score = 0
        
        for intent, terms, tools in INTENTS:
            score = sum(1 for term in terms if _has_term(normalized, term))
            if explicit_provider_search and intent == "search":
                score += 3
            if named_plugin_request and intent == "search":
                score += 4
            if generic_function_search and intent == "search":
                score += 3
            if explicit_smart_patch and intent == "patch":
                score += 3
            if explicit_xrefs and intent == "xrefs":
                score += 5
            
            # Boost discovery intents when discovery terms are present
            if has_discovery and intent in ("triage", "continue", "investigate", "category", "boolean", "vulnerabilities", "map", "strings", "symbols"):
                score += 2
            
            # Deprioritize mutation intents when discovery terms are also present
            if has_discovery and has_mutation and intent in ("patch", "rename") and not explicit_smart_patch:
                score -= 2
                
            if score > best_score:
                best_intent, selected, best_score = intent, tools, score
        
        # If both discovery and mutation, ensure discovery tools are included
        if has_discovery and has_mutation:
            if best_intent in ("patch", "rename"):
                if explicit_smart_patch:
                    selected = ("get_function_context", "apply_patch")
                else:
                    # Prepend discovery tools
                    discovery_tools = ("find_functions", "semantic_search", "get_xrefs", "boolhunter_quick_scan", "boolhunter_find_category")
                    selected = tuple(dict.fromkeys(discovery_tools + selected))
            else:
                # A compound goal ("find the vulnerable functions and patch them")
                # must still carry the requested mutation tool even though a
                # discovery intent won the keyword score.
                selected = tuple(dict.fromkeys(selected + _mutation_tools(normalized)))
        
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
            if getattr(capability, "status", "CALLABLE") != "CALLABLE":
                continue
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
