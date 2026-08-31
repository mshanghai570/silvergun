"""Small, local, durable analysis notebook for Silvergun findings."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Finding:
    title: str
    note: str
    address: str = ""
    evidence: tuple[str, ...] = ()
    confidence: str = "inferred"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AnalysisNotebook:
    """File-backed notes keyed by the binary path, never by remote provider."""

    def __init__(self, filename: str) -> None:
        self.filename = filename or "untitled-binary"
        digest = hashlib.sha256(self.filename.encode("utf-8")).hexdigest()[:20]
        self.path = Path.home() / ".binaryninja" / "silvergun" / "notebooks" / f"{digest}.json"

    def entries(self) -> list[dict[str, Any]]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            entries = payload.get("entries", []) if isinstance(payload, dict) else []
            return [entry for entry in entries if isinstance(entry, dict)]
        except (OSError, TypeError, json.JSONDecodeError):
            return []

    def add(self, finding: Finding) -> dict[str, Any]:
        entries = self.entries()
        record = finding.to_dict()
        record["recorded_at"] = datetime.now(timezone.utc).isoformat()
        entries.append(record)
        payload = {"binary": self.filename, "entries": entries[-200:]}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary.replace(self.path)
        return record

    def compact_context(self, limit: int = 8) -> str:
        entries = self.entries()[-max(1, limit):]
        if not entries:
            return "No notebook findings recorded for this binary."
        return json.dumps(entries, separators=(",", ":"))
