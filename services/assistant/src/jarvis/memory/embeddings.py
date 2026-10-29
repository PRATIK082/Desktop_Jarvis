"""Embeddings via Ollama (Agent.md §12C).

Generates embeddings for document chunks and memory items using the
local Ollama embedding model. Falls back gracefully when Ollama is
unavailable (degraded mode).
"""

from __future__ import annotations

from jarvis.api.ollama import OllamaClient, OllamaError
from jarvis.config import settings
from jarvis.telemetry.logger import get_logger, log_event

logger = get_logger("jarvis.memory.embeddings")


class EmbeddingService:
    """Generates embeddings using the local Ollama embedding model.

    Never auto-downloads a model — if the embedding model is not installed,
    returns empty embeddings and logs a warning.
    """

    def __init__(self, ollama_client: OllamaClient | None = None) -> None:
        self._ollama = ollama_client
        self._model = settings.ollama_embedding_model

    @property
    def model(self) -> str:
        return self._model

    def set_model(self, model_name: str) -> None:
        self._model = model_name

    async def embed(self, text: str) -> list[float]:
        """Return an embedding vector for `text`.

        Returns an empty list if Ollama is unavailable or the model
        is not installed (degraded mode — no exception raised).
        """
        if not self._model:
            return []
        if self._ollama is None:
            return []
        try:
            return await self._ollama.embed(text, model=self._model)
        except OllamaError as exc:
            if exc.error_code == "ollama_model_not_installed":
                log_event(
                    "jarvis.memory.embeddings",
                    "embedding_model_not_installed",
                    level="warn",
                    details={"model": self._model},
                )
            else:
                log_event(
                    "jarvis.memory.embeddings",
                    "embedding_error",
                    level="warn",
                    details={"error": str(exc)[:200]},
                )
            return []
        except Exception as exc:  # noqa: BLE001 — degraded mode
            log_event(
                "jarvis.memory.embeddings",
                "embedding_error",
                level="warn",
                details={"error": str(exc)[:200]},
            )
            return []

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts, returning one vector per text."""
        return [await self.embed(text) for text in texts]
