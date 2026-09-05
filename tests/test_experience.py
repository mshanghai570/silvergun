from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _silvergun.experience import ExperienceMemory


class ExperienceTests(unittest.TestCase):
    def setUp(self):
        self.memory = ExperienceMemory.get()

    def test_record_and_find_similar(self):
        self.memory.record(
            request="find buffer overflow in login",
            intent="vulnerabilities",
            tool_sequence=("get_function_context", "review_vulnerabilities"),
            evidence_quality="moderate",
            outcome="success",
        )
        results = self.memory.find_similar("find buffer overflow")
        self.assertGreater(len(results), 0)

    def test_empty_find_similar(self):
        results = self.memory.find_similar("nonexistent term xyzabc123")
        self.assertEqual(len(results), 0)

    def test_get_best_strategy(self):
        self.memory.record(
            request="triage main",
            intent="triage",
            tool_sequence=("semantic_search", "get_function_context"),
            evidence_quality="strong",
            outcome="success",
        )
        strategy = self.memory.get_best_strategy("triage main")
        self.assertIsNotNone(strategy)


if __name__ == "__main__":
    unittest.main()
