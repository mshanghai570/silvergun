"""Silvergun SidebarWidget: a compact retro-industrial analysis console."""

from __future__ import annotations

from pathlib import Path

from binaryninjaui import Sidebar, SidebarWidget, SidebarWidgetType
try:
    from binaryninjaui import SidebarContextSensitivity, SidebarWidgetLocation
except ImportError:
    SidebarContextSensitivity = None
    SidebarWidgetLocation = None
<<<<<<< HEAD
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QImage, QPixmap, QAction
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QMenuBar, QPlainTextEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget
=======
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QScrollArea, QVBoxLayout
>>>>>>> 1630c0d351f49b041623dfd9440b74c011846a37

from .commands import start_request
from .external import ExternalCommandIndex
from .notebook import AnalysisNotebook
from .theme import CONSOLE_STYLESHEET, mark
from .tools import TOOL_SCHEMAS
<<<<<<< HEAD
from .events import get_event_emitter, reset_event_emitter, EventFormatter, InvestigationEvent
=======
>>>>>>> 1630c0d351f49b041623dfd9440b74c011846a37


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


<<<<<<< HEAD
class SilverPrompt(QPlainTextEdit):
    """Prompt box: Enter or Ctrl+Return fires the request; Shift+Enter adds a newline."""

    def __init__(self, submit, parent=None) -> None:
        super().__init__(parent)
        self._submit_request = submit

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self._submit_request()
            return
        super().keyPressEvent(event)


=======
>>>>>>> 1630c0d351f49b041623dfd9440b74c011846a37
class SilvergunSidebarWidget(SidebarWidget):
    def __init__(self, name, frame, data):
        super().__init__(name)
        self.setObjectName("silvergunConsole")
        self.setStyleSheet(CONSOLE_STYLESHEET)
        self._frame = frame
        self._offset = None
<<<<<<< HEAD
        self._bv = _view_from_frame(data)
        self._data = data
        self._capability_labels: list[QLabel] = []
        self._last_narration = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(8, 8, 8, 8)
        content_layout.setSpacing(7)

        menu_bar = QMenuBar()
        file_menu = menu_bar.addMenu("File")
        file_menu.addAction("Clear Console", self._clear_console)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)
        actions_menu = menu_bar.addMenu("Actions")
        actions_menu.addAction("Explain Function", self._explain)
        actions_menu.addAction("Find Vulnerabilities", self._security)
        actions_menu.addAction("Triage Binary", self._triage)
        actions_menu.addAction("Verify Function", self._verify)
        actions_menu.addAction("Code Map", self._map)
        actions_menu.addAction("Continue Case", self._continue_case)
        actions_menu.addAction("Review Evidence", self._review_evidence)
        tools_menu = menu_bar.addMenu("Tools")
        tools_menu.addAction("BoolHunter: Quick Scan", lambda: self._submit("Use BoolHunter to quick scan for boolean functions"))
        tools_menu.addAction("BoolHunter: Find Category", lambda: self._submit("Use BoolHunter to find authentication functions"))
        tools_menu.addAction("BoolHunter: Analyze", lambda: self._submit("Analyze the current function with BoolHunter"))
        settings_menu = menu_bar.addMenu("Settings")
        settings_menu.addAction("Configure Provider...", self._configure)
        settings_menu.addAction("Inspect Capabilities", self._inspect_capabilities)
        content_layout.addWidget(menu_bar)

        logo = QLabel()
        logo.setPixmap(self._icon_pixmap())
        logo.setFixedSize(48, 48)
        logo.setScaledContents(True)
        title = QLabel("SILVERGUN")
        mark(title, "display")
        subtitle = QLabel("BINARY ANALYSIS WEAPON")
=======
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
>>>>>>> 1630c0d351f49b041623dfd9440b74c011846a37
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
<<<<<<< HEAD
        content_layout.addLayout(header)
