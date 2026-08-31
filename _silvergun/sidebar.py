"""Silvergun SidebarWidget: a compact retro-industrial analysis console."""

from __future__ import annotations

from pathlib import Path

from binaryninjaui import Sidebar, SidebarWidget, SidebarWidgetType
try:
    from binaryninjaui import SidebarContextSensitivity, SidebarWidgetLocation
except ImportError:
    SidebarContextSensitivity = None
    SidebarWidgetLocation = None
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout

from .commands import start_request
from .external import ExternalCommandIndex
from .notebook import AnalysisNotebook
from .theme import CONSOLE_STYLESHEET, mark
from .tools import TOOL_SCHEMAS


def _view_from_frame(view_frame):
    """Unwrap Binary Ninja's ViewFrame into the underlying BinaryView."""
    if view_frame is None:
        return None
    try:
        interface = view_frame.getCurrentViewInterface()
        view = interface.getData() if interface is not None else None
        if view is not None:
            return view
    except Exception:
        pass
    return view_frame if hasattr(view_frame, "get_function_containing") else None


class SilvergunSidebarWidget(SidebarWidget):
    def __init__(self, name, frame, data):
        super().__init__(name)
        self.setObjectName("silvergunConsole")
        self.setStyleSheet(CONSOLE_STYLESHEET)
        self._frame = frame
        self._offset = None
        self._bv = data if hasattr(data, "get_function_containing") else None
        self._data = data
        self._capability_labels: list[QLabel] = []

        logo = QLabel()
        logo.setPixmap(self._icon_pixmap())
        logo.setFixedSize(58, 58)
        logo.setScaledContents(True)
        title = QLabel("SILVERGUN")
        mark(title, "display")
        subtitle = QLabel("BINARY ANALYSIS WEAPON / REV 01")
        mark(subtitle, "eyebrow")
        header_text = QVBoxLayout()
        header_text.setSpacing(2)
        header_text.addWidget(title)
        header_text.addWidget(subtitle)
        header = QHBoxLayout()
        header.setSpacing(10)
        header.addWidget(logo)
        header.addLayout(header_text, 1)
        header.addStretch()

        self._target_panel = self._panel()
        target_layout = QGridLayout(self._target_panel)
        target_layout.setContentsMargins(10, 8, 10, 8)
        target_layout.setHorizontalSpacing(12)
        target_layout.setVerticalSpacing(3)
        eyebrow = QLabel("TARGET / BINARY CONTEXT")
        mark(eyebrow, "eyebrow")
        target_layout.addWidget(eyebrow, 0, 0, 1, 2)
        self._target_binary = self._value_label("NO BINARY VIEW")
        self._target_arch = self._value_label("—")
        self._target_platform = self._value_label("—")
        self._target_function = self._value_label("NO TARGET ACQUIRED")
        self._target_address = self._value_label("—")
        for row, label, value in ((1, "BINARY", self._target_binary), (2, "ARCH", self._target_arch), (3, "PLATFORM", self._target_platform), (4, "FUNCTION", self._target_function), (5, "ADDRESS", self._target_address)):
            caption = QLabel(label)
            mark(caption, "muted")
            target_layout.addWidget(caption, row, 0)
            target_layout.addWidget(value, row, 1)
        case_caption = QLabel("CASE FILE")
        mark(case_caption, "muted")
        self._case_status = self._value_label("STANDBY")
        target_layout.addWidget(case_caption, 6, 0)
        target_layout.addWidget(self._case_status, 6, 1)

        self._capability_panel = self._panel()
        capability_layout = QVBoxLayout(self._capability_panel)
        capability_layout.setContentsMargins(10, 8, 10, 8)
        capability_layout.setSpacing(2)
        capability_heading = QLabel("SYSTEM CAPABILITIES")
        mark(capability_heading, "eyebrow")
        capability_layout.addWidget(capability_heading)
        self._capability_layout = capability_layout
        self._refresh_capabilities()

        self._status = QLabel("SYSTEM READY / ACQUIRE A TARGET")
        self._status.setWordWrap(True)
        mark(self._status, "status")
        self._activity = QPlainTextEdit()
        self._activity.setReadOnly(True)
        self._activity.setMaximumHeight(76)
        self._activity.setPlaceholderText("Telemetry will appear here.")
        self._activity.setPlainText("[00:00:00] CONSOLE ONLINE\n[00:00:00] AWAITING INVESTIGATION")

        self._prompt = QPlainTextEdit()
        self._prompt.setPlaceholderText("Enter investigation directive…\nExamples: use BoolHunter to find purchase validation; investigate authentication flow")
        self._prompt.setMinimumHeight(78)
        fire = QPushButton("FIRE")
        mark(fire, "fire")
        fire.clicked.connect(self._ask)
        explain = QPushButton("EXPLAIN TARGET")
        explain.clicked.connect(self._explain)
        security = QPushButton("SCAN VULNERABILITIES")
        security.clicked.connect(self._security)
        triage = QPushButton("TRIAGE BINARY")
        triage.clicked.connect(self._triage)
        verify = QPushButton("VERIFY TARGET")
        verify.clicked.connect(self._verify)
        code_map = QPushButton("CODE MAP")
        code_map.clicked.connect(self._map)
        configure = QPushButton("PROVIDER")
        configure.clicked.connect(self._configure)
        command_row = QHBoxLayout()
        command_row.addWidget(fire)
        command_row.addWidget(configure)
        quick = QHBoxLayout()
        quick.addWidget(explain)
        quick.addWidget(security)
        advanced = QHBoxLayout()
        advanced.addWidget(triage)
        advanced.addWidget(verify)
        advanced.addWidget(code_map)

        result_label = QLabel("INVESTIGATION OUTPUT")
        mark(result_label, "eyebrow")
        self._result = QPlainTextEdit()
        self._result.setReadOnly(True)
        self._result.setPlaceholderText("Analysis stream and tool results appear here.")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(7)
        layout.addLayout(header)
        layout.addWidget(self._target_panel)
        layout.addWidget(self._capability_panel)
        layout.addWidget(self._status)
        layout.addWidget(self._activity)
        layout.addWidget(self._prompt)
        layout.addLayout(command_row)
        layout.addLayout(quick)
        layout.addLayout(advanced)
        layout.addWidget(result_label)
        layout.addWidget(self._result, 1)
        self._update_target()

    def _panel(self) -> QFrame:
        panel = QFrame()
        panel.setProperty("role", "panel")
        return panel

    @staticmethod
    def _value_label(text: str) -> QLabel:
        label = QLabel(text)
        mark(label, "value")
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return label

    def _icon_pixmap(self) -> QPixmap:
        icon = QImage(str(Path(__file__).parent / "assets" / "silvergun_icon.png"))
        if icon.isNull():
            icon = QImage(56, 56, QImage.Format.Format_RGB32)
            icon.fill(0)
        return QPixmap.fromImage(icon).scaled(58, 58, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)

    def _refresh_capabilities(self) -> None:
        for label in self._capability_labels:
            self._capability_layout.removeWidget(label)
            label.deleteLater()
        self._capability_labels.clear()
        for tool_name, schema in TOOL_SCHEMAS.items():
            function = schema.get("function", {})
            label = tool_name.replace("_", " ").upper()
            description = str(function.get("description", "Native analysis capability"))
            self._add_capability(label, description, available=True)
        view = self._active_view()
        if view is not None:
            try:
                external = ExternalCommandIndex().refresh(view, self._function())
                for capability in external:
                    self._add_capability(capability.name.upper(), capability.description, available=True)
            except Exception:
                pass
        if not self._capability_labels:
            self._add_capability("NO CAPABILITIES", "Open a BinaryView to populate the instrument array.", available=False)

    def _add_capability(self, name: str, description: str, *, available: bool) -> None:
        label = QLabel(f"●  {name}\n   {description[:78]}")
        label.setToolTip(description)
        mark(label, "capability", available=available)
        self._capability_layout.addWidget(label)
        self._capability_labels.append(label)

    def _engage_capability(self, request: str) -> None:
        """Illuminate the best visible instrument for the active directive."""
        normalized = request.lower()
        matched = False
        for label in self._capability_labels:
            name = label.text().split("\n", 1)[0].replace("●", "").strip().lower()
            active = name != "no capabilities" and any(token in normalized for token in name.split() if len(token) > 3)
            label.setProperty("active", active)
            label.style().unpolish(label)
            label.style().polish(label)
            matched = matched or active
        if not matched and self._capability_labels:
            self._capability_labels[0].setProperty("active", True)
            self._capability_labels[0].style().unpolish(self._capability_labels[0])
            self._capability_labels[0].style().polish(self._capability_labels[0])

    def _update_target(self) -> None:
        view = self._active_view()
        if view is None:
            self._target_binary.setText("NO BINARY VIEW")
            self._target_arch.setText("—")
            self._target_platform.setText("—")
            self._target_function.setText("NO TARGET ACQUIRED")
            self._target_address.setText("—")
            self._case_status.setText("STANDBY")
            return
        filename = str(getattr(getattr(view, "file", None), "filename", "")) or "UNTITLED BINARY"
        architecture = str(getattr(getattr(view, "arch", None), "name", "")) or "UNKNOWN ARCHITECTURE"
        platform = str(getattr(getattr(view, "platform", None), "name", "")) or "UNKNOWN PLATFORM"
        function = self._function()
        self._target_binary.setText(Path(filename).name[:42])
        self._target_arch.setText(architecture[:42])
        self._target_platform.setText(platform[:42])
        self._target_function.setText(str(getattr(function, "name", "NO TARGET ACQUIRED"))[:42])
        self._target_address.setText(hex(function.start) if function is not None else "—")
        case = AnalysisNotebook(filename).summary()
        self._case_status.setText(f"{case['entries']} RECORDS / {case['kinds'].get('finding', 0)} FINDINGS")

    def notifyViewChanged(self, view_frame):
        self._frame = view_frame
        self._bv = _view_from_frame(view_frame)
        self._update_target()
        self._refresh_capabilities()
        self._status.setText("TARGET ACQUIRED / SYSTEM READY" if self._bv is not None else "NO ACTIVE BINARY VIEW")

    def notifyOffsetChanged(self, offset):
        self._offset = offset
        self._update_target()

    def _active_view(self):
        if self._bv is not None:
            return self._bv
        return self._data if hasattr(self._data, "get_function_containing") else None

    def _function(self):
        try:
            view = self._active_view()
            return view.get_function_containing(self._offset) if view is not None and self._offset is not None else None
        except Exception:
            return None

    def _submit(self, request: str) -> None:
        request = request.strip()
        if not request:
            self._status.setText("DIRECTIVE REQUIRED / ENTER A REQUEST")
            return
        view = self._active_view()
        if view is None:
            self._status.setText("TARGET NOT ACQUIRED / OPEN A BINARY VIEW")
            return
        self._status.setText("SCANNING / ANALYZING / CAPABILITY STANDBY")
        self._engage_capability(request)
        self._activity.setPlainText("[NOW] TARGET ACQUIRED\n[NOW] CAPABILITY ENGAGED\n[NOW] ANALYSIS IN PROGRESS…")
        self._result.setPlainText("")
        start_request(view, request, self._function(), self._completed)

    def _ask(self) -> None:
        self._submit(self._prompt.toPlainText())

    def _explain(self) -> None:
        self._submit("Explain the current function with evidence from its compact context and xrefs.")

    def _security(self) -> None:
        self._submit("Find potential vulnerabilities in the current function. Report evidence, reachability questions, impact, and confidence without overstating.")

    def _triage(self) -> None:
        self._submit("Triage this binary using semantic search and local query results. Return a ranked shortlist of high-value functions with evidence and uncertainty.")

    def _verify(self) -> None:
        self._submit("Verify the current function. Separate PROVEN host facts from INFERRED interpretations and cite every evidence locator.")

    def _map(self) -> None:
        self._submit("Build a compact code map for the current function and explain the important caller/callee relationships with evidence.")

    def _configure(self) -> None:
        from .ui import ProviderDialog
        ProviderDialog(self).exec()

    def _completed(self, markdown: str) -> None:
        failed = markdown.startswith("# Provider error") or markdown.startswith("# Silvergun error")
        self._status.setText("ANALYSIS FAILED / REVIEW TELEMETRY" if failed else "ANALYSIS COMPLETE / RESULTS LOCKED")
        self._activity.setPlainText("[NOW] CAPABILITY DISENGAGED\n[NOW] ANALYSIS COMPLETE" if not failed else "[NOW] PROVIDER FAULT\n[NOW] ANALYSIS ABORTED")
        self._result.setPlainText(markdown)


class SilvergunSidebarWidgetType(SidebarWidgetType):
    def __init__(self):
        icon_path = Path(__file__).parent / "assets" / "silvergun_icon.png"
        icon = QImage(str(icon_path))
        if icon.isNull():
            icon = QImage(56, 56, QImage.Format.Format_RGB32)
            icon.fill(0)
        SidebarWidgetType.__init__(self, icon, "Silvergun")

    def createWidget(self, frame, data):
        return SilvergunSidebarWidget("Silvergun", frame, data)

    def defaultLocation(self):
        return SidebarWidgetLocation.RightContent if SidebarWidgetLocation is not None else None

    if SidebarContextSensitivity is not None:
        def contextSensitivity(self):
            return SidebarContextSensitivity.SelfManagedSidebarContext
    else:
        def viewSensitive(self):
            return False


SIDEBAR_WIDGET_TYPE = SilvergunSidebarWidgetType()
Sidebar.addSidebarWidgetType(SIDEBAR_WIDGET_TYPE)
