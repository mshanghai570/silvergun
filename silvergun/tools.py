"""Native Binary Ninja tools with compact reads and explicitly approved mutations."""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from binaryninja import log_warn
from binaryninja.interaction import get_choice_input
from binaryninja.mainthread import execute_on_main_thread_and_wait, is_main_thread

from .external import ExternalCommandIndex
from .router import ExternalCapability, capability_digest


MAX_ITEMS = 64
MAX_IL_LINES = 180


def _main_thread(func):
    """Run UI and mutation work on the host UI thread, returning its value."""
    def wrapper(*args, **kwargs):
        if is_main_thread():
            return func(*args, **kwargs)
        result = {}
        def invoke():
            result["value"] = func(*args, **kwargs)
        execute_on_main_thread_and_wait(invoke)
        return result.get("value")
    return wrapper


def _function_schema(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required or [], "additionalProperties": False},
        },
    }


TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "get_function_context": _function_schema("get_function_context", "Get a compact HLIL, metadata, variable, and edge snapshot. Use this before making claims.", {"address": {"type": "string", "description": "Optional hexadecimal function address; current function when omitted."}}),
    "find_functions": _function_schema("find_functions", "Find functions whose name contains the query.", {"query": {"type": "string"}, "max_results": {"type": "integer", "minimum": 1, "maximum": 32}} , ["query"]),
    "get_xrefs": _function_schema("get_xrefs", "Get compact caller and callee evidence for a function.", {"address": {"type": "string", "description": "Optional hexadecimal function address."}}),
    "get_type_evidence": _function_schema("get_type_evidence", "Get the current signature and parameter/local type evidence.", {"address": {"type": "string", "description": "Optional hexadecimal function address."}}),
    "review_vulnerabilities": _function_schema("review_vulnerabilities", "Run a deterministic first-pass check for risky calls, formatting, memory, and integer hints; report evidence, not certainty.", {"address": {"type": "string", "description": "Optional hexadecimal function address."}}),
    "fanout_investigate": _function_schema("fanout_investigate", "Request independent read-only reviews of several functions. The execution layer snapshots first, then runs bounded remote work in parallel.", {"addresses": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 8}, "focus": {"type": "string", "description": "Question each review should answer."}}, ["addresses", "focus"]),
    "search_capabilities": _function_schema("search_capabilities", "Search the compact index of compatible installed Binary Ninja plugin commands.", {"query": {"type": "string"}}, ["query"]),
    "invoke_external_command": _function_schema("invoke_external_command", "Invoke a capability from another installed Binary Ninja plugin. Always requires user approval.", {"capability_id": {"type": "string"}}, ["capability_id"]),
    "apply_patch": _function_schema("apply_patch", "Write a proposed byte patch. Always shows the user exact before/after bytes for approval.", {"address": {"type": "string", "description": "Patch start address in hexadecimal."}, "bytes_hex": {"type": "string", "description": "Replacement bytes, hexadecimal pairs only."}, "reason": {"type": "string"}}, ["address", "bytes_hex", "reason"]),
    "rename_function": _function_schema("rename_function", "Rename a function after user approval.", {"address": {"type": "string"}, "name": {"type": "string", "minLength": 1, "maxLength": 160}, "reason": {"type": "string"}}, ["name", "reason"]),
    "apply_function_type": _function_schema("apply_function_type", "Apply a C-like function declaration after user approval. Use only a complete declaration.", {"address": {"type": "string"}, "declaration": {"type": "string", "minLength": 3, "maxLength": 800}, "reason": {"type": "string"}}, ["declaration", "reason"]),
    "annotate_function": _function_schema("annotate_function", "Set a concise function comment and optional tag after user approval.", {"address": {"type": "string"}, "comment": {"type": "string", "minLength": 1, "maxLength": 4000}, "tag": {"type": "string", "maxLength": 120}}, ["comment"]),
}


