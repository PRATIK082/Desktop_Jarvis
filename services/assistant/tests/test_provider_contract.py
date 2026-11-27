"""Contract tests for the provider-neutral LLM interface."""

from __future__ import annotations

import pytest

from jarvis.api.ollama import OllamaClient
from jarvis.providers.base import LLMProvider, MockOllamaProvider, OllamaProvider


def test_mock_provider_implements_provider_neutral_contract() -> None:
    provider = MockOllamaProvider()
    assert isinstance(provider, LLMProvider)
    assert isinstance(provider, OllamaProvider)


def test_ollama_client_implements_provider_neutral_contract() -> None:
    # Structural check only: this does not connect to a running Ollama server.
    provider = OllamaClient(base_url="http://127.0.0.1:11434")
    try:
        assert isinstance(provider, LLMProvider)
        assert isinstance(provider, OllamaProvider)
    finally:
        # AsyncClient.close is async; no network request is made by construction.
        import asyncio

        asyncio.run(provider.close())


@pytest.mark.asyncio
async def test_mock_provider_supports_chat_structured_and_embeddings() -> None:
    provider = MockOllamaProvider()

    chunks = [
        chunk
        async for chunk in provider.chat_stream(
            [{"role": "user", "content": "hello"}],
            model="test-model",
        )
    ]
    structured = await provider.chat_structured(
        [{"role": "user", "content": "hello"}],
        schema={"type": "object"},
        model="test-model",
    )
    embedding = await provider.embed("hello", model="test-embedding")

    assert chunks
    assert structured["tool_calls"] == []
    assert len(embedding) == 32
    assert await provider.health_check() is True
