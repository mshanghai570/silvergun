#!/usr/bin/env python3
"""Test BoolHunter adapter integration."""

import sys
import os

plugin_path = "/Users/michaelshingara/Library/Application Support/Binary Ninja/plugins/silvergun"
sys.path.insert(0, plugin_path)

# Test imports
try:
    from _silvergun.adapters.boolhunter import BoolHunterAdapter, BOOLHUNTER_TOOLS, BOOLHUNTER_CATEGORIES
    print("PASS: BoolHunterAdapter imports")
except ImportError as e:
    print(f"FAIL: BoolHunterAdapter import: {e}")
    sys.exit(1)

try:
    from _silvergun.adapters import AdapterRegistry
    print("PASS: AdapterRegistry imports")
except ImportError as e:
    print(f"FAIL: AdapterRegistry import: {e}")
    sys.exit(1)

try:
    from _silvergun.agent import LeanAgent
    print("PASS: LeanAgent imports")
except ImportError as e:
    print(f"FAIL: LeanAgent import: {e}")
    sys.exit(1)

# Test tool schemas exist
required_tools = ["boolhunter_quick_scan", "boolhunter_analyze", "boolhunter_batch_scan", "boolhunter_find_category"]
for tool in required_tools:
    if tool not in BOOLHUNTER_TOOLS:
        print(f"FAIL: Missing tool schema: {tool}")
        sys.exit(1)
print(f"PASS: All {len(required_tools)} BoolHunter tool schemas exist")

# Test categories
print(f"PASS: {len(BOOLHUNTER_CATEGORIES)} BoolHunter categories defined")
print(f"      Categories: {', '.join(BOOLHUNTER_CATEGORIES)}")

# Test adapter has correct methods
adapter = BoolHunterAdapter.__new__(BoolHunterAdapter)
required_methods = ["discover", "get_tools", "execute", "capabilities", "is_available"]
for method in required_methods:
    if not hasattr(adapter, method):
        print(f"FAIL: BoolHunterAdapter missing method: {method}")
        sys.exit(1)
print(f"PASS: BoolHunterAdapter has all required methods")

# Test AdapterRegistry has correct methods
registry = AdapterRegistry.__new__(AdapterRegistry)
registry_methods = ["discover", "get_adapter", "is_available", "execute", "capabilities", "tools_for_intent"]
for method in registry_methods:
    if not hasattr(registry, method):
        print(f"FAIL: AdapterRegistry missing method: {method}")
        sys.exit(1)
print(f"PASS: AdapterRegistry has all required methods")

print("\nAll integration tests passed!")
