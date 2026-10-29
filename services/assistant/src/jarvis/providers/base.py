"""Provider interfaces (abstract base classes) with mock implementations.

Interfaces are provider-agnostic so the sidecar stays operational when an
optional provider is unavailable (degraded mode, Agent.md rule 20).
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@runtime_checkable
class STTProvider(Protocol):
    """Speech-to-text provider. Stream transcripts from audio."""

    async def transcribe_stream(self, audio_chunks: AsyncIterator[bytes]) -> AsyncIterator[str]:
        ...

    async def health(self) -> bool:
        ...


@runtime_checkable
class WakeWordProvider(Protocol):
    """Optional wake-word detection provider."""

    async def detect(self, audio_chunks: AsyncIterator[bytes]) -> AsyncIterator[bool]:
        ...

    async def health(self) -> bool:
        ...


@runtime_checkable
class TTSProvider(Protocol):
    """Text-to-speech provider. Stream audio from text."""

    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        ...

    async def health(self) -> bool:
        ...


@runtime_checkable
class OllamaProvider(Protocol):
    """Ollama local LLM provider (Agent.md §8)."""

    async def health_check(self) -> bool:
        ...

    async def list_models(self) -> list[str]:
        ...

    async def show_model(self, model: str) -> dict[str, object]:
        ...

    async def chat_stream(
        self,
        messages: list[dict[str, object]],
        model: str | None = None,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        ...

    async def chat_structured(
        self,
        messages: list[dict[str, object]],
        schema: dict[str, object],
        model: str | None = None,
        temperature: float = 0.1,
    ) -> dict[str, object]:
        ...

    async def embed(self, text: str, model: str | None = None) -> list[float]:
        ...

    async def cancel_generation(self) -> None:
        ...

    async def get_runtime_metrics(self) -> dict[str, object]:
        ...


@dataclass
class MockSTTResult:
    text: str
    is_final: bool


class MockSTTProvider:
    """Deterministic mock STT for tests (no real microphone/audio)."""

    def __init__(self, transcripts: list[str] | None = None) -> None:
        self._transcripts = transcripts or ["hello jarvis"]
        self._index = 0

    async def transcribe_stream(self, audio_chunks: AsyncIterator[bytes]) -> AsyncIterator[str]:
        if self._index < len(self._transcripts):
            text = self._transcripts[self._index]
            self._index += 1
            yield text
        return

    async def health(self) -> bool:
        return True


class MockWakeWordProvider:
    """Deterministic mock wake-word provider for tests."""

    def __init__(self, detections: list[bool] | None = None) -> None:
        self._detections = detections or [False]
        self._index = 0

    async def detect(self, audio_chunks: AsyncIterator[bytes]) -> AsyncIterator[bool]:
        if self._index < len(self._detections):
            value = self._detections[self._index]
            self._index += 1
            yield value
        return

    async def health(self) -> bool:
        return True


class MockTTSProvider:
    """Deterministic mock TTS for tests (yields silence bytes)."""

    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        # Yield a small silence frame to represent synthesized audio.
        yield b"\x00" * 160
        return

    async def health(self) -> bool:
        return True


class MockOllamaProvider:
    """Deterministic mock Ollama for tests (no live model required)."""

    def __init__(self, models: list[str] | None = None) -> None:
        self._models = models or ["llama3.2:latest", "nomic-embed-text:latest"]
        self._cancelled = False

    async def health_check(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return list(self._models)

    async def show_model(self, model: str) -> dict[str, object]:
        return {
            "name": model,
            "modified_at": "2024-01-01T00:00:00Z",
            "size": 0,
            "digest": "sha256:" + "0" * 64,
            "details": {"format": "gguf", "family": "llama", "parameter_size": "mock"},
        }

    async def chat_stream(
        self,
        messages: list[dict[str, object]],
        model: str | None = None,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        self._cancelled = False
        # Stream a short deterministic response word by word.
        response = "This is a mocked streaming response from JARVIS."
        for word in response.split():
            if self._cancelled:
                return
            yield word + " "
        return

    async def chat_structured(
        self,
        messages: list[dict[str, object]],
        schema: dict[str, object],
        model: str | None = None,
        temperature: float = 0.1,
    ) -> dict[str, object]:
        # Deterministic structured response: no tool call by default.
        return {"tool_calls": [], "text": "I can help with that."}

    async def embed(self, text: str, model: str | None = None) -> list[float]:
        # Deterministic pseudo-embedding: hash-based stable vector.
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [float(b) / 255.0 for b in digest[:32]]

    async def cancel_generation(self) -> None:
        self._cancelled = True

    async def get_runtime_metrics(self) -> dict[str, object]:
        return {"mock": True, "models": len(self._models)}
