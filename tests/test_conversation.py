from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _silvergun.conversation import ConversationState, acknowledgement
from _silvergun.contracts import CapabilitySpec, normalize_result


class ConversationLayerTests(unittest.TestCase):
    def test_acknowledgement_is_request_and_capability_aware(self):
        text = acknowledgement(
            "Search the binary for purchase related functions",
            "category",
            ("bn_find_functions", "get_xrefs"),
        )
        self.assertIn("purchase", text.lower())
        self.assertIn("callers and callees", text.lower())
        self.assertNotIn("starting investigation round", text.lower())

    def test_planner_status_is_not_a_final_answer(self):
        answer = "I found purchaseManager at 0x401000. Evidence: Binary Ninja function search."
        self.assertNotIn("validated capabilities", answer.lower())
        self.assertNotIn("starting investigation round", answer.lower())

    def test_follow_up_retains_prior_answer_as_context(self):
        state = ConversationState()
        state.remember("Find purchase functions", "The strongest match is purchaseManager.", "category")
        self.assertIn("purchaseManager", state.context_for_follow_up())
        self.assertEqual(state.last_intent, "category")

    def test_model_interpretation_does_not_become_host_observation(self):
        spec = CapabilitySpec("semantic_search", "Semantic search", "", evidence_types=("function",))
        result = normalize_result(spec, "view-1", {"matches": [{"name": "candidate", "inferred": "purchase flow"}]})
        self.assertEqual(result.evidence[0].source_kind, "model_interpretation")
        self.assertNotEqual(result.evidence[0].source_kind, "host_observation")


if __name__ == "__main__":
    unittest.main()
