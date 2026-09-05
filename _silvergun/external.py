"""Adapter exposing compatible installed Binary Ninja commands as compact capabilities."""

from __future__ import annotations

from collections import OrderedDict
import hashlib
from typing import Any

from binaryninja import PluginCommand, PluginCommandContext

from .router import ExternalCapability
from .events import emit_tool_started, emit_tool_result, emit_tool_completed, emit_tool_failed


class ExternalCommandIndex:
    """Indexes valid commands in the current context without loading a large plugin framework."""

    _cache: "OrderedDict[tuple[int, tuple[Any, ...]], tuple[dict[str, Any], tuple[ExternalCapability, ...]]]" = OrderedDict()
    _cache_limit = 48

    def __init__(self) -> None:
        self._commands: dict[str, Any] = {}

    def refresh(self, bv, function=None, *, force: bool = False) -> list[ExternalCapability]:
        key = (id(bv), self._context_fingerprint(bv, function))
        if not force and key in self._cache:
            commands, capabilities = self._cache[key]
            self._commands = commands.copy()
            self._cache.move_to_end(key)
            return list(capabilities)
        context = self._context(bv, function)
        valid = PluginCommand.get_valid_list(context)
        commands = valid.values() if hasattr(valid, "values") else valid
        self._commands.clear()
        capabilities: list[ExternalCapability] = []
        for command in commands:
            name = getattr(command, "name", "")
            if not isinstance(name, str) or not name or name.startswith("Silvergun\\"):
                continue
            identifier = self._identifier(name)
            description = str(getattr(command, "description", "") or "No description supplied by the plugin.")
            self._commands[identifier] = command
            callable_command = callable(getattr(command, "execute", None))
            status = "CALLABLE" if callable_command else "UI_ONLY"
            capabilities.append(ExternalCapability(identifier, name, description, mutation_risk=True, status=status))
        ordered = tuple(sorted(capabilities, key=lambda capability: capability.name.lower()))
        self._cache[key] = (self._commands.copy(), ordered)
        self._cache.move_to_end(key)
        while len(self._cache) > self._cache_limit:
            self._cache.popitem(last=False)
        return list(ordered)

    def execute(self, identifier: str, bv, function=None) -> str:
        command = self._commands.get(identifier)
        if command is None:
            emit_tool_failed("external_command", f"Command unavailable: {identifier}", "Plugin capability not found")
            raise KeyError("The requested plugin capability is unavailable in the current Binary Ninja context.")
        if not callable(getattr(command, "execute", None)):
            emit_tool_failed("external_command", f"Command is UI-only: {identifier}", "The plugin does not expose a callable command API")
            raise RuntimeError("The requested plugin capability is UI-only and cannot be invoked autonomously.")
        
        command_name = getattr(command, 'name', identifier)
        emit_tool_started("external_command", f"Executing plugin command: {command_name}")
        
        try:
            command.execute(self._context(bv, function))
            emit_tool_result("external_command", f"Plugin command executed: {command_name}", {"command": command_name})
            emit_tool_completed("external_command", f"Completed: {command_name}")
            return f"Executed external command: {command_name}"
        except Exception as e:
            emit_tool_failed("external_command", f"Plugin command failed: {command_name}", str(e))
            raise

    @staticmethod
    def _context_fingerprint(bv, function=None) -> tuple[Any, ...]:
        """Capture context fields known to affect PluginCommand validity.

        Binary Ninja does not expose a universal validity revision for plugin
        commands, so cache reuse is conservative: selected function/address,
        selection, current function, and view type all participate. Callers
        can still force discovery when a plugin changes external state.
        """
        current = getattr(bv, "current_function", None)
        selection = getattr(bv, "selection", None)
        return (
            getattr(function, "start", None),
            getattr(current, "start", None),
            getattr(bv, "current_address", None),
            getattr(selection, "start", None),
            getattr(selection, "end", None),
            str(getattr(bv, "view_type", "")),
        )

    @staticmethod
    def _identifier(name: str) -> str:
        return "cmd_" + hashlib.sha256(name.encode("utf-8")).hexdigest()[:12]

    @staticmethod
    def _context(bv, function=None) -> PluginCommandContext:
        context = PluginCommandContext(bv)
        if function is not None:
            context.function = function
            context.address = function.start
        return context
