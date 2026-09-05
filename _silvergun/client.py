"""Small OpenAI-compatible HTTP client using only the Python standard library."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
import ssl
from typing import Any, Iterable, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MODERN_OPENAI_REASONING_PREFIXES = ("gpt-5", "o1", "o3", "o4")
MAX_COMPATIBILITY_RETRIES = 3


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
            "stream": False,
        }
        if _uses_completion_token_limit(model):
            # GPT-5 and OpenAI reasoning models reject the legacy max_tokens
            # field and only accept their default temperature.
            body["max_completion_tokens"] = max_tokens
        else:
            body["temperature"] = 0.1
            body["max_tokens"] = max_tokens
        compact_tools = list(tools)
        if compact_tools:
            body["tools"] = compact_tools
            body["tool_choice"] = "auto"
        payload = self._chat_request(body, max_tokens)
        try:
            choice = payload["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError, TypeError) as error:
            raise ProviderError("The provider returned no chat completion choices.") from error
        content = _text_content(message.get("content", "")) if isinstance(message, dict) else ""
        calls = message.get("tool_calls", []) if isinstance(message, dict) else []
        tool_calls = tuple(call for call in calls if isinstance(call, dict)) if isinstance(calls, list) else ()
        content, legacy_calls = _extract_legacy_tool_calls(content)
        tool_calls = tool_calls + legacy_calls
        return ChatCompletion(content, tool_calls, choice.get("finish_reason"), payload)

    def _chat_request(self, body: dict[str, Any], max_tokens: int) -> dict[str, Any]:
        """Retry only documented parameter incompatibilities from compatible APIs.

        Some gateways expose an OpenAI reasoning model through a deployment alias,
        so its name cannot be used to choose the right request shape in advance.
        Adapt only after an explicit unsupported-parameter response; authentication,
        quota, model, and ordinary provider errors still surface immediately.
        """
        for _attempt in range(MAX_COMPATIBILITY_RETRIES):
            try:
                return self._request("POST", "/chat/completions", body)
            except ProviderError as error:
                if not _apply_chat_compatibility_fix(body, max_tokens, str(error)):
                    raise
        # Every retry changes the payload, so reaching this branch is defensive.
        return self._request("POST", "/chat/completions", body)

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


def _extract_legacy_tool_calls(content: str) -> tuple[str, tuple[dict[str, Any], ...]]:
    """Convert common XML-like tool markup emitted by older compatible models.

    Some providers return strings such as ``<tool_call>bn_search_strings`` in
    ``message.content`` instead of using the OpenAI ``tool_calls`` field. Keep
    the compatibility path deliberately narrow: only a tool block containing
    ``arg_key``/``arg_value`` pairs is promoted to an executable call.
    """
    if "<tool_call>" not in content or "<arg_key>" not in content:
        return content, ()
    calls: list[dict[str, Any]] = []
    spans: list[tuple[int, int]] = []
    block_pattern = re.compile(r"<tool_call>(.*?)(?:</tool_call>|$)", re.IGNORECASE | re.DOTALL)
    for match in block_pattern.finditer(content):
        block = match.group(1)
        name_match = re.search(r"(?:^|>)([A-Za-z_][A-Za-z0-9_-]*)\s*<arg_key>", block, re.IGNORECASE)
        if not name_match:
            continue
        arguments: dict[str, Any] = {}
        for argument in re.finditer(r"<arg_key>\s*(.*?)\s*</arg_key>\s*<arg_value>\s*(.*?)\s*</arg_value>", block, re.IGNORECASE | re.DOTALL):
            key = argument.group(1).strip()
            raw_value = re.sub(r"<[^>]+>", "", argument.group(2)).strip()
            try:
                value: Any = json.loads(raw_value)
            except json.JSONDecodeError:
                value = raw_value
            arguments[key] = value
        if arguments:
            calls.append({
                "id": f"legacy_call_{len(calls) + 1}",
                "type": "function",
                "function": {"name": name_match.group(1), "arguments": json.dumps(arguments, separators=(",", ":"))},
            })
            spans.append((match.start(), match.end()))
    if not calls:
        return content, ()
    cleaned = content
    for start, end in reversed(spans):
        cleaned = cleaned[:start] + cleaned[end:]
    return cleaned.strip(), tuple(calls)


def _uses_completion_token_limit(model: str) -> bool:
    """Identify OpenAI models that reject max_tokens and non-default temperature."""
    normalized = model.strip().lower()
    return normalized.startswith(MODERN_OPENAI_REASONING_PREFIXES)


def _apply_chat_compatibility_fix(body: dict[str, Any], max_tokens: int, detail: str) -> bool:
    """Apply one safe, provider-directed Chat Completions compatibility change."""
    normalized = detail.lower()
    unsupported = "unsupported" in normalized or "not supported" in normalized or "does not support" in normalized
    if unsupported and "max_completion_tokens" in normalized and "max_completion_tokens" in body:
        # A non-OpenAI gateway may expose a modern model name while retaining
        # the legacy OpenAI-compatible field names.
        body.pop("max_completion_tokens", None)
        body["max_tokens"] = max_tokens
        body.setdefault("temperature", 0.1)
        return True
    if unsupported and "max_tokens" in normalized and "max_completion_tokens" in normalized and "max_tokens" in body:
        body.pop("max_tokens", None)
        body["max_completion_tokens"] = max_tokens
        return True
    if unsupported and "temperature" in normalized and "temperature" in body:
        body.pop("temperature", None)
        return True
    return False


def _safe_error_body(error: HTTPError) -> str:
    try:
        raw = error.read(2048).decode("utf-8", errors="replace")
        payload = json.loads(raw)
        if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
            return str(payload["error"].get("message", "unspecified error"))
        return raw.strip().replace("\n", " ")[:500] or "unspecified error"
    except Exception:
        return error.reason or "unspecified error"
