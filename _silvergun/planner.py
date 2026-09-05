"""Adaptive investigation planner for Silvergun.

The planner composes investigation strategies from capabilities,
adapts based on experience, and provides observable reasoning.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .tools import NativeTools

from .experience import ExperienceMemory
from .capabilities import CAPABILITY_CATALOG, get_capabilities_for_intent
from .events import (
    emit_planner_started, emit_planner_strategy, emit_memory_search, 
    emit_memory_found, emit_round_started, emit_round_evidence
)


@dataclass
class StrategyStep:
    tool: str
    reason: str
    expected_evidence: str


@dataclass
class InvestigationPlan:
    intent: str
    steps: list[StrategyStep]
    reasoning: str
    experience_id: str | None = None


class AdaptivePlanner:
    MIN_QUALITY_FOR_RECORDING = "moderate"
    MIN_CONFIDENCE_FOR_REUSE = 0.3

    def __init__(self, on_event: callable | None = None) -> None:
        self._experience = ExperienceMemory.get()
        self._on_event = on_event
        self._failed_tools: list[str] = []
        self._attempted_strategies: list[str] = []

    def _emit(self, message: str) -> None:
        if self._on_event:
            self._on_event(message)

    def memory_emit(self, message: str) -> None:
        self._emit(f"[MEMORY] {message}")

    def plan(self, request: str, base_intent: str, available_tools: tuple[str, ...], native: "NativeTools | None" = None) -> InvestigationPlan:
        self._failed_tools.clear()
        self._attempted_strategies.clear()

        # Emit initial planner events
        emit_planner_started(base_intent, f"Understanding request: {request[:50]}...")
        emit_memory_search("Searching previous experience...")

        similar = self._experience.find_similar(request, base_intent, min_confidence=self.MIN_CONFIDENCE_FOR_REUSE)

        if similar:
            emit_memory_found(len(similar), f"Found {len(similar)} relevant investigations")
            best = similar[0]
            emit_planner_strategy(f"Similar: '{best.request_pattern[:60]}...' (confidence: {best.confidence:.0%})", base_intent)
            emit_planner_strategy(f"Previous approach: {' → '.join(best.tool_sequence[:4])}", base_intent)

            if best.outcome == "success" and best.confidence >= 0.7:
                emit_planner_strategy("Using previously successful approach", base_intent)
                steps = [StrategyStep(tool=t, reason="from_experience", expected_evidence="") for t in best.tool_sequence[:6]]
                return InvestigationPlan(
                    intent=best.intent,
                    steps=steps,
                    reasoning=f"Using a strategy that worked for similar investigations (confidence: {best.confidence:.0%})",
                    experience_id=best.id,
                )
            elif best.outcome in ("success", "partial"):
                emit_planner_strategy("Adapting previous approach based on past results", base_intent)
                return self._build_adaptive_plan(request, base_intent, best, available_tools)

        emit_memory_search("No relevant prior experience - building plan from capabilities")
        emit_planner_strategy("Building plan from capability catalog", base_intent)
        return self._build_default_plan(request, base_intent, available_tools)

    def _build_adaptive_plan(
        self,
        request: str,
        intent: str,
        experience,
        available_tools: tuple[str, ...],
    ) -> InvestigationPlan:
        existing = set(experience.tool_sequence)
        categories = self._get_categories(request)
        new_tools = self._suggest_for_categories(categories, available_tools)
        untried = [t for t in new_tools if t not in existing]
        steps = [StrategyStep(tool=t, reason="from_experience", expected_evidence="") for t in experience.tool_sequence[:4]]
        for tool in untried[:3]:
            cat = CAPABILITY_CATALOG.get(tool)
            reason = f"Category match for: {', '.join(categories)}" if cat else "adaptive exploration"
            steps.append(StrategyStep(tool=tool, reason=reason, expected_evidence=""))
        return InvestigationPlan(
            intent=intent,
            steps=steps[:6],
            reasoning=f"Adapting strategy from partial success: {' → '.join(experience.tool_sequence)}",
            experience_id=experience.id,
        )

    def _build_default_plan(self, request: str, intent: str, available_tools: tuple[str, ...]) -> InvestigationPlan:
        categories = self._get_categories(request)
        emit_planner_strategy(f"Detected categories: {', '.join(categories) if categories else 'general'}", intent)
        base_tools = get_capabilities_for_intent(intent)
        steps = []
        for tool in base_tools:
            if tool in available_tools or tool.startswith("boolhunter"):
                cat = CAPABILITY_CATALOG.get(tool)
                desc = cat.description if cat else ""
                steps.append(StrategyStep(tool=tool, reason=f"intent:{intent}", expected_evidence=desc))
        if categories:
            category_tools = self._suggest_for_categories(categories, available_tools)
            for tool in category_tools[:2]:
                if not any(s.tool == tool for s in steps):
                    steps.append(StrategyStep(tool=tool, reason=f"category:{','.join(categories)}", expected_evidence=""))
        emit_planner_strategy(f"Built plan with {len(steps)} steps", intent)
        return InvestigationPlan(intent=intent, steps=steps[:6], reasoning=f"Built plan based on {intent} intent and detected categories")

    def _get_categories(self, request: str) -> list[str]:
        request_lower = request.lower()
        from .capabilities import CATEGORY_PATTERNS
        categories = []
        for category, patterns in CATEGORY_PATTERNS.items():
            if any(p in request_lower for p in patterns):
                categories.append(category)
        return categories

    def _suggest_for_categories(self, categories: list[str], available_tools: tuple[str, ...]) -> list[str]:
        suggestions = []
        category_to_tools = {
            "boolean": ["boolhunter_quick_scan", "boolhunter_analyze", "boolhunter_batch_scan"],
            "authentication": ["get_xrefs", "semantic_search", "query_binary", "get_function_context"],
            "purchase": ["boolhunter_find_category", "semantic_search", "get_xrefs"],
            "network": ["semantic_search", "query_binary", "get_xrefs", "code_map"],
            "security": ["review_vulnerabilities", "get_xrefs", "get_function_context"],
            "data": ["semantic_search", "query_binary", "get_function_context"],
        }
        for cat in categories:
            if cat in category_to_tools:
                suggestions.extend(category_to_tools[cat])
        return list(dict.fromkeys(suggestions))

    def record_result(
        self,
        request: str,
        intent: str,
        tool_sequence: tuple[str, ...],
        experience_id: str | None,
        evidence_quality: str,
        outcome: str,
    ) -> None:
        quality_rank = {"strong": 3, "moderate": 2, "weak": 1, "none": 0}

        if experience_id:
            self._experience.update(experience_id, evidence_quality, outcome)
            q_rank = quality_rank.get(evidence_quality, 0)
            if q_rank >= quality_rank[self.MIN_QUALITY_FOR_RECORDING]:
                emit_memory_found(0, f"Updated experience record: {outcome} ({evidence_quality})")
            else:
                emit_memory_search(f"Weak result - not recording: {evidence_quality} quality")
            emit_round_evidence(evidence_quality)
            return

        if not tool_sequence:
            emit_memory_search("No tools executed - not recording empty investigation")
            return

        q_rank = quality_rank.get(evidence_quality, 0)
        if q_rank < quality_rank[self.MIN_QUALITY_FOR_RECORDING]:
            emit_memory_search(f"Weak result - not recording: {evidence_quality} quality ({outcome})")
            return

        if outcome == "failure" and evidence_quality == "weak":
            emit_memory_search("Failed investigation - not recording")
            return

        try:
            new_exp = self._experience.record(
                request=request,
                intent=intent,
                tool_sequence=tool_sequence,
                evidence_quality=evidence_quality,
                outcome=outcome,
            )
            emit_memory_found(0, f"Recorded successful strategy: {outcome} ({evidence_quality})")
        except Exception as e:
            emit_memory_search(f"Failed to record experience: {e}")

    def record_failed_tool(self, tool: str) -> None:
        if tool not in self._failed_tools:
            self._failed_tools.append(tool)
            hint = self._experience.get_adaptive_hint("", self._failed_tools)
            if hint:
                self._emit(f"[STRATEGY] {hint}")
