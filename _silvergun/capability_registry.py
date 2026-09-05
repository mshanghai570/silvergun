"""Runtime capability registry assembled from the active BinaryView context."""
from __future__ import annotations

from typing import Any, Mapping

from .contracts import (
    CapabilitySpec, CapabilityStatus, ExecutionRequirement, InvestigationPlan,
    PlanStep, validate_plan,
)


def _schema_for(tool: Mapping[str, Any]) -> Mapping[str, Any]:
    function = tool.get("function", {}) if isinstance(tool, Mapping) else {}
    return function.get("parameters", {}) if isinstance(function, Mapping) else {}


class CapabilityRegistry:
    """Single source of truth for capabilities available in one investigation."""

    def __init__(self, native_tools: Mapping[str, Mapping[str, Any]], adapter_registry=None, external_capabilities=()) -> None:
        self._specs: dict[str, CapabilitySpec] = {}
        self._schemas: dict[str, Mapping[str, Any]] = {}
        for name, schema in native_tools.items():
            self._add_tool(name, schema, adapter="native", category="analysis", requirements=(ExecutionRequirement.BN_MAIN_THREAD,))
        if adapter_registry is not None:
            for name, adapter in adapter_registry.all_adapters().items():
                for tool_name, schema in adapter.get_tools().items():
                    self._add_tool(tool_name, schema, adapter=name, category=name, requirements=(ExecutionRequirement.BN_MAIN_THREAD,))
        external = list(external_capabilities or ())
        if external:
            self._specs["invoke_external_command"] = CapabilitySpec(
                "invoke_external_command", "Installed plugin command", "Invoke a callable installed plugin command after approval.",
                category="plugin", input_schema={"type": "object"}, evidence_types=("plugin_result",),
                execution_requirements=(ExecutionRequirement.BN_MAIN_THREAD, ExecutionRequirement.USER_APPROVAL,), adapter="external",
            )
        self._external = tuple(external)

    def _add_tool(self, name: str, schema: Mapping[str, Any], *, adapter: str, category: str, requirements=()) -> None:
        function = schema.get("function", {}) if isinstance(schema, Mapping) else {}
        self._schemas[name] = schema
        self._specs[name] = CapabilitySpec(
            capability_id=name,
            name=str(function.get("name", name)),
            description=str(function.get("description", "")),
            category=category,
            input_schema=_schema_for(schema),
            output_schema={"type": "object"},
            evidence_types=("analysis", "function", "search", "plugin_result"),
            execution_requirements=tuple(requirements),
            adapter=adapter,
            status=CapabilityStatus.AVAILABLE,
        )

    def get(self, capability_id: str) -> CapabilitySpec | None:
        return self._specs.get(capability_id)

    def specs(self) -> dict[str, CapabilitySpec]:
        return dict(self._specs)

    def schemas(self, names) -> list[Mapping[str, Any]]:
        return [self._schemas[name] for name in names if name in self._schemas]

    def available_ids(self) -> tuple[str, ...]:
        return tuple(name for name, spec in self._specs.items() if spec.available)

    def cards(self) -> list[str]:
        return [spec.card() for spec in self._specs.values()]


def plan_from_route(goal: str, intent: str, tools: tuple[str, ...], registry: CapabilityRegistry, *, experience_id: str | None = None) -> InvestigationPlan:
    steps = tuple(
        PlanStep(
            capability_id=tool,
            expected_evidence=registry.get(tool).evidence_types if registry.get(tool) else (),
            reason=f"router:{intent}",
        )
        for tool in tools
    )
    plan = InvestigationPlan(goal=goal, intent=intent, steps=steps, source="validated-router", experience_id=experience_id)
    validate_plan(plan, registry.specs())
    return plan
