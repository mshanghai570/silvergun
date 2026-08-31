from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _silvergun.notebook import AnalysisNotebook, Finding


class NotebookTests(unittest.TestCase):
    def test_findings_are_durable_and_capped(self):
        with tempfile.TemporaryDirectory() as directory:
            notebook = AnalysisNotebook("sample.bin")
            notebook.path = Path(directory) / "sample.json"
            notebook.add(Finding("Input parser", "Review bounded copy", "0x401000", ("HLIL at 0x401000",), "proven"))
            restored = AnalysisNotebook("sample.bin")
            restored.path = notebook.path
            entries = restored.entries()
            self.assertEqual(entries[0]["title"], "Input parser")
            self.assertEqual(entries[0]["confidence"], "proven")
            self.assertIn("Input parser", restored.compact_context())


if __name__ == "__main__":
    unittest.main()
