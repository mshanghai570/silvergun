"""Structured capability catalog for Silvergun's adaptive planner."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CapabilityCatalog:
    name: str
    description: str
    category: str
    evidence_types: tuple[str, ...]
    cost_level: int
    prerequisites: tuple[str, ...]
    inputs: dict
    outputs: str
    best_for: tuple[str, ...]


CAPABILITY_CATALOG: dict[str, CapabilityCatalog] = {
    "get_function_context": CapabilityCatalog(
        name="get_function_context",
        description="Get a compact HLIL, metadata, variable, and edge snapshot",
        category="context",
        evidence_types=("il", "variables", "edges", "metadata"),
        cost_level=1,
        prerequisites=(),
        inputs={"address": "optional hex address"},
        outputs="function snapshot JSON",
        best_for=("any", "baseline", "starting_point"),
    ),
    "get_xrefs": CapabilityCatalog(
        name="get_xrefs",
        description="Get compact caller and callee evidence",
        category="relationships",
        evidence_types=("xrefs", "callers", "callees", "addresses"),
        cost_level=1,
        prerequisites=("get_function_context",),
        inputs={"address": "optional hex address"},
        outputs="xref JSON",
        best_for=("understanding_flow", "tracing_calls", "finding_usages"),
    ),
    "semantic_search": CapabilityCatalog(
        name="semantic_search",
        description="Rank functions by lexical meaning evidence from names, signatures, HLIL",
        category="search",
        evidence_types=("function_list", "names", "signatures", "scores"),
        cost_level=2,
        prerequisites=(),
        inputs={"query": "search terms", "max_results": "optional limit"},
        outputs="ranked function list",
        best_for=("triage", "finding_similar", "exploration"),
    ),
    "query_binary": CapabilityCatalog(
        name="query_binary",
        description="Run a bounded BNQL-style query on the binary",
        category="search",
        evidence_types=("function_list", "predicates", "addresses"),
        cost_level=1,
        prerequisites=(),
        inputs={"query": "BNQL query"},
        outputs="matching functions",
        best_for=("targeted_search", "filtered_results"),
    ),
    "code_map": CapabilityCatalog(
        name="code_map",
        description="Build a compact caller/callee relationship map",
        category="relationships",
        evidence_types=("nodes", "edges", "graph"),
        cost_level=2,
        prerequisites=("get_function_context",),
        inputs={"address": "root address", "depth": "optional traversal depth"},
        outputs="graph JSON",
        best_for=("understanding_structure", "call_graphs"),
    ),
    "get_verification": CapabilityCatalog(
        name="get_verification",
        description="Separate proven facts from inferred interpretations",
        category="verification",
        evidence_types=("proven", "inferred", "sources"),
        cost_level=1,
        prerequisites=("get_function_context",),
        inputs={"address": "optional hex address"},
        outputs="verified claims",
        best_for=("validation", "certainty_checking"),
    ),
    "review_vulnerabilities": CapabilityCatalog(
        name="review_vulnerabilities",
        description="Run deterministic first-pass vulnerability checks",
        category="security",
        evidence_types=("heuristics", "patterns", "risk_indicators"),
        cost_level=2,
        prerequisites=("get_function_context",),
        inputs={"address": "optional hex address"},
        outputs="vulnerability hints",
        best_for=("security_review", "vulnerability_hunting"),
    ),
    "fanout_investigate": CapabilityCatalog(
        name="fanout_investigate",
        description="Request independent read-only reviews of multiple functions in parallel",
        category="investigation",
        evidence_types=("reviews", "analyses", "findings"),
        cost_level=3,
        prerequisites=(),
        inputs={"addresses": "list of hex addresses", "focus": "review question"},
        outputs="parallel review results",
        best_for=("batch_analysis", "comparative_review"),
    ),
    "find_functions": CapabilityCatalog(
        name="find_functions",
        description="Find functions by name substring",
        category="search",
        evidence_types=("matches", "names", "addresses"),
        cost_level=1,
        prerequisites=(),
        inputs={"query": "name substring", "max_results": "optional limit"},
        outputs="matching functions",
        best_for=("targeted_search", "function_discovery"),
    ),
    "get_type_evidence": CapabilityCatalog(
        name="get_type_evidence",
        description="Get signature and parameter/local type evidence",
        category="types",
        evidence_types=("signature", "variables", "types"),
        cost_level=1,
        prerequisites=(),
        inputs={"address": "optional hex address"},
        outputs="type evidence JSON",
        best_for=("signature_recovery", "type_analysis"),
    ),
    "notebook_context": CapabilityCatalog(
        name="notebook_context",
        description="Load local case-file findings and progress",
        category="notebook",
        evidence_types=("findings", "progress", "history"),
        cost_level=1,
        prerequisites=(),
        inputs={},
        outputs="case context JSON",
        best_for=("continuity", "context_restoration"),
    ),
    "notebook_record": CapabilityCatalog(
        name="notebook_record",
        description="Record a structured finding locally for future reference",
        category="notebook",
        evidence_types=("finding", "evidence", "metadata"),
        cost_level=1,
        prerequisites=(),
        inputs={"title": "finding title", "note": "description", "kind": "finding type"},
        outputs="recorded confirmation",
        best_for=("documentation", "finding_tracking"),
    ),
    "disassemble": CapabilityCatalog(
        name="disassemble",
        description="Read instruction-level disassembly with raw bytes and lengths",
        category="disassembly",
        evidence_types=("instructions", "bytes", "addresses"),
        cost_level=1,
        prerequisites=(),
        inputs={"address": "optional hex address", "count": "instruction count"},
        outputs="instruction list JSON",
        best_for=("patching", "instruction_analysis", "byte_evidence"),
    ),
    "apply_assembly_patch": CapabilityCatalog(
        name="apply_assembly_patch",
        description="Assemble instructions and write them after approval, NOP-padding to instruction boundaries",
        category="patching",
        evidence_types=("patch", "original_bytes", "replacement_bytes", "verification"),
        cost_level=2,
        prerequisites=("disassemble", "get_function_context"),
        inputs={"address": "hex address", "assembly": "instruction text", "instructions": "optional original instruction count", "reason": "justification"},
        outputs="patch result JSON",
        best_for=("patching", "behavior_change", "smart_patch"),
    ),
    "patch_history": CapabilityCatalog(
        name="patch_history",
        description="List locally recorded Silvergun patches that can still be undone",
        category="patching",
        evidence_types=("patch", "history", "metadata"),
        cost_level=1,
        prerequisites=(),
        inputs={},
        outputs="patch journal JSON",
        best_for=("audit", "patching", "undo"),
    ),
    "undo_last_patch": CapabilityCatalog(
        name="undo_last_patch",
        description="Restore original bytes of the most recent Silvergun patch after approval",
        category="patching",
        evidence_types=("patch", "original_bytes"),
        cost_level=1,
        prerequisites=("patch_history",),
        inputs={},
        outputs="undo result JSON",
        best_for=("revert", "patching", "safety"),
    ),
    # Binary Ninja built-in tools
    "bn_analyze": CapabilityCatalog(
        name="bn_analyze",
        description="Run Binary Ninja's automatic analysis on the current binary or function",
        category="analysis",
        evidence_types=("analysis", "functions", "metadata"),
        cost_level=2,
        prerequisites=(),
        inputs={"address": "optional address", "function_only": "boolean", "full_analysis": "boolean"},
        outputs="analysis results",
        best_for=("binary_analysis", "function_analysis", "refresh_analysis"),
    ),
    "bn_decompile": CapabilityCatalog(
        name="bn_decompile",
        description="Decompile the current function or a specified function using Binary Ninja's decompiler",
        category="decompilation",
        evidence_types=("hlil", "decompilation", "pseudocode"),
        cost_level=3,
        prerequisites=(),
        inputs={"address": "optional address", "timeout": "seconds"},
        outputs="decompilation results",
        best_for=("decompilation", "pseudocode", "source_recovery"),
    ),
    "bn_find_cross_references": CapabilityCatalog(
        name="bn_find_cross_references",
        description="Find all cross-references to/from a specific address or function",
        category="xrefs",
        evidence_types=("callers", "callees", "xrefs", "addresses"),
        cost_level=1,
        prerequisites=(),
        inputs={"address": "hexadecimal address", "direction": "both/callers/callees", "max_depth": "integer"},
        outputs="cross-reference information",
        best_for=("xref_analysis", "call_graph", "caller_analysis", "callee_analysis"),
    ),
    "bn_search_strings": CapabilityCatalog(
        name="bn_search_strings",
        description="Search for strings in the binary and find their cross-references",
        category="search",
        evidence_types=("strings", "matches", "addresses", "xrefs"),
        cost_level=2,
        prerequisites=(),
        inputs={"query": "search string", "case_sensitive": "boolean", "regex": "boolean", "min_length": "integer"},
        outputs="string matches",
        best_for=("string_analysis", "hardcoded_secrets", "clues", "hints"),
    ),
    "bn_find_functions": CapabilityCatalog(
        name="bn_find_functions",
        description="Find functions in the binary using various criteria",
        category="search",
        evidence_types=("functions", "matches", "names", "addresses"),
        cost_level=2,
        prerequisites=(),
        inputs={"name_pattern": "regex", "min_size": "integer", "max_size": "integer", "has_calls": "boolean", "limit": "integer"},
        outputs="function matches",
        best_for=("function_discovery", "pattern_matching", "function_search"),
    ),
    "bn_get_comments": CapabilityCatalog(
        name="bn_get_comments",
        description="Get all comments in the current function or binary",
        category="comments",
        evidence_types=("comments", "annotations", "notes"),
        cost_level=1,
        prerequisites=(),
        inputs={"address": "optional address", "include_auto": "boolean"},
        outputs="comments",
        best_for=("comment_analysis", "documentation", "analyst_notes"),
    ),
    "bn_get_function_tags": CapabilityCatalog(
        name="bn_get_function_tags",
        description="Get all tags applied to functions in the binary",
        category="tags",
        evidence_types=("tags", "classifications", "labels"),
        cost_level=1,
        prerequisites=(),
        inputs={"filter": "optional tag filter", "address": "optional address"},
        outputs="tags",
        best_for=("tag_analysis", "classification", "categorization"),
    ),
    "bn_get_types": CapabilityCatalog(
        name="bn_get_types",
        description="Get type information from the binary including function signatures and variable types",
        category="types",
        evidence_types=("types", "signatures", "variables", "parameters"),
        cost_level=1,
        prerequisites=(),
        inputs={"address": "optional address", "include_references": "boolean"},
        outputs="type information",
        best_for=("type_recovery", "signature_analysis", "variable_types"),
    ),
    "bn_get_metadata": CapabilityCatalog(
        name="bn_get_metadata",
        description="Get binary metadata including architecture, platform, entry point, etc.",
        category="metadata",
        evidence_types=("filename", "architecture", "platform", "entry_point", "counts"),
        cost_level=1,
        prerequisites=(),
        inputs={},
        outputs="binary metadata",
        best_for=("binary_info", "architecture_analysis", "platform_analysis", "entry_point_analysis"),
    ),
}

CATEGORY_PATTERNS = {
    "boolean": ("boolean", "is_*", "has_*", "can_*", "validate", "enabled", "check", "flag", "toggle"),
    "authentication": ("auth", "login", "password", "credential", "token", "session", "verify", "validate"),
    "purchase": ("purchase", "buy", "subscription", "payment", "checkout", "cart", "order", "transaction"),
    "network": ("network", "http", "socket", "connect", "send", "receive", "request", "response"),
    "security": ("vulnerability", "exploit", "overflow", "injection", "bypass", "privilege", "root"),
    "data": ("file", "read", "write", "save", "load", "storage", "database", "serialize"),
}




def suggest_capabilities(category: str) -> list[str]:
    suggestions = []
    for name, cap in CAPABILITY_CATALOG.items():
        if category in cap.category or any(category in bf for bf in cap.best_for):
            suggestions.append(name)
    return suggestions


def get_capability_info(name: str) -> CapabilityCatalog | None:
    return CAPABILITY_CATALOG.get(name)


def get_capabilities_for_intent(intent: str) -> list[str]:
    intent_map = {
        "triage": ["semantic_search", "query_binary", "get_function_context", "bn_search_strings"],
        "investigate": ["get_function_context", "fanout_investigate", "get_xrefs", "bn_find_functions", "bn_find_cross_references"],
        "vulnerabilities": ["get_function_context", "review_vulnerabilities", "get_xrefs", "bn_search_strings"],
        "verify": ["get_function_context", "get_verification", "get_xrefs", "bn_get_types"],
        "map": ["get_function_context", "code_map", "get_xrefs", "bn_find_cross_references"],
        "patch": ["get_function_context", "disassemble", "apply_patch", "apply_assembly_patch", "patch_history", "undo_last_patch"],
        "explain": ["get_function_context", "get_xrefs", "get_type_evidence", "bn_decompile"],
        "boolhunter": ["boolhunter_quick_scan", "boolhunter_analyze", "boolhunter_batch_scan"],
        "bool_category": ["boolhunter_batch_scan", "boolhunter_find_category"],
        "binaryninja": ["bn_analyze", "bn_decompile", "bn_get_metadata", "bn_get_types"],
        "metadata": ["bn_get_metadata", "get_function_context"],
        "strings": ["bn_search_strings", "query_binary"],
        "functions": ["bn_find_functions", "semantic_search", "query_binary"],
    }
    return intent_map.get(intent, ["get_function_context"])
