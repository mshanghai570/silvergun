"""Event streaming system for Silvergun real-time investigation updates.

This module provides structured events that are emitted during investigation
execution, allowing the UI to display real-time progress as work happens.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable


class EventType(Enum):
    """Types of investigation events that can be emitted."""
    
    # Planner events
    PLANNER_STARTED = "planner_started"
    PLANNER_PROGRESS = "planner_progress"
    PLANNER_STRATEGY = "planner_strategy"
    PLANNER_COMPLETED = "planner_completed"
    
    # Memory events
    MEMORY_SEARCH = "memory_search"
    MEMORY_FOUND = "memory_found"
    MEMORY_RECORDED = "memory_recorded"
    
    # Round events
    ROUND_STARTED = "round_started"
    ROUND_PROGRESS = "round_progress"
    ROUND_COMPLETED = "round_completed"
    ROUND_EVIDENCE = "round_evidence"
    
    # Tool events
    TOOL_STARTED = "tool_started"
    TOOL_PROGRESS = "tool_progress"
    TOOL_RESULT = "tool_result"
    TOOL_COMPLETED = "tool_completed"
    TOOL_FAILED = "tool_failed"
    
    # Analysis events
    ANALYSIS_STARTED = "analysis_started"
    ANALYSIS_PROGRESS = "analysis_progress"
    ANALYSIS_FINDING = "analysis_finding"
    ANALYSIS_WARNING = "analysis_warning"
    
    # Final events
    INVESTIGATION_COMPLETED = "investigation_completed"
    INVESTIGATION_FAILED = "investigation_failed"
    FINAL_SYNTHESIS = "final_synthesis"


@dataclass
class InvestigationEvent:
    """Structured event emitted during investigation execution."""
    
    # Event identification
    event_type: EventType
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S.%f")[:-3])
    sequence: int = 0
    
    # Content
    message: str = ""
    capability: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    
    # Context
    intent: str = ""
    round_number: int = 0
    tool_name: str = ""
    
    # Status
    success: bool = True
    error: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary for serialization."""
        return {
            "type": self.event_type.value,
            "timestamp": self.timestamp,
            "sequence": self.sequence,
            "message": self.message,
            "capability": self.capability,
            "data": self.data,
            "intent": self.intent,
            "round_number": self.round_number,
            "tool_name": self.tool_name,
            "success": self.success,
            "error": self.error,
        }
    
    def to_json(self) -> str:
        """Convert event to JSON string."""
        return json.dumps(self.to_dict(), separators=(",", ":"))
    
    @classmethod
    def from_dict(cls, data: dict[str, Any], sequence: int = 0) -> "InvestigationEvent":
        """Create event from dictionary."""
        return cls(
            event_type=EventType(data.get("type", "info")),
            timestamp=data.get("timestamp", datetime.now().strftime("%H:%M:%S.%f")[:-3]),
            sequence=sequence,
            message=data.get("message", ""),
            capability=data.get("capability", ""),
            data=data.get("data", {}),
            intent=data.get("intent", ""),
            round_number=data.get("round_number", 0),
            tool_name=data.get("tool_name", ""),
            success=data.get("success", True),
            error=data.get("error", ""),
        )


class EventEmitter:
    """Emits structured investigation events to registered listeners."""
    
    def __init__(self) -> None:
        self._listeners: list[Callable[[InvestigationEvent], None]] = []
        self._sequence: int = 0
        self._start_time: float = time.time()
    
    def add_listener(self, listener: Callable[[InvestigationEvent], None]) -> None:
        """Add a listener for investigation events."""
        if listener not in self._listeners:
            self._listeners.append(listener)
    
    def remove_listener(self, listener: Callable[[InvestigationEvent], None]) -> None:
        """Remove a listener."""
        if listener in self._listeners:
            self._listeners.remove(listener)
    
    def clear_listeners(self) -> None:
        """Remove all listeners."""
        self._listeners.clear()
    
    def emit(self, event: InvestigationEvent) -> None:
        """Emit an event to all listeners."""
        self._sequence += 1
        event.sequence = self._sequence
        
        # Calculate elapsed time and add to event data
        elapsed = time.time() - self._start_time
        event.data["elapsed_seconds"] = round(elapsed, 3)
        
        for listener in self._listeners[:]:  # Copy list to avoid modification during iteration
            try:
                listener(event)
            except Exception as e:
                # Don't let listener errors break the event stream
                print(f"[SILVERGUN] Event listener error: {e}")
    
    def reset(self) -> None:
        """Reset the emitter for a new investigation."""
        self._sequence = 0
        self._start_time = time.time()