=======
>>>>>>> 1630c0d351f49b041623dfd9440b74c011846a37

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
<<<<<<< HEAD
        content_layout.addWidget(self._target_panel)

        self._status = QLabel("SYSTEM READY / ACQUIRE A TARGET")
        self._status.setWordWrap(True)
        mark(self._status, "status")
        content_layout.addWidget(self._status)

        input_label = QLabel("ASK SILVER")
        mark(input_label, "eyebrow")
        content_layout.addWidget(input_label)

        self._prompt = SilverPrompt(self._ask)
        self._prompt.setPlaceholderText("Ask Silver anything... (Enter to send)\n\nExamples:\n  • Find the purchase flow\n  • Explain the login function\n  • Search for binary vulnerabilities and patch them\n  • Use BoolHunter to find authentication\n  • What does this function do?")
        self._prompt.setMinimumHeight(80)
        self._prompt.setMaximumHeight(120)
        content_layout.addWidget(self._prompt)

        button_row = QHBoxLayout()
        fire = QPushButton("FIRE")
        mark(fire, "fire")
        fire.clicked.connect(self._ask)
        configure = QPushButton("SETTINGS")
        configure.clicked.connect(self._configure)
        button_row.addWidget(fire)
        button_row.addWidget(configure)
        content_layout.addLayout(button_row)

        quick_label = QLabel("QUICK ACTIONS")
        mark(quick_label, "eyebrow")
        content_layout.addWidget(quick_label)

        quick_row = QHBoxLayout()
        explain = QPushButton("EXPLAIN")
        explain.setMaximumWidth(80)
        explain.clicked.connect(self._explain)
        triage = QPushButton("TRIAGE")
        triage.setMaximumWidth(80)
        triage.clicked.connect(self._triage)
        vuln = QPushButton("VULNS")
        vuln.setMaximumWidth(80)
        vuln.clicked.connect(self._security)
        verify = QPushButton("VERIFY")
        verify.setMaximumWidth(80)
        verify.clicked.connect(self._verify)
        quick_row.addWidget(explain)
        quick_row.addWidget(triage)
        quick_row.addWidget(vuln)
        quick_row.addWidget(verify)
        content_layout.addLayout(quick_row)

        self._activity = QPlainTextEdit()
        self._activity.setReadOnly(True)
        self._activity.setMaximumHeight(150)  # Increased height for better visibility
        self._activity.setPlaceholderText("Tool activity will appear here.")
        self._activity.setPlainText("[00:00:00] CONSOLE ONLINE\n[00:00:00] AWAITING INVESTIGATION")
        activity_label = QLabel("ACTIVITY STREAM")
        mark(activity_label, "eyebrow")
        content_layout.addWidget(activity_label)
        content_layout.addWidget(self._activity)

        self._result = QPlainTextEdit()
        self._result.setReadOnly(True)
        self._result.setMinimumHeight(200)
        self._result.setPlaceholderText("Analysis results will appear here...")
        result_label = QLabel("RESULTS")
        mark(result_label, "eyebrow")
        content_layout.addWidget(result_label)
        content_layout.addWidget(self._result)

        result_actions = QHBoxLayout()
        continue_case = QPushButton("CONTINUE")
        continue_case.clicked.connect(self._continue_case)
        review = QPushButton("REVIEW")
        review.clicked.connect(self._review_evidence)
        clear = QPushButton("CLEAR")
        clear.clicked.connect(self._clear_console)
        result_actions.addWidget(continue_case)
        result_actions.addWidget(review)
        result_actions.addWidget(clear)
        content_layout.addLayout(result_actions)
=======
>>>>>>> 1630c0d351f49b041623dfd9440b74c011846a37

        self._capability_panel = self._panel()
        capability_layout = QVBoxLayout(self._capability_panel)
        capability_layout.setContentsMargins(10, 8, 10, 8)
        capability_layout.setSpacing(2)
<<<<<<< HEAD
        capability_heading = QLabel("CAPABILITY INVENTORY")
=======
        capability_heading = QLabel("SYSTEM CAPABILITIES")
>>>>>>> 1630c0d351f49b041623dfd9440b74c011846a37
        mark(capability_heading, "eyebrow")
        capability_layout.addWidget(capability_heading)
        self._capability_layout = capability_layout
        self._refresh_capabilities()

<<<<<<< HEAD
        capability_scroll = QScrollArea()
        capability_scroll.setWidgetResizable(True)
        capability_scroll.setFrameShape(QFrame.Shape.NoFrame)
        capability_scroll.setMaximumHeight(160)
        capability_scroll.setWidget(self._capability_panel)
        content_layout.addWidget(capability_scroll)

        content_layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)
