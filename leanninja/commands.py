"""Binary Ninja command callbacks and background agent task."""

from __future__ import annotations

from binaryninja import log_error
from binaryninja.interaction import get_text_line_input, show_markdown_report
from binaryninja.mainthread import execute_on_main_thread
from binaryninja.plugin import BackgroundTaskThread

from .agent import LeanAgent
from .client import OpenAICompatibleClient, ProviderError
from .config import api_key, config
from .external import ExternalCommandIndex
from .tools import NativeTools


def configure_provider(_bv) -> None:
    from .ui import configure_provider_dialog
    configure_provider_dialog()


def run_prompt(bv) -> None:
    request = get_text_line_input("What would you like Lean Ninja to investigate?", "Lean Ninja")
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


def inspect_capabilities(bv) -> None:
    index = ExternalCommandIndex()
    capabilities = index.refresh(bv, None, force=True)
    rows = "\n".join(f"| `{item.identifier}` | {item.name} | {item.description or '—'} |" for item in capabilities)
    report = "# Lean Ninja Capabilities\n\n| ID | Command | Description |\n| --- | --- | --- |\n" + (rows or "| — | No compatible plugin commands are valid in this context. | — |")
    execute_on_main_thread(lambda: show_markdown_report(bv, "Lean Ninja Capabilities", report, report))


def _start(bv, function, request: str) -> None:
    AgentTask(bv, function, request).start()


class AgentTask(BackgroundTaskThread):
    """Moves network/model work off the UI while preserving explicit write confirmation."""

    def __init__(self, bv, function, request: str) -> None:
        super().__init__("Lean Ninja: preparing compact context", True)
        self._bv = bv
        self._function = function
        self._request = request

    def run(self) -> None:
        try:
            settings = config()
            self.progress = "Lean Ninja: contacting provider"
            client = OpenAICompatibleClient(settings, api_key(settings.normalized_base_url))
            native = NativeTools(self._bv, self._function, ExternalCommandIndex(), settings.max_context_chars)
            self.progress = "Lean Ninja: routing and analyzing"
            result = LeanAgent(client, settings).run(self._request, native)
            self._report("Lean Ninja", f"# Lean Ninja\n\n**Intent:** `{result.intent}`  \n**Tool rounds:** `{result.rounds}`\n\n{result.answer}")
        except ProviderError as error:
            self._report("Lean Ninja — Provider Error", f"# Provider error\n\n{error}\n\nUse **Lean Ninja → Configure Provider...** to verify the endpoint, API key, and model.")
        except Exception as error:
            log_error(f"Lean Ninja task failed: {error}", "Lean Ninja")
            self._report("Lean Ninja — Error", f"# Lean Ninja error\n\n{error}")
        finally:
            self.finish()

    def _report(self, title: str, markdown: str) -> None:
        execute_on_main_thread(lambda: show_markdown_report(self._bv, title, markdown, markdown))