class EventFormatter:
    """Formats investigation events into human-readable strings."""
    
    @staticmethod
    def format_event(event: InvestigationEvent) -> str:
        """Format an event for display in the activity stream."""
        prefix = EventFormatter._get_prefix(event)
        message = event.message
        
        # Add timestamp if not already in message
        if event.timestamp and not message.startswith(f"[{event.timestamp}]"):
            timestamp_prefix = f"[{event.timestamp}] "
        else:
            timestamp_prefix = ""
        
        # Format based on event type
        if event.event_type == EventType.TOOL_STARTED:
            return f"{timestamp_prefix}[TOOL] {event.tool_name}: {message}"
        
        elif event.event_type == EventType.TOOL_RESULT:
            data_summary = EventFormatter._summarize_data(event.data)
            if data_summary:
                return f"{timestamp_prefix}[RESULT] {event.tool_name}: {message} {data_summary}"
            return f"{timestamp_prefix}[RESULT] {event.tool_name}: {message}"
        
        elif event.event_type == EventType.TOOL_PROGRESS:
            return f"{timestamp_prefix}[PROGRESS] {event.tool_name}: {message}"
        
        elif event.event_type == EventType.TOOL_FAILED:
            return f"{timestamp_prefix}[FAILED] {event.tool_name}: {message}"
        
        elif event.event_type == EventType.ANALYSIS_FINDING:
            return f"{timestamp_prefix}[FINDING] {message}"
        
        elif event.event_type == EventType.ANALYSIS_WARNING:
            return f"{timestamp_prefix}[WARNING] {message}"
        
        elif event.event_type == EventType.PLANNER_STARTED:
            return f"{timestamp_prefix}[PLANNER] Investigating {event.intent}..."
        
        elif event.event_type == EventType.PLANNER_STRATEGY:
            return f"{timestamp_prefix}[STRATEGY] {message}"
        
        elif event.event_type == EventType.PLANNER_COMPLETED:
            return f"{timestamp_prefix}[PLANNER] {message}"
        
        elif event.event_type == EventType.ROUND_STARTED:
            return f"{timestamp_prefix}[ROUND] Starting investigation round {event.round_number}"
        
        elif event.event_type == EventType.ROUND_EVIDENCE:
            detail = message
            if detail.lower().startswith("evidence quality:"):
                detail = detail.split(":", 1)[1].strip()
            return f"{timestamp_prefix}[ROUND] Evidence quality: {detail}"
        
        elif event.event_type == EventType.MEMORY_SEARCH:
            return f"{timestamp_prefix}[MEMORY] {message}"
        
        elif event.event_type == EventType.MEMORY_FOUND:
            return f"{timestamp_prefix}[MEMORY] {message}"
        
        elif event.event_type == EventType.INVESTIGATION_COMPLETED:
            return f"{timestamp_prefix}[MEMORY] Investigation completed successfully"
        
        elif event.event_type == EventType.FINAL_SYNTHESIS:
            return f"{timestamp_prefix}[FINAL] {message}"
        
        else:
            return f"{timestamp_prefix}{prefix} {message}"
    
    @staticmethod
    def _get_prefix(event: InvestigationEvent) -> str:
        """Get the prefix for an event type."""
        prefixes = {
            EventType.PLANNER_STARTED: "[PLANNER]",
            EventType.PLANNER_PROGRESS: "[PLANNER]",
            EventType.PLANNER_STRATEGY: "[STRATEGY]",
            EventType.PLANNER_COMPLETED: "[PLANNER]",
            EventType.MEMORY_SEARCH: "[MEMORY]",
            EventType.MEMORY_FOUND: "[MEMORY]",
            EventType.MEMORY_RECORDED: "[MEMORY]",
            EventType.ROUND_STARTED: "[ROUND]",
            EventType.ROUND_PROGRESS: "[ROUND]",
            EventType.ROUND_COMPLETED: "[ROUND]",
            EventType.ROUND_EVIDENCE: "[ROUND]",
            EventType.TOOL_STARTED: "[TOOL]",
            EventType.TOOL_PROGRESS: "[TOOL]",
            EventType.TOOL_RESULT: "[RESULT]",
            EventType.TOOL_COMPLETED: "[TOOL]",
            EventType.TOOL_FAILED: "[FAILED]",
            EventType.ANALYSIS_STARTED: "[ANALYSIS]",
            EventType.ANALYSIS_PROGRESS: "[ANALYSIS]",
            EventType.ANALYSIS_FINDING: "[FINDING]",
            EventType.ANALYSIS_WARNING: "[WARNING]",
            EventType.INVESTIGATION_COMPLETED: "[MEMORY]",
            EventType.INVESTIGATION_FAILED: "[ERROR]",
            EventType.FINAL_SYNTHESIS: "[FINAL]",
        }
        return prefixes.get(event.event_type, "[INFO]")
    
    @staticmethod
    def _summarize_data(data: dict[str, Any]) -> str:
        """Summarize event data for display."""
        if not data:
            return ""
        
        # Handle common data patterns
        if "count" in data:
            return f"({data['count']} items)"
        if "scanned" in data:
            return f"(scanned {data['scanned']} functions)"
        if "matches" in data:
            matches = data["matches"]
            if isinstance(matches, list):
                return f"({len(matches)} matches)"
        if "results" in data:
            results = data["results"]
            if isinstance(results, list):
                return f"({len(results)} results)"
        
        return ""

    # ---- Plain-English narration for the RESULTS panel ----------------------
    # narrate() renders an InvestigationEvent as a short first-person sentence
    # ("I'm searching the binary's strings for 'password'...") so the results
    # panel explains what Silvergun is doing while the investigation runs.
    # format_event() above keeps the technical line for the ACTIVITY stream.
    # Templates are filled with str.replace() so unusual search text that
    # contains braces can never break formatting.

    @staticmethod
    def narrate(event: "InvestigationEvent") -> str:
        """Return a plain-English, first-person sentence describing the event."""
        tool = (event.tool_name or "").strip()
        message = (event.message or "").strip()
        data = event.data if isinstance(event.data, dict) else {}
        kind = event.event_type

        start_templates = {
            "get_function_context": "I'm pulling a compact snapshot of {target}: code, variables, and call edges…",
            "find_functions": "I'm scanning the function table for names matching '{query}'…",
            "get_xrefs": "I'm mapping who calls {target} and what it calls…",
            "get_type_evidence": "I'm collecting the current signature and variable-type evidence…",
            "review_vulnerabilities": "I'm running a first-pass vulnerability sweep on {target}…",
            "semantic_search": "I'm ranking the binary's functions by how well they match '{query}'…",
            "query_binary": "I'm running the local query '{query}' against the binary…",
            "get_verification": "I'm separating proven facts from interpretation for {target}…",
            "code_map": "I'm building a caller/callee map around {target}…",
            "notebook_context": "I'm opening the local case file for this binary…",
            "notebook_search": "I'm searching the case file for '{query}'…",
            "notebook_progress": "I'm saving the analysis progress…",
            "notebook_record": "I'm recording a finding to the local case file…",
            "search_capabilities": "I'm checking installed plugins for anything matching '{query}'…",
            "invoke_external_command": "I need your approval before I run that plugin command…",
            "fanout_investigate": "I'm fanning out independent read-only reviews across the requested functions…",
            "apply_patch": "I'm preparing a byte patch — you'll see the exact bytes before anything is written…",
            "rename_function": "I'm preparing the rename — nothing changes until you approve it…",
            "apply_function_type": "I'm preparing the type change — you'll approve the declaration first…",
            "annotate_function": "I'm drafting the function comment — you'll approve before it's applied…",
            "external_command": "I'm running the approved plugin command…",
            "bn_analyze": "I'm asking Binary Ninja to deepen its analysis…",
            "bn_decompile": "I'm decompiling {target} with Binary Ninja's decompiler…",
            "bn_find_cross_references": "I'm collecting Binary Ninja cross-references for {target}…",
            "bn_search_strings": "I'm searching the binary's strings for '{query}'…",
            "bn_search_symbols": "I'm searching the symbol table for '{query}'…",
            "bn_find_functions": "I'm scanning the function names for '{query}'…",
            "bn_get_comments": "I'm reading the comments already on this function…",
            "bn_get_function_tags": "I'm collecting the tags on this function…",
            "bn_get_types": "I'm gathering type information from the binary…",
            "bn_get_metadata": "I'm reading the binary's metadata: architecture, platform, entry point…",
            "boolhunter_quick_scan": "I'm running BoolHunter's quick scan across the binary…",
            "boolhunter_analyze": "I'm running BoolHunter's deep analysis on the current function…",
            "boolhunter_batch_scan": "I'm batch-scanning the requested functions with BoolHunter…",
            "boolhunter_find_category": "I'm asking BoolHunter to find functions in that category…",
        }
        labels = {
            "get_function_context": "context snapshot", "find_functions": "function-name search",
            "get_xrefs": "cross-reference scan", "get_type_evidence": "type evidence check",
            "review_vulnerabilities": "vulnerability sweep", "semantic_search": "semantic function search",
            "query_binary": "local binary query", "get_verification": "fact verification",
            "code_map": "call-map builder", "notebook_context": "case-file review",
            "notebook_search": "case-file search", "notebook_progress": "progress save",
            "notebook_record": "finding record", "search_capabilities": "plugin capability search",
            "invoke_external_command": "plugin command", "fanout_investigate": "parallel function review",
            "apply_patch": "byte patch", "rename_function": "function rename",
            "apply_function_type": "type update", "annotate_function": "annotation",
            "external_command": "plugin command", "bn_analyze": "Binary Ninja analysis",
            "bn_decompile": "Binary Ninja decompilation", "bn_find_cross_references": "Binary Ninja cross-reference scan",
            "bn_search_strings": "Binary Ninja string search", "bn_search_symbols": "Binary Ninja symbol search",
            "bn_find_functions": "Binary Ninja function search", "bn_get_comments": "comment review",
            "bn_get_function_tags": "tag review", "bn_get_types": "type inventory",
            "bn_get_metadata": "binary metadata check", "boolhunter_quick_scan": "BoolHunter quick scan",
            "boolhunter_analyze": "BoolHunter deep analysis", "boolhunter_batch_scan": "BoolHunter batch scan",
            "boolhunter_find_category": "BoolHunter category search",
        }

        def label_of(name: str) -> str:
            return labels.get(name, (name or "the requested tool").replace("_", " "))

        if kind == EventType.TOOL_STARTED:
            query = EventFormatter._narration_query(message, data)
            target = EventFormatter._narration_target(data)
            template = start_templates.get(tool)
            if template:
                if query:
                    return template.replace("{query}", query).replace("{target}", target)
                return template.replace(" '{query}'", "").replace("{query}", "").replace("{target}", target)
            return f"I'm running the {label_of(tool)}…"

        if kind == EventType.TOOL_PROGRESS:
            if not message:
                return ""
            softened = message[0].lower() + message[1:] if len(message) > 1 else message.lower()
            return f"Still working — {softened}."

        if kind == EventType.TOOL_RESULT:
            if message.lower().startswith("skipped duplicate call"):
                return "That call would repeat work I already did — reusing the earlier result."
            if isinstance(data.get("command"), str) and data.get("command"):
                return f"Done — the plugin command '{data['command']}' ran without errors."
            analyzed = data.get("functions_analyzed")
            if isinstance(analyzed, int) and not isinstance(analyzed, bool):
                return f"Done — Binary Ninja finished analyzing {analyzed} function(s)."
            callers = data.get("callers_count")
            callees = data.get("callees_count")
            if isinstance(callers, int) and not isinstance(callers, bool) and isinstance(callees, int) and not isinstance(callees, bool):
                return f"Done — {callers} caller(s) and {callees} callee(s) mapped."
            matches = data.get("matches")
            count = data.get("count")
            total = matches if isinstance(matches, int) and not isinstance(matches, bool) else (count if isinstance(count, int) and not isinstance(count, bool) else None)
            if total is not None:
                if tool == "bn_search_strings":
                    return f"Done — found {total} matching string(s), with the functions that reference them."
                if tool == "semantic_search":
                    return f"Done — {total} candidate function(s) ranked by relevance."
                return f"Done — the {label_of(tool)} found {total} item(s)."
            return f"Done — {label_of(tool)} finished."

        if kind == EventType.TOOL_FAILED:
            reason = event.error or message or "unknown error"
            return f"That ran into a problem ({reason}). I'll adapt and keep going."

        if kind == EventType.TOOL_COMPLETED:
            # The result narration already covers completion; keep the transcript lean.
            return ""

        if kind == EventType.ROUND_STARTED:
            total = data.get("total")
            budget = f" of {total}" if isinstance(total, int) and not isinstance(total, bool) and total > 0 else ""
            if event.round_number <= 1:
                return f"I'm on it — starting the first evidence-gathering round{budget}."
            return f"Round {event.round_number}{budget}: digging deeper with the evidence gathered so far."

        if kind == EventType.ROUND_EVIDENCE:
            quality = data.get("quality") if isinstance(data.get("quality"), str) else ""
            if not quality and message.lower().startswith("evidence quality:"):
                quality = message.split(":", 1)[1].strip()
            if quality:
                return f"How it's going: the evidence so far looks {quality}."
            return f"Status: {message}." if message else ""

        if kind == EventType.INVESTIGATION_COMPLETED:
            return "Investigation complete — putting together the final answer."

        if kind == EventType.INVESTIGATION_FAILED:
            reason = event.error or message or "an unexpected error"
            return f"The investigation hit a wall: {reason}."

        if kind == EventType.PLANNER_STARTED:
            return "I'm thinking through the best way to tackle this…"

        if kind in (EventType.PLANNER_PROGRESS, EventType.PLANNER_STRATEGY):
            return f"Plan: {message}." if message else ""

        if kind == EventType.PLANNER_COMPLETED:
            return f"Plan locked in: {message}." if message else "Plan locked in."

        if kind == EventType.MEMORY_SEARCH:
            lowered = message.lower()
            if not message or "not recording" in lowered or "failed to record" in lowered:
                return ""
            if "searching previous" in lowered:
                return "Checking my notes from earlier investigations…"
            return f"From my notes: {message}"

        if kind in (EventType.MEMORY_FOUND, EventType.MEMORY_RECORDED):
            lowered = message.lower()
            if "recorded successful strategy" in lowered:
                return "Saved this approach so I can reuse it next time."
            if "updated experience record" in lowered:
                return "I updated my notes from this case."
            count = data.get("count")
            if isinstance(count, int) and not isinstance(count, bool) and count:
                return f"I've seen {count} similar case(s) before — reusing what worked."
            return f"From my notes: {message}" if message else ""

        if kind == EventType.ANALYSIS_FINDING:
            return f"Notable: {message}" if message else ""

        if kind == EventType.ANALYSIS_WARNING:
            return f"Heads up — {message}" if message else ""

        if kind == EventType.ROUND_COMPLETED:
            return f"Round {event.round_number} finished." if event.round_number else ""

        if message and not message.startswith("["):
            return message
        return ""

    @staticmethod
    def _narration_query(message: str, data: dict) -> str:
        """Extract the user-visible search term from event data or message."""
        query = data.get("query") if isinstance(data, dict) else None
        if isinstance(query, str) and query.strip():
            return query.strip()[:60]
        lowered = message.lower()
        for marker in ("for string: ", "searching for: ", "for pattern: ", "for query: ", "query: ", "matching "):
            index = lowered.find(marker)
            if index >= 0:
                candidate = message[index + len(marker):].strip().strip(".…")
                if candidate:
                    return candidate[:60]
        return ""

    @staticmethod
    def _narration_target(data: dict) -> str:
        """Extract a human-readable target reference from event data."""
        for key in ("function", "function_name", "address", "root"):
            value = data.get(key) if isinstance(data, dict) else None
            if isinstance(value, str) and value.strip():
                return value.strip()
        return "the current function"


