# Copyright (c) 2026 MShin13
# SPDX-License-Identifier: MIT
"""Silvergun Binary Ninja plugin entry point."""

from binaryninja import PluginCommand, log_info, log_warn

from _silvergun.commands import (
    annotate_current,
    configure_provider,
    disassemble_current,
    explain_current,
    find_vulnerabilities_current,
    inspect_capabilities,
    map_current,
    rename_current,
    run_prompt,
    smart_patch_current,
    suggest_types_current,
    triage_binary,
    undo_patch,
    verify_current,
    xref_analysis_current,
)
from _silvergun.config import register_settings
try:
    from _silvergun import sidebar  # noqa: F401 - registers SilvergunSidebarWidgetType
except Exception as error:
    # Keep the core plugin commands available if an older GUI lacks a sidebar API.
    log_warn(f"Sidebar unavailable; core commands remain enabled: {error}", "Silvergun")


register_settings()

PluginCommand.register("Silvergun\\Configure Provider...", "Configure an OpenAI-compatible endpoint and load models.", configure_provider)
PluginCommand.register("Silvergun\\Ask...", "Send a compact, routed request to Silvergun.", run_prompt)
PluginCommand.register_for_function("Silvergun\\Explain Function", "Explain the selected function using compact decompilation context.", explain_current)
PluginCommand.register_for_function("Silvergun\\Smart Patch", "Propose a precise patch for the selected function; never applies without approval.", smart_patch_current)
PluginCommand.register_for_function("Silvergun\\Disassemble Function", "Read instruction-level disassembly with byte boundaries.", disassemble_current)
PluginCommand.register("Silvergun\\Undo Last Patch", "Restore the original bytes of the most recent Silvergun patch.", undo_patch)
PluginCommand.register_for_function("Silvergun\\Rename Function", "Suggest and confirm a semantic function name.", rename_current)
PluginCommand.register_for_function("Silvergun\\Suggest Types", "Recover and propose a function signature and variable types.", suggest_types_current)
PluginCommand.register_for_function("Silvergun\\Analyze Xrefs", "Analyze callers, callees, and cross-reference implications.", xref_analysis_current)
PluginCommand.register_for_function("Silvergun\\Annotate Function", "Draft evidence-backed function comments and tags.", annotate_current)
PluginCommand.register_for_function("Silvergun\\Find Vulnerabilities", "Perform a focused vulnerability review.", find_vulnerabilities_current)
PluginCommand.register("Silvergun\\Triage Binary", "Rank likely-interesting functions using local semantic evidence.", triage_binary)
PluginCommand.register_for_function("Silvergun\\Verify Current Function", "Separate proven facts from inferred interpretations.", verify_current)
PluginCommand.register_for_function("Silvergun\\Code Map", "Map local caller/callee relationships.", map_current)
PluginCommand.register("Silvergun\\Inspect Available Capabilities", "List native tools and compatible installed plugin commands.", inspect_capabilities)

log_info("Silvergun loaded", "Silvergun")
