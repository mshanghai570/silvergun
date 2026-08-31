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
    QFileDialog,
    QVBoxLayout,
)

from .client import OpenAICompatibleClient, ProviderError
from .config import ProviderConfig, api_key, cached_models, config, has_secret_storage, set_cached_models, set_provider, store_api_key


class _ModelLoader(QObject):
    completed = Signal(int, list, str)

    def load(self, token: int, base_url: str, key: str, ca_bundle: str) -> None:
        def worker() -> None:
            try:
                current = config()
                temporary = ProviderConfig(base_url.strip().rstrip("/"), "", current.timeout_seconds, current.max_steps, current.parallel_jobs, current.max_context_chars, ca_bundle.strip())
                models = OpenAICompatibleClient(temporary, key).list_models()
                self.completed.emit(token, models, f"Loaded {len(models)} model(s).")
            except ProviderError as error:
                self.completed.emit(token, [], str(error))
            except Exception as error:
                self.completed.emit(token, [], f"Model lookup failed: {error}")
        threading.Thread(target=worker, name="silvergun-model-list", daemon=True).start()


class ProviderDialog(QDialog):
    """A short, debounced dialog that can discover models without blocking the UI."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        current = config()
        self._token = 0
        self._key_dirty = False
        self.setWindowTitle("Silvergun Provider")
        self.setMinimumWidth(620)

        self.base_url = QLineEdit(current.normalized_base_url)
        self.base_url.setPlaceholderText("https://provider.example/v1")
        self.key = QLineEdit(api_key(current.normalized_base_url))
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("API key (stored through Binary Ninja's secret provider when available)")
        self.ca_bundle = QLineEdit(current.ca_bundle)
        self.ca_bundle.setPlaceholderText("Optional PEM bundle path; leave empty for system roots or certifi")
        browse_ca = QPushButton("Browse…")
        browse_ca.clicked.connect(self._browse_ca_bundle)
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
        ca_row = QHBoxLayout()
        ca_row.addWidget(self.ca_bundle)
        ca_row.addWidget(browse_ca)
        form.addRow("CA bundle", ca_row)
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
        self.base_url.textChanged.connect(self._base_url_changed)
        self.key.textChanged.connect(self._mark_key_dirty_and_refresh)
        self.ca_bundle.textChanged.connect(self._schedule_refresh)

    def _browse_ca_bundle(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select PEM CA bundle")
        if path:
            self.ca_bundle.setText(path)

    def _base_url_changed(self) -> None:
        # A key is namespaced by base URL, so changing the endpoint must save the
        # current key under the new endpoint when secret storage is available.
        self._key_dirty = True
        self._schedule_refresh()

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
        self._loader.load(self._token, self.base_url.text(), self.key.text(), self.ca_bundle.text())

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
        try:
            set_provider(base_url, model, self.ca_bundle.text())
            set_cached_models(self.model.itemText(index) for index in range(self.model.count()))
            if self._key_dirty:
                key = self.key.text()
                if key and not has_secret_storage():
                    self.status.setText("Provider settings were saved, but no Binary Ninja secret provider is available. The API key was not persisted; configure secret storage or leave the key blank.")
                    return
                if has_secret_storage() and not store_api_key(base_url, key):
                    self.status.setText("Provider settings were saved, but the API key could not be stored. Check Binary Ninja secret-provider permissions.")
                    return
        except Exception as error:
            self.status.setText(f"Could not save provider settings: {type(error).__name__}: {error}")
            return
        self.accept()


def configure_provider_dialog() -> bool:
    return ProviderDialog().exec() == QDialog.DialogCode.Accepted
