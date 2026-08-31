from __future__ import annotations

import json
from pathlib import Path
import sys
import types
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


_choice_calls = []


class FakePluginCommand:
    @staticmethod
    def get_valid_list(_context):
        return {}


class FakePluginCommandContext:
    def __init__(self, bv):
        self.bv = bv


def install_binaryninja_stub():
    binaryninja = types.ModuleType("binaryninja")
    binaryninja.PluginCommand = FakePluginCommand
    binaryninja.PluginCommandContext = FakePluginCommandContext
    binaryninja.log_warn = lambda *_args, **_kwargs: None
    interaction = types.ModuleType("binaryninja.interaction")
    interaction.get_choice_input = lambda *args: _choice_calls.append(args) or 0
    mainthread = types.ModuleType("binaryninja.mainthread")
    mainthread.is_main_thread = lambda: True
    mainthread.execute_on_main_thread_and_wait = lambda callback: callback()
    sys.modules["binaryninja"] = binaryninja
    sys.modules["binaryninja.interaction"] = interaction
    sys.modules["binaryninja.mainthread"] = mainthread


install_binaryninja_stub()
from _silvergun import tools as tools_module
from _silvergun.agent import LeanAgent
from _silvergun.external import ExternalCommandIndex
from _silvergun.tools import NativeTools


class Instruction:
    def __init__(self, address, text):
        self.address = address
        self.text = text

    def __str__(self):
        return self.text


class Variable:
    name = "arg1"
    type = "char *"
    source_type = "FunctionParameter"
    storage = 0


class Function:
    start = 0x401000
    name = "sub_401000"
    total_bytes = 22
    type = "int32_t sub_401000(char *arg1)"
    parameter_vars = [Variable()]
    vars = []
    callers = []
    callees = []
    hlil = [[Instruction(0x401000, "return puts(arg1)")]]


class View:
    def __init__(self):
        self.functions = [Function()]
        self.writes = []

    def get_function_at(self, address):
        return self.functions[0] if address == 0x401000 else None

    def get_function_containing(self, address):
        return self.functions[0] if 0x401000 <= address < 0x401016 else None

    def read(self, _address, length):
        return b"\x90" * length

    def write(self, address, data):
        self.writes.append((address, data))
        return len(data)


class NativeToolsTests(unittest.TestCase):
    def setUp(self):
        _choice_calls.clear()
        self.view = View()
        self.tools = NativeTools(self.view, self.view.functions[0], ExternalCommandIndex(), 4000)

    def test_agent_context_hint_confirms_attached_binary(self):
        payload = json.loads(self.tools.context_hint())
        self.assertTrue(payload["binary_view_attached"])
        self.assertEqual(payload["current_function"]["address"], "0x401000")

    def test_context_is_compact_json(self):
        payload = json.loads(self.tools.execute("get_function_context", {}))
        self.assertEqual(payload["address"], "0x401000")
        self.assertIn("puts", payload["hlil"])
        self.assertEqual(payload["parameters_and_locals"], ["arg1: char *"])

    def test_host_reads_are_marshaled_from_agent_thread(self):
        original_is_main_thread = tools_module.is_main_thread
        original_execute = tools_module.execute_on_main_thread_and_wait
        dispatches = []
        tools_module.is_main_thread = lambda: False
        tools_module.execute_on_main_thread_and_wait = lambda callback: dispatches.append(callback) or callback()
        try:
            native = NativeTools(self.view, self.view.functions[0], ExternalCommandIndex(), 4000)
            native.context_hint()
            native.execute("get_function_context", {})
            native.snapshots(["0x401000"])
        finally:
            tools_module.is_main_thread = original_is_main_thread
            tools_module.execute_on_main_thread_and_wait = original_execute
        self.assertGreaterEqual(len(dispatches), 4)

    def test_malformed_tool_call_does_not_abort_the_agent(self):
        class Settings:
            max_steps = 2
            parallel_jobs = 1
            model = "test-model"

        class Client:
            def __init__(self):
                self.calls = 0

            def chat(self, _model, _messages, _tools, **_kwargs):
                self.calls += 1
                if self.calls == 1:
                    return type("Completion", (), {"content": "", "tool_calls": ({"id": "bad_1", "function": {"name": "get_function_context", "arguments": "not-json"}},)})()
                return type("Completion", (), {"content": "Recovered after malformed tool call.", "tool_calls": ()})()

        result = LeanAgent(Client(), Settings()).run("Explain this function", self.tools)
        self.assertEqual(result.answer, "Recovered after malformed tool call.")

    def test_patch_never_writes_when_approval_is_declined(self):
        result = self.tools.execute("apply_patch", {"address": "0x401000", "bytes_hex": "90 90", "reason": "test"})
        self.assertEqual(result, "User declined the patch.")
        self.assertEqual(self.view.writes, [])
        self.assertEqual(len(_choice_calls), 1)


if __name__ == "__main__":
    unittest.main()
