"""Adapter exposing compatible installed Binary Ninja commands as compact capabilities."""

from __future__ import annotations

from collections import OrderedDict
import hashlib
from typing import Any

from binaryninja import PluginCommand, PluginCommandContext

from .router import ExternalCapability
<<<<<<< HEAD
from .events import emit_tool_started, emit_tool_result, emit_tool_completed, emit_tool_failed
=======
>>>>>>> 1630c0d351f49b041623dfd9440b74c011846a37


class ExternalCommandIndex:
    """Indexes valid commands in the current context without loading a large plugin framework."""

    _cache: "OrderedDict[tuple[int, int | None], tuple[dict[str, Any], tuple[ExternalCapability, ...]]]" = OrderedDict()
    _cache_limit = 48

    def __init__(self) -> None:
        self._commands: dict[str, Any] = {}

    def refresh(self, bv, function=None, *, force: bool = False) -> list[ExternalCapability]:
        key = (id(bv), getattr(function, "start", None))
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
            capabilities.append(ExternalCapability(identifier, name, description, mutation_risk=True))
        ordered = tuple(sorted(capabilities, key=lambda capability: capability.name.lower()))
        self._cache[key] = (self._commands.copy(), ordered)
        self._cache.move_to_end(key)
        while len(self._cache) > self._cache_limit:
            self._cache.popitem(last=False)
        return list(ordered)

    def execute(self, identifier: str, bv, function=None) -> str:
        command = self._commands.get(identifier)
        if command is None:
<<<<<<< HEAD
            emit_tool_failed("external_command", f"Command unavailable: {identifier}", "Plugin capability not found")
            raise KeyError("The requested plugin capability is unavailable in the current Binary Ninja context.")
        
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
=======
            raise KeyError("The requested plugin capability is unavailable in the current Binary Ninja context.")
        command.execute(self._context(bv, function))
        return f"Executed external command: {getattr(command, 'name', identifier)}"
>>>>>>> 1630c0d351f49b041623dfd9440b74c011846a37

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
