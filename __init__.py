# Copyright (c) 2026 MShin13
# SPDX-License-Identifier: MIT
"""Lean Ninja Binary Ninja plugin entry point."""

from binaryninja import PluginCommand, log_info

from leanninja.commands import (
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
from leanninja.config import register_settings


register_settings()

PluginCommand.register("Lean Ninja\\Configure Provider...", "Configure an OpenAI-compatible endpoint and load models.", configure_provider)
PluginCommand.register("Lean Ninja\\Ask...", "Send a compact, routed request to Lean Ninja.", run_prompt)
PluginCommand.register_for_function("Lean Ninja\\Explain Function", "Explain the selected function using compact decompilation context.", explain_current)
PluginCommand.register_for_function("Lean Ninja\\Smart Patch", "Propose a precise patch for the selected function; never applies without approval.", smart_patch_current)
PluginCommand.register_for_function("Lean Ninja\\Rename Function", "Suggest and confirm a semantic function name.", rename_current)
PluginCommand.register_for_function("Lean Ninja\\Suggest Types", "Recover and propose a function signature and variable types.", suggest_types_current)
PluginCommand.register_for_function("Lean Ninja\\Analyze Xrefs", "Analyze callers, callees, and cross-reference implications.", xref_analysis_current)
PluginCommand.register_for_function("Lean Ninja\\Annotate Function", "Draft evidence-backed function comments and tags.", annotate_current)
PluginCommand.register_for_function("Lean Ninja\\Find Vulnerabilities", "Perform a focused vulnerability review.", find_vulnerabilities_current)
PluginCommand.register("Lean Ninja\\Inspect Available Capabilities", "List native tools and compatible installed plugin commands.", inspect_capabilities)

log_info("Lean Ninja loaded", "Lean Ninja")
