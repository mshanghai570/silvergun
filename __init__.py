# Copyright (c) 2026 MShin13
# SPDX-License-Identifier: MIT
"""Silvergun Binary Ninja plugin entry point."""

from binaryninja import PluginCommand, log_info, log_warn

from silvergun.commands import (
    annotate_current,
    configure_provider,
    explain_current,
    find_vulnerabilities_current,
    inspect_capabilities,
    rename_current,
    run_prompt,
    smart_patch_current,
    suggest_types_current,
    xref_analysis_current,
)
from silvergun.config import register_settings
try:
    from silvergun import sidebar  # noqa: F401 - registers SilvergunSidebarWidgetType
except Exception as error:
    # Keep the core plugin commands available if an older GUI lacks a sidebar API.
    log_warn(f"Sidebar unavailable; core commands remain enabled: {error}", "Silvergun")


register_settings()

PluginCommand.register("Silvergun\\Configure Provider...", "Configure an OpenAI-compatible endpoint and load models.", configure_provider)
PluginCommand.register("Silvergun\\Ask...", "Send a compact, routed request to Silvergun.", run_prompt)
PluginCommand.register_for_function("Silvergun\\Explain Function", "Explain the selected function using compact decompilation context.", explain_current)
PluginCommand.register_for_function("Silvergun\\Smart Patch", "Propose a precise patch for the selected function; never applies without approval.", smart_patch_current)
PluginCommand.register_for_function("Silvergun\\Rename Function", "Suggest and confirm a semantic function name.", rename_current)
PluginCommand.register_for_function("Silvergun\\Suggest Types", "Recover and propose a function signature and variable types.", suggest_types_current)
PluginCommand.register_for_function("Silvergun\\Analyze Xrefs", "Analyze callers, callees, and cross-reference implications.", xref_analysis_current)
PluginCommand.register_for_function("Silvergun\\Annotate Function", "Draft evidence-backed function comments and tags.", annotate_current)
PluginCommand.register_for_function("Silvergun\\Find Vulnerabilities", "Perform a focused vulnerability review.", find_vulnerabilities_current)
PluginCommand.register("Silvergun\\Inspect Available Capabilities", "List native tools and compatible installed plugin commands.", inspect_capabilities)

log_info("Silvergun loaded", "Silvergun")
