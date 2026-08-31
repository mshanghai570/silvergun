"""Small Qt configuration dialog; imported only by the interactive configuration command."""

from __future__ import annotations

import threading

import binaryninjaui  # Must precede PySide imports in Binary Ninja UI plugins.
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from .client import OpenAICompatibleClient, ProviderError
from .config import ProviderConfig, api_key, cached_models, config, has_secret_storage, set_cached_models, set_provider, store_api_key


class _ModelLoader(QObject):
    completed = Signal(int, list, str)

    def load(self, token: int, base_url: str, key: str) -> None:
        def worker() -> None:
            try:
                current = config()
                temporary = ProviderConfig(base_url.strip().rstrip("/"), "", current.timeout_seconds, current.max_steps, current.parallel_jobs, current.max_context_chars)
                models = OpenAICompatibleClient(temporary, key).list_models()
                self.completed.emit(token, models, f"Loaded {len(models)} model(s).")
            except ProviderError as error:
                self.completed.emit(token, [], str(error))
            except Exception as error:
                self.completed.emit(token, [], f"Model lookup failed: {error}")
        threading.Thread(target=worker, name="lean-model-list", daemon=True).start()


class ProviderDialog(QDialog):
    """A short, debounced dialog that can discover models without blocking the UI."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        current = config()
        self._token = 0
        self._key_dirty = False
        self.setWindowTitle("Lean Ninja Provider")
        self.setMinimumWidth(620)

        self.base_url = QLineEdit(current.normalized_base_url)
        self.base_url.setPlaceholderText("https://provider.example/v1")
        self.key = QLineEdit(api_key(current.normalized_base_url))
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("API key (stored through Binary Ninja's secret provider when available)")
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.addItems(cached_models())
        if current.model:
            self.model.setCurrentText(current.model)
        self.status = QLabel("Edit the base URL or API key to load available models.")
        self.status.setWordWrap(True)
        refresh = QPushButton("Refresh models")
        refresh.clicked.connect(self._schedule_refresh)

        form = QFormLayout()
        form.addRow("Base URL", self.base_url)
        form.addRow("API key", self.key)
        form.addRow("Model", self.model)
        controls = QHBoxLayout()
        controls.addWidget(refresh)
        controls.addStretch(1)
        form.addRow("Models", controls)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.status)
        layout.addWidget(buttons)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(420)
        self._timer.timeout.connect(self._refresh)
        self._loader = _ModelLoader(self)
        self._loader.completed.connect(self._models_loaded)
        self.base_url.textChanged.connect(self._schedule_refresh)
        self.key.textChanged.connect(self._mark_key_dirty_and_refresh)

    def _mark_key_dirty_and_refresh(self) -> None:
        self._key_dirty = True
        self._schedule_refresh()

    def _schedule_refresh(self) -> None:
        if self.base_url.text().strip():
            self.status.setText("Waiting briefly for more edits before loading models…")
            self._timer.start()

    def _refresh(self) -> None:
        self._token += 1
        self.status.setText("Loading models…")
        self._loader.load(self._token, self.base_url.text(), self.key.text())

    def _models_loaded(self, token: int, models: list, message: str) -> None:
        if token != self._token:
            return
        if models:
            chosen = self.model.currentText()
            self.model.blockSignals(True)
            self.model.clear()
            self.model.addItems(models)
            self.model.setCurrentText(chosen if chosen in models else models[0])
            self.model.blockSignals(False)
        self.status.setText(message)

    def _save(self) -> None:
        base_url = self.base_url.text().strip().rstrip("/")
        model = self.model.currentText().strip()
        if not base_url or not model:
            self.status.setText("Both a base URL and a model are required.")
            return
        set_provider(base_url, model)
        set_cached_models(self.model.itemText(index) for index in range(self.model.count()))
        if self._key_dirty:
            if not store_api_key(base_url, self.key.text()):
                if self.key.text() and not has_secret_storage():
                    self.status.setText("Provider settings were saved, but no Binary Ninja secret provider is available. The API key was not persisted.")
                    return
                self.status.setText("Provider settings were saved, but the API key could not be stored.")
                return
        self.accept()


def configure_provider_dialog() -> bool:
    return ProviderDialog().exec() == QDialog.DialogCode.Accepted
