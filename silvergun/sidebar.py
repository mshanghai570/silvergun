"""Silvergun SidebarWidget: a compact UI entry point for the bounded agent."""

from __future__ import annotations

from pathlib import Path

from binaryninjaui import Sidebar, SidebarContextSensitivity, SidebarWidget, SidebarWidgetType, SidebarWidgetLocation
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout

from .commands import start_request
from .ui import ProviderDialog


class SilvergunSidebarWidget(SidebarWidget):
    def __init__(self, name, frame, data):
        super().__init__(name)
        self._frame = frame
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

    def _function(self):
        try:
            offset = self._frame.getCurrentOffset()
            return self._data.get_function_containing(offset)
        except Exception:
            return None

    def _submit(self, request: str) -> None:
        request = request.strip()
        if not request:
            self._status.setText("Enter a request first.")
            return
        self._status.setText("Silvergun is analyzing in the background…")
        self._result.setPlainText("")
        start_request(self._data, request, self._function(), self._completed)

    def _ask(self) -> None:
        self._submit(self._prompt.toPlainText())

    def _explain(self) -> None:
        self._submit("Explain the current function with evidence from its compact context and xrefs.")

    def _security(self) -> None:
        self._submit("Find potential vulnerabilities in the current function. Report evidence, reachability questions, impact, and confidence without overstating.")

    def _configure(self) -> None:
        ProviderDialog(self).exec()

    def _completed(self, markdown: str) -> None:
        self._status.setText("Analysis complete.")
        self._result.setPlainText(markdown)


class SilvergunSidebarWidgetType(SidebarWidgetType):
    def __init__(self):
        icon_path = Path(__file__).parent / "assets" / "silvergun_icon.png"
        icon = QImage(str(icon_path))
        if icon.isNull():
            icon = QImage(56, 56, QImage.Format.Format_ARGB32)
            icon.fill(Qt.GlobalColor.transparent)
        SidebarWidgetType.__init__(self, icon, "Silvergun")

    def createWidget(self, frame, data):
        return SilvergunSidebarWidget("Silvergun", frame, data)

    def defaultLocation(self):
        return SidebarWidgetLocation.RightContent

    def contextSensitivity(self):
        return SidebarContextSensitivity.SelfManagedSidebarContext


SIDEBAR_WIDGET_TYPE = SilvergunSidebarWidgetType()
Sidebar.addSidebarWidgetType(SIDEBAR_WIDGET_TYPE)
