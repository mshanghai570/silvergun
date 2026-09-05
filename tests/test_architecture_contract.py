import json
import unittest

from _silvergun.capability_registry import CapabilityRegistry, plan_from_route
from _silvergun.contracts import (
    CapabilitySpec,
    CapabilityStatus,
    PlanStep,
    InvestigationPlan,
    PlanValidationError,
    normalize_result,
    validate_plan,
    view_context_from_payload,
)


SCHEMA = {
    "type": "function",
    "function": {
        "name": "semantic_search",
        "description": "Search function meaning",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
    },
}


class ArchitectureContractTests(unittest.TestCase):
    def test_registry_is_source_of_truth_for_validated_plan(self):
        registry = CapabilityRegistry({"semantic_search": SCHEMA})
        plan = plan_from_route("find purchase functions", "category", ("semantic_search",), registry)
        self.assertEqual(plan.steps[0].capability_id, "semantic_search")
        self.assertEqual(registry.get("semantic_search").status, CapabilityStatus.AVAILABLE)

    def test_unknown_capability_is_rejected(self):
        registry = CapabilityRegistry({"semantic_search": SCHEMA})
        with self.assertRaises(PlanValidationError):
            plan_from_route("bad", "general", ("imaginary_tool",), registry)

    def test_unavailable_capability_is_rejected(self):
        spec = CapabilitySpec("broken", "Broken", "Unavailable", status=CapabilityStatus.BROKEN)
        with self.assertRaises(PlanValidationError):
            validate_plan(InvestigationPlan("bad", "general", (PlanStep("broken"),)), {"broken": spec})

    def test_result_normalization_preserves_provenance_and_address(self):
        spec = CapabilitySpec("semantic_search", "Semantic", "Search", evidence_types=("function",))
        result = normalize_result(spec, "0xview", {"matches": [{"address": "0x401000", "name": "purchaseManager", "score": 0.9}]})
        self.assertTrue(result.success)
        self.assertEqual(result.evidence[0].address, "0x401000")
        self.assertEqual(result.evidence[0].provenance, "Semantic")
        self.assertEqual(result.evidence[0].binary_view_id, "0xview")

    def test_binary_view_context_requires_active_view(self):
        payload = {"binary_view_attached": True, "filename": "app", "function_count": 4, "current_function": {"address": "0x401000", "name": "main"}}
        context = view_context_from_payload(json.dumps(payload), view_id="0xview")
        self.assertEqual(context.binary_view_id, "0xview")
        self.assertEqual(context.current_function_name, "main")


if __name__ == "__main__":
    unittest.main()