=======
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
        self._prompt.setMinimumHeight(108)
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
        self._result.setMinimumHeight(240)
        self._result.setPlaceholderText("Analysis stream and tool results appear here.")

        result_actions = QHBoxLayout()
        continue_case = QPushButton("CONTINUE CASE")
        continue_case.clicked.connect(self._continue_case)
        review_evidence = QPushButton("REVIEW EVIDENCE")
        review_evidence.clicked.connect(self._review_evidence)
        clear_console = QPushButton("CLEAR CONSOLE")
        clear_console.clicked.connect(self._clear_console)
        result_actions.addWidget(continue_case)
        result_actions.addWidget(review_evidence)
        result_actions.addWidget(clear_console)

        capability_scroll = QScrollArea()
        capability_scroll.setWidgetResizable(True)
        capability_scroll.setFrameShape(QFrame.Shape.NoFrame)
        capability_scroll.setMaximumHeight(190)
        capability_scroll.setWidget(self._capability_panel)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(7)
        layout.addLayout(header)
        layout.addWidget(self._target_panel)
        layout.addWidget(self._status)
        console_label = QLabel("AGENT CONSOLE / NATURAL-LANGUAGE CONTROL")
        mark(console_label, "eyebrow")
        layout.addWidget(console_label)
        layout.addWidget(self._activity)
        layout.addWidget(self._prompt)
        layout.addLayout(command_row)
        layout.addLayout(quick)
        layout.addLayout(advanced)
        layout.addWidget(result_label)
        layout.addWidget(self._result, 1)
        layout.addLayout(result_actions)
        inventory_label = QLabel("CAPABILITY INVENTORY / STATUS")
        mark(inventory_label, "eyebrow")
        layout.addWidget(inventory_label)
        layout.addWidget(capability_scroll)
>>>>>>> 1630c0d351f49b041623dfd9440b74c011846a37
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
<<<<<<< HEAD
        return QPixmap.fromImage(icon).scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
