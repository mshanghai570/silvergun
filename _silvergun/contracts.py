"""Canonical contracts shared by Silvergun's planner and execution layers.

The contracts keep provider responses, installed plugins, Binary Ninja adapters,
plans, and evidence distinguishable. Compatibility adapters may still expose
legacy dictionaries, but the orchestration layer can validate them here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
from typing import Any, Mapping


class CapabilityStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    UI_ONLY = "UI_ONLY"
    BROKEN = "BROKEN"


class ExecutionRequirement(str, Enum):
    BACKGROUND = "background"
    BN_MAIN_THREAD = "bn_main_thread"
    USER_APPROVAL = "user_approval"


@dataclass(frozen=True)
class CapabilitySpec:
    capability_id: str
    name: str
    description: str
    category: str = "general"
    input_schema: Mapping[str, Any] = field(default_factory=dict)
    output_schema: Mapping[str, Any] = field(default_factory=dict)
    evidence_types: tuple[str, ...] = ()
    prerequisites: tuple[str, ...] = ()
    cost: str = "low"
    execution_requirements: tuple[ExecutionRequirement, ...] = ()
    adapter: str = "native"
    status: CapabilityStatus = CapabilityStatus.AVAILABLE
    status_detail: str = ""

    @property
    def available(self) -> bool:
        return self.status == CapabilityStatus.AVAILABLE

    def card(self) -> str:
        state = self.status.value
        return f"{self.capability_id}: {self.name} — {self.description[:180]} [{state}]"


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    capability_id: str
    binary_view_id: str
    evidence_type: str
    confidence: str
    summary: str
    provenance: str
    source_kind: str = "host_observation"
    address: str = ""
    function_name: str = ""
    related_entities: tuple[str, ...] = ()
    raw_reference: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CapabilityResult:
    capability_id: str
    success: bool
    summary: str
    evidence: tuple[Evidence, ...] = ()
    data: Mapping[str, Any] = field(default_factory=dict)
    failure: "StructuredFailure | None" = None


@dataclass(frozen=True)
class PlanStep:
    capability_id: str
    inputs: Mapping[str, Any] = field(default_factory=dict)
    expected_evidence: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    reason: str = ""


@dataclass(frozen=True)
class InvestigationPlan:
    goal: str
    intent: str
    steps: tuple[PlanStep, ...]
    source: str = "deterministic"
    experience_id: str | None = None


@dataclass(frozen=True)
class BinaryViewContext:
    binary_view_id: str
    filename: str
    architecture: str
    platform: str
    file_format: str
    analysis_state: str
    function_count: int
    current_function_address: str | None = None
    current_function_name: str | None = None
    current_address: str | None = None


@dataclass(frozen=True)
class StructuredFailure:
    kind: str
    layer: str
    operation: str
    message: str
    recoverable: bool = True
    next_action: str = ""
    details: Mapping[str, Any] = field(default_factory=dict)

    def display(self) -> str:
        recovery = "recoverable" if self.recoverable else "not recoverable"
        suffix = f" Next: {self.next_action}" if self.next_action else ""
        return f"[{self.kind}] {self.layer}.{self.operation}: {self.message} ({recovery}).{suffix}"

    def __str__(self) -> str:
        return self.display()


class ProviderError(StructuredFailure, RuntimeError):
    def __init__(self, message: str, *, operation: str = "chat", recoverable: bool = True, next_action: str = "Check provider configuration or retry.", details: Mapping[str, Any] | None = None):
        StructuredFailure.__init__(self, "ProviderError", "provider", operation, message, recoverable, next_action, details or {})


class CapabilityUnavailable(StructuredFailure, RuntimeError):
    def __init__(self, capability_id: str, message: str, *, next_action: str = "Choose another available capability."):
        StructuredFailure.__init__(self, "CapabilityUnavailable", "capability", capability_id, message, True, next_action, {})


class CapabilityArgumentError(StructuredFailure, ValueError):
    def __init__(self, capability_id: str, message: str):
        StructuredFailure.__init__(self, "CapabilityArgumentError", "capability", capability_id, message, True, "Correct the arguments and retry.", {})


class BinaryViewUnavailable(StructuredFailure, RuntimeError):
    def __init__(self, message: str, *, next_action: str = "Open or select a valid BinaryView."):
        StructuredFailure.__init__(self, "BinaryViewUnavailable", "binaryview", "resolve", message, True, next_action, {})


class BNExecutionError(StructuredFailure, RuntimeError):
    def __init__(self, operation: str, message: str):
        StructuredFailure.__init__(self, "BNExecutionError", "binaryninja", operation, message, True, "Retry through the Binary Ninja execution bridge.", {})


class AdapterError(StructuredFailure, RuntimeError):
    def __init__(self, capability_id: str, message: str):
        StructuredFailure.__init__(self, "AdapterError", "adapter", capability_id, message, True, "Replan with another available adapter.", {})


class EvidenceNormalizationError(StructuredFailure, RuntimeError):
    def __init__(self, capability_id: str, message: str):
        StructuredFailure.__init__(self, "EvidenceNormalizationError", "evidence", capability_id, message, True, "Keep the raw result and retry normalization.", {})


class PlanValidationError(StructuredFailure, ValueError):
    def __init__(self, message: str):
        StructuredFailure.__init__(self, "PlanValidationError", "planner", "validate", message, True, "Replan using the current capability registry.", {})


def view_context_from_payload(payload: str | Mapping[str, Any], *, view_id: str) -> BinaryViewContext:
    data = json.loads(payload) if isinstance(payload, str) else dict(payload)
    if not data.get("binary_view_attached"):
        raise BinaryViewUnavailable("No active BinaryView is attached.")
    current = data.get("current_function") or {}
    return BinaryViewContext(
        binary_view_id=view_id,
        filename=str(data.get("filename", "")),
        architecture=str(data.get("architecture", "")),
        platform=str(data.get("platform", "")),
        file_format=str(data.get("file_format", "")),
        analysis_state=str(data.get("analysis_state", "unknown")),
        function_count=int(data.get("function_count", 0) or 0),
        current_function_address=current.get("address"),
        current_function_name=current.get("name"),
        current_address=current.get("address"),
    )


def normalize_result(capability: CapabilitySpec, binary_view_id: str, raw: Any, *, sequence: int = 0) -> CapabilityResult:
    """Normalize JSON-like adapter output without inventing facts."""
    data: Mapping[str, Any]
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
            data = decoded if isinstance(decoded, dict) else {"text": raw}
        except json.JSONDecodeError:
            data = {"text": raw}
    elif isinstance(raw, Mapping):
        data = raw
    else:
        data = {"value": raw}
    if "error" in data:
        failure = StructuredFailure("AdapterError", "adapter", capability.capability_id, str(data["error"]), True, "Replan with another capability.", data)
        return CapabilityResult(capability.capability_id, False, str(data["error"]), data=data, failure=failure)
    rows = data.get("matches") or data.get("results") or data.get("parallel_reviews") or []
    if not isinstance(rows, list):
        rows = []
    evidence: list[Evidence] = []
    for index, row in enumerate(rows[:128]):
        item = row if isinstance(row, Mapping) else {"value": row}
        address = str(item.get("address", ""))
        source_kind = "model_interpretation" if any(key in item for key in ("interpretation", "inferred", "hypothesis")) else "host_observation"
        evidence.append(Evidence(
            evidence_id=f"{capability.capability_id}:{sequence}:{index}",
            capability_id=capability.capability_id,
            binary_view_id=binary_view_id,
            evidence_type=capability.evidence_types[0] if capability.evidence_types else "tool_result",
            confidence=str(item.get("confidence", item.get("score", "unknown"))),
            summary=str(item.get("summary", item.get("name", item.get("value", "match"))))[:500],
            provenance=capability.name,
            source_kind=source_kind,
            address=address,
            function_name=str(item.get("name", item.get("function", ""))),
            related_entities=tuple(str(v) for v in item.get("related_functions", []) if v),
            raw_reference=dict(item),
        ))
    summary = str(data.get("summary", data.get("message", f"{len(evidence)} evidence items returned")))
    return CapabilityResult(capability.capability_id, True, summary, tuple(evidence), data)


def validate_plan(plan: InvestigationPlan, registry: Mapping[str, CapabilitySpec]) -> None:
    seen: set[str] = set()
    for step in plan.steps:
        capability = registry.get(step.capability_id)
        if capability is None:
            raise PlanValidationError(f"Unknown capability: {step.capability_id}")
        if not capability.available:
            raise PlanValidationError(f"Capability {step.capability_id} is {capability.status.value}: {capability.status_detail}")
        missing = [dependency for dependency in step.dependencies if dependency not in seen]
        if missing:
            raise PlanValidationError(f"Step {step.capability_id} has unmet dependencies: {', '.join(missing)}")
        seen.add(step.capability_id)


__all__ = [
    "CapabilitySpec", "CapabilityStatus", "ExecutionRequirement", "Evidence", "CapabilityResult",
    "PlanStep", "InvestigationPlan", "BinaryViewContext", "StructuredFailure", "ProviderError",
    "CapabilityUnavailable", "CapabilityArgumentError", "BinaryViewUnavailable", "BNExecutionError",
    "AdapterError", "EvidenceNormalizationError", "PlanValidationError", "normalize_result",
    "validate_plan", "view_context_from_payload",
]

# Legacy imports in older modules use this name; the canonical provider error
# remains available without forcing a broad migration in one commit.
