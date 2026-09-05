"""Adaptive experience memory for Silvergun investigation strategies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import re
import uuid


EXPERIENCE_PATH = Path.home() / ".binaryninja" / "silvergun" / "experiences.json"
MIN_CONFIDENCE = 0.3
MAX_EXPERIENCES = 500


@dataclass
class CapabilitySpec:
    name: str
    evidence_types: tuple[str, ...]
    cost_level: int = 1
    prerequisites: tuple[str, ...] = ()


@dataclass
class StrategyStep:
    tool: str
    args: dict | None = None
    expected_evidence: str = ""


@dataclass
class InvestigationExperience:
    id: str
    request_pattern: str
    intent: str
    strategy: tuple[str, ...]
    tool_sequence: tuple[str, ...]
    evidence_quality: str
    confidence: float
    outcome: str
    similarity_terms: tuple[str, ...]
    created_at: str
    use_count: int = 0
    last_used: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "request_pattern": self.request_pattern,
            "intent": self.intent,
            "strategy": list(self.strategy),
            "tool_sequence": list(self.tool_sequence),
            "evidence_quality": self.evidence_quality,
            "confidence": self.confidence,
            "outcome": self.outcome,
            "similarity_terms": list(self.similarity_terms),
            "created_at": self.created_at,
            "use_count": self.use_count,
            "last_used": self.last_used,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InvestigationExperience":
        return cls(
            id=data["id"],
            request_pattern=data["request_pattern"],
            intent=data["intent"],
            strategy=tuple(data.get("strategy", [])),
            tool_sequence=tuple(data.get("tool_sequence", [])),
            evidence_quality=data.get("evidence_quality", "unknown"),
            confidence=data.get("confidence", 0.5),
            outcome=data.get("outcome", "unknown"),
            similarity_terms=tuple(data.get("similarity_terms", [])),
            created_at=data.get("created_at", ""),
            use_count=data.get("use_count", 0),
            last_used=data.get("last_used"),
        )


class ExperienceMemory:
    _instance: "ExperienceMemory | None" = None

    def __init__(self) -> None:
        self._experiences: list[InvestigationExperience] = []
        self._loaded = False

    @classmethod
    def get(cls) -> "ExperienceMemory":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            if EXPERIENCE_PATH.exists():
                data = json.loads(EXPERIENCE_PATH.read_text(encoding="utf-8"))
                self._experiences = [InvestigationExperience.from_dict(e) for e in data.get("experiences", [])]
        except (OSError, json.JSONDecodeError):
            self._experiences = []

    def save(self) -> None:
        EXPERIENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {"experiences": [e.to_dict() for e in self._experiences[-MAX_EXPERIENCES:]]}
        temporary = EXPERIENCE_PATH.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
        temporary.replace(EXPERIENCE_PATH)

    def record(
        self,
        request: str,
        intent: str,
        tool_sequence: tuple[str, ...],
        evidence_quality: str,
        outcome: str,
    ) -> InvestigationExperience:
        self.load()
        terms = self._extract_terms(request)
        confidence = self._compute_confidence(evidence_quality, outcome)
        experience = InvestigationExperience(
            id=str(uuid.uuid4())[:8],
            request_pattern=request[:200],
            intent=intent,
            strategy=tool_sequence,
            tool_sequence=tool_sequence,
            evidence_quality=evidence_quality,
            confidence=confidence,
            outcome=outcome,
            similarity_terms=tuple(terms),
            created_at=datetime.now(timezone.utc).isoformat(),
            use_count=1,
            last_used=datetime.now(timezone.utc).isoformat(),
        )
        self._experiences.append(experience)
        self.save()
        return experience

    def update(self, experience_id: str, evidence_quality: str, outcome: str) -> None:
        self.load()
        for exp in reversed(self._experiences):
            if exp.id == experience_id:
                exp.evidence_quality = evidence_quality
                exp.confidence = self._compute_confidence(evidence_quality, outcome)
                exp.outcome = outcome
                exp.use_count += 1
                exp.last_used = datetime.now(timezone.utc).isoformat()
                break
        self.save()

    def find_similar(self, request: str, intent: str | None = None, min_confidence: float = MIN_CONFIDENCE) -> list[InvestigationExperience]:
        self.load()
        request_terms = set(self._extract_terms(request))
        scored: list[tuple[float, int, InvestigationExperience]] = []
        for i, exp in enumerate(self._experiences):
            if exp.confidence < min_confidence:
                continue
            if intent and exp.intent != intent:
                continue
            exp_terms = set(exp.similarity_terms)
            overlap = request_terms & exp_terms
            if overlap:
                score = len(overlap) / max(len(request_terms), len(exp_terms))
                scored.append((score * exp.confidence, i, exp))
        scored.sort(key=lambda x: -x[0])
        return [exp for _, _, exp in scored[:10]]

    def get_best_strategy(self, request: str, intent: str | None = None) -> tuple[list[str], str] | None:
        similar = self.find_similar(request, intent)
        if not similar:
            return None
        best = similar[0]
        return list(best.tool_sequence), f"Using strategy that worked for similar investigations (confidence: {best.confidence:.0%})"

    def get_adaptive_hint(self, request: str, failed_tools: list[str]) -> str | None:
        self.load()
        request_terms = set(self._extract_terms(request))
        for exp in reversed(self._experiences):
            if exp.confidence < MIN_CONFIDENCE:
                continue
            exp_terms = set(exp.similarity_terms)
            if request_terms & exp_terms:
                failed_set = set(failed_tools)
                exp_tools = set(exp.tool_sequence)
                untried = list(exp_tools - failed_set)
                if untried and exp.outcome in ("success", "partial"):
                    return f"Previous similar investigation found strong evidence using: {', '.join(untried)}"
        return None

    @staticmethod
    def _extract_terms(request: str) -> list[str]:
        cleaned = re.sub(r"[^\w\s]", " ", request.lower())
        tokens = cleaned.split()
        return [t for t in tokens if len(t) > 2 and t not in {
            "find", "where", "what", "how", "does", "this", "that", "these",
            "those", "function", "functions", "the", "and", "for", "with",
            "from", "into", "about", "using", "use", "try", "not", "can",
            "could", "should", "would", "will", "are", "was", "were", "been",
        }]

    @staticmethod
    def _compute_confidence(evidence_quality: str, outcome: str) -> float:
        quality_map = {"strong": 0.9, "moderate": 0.6, "weak": 0.3, "none": 0.1}
        outcome_map = {"success": 1.0, "partial": 0.7, "failure": 0.2, "unknown": 0.5}
        base = quality_map.get(evidence_quality, 0.5)
        multiplier = outcome_map.get(outcome, 0.5)
        return max(0.1, min(0.95, base * multiplier))


EXPERIENCE_MEMORY = ExperienceMemory.get()
