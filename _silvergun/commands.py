"""Binary Ninja command callbacks and background agent task."""

from __future__ import annotations

from typing import Callable

from binaryninja import log_error
from binaryninja.interaction import get_text_line_input, show_markdown_report
from binaryninja.mainthread import execute_on_main_thread
from binaryninja.plugin import BackgroundTaskThread

from .adapters import AdapterRegistry
from .agent import LeanAgent
from .client import OpenAICompatibleClient, ProviderError
from .config import api_key, config
from .external import ExternalCommandIndex
from .tools import NativeTools


def configure_provider(_bv) -> None:
    from .ui import configure_provider_dialog
    configure_provider_dialog()


def run_prompt(bv) -> None:
    request = get_text_line_input("What would you like Silvergun to investigate?", "Silvergun")
    if request:
        _start(bv, None, request)


def explain_current(bv, function) -> None:
    _start(bv, function, "Explain this function. Use the function snapshot and xrefs; identify purpose, inputs, outputs, side effects, and uncertainty.")


def smart_patch_current(bv, function) -> None:
    _start(bv, function, "Review this function for a precise smart patch. Explain the fix first. Call apply_patch only for an exact, necessary byte-level patch; it requires user approval.")


def rename_current(bv, function) -> None:
    _start(bv, function, "Suggest a semantic name for this function from its behavior and callers/callees. Call rename_function only with one clear, justified name; it requires user approval.")


def suggest_types_current(bv, function) -> None:
    _start(bv, function, "Recover the likely function signature and significant variable types. Cite the evidence. Call apply_function_type only with a complete declaration you can justify; it requires user approval.")


def xref_analysis_current(bv, function) -> None:
    _start(bv, function, "Analyze this function's callers and callees. Identify its role, data/control-flow boundaries, and the most useful next xrefs to inspect.")


def annotate_current(bv, function) -> None:
    _start(bv, function, "Draft a concise, evidence-backed function comment and optional tag. Call annotate_function only if the comment will materially help future analysis; it requires user approval.")


def find_vulnerabilities_current(bv, function) -> None:
    _start(bv, function, "Perform a focused vulnerability review. Use heuristic leads and function/xref context. Report evidence, reachability questions, impact, and confidence. Do not overstate findings.")


def triage_binary(bv) -> None:
    _start(bv, None, "Triage this binary using semantic_search and query_binary. Return the highest-value functions to inspect with evidence and uncertainty.")


def verify_current(bv, function) -> None:
    _start(bv, function, "Verify the current function. Separate PROVEN host facts from INFERRED interpretations and cite every evidence locator.")


def map_current(bv, function) -> None:
    _start(bv, function, "Build a compact code map for this function and explain the important caller/callee relationships with evidence.")


def inspect_capabilities(bv) -> None:
    index = ExternalCommandIndex()
    capabilities = index.refresh(bv, None, force=True)
    registry = AdapterRegistry.get()
    registry.discover(bv)
    adapter_info = registry.available_plugins()
    adapter_caps = registry.capabilities()
    rows = "\n".join(f"| `{item.identifier}` | {item.name} | {item.description or '—'} |" for item in capabilities)
    adapter_rows = "\n".join(f"| `{cap.identifier}` | {cap.name} | {cap.description[:60]}... |" for cap in adapter_caps)
    plugin_status = "\n".join(f"- **{name}**: {'available' if info['available'] else 'not available'}" for name, info in [(p['Name'], p) for p in adapter_info])
    report = (
        "# Silvergun Capabilities\n\n"
        f"## Plugin Adapters\n{plugin_status}\n\n"
        f"### Adapter Capabilities\n| ID | Command | Description |\n| --- | --- | --- |\n{adapter_rows}\n\n"
        f"### External Commands\n| ID | Command | Description |\n| --- | --- | --- |\n"
        + (rows or "| — | No compatible plugin commands are valid in this context. | — |")
    )
    execute_on_main_thread(lambda: show_markdown_report(bv, "Silvergun Capabilities", report, report))


def _start(bv, function, request: str) -> None:
    start_request(bv, request, function)


def start_request(bv, request: str, function=None, on_complete: Callable[[str], None] | None = None, on_progress: Callable[..., None] | None = None) -> None:
    """Run an investigation on a background task.

    on_progress receives (technical, narration): the technical line is a
    detailed event record for the activity stream; narration is the plain-
    English sentence intended for the results panel.
    """
    AgentTask(bv, function, request, on_complete, on_progress).start()


class AgentTask(BackgroundTaskThread):
    """Moves network/model work off the UI while preserving explicit write confirmation."""

    def __init__(self, bv, function, request: str, on_complete: Callable[[str], None] | None = None, on_progress: Callable[[str], None] | None = None) -> None:
        super().__init__("Silvergun: preparing compact context", True)
        self._bv = bv
        self._function = function
        self._request = request
        self._on_complete = on_complete
        self._on_progress = on_progress

    def run(self) -> None:
        try:
            settings = config()
            self.progress = "Silvergun: discovering plugin capabilities"
            adapter_registry = AdapterRegistry.get()
            adapter_registry.discover(self._bv, self._function)
            self.progress = "Silvergun: contacting provider"
            client = OpenAICompatibleClient(settings, api_key(settings.normalized_base_url))
            native = NativeTools(self._bv, self._function, ExternalCommandIndex(), settings.max_context_chars)
            native.mark_progress("analysis", 0, settings.max_steps, self._request[:240])
            self.progress = "Silvergun: routing and analyzing"
            result = LeanAgent(client, settings, adapter_registry, on_event=self._event).run(self._request, native)
            native.mark_progress("complete", result.rounds, settings.max_steps, f"Completed {result.intent} investigation.")
            self._report("Silvergun", f"# Silvergun\n\n**Intent:** `{result.intent}`  \n**Tool rounds:** `{result.rounds}`\n\n{result.answer}")
        except ProviderError as error:
            self._report("Silvergun — Provider Error", f"# Provider error\n\n{error}\n\nUse **Silvergun → Configure Provider...** to verify the endpoint, API key, and model.")
        except Exception as error:
            log_error(f"Silvergun task failed: {error}", "Silvergun")
            self._report("Silvergun — Error", f"# Silvergun error\n\n{error}")
        finally:
            self.finish()

    def _report(self, title: str, markdown: str) -> None:
        def deliver() -> None:
            if self._on_complete is not None:
                self._on_complete(markdown)
            show_markdown_report(self._bv, title, markdown, markdown)
        execute_on_main_thread(deliver)

    def _event(self, technical: str, narration: str | None = None) -> None:
        if self._on_progress is not None:
            execute_on_main_thread(lambda: self._on_progress(technical, narration))