class NativeTools:
    """Executes native tools against one view and an optional selected function."""

    def __init__(self, bv, function, external: ExternalCommandIndex, max_context_chars: int) -> None:
        self.bv = bv
        self.function = function
        self.external = external
        self.max_context_chars = max(4000, max_context_chars)
        self.capabilities: list[ExternalCapability] = external.refresh(bv, function)

    def definitions(self, names: tuple[str, ...]) -> list[dict[str, Any]]:
        return [TOOL_SCHEMAS[name] for name in names if name in TOOL_SCHEMAS]

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        actions: dict[str, Callable[[dict[str, Any]], str]] = {
            "get_function_context": self._context,
            "find_functions": self._find_functions,
            "get_xrefs": self._xrefs,
            "get_type_evidence": self._type_evidence,
            "review_vulnerabilities": self._vulnerability_hints,
            "search_capabilities": self._search_capabilities,
            "invoke_external_command": self._invoke_external,
            "apply_patch": self._apply_patch,
            "rename_function": self._rename,
            "apply_function_type": self._apply_type,
            "annotate_function": self._annotate,
        }
        if name not in actions:
            raise KeyError(f"Unknown or agent-managed tool: {name}")
        return _cap(actions[name](arguments), self.max_context_chars)

    def snapshots(self, addresses: list[str]) -> list[dict[str, Any]]:
        """Build immutable snapshots on the Binary Ninja side before remote fan-out."""
        unique: list[int] = []
        for raw in addresses:
            try:
                address = _address(raw, self.function.start if self.function else None)
            except ValueError:
                continue
            if address not in unique:
                unique.append(address)
        snapshots: list[dict[str, Any]] = []
        for address in unique[:8]:
            func = self._function_at(address)
            if func is not None:
                snapshots.append(self._snapshot(func))
        return snapshots

    def _context(self, args: dict[str, Any]) -> str:
        func = self._resolve(args)
        if func is None:
            return "No function exists at that address."
        return json.dumps(self._snapshot(func), separators=(",", ":"))

    def _find_functions(self, args: dict[str, Any]) -> str:
        query = str(args.get("query", "")).strip().lower()
        limit = min(MAX_ITEMS, max(1, int(args.get("max_results", 12))))
        matches = [
            {"address": hex(func.start), "name": func.name, "size": getattr(func, "total_bytes", 0)}
            for func in self.bv.functions
            if query in func.name.lower()
        ][:limit]
        return json.dumps({"query": query, "matches": matches}, separators=(",", ":"))

    def _xrefs(self, args: dict[str, Any]) -> str:
        func = self._resolve(args)
        if func is None:
            return "No function exists at that address."
        return json.dumps({"function": hex(func.start), "callers": _edge_list(getattr(func, "callers", [])), "callees": _edge_list(getattr(func, "callees", []))}, separators=(",", ":"))

    def _type_evidence(self, args: dict[str, Any]) -> str:
        func = self._resolve(args)
        if func is None:
            return "No function exists at that address."
        variables = []
        for variable in list(getattr(func, "parameter_vars", [])) + list(getattr(func, "vars", [])):
            variables.append({"name": variable.name, "type": str(variable.type), "source": str(variable.source_type), "storage": str(variable.storage)})
            if len(variables) >= MAX_ITEMS:
                break
        return json.dumps({"function": hex(func.start), "signature": str(func.type), "variables": variables}, separators=(",", ":"))

    def _vulnerability_hints(self, args: dict[str, Any]) -> str:
        func = self._resolve(args)
        if func is None:
            return "No function exists at that address."
        snapshot = self._snapshot(func)
        text = snapshot.get("hlil", "").lower()
        patterns = {
            "unbounded-copy": ("strcpy", "strcat", "gets"),
            "format-string": ("printf", "fprintf", "sprintf", "syslog"),
            "memory-copy": ("memcpy", "memmove", "read", "recv"),
            "allocation": ("malloc", "calloc", "realloc", "free"),
            "command-execution": ("system", "popen", "exec"),
        }
        hints = [{"class": category, "matched": [needle for needle in needles if needle in text]} for category, needles in patterns.items() if any(needle in text for needle in needles)]
        return json.dumps({"function": hex(func.start), "heuristic_hints": hints, "note": "Heuristics are leads only. Verify source/sink reachability and bounds in the IL."}, separators=(",", ":"))

    def _search_capabilities(self, args: dict[str, Any]) -> str:
        query = str(args.get("query", "")).lower().strip()
        matches = [capability for capability in self.capabilities if query in f"{capability.name} {capability.description}".lower()]
        return capability_digest(matches[:12], limit=2200) or "No compatible installed plugin commands matched."

    @_main_thread
    def _invoke_external(self, args: dict[str, Any]) -> str:
        identifier = str(args.get("capability_id", ""))
        capability = next((item for item in self.capabilities if item.identifier == identifier), None)
        if capability is None:
            return "That plugin capability is not available in the current context."
        if not self._confirm("Run External Plugin Command", f"Run '{capability.name}'?\n\n{capability.description}\n\nExternal commands may modify the current analysis."):
            return "User declined the external plugin command."
        return self.external.execute(identifier, self.bv, self.function)

    @_main_thread
    def _apply_patch(self, args: dict[str, Any]) -> str:
        try:
            address = _address(str(args.get("address", "")), None)
            replacement = _hex_bytes(str(args.get("bytes_hex", "")))
        except ValueError as error:
            return f"Invalid patch request: {error}"
        original = bytes(self.bv.read(address, len(replacement)))
        reason = str(args.get("reason", ""))
        prompt = f"Apply patch at {hex(address)}?\n\nBefore: {original.hex(' ')}\nAfter:  {replacement.hex(' ')}\n\nReason: {reason}"
        if not self._confirm("Apply Silvergun Patch", prompt):
            return "User declined the patch."
        written = self.bv.write(address, replacement)
        return f"Patch {'applied' if written == len(replacement) else 'partially applied'} at {hex(address)} ({written}/{len(replacement)} bytes)."

    @_main_thread
    def _rename(self, args: dict[str, Any]) -> str:
        func = self._resolve(args)
        name = str(args.get("name", "")).strip()
        if func is None or not name:
            return "A valid function and non-empty name are required."
        if not self._confirm("Rename Function", f"Rename {func.name} at {hex(func.start)} to {name}?\n\nReason: {args.get('reason', '')}"):
            return "User declined the rename."
        func.name = name
        return f"Renamed function at {hex(func.start)} to {name}."

    @_main_thread
    def _apply_type(self, args: dict[str, Any]) -> str:
        func = self._resolve(args)
        declaration = str(args.get("declaration", "")).strip()
        if func is None or not declaration:
            return "A valid function and complete declaration are required."
        if not self._confirm("Apply Function Type", f"Apply this type to {func.name} at {hex(func.start)}?\n\n{declaration}\n\nReason: {args.get('reason', '')}"):
            return "User declined the type change."
        try:
            parsed = self.bv.parse_type_string(declaration)
            func.type = parsed[0] if isinstance(parsed, tuple) else parsed
        except Exception as error:
            return f"Binary Ninja could not parse the declaration: {error}"
        return f"Applied type to {func.name}: {declaration}"

    @_main_thread
    def _annotate(self, args: dict[str, Any]) -> str:
        func = self._resolve(args)
        comment = str(args.get("comment", "")).strip()
        tag = str(args.get("tag", "")).strip()
        if func is None or not comment:
            return "A valid function and non-empty comment are required."
        if not self._confirm("Annotate Function", f"Set comment on {func.name} at {hex(func.start)}?\n\n{comment}"):
            return "User declined the annotation."
        func.comment = comment
        if tag:
            try:
                func.add_tag("Silvergun", tag)
            except Exception as error:
                log_warn(f"Comment applied but tag could not be added: {error}", "Silvergun")
        return f"Annotated {func.name}."

    def _resolve(self, args: dict[str, Any]):
        raw = args.get("address")
        if raw in (None, ""):
            return self.function
        try:
            return self._function_at(_address(str(raw), self.function.start if self.function else None))
        except ValueError:
            return None

    def _function_at(self, address: int):
        return self.bv.get_function_at(address) or self.bv.get_function_containing(address)

    def _snapshot(self, func) -> dict[str, Any]:
        il_lines = []
        try:
            for block in func.hlil:
                for instruction in block:
                    il_lines.append(f"{hex(instruction.address)}: {instruction}")
                    if len(il_lines) >= MAX_IL_LINES:
                        raise StopIteration
        except StopIteration:
            pass
        except Exception as error:
            il_lines.append(f"<HLIL unavailable: {error}>")
        variables = []
        for variable in list(getattr(func, "parameter_vars", [])) + list(getattr(func, "vars", [])):
            variables.append(f"{variable.name}: {variable.type}")
            if len(variables) >= 24:
                break
        return {
            "address": hex(func.start),
            "name": func.name,
            "size": getattr(func, "total_bytes", 0),
            "signature": str(func.type),
            "parameters_and_locals": variables,
            "callers": _edge_list(getattr(func, "callers", []), limit=16),
            "callees": _edge_list(getattr(func, "callees", []), limit=16),
            "hlil": "\n".join(il_lines),
        }

    @staticmethod
    def _confirm(title: str, text: str) -> bool:
        return get_choice_input(text, title, ["Cancel", "Approve"]) == 1


def _edge_list(functions, limit: int = MAX_ITEMS) -> list[dict[str, Any]]:
    return [{"address": hex(func.start), "name": func.name} for func in list(functions)[:limit]]


def _address(value: str, default: int | None) -> int:
    value = value.strip()
    if not value and default is not None:
        return default
    if not value:
        raise ValueError("address is required")
    return int(value, 0)


def _hex_bytes(value: str) -> bytes:
    normalized = re.sub(r"[^0-9a-fA-F]", "", value)
    if not normalized or len(normalized) % 2:
        raise ValueError("bytes_hex must contain complete hexadecimal byte pairs")
    return bytes.fromhex(normalized)


def _cap(value: str, limit: int) -> str:
    return value[:limit] + ("\n…[truncated]" if len(value) > limit else "")
