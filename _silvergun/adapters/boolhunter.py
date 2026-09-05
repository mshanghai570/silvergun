"""BoolHunter adapter for Silvergun - programmatic invocation without UI."""

from __future__ import annotations

import json
import re
from typing import Any

from ..router import ExternalCapability
from ..events import (
    emit_tool_started, emit_tool_progress, emit_tool_result, 
    emit_tool_completed, emit_tool_failed, emit_analysis_finding
)


BOOLHUNTER_TOOLS = {
    "boolhunter_quick_scan": {
        "type": "function",
        "function": {
            "name": "boolhunter_quick_scan",
            "description": "Quick scan for boolean functions using BoolHunter's engine. Returns categorized results with confidence scores.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Optional category filter: Purchases, Authentication & Security, Network & Communication, Files & Storage, UI & Interaction, Navigation & Location, Media, Validation & State",
                    },
                    "min_score": {"type": "integer", "minimum": 0, "maximum": 100, "default": 1},
                    "max_results": {"type": "integer", "minimum": 1, "maximum": 64, "default": 24},
                },
                "additionalProperties": False,
            },
        },
    },
    "boolhunter_analyze": {
        "type": "function",
        "function": {
            "name": "boolhunter_analyze",
            "description": "Deep analysis of a specific function using BoolHunter's deterministic engine. Returns evidence-based scoring.",
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {"type": "string", "description": "Hexadecimal function address"},
                },
                "required": ["address"],
                "additionalProperties": False,
            },
        },
    },
    "boolhunter_batch_scan": {
        "type": "function",
        "function": {
            "name": "boolhunter_batch_scan",
            "description": "Scan multiple functions with BoolHunter engine for boolean patterns. Returns categorized candidates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "addresses": {"type": "array", "items": {"type": "string"}, "description": "Hex addresses to scan"},
                    "min_score": {"type": "integer", "minimum": 0, "maximum": 100, "default": 15},
                },
                "additionalProperties": False,
            },
        },
    },
    "boolhunter_find_category": {
        "type": "function",
        "function": {
            "name": "boolhunter_find_category",
            "description": "Find functions matching a semantic category using BoolHunter's classification.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["Purchases", "Authentication & Security", "Network & Communication", "Files & Storage", "UI & Interaction", "Navigation & Location", "Media", "Validation & State", "Other"],
                        "description": "Target category",
                    },
                    "min_score": {"type": "integer", "minimum": 0, "maximum": 100, "default": 1},
                    "max_results": {"type": "integer", "minimum": 1, "maximum": 48, "default": 16},
                },
                "required": ["category"],
                "additionalProperties": False,
            },
        },
    },
}


BOOLHUNTER_CATEGORIES = [
    "Purchases",
    "Authentication & Security",
    "Network & Communication",
    "Files & Storage",
    "UI & Interaction",
    "Navigation & Location",
    "Media",
    "Validation & State",
    "Other",
]


CATEGORY_KEYWORDS = {
    "Purchases": ["purchase", "buy", "checkout", "cart", "order", "transaction", "payment", "billing", "subscription", "receipt", "store"],
    "Authentication & Security": ["login", "logout", "auth", "password", "credential", "token", "session", "secure", "encrypt", "decrypt", "permission", "authorize", "biometric"],
    "Network & Communication": ["http", "https", "url", "request", "response", "fetch", "download", "upload", "socket", "network", "connect", "message", "send", "receive", "sync"],
    "Files & Storage": ["file", "read", "write", "save", "load", "cache", "document", "path", "directory", "storage", "database", "sqlite", "persist"],
    "UI & Interaction": ["view", "window", "screen", "button", "menu", "dialog", "display", "render", "draw", "click", "tap", "gesture", "touch"],
    "Navigation & Location": ["navigate", "navigation", "route", "redirect", "location", "coordinate", "map", "gps", "latitude", "longitude"],
    "Media": ["audio", "video", "image", "photo", "camera", "microphone", "record", "play", "pause", "stream", "media", "frame"],
    "Validation & State": ["valid", "invalid", "check", "verify", "validate", "is_ready", "enabled", "active", "available", "exists", "empty"],
    "Other": [],
}


def _canonical_category(value: Any) -> str:
    raw = str(value or "").strip()
    aliases = {
        "purchase": "Purchases", "purchases": "Purchases", "payment": "Purchases", "payments": "Purchases",
        "authentication": "Authentication & Security", "auth": "Authentication & Security", "security": "Authentication & Security",
        "network": "Network & Communication", "networking": "Network & Communication", "communication": "Network & Communication",
        "files": "Files & Storage", "storage": "Files & Storage", "ui": "UI & Interaction", "interface": "UI & Interaction",
        "navigation": "Navigation & Location", "location": "Navigation & Location", "validation": "Validation & State", "state": "Validation & State",
    }
    return aliases.get(raw.lower(), raw)


