from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _silvergun.events import EventFormatter, EventType, InvestigationEvent


class StreamingMessageTests(unittest.TestCase):
    def test_memory_message_prefix(self):
        msg = "[MEMORY] Experience retrieved: high confidence match"
        self.assertTrue(msg.startswith("[MEMORY]"))

    def test_strategy_message_prefix(self):
        msg = "[STRATEGY] triage - sequential"
        self.assertTrue(msg.startswith("[STRATEGY]"))
        self.assertIn(" - ", msg)

    def test_round_message_prefix(self):
        msg = "[ROUND] 2 / 5"
        self.assertTrue(msg.startswith("[ROUND]"))

    def test_tool_message_prefix(self):
        msg = "[TOOL] get_function_context"
        self.assertTrue(msg.startswith("[TOOL]"))

    def test_model_message_prefix(self):
        msg = "[MODEL] Generating response..."
        self.assertTrue(msg.startswith("[MODEL]"))

    def test_info_message_handling(self):
        msg = "ROUTE / triage / 4 NATIVE TOOLS SELECTED"
        self.assertFalse(msg.startswith("["))


class NarrationTests(unittest.TestCase):
    """The results panel must show plain-English updates, not bracket jargon."""

    def test_string_search_start_is_plain_english_with_query(self):
        event = InvestigationEvent(
            event_type=EventType.TOOL_STARTED,
            tool_name="bn_search_strings",
            message="Searching for string: password",
        )
        text = EventFormatter.narrate(event)
        self.assertTrue(text)
        self.assertFalse(text.startswith("["))
        self.assertIn("strings", text.lower())
        self.assertIn("password", text.lower())

    def test_symbol_search_start_is_plain_english(self):
        event = InvestigationEvent(
            event_type=EventType.TOOL_STARTED,
            tool_name="bn_search_symbols",
            message="Searching symbols for: parse_header",
        )
        text = EventFormatter.narrate(event)
        self.assertTrue(text)
        self.assertFalse(text.startswith("["))
        self.assertIn("symbol", text.lower())

    def test_progress_narration_reports_scanned_counts(self):
        event = InvestigationEvent(
            event_type=EventType.TOOL_PROGRESS,
            tool_name="bn_search_strings",
            message="Scanned 500 strings",
        )
        text = EventFormatter.narrate(event)
        self.assertTrue(text)
        self.assertFalse(text.startswith("["))
        self.assertIn("500", text)

    def test_result_narration_reports_match_count(self):
        event = InvestigationEvent(
            event_type=EventType.TOOL_RESULT,
            tool_name="bn_search_strings",
            message="Found 3 string matches",
            data={"matches": 3, "scanned": 10},
        )
        text = EventFormatter.narrate(event)
        self.assertTrue(text)
        self.assertIn("3", text)
        self.assertFalse(text.startswith("["))

    def test_duplicate_result_is_explained(self):
        event = InvestigationEvent(
            event_type=EventType.TOOL_RESULT,
            tool_name="get_function_context",
            message="Skipped duplicate call: get_function_context:{}...",
        )
        text = EventFormatter.narrate(event)
        self.assertIn("reus", text.lower())

    def test_unknown_tool_still_narrates(self):
        event = InvestigationEvent(
            event_type=EventType.TOOL_STARTED,
            tool_name="mystery_tool",
            message="",
        )
        self.assertTrue(EventFormatter.narrate(event))

    def test_completion_narration(self):
        event = InvestigationEvent(event_type=EventType.INVESTIGATION_COMPLETED, intent="triage")
        text = EventFormatter.narrate(event)
        self.assertIn("complete", text.lower())
        self.assertFalse(text.startswith("["))

    def test_tool_completed_is_skipped_to_keep_transcript_lean(self):
        event = InvestigationEvent(event_type=EventType.TOOL_COMPLETED, tool_name="bn_search_strings")
        self.assertEqual(EventFormatter.narrate(event), "")

    def test_narration_never_contains_bracket_prefixes(self):
        events = [
            InvestigationEvent(event_type=EventType.TOOL_STARTED, tool_name="get_xrefs", message="Executing get_xrefs"),
            InvestigationEvent(event_type=EventType.ROUND_STARTED, round_number=2),
            InvestigationEvent(event_type=EventType.PLANNER_STARTED, intent="map"),
            InvestigationEvent(event_type=EventType.MEMORY_SEARCH, message="Searching previous experience..."),
            InvestigationEvent(event_type=EventType.ANALYSIS_WARNING, message="Invalid address skipped: 0x0"),
            InvestigationEvent(event_type=EventType.TOOL_FAILED, tool_name="semantic_search", message="failed", error="boom"),
        ]
        for event in events:
            text = EventFormatter.narrate(event)
            self.assertTrue(text, f"narration missing for {event.event_type}")
            self.assertFalse(text.startswith("["), f"technical prefix leaked: {text}")


if __name__ == "__main__":
    unittest.main()
