from __future__ import annotations

import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


STATE = {"approve": 0}


def _install_stub() -> None:
    binaryninja = sys.modules.setdefault("binaryninja", types.ModuleType("binaryninja"))
    if not hasattr(binaryninja, "PluginCommand"):
        binaryninja.PluginCommand = type("PluginCommand", (), {"get_valid_list": staticmethod(lambda _context: {})})
    if not hasattr(binaryninja, "PluginCommandContext"):
        binaryninja.PluginCommandContext = type("PluginCommandContext", (), {"__init__": lambda self, bv: setattr(self, "bv", bv)})
    if not hasattr(binaryninja, "log_warn"):
        binaryninja.log_warn = lambda *_args, **_kwargs: None
    if "binaryninja.interaction" not in sys.modules:
        interaction = types.ModuleType("binaryninja.interaction")
        interaction.get_choice_input = lambda *_args, **_kwargs: STATE["approve"]
        sys.modules["binaryninja.interaction"] = interaction
    if "binaryninja.mainthread" not in sys.modules:
        mainthread = types.ModuleType("binaryninja.mainthread")
        mainthread.is_main_thread = lambda: True
        mainthread.execute_on_main_thread_and_wait = lambda callback: callback()
        sys.modules["binaryninja.mainthread"] = mainthread


_install_stub()

from _silvergun import tools as tools_module
from _silvergun.external import ExternalCommandIndex
from _silvergun.patchlog import PatchJournal
from _silvergun.tools import NativeTools


class Token:
    def __init__(self, text):
        self.text = text


class FakeArch:
    # Minimal x86-ish decoder: one entry per first opcode byte.
    _TABLE = {0x90: (1, "nop"), 0x85: (2, "test eax, eax"), 0x74: (2, "je"), 0xC3: (1, "ret"), 0xB8: (5, "mov eax, imm32")}

    def get_instruction_text(self, data, address):
        first = data[0] if data else 0
        length, text = self._TABLE.get(first, (1, "db"))
        return [Token(text)], length

    def assemble(self, code, address):
        code = code.strip().lower()
        if code == "nop":
            return b"\x90"
        if code == "ret":
            return b"\xc3"
        if code.startswith("mov eax,"):
            value = int(code.split(",", 1)[1].strip(), 0)
            return b"\xb8" + value.to_bytes(4, "little")
        if code.startswith("jmp"):
            return b"\xe9" + b"\x00\x00\x00\x00"
        return None


class FakeFunction:
    def __init__(self, start):
        self.start = start
        self.name = "sub_401000"
        self.total_bytes = 0x20
        self.type = "int32_t sub_401000(void)"
        self.parameter_vars = []
        self.vars = []
        self.callers = []
        self.callees = []
        self.hlil = []


class FakeView:
    def __init__(self, data: bytes, base: int = 0x401000):
        self._data = bytearray(data)
        self.base = base
        self.arch = FakeArch()
        self.functions = [FakeFunction(base)]
        self.writes = []
        self.analysis_updates = 0
        self.file = type("File", (), {"filename": "sample.bin"})()

    def read(self, address, length):
        offset = int(address) - self.base
        chunk = bytes(self._data[offset:offset + length])
        return chunk + b"\x00" * (length - len(chunk))

    def write(self, address, data):
        offset = int(address) - self.base
        self._data[offset:offset + len(data)] = data
        self.writes.append((int(address), bytes(data)))
        return len(data)

    def get_function_at(self, address):
        return self.functions[0] if int(address) == self.base else None

    def get_function_containing(self, address):
        return self.functions[0]

    def update_analysis_and_wait(self):
        self.analysis_updates += 1


