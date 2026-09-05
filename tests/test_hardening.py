import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
import sys
import types

binaryninja = sys.modules.setdefault("binaryninja", types.ModuleType("binaryninja"))
if not hasattr(binaryninja, "PluginCommand"):
    binaryninja.PluginCommand = type("PluginCommand", (), {"get_valid_list": staticmethod(lambda _context: {})})
if not hasattr(binaryninja, "PluginCommandContext"):
    binaryninja.PluginCommandContext = type("PluginCommandContext", (), {"__init__": lambda self, bv: setattr(self, "bv", bv)})
if not hasattr(binaryninja, "log_warn"):
    binaryninja.log_warn = lambda *_args, **_kwargs: None
if "binaryninja.interaction" not in sys.modules:
    interaction = types.ModuleType("binaryninja.interaction")
    interaction.get_choice_input = lambda *_args, **_kwargs: 0
    sys.modules["binaryninja.interaction"] = interaction
if "binaryninja.mainthread" not in sys.modules:
    mainthread = types.ModuleType("binaryninja.mainthread")
    mainthread.is_main_thread = lambda: True
    mainthread.execute_on_main_thread_and_wait = lambda callback: callback()
    sys.modules["binaryninja.mainthread"] = mainthread

from _silvergun.adapters.binaryninja_builtins import BinaryNinjaBuiltinsAdapter
from _silvergun.contracts import CapabilitySpec, normalize_result
from _silvergun.events import EventEmitter, EventType, InvestigationEvent, get_event_emitter, reset_event_emitter
from _silvergun.external import ExternalCommandIndex
from _silvergun.notebook import AnalysisNotebook


class Instruction:
    def __init__(self, text):
        self.text = text
    def __str__(self):
        return self.text


class Function:
    def __init__(self, address, name):
        self.start = address
        self.name = name
        self.callers = []
        self.callees = []
        self.hlil = [[Instruction(f"return {name}()")]]
        self.analyzed = 0
    def analyze(self):
        self.analyzed += 1


class String:
    def __init__(self, address, value):
        self.address = address
        self.value = value


class View:
    def __init__(self, functions):
        self.functions = functions
        self.current_function = functions[0] if functions else None
        self.current_address = functions[0].start if functions else None
        self.selection = type("Selection", (), {"start": 0, "end": 0})()
        self.view_type = "Raw"
        self.strings = []
    def get_function_at(self, address):
        return next((f for f in self.functions if f.start == address), None)
    def get_function_containing(self, address):
        return self.get_function_at(address)
    def get_strings(self):
        return self.strings


