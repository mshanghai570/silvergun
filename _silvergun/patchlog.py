"""Local, auditable patch journal enabling one-step undo of Silvergun patches.

Every byte mutation Silvergun applies is recorded with its original bytes so the
analyst can reverse the most recent change without leaving Binary Ninja. The
journal is keyed by the normalized binary path, mirrors the notebook's atomic
write strategy, and never stores provider data.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


MAX_ENTRIES = 200


class PatchJournal:
    """Append-only per-binary record of applied patches with reverse capability."""

    def __init__(self, filename: str) -> None:
        self.filename = filename or "untitled-binary"
        raw_path = Path(self.filename).expanduser()
        identity = str(raw_path.resolve(strict=False)) if self.filename != "untitled-binary" else self.filename
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
        self.path = Path.home() / ".binaryninja" / "silvergun" / "patches" / f"{digest}.json"

    def _payload(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (OSError, TypeError, json.JSONDecodeError):
            return {}

    def entries(self) -> list[dict[str, Any]]:
        entries = self._payload().get("entries", [])
        return [entry for entry in entries if isinstance(entry, dict)] if isinstance(entries, list) else []

    def record(self, address: int, original: bytes, replacement: bytes, reason: str = "", tool: str = "apply_patch") -> dict[str, Any]:
        entry = {
            "address": hex(int(address)),
            "original_hex": bytes(original).hex(),
            "replacement_hex": bytes(replacement).hex(),
            "length": len(replacement),
            "reason": reason,
            "tool": tool,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "undone": False,
        }
        self._write(self.entries() + [entry])
        return entry

    def last(self) -> dict[str, Any] | None:
        for entry in reversed(self.entries()):
            if not entry.get("undone"):
                return entry
        return None

    def mark_undone(self, entry: dict[str, Any]) -> None:
        entries = self.entries()
        for item in entries:
            if item.get("undone"):
                continue
            if item.get("address") == entry.get("address") and item.get("recorded_at") == entry.get("recorded_at"):
                item["undone"] = True
                break
        self._write(entries)

    def summary(self) -> dict[str, Any]:
        entries = self.entries()
        pending = [entry for entry in entries if not entry.get("undone")]
        return {"binary": self.filename, "path": str(self.path), "entries": len(entries), "pending": len(pending), "last": pending[-1] if pending else None}

    def compact_context(self, limit: int = 8) -> str:
        pending = [entry for entry in self.entries() if not entry.get("undone")][-max(1, limit):]
        if not pending:
            return "No Silvergun patches are pending undo for this binary."
        return json.dumps(pending, separators=(",", ":"))

    def _write(self, entries: Iterable[dict[str, Any]]) -> None:
        payload = {"schema_version": 1, "binary": self.filename, "entries": list(entries)[-MAX_ENTRIES:]}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary.replace(self.path)
