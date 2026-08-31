"""Small OpenAI-compatible HTTP client using only the Python standard library."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import ssl
from typing import Any, Iterable, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


MAX_RESPONSE_BYTES = 8 * 1024 * 1024


class ProviderSettings(Protocol):
    normalized_base_url: str
    model: str
    timeout_seconds: int
    ca_bundle: str


class ProviderError(RuntimeError):
    """A provider error safe to show in the Binary Ninja UI."""


@dataclass(frozen=True)
class ChatCompletion:
    content: str
    tool_calls: tuple[dict[str, Any], ...]
    finish_reason: str | None
    raw: Mapping[str, Any]


class OpenAICompatibleClient:
    """Implements the two interoperable endpoints Silvergun needs."""

    def __init__(self, settings: ProviderSettings, api_key: str) -> None:
        if not settings.normalized_base_url:
            raise ProviderError("A provider base URL is required.")
        self._base_url = settings.normalized_base_url
        self._api_key = api_key
        self._timeout = max(5, int(settings.timeout_seconds))
        self._ssl_context = _build_ssl_context(getattr(settings, "ca_bundle", ""))

    def list_models(self) -> list[str]:
        payload = self._request("GET", "/models")
        records = payload.get("data", [])
        if not isinstance(records, list):
            raise ProviderError("The /models response did not contain a data array.")
        names = [record.get("id") for record in records if isinstance(record, dict) and isinstance(record.get("id"), str)]
        return sorted(set(names))

    def chat(
        self,
        model: str,
        messages: Iterable[Mapping[str, Any]],
        tools: Iterable[Mapping[str, Any]] = (),
        *,
        max_tokens: int = 1400,
    ) -> ChatCompletion:
        if not model:
            raise ProviderError("Choose a model in Silvergun > Configure Provider before asking the agent.")
        body: dict[str, Any] = {
            "model": model,
            "messages": list(messages),
            "temperature": 0.1,
            "max_tokens": max_tokens,
            "stream": False,
        }
        compact_tools = list(tools)
        if compact_tools:
            body["tools"] = compact_tools
            body["tool_choice"] = "auto"
        payload = self._request("POST", "/chat/completions", body)
        try:
            choice = payload["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError, TypeError) as error:
            raise ProviderError("The provider returned no chat completion choices.") from error
        content = _text_content(message.get("content", "")) if isinstance(message, dict) else ""
        calls = message.get("tool_calls", []) if isinstance(message, dict) else []
        tool_calls = tuple(call for call in calls if isinstance(call, dict)) if isinstance(calls, list) else ()
        return ChatCompletion(content, tool_calls, choice.get("finish_reason"), payload)

    def _request(self, method: str, path: str, body: Mapping[str, Any] | None = None) -> dict[str, Any]:
        headers = {"Accept": "application/json", "User-Agent": "Silvergun/0.1"}
        data = None
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        request = Request(f"{self._base_url}{path}", data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self._timeout, context=self._ssl_context) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as error:
            detail = _safe_error_body(error)
            raise ProviderError(f"Provider returned HTTP {error.code}: {detail}") from error
        except URLError as error:
            reason = str(error.reason)
            if "CERTIFICATE_VERIFY_FAILED" in reason or "certificate verify failed" in reason.lower():
                raise ProviderError(
                    "TLS certificate verification failed. Install/update the host CA roots or set "
                    "Silvergun’s CA Bundle Path to a PEM CA bundle. Verification remains enabled; "
                    "Silvergun will not disable TLS verification."
                ) from error
            raise ProviderError(f"Could not reach provider: {error.reason}") from error
        except TimeoutError as error:
            raise ProviderError(f"Provider request timed out after {self._timeout} seconds.") from error
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ProviderError("Provider response exceeded the 8 MiB safety limit.")
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProviderError("Provider returned invalid JSON.") from error
        if not isinstance(decoded, dict):
            raise ProviderError("Provider returned an unexpected JSON response.")
        if isinstance(decoded.get("error"), dict):
            message = decoded["error"].get("message", "unspecified provider error")
            raise ProviderError(f"Provider error: {message}")
        return decoded


def _build_ssl_context(ca_bundle: str) -> ssl.SSLContext:
    """Build a verifying context, preferring an explicit PEM bundle then certifi."""
    requested = ca_bundle.strip() or os.environ.get("SSL_CERT_FILE", "").strip() or os.environ.get("REQUESTS_CA_BUNDLE", "").strip()
    if requested:
        if not os.path.isfile(requested):
            raise ProviderError(f"CA bundle path does not exist: {requested}")
        try:
            return ssl.create_default_context(cafile=requested)
        except ssl.SSLError as error:
            raise ProviderError(f"CA bundle could not be loaded: {error}") from error
    try:
        import certifi  # Optional; Binary Ninja installations may not ship it.
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _text_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            item.get("text", "") for item in content if isinstance(item, dict) and isinstance(item.get("text"), str)
        )
    return ""


def _safe_error_body(error: HTTPError) -> str:
    try:
        raw = error.read(2048).decode("utf-8", errors="replace")
        payload = json.loads(raw)
        if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
            return str(payload["error"].get("message", "unspecified error"))
        return raw.strip().replace("\n", " ")[:500] or "unspecified error"
    except Exception:
        return error.reason or "unspecified error"
