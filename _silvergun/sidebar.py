"""Silvergun SidebarWidget: a compact UI entry point for the bounded agent."""

from __future__ import annotations

from pathlib import Path

from binaryninjaui import Sidebar, SidebarWidget, SidebarWidgetType
try:
    from binaryninjaui import SidebarContextSensitivity, SidebarWidgetLocation
except ImportError:
    SidebarContextSensitivity = None
    SidebarWidgetLocation = None
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout

from .commands import start_request


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
        self._frame = frame
        self._offset = None
        # `data` is not consistently a BinaryView across Binary Ninja versions;
        # notifyViewChanged supplies the authoritative ViewFrame-to-BinaryView handoff.
        self._bv = data if hasattr(data, "get_function_containing") else None
        self._data = data
        self._status = QLabel("Ready. Ask a focused question about the current binary.")
        self._status.setWordWrap(True)
        self._prompt = QPlainTextEdit()
        self._prompt.setPlaceholderText("Ask Silvergun… e.g. explain this function or find unsafe input flows")
        self._prompt.setMinimumHeight(84)
        self._result = QPlainTextEdit()
        self._result.setReadOnly(True)
        self._result.setPlaceholderText("Results appear here while the analysis report is also available in a separate report view.")

        ask = QPushButton("Ask")
        ask.clicked.connect(self._ask)
        explain = QPushButton("Explain current function")
        explain.clicked.connect(self._explain)
        security = QPushButton("Find vulnerabilities")
        security.clicked.connect(self._security)
        configure = QPushButton("Provider…")
        configure.clicked.connect(self._configure)
        row = QHBoxLayout()
        row.addWidget(ask)
        row.addWidget(configure)
        quick = QHBoxLayout()
        quick.addWidget(explain)
        quick.addWidget(security)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        title = QLabel("Silvergun")
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(title)
        layout.addWidget(self._prompt)
        layout.addLayout(row)
        layout.addLayout(quick)
        layout.addWidget(self._status)
        layout.addWidget(self._result, 1)

    def notifyViewChanged(self, view_frame):
        """Receive Binary Ninja's ViewFrame and unwrap its active BinaryView."""
        self._frame = view_frame
        self._bv = _view_from_frame(view_frame)
        if self._bv is None:
            self._status.setText("No active BinaryView is available.")
        else:
            self._status.setText("Ready. Ask a focused question about the current binary.")

    def notifyOffsetChanged(self, offset):
        """Track cursor movement without querying unsupported ViewFrame fields."""
        self._offset = offset

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
            self._status.setText("Enter a request first.")
            return
        view = self._active_view()
        if view is None:
            self._status.setText("No active BinaryView is available. Open a binary in a Binary Ninja view first.")
            return
        self._status.setText("Silvergun is analyzing in the background…")
        self._result.setPlainText("")
        start_request(view, request, self._function(), self._completed)

    def _ask(self) -> None:
        self._submit(self._prompt.toPlainText())

    def _explain(self) -> None:
        self._submit("Explain the current function with evidence from its compact context and xrefs.")

    def _security(self) -> None:
        self._submit("Find potential vulnerabilities in the current function. Report evidence, reachability questions, impact, and confidence without overstating.")

    def _configure(self) -> None:
        from .ui import ProviderDialog
        ProviderDialog(self).exec()

    def _completed(self, markdown: str) -> None:
        self._status.setText("Analysis complete.")
        self._result.setPlainText(markdown)


class SilvergunSidebarWidgetType(SidebarWidgetType):
    def __init__(self):
        icon_path = Path(__file__).parent / "assets" / "silvergun_icon.png"
        icon = QImage(str(icon_path))
        if icon.isNull():
            icon = QImage(56, 56, QImage.Format_RGB32)
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
