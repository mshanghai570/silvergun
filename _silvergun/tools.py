"""Native Binary Ninja tools with compact reads and explicitly approved mutations."""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from binaryninja import log_warn
from binaryninja.interaction import get_choice_input
try:
    from binaryninja.mainthread import execute_on_main_thread_and_wait, is_main_thread
except ImportError:
    from binaryninja.mainthread import execute_on_main_thread_and_wait
    def is_main_thread() -> bool:
        return False

from .external import ExternalCommandIndex
from .notebook import AnalysisNotebook, Finding
from .router import ExternalCapability, capability_digest
from .events import emit_tool_started, emit_tool_progress, emit_tool_result, emit_tool_completed, emit_tool_failed


MAX_ITEMS = 64
MAX_TRIAGE_FUNCTIONS = 10000
MAX_IL_LINES = 180


def _on_main_thread(callback: Callable[[], Any]) -> Any:
    """Run all Binary Ninja API work on the host thread and return its result."""
    if is_main_thread():
        return callback()
    result: dict[str, Any] = {}

    def invoke() -> None:
        result["value"] = callback()

    execute_on_main_thread_and_wait(invoke)
    return result.get("value")


def _main_thread(func):
    """Marshal a Binary Ninja API operation to the host UI thread."""
    def wrapper(*args, **kwargs):
        return _on_main_thread(lambda: func(*args, **kwargs))
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
    "semantic_search": _function_schema("semantic_search", "Rank functions by meaning-like lexical evidence from names, signatures, and compact HLIL. Useful for stripped-binary triage.", {"query": {"type": "string"}, "max_results": {"type": "integer", "minimum": 1, "maximum": 24}}, ["query"]),
    "query_binary": _function_schema("query_binary", "Run a bounded local BNQL-style query: name~text, calls:text, has:text, or addr:0xADDRESS.", {"query": {"type": "string"}}, ["query"]),
    "get_verification": _function_schema("get_verification", "Separate host-proven facts from model inferences and attach source locators to the selected function.", {"address": {"type": "string", "description": "Optional hexadecimal function address."}}),
    "code_map": _function_schema("code_map", "Build a compact caller/callee relationship map for visual navigation.", {"address": {"type": "string"}, "depth": {"type": "integer", "minimum": 1, "maximum": 3}}, ["address"]),
    "notebook_context": _function_schema("notebook_context", "Load the latest local findings, counts, and analysis progress for this binary.", {}),
    "notebook_search": _function_schema("notebook_search", "Search local notebook records for a term or address.", {"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 50}}, ["query"]),
    "notebook_progress": _function_schema("notebook_progress", "Record or update local analysis progress for this binary.", {"phase": {"type": "string"}, "completed": {"type": "integer", "minimum": 0}, "total": {"type": "integer", "minimum": 0}, "note": {"type": "string"}}, ["phase"]),
    "notebook_record": _function_schema("notebook_record", "Record a structured finding locally for future investigations; never writes to the binary.", {"title": {"type": "string"}, "note": {"type": "string"}, "address": {"type": "string"}, "kind": {"type": "string", "enum": ["finding", "hypothesis", "question", "function", "tool_result"]}, "status": {"type": "string", "enum": ["open", "resolved", "blocked", "active"]}, "evidence": {"type": "array", "items": {"type": "object"}}, "related_functions": {"type": "array", "items": {"type": "string"}}, "xrefs": {"type": "array", "items": {"type": "string"}}, "strings": {"type": "array", "items": {"type": "string"}}, "il_refs": {"type": "array", "items": {"type": "string"}}, "search_refs": {"type": "array", "items": {"type": "string"}}, "plugin_results": {"type": "array", "items": {"type": "string"}}, "confidence": {"type": "string", "enum": ["proven", "inferred", "hypothesis"]}}, ["title", "note", "evidence"]),
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
        self._triage_index: list[tuple[Any, str, str]] | None = None
        # AgentTask runs on a BackgroundTaskThread. Plugin-command discovery and
        # every BinaryView access must be marshalled to Binary Ninja's API thread.
        self.capabilities: list[ExternalCapability] = _on_main_thread(lambda: external.refresh(bv, function))

    def definitions(self, names: tuple[str, ...]) -> list[dict[str, Any]]:
        return [TOOL_SCHEMAS[name] for name in names if name in TOOL_SCHEMAS]

    @_main_thread
    def context_hint(self) -> str:
        """Return small host metadata that prevents the model treating BN as detached."""
        filename = ""
        try:
            filename = str(getattr(getattr(self.bv, "file", None), "filename", ""))
        except Exception:
            pass
        platform = str(getattr(getattr(self.bv, "platform", None), "name", ""))
        image_base = getattr(self.bv, "start", None)
        entry = getattr(self.bv, "entry_point", None)
        current = self._snapshot(self.function) if self.function is not None else None

        file_format = ""
        try:
            file_format = str(getattr(self.bv, "file_format", ""))
        except Exception:
            pass

        architecture = ""
        try:
            arch = getattr(self.bv, "arch", None)
            if arch:
                architecture = f"{getattr(arch, 'name', '')}/{getattr(arch, 'size', '')}-bit"
        except Exception:
            pass

        analysis_state = "partial"
        try:
            analysis_state = "full" if getattr(self.bv, "analysis_changed", False) else "incremental"
        except Exception:
            pass

        payload = {
            "binary_view_attached": True,
            "binary_view_id": hex(id(self.bv)),
            "filename": filename,
            "platform": platform,
            "file_format": file_format,
            "architecture": architecture,
            "image_base": hex(image_base) if isinstance(image_base, int) else None,
            "entry_point": hex(entry) if isinstance(entry, int) else None,
            "function_count": len(getattr(self.bv, "functions", [])),
            "analysis_state": analysis_state,
            "current_function": current,
        }
        return json.dumps(payload, separators=(",", ":"))

    @_main_thread
    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        actions: dict[str, Callable[[dict[str, Any]], str]] = {
            "get_function_context": self._context,
            "find_functions": self._find_functions,
            "get_xrefs": self._xrefs,
            "get_type_evidence": self._type_evidence,
            "review_vulnerabilities": self._vulnerability_hints,
            "semantic_search": self._semantic_search,
            "query_binary": self._query_binary,
            "get_verification": self._verification,
            "code_map": self._code_map,
            "notebook_context": self._notebook_context,
            "notebook_search": self._notebook_search,
            "notebook_progress": self._notebook_progress,
            "notebook_record": self._notebook_record,
            "search_capabilities": self._search_capabilities,
            "invoke_external_command": self._invoke_external,
            "apply_patch": self._apply_patch,
            "rename_function": self._rename,
            "apply_function_type": self._apply_type,
            "annotate_function": self._annotate,
        }
        if name not in actions:
            raise KeyError(f"Unknown or agent-managed tool: {name}")
        
        # Emit tool started event
        emit_tool_started(name, f"Executing {name}")
        
        try:
            result = _cap(actions[name](arguments), self.max_context_chars)
            # Emit tool completed event
            emit_tool_completed(name, f"Completed {name}")
            return result
        except Exception as e:
            # Emit tool failed event
            emit_tool_failed(name, f"Failed: {name}", str(e))
            raise

    @_main_thread
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
        if len(query) < 3:
            # An empty substring matches every function name and teaches the
            # model nothing; steer it toward a useful query instead.
            return json.dumps({
                "error": "query must be a function-name substring of at least 3 characters.",
                "hint": "Pass a concrete fragment such as 'login', 'parse', or 'auth', or call semantic_search with natural-language terms to rank functions by meaning.",
                "query": query,
                "matches": [],
            }, separators=(",", ":"))
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

    def _semantic_search(self, args: dict[str, Any]) -> str:
        query = str(args.get("query", "")).strip().lower()
        terms = [term for term in re.findall(r"[a-z0-9_]{3,}", query) if term not in {"find", "show", "likely", "functions"}]
        limit = min(24, max(1, int(args.get("max_results", 10))))
        
        emit_tool_progress("semantic_search", f"Searching for: {', '.join(terms[:5])}")
        
        if not terms:
            return json.dumps({"query": query, "matches": [], "note": "Add at least one meaningful search term."}, separators=(",", ":"))
        ranked = []
        
        # Emit progress as we scan
        total_functions = len(self._triage_records())
        emit_tool_progress("semantic_search", f"Scanning {total_functions} functions for {len(terms)} terms")
        
        for i, (function, name, haystack) in enumerate(self._triage_records()):
            # Emit progress every 200 functions
            if i > 0 and i % 200 == 0:
                emit_tool_progress("semantic_search", f"Scanned {i}/{total_functions} functions")
            
            score = sum((3 if term in str(function.name).lower() else 1) for term in terms if term in haystack)
            if score:
                ranked.append((score, function))
        
        ranked.sort(key=lambda item: (-item[0], item[1].start))
        matches = [{"address": hex(function.start), "name": function.name, "score": score, "evidence": [f"HLIL/name/signature match for: {', '.join(terms)}"]} for score, function in ranked[:limit]]
        
        emit_tool_result("semantic_search", f"Found {len(matches)} matches for query: {query[:30]}...", {"count": len(matches)})
        
        return json.dumps({"query": query, "matches": matches, "method": "bounded lexical semantic triage; verify each result", "indexed_functions": total_functions, "total_functions": getattr(self, "_triage_total", total_functions), "truncated": bool(getattr(self, "_triage_truncated", False))}, separators=(",", ":"))

    def _query_binary(self, args: dict[str, Any]) -> str:
        query = str(args.get("query", "")).strip()
        lowered = query.lower()
        matches = []
        if lowered.startswith("addr:"):
            try:
                function = self._function_at(_address(query.split(":", 1)[1], None))
            except ValueError:
                function = None
            if function is not None:
                matches.append(self._result_row(function, "address predicate"))
        else:
            operator, _, value = lowered.partition(":")
            if operator not in {"name~", "calls", "has"}:
                operator, value = "has", lowered
            for function, name, haystack in self._triage_records():
                if (operator == "name~" and value in name) or (operator == "calls" and value in haystack) or (operator == "has" and value in f"{name} {haystack}"):
                    matches.append(self._result_row(function, f"{operator}:{value}"))
                    if len(matches) >= 32:
                        break
        indexed = self._triage_records()
        return json.dumps({"query": query, "matches": matches, "syntax": "name~:text | calls:text | has:text | addr:0xADDRESS", "indexed_functions": len(indexed), "total_functions": getattr(self, "_triage_total", len(indexed)), "truncated": bool(getattr(self, "_triage_truncated", False))}, separators=(",", ":"))

    def _verification(self, args: dict[str, Any]) -> str:
        func = self._resolve(args)
        if func is None:
            return json.dumps({"proven": [], "inferred": [], "status": "no target"}, separators=(",", ":"))
        snapshot = self._snapshot(func)
        return json.dumps({"status": "evidence attached", "proven": [{"claim": "Function exists in the active BinaryView", "source": f"BinaryView function table at {snapshot['address']}"}, {"claim": "Current signature", "value": snapshot["signature"], "source": f"Function.type at {snapshot['address']}"}, {"claim": "HLIL is available", "source": f"HLIL instructions at {snapshot['address']}" if snapshot["hlil"] else "No HLIL returned"}], "inferred": [{"claim": "Behavioral interpretation", "note": "Must be supported by the cited HLIL, xrefs, or memory evidence."}], "evidence": snapshot["evidence"]}, separators=(",", ":"))

    def _code_map(self, args: dict[str, Any]) -> str:
        root = self._resolve(args)
        if root is None:
            return json.dumps({"nodes": [], "edges": [], "status": "target not found"}, separators=(",", ":"))
        depth = min(3, max(1, int(args.get("depth", 1))))
        seen = {root.start: (root, 0)}
        frontier = [root]
        for level in range(depth):
            next_frontier = []
            for function in frontier:
                for neighbor in list(getattr(function, "callers", [])) + list(getattr(function, "callees", [])):
                    if neighbor.start not in seen:
                        seen[neighbor.start] = (neighbor, level + 1)
                        next_frontier.append(neighbor)
            frontier = next_frontier
        edges = []
        for function, _level in seen.values():
            for callee in getattr(function, "callees", []):
                if callee.start in seen:
                    edges.append({"from": hex(function.start), "to": hex(callee.start), "kind": "calls"})
        nodes = [{"address": hex(function.start), "name": function.name, "depth": level, "evidence": f"caller/callee relation from {hex(root.start)}"} for function, level in seen.values()]
        return json.dumps({"root": hex(root.start), "nodes": nodes, "edges": edges}, separators=(",", ":"))

    def _notebook_context(self, _args: dict[str, Any]) -> str:
        filename = str(getattr(getattr(self.bv, "file", None), "filename", ""))
        notebook = AnalysisNotebook(filename)
        return json.dumps({"summary": notebook.summary(), "recent": notebook.search("", 8)}, separators=(",", ":"))

    @_main_thread
    def notebook_context(self) -> str:
        """Return restored local case context without requiring a model tool call."""
        return self._notebook_context({})

    @_main_thread
    def mark_progress(self, phase: str, completed: int = 0, total: int = 0, note: str = "") -> str:
        return self._notebook_progress({"phase": phase, "completed": completed, "total": total, "note": note})

    def _notebook_search(self, args: dict[str, Any]) -> str:
        filename = str(getattr(getattr(self.bv, "file", None), "filename", ""))
        notebook = AnalysisNotebook(filename)
        return json.dumps({"query": str(args.get("query", "")), "matches": notebook.search(str(args.get("query", "")), int(args.get("limit", 20)))}, separators=(",", ":"))

    def _notebook_progress(self, args: dict[str, Any]) -> str:
        filename = str(getattr(getattr(self.bv, "file", None), "filename", ""))
        notebook = AnalysisNotebook(filename)
        progress = notebook.set_progress(str(args.get("phase", "active")), int(args.get("completed", 0)), int(args.get("total", 0)), str(args.get("note", "")))
        return json.dumps({"progress": progress, "summary": notebook.summary()}, separators=(",", ":"))

    def _notebook_record(self, args: dict[str, Any]) -> str:
        filename = str(getattr(getattr(self.bv, "file", None), "filename", ""))
        evidence = tuple(item if isinstance(item, dict) else {"kind": "unspecified", "locator": str(item)} for item in args.get("evidence", []) if item)
        record = AnalysisNotebook(filename).add(Finding(str(args.get("title", "Untitled finding")), str(args.get("note", "")), str(args.get("address", "")), evidence, str(args.get("confidence", "inferred")), str(args.get("kind", "finding")), str(args.get("status", "open")), tuple(str(item) for item in args.get("related_functions", [])), tuple(str(item) for item in args.get("xrefs", [])), tuple(str(item) for item in args.get("strings", [])), tuple(str(item) for item in args.get("il_refs", [])), tuple(str(item) for item in args.get("search_refs", [])), tuple(str(item) for item in args.get("plugin_results", []))))
        return json.dumps({"recorded": record, "summary": AnalysisNotebook(filename).summary(), "note": "Local notebook only; binary unchanged."}, separators=(",", ":"))

    @staticmethod
    def _il_text(function) -> str:
        try:
            return " ".join(str(instruction) for block in function.hlil for instruction in block)[:6000]
        except Exception:
            return ""

    def _triage_records(self) -> list[tuple[Any, str, str]]:
        """Build one bounded in-memory index per agent task, avoiding repeated HLIL walks."""
        if self._triage_index is None:
            self._triage_index = []
            all_functions = list(getattr(self.bv, "functions", []))
            self._triage_total = len(all_functions)
            self._triage_truncated = len(all_functions) > MAX_TRIAGE_FUNCTIONS
            for function in all_functions[:MAX_TRIAGE_FUNCTIONS]:
                name = str(getattr(function, "name", "")).lower()
                haystack = f"{name} {getattr(function, 'type', '')} {self._il_text(function)}".lower()
                self._triage_index.append((function, name, haystack))
        return self._triage_index

    @staticmethod
    def _result_row(function, predicate: str) -> dict[str, Any]:
        return {"address": hex(function.start), "name": function.name, "predicate": predicate, "evidence": f"BinaryView function table + HLIL at {hex(function.start)}"}

    def _search_capabilities(self, args: dict[str, Any]) -> str:
        query = str(args.get("query", "")).lower().strip()
        if not query:
            return capability_digest(self.capabilities[:24], limit=4000) or "No compatible installed plugin commands are available in the current context."
        matches = [capability for capability in self.capabilities if query in f"{capability.name} {capability.description}".lower()]
        return capability_digest(matches[:24], limit=4000) or f"No compatible installed plugin commands matched '{query}'. Try a broader capability term."

    @_main_thread
    def _invoke_external(self, args: dict[str, Any]) -> str:
        identifier = str(args.get("capability_id", ""))
        capability = next((item for item in self.capabilities if item.identifier == identifier), None)
        if capability is None:
            emit_tool_failed("invoke_external_command", f"Plugin capability not found: {identifier}", "Capability not available")
            return "That plugin capability is not available in the current context."
        
        emit_tool_started("invoke_external_command", f"Preparing to run: {capability.name}")
        
        if not self._confirm("Run External Plugin Command", f"Run '{capability.name}'?\n\n{capability.description}\n\nExternal commands may modify the current analysis."):
            emit_tool_completed("invoke_external_command", f"User declined: {capability.name}")
            return "User declined the external plugin command."
        
        emit_tool_progress("invoke_external_command", f"Executing: {capability.name}")
        try:
            result = self.external.execute(identifier, self.bv, self.function)
            emit_tool_result("invoke_external_command", f"Plugin command completed: {capability.name}", {"result": result})
            emit_tool_completed("invoke_external_command", f"Completed: {capability.name}")
            return result
        except Exception as e:
            emit_tool_failed("invoke_external_command", f"Plugin execution failed: {capability.name}", str(e))
            return f"Plugin execution failed: {e}"

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
            "evidence": [f"BinaryView function table: {hex(func.start)}", f"Function.type: {hex(func.start)}", f"HLIL instructions: {hex(func.start)}" if il_lines else f"HLIL unavailable: {hex(func.start)}"],
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
    try:
        return int(value, 0)
    except ValueError:
        # Some model responses omit 0x while still using hexadecimal digits.
        if re.fullmatch(r"[0-9a-fA-F]+", value):
            return int(value, 16)
        raise


def _hex_bytes(value: str) -> bytes:
    normalized = re.sub(r"(?i)0x", "", value)
    normalized = re.sub(r"[\s,;:_-]+", "", normalized)
    if not normalized or not re.fullmatch(r"[0-9a-fA-F]+", normalized) or len(normalized) % 2:
        raise ValueError("bytes_hex must contain complete hexadecimal byte pairs (for example: 90 90 or 0x90 0x90)")
    return bytes.fromhex(normalized)


def _cap(value: str, limit: int) -> str:
    return value[:limit] + ("\n…[truncated]" if len(value) > limit else "")