class HardeningTests(unittest.TestCase):
    def adapter(self, view):
        return BinaryNinjaBuiltinsAdapter.create(view)

    def test_decompile_returns_bounded_hlil_and_distinguishes_missing(self):
        function = Function(0x1000, "purchase")
        view = View([function])
        adapter = self.adapter(view)
        result = json.loads(adapter.execute("bn_decompile", {"address": "0x1000", "timeout": 2}))
        self.assertEqual(result["status"], "completed")
        self.assertIn("return purchase()", result["hlil"])
        self.assertLessEqual(len(result["hlil"]), 6000)
        missing = json.loads(adapter.execute("bn_decompile", {"address": "0x9999"}))
        self.assertEqual(missing["status"], "missing_function")
        function.hlil = None
        unavailable = json.loads(adapter.execute("bn_decompile", {"address": "0x1000"}))
        self.assertEqual(unavailable["status"], "unavailable_hlil")

    def test_context_hint_does_not_materialize_hlil(self):
        class LazyFunction(Function):
            def __init__(self, address, name):
                super().__init__(address, name)
                self.hlil_reads = 0

            @property
            def hlil(self):
                self.hlil_reads += 1
                return [[Instruction("return 1")]]

            @hlil.setter
            def hlil(self, value):
                self._hlil = value

        function = LazyFunction(0x1000, "purchase")
        view = View([function])
        from _silvergun.tools import NativeTools
        native = NativeTools(view, function, ExternalCommandIndex(), 8000)
        json.loads(native.context_hint())
        self.assertEqual(function.hlil_reads, 0)

    def test_native_snapshot_is_reused_within_investigation(self):
        function = Function(0x1000, "purchase")
        function.type = "void purchase()"
        view = View([function])
        from _silvergun.tools import NativeTools
        native = NativeTools(view, function, ExternalCommandIndex(), 8000)
        calls = []
        original = native._snapshot
        native._snapshot = lambda target: (calls.append(target.start) or original(target))
        native.execute("get_function_context", {})
        native.execute("get_verification", {})
        self.assertEqual(calls, [0x1000])

    def test_analyze_modes_do_not_claim_zero_work(self):
        function = Function(0x1000, "purchase")
        view = View([function])
        adapter = self.adapter(view)
        address = json.loads(adapter.execute("bn_analyze", {"address": "0x1000"}))
        self.assertEqual(address["functions_analyzed"], 1)
        self.assertEqual(address["mode"], "address")
        conflict = json.loads(adapter.execute("bn_analyze", {"address": "0x1000", "function_only": True, "full_analysis": True}))
        self.assertEqual(conflict["mode"], "address")
        full = json.loads(adapter.execute("bn_analyze", {"full_analysis": True}))
        self.assertEqual(full["functions_analyzed"], 1)
        invalid = json.loads(adapter.execute("bn_analyze", {"address": "not-an-address"}))
        self.assertEqual(invalid["status"], "invalid_address")
        view.current_function = None
        missing = json.loads(adapter.execute("bn_analyze", {"function_only": True}))
        self.assertEqual(missing["status"], "missing_current_function")
        empty = json.loads(self.adapter(View([])).execute("bn_analyze", {"full_analysis": True}))
        self.assertEqual(empty["status"], "no_work")

    def test_xrefs_traverse_depth_direction_and_cycles(self):
        a, b, c, d = [Function(0x1000 + i * 0x10, name) for i, name in enumerate("abcd")]
        a.callees = [b]; b.callers = [a]; b.callees = [c]; c.callers = [b]; c.callees = [a]; a.callers = [c]
        view = View([a, b, c, d])
        result = json.loads(self.adapter(view).execute("bn_find_cross_references", {"address": "0x1000", "direction": "callees", "max_depth": 2}))
        self.assertEqual({node["depth"] for node in result["nodes"]}, {0, 1, 2})
        self.assertNotIn("0x1030", {node["address"] for node in result["nodes"]})
        self.assertTrue(all(edge["depth"] <= 2 for edge in result["edges"]))

    def test_string_regex_flags_invalid_regex_literal_and_min_length(self):
        f = Function(0x1000, "main")
        view = View([f])
        view.strings = [String(1, "StoreKit PURCHASE"), String(2, "purchase"), String(3, "x")]
        adapter = self.adapter(view)
        insensitive = json.loads(adapter.execute("bn_search_strings", {"query": "purchase", "regex": True, "case_sensitive": False, "min_length": 4}))
        self.assertEqual(len(insensitive["matches"]), 2)
        sensitive = json.loads(adapter.execute("bn_search_strings", {"query": "purchase", "regex": True, "case_sensitive": True, "min_length": 4}))
        self.assertEqual(len(sensitive["matches"]), 1)
        literal = json.loads(adapter.execute("bn_search_strings", {"query": "PURCHASE", "regex": False, "case_sensitive": True, "min_length": 4}))
        self.assertEqual(len(literal["matches"]), 1)
        invalid = json.loads(adapter.execute("bn_search_strings", {"query": "[", "regex": True}))
        self.assertEqual(invalid["status"], "invalid_regex")
        short = json.loads(adapter.execute("bn_search_strings", {"query": "x", "min_length": 2}))
        self.assertEqual(len(short["matches"]), 0)

    def test_external_cache_changes_when_context_changes(self):
        class Command:
            name = "Contextual"
            description = "depends on selection"
        class Plugin:
            calls = 0
            @staticmethod
            def get_valid_list(context):
                Plugin.calls += 1
                return {"contextual": Command()} if getattr(context.bv, "current_address", 0) == 1 else {}
        import _silvergun.external as external
        original = external.PluginCommand
        external.PluginCommand = Plugin
        try:
            view = View([Function(0x1000, "f")])
            view.current_address = 1
            index = ExternalCommandIndex()
            self.assertEqual(len(index.refresh(view)), 1)
            view.current_address = 2
            self.assertEqual(len(index.refresh(view)), 0)
            self.assertEqual(Plugin.calls, 2)
        finally:
            external.PluginCommand = original

    def test_notebook_identity_normalizes_symlink_and_relative_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / "app.bin"
            binary.write_bytes(b"binary")
            link = root / "alias.bin"
            link.symlink_to(binary)
            original = os.getcwd()
            os.chdir(root)
            try:
                self.assertEqual(AnalysisNotebook("app.bin").path, AnalysisNotebook(str(link)).path)
            finally:
                os.chdir(original)

    def test_evidence_marks_interpretation_without_fabricating_observation(self):
        spec = CapabilitySpec("review", "Review", "Interpret", evidence_types=("finding",))
        result = normalize_result(spec, "view", {"matches": [{"name": "x", "interpretation": "likely purchase"}]})
        self.assertEqual(result.evidence[0].source_kind, "model_interpretation")

    def test_event_emitter_contexts_are_isolated(self):
        values = []
        reset_event_emitter()
        main = get_event_emitter()
        def worker():
            reset_event_emitter()
            get_event_emitter().add_listener(lambda event: values.append("worker"))
            get_event_emitter().emit(InvestigationEvent(EventType.TOOL_STARTED, message="worker"))
        thread = threading.Thread(target=worker)
        thread.start(); thread.join()
        main.emit(InvestigationEvent(EventType.TOOL_STARTED, message="main"))
        self.assertEqual(values, ["worker"])
        self.assertIs(main, get_event_emitter())


if __name__ == "__main__":
    unittest.main()
