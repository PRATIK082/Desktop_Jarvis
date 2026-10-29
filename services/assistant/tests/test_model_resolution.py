"""Regression tests for model threading (commit 1).

Covers the spoken-error root cause: ChatRequest had no model field and the
orchestrator never passed a model to chat_stream/chat_structured, so every
chat fell back to an empty settings.ollama_chat_model; the Ollama failure
was then embedded as speakable '[JARVIS error: ...]' text and read aloud.

Tests: request → settings → first-installed-non-embedding resolution order,
model_missing error event (never spoken) when nothing is available, no
speakable raw-error text on Ollama failure (specific error code instead),
ChatRequest.model field, and /v1/chat threading the model end to end.

Hermetic: Ollama is stubbed/mocked (no live server needed); settings mutated
via monkeypatch (auto-restored).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette import status as http_status

import jarvis.api.app as app_module
from jarvis.api.app import ChatRequest, create_app
from jarvis.api.ollama import OllamaConnectionError
from jarvis.config import settings
from jarvis.orchestration.events import TranscriptEvent
from jarvis.orchestration.orchestrator import Orchestrator
from jarvis.policy.engine import PolicyEngine
from jarvis.providers.base import MockOllamaProvider as MockOllama
from jarvis.tools.registry import ToolRegistry


class _RecordingOllama(MockOllama):
    """Mock Ollama that records which model each call received."""

    def __init__(self, models: list[str] | None = None) -> None:
        super().__init__(models=models)
        self.last_stream_model: object = "unset"
        self.last_structured_model: object = "unset"

    async def chat_stream(
        self,
        messages: list[dict[str, object]],
        model: str | None = None,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        self.last_stream_model = model
        async for chunk in super().chat_stream(messages, model=model, temperature=temperature):
            yield chunk

    async def chat_structured(
        self,
        messages: list[dict[str, object]],
        schema: dict[str, object],
        model: str | None = None,
        temperature: float = 0.1,
    ) -> dict[str, object]:
        self.last_structured_model = model
        return await super().chat_structured(messages, schema, model=model, temperature=temperature)


class _FailingOllama(MockOllama):
    """Mock Ollama whose chat_stream always fails (connection refused)."""

    _failure = "connection refused"

    async def chat_stream(
        self,
        messages: list[dict[str, object]],
        model: str | None = None,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        raise OllamaConnectionError(self._failure)
        yield  # pragma: no cover — makes this an async generator


def _orchestrator(ollama: MockOllama) -> Orchestrator:
    return Orchestrator(
        ollama=ollama,
        registry=ToolRegistry(),
        policy=PolicyEngine(),
        max_tool_iterations=3,
    )


async def _collect(orch: Orchestrator, **kwargs: Any) -> list[Any]:
    return [
        event
        async for event in orch.run_turn(
            user_input="hello",
            conversation_id="test-conv",
            request_id="test-req",
            **kwargs,
        )
    ]


async def test_request_model_wins_over_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ollama_chat_model", "settings-model")
    rec = _RecordingOllama(models=["settings-model"])
    await _collect(_orchestrator(rec), model="request-model")
    assert rec.last_stream_model == "request-model"


async def test_settings_model_used_when_no_request_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ollama_chat_model", "settings-model")
    rec = _RecordingOllama(models=["settings-model"])
    await _collect(_orchestrator(rec))
    assert rec.last_stream_model == "settings-model"


async def test_first_installed_non_embedding_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ollama_chat_model", "")
    rec = _RecordingOllama(models=["nomic-embed-text:latest", "qwen3:8b"])
    await _collect(_orchestrator(rec))
    assert rec.last_stream_model == "qwen3:8b"


class _EmptyOllama(MockOllama):
    """Mock Ollama with zero installed models (MockOllama maps [] to defaults)."""

    async def list_models(self) -> list[str]:
        return []


async def test_model_missing_event_when_no_model_anywhere(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ollama_chat_model", "")
    events = await _collect(_orchestrator(_EmptyOllama()))
    errors = [e for e in events if e.type == "assistant_error"]
    assert len(errors) == 1
    assert errors[0].code == "model_missing"
    # Never spoken: no assistant transcript, no speakable error text.
    assert not [e for e in events if e.type == "transcript" and e.role == "assistant"]
    assert not [e for e in events if e.type == "stream_chunk"]


async def test_ollama_failure_emits_error_event_not_speakable_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ollama_chat_model", "dead-model")
    events = await _collect(_orchestrator(_FailingOllama()))
    texts = [
        e.text if e.type == "transcript" else e.delta
        for e in events
        if e.type in ("transcript", "stream_chunk")
    ]
    assert not any("[JARVIS error" in t for t in texts)
    assert not any(t.startswith("[error:") for t in texts)
    errors = [e for e in events if e.type == "assistant_error"]
    assert len(errors) == 1
    assert errors[0].code == "ollama_connection_error"


def test_chat_request_carries_optional_model() -> None:
    body = ChatRequest(user_input="hi", conversation_id="c", request_id="r", model="m")
    assert body.model == "m"
    assert ChatRequest(user_input="hi", conversation_id="c", request_id="r").model is None


class _RecordingEndpointOrchestrator:
    """Minimal run_turn double proving the endpoint threads the model."""

    def __init__(self) -> None:
        self.last_model: object = "unset"

    async def run_turn(
        self,
        user_input: str,
        conversation_id: str,
        request_id: str,
        model: str | None = None,
    ) -> AsyncIterator[TranscriptEvent]:
        self.last_model = model
        yield TranscriptEvent(role="assistant", text="ok", is_final=True, turn_id=request_id)


def test_chat_endpoint_threads_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "auth_token", "secret123")
    fake = _RecordingEndpointOrchestrator()
    monkeypatch.setattr(app_module, "_orchestrator", fake)
    client = TestClient(create_app())
    resp = client.post(
        "/v1/chat",
        headers={"Authorization": "Bearer secret123"},
        json={
            "user_input": "hi",
            "conversation_id": "c",
            "request_id": "r",
            "model": "endpoint-model",
        },
    )
    assert resp.status_code == http_status.HTTP_200_OK, resp.text
    assert fake.last_model == "endpoint-model"
