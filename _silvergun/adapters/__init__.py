"""Plugin adapter system for Silvergun - programmatic invocation without UI."""

from __future__ import annotations

import json
import logging
from typing import Any

from ..router import ExternalCapability
from ..events import emit_tool_started, emit_tool_result, emit_tool_completed, emit_tool_failed
from ..execution import on_binary_ninja_thread

logger = logging.getLogger(__name__)


ADAPTER_TOOL_PREFIXES = {
    "boolhunter": "boolhunter_",
    "binaryninja": "bn_",
    "builtin": "bn_",
}


class AdapterRegistry:
    _instance: "AdapterRegistry | None" = None

    def __init__(self) -> None:
        self._adapters: dict[str, Any] = {}
        self._tools: dict[str, tuple[str, dict[str, Any]]] = {}
        self._capabilities: list[ExternalCapability] = []
        self._discovered = False
        self._context_key: tuple[int | None, int | None] | None = None

    @classmethod
    def get(cls) -> "AdapterRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    def discover(self, bv, function=None) -> None:
        context_key = ((id(bv) if bv is not None else None), getattr(function, "start", None))
        if self._discovered and self._context_key == context_key:
            return
        # A SidebarWidget and background task can survive a view switch. Never
        # reuse adapters bound to the old BinaryView.
        self._adapters.clear()
        self._tools.clear()
        self._capabilities.clear()
        self._discovered = True
        self._context_key = context_key

        self._discover_boolhunter(bv)
        self._discover_binaryninja_builtins(bv, function)
        self._build_tool_index()

    def _discover_boolhunter(self, bv) -> None:
        try:
            from .boolhunter import BoolHunterAdapter
            adapter = BoolHunterAdapter.create(bv)
            if adapter.is_available:
                self._adapters["boolhunter"] = adapter
                logger.info("BoolHunter adapter loaded successfully")
            else:
                logger.info(f"BoolHunter not available: {adapter.error}")
        except Exception as e:
            logger.warning(f"BoolHunter adapter failed to load: {e}")

    def _discover_binaryninja_builtins(self, bv, function=None) -> None:
        """Discover and adapt Binary Ninja's built-in analysis capabilities."""
        try:
            from .binaryninja_builtins import BinaryNinjaBuiltinsAdapter
            adapter = BinaryNinjaBuiltinsAdapter.create(bv, function)
            if adapter.is_available:
                self._adapters["binaryninja"] = adapter
                logger.info("Binary Ninja builtins adapter loaded successfully")
            else:
                logger.info(f"Binary Ninja builtins not available: {adapter.error}")
        except Exception as e:
            logger.warning(f"Binary Ninja builtins adapter failed to load: {e}")

    def _build_tool_index(self) -> None:
        self._tools.clear()
        self._capabilities.clear()

        for name, adapter in self._adapters.items():
            prefix = ADAPTER_TOOL_PREFIXES.get(name, f"{name}_")
            for tool_name, tool_schema in adapter.get_tools().items():
                self._tools[tool_name] = (name, tool_schema)

            for cap in adapter.capabilities():
                self._capabilities.append(cap)

    def all_adapters(self) -> dict[str, Any]:
        return dict(self._adapters)

    def get_adapter(self, name: str) -> Any | None:
        return self._adapters.get(name)

    def is_available(self, tool_name: str) -> bool:
        adapter_name = self._adapter_for_tool(tool_name)
        return adapter_name in self._adapters

    def get_tool_schema(self, tool_name: str) -> dict[str, Any] | None:
        _, schema = self._tools.get(tool_name, (None, None))
        return schema

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> str:
        def invoke() -> str:
            adapter_name = self._adapter_for_tool(tool_name)
            adapter = self._adapters.get(adapter_name)
            if adapter is None:
                return json.dumps({"error": f"Adapter not available: {adapter_name}", "available": False})
            return adapter.execute(tool_name, arguments)

        return on_binary_ninja_thread(invoke)

    def capabilities(self) -> list[ExternalCapability]:
        return list(self._capabilities)

    def tools_for_intent(self, intent: str) -> list[str]:
        intent_keywords = {
            "triage": ["quick_scan", "batch_scan", "analyze", "functions"],
            "vulnerabilities": ["analyze", "batch_scan", "strings", "comments"],
            "investigate": ["analyze", "find_category", "functions", "cross_references"],
            "map": ["batch_scan", "cross_references", "functions"],
            "verify": ["analyze", "types", "metadata"],
            "explain": ["analyze", "decompile", "types"],
            "boolean": ["analyze", "quick_scan", "find_category"],
            "category": ["find_category", "quick_scan", "analyze"],
        }
        keywords = intent_keywords.get(intent, [])
        return [t for t in self._tools.keys() if any(k in t for k in keywords)]

    def _adapter_for_tool(self, tool_name: str) -> str | None:
        for adapter_name, prefix in ADAPTER_TOOL_PREFIXES.items():
            if tool_name.startswith(prefix):
                return adapter_name
        return None

    def available_plugins(self) -> list[dict[str, Any]]:
        result = []
        for name, adapter in self._adapters.items():
            info = {"name": name, "available": adapter.is_available}
            if not adapter.is_available and adapter.error:
                info["error"] = adapter.error
            result.append(info)
        return result


class Adapter:
    def discover(self, bv) -> None:
        raise NotImplementedError

    def get_tools(self) -> dict[str, dict[str, Any]]:
        raise NotImplementedError

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        raise NotImplementedError