class PluginPatchTests(unittest.TestCase):
    def setUp(self):
        self._home = tempfile.TemporaryDirectory()
        self._original_home = os.environ.get("HOME")
        os.environ["HOME"] = self._home.name
        self._original_choice = tools_module.get_choice_input
        tools_module.get_choice_input = lambda *_args, **_kwargs: STATE["approve"]
        STATE["approve"] = 0

    def tearDown(self):
        tools_module.get_choice_input = self._original_choice
        if self._original_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self._original_home
        self._home.cleanup()

    def _tools(self, data: bytes) -> tuple[FakeView, NativeTools]:
        view = FakeView(data)
        return view, NativeTools(view, view.functions[0], ExternalCommandIndex(), 8000)

    def test_disassemble_reports_instruction_bytes_and_lengths(self):
        view, tools = self._tools(b"\x85\xc0\x74\x05\xc3")
        payload = json.loads(tools.execute("disassemble", {"count": 3}))
        self.assertEqual([row["length"] for row in payload["instructions"]], [2, 2, 1])
        self.assertEqual(payload["instructions"][0]["bytes"], "85 c0")
        self.assertEqual(payload["instructions"][0]["text"], "test eax, eax")

    def test_assembly_patch_pads_to_instruction_boundary_and_journals(self):
        view, tools = self._tools(b"\xb8\x03\x00\x00\x00\xc3")
        STATE["approve"] = 1
        payload = json.loads(tools.execute("apply_assembly_patch", {"address": "0x401000", "assembly": "ret", "reason": "disable check"}))
        self.assertTrue(payload["applied"])
        self.assertEqual(payload["padded_nops"], 4)
        self.assertEqual(view.writes[0][1], b"\xc3\x90\x90\x90\x90")
        self.assertEqual(payload["pending_undo"], 1)
        self.assertEqual(view.analysis_updates, 1)

    def test_assembly_patch_requires_approval_before_writing(self):
        view, tools = self._tools(b"\xb8\x03\x00\x00\x00")
        STATE["approve"] = 0
        result = tools.execute("apply_assembly_patch", {"address": "0x401000", "assembly": "ret", "reason": "x"})
        self.assertEqual(result, "User declined the patch.")
        self.assertEqual(view.writes, [])

    def test_patch_readback_failure_restores_original_and_is_not_journaled(self):
        view, tools = self._tools(b"\x90")
        STATE["approve"] = 1
        real_read = view.read
        reads = 0

        def stale_read(address, length):
            nonlocal reads
            reads += 1
            if reads == 2:
                return b"\x90"
            return real_read(address, length)

        view.read = stale_read
        result = tools.execute("apply_patch", {"address": "0x401000", "bytes_hex": "cc", "reason": "trap"})
        self.assertIn("verification failed", result.lower())
        self.assertEqual(view._data[0], 0x90)
        self.assertEqual(PatchJournal("sample.bin").summary()["pending"], 0)

    def test_assembly_patch_rejects_replacement_larger_than_allowed_span(self):
        view, tools = self._tools(b"\x90\x90\x90\x90\x90\x90\x90\x90")
        STATE["approve"] = 1
        result = tools.execute("apply_assembly_patch", {"address": "0x401000", "assembly": "mov eax, 6", "instructions": 1, "reason": "x"})
        self.assertIn("does not fit", result)
        self.assertEqual(view.writes, [])

    def test_undo_restores_original_bytes_and_marks_history(self):
        view, tools = self._tools(b"\xb8\x03\x00\x00\x00")
        STATE["approve"] = 1
        tools.execute("apply_assembly_patch", {"address": "0x401000", "assembly": "mov eax, 6", "reason": "tune"})
        self.assertEqual(view.writes[0][1], b"\xb8\x06\x00\x00\x00")
        payload = json.loads(tools.execute("undo_last_patch", {}))
        self.assertTrue(payload["undone"])
        self.assertEqual(view.writes[1][1], b"\xb8\x03\x00\x00\x00")
        self.assertEqual(payload["remaining"], 0)

    def test_undo_refuses_to_overwrite_bytes_changed_after_patch(self):
        view, tools = self._tools(b"\xb8\x03\x00\x00\x00")
        STATE["approve"] = 1
        tools.execute("apply_assembly_patch", {"address": "0x401000", "assembly": "mov eax, 6", "reason": "tune"})
        view._data[:5] = b"\xb8\x07\x00\x00\x00"
        writes_before = len(view.writes)
        payload = json.loads(tools.execute("undo_last_patch", {}))
        self.assertFalse(payload["undone"])
        self.assertTrue(payload["conflict"])
        self.assertEqual(len(view.writes), writes_before)
        self.assertEqual(PatchJournal("sample.bin").summary()["pending"], 1)

    def test_partial_undo_keeps_journal_entry_pending(self):
        view, tools = self._tools(b"\xb8\x03\x00\x00\x00")
        STATE["approve"] = 1
        tools.execute("apply_assembly_patch", {"address": "0x401000", "assembly": "mov eax, 6", "reason": "tune"})
        original_write = view.write

        def partial_write(address, data):
            if bytes(data) == b"\xb8\x03\x00\x00\x00":
                original_write(address, data[:2])
                return 2
            return original_write(address, data)

        view.write = partial_write
        payload = json.loads(tools.execute("undo_last_patch", {}))
        self.assertFalse(payload["undone"])
        self.assertEqual(payload["written"], 2)
        self.assertEqual(PatchJournal("sample.bin").summary()["pending"], 1)

    def test_undo_without_history_is_reported_plainly(self):
        _view, tools = self._tools(b"\xc3")
        self.assertEqual(tools.execute("undo_last_patch", {}), "No Silvergun patch is available to undo for this binary.")

    def test_patch_history_lists_pending_entries(self):
        _view, tools = self._tools(b"\xb8\x03\x00\x00\x00")
        STATE["approve"] = 1
        tools.execute("apply_patch", {"address": "0x401000", "bytes_hex": "b8 06 00 00 00", "reason": "raw"})
        payload = json.loads(tools.execute("patch_history", {}))
        self.assertEqual(payload["pending_undo"], 1)
        self.assertEqual(payload["entries"][-1]["tool"], "apply_patch")


class PatchJournalTests(unittest.TestCase):
    def setUp(self):
        self._home = tempfile.TemporaryDirectory()
        self._original_home = os.environ.get("HOME")
        os.environ["HOME"] = self._home.name

    def tearDown(self):
        if self._original_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self._original_home
        self._home.cleanup()

    def test_record_last_and_summary_normalize_hex(self):
        journal = PatchJournal("sample.bin")
        entry = journal.record(0x401000, b"\x90", b"\xcc", "trap", tool="apply_patch")
        self.assertEqual(entry["address"], "0x401000")
        self.assertEqual(entry["original_hex"], "90")
        self.assertEqual(journal.last(), journal.entries()[0])
        summary = journal.summary()
        self.assertEqual(summary["entries"], 1)
        self.assertEqual(summary["pending"], 1)

    def test_mark_undone_clears_pending_and_last(self):
        journal = PatchJournal("sample.bin")
        entry = journal.record(0x401000, b"\x90", b"\xcc", "trap")
        journal.mark_undone(entry)
        self.assertIsNone(journal.last())
        self.assertEqual(journal.summary()["pending"], 0)
        self.assertTrue(journal.entries()[0]["undone"])

    def test_identity_normalizes_relative_and_absolute_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / "app.bin"
            binary.write_bytes(b"binary")
            original = os.getcwd()
            os.chdir(root)
            try:
                self.assertEqual(PatchJournal("app.bin").path, PatchJournal(str(binary)).path)
            finally:
                os.chdir(original)


if __name__ == "__main__":
    unittest.main()
