"""Provider configuration backed by Binary Ninja user settings and secrets storage."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable

from binaryninja import Settings
from binaryninja.enums import SettingsScope
from binaryninja.secretsprovider import SecretsProvider


PREFIX = "silvergun"
SETTINGS = Settings()


@dataclass(frozen=True)
class ProviderConfig:
    """Non-secret settings needed for an OpenAI-compatible API."""

    base_url: str
    model: str
    timeout_seconds: int
    max_steps: int
    parallel_jobs: int
    max_context_chars: int
    ca_bundle: str

    @property
    def normalized_base_url(self) -> str:
        return self.base_url.rstrip("/")


def _schema(title: str, description: str, kind: str, default, **extra: object) -> str:
    properties = {
        "title": title,
        "description": description,
        "type": kind,
        "default": default,
        "ignore": ["SettingsProjectScope", "SettingsResourceScope"],
    }
    properties.update(extra)
    return json.dumps(properties)


def register_settings() -> None:
    """Register non-analysis settings once in the default settings schema."""
    SETTINGS.register_group(PREFIX, "Silvergun")
    definitions = {
        "baseUrl": _schema("Provider Base URL", "OpenAI-compatible API root, normally ending in /v1.", "string", "https://api.openai.com/v1"),
        "model": _schema("Model", "Model identifier to use for chat completions.", "string", ""),
        "modelCache": _schema("Model Cache", "Cached models from the last successful provider lookup.", "string", "[]", isSerialized=True, hidden=True),
        "secretProvider": _schema("Secret Provider", "Optional Binary Ninja secrets provider name used for the API key.", "string", ""),
        "timeoutSeconds": _schema("Request Timeout", "Network timeout for provider requests in seconds.", "number", 45, minValue=5, maxValue=300),
<<<<<<< HEAD
        "maxSteps": _schema("Maximum Tool Rounds", "Hard limit for agent tool rounds; compound goals like find-and-patch need several rounds.", "number", 5, minValue=1, maxValue=8),
=======
        "maxSteps": _schema("Maximum Tool Rounds", "Hard limit for agent tool rounds; keep this low for speed.", "number", 3, minValue=1, maxValue=8),
>>>>>>> 1630c0d351f49b041623dfd9440b74c011846a37
        "parallelJobs": _schema("Parallel Reviews", "Maximum independent remote read-only reviews.", "number", 3, minValue=1, maxValue=8),
        "maxContextChars": _schema("Context Budget", "Maximum compact program context passed to the model.", "number", 18000, minValue=4000, maxValue=64000),
        "caBundle": _schema("CA Bundle Path", "Optional PEM CA bundle used for provider TLS verification. Leave empty for system roots or certifi.", "string", "", ignore=["SettingsProjectScope", "SettingsResourceScope"]),
    }
    for suffix, props in definitions.items():
        key = f"{PREFIX}.{suffix}"
        if not SETTINGS.contains(key):
            SETTINGS.register_setting(key, props)


def config() -> ProviderConfig:
    return ProviderConfig(
        base_url=SETTINGS.get_string(f"{PREFIX}.baseUrl"),
        model=SETTINGS.get_string(f"{PREFIX}.model"),
        timeout_seconds=SETTINGS.get_integer(f"{PREFIX}.timeoutSeconds"),
        max_steps=SETTINGS.get_integer(f"{PREFIX}.maxSteps"),
        parallel_jobs=SETTINGS.get_integer(f"{PREFIX}.parallelJobs"),
        max_context_chars=SETTINGS.get_integer(f"{PREFIX}.maxContextChars"),
        ca_bundle=SETTINGS.get_string(f"{PREFIX}.caBundle"),
    )


def _set_user_string(key: str, value: str) -> None:
    """Write a user setting across Binary Ninja Settings API signatures."""
    try:
        SETTINGS.set_string(key, value, SettingsScope.SettingsUserScope)
    except TypeError:
        # Older hosts expose set_string(key, value) and use the default user scope.
        SETTINGS.set_string(key, value)


def set_provider(base_url: str, model: str, ca_bundle: str = "") -> None:
    _set_user_string(f"{PREFIX}.baseUrl", base_url.strip().rstrip("/"))
    _set_user_string(f"{PREFIX}.model", model.strip())
    _set_user_string(f"{PREFIX}.caBundle", ca_bundle.strip())


def cached_models() -> list[str]:
    raw = SETTINGS.get_string(f"{PREFIX}.modelCache")
    try:
        models = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    return [str(model) for model in models if isinstance(model, str)]


def set_cached_models(models: Iterable[str]) -> None:
    unique = sorted(set(str(model) for model in models if model))
    _set_user_string(f"{PREFIX}.modelCache", json.dumps(unique))


def available_secret_providers() -> list[str]:
    try:
        return [provider.name for provider in SecretsProvider if provider.name]
    except Exception:
        return []


def _secret_key(base_url: str) -> str:
    digest = hashlib.sha256(base_url.strip().rstrip("/").encode("utf-8")).hexdigest()[:20]
    return f"{PREFIX}.api-key.{digest}"


def _secrets_provider():
    preferred = SETTINGS.get_string(f"{PREFIX}.secretProvider")
    if preferred:
        provider = SecretsProvider.get(preferred)
        if provider is not None:
            return provider
    providers = list(SecretsProvider)
    return providers[0] if providers else None


def api_key(base_url: str) -> str:
    provider = _secrets_provider()
    if provider is None:
        return ""
    try:
        return provider.get_data(_secret_key(base_url)) or ""
    except Exception:
        return ""


def store_api_key(base_url: str, value: str) -> bool:
    """Store a key only through a configured Binary Ninja secret provider."""
    provider = _secrets_provider()
    if provider is None:
        return False
    try:
        if value:
            # Binary Ninja providers commonly return None on success.
            result = provider.store_data(_secret_key(base_url), value)
            return result is not False
        result = provider.delete_data(_secret_key(base_url))
        return result is not False
    except Exception:
        return False


def has_secret_storage() -> bool:
    return _secrets_provider() is not None