# Global event emitter instance for the current investigation
_current_emitter: EventEmitter | None = None


def get_event_emitter() -> EventEmitter:
    """Get or create the global event emitter for the current investigation."""
    global _current_emitter
    if _current_emitter is None:
        _current_emitter = EventEmitter()
    return _current_emitter


def reset_event_emitter() -> None:
    """Reset the global event emitter."""
    global _current_emitter
    if _current_emitter is not None:
        _current_emitter.reset()
    _current_emitter = None


# Convenience functions for emitting common event types
def emit_planner_started(intent: str, message: str = "Investigating request") -> None:
    """Emit a planner started event."""
    emitter = get_event_emitter()
    emitter.emit(InvestigationEvent(
        event_type=EventType.PLANNER_STARTED,
        message=message,
        intent=intent,
    ))


def emit_planner_strategy(message: str, intent: str = "") -> None:
    """Emit a planner strategy event."""
    emitter = get_event_emitter()
    emitter.emit(InvestigationEvent(
        event_type=EventType.PLANNER_STRATEGY,
        message=message,
        intent=intent,
    ))


def emit_tool_started(tool_name: str, message: str = "", capability: str = "") -> None:
    """Emit a tool started event."""
    emitter = get_event_emitter()
    emitter.emit(InvestigationEvent(
        event_type=EventType.TOOL_STARTED,
        message=message or f"Starting {tool_name}",
        tool_name=tool_name,
        capability=capability,
    ))


