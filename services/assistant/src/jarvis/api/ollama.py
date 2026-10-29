"""Ollama local LLM client (Agent.md §8).

- Binds to local Ollama base URL (configurable, default 127.0.0.1:11434)
- health_check, list_models, show_model, chat_stream, chat_structured, embed,
  cancel_generation, get_runtime_metrics, close
- Timeouts, exponential backoff with limit for safe transient failures
- Structured error categories; never downloads a model without explicit approval
- Strict JSON schema validation for structured tool-plan responses
- Sanitizes tool outputs before returning them to the model
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, cast

import httpx

from jarvis.config import settings

HTTP_OK = 200
HTTP_NOT_FOUND = 404
HTTP_BAD_REQUEST = 400

# Retry only safe transient failures (connection / timeout). Max attempts
# includes the original attempt, so max_attempts=3 => 1 initial + 2 retries.
MAX_RETRY_ATTEMPTS = 3
BACKOFF_BASE_S = 0.5


class OllamaError(Exception):
    """Base Ollama client error."""

    def __init__(self, message: str, error_code: str = "ollama_error") -> None:
        super().__init__(message)
        self.error_code = error_code


class OllamaConnectionError(OllamaError):
    def __init__(self, message: str) -> None:
        super().__init__(message, "ollama_connection_error")


class OllamaTimeoutError(OllamaError):
    def __init__(self, message: str) -> None:
        super().__init__(message, "ollama_timeout")


class OllamaModelNotInstalledError(OllamaError):
    def __init__(self, model: str) -> None:
        message = f"model not installed: {model}"
        super().__init__(message, "ollama_model_not_installed")
        self.model = model


class OllamaContextLengthError(OllamaError):
    def __init__(self, message: str) -> None:
        super().__init__(message, "ollama_context_length")


class OllamaMalformedOutputError(OllamaError):
    def __init__(self, message: str) -> None:
        super().__init__(message, "ollama_malformed_output")


class OllamaInternalError(OllamaError):
    def __init__(self, message: str) -> None:
        super().__init__(message, "ollama_internal_error")


def _is_retriable(exc: Exception) -> bool:
    """Only connection and timeout errors are safe to retry."""
    retriable = (
        httpx.ConnectError,
        httpx.ConnectTimeout,
        httpx.ReadTimeout,
        httpx.WriteTimeout,
    )
    return isinstance(exc, retriable)


async def _retry(
    fn: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any
) -> Any:
    """Run `fn` with exponential backoff, retrying only safe transient failures."""
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRY_ATTEMPTS):
        try:
            return await fn(*args, **kwargs)
        except OllamaError:
            # Structured Ollama errors are not retried (model-not-installed,
            # context-length, malformed-output are permanent).
            raise
        except Exception as exc:  # noqa: BLE001 — classify below
            last_exc = exc
            if not _is_retriable(exc) or attempt == MAX_RETRY_ATTEMPTS - 1:
                break
            delay = BACKOFF_BASE_S * (2**attempt)
            await asyncio.sleep(delay)
    if last_exc is not None:
        raise last_exc  # unreachable in practice; satisfies type checker
    _retry_exhausted = "unexpected retry exhaustion"
    raise OllamaError(_retry_exhausted, "ollama_internal_error")


def _sanitize_tool_output(output: Any) -> str:
    """Sanitize a tool result before returning it to the model.

    Redacts secrets, truncates oversized payloads, and never returns raw
    exceptions/stack traces. The model must never see untrusted tool output
    verbatim.
    """
    if output is None:
        return ""
    text = str(output)
    # Redact likely secrets (tokens, keys, passwords) crudely; a richer
    # redaction pass lives in telemetry.logger.SENSITIVE_KEYS.
    _secret_pattern = r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*\S+"  # noqa: S105 — redaction pattern, not a credential
    text = re.sub(_secret_pattern, r"\1=***REDACTED***", text)
    # Truncate oversized outputs to protect the context window.
    max_len = 4000
    if len(text) > max_len:
        text = text[:max_len] + "\n...[output truncated by JARVIS]..."
    return text


class OllamaClient:
    """Client for the local Ollama HTTP API."""

    def __init__(self, base_url: str, timeout_s: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout_s)

    # ── health / discovery -----------------------------------------------

    async def health_check(self) -> bool:
        """Return True if Ollama is reachable and responding."""
        try:
            resp = await self._client.get("/api/tags", timeout=5.0)
        except (httpx.ConnectError, httpx.ConnectTimeout):
            return False
        except httpx.RequestError:
            return False
        else:
            return resp.status_code == HTTP_OK

    async def list_models(self) -> list[str]:
        """List installed model names."""
        resp = await self._client.get("/api/tags")
        if resp.status_code != HTTP_OK:
            msg = f"list_models failed: HTTP {resp.status_code}"
            raise OllamaError(msg)
        data: dict[str, object] = resp.json()
        models = data.get("models", [])
        if not isinstance(models, list):
            return []
        return [str(m.get("name", "")) for m in models if isinstance(m, dict)]

    async def show_model(self, model: str) -> dict[str, object]:
        """Return metadata for an installed model (modelfile, parameters, etc.)."""
        resp = await self._client.post("/api/show", json={"name": model})
        if resp.status_code == HTTP_NOT_FOUND:
            raise OllamaModelNotInstalledError(model)
        if resp.status_code != HTTP_OK:
            _show_error = f"show_model failed: HTTP {resp.status_code}"
            raise OllamaError(_show_error)
        data: dict[str, object] = resp.json()
        if not isinstance(data, dict):
            _non_object = "show_model returned non-object body"
            raise OllamaMalformedOutputError(_non_object)
        return data

    # ── chat -------------------------------------------------------------

    async def chat_stream(
        self,
        messages: list[dict[str, object]],
        model: str | None = None,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        """Stream chat tokens from Ollama. Raises OllamaError subclasses on failure."""

        async def _stream() -> AsyncIterator[str]:
            payload: dict[str, object] = {
                "model": model or settings.ollama_chat_model,
                "messages": messages,
                "stream": True,
                "options": {"temperature": temperature},
            }
            async with self._client.stream(
                "POST", "/api/chat", json=payload, timeout=self.timeout_s
            ) as resp:
                if resp.status_code == HTTP_NOT_FOUND:
                    raise OllamaModelNotInstalledError(str(payload["model"]))
                if resp.status_code == HTTP_BAD_REQUEST:
                    body = await resp.aread()
                    text = body.decode("utf-8", errors="replace")
                    if "context length" in text.lower() or "context" in text.lower():
                        raise OllamaContextLengthError(text)
                    raise OllamaMalformedOutputError(text)
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    obj: dict[str, object] = json.loads(line)
                    message = obj.get("message", {})
                    content = ""
                    if isinstance(message, dict):
                        content_val = message.get("content", "")
                        if isinstance(content_val, str):
                            content = content_val
                    if content:
                        yield content
                    if obj.get("done"):
                        return

        async for chunk in _stream():
            yield chunk

    async def chat_structured(
        self,
        messages: list[dict[str, object]],
        schema: dict[str, object],
        model: str | None = None,
        temperature: float = 0.1,
    ) -> dict[str, object]:
        """Request a structured (JSON-schema-constrained) response.

        Validates the parsed JSON against `schema`. Raises
        OllamaMalformedOutputError if the model's output does not conform.
        Temperature defaults low (0.1) for deterministic action planning.
        """

        async def _structured() -> dict[str, object]:
            payload: dict[str, object] = {
                "model": model or settings.ollama_chat_model,
                "messages": messages,
                "stream": False,
                "format": schema,
                "options": {"temperature": temperature},
            }
            resp = await self._client.post("/api/chat", json=payload, timeout=self.timeout_s)
            if resp.status_code == HTTP_NOT_FOUND:
                raise OllamaModelNotInstalledError(str(payload["model"]))
            if resp.status_code == HTTP_BAD_REQUEST:
                body = await resp.aread()
                text = body.decode("utf-8", errors="replace")
                if "context length" in text.lower() or "context" in text.lower():
                    raise OllamaContextLengthError(text)
                raise OllamaMalformedOutputError(text)
            resp.raise_for_status()
            data: dict[str, object] = resp.json()
            message = data.get("message", {})
            if not isinstance(message, dict):
                _msg = "chat response missing message object"
                raise OllamaMalformedOutputError(_msg)
            content = message.get("content", "")
            if not isinstance(content, str) or not content.strip():
                _msg = "chat response missing text content"
                raise OllamaMalformedOutputError(_msg)
            try:
                parsed: dict[str, object] = json.loads(content)
            except json.JSONDecodeError as exc:
                _msg = f"model output is not valid JSON: {exc}"
                raise OllamaMalformedOutputError(_msg) from exc
            if not isinstance(parsed, dict):
                _msg = "model output JSON is not an object"
                raise OllamaMalformedOutputError(_msg)
            _validate_against_schema(parsed, schema)
            return parsed

        return cast(dict[str, object], await _retry(_structured))

    # ── embeddings -------------------------------------------------------

    async def embed(self, text: str, model: str | None = None) -> list[float]:
        """Get embeddings for text via Ollama."""
        payload: dict[str, object] = {
            "model": model or settings.ollama_embedding_model,
            "prompt": text,
        }
        resp = await self._client.post("/api/embeddings", json=payload)
        if resp.status_code == HTTP_NOT_FOUND:
            raise OllamaModelNotInstalledError(str(payload["model"]))
        if resp.status_code != HTTP_OK:
            _msg = f"embed failed: HTTP {resp.status_code}"
            raise OllamaError(_msg)
        data: dict[str, object] = resp.json()
        embedding = data.get("embedding", [])
        return [float(x) for x in embedding] if isinstance(embedding, list) else []

    # ── control / metrics ------------------------------------------------

    async def cancel_generation(self) -> None:
        """Cancel the current Ollama generation (best-effort)."""
        try:
            await self._client.post("/api/generate/cancel")
        except httpx.RequestError:
            pass  # cancel is best-effort

    async def get_runtime_metrics(self) -> dict[str, object]:
        """Return Ollama runtime metrics if available."""
        try:
            resp = await self._client.get("/api/version")
            if resp.status_code == HTTP_OK:
                data: dict[str, object] = resp.json()
                return data
        except httpx.RequestError:
            pass
        return {}

    async def close(self) -> None:
        await self._client.aclose()


# ── JSON schema validation ------------------------------------------------


def _validate_against_schema(instance: dict[str, object], schema: dict[str, object]) -> None:
    """Lightweight structural validation of `instance` against `schema`.

    Supports: type (object/string/number/integer/boolean/array), required,
    properties, additionalProperties:false, enum, minLength/maxLength,
    minimum/maximum, items. Raises OllamaMalformedOutputError on violation.
    This is intentionally small and dependency-free; do not expand without
    an explicit need — the schema contracts are simple.
    """
    SchemaValidator(instance, schema).validate()


class SchemaValidator:
    """Structural validator for JSON-schema-like constraints.

    Each `_check_*` method is small to avoid PLR0915 (too-many-statements).
    """

    def __init__(self, instance: dict[str, object], schema: dict[str, object]) -> None:
        self.instance = instance
        self.schema = schema

    def validate(self) -> None:
        self._check(self.instance, self.schema, "")

    # -- dispatch -----------------------------------------------------------

    def _check(self, node: Any, subschema: dict[str, object], path: str) -> None:
        expected_type = subschema.get("type")
        if isinstance(expected_type, str):
            self._check_type(node, expected_type, path, subschema)
        if isinstance(node, dict) and expected_type == "object":
            self._check_object(node, subschema, path)
        elif isinstance(node, list) and expected_type == "array":
            self._check_array(node, subschema, path)
        elif isinstance(node, str) and expected_type == "string":
            self._check_string(node, subschema, path)
        elif isinstance(node, bool) and expected_type == "boolean":
            self._check_boolean(node, subschema, path)
        elif (
            isinstance(node, (int, float))
            and not isinstance(node, bool)
            and expected_type in ("number", "integer")
        ):
            self._check_number(node, subschema, path)

    # -- type ---------------------------------------------------------------

    def _check_type(
        self, node: Any, expected_type: str, path: str, subschema: dict[str, object]
    ) -> None:
        ok = False
        if expected_type == "object":
            ok = isinstance(node, dict)
        elif expected_type == "array":
            ok = isinstance(node, list)
        elif expected_type == "string":
            ok = isinstance(node, str)
        elif expected_type == "boolean":
            ok = isinstance(node, bool)
        elif expected_type in ("number", "integer"):
            ok = isinstance(node, (int, float)) and not isinstance(node, bool)
            if expected_type == "integer" and ok and isinstance(node, float):
                ok = node.is_integer()
        if not ok:
            _msg = (
                f"at {path or 'root'}: expected type {expected_type}, "
                f"got {type(node).__name__}"
            )
            raise OllamaMalformedOutputError(_msg)

    # -- object -------------------------------------------------------------

    def _check_object(
        self, node: dict[str, object], subschema: dict[str, object], path: str
    ) -> None:
        required = subschema.get("required", [])
        if isinstance(required, list):
            for key in required:
                if key not in node:
                    _msg = f"at {path or 'root'}: missing required property '{key}'"
                    raise OllamaMalformedOutputError(_msg)
        properties = subschema.get("properties", {})
        if isinstance(properties, dict):
            for key, value in node.items():
                if key in properties:
                    self._check(
                        value,
                        properties[key] if isinstance(properties[key], dict) else {},
                        f"{path}.{key}",
                    )
                else:
                    additional = subschema.get("additionalProperties", True)
                    if additional is False:
                        _msg = (
                            f"at {path}.{key}: additional property not allowed "
                            "(additionalProperties:false)"
                        )
                        raise OllamaMalformedOutputError(_msg)

    # -- array --------------------------------------------------------------

    def _check_array(self, node: list[object], subschema: dict[str, object], path: str) -> None:
        items = subschema.get("items")
        if isinstance(items, dict):
            for idx, item in enumerate(node):
                self._check(item, items, f"{path}[{idx}]")

    # -- string -------------------------------------------------------------

    def _check_string(self, node: str, subschema: dict[str, object], path: str) -> None:
        enum = subschema.get("enum")
        if isinstance(enum, list) and node not in enum:
            _msg = f"at {path}: value '{node}' not in enum {enum}"
            raise OllamaMalformedOutputError(_msg)
        min_len = subschema.get("minLength")
        if isinstance(min_len, int) and len(node) < min_len:
            _msg = f"at {path}: string shorter than minLength {min_len}"
            raise OllamaMalformedOutputError(_msg)
        max_len = subschema.get("maxLength")
        if isinstance(max_len, int) and len(node) > max_len:
            _msg = f"at {path}: string longer than maxLength {max_len}"
            raise OllamaMalformedOutputError(_msg)

    # -- boolean ------------------------------------------------------------

    def _check_boolean(self, node: bool, subschema: dict[str, object], path: str) -> None:
        # boolean has no facets beyond type.
        _ = node, subschema, path

    # -- number -------------------------------------------------------------

    def _check_number(self, node: float, subschema: dict[str, object], path: str) -> None:
        minimum = subschema.get("minimum")
        if isinstance(minimum, (int, float)) and node < minimum:
            _msg = f"at {path}: value {node} below minimum {minimum}"
            raise OllamaMalformedOutputError(_msg)
        maximum = subschema.get("maximum")
        if isinstance(maximum, (int, float)) and node > maximum:
            _msg = f"at {path}: value {node} above maximum {maximum}"
            raise OllamaMalformedOutputError(_msg)