=======
        return QPixmap.fromImage(icon).scaled(58, 58, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
>>>>>>> 1630c0d351f49b041623dfd9440b74c011846a37

    def _refresh_capabilities(self) -> None:
        for label in self._capability_labels:
            self._capability_layout.removeWidget(label)
            label.deleteLater()
        self._capability_labels.clear()
<<<<<<< HEAD
        
        view = self._active_view()
        
        # Add native Silvergun tools
        if TOOL_SCHEMAS:
            self._add_capability_section("SILVERGUN CORE", TOOL_SCHEMAS)
        
        # Add adapter tools with categorization
        from .adapters import AdapterRegistry
        adapter_registry = AdapterRegistry.get()
        if view is not None:
            adapter_registry.discover(view)
        
        for adapter_name, adapter in adapter_registry.all_adapters().items():
            adapter_display = adapter_name.upper()
            if adapter_name == "binaryninja":
                adapter_display = "BINARY NINJA"
            elif adapter_name == "boolhunter":
                adapter_display = "BOOLHUNTER"
            
            tools = adapter.get_tools()
            if tools:
                self._add_capability_section(f"{adapter_display} PLUGIN", tools)
        
        # Add external plugin commands
        if view is not None:
            try:
                external = ExternalCommandIndex().refresh(view, self._function())
                if external:
                    # Group external capabilities
                    external_dict = {cap.identifier: {
                        "function": {
                            "name": cap.name,
                            "description": cap.description
                        }
                    } for cap in external}
                    self._add_capability_section("INSTALLED PLUGINS", external_dict)
            except Exception:
                pass
        if not self._capability_labels:
            self._add_capability("NO CAPABILITIES", "Open a BinaryView to populate.", available=False)
    
    def _add_capability_section(self, section_name: str, tools_dict: dict[str, dict]) -> None:
        """Add a section of capabilities with a header."""
        if not tools_dict:
            return
        
        # Add section header
        header = QLabel(f"━ {section_name} ━")
        mark(header, "section_header")
        self._capability_layout.addWidget(header)
        self._capability_labels.append(header)
        
        # Add tools in this section
        for tool_name, schema in tools_dict.items():
            function = schema.get("function", {})
            label = tool_name.replace("_", " ").upper()
            description = str(function.get("description", f"{section_name} capability"))
            self._add_capability(label, description, available=True)
=======
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
>>>>>>> 1630c0d351f49b041623dfd9440b74c011846a37

    def _add_capability(self, name: str, description: str, *, available: bool) -> None:
        label = QLabel(f"●  {name}\n   {description[:78]}")
        label.setToolTip(description)
        mark(label, "capability", available=available)
        self._capability_layout.addWidget(label)
        self._capability_labels.append(label)

<<<<<<< HEAD
    def _highlight_tool(self, tool_name: str) -> None:
        """Highlight a tool in the capabilities list when it's being used."""
        if not tool_name or len(tool_name) < 2:
            return
        
        # Normalize the tool name for matching
        normalized = tool_name.lower().replace("_", " ")
        
        # Also handle tool names with prefixes
        tool_name_lower = tool_name.lower()
        
        # Check if this is a prefixed tool (bn_, boolhunter_, etc.)
        base_tool_name = None
        if tool_name_lower.startswith("bn_"):
            base_tool_name = tool_name[3:]  # Remove "bn_" prefix
        elif tool_name_lower.startswith("boolhunter_"):
            base_tool_name = tool_name[11:]  # Remove "boolhunter_" prefix
        elif tool_name_lower.startswith("external_"):
            base_tool_name = tool_name[9:]  # Remove "external_" prefix
        
        for label in self._capability_labels:
            label_text = label.text().split("\n", 1)[0].replace("●", "").strip().lower()
            
            # Check for direct match
            if normalized in label_text:
                self._set_label_active(label)
                continue
            
            # Check for match with base tool name
            if base_tool_name:
                base_normalized = base_tool_name.replace("_", " ")
                if base_normalized in label_text:
                    self._set_label_active(label)
                    continue
            
            # Check for token matches (more lenient)
            tokens = [token for token in normalized.split() if len(token) > 3]
            if tokens and any(token in label_text for token in tokens):
                self._set_label_active(label)
                continue
            
            # Check for prefixed matches in label
            if any(prefix in label_text for prefix in ["[bn]", "[bh]", "[boolhunter]"]):
                if base_tool_name and base_normalized in label_text:
                    self._set_label_active(label)
    
    def _set_label_active(self, label) -> None:
        """Set a capability label to active state and refresh its style."""
        label.setProperty("active", True)
        label.style().unpolish(label)
        label.style().polish(label)
=======
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
>>>>>>> 1630c0d351f49b041623dfd9440b74c011846a37

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
<<<<<<< HEAD
        prefixes = ("silver, ", "silver: ", "silver ", "hey silver, ", "hey silver: ", "hey silver ")
        lower_request = request.lower()
        for prefix in prefixes:
            if lower_request.startswith(prefix):
                request = request[len(prefix):].strip()
                break
=======
>>>>>>> 1630c0d351f49b041623dfd9440b74c011846a37
        if not request:
            self._status.setText("DIRECTIVE REQUIRED / ENTER A REQUEST")
            return
        view = self._active_view()
        if view is None:
            self._status.setText("TARGET NOT ACQUIRED / OPEN A BINARY VIEW")
            return
<<<<<<< HEAD
        self._prompt.clear()
        self._status.setText("SCANNING / ANALYZING / CAPABILITY STANDBY")
        self._activity.setPlainText("[00:00:00] CONSOLE ONLINE\n[00:00:00] AWAITING INVESTIGATION")
        self._result.setPlainText(f"REQUEST / {request}\n")
        self._last_narration = ""
=======
        self._status.setText("SCANNING / ANALYZING / CAPABILITY STANDBY")
        self._engage_capability(request)
        self._activity.setPlainText("[NOW] TARGET ACQUIRED\n[NOW] CAPABILITY ROUTING\n[NOW] ANALYSIS IN PROGRESS…")
        self._result.setPlainText("[STREAM] Silvergun is routing this request and gathering evidence…")
>>>>>>> 1630c0d351f49b041623dfd9440b74c011846a37
        start_request(view, request, self._function(), self._completed, self._stream_update)

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

<<<<<<< HEAD
    def _typed_request(self, fallback: str) -> str:
        """Prefer whatever the analyst typed; fall back to the canned directive."""
        typed = self._prompt.toPlainText().strip()
        return typed if typed else fallback

    def _continue_case(self) -> None:
        self._submit(self._typed_request("Continue the investigation from the restored case file. Review unresolved questions and choose the highest-value next evidence to collect."))

    def _review_evidence(self) -> None:
        self._submit(self._typed_request("Audit the latest investigation results. List every significant conclusion with its supporting function, address, xref, string, IL, search, or plugin evidence, and flag unsupported claims."))

    def _clear_console(self) -> None:
        self._prompt.clear()
        self._activity.setPlainText("[00:00:00] CONSOLE CLEARED\n[00:00:00] AWAITING INVESTIGATION")
        self._result.clear()
        self._last_narration = ""
        self._status.setText("SYSTEM READY / ENTER AN INVESTIGATION DIRECTIVE")
        
        # Reset the global event emitter
        reset_event_emitter()
        
        for label in self._capability_labels:
            label.setProperty("active", False)
            label.style().unpolish(label)
            label.style().polish(label)
=======
    def _continue_case(self) -> None:
        self._submit("Continue the investigation from the restored case file. Review unresolved questions and choose the highest-value next evidence to collect.")

    def _review_evidence(self) -> None:
        self._submit("Audit the latest investigation results. List every significant conclusion with its supporting function, address, xref, string, IL, search, or plugin evidence, and flag unsupported claims.")

    def _clear_console(self) -> None:
        self._prompt.clear()
        self._activity.setPlainText("[NOW] CONSOLE CLEARED\n[NOW] AWAITING INVESTIGATION")
        self._result.clear()
        self._status.setText("SYSTEM READY / ENTER AN INVESTIGATION DIRECTIVE")
>>>>>>> 1630c0d351f49b041623dfd9440b74c011846a37

    def _configure(self) -> None:
        from .ui import ProviderDialog
        ProviderDialog(self).exec()

<<<<<<< HEAD
    def _inspect_capabilities(self) -> None:
        from .commands import inspect_capabilities
        view = self._active_view()
        if view:
            inspect_capabilities(view)

    def _completed(self, markdown: str) -> None:
        failed = markdown.startswith("# Provider error") or markdown.startswith("# Silvergun error")
        self._status.setText("ANALYSIS FAILED / REVIEW OUTPUT" if failed else "ANALYSIS COMPLETE / RESULTS LOCKED")
        self._activity.appendPlainText("\n[COMPLETE]" if not failed else "\n[FAILED]")
        self._result.setPlainText(markdown)
        
        # Reset tool highlighting after investigation completes
        self._reset_tool_highlights()
    
    def _reset_tool_highlights(self) -> None:
        """Reset all tool highlights to inactive state."""
        for label in self._capability_labels:
            # Only reset capability labels, not section headers
            if label.property("role") == "capability":
                label.setProperty("active", False)
                label.style().unpolish(label)
                label.style().polish(label)

    def _stream_update(self, technical: str, narration: str | None = None) -> None:
        # Technical event line feeds the ACTIVITY stream.
        formatted_message = self._format_activity_message(technical)
        self._activity.appendPlainText(formatted_message)

        # Extract tool name for highlighting if this is a tool-related message
        tool_name = self._extract_tool_name(technical)
        if tool_name:
            self._highlight_tool(tool_name)

        # Auto-scroll to show latest activity
        scrollbar = self._activity.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

        # Plain-English narration goes to the RESULTS panel so the user can
        # follow what Silvergun is doing while the investigation runs. When no
        # narration was produced (legacy single-argument callers), fall back to
        # the technical line so updates still surface.
        if narration is None:
            narration = technical
        if narration and narration != self._last_narration:
            self._last_narration = narration
            current = self._result.toPlainText()
            if current and not current.endswith("\n"):
                current += "\n"
            self._result.setPlainText((current + f"• {narration}")[-32000:])
            result_scrollbar = self._result.verticalScrollBar()
            result_scrollbar.setValue(result_scrollbar.maximum())
            self._status.setText(f"WORKING / {narration[:44].upper()}")
    
    def _format_activity_message(self, message: str) -> str:
        """Format activity message for consistent display in the stream."""
        if not message:
            return message
        
        # Ensure message ends with newline
        if not message.endswith("\n"):
            message += "\n"
        
        # Apply consistent formatting for different event types
        if message.startswith("[TOOL]"):
            # Clean up tool messages
            return message
        elif message.startswith("[RESULT]"):
            # Clean up result messages
            return message
        elif message.startswith("[PROGRESS]"):
            # Clean up progress messages
            return message
        elif message.startswith("[FINDING]"):
            # Clean up finding messages
            return message
        elif message.startswith("[PLANNER]"):
            # Clean up planner messages
            return message
        elif message.startswith("[STRATEGY]"):
            # Clean up strategy messages
            return message
        elif message.startswith("[ROUND]"):
            # Clean up round messages
            return message
        elif message.startswith("[MEMORY]"):
            # Clean up memory messages
            return message
        elif message.startswith("[FINAL]"):
            # Clean up final messages
            return message
        elif message.startswith("[WARNING]"):
            # Clean up warning messages
            return message
        elif message.startswith("[FAILED]"):
            # Clean up failed messages
            return message
        else:
            # Default formatting for unrecognized messages
            return f"[INFO] {message}" if not message.startswith("[") else message
    
    def _extract_tool_name(self, message: str) -> str | None:
        """Extract tool name from activity message for highlighting."""
        # Handle various message formats
        if message.startswith("[TOOL]") or message.startswith("[RESULT]") or message.startswith("[PROGRESS]") or message.startswith("[FAILED]") or message.startswith("[ANALYSIS]"):
            # Extract text between brackets and the next bracket/colon
            prefix_end = message.find("]") + 1
            if prefix_end > 0 and prefix_end < len(message):
                potential_tool = message[prefix_end:].strip()
                
                # Clean up the tool name
                if potential_tool:
                    # Remove trailing punctuation
                    potential_tool = potential_tool.rstrip(":.")
                    
                    # Extract the actual tool name (before any description)
                    if ":" in potential_tool:
                        potential_tool = potential_tool.split(":")[0].strip()
                    elif " " in potential_tool:
                        # Handle cases like "tool_name: description" or "tool_name description"
                        parts = potential_tool.split()
                        if len(parts) >= 1:
                            potential_tool = parts[0]
                    
                    # Clean up any remaining brackets or special characters
                    potential_tool = potential_tool.strip(" []")
                    
                    if len(potential_tool) > 2:
                        return potential_tool
        
        # Handle tool names in other message types
        for prefix in ["[TOOL]", "[RESULT]", "[PROGRESS]", "[FAILED]", "[ANALYSIS]", "[FINDING]", "[WARNING]"]:
            if prefix in message:
                start_idx = message.find(prefix) + len(prefix)
                if start_idx < len(message):
                    remaining = message[start_idx:].strip()
                    # Look for common tool name patterns
                    if remaining:
                        # Check for known tool prefixes
                        for tool_prefix in ["bn_", "boolhunter_", "external_", "invoke_"]:
                            if tool_prefix in remaining:
                                # Extract the tool name
                                tool_start = remaining.find(tool_prefix)
                                if tool_start >= 0:
                                    # Find the end of the tool name
                                    tool_end = remaining.find(":", tool_start)
                                    if tool_end > tool_start:
                                        tool_name = remaining[tool_start:tool_end].strip()
                                        if len(tool_name) > 2:
                                            return tool_name
                                    else:
                                        # No colon, take to end or space
                                        space_after = remaining.find(" ", tool_start)
                                        if space_after > tool_start:
                                            tool_name = remaining[tool_start:space_after].strip()
                                        else:
                                            tool_name = remaining[tool_start:].strip()
                                        if len(tool_name) > 2:
                                            return tool_name
                        
                        # Try to get the first word that looks like a tool
                        words = remaining.split()
                        for word in words:
                            if len(word) > 2 and word not in ["the", "for", "with", "at", "to", "of", "and", "from"]:
                                # Clean up the word
                                cleaned = word.strip(":.[]")
                                if cleaned:
                                    return cleaned
        
        return None

=======
    def _completed(self, markdown: str) -> None:
        failed = markdown.startswith("# Provider error") or markdown.startswith("# Silvergun error")
        self._status.setText("ANALYSIS FAILED / REVIEW TELEMETRY" if failed else "ANALYSIS COMPLETE / RESULTS LOCKED")
        self._activity.setPlainText("[NOW] CAPABILITY DISENGAGED\n[NOW] ANALYSIS COMPLETE" if not failed else "[NOW] PROVIDER FAULT\n[NOW] ANALYSIS ABORTED")
        self._result.setPlainText(markdown)

    def _stream_update(self, message: str) -> None:
        """Display bounded tool/model events while the background investigation runs."""
        activity = self._activity.toPlainText().splitlines()
        activity.extend(message.splitlines())
        self._activity.setPlainText("\n".join(activity[-12:]))
        current = self._result.toPlainText()
        self._result.setPlainText((current + "\n\n[STREAM] " + message)[-16000:])
        scrollbar = self._result.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

>>>>>>> 1630c0d351f49b041623dfd9440b74c011846a37

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
