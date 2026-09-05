"""Local, structured, durable investigation case files for Silvergun."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


MAX_ENTRIES = 200


@dataclass(frozen=True)
class EvidenceRef:
    """A human-auditable pointer from a conclusion to host or tool evidence."""

    kind: str
    locator: str
    detail: str = ""
    address: str = ""
    function: str = ""

    def to_dict(self) -> dict[str, str]:
        return {key: value for key, value in {
            "kind": self.kind, "locator": self.locator, "detail": self.detail,
            "address": self.address, "function": self.function,
        }.items() if value}


@dataclass(frozen=True)
class Finding:
    title: str
    note: str
    address: str = ""
    evidence: tuple[Any, ...] = ()
    confidence: str = "inferred"
    kind: str = "finding"
    status: str = "open"
    related_functions: tuple[str, ...] = ()
    xrefs: tuple[str, ...] = ()
    strings: tuple[str, ...] = ()
    il_refs: tuple[str, ...] = ()
    search_refs: tuple[str, ...] = ()
    plugin_results: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        links = []
        for item in self.evidence:
            if isinstance(item, EvidenceRef):
                links.append(item.to_dict())
            elif isinstance(item, dict):
                links.append({str(key): str(value) for key, value in item.items()})
            elif item:
                links.append({"kind": "unspecified", "locator": str(item)})
        return {
            "title": self.title,
            "note": self.note,
            "address": self.address,
            "confidence": self.confidence if self.confidence in {"proven", "inferred", "hypothesis"} else "inferred",
            "kind": self.kind if self.kind in {"finding", "hypothesis", "question", "function", "tool_result", "progress"} else "finding",
            "status": self.status if self.status in {"open", "resolved", "blocked", "active"} else "open",
            "related_functions": list(self.related_functions),
            "xrefs": list(self.xrefs),
            "strings": list(self.strings),
            "il_refs": list(self.il_refs),
            "search_refs": list(self.search_refs),
            "plugin_results": list(self.plugin_results),
            "evidence_links": links,
        }


class AnalysisNotebook:
    """Atomic JSON storage keyed by the normalized binary path, never by provider."""

    def __init__(self, filename: str) -> None:
        self.filename = filename or "untitled-binary"
        raw_path = Path(self.filename).expanduser()
        # resolve(strict=False) normalizes relative components and resolves
        # existing symlinks without requiring an unsaved/temporary binary to exist.
        identity = str(raw_path.resolve(strict=False)) if self.filename != "untitled-binary" else self.filename
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
        self.path = Path.home() / ".binaryninja" / "silvergun" / "notebooks" / f"{digest}.json"

    def _payload(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (OSError, TypeError, json.JSONDecodeError):
            return {}

    def entries(self) -> list[dict[str, Any]]:
        entries = self._payload().get("entries", [])
        return [entry for entry in entries if isinstance(entry, dict)] if isinstance(entries, list) else []

    def add(self, finding: Finding) -> dict[str, Any]:
        record = finding.to_dict()
        record["recorded_at"] = datetime.now(timezone.utc).isoformat()
        self._write(self.entries() + [record])
        return record

    def set_progress(self, phase: str, completed: int = 0, total: int = 0, note: str = "") -> dict[str, Any]:
        progress = Finding("Analysis progress", note or phase, confidence="inferred", kind="progress", status="active").to_dict()
        progress.update({"phase": phase, "completed": max(0, completed), "total": max(0, total), "recorded_at": datetime.now(timezone.utc).isoformat()})
        entries = [entry for entry in self.entries() if entry.get("kind") != "progress"]
        self._write(entries + [progress])
        return progress

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        terms = [term for term in query.lower().split() if term]
        matches = []
        for entry in reversed(self.entries()):
            haystack = json.dumps(entry, separators=(",", ":")).lower()
            if not terms or all(term in haystack for term in terms):
                matches.append(entry)
                if len(matches) >= max(1, min(limit, 50)):
                    break
        return matches

    def summary(self) -> dict[str, Any]:
        entries = self.entries()
        counts: dict[str, int] = {}
        for entry in entries:
            kind = str(entry.get("kind", "finding"))
            counts[kind] = counts.get(kind, 0) + 1
        progress = next((entry for entry in reversed(entries) if entry.get("kind") == "progress"), None)
        return {"binary": self.filename, "path": str(self.path), "entries": len(entries), "kinds": counts, "progress": progress}

    def compact_context(self, limit: int = 8) -> str:
        entries = [entry for entry in self.entries() if entry.get("kind") != "progress"][-max(1, limit):]
        if not entries:
            return "No notebook findings recorded for this binary."
        return json.dumps(entries, separators=(",", ":"))

    def _write(self, entries: Iterable[dict[str, Any]]) -> None:
        payload = {"schema_version": 2, "binary": self.filename, "entries": list(entries)[-MAX_ENTRIES:]}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary.replace(self.path)