def emit_tool_progress(tool_name: str, message: str, progress: int = 0, total: int = 100) -> None:
    """Emit a tool progress event."""
    emitter = get_event_emitter()
    emitter.emit(InvestigationEvent(
        event_type=EventType.TOOL_PROGRESS,
        message=message,
        tool_name=tool_name,
        data={"progress": progress, "total": total},
    ))


def emit_tool_result(tool_name: str, message: str, data: dict[str, Any] = None) -> None:
    """Emit a tool result event."""
    emitter = get_event_emitter()
    emitter.emit(InvestigationEvent(
        event_type=EventType.TOOL_RESULT,
        message=message,
        tool_name=tool_name,
        data=data or {},
    ))


def emit_tool_completed(tool_name: str, message: str = "Completed") -> None:
    """Emit a tool completed event."""
    emitter = get_event_emitter()
    emitter.emit(InvestigationEvent(
        event_type=EventType.TOOL_COMPLETED,
        message=message,
        tool_name=tool_name,
    ))


def emit_tool_failed(tool_name: str, message: str, error: str = "") -> None:
    """Emit a tool failed event."""
    emitter = get_event_emitter()
    emitter.emit(InvestigationEvent(
        event_type=EventType.TOOL_FAILED,
        message=message,
        tool_name=tool_name,
        error=error,
        success=False,
    ))