class BoolHunterAdapter:
    __slots__ = ("_bv", "_engine", "_available", "_error")

    def __init__(self) -> None:
        self._bv = None
        self._engine = None
        self._available = False
        self._error = None

    @classmethod
    def create(cls, bv) -> "BoolHunterAdapter":
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
                "boolhunter.quick_scan",
                "BoolHunter/Analysis",
                "Quick boolean function scan using deterministic heuristics",
                False,
            ),
            ExternalCapability(
                "boolhunter.analyze",
                "BoolHunter/Analysis",
                "Deep boolean function analysis with evidence scoring",
                False,
            ),
            ExternalCapability(
                "boolhunter.batch_scan",
                "BoolHunter/Analysis",
                "Batch scan multiple functions for boolean patterns",
                False,
            ),
            ExternalCapability(
                "boolhunter.find_category",
                "BoolHunter/Category",
                "Find functions by semantic category (authentication, purchase, network, etc.)",
                False,
            ),
        ]

    def discover(self, bv) -> None:
        self._bv = bv
        try:
            from BoolHunter.engine import BoolHunterEngine
            self._engine = BoolHunterEngine(bv)
            self._available = True
            self._error = None
        except ImportError:
            self._available = False
            self._error = "BoolHunter plugin is not installed"
        except Exception as e:
            self._available = False
            self._error = f"BoolHunter initialization failed: {e}"

    def get_tools(self) -> dict[str, dict[str, Any]]:
        return dict(BOOLHUNTER_TOOLS)

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        if not self._available:
            return json.dumps({"error": self._error or "BoolHunter not available", "available": False})

        if self._bv is None:
            return json.dumps({"error": "No BinaryView attached", "available": False})

        if name == "boolhunter_quick_scan":
            return self._quick_scan(arguments)
        elif name == "boolhunter_analyze":
            return self._analyze(arguments)
        elif name == "boolhunter_batch_scan":
            return self._batch_scan(arguments)
        elif name == "boolhunter_find_category":
            return self._find_category(arguments)
        return json.dumps({"error": f"Unknown tool: {name}"})

    def _quick_scan(self, args: dict[str, Any]) -> str:
        category_filter = _canonical_category(args.get("category")) or None
        min_score = max(0, min(100, args.get("min_score", 1)))
        max_results = max(1, min(64, args.get("max_results", 24)))

        emit_tool_started("boolhunter_quick_scan", f"Scanning for boolean functions{': ' + category_filter if category_filter else ''}")

        candidates = []
        scanned = 0
        total_functions = min(2000, len(list(self._bv.functions)))
        
        for func in self._bv.functions[:2000]:
            scanned += 1
            
            # Emit progress every 100 functions or when we have candidates
            if scanned % 100 == 0:
                emit_tool_progress("boolhunter_quick_scan", f"Scanned {scanned}/{total_functions} functions", scanned, total_functions)
            
            if self._engine.is_fast_candidate(func):
                result = self._engine.analyze_function(func)
                if result.final_score >= min_score:
                    if category_filter is None or result.category == category_filter:
                        candidates.append(self._result_to_dict(result))
                        
                        # Emit finding when we discover candidates
                        if len(candidates) == 1:
                            emit_tool_result("boolhunter_quick_scan", f"First candidate found: {result.func.name}", {"address": hex(result.func.start)})
                        elif len(candidates) % 5 == 0:
                            emit_tool_progress("boolhunter_quick_scan", f"Found {len(candidates)} candidates so far", len(candidates), max_results)
                        
                        if len(candidates) >= max_results:
                            break

        emit_tool_result("boolhunter_quick_scan", f"Found {len(candidates)} candidates", {
            "count": len(candidates),
            "scanned": scanned
        })
        emit_tool_completed("boolhunter_quick_scan", f"Quick scan completed with {len(candidates)} results")

        return json.dumps({
            "tool": "boolhunter_quick_scan",
            "category_filter": category_filter,
            "min_score": min_score,
            "scanned": scanned,
            "results": candidates,
            "count": len(candidates),
            "available": True,
        }, separators=(",", ":"))

    def _analyze(self, args: dict[str, Any]) -> str:
        address = args.get("address", "")
        if not address:
            return json.dumps({"error": "address is required"})

        try:
            addr = int(address, 0)
        except ValueError:
            return json.dumps({"error": f"Invalid address: {address}"})

        emit_tool_started("boolhunter_analyze", f"Analyzing function at {address}")

        func = self._bv.get_function_at(addr) or self._bv.get_function_containing(addr)
        if func is None:
            emit_tool_failed("boolhunter_analyze", f"No function found at {address}", "Function not found")
            return json.dumps({"error": f"No function at {address}"})

        emit_tool_progress("boolhunter_analyze", f"Retrieved function {func.name} at {hex(func.start)}")

        result = self._engine.analyze_function(func)
        
        emit_tool_result("boolhunter_analyze", f"Analysis complete for {func.name}", {
            "score": result.final_score,
            "category": result.category,
            "evidence_count": len(result.evidence_list)
        })
        
        emit_tool_completed("boolhunter_analyze", f"Analysis completed")

        return json.dumps({
            "tool": "boolhunter_analyze",
            "address": address,
            "function": self._function_summary(func),
            "analysis": self._result_to_dict(result),
            "available": True,
        }, separators=(",", ":"))

    def _batch_scan(self, args: dict[str, Any]) -> str:
        addresses = args.get("addresses", [])
        min_score = max(0, min(100, args.get("min_score", 15)))

        if not addresses:
            return json.dumps({"error": "addresses list is required"})

        emit_tool_started("boolhunter_batch_scan", f"Batch scanning {len(addresses)} functions")

        results = []
        total_addresses = len(addresses[:64])
        processed = 0
        
        for addr_str in addresses[:64]:
            processed += 1
            
            # Emit progress every few functions
            if processed % 5 == 0:
                emit_tool_progress("boolhunter_batch_scan", f"Processing {processed}/{total_addresses} addresses", processed, total_addresses)
            
            try:
                addr = int(addr_str, 0)
            except ValueError:
                emit_analysis_warning(f"Invalid address skipped: {addr_str}")
                continue
                
            func = self._bv.get_function_at(addr) or self._bv.get_function_containing(addr)
            if func is None:
                emit_analysis_warning(f"No function found at {hex(addr) if isinstance(addr, int) else addr_str}")
                continue
                
            result = self._engine.analyze_function(func)
            if result.final_score >= min_score:
                results.append(self._result_to_dict(result))
                emit_tool_result("boolhunter_batch_scan", f"Analyzed {func.name} at {hex(func.start)}", {
                    "address": hex(func.start),
                    "score": result.final_score
                })

        emit_tool_result("boolhunter_batch_scan", f"Batch scan complete: {len(results)}/{len(addresses[:64])} functions analyzed", {
            "count": len(results),
            "scanned": len(results)
        })
        emit_tool_completed("boolhunter_batch_scan", f"Batch scan completed with {len(results)} results")

        return json.dumps({
            "tool": "boolhunter_batch_scan",
            "requested": len(addresses),
            "scanned": len(results),
            "min_score": min_score,
            "results": results,
            "count": len(results),
            "available": True,
        }, separators=(",", ":"))

    def _find_category(self, args: dict[str, Any]) -> str:
        category = _canonical_category(args.get("category", "Other"))
        min_score = max(0, min(100, args.get("min_score", 1)))
        max_results = max(1, min(48, args.get("max_results", 16)))

        if category not in BOOLHUNTER_CATEGORIES:
            return json.dumps({
                "error": f"Invalid category. Must be one of: {', '.join(BOOLHUNTER_CATEGORIES)}",
                "valid_categories": BOOLHUNTER_CATEGORIES,
            })

        emit_tool_started("boolhunter_find_category", f"Searching for {category} functions")

        candidates = []
        scanned = 0
        total_functions = min(2000, len(list(self._bv.functions)))
        
        for func in self._bv.functions[:2000]:
            scanned += 1
            
            # Emit progress periodically
            if scanned % 100 == 0:
                emit_tool_progress("boolhunter_find_category", f"Scanning for {category}... {scanned}/{total_functions} functions", scanned, total_functions)
            
            if self._engine.is_fast_candidate(func):
                result = self._engine.analyze_function(func)
                if result.category == category and result.final_score >= min_score:
                    candidates.append(self._result_to_dict(result))
                    
                    # Emit findings as they're discovered
                    if len(candidates) == 1:
                        emit_tool_result("boolhunter_find_category", f"First {category} candidate: {result.func.name}", {"address": hex(result.func.start), "score": result.final_score})
                    elif len(candidates) % 3 == 0:
                        emit_tool_progress("boolhunter_find_category", f"Found {len(candidates)} {category} candidates", len(candidates), max_results)
                    
                    if len(candidates) >= max_results:
                        emit_tool_result("boolhunter_find_category", f"Reached maximum results: {len(candidates)} {category} functions", {"count": len(candidates)})
                        break

        emit_tool_result("boolhunter_find_category", f"Found {len(candidates)} {category} functions", {
            "category": category,
            "count": len(candidates),
            "scanned": scanned
        })
        emit_tool_completed("boolhunter_find_category", f"Category search completed with {len(candidates)} results")

        return json.dumps({
            "tool": "boolhunter_find_category",
            "category": category,
            "min_score": min_score,
            "scanned": scanned,
            "results": candidates,
            "count": len(candidates),
            "available": True,
        }, separators=(",", ":"))

    def _result_to_dict(self, result) -> dict[str, Any]:
        return {
            "address": hex(result.func.start),
            "name": result.func.name,
            "category": result.category,
            "score": result.final_score,
            "evidence": [{"score": e.score, "message": e.message} for e in result.evidence_list],
        }

    def _function_summary(self, func) -> dict[str, Any]:
        return {
            "address": hex(func.start),
            "name": func.name,
            "signature": str(func.type) if hasattr(func, 'type') else "unknown",
        }
