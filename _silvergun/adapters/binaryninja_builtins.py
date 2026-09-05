"""Binary Ninja built-ins adapter for Silvergun - programmatic access to BN's native capabilities."""

from __future__ import annotations

import json
import re
from typing import Any

from ..router import ExternalCapability
from ..events import emit_tool_started, emit_tool_progress, emit_tool_result, emit_tool_completed, emit_tool_failed


# Binary Ninja built-in tool definitions
BINARYNINJA_TOOLS = {
    "bn_analyze": {
        "type": "function",
        "function": {
            "name": "bn_analyze",
            "description": "Run Binary Ninja's automatic analysis on the current binary or function",
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {"type": "string", "description": "Optional hexadecimal address to analyze"},
                    "function_only": {"type": "boolean", "default": False, "description": "Analyze only the current function"},
                    "full_analysis": {"type": "boolean", "default": False, "description": "Run full analysis including decompilation"},
                },
                "additionalProperties": False,
            },
        },
    },
    "bn_decompile": {
        "type": "function",
        "function": {
            "name": "bn_decompile",
            "description": "Decompile the current function or a specified function using Binary Ninja's decompiler",
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {"type": "string", "description": "Optional hexadecimal function address"},
                    "timeout": {"type": "integer", "minimum": 1, "maximum": 60, "default": 30, "description": "Decompilation timeout in seconds"},
                },
                "additionalProperties": False,
            },
        },
    },
    "bn_find_cross_references": {
        "type": "function",
        "function": {
            "name": "bn_find_cross_references",
            "description": "Find all cross-references to/from a specific address or function",
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {"type": "string", "description": "Hexadecimal address to find references for"},
                    "direction": {"type": "string", "enum": ["both", "callers", "callees"], "default": "both"},
                    "max_depth": {"type": "integer", "minimum": 1, "maximum": 5, "default": 3},
                },
                "required": ["address"],
                "additionalProperties": False,
            },
        },
    },
    "bn_search_strings": {
        "type": "function",
        "function": {
            "name": "bn_search_strings",
            "description": "Search for strings in the binary and find their cross-references",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "String or regex pattern to search for"},
                    "case_sensitive": {"type": "boolean", "default": False},
                    "regex": {"type": "boolean", "default": False},
                    "min_length": {"type": "integer", "minimum": 1, "maximum": 100, "default": 4},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    "bn_find_functions": {
        "type": "function", 
        "function": {
            "name": "bn_find_functions",
            "description": "Find functions in the binary using various criteria",
            "parameters": {
                "type": "object",
                "properties": {
                    "name_pattern": {"type": "string", "description": "Regex pattern to match function names"},
                    "min_size": {"type": "integer", "minimum": 0, "default": 0},
                    "max_size": {"type": "integer", "minimum": 0, "default": 0},
                    "has_calls": {"type": "boolean", "default": False, "description": "Only functions that make calls"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50},
                },
                "additionalProperties": False,
            },
        },
    },
    "bn_search_symbols": {
        "type": "function",
        "function": {
            "name": "bn_search_symbols",
            "description": "Search the binary's symbol table (imports, exports, named functions and data) for names containing the query",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Symbol name substring to search for"},
                    "case_sensitive": {"type": "boolean", "default": False},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    "bn_get_comments": {
        "type": "function",
        "function": {
            "name": "bn_get_comments", 
            "description": "Get all comments in the current function or binary",
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {"type": "string", "description": "Optional hexadecimal address to get comments for"},
                    "include_auto": {"type": "boolean", "default": True, "description": "Include auto-generated comments"},
                },
                "additionalProperties": False,
            },
        },
    },
    "bn_get_function_tags": {
        "type": "function",
        "function": {
            "name": "bn_get_function_tags",
            "description": "Get all tags applied to functions in the binary",
            "parameters": {
                "type": "object",
                "properties": {
                    "filter": {"type": "string", "description": "Optional tag name filter"},
                    "address": {"type": "string", "description": "Optional hexadecimal address to get tags for"},
                },
                "additionalProperties": False,
            },
        },
    },
    "bn_rename_variable": {
        "type": "function",
        "function": {
            "name": "bn_rename_variable",
            "description": "Rename a variable in the current function (requires user approval)",
            "parameters": {
                "type": "object", 
                "properties": {
                    "address": {"type": "string", "description": "Function address"},
                    "variable_name": {"type": "string", "description": "Current variable name"},
                    "new_name": {"type": "string", "description": "New variable name"},
                    "reason": {"type": "string", "description": "Reason for renaming"},
                },
                "required": ["address", "variable_name", "new_name"],
                "additionalProperties": False,
            },
        },
    },
    "bn_get_types": {
        "type": "function",
        "function": {
            "name": "bn_get_types",
            "description": "Get type information from the binary including function signatures and variable types",
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {"type": "string", "description": "Optional hexadecimal address"},
                    "include_references": {"type": "boolean", "default": True},
                },
                "additionalProperties": False,
            },
        },
    },
    "bn_get_metadata": {
        "type": "function",
        "function": {
            "name": "bn_get_metadata",
            "description": "Get binary metadata including architecture, platform, entry point, etc.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
}


class BinaryNinjaBuiltinsAdapter:
    """Adapter for Binary Ninja's built-in analysis capabilities."""
    
    __slots__ = ("_bv", "_available", "_error")

    def __init__(self) -> None:
        self._bv = None
        self._available = False
        self._error = None

    @classmethod
    def create(cls, bv) -> "BinaryNinjaBuiltinsAdapter":
        adapter = cls()
        adapter.discover(bv)
        return adapter

    @property
    def is_available(self) -> bool:
        return self._available

    @property
    def error(self) -> str | None:
        return self._error

    def capabilities(self) -> list[ExternalCapability]:
        if not self._available:
            return []
        return [
            ExternalCapability(
                "bn.analyze",
                "Binary Ninja/Analysis",
                "Run Binary Ninja's automatic analysis on functions or binary",
                False,
            ),
            ExternalCapability(
                "bn.decompile",
                "Binary Ninja/Decompiler", 
                "Decompile functions using Binary Ninja's built-in decompiler",
                False,
            ),
            ExternalCapability(
                "bn.cross_references",
                "Binary Ninja/Xrefs",
                "Find cross-references to/from addresses or functions",
                False,
            ),
            ExternalCapability(
                "bn.search_strings",
                "Binary Ninja/Search",
                "Search for strings and their references in the binary",
                False,
            ),
            ExternalCapability(
                "bn.search_symbols",
                "Binary Ninja/Search",
                "Search the binary's symbol table for imports, exports, and named symbols",
                False,
            ),
            ExternalCapability(
                "bn.functions",
                "Binary Ninja/Functions",
                "Find and filter functions in the binary",
                False,
            ),
            ExternalCapability(
                "bn.comments",
                "Binary Ninja/Comments",
                "Get comments from the binary analysis",
                False,
            ),
            ExternalCapability(
                "bn.tags",
                "Binary Ninja/Tags",
                "Get tags applied to functions and addresses",
                False,
            ),
            ExternalCapability(
                "bn.types",
                "Binary Ninja/Types",
                "Get type information including function signatures and variables",
                False,
            ),
            ExternalCapability(
                "bn.metadata",
                "Binary Ninja/Metadata",
                "Get binary metadata including architecture, platform, etc.",
                False,
            ),
        ]

    def discover(self, bv) -> None:
        self._bv = bv
        try:
            # Binary Ninja built-ins are always available if we have a BinaryView
            if bv is not None and hasattr(bv, 'functions'):
                self._available = True
                self._error = None
            else:
                self._available = False
                self._error = "No valid BinaryView provided"
        except Exception as e:
            self._available = False
            self._error = f"Failed to initialize Binary Ninja adapter: {e}"

    def get_tools(self) -> dict[str, dict[str, Any]]:
        return dict(BINARYNINJA_TOOLS)

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        if not self._available:
            return json.dumps({"error": self._error or "Binary Ninja adapter not available", "available": False})

        if self._bv is None:
            return json.dumps({"error": "No BinaryView attached", "available": False})

        try:
            if name == "bn_analyze":
                return self._analyze(arguments)
            elif name == "bn_decompile":
                return self._decompile(arguments)
            elif name == "bn_find_cross_references":
                return self._find_cross_references(arguments)
            elif name == "bn_search_strings":
                return self._search_strings(arguments)
            elif name == "bn_search_symbols":
                return self._search_symbols(arguments)
            elif name == "bn_find_functions":
                return self._find_functions(arguments)
            elif name == "bn_get_comments":
                return self._get_comments(arguments)
            elif name == "bn_get_function_tags":
                return self._get_function_tags(arguments)
            elif name == "bn_get_types":
                return self._get_types(arguments)
            elif name == "bn_get_metadata":
                return self._get_metadata(arguments)
            else:
                return json.dumps({"error": f"Unknown Binary Ninja tool: {name}"})
        except Exception as e:
            emit_tool_failed(name, f"Binary Ninja tool failed: {name}", str(e))
            return json.dumps({"error": str(e), "tool": name})

    def _analyze(self, args: dict[str, Any]) -> str:
        emit_tool_started("bn_analyze", "Running Binary Ninja analysis")
        
        address = args.get("address")
        function_only = args.get("function_only", False)
        full_analysis = args.get("full_analysis", False)
        
        try:
            if address:
                # Analyze specific address
                try:
                    addr = int(address, 0)
                    func = self._bv.get_function_at(addr) or self._bv.get_function_containing(addr)
                    if func:
                        emit_tool_progress("bn_analyze", f"Analyzing function at {hex(func.start)}")
                        # Trigger BN analysis on this function
                        func.analyze()
                        emit_tool_result("bn_analyze", f"Analysis completed for {func.name}", {
                            "address": hex(func.start),
                            "name": func.name,
                            "size": getattr(func, 'total_bytes', 0)
                        })
                    else:
                        emit_tool_result("bn_analyze", "No function found at specified address", {"address": address})
                except ValueError:
                    emit_tool_result("bn_analyze", "Invalid address format", {"address": address})
            elif function_only:
                # Analyze current function if available
                if hasattr(self._bv, 'current_function') and self._bv.current_function:
                    func = self._bv.current_function
                    emit_tool_progress("bn_analyze", f"Analyzing current function: {func.name}")
                    func.analyze()
                    emit_tool_result("bn_analyze", f"Current function analysis completed", {
                        "address": hex(func.start),
                        "name": func.name
                    })
            else:
                # Full binary analysis
                emit_tool_progress("bn_analyze", "Running full binary analysis")
                functions_analyzed = 0
                for func in self._bv.functions[:1000]:  # Limit for performance
                    func.analyze()
                    functions_analyzed += 1
                    if functions_analyzed % 100 == 0:
                        emit_tool_progress("bn_analyze", f"Analyzed {functions_analyzed} functions")
                
                emit_tool_result("bn_analyze", f"Full analysis completed: {functions_analyzed} functions", {
                    "functions_analyzed": functions_analyzed
                })
            
            emit_tool_completed("bn_analyze", "Binary Ninja analysis completed")
            return json.dumps({
                "tool": "bn_analyze",
                "status": "completed",
                "functions_analyzed": functions_analyzed if 'functions_analyzed' in locals() else 1,
                "available": True,
            })
            
        except Exception as e:
            emit_tool_failed("bn_analyze", f"Analysis failed: {e}", str(e))
            return json.dumps({"error": str(e), "tool": "bn_analyze"})

    def _decompile(self, args: dict[str, Any]) -> str:
        emit_tool_started("bn_decompile", "Running Binary Ninja decompiler")
        
        address = args.get("address")
        timeout = args.get("timeout", 30)
        
        try:
            if address:
                try:
                    addr = int(address, 0)
                    func = self._bv.get_function_at(addr) or self._bv.get_function_containing(addr)
                    if func:
                        emit_tool_progress("bn_decompile", f"Decompiling function at {hex(func.start)}")
                        # Trigger decompilation
                        hlil = getattr(func, 'hlil', None)
                        if hlil is not None:
                            # HLIL is already available
                            emit_tool_result("bn_decompile", f"HLIL available for {func.name}", {
                                "address": hex(func.start),
                                "hlil_available": True,
                                "instruction_count": len(list(hlil))
                            })
                        else:
                            # Force reanalysis which may trigger decompilation
                            func.analyze()
                            emit_tool_result("bn_decompile", f"Decompilation requested for {func.name}", {
                                "address": hex(func.start)
                            })
                    else:
                        emit_tool_result("bn_decompile", "No function found at specified address", {"address": address})
                except ValueError:
                    emit_tool_result("bn_decompile", "Invalid address format", {"address": address})
            else:
                # Decompile current function
                if hasattr(self._bv, 'current_function') and self._bv.current_function:
                    func = self._bv.current_function
                    emit_tool_progress("bn_decompile", f"Decompiling current function: {func.name}")
                    hlil = getattr(func, 'hlil', None)
                    if hlil is not None:
                        emit_tool_result("bn_decompile", f"HLIL available for current function", {
                            "address": hex(func.start),
                            "hlil_available": True
                        })
                    else:
                        func.analyze()
                        emit_tool_result("bn_decompile", f"Decompilation requested for current function")
            
            emit_tool_completed("bn_decompile", "Decompilation completed")
            return json.dumps({
                "tool": "bn_decompile",
                "status": "completed",
                "available": True,
            })
            
        except Exception as e:
            emit_tool_failed("bn_decompile", f"Decompilation failed: {e}", str(e))
            return json.dumps({"error": str(e), "tool": "bn_decompile"})

    def _find_cross_references(self, args: dict[str, Any]) -> str:
        emit_tool_started("bn_find_cross_references", "Finding cross-references")
        
        address_str = args.get("address", "")
        direction = args.get("direction", "both")
        max_depth = args.get("max_depth", 3)
        
        if not address_str:
            return json.dumps({"error": "address is required", "tool": "bn_find_cross_references"})
        
        try:
            address = int(address_str, 0)
        except ValueError:
            return json.dumps({"error": f"Invalid address: {address_str}", "tool": "bn_find_cross_references"})
        
        func = self._bv.get_function_at(address) or self._bv.get_function_containing(address)
        if func is None:
            emit_tool_result("bn_find_cross_references", "No function found at address", {"address": hex(address)})
            return json.dumps({"error": "No function at address", "address": hex(address)})
        
        emit_tool_progress("bn_find_cross_references", f"Analyzing xrefs for {func.name} at {hex(func.start)}")
        
        cross_refs = {"callers": [], "callees": []}
        
        # Get callers
        if direction in ("both", "callers"):
            for caller in getattr(func, 'callers', []):
                cross_refs["callers"].append({
                    "address": hex(caller.start),
                    "name": caller.name,
                    "type": "caller"
                })
        
        # Get callees
        if direction in ("both", "callees"):
            for callee in getattr(func, 'callees', []):
                cross_refs["callees"].append({
                    "address": hex(callee.start),
                    "name": callee.name,
                    "type": "callee"
                })
        
        emit_tool_result("bn_find_cross_references", f"Found {len(cross_refs['callers'])} callers and {len(cross_refs['callees'])} callees", {
            "callers_count": len(cross_refs["callers"]),
            "callees_count": len(cross_refs["callees"]),
            "total": len(cross_refs["callers"]) + len(cross_refs["callees"])
        })
        
        emit_tool_completed("bn_find_cross_references", "Cross-reference analysis completed")
        
        return json.dumps({
            "tool": "bn_find_cross_references",
            "address": hex(func.start),
            "function": func.name,
            "direction": direction,
            "cross_refs": cross_refs,
            "total": len(cross_refs["callers"]) + len(cross_refs["callees"]),
            "available": True,
        }, separators=(",", ":"))

    def _search_strings(self, args: dict[str, Any]) -> str:
        emit_tool_started("bn_search_strings", "Searching for strings")
        
        query = args.get("query", "")
        case_sensitive = args.get("case_sensitive", False)
        use_regex = args.get("regex", False)
        min_length = args.get("min_length", 4)
        
        if not query:
            return json.dumps({"error": "query is required", "tool": "bn_search_strings"})
        
        emit_tool_progress("bn_search_strings", f"Searching for string: {query[:30]}...")
        
        try:
            # Search for strings in the binary
            matches = []
            string_count = 0
            
            for string in self._bv.get_strings():
                string_value = str(getattr(string, 'value', string))
                
                if len(string_value) < min_length:
                    continue
                
                if use_regex:
                    try:
                        if not case_sensitive:
                            string_value_lower = string_value.lower()
                            query_lower = query.lower()
                            if re.search(query_lower, string_value_lower):
                                matches.append({
                                    "address": hex(getattr(string, 'address', 0)),
                                    "value": string_value,
                                    "length": len(string_value)
                                })
                        else:
                            if re.search(query, string_value):
                                matches.append({
                                    "address": hex(getattr(string, 'address', 0)),
                                    "value": string_value,
                                    "length": len(string_value)
                                })
                    except Exception:
                        # Invalid regex pattern
                        continue
                else:
                    if not case_sensitive and query.lower() in string_value.lower():
                        matches.append({
                            "address": hex(getattr(string, 'address', 0)),
                            "value": string_value,
                            "length": len(string_value)
                        })
                    elif case_sensitive and query in string_value:
                        matches.append({
                            "address": hex(getattr(string, 'address', 0)),
                            "value": string_value,
                            "length": len(string_value)
                        })
                
                string_count += 1
                if string_count % 500 == 0:
                    emit_tool_progress("bn_search_strings", f"Scanned {string_count} strings")
                
                if len(matches) >= 100:  # Limit results
                    break
            
            # Fulfil the tool contract: note which functions reference each
            # matched string so the model can jump straight to usage sites.
            if matches and hasattr(self._bv, "get_code_refs"):
                emit_tool_progress("bn_search_strings", "Resolving which functions reference the matched strings")
                for match in matches[:20]:
                    try:
                        string_address = int(match["address"], 16)
                    except (KeyError, ValueError, TypeError):
                        continue
                    references = []
                    try:
                        for reference in self._bv.get_code_refs(string_address):
                            owner = getattr(reference, "function", None)
                            function_name = str(getattr(owner, "name", "")) if owner is not None else ""
                            if function_name:
                                references.append({"function": function_name, "address": hex(getattr(reference, "address", 0))})
                            if len(references) >= 3:
                                break
                    except Exception:
                        pass
                    if references:
                        match["references"] = references

            emit_tool_result("bn_search_strings", f"Found {len(matches)} string matches", {
                "matches": len(matches),
                "scanned": string_count
            })
            
            emit_tool_completed("bn_search_strings", "String search completed")
            
            return json.dumps({
                "tool": "bn_search_strings",
                "query": query,
                "matches": matches,
                "count": len(matches),
                "available": True,
            }, separators=(",", ":"))
            
        except Exception as e:
            emit_tool_failed("bn_search_strings", f"String search failed: {e}", str(e))
            return json.dumps({"error": str(e), "tool": "bn_search_strings"})

    def _search_symbols(self, args: dict[str, Any]) -> str:
        emit_tool_started("bn_search_symbols", f"Searching symbols for: {str(args.get('query', ''))[:40]}")

        query = str(args.get("query", "")).strip()
        if not query:
            emit_tool_failed("bn_search_symbols", "No symbol query supplied", "empty query")
            return json.dumps({"error": "A non-empty 'query' is required.", "tool": "bn_search_symbols"})

        case_sensitive = bool(args.get("case_sensitive", False))
        limit = min(200, max(1, int(args.get("limit", 50))))

        try:
            if not hasattr(self._bv, "get_symbols"):
                emit_tool_failed("bn_search_symbols", "Symbol table unavailable in this BinaryView", "no get_symbols API")
                return json.dumps({"error": "This BinaryView does not expose a symbol table.", "tool": "bn_search_symbols"})

            emit_tool_progress("bn_search_symbols", f"Scanning the symbol table for '{query[:30]}'")

            matches = []
            scanned = 0
            needle = query if case_sensitive else query.lower()
            for symbol in self._bv.get_symbols():
                scanned += 1
                if scanned % 2000 == 0:
                    emit_tool_progress("bn_search_symbols", f"Scanned {scanned} symbols")
                name = str(getattr(symbol, "name", ""))
                full_name = str(getattr(symbol, "fullName", name))
                haystack = name if case_sensitive else name.lower()
                full_haystack = full_name if case_sensitive else full_name.lower()
                if needle in haystack or needle in full_haystack:
                    matches.append({
                        "address": hex(getattr(symbol, "address", 0)),
                        "name": name,
                        "full_name": full_name,
                        "type": str(getattr(symbol, "type", "")),
                    })
                    if len(matches) >= limit:
                        break

            emit_tool_result("bn_search_symbols", f"Found {len(matches)} symbol matches", {
                "matches": len(matches),
                "scanned": scanned,
            })
            emit_tool_completed("bn_search_symbols", "Symbol search completed")

            return json.dumps({
                "tool": "bn_search_symbols",
                "query": query,
                "matches": matches,
                "count": len(matches),
                "available": True,
            }, separators=(",", ":"))

        except Exception as e:
            emit_tool_failed("bn_search_symbols", f"Symbol search failed: {e}", str(e))
            return json.dumps({"error": str(e), "tool": "bn_search_symbols"})

    def _find_functions(self, args: dict[str, Any]) -> str:
        emit_tool_started("bn_find_functions", "Finding functions")
        
        name_pattern = args.get("name_pattern", ".*")
        min_size = args.get("min_size", 0)
        max_size = args.get("max_size", 0)
        has_calls = args.get("has_calls", False)
        limit = args.get("limit", 50)
        
        try:
            import re
            pattern = re.compile(name_pattern)
        except Exception:
            emit_tool_failed("bn_find_functions", "Invalid regex pattern", name_pattern)
            return json.dumps({"error": "Invalid regex pattern", "pattern": name_pattern})
        
        emit_tool_progress("bn_find_functions", f"Searching functions with pattern: {name_pattern}")
        
        try:
            matches = []
            scanned = 0
            
            for func in self._bv.functions:
                scanned += 1
                func_name = getattr(func, 'name', '')
                func_size = getattr(func, 'total_bytes', 0)
                
                # Check name pattern
                if not pattern.search(func_name):
                    continue
                
                # Check size constraints
                if min_size > 0 and func_size < min_size:
                    continue
                if max_size > 0 and func_size > max_size:
                    continue
                
                # Check if function has calls
                if has_calls:
                    callers = getattr(func, 'callers', [])
                    callees = getattr(func, 'callees', [])
                    if not callers and not callees:
                        continue
                
                matches.append({
                    "address": hex(func.start),
                    "name": func_name,
                    "size": func_size,
                    "callers_count": len(getattr(func, 'callers', [])),
                    "callees_count": len(getattr(func, 'callees', []))
                })
                
                if len(matches) >= limit:
                    break
                
                if scanned % 200 == 0:
                    emit_tool_progress("bn_find_functions", f"Scanned {scanned} functions, found {len(matches)} matches")
            
            emit_tool_result("bn_find_functions", f"Found {len(matches)} functions matching criteria", {
                "matches": len(matches),
                "scanned": scanned
            })
            
            emit_tool_completed("bn_find_functions", "Function search completed")
            
            return json.dumps({
                "tool": "bn_find_functions",
                "pattern": name_pattern,
                "matches": matches,
                "count": len(matches),
                "available": True,
            }, separators=(",", ":"))
            
        except Exception as e:
            emit_tool_failed("bn_find_functions", f"Function search failed: {e}", str(e))
            return json.dumps({"error": str(e), "tool": "bn_find_functions"})

    def _get_comments(self, args: dict[str, Any]) -> str:
        emit_tool_started("bn_get_comments", "Retrieving comments")
        
        address = args.get("address")
        include_auto = args.get("include_auto", True)
        
        try:
            comments = []
            
            if address:
                # Get comments for specific address
                try:
                    addr = int(address, 0)
                    func = self._bv.get_function_at(addr) or self._bv.get_function_containing(addr)
                    if func:
                        func_comments = getattr(func, 'comment', '')
                        if func_comments:
                            comments.append({
                                "address": hex(func.start),
                                "type": "function_comment",
                                "content": func_comments,
                                "auto": False
                            })
                        
                        # Check for address-specific comments
                        bn_comments = getattr(self._bv, 'get_comments_at', lambda addr: [])(addr)
                        for comment in bn_comments:
                            if include_auto or not getattr(comment, 'auto', False):
                                comments.append({
                                    "address": hex(getattr(comment, 'address', addr)),
                                    "type": "address_comment",
                                    "content": str(getattr(comment, 'text', '')),
                                    "auto": getattr(comment, 'auto', False)
                                })
                except ValueError:
                    emit_tool_result("bn_get_comments", "Invalid address format", {"address": address})
            else:
                # Get all comments in binary
                emit_tool_progress("bn_get_comments", "Scanning all comments in binary")
                
                for func in self._bv.functions[:500]:  # Limit for performance
                    func_comment = getattr(func, 'comment', '')
                    if func_comment:
                        comments.append({
                            "address": hex(func.start),
                            "type": "function_comment",
                            "content": func_comment,
                            "function": func.name,
                            "auto": False
                        })
                
                # Try to get address-specific comments if BN API supports it
                if hasattr(self._bv, 'get_comments_at'):
                    for func in self._bv.functions[:500]:
                        for comment in self._bv.get_comments_at(func.start):
                            if include_auto or not getattr(comment, 'auto', False):
                                comments.append({
                                    "address": hex(getattr(comment, 'address', func.start)),
                                    "type": "address_comment",
                                    "content": str(getattr(comment, 'text', '')),
                                    "function": func.name,
                                    "auto": getattr(comment, 'auto', False)
                                })
            
            emit_tool_result("bn_get_comments", f"Retrieved {len(comments)} comments", {"count": len(comments)})
            emit_tool_completed("bn_get_comments", "Comment retrieval completed")
            
            return json.dumps({
                "tool": "bn_get_comments",
                "comments": comments,
                "count": len(comments),
                "available": True,
            }, separators=(",", ":"))
            
        except Exception as e:
            emit_tool_failed("bn_get_comments", f"Comment retrieval failed: {e}", str(e))
            return json.dumps({"error": str(e), "tool": "bn_get_comments"})

    def _get_function_tags(self, args: dict[str, Any]) -> str:
        emit_tool_started("bn_get_function_tags", "Retrieving function tags")
        
        filter_tag = args.get("filter", "")
        address = args.get("address")
        
        try:
            tags = []
            
            if address:
                try:
                    addr = int(address, 0)
                    func = self._bv.get_function_at(addr) or self._bv.get_function_containing(addr)
                    if func:
                        func_tags = getattr(func, 'tags', [])
                        for tag in func_tags:
                            tag_name = getattr(tag, 'name', str(tag))
                            if not filter_tag or filter_tag.lower() in tag_name.lower():
                                tags.append({
                                    "address": hex(func.start),
                                    "function": func.name,
                                    "tag": tag_name,
                                    "source": getattr(tag, 'source', 'unknown')
                                })
                except ValueError:
                    pass
            else:
                emit_tool_progress("bn_get_function_tags", "Scanning all function tags in binary")
                
                for func in self._bv.functions[:1000]:  # Limit for performance
                    func_tags = getattr(func, 'tags', [])
                    for tag in func_tags:
                        tag_name = getattr(tag, 'name', str(tag))
                        if not filter_tag or filter_tag.lower() in tag_name.lower():
                            tags.append({
                                "address": hex(func.start),
                                "function": func.name,
                                "tag": tag_name,
                                "source": getattr(tag, 'source', 'unknown')
                            })
            
            emit_tool_result("bn_get_function_tags", f"Found {len(tags)} tags", {"count": len(tags)})
            emit_tool_completed("bn_get_function_tags", "Tag retrieval completed")
            
            return json.dumps({
                "tool": "bn_get_function_tags",
                "tags": tags,
                "filter": filter_tag,
                "count": len(tags),
                "available": True,
            }, separators=(",", ":"))
            
        except Exception as e:
            emit_tool_failed("bn_get_function_tags", f"Tag retrieval failed: {e}", str(e))
            return json.dumps({"error": str(e), "tool": "bn_get_function_tags"})

    def _get_types(self, args: dict[str, Any]) -> str:
        emit_tool_started("bn_get_types", "Retrieving type information")
        
        address = args.get("address")
        include_references = args.get("include_references", True)
        
        try:
            type_info = {}
            
            if address:
                try:
                    addr = int(address, 0)
                    func = self._bv.get_function_at(addr) or self._bv.get_function_containing(addr)
                    if func:
                        type_info = {
                            "address": hex(func.start),
                            "function": func.name,
                            "signature": str(getattr(func, 'type', 'unknown')),
                            "return_type": str(getattr(getattr(func, 'return_type', None), 'name', 'unknown')),
                        }
                        
                        if include_references:
                            # Get parameter types
                            parameters = []
                            for param in getattr(func, 'parameter_vars', []):
                                parameters.append({
                                    "name": param.name,
                                    "type": str(param.type),
                                    "source": str(param.source_type)
                                })
                            type_info["parameters"] = parameters
                            
                            # Get local variable types
                            locals = []
                            for var in getattr(func, 'vars', []):
                                if not var.source_type.name.startswith('parameter'):
                                    locals.append({
                                        "name": var.name,
                                        "type": str(var.type),
                                        "source": str(var.source_type)
                                    })
                            type_info["locals"] = locals
                except ValueError:
                    pass
            else:
                # Get type info for current function or all functions
                emit_tool_progress("bn_get_types", "Collecting type information for functions")
                
                function_types = []
                for func in self._bv.functions[:100]:  # Limit for performance
                    func_type = str(getattr(func, 'type', 'unknown'))
                    if func_type != 'unknown':
                        function_types.append({
                            "address": hex(func.start),
                            "function": func.name,
                            "signature": func_type
                        })
                
                type_info["functions"] = function_types
                type_info["count"] = len(function_types)
            
            emit_tool_result("bn_get_types", f"Retrieved type information", type_info)
            emit_tool_completed("bn_get_types", "Type retrieval completed")
            
            return json.dumps({
                "tool": "bn_get_types",
                "type_info": type_info,
                "available": True,
            }, separators=(",", ":"))
            
        except Exception as e:
            emit_tool_failed("bn_get_types", f"Type retrieval failed: {e}", str(e))
            return json.dumps({"error": str(e), "tool": "bn_get_types"})

    def _get_metadata(self, args: dict[str, Any]) -> str:
        emit_tool_started("bn_get_metadata", "Retrieving binary metadata")
        
        try:
            metadata = {
                "filename": str(getattr(getattr(self._bv, 'file', None), 'filename', 'unknown')),
                "architecture": str(getattr(getattr(self._bv, 'arch', None), 'name', 'unknown')),
                "platform": str(getattr(getattr(self._bv, 'platform', None), 'name', 'unknown')),
                "file_format": str(getattr(self._bv, 'file_format', 'unknown')),
                "entry_point": hex(getattr(self._bv, 'entry_point', 0)),
                "image_base": hex(getattr(self._bv, 'start', 0)),
                "function_count": len(getattr(self._bv, 'functions', [])),
                "analysis_changed": getattr(self._bv, 'analysis_changed', False),
            }
            
            # Add additional metadata if available
            if hasattr(self._bv, 'get_metadata'):
                try:
                    additional_metadata = self._bv.get_metadata()
                    if additional_metadata:
                        metadata["additional"] = str(additional_metadata)
                except Exception:
                    pass
            
            emit_tool_result("bn_get_metadata", "Binary metadata retrieved", metadata)
            emit_tool_completed("bn_get_metadata", "Metadata retrieval completed")
            
            return json.dumps({
                "tool": "bn_get_metadata",
                "metadata": metadata,
                "available": True,
            }, separators=(",", ":"))
            
        except Exception as e:
            emit_tool_failed("bn_get_metadata", f"Metadata retrieval failed: {e}", str(e))
            return json.dumps({"error": str(e), "tool": "bn_get_metadata"})