def emit_analysis_finding(message: str, data: dict[str, Any] = None) -> None:
    """Emit an analysis finding event."""
    emitter = get_event_emitter()
    emitter.emit(InvestigationEvent(
        event_type=EventType.ANALYSIS_FINDING,
        message=message,
        data=data or {},
    ))


def emit_analysis_warning(message: str, data: dict[str, Any] = None) -> None:
    """Emit an analysis warning event."""
    emitter = get_event_emitter()
    emitter.emit(InvestigationEvent(
        event_type=EventType.ANALYSIS_WARNING,
        message=message,
        data=data or {},
    ))


def emit_round_started(round_number: int, total: int = 0) -> None:
    """Emit a round started event."""
    emitter = get_event_emitter()
    emitter.emit(InvestigationEvent(
        event_type=EventType.ROUND_STARTED,
        message=f"Starting investigation round {round_number}",
        round_number=round_number,
        data={"total": total},
    ))


def emit_round_evidence(quality: str, message: str = "") -> None:
    """Emit a round evidence quality event."""
    emitter = get_event_emitter()
    emitter.emit(InvestigationEvent(
        event_type=EventType.ROUND_EVIDENCE,
        message=message or f"Evidence quality: {quality}",
        data={"quality": quality},
    ))


def emit_investigation_complete(intent: str, message: str = "Investigation completed") -> None:
    """Emit an investigation completed event."""
    emitter = get_event_emitter()
    emitter.emit(InvestigationEvent(
        event_type=EventType.INVESTIGATION_COMPLETED,
        message=message,
        intent=intent,
    ))


def emit_final_synthesis(message: str, intent: str = "") -> None:
    """Emit a final synthesis event."""
    emitter = get_event_emitter()
    emitter.emit(InvestigationEvent(
        event_type=EventType.FINAL_SYNTHESIS,
        message=message,
        intent=intent,
    ))


def emit_memory_search(message: str) -> None:
    """Emit a memory search event."""
    emitter = get_event_emitter()
    emitter.emit(InvestigationEvent(
        event_type=EventType.MEMORY_SEARCH,
        message=message,
    ))


def emit_memory_found(count: int, message: str = "") -> None:
    """Emit a memory found event."""
    emitter = get_event_emitter()
    emitter.emit(InvestigationEvent(
        event_type=EventType.MEMORY_FOUND,
        message=message or f"Found {count} relevant investigations",
        data={"count": count},
    ))