"""Memory & RAG data models (Agent.md §12).

Three memory layers:
A. Conversation memory — recent turns for ongoing context.
B. Explicit long-term memory — user-initiated or approved memories.
C. Document knowledge — user-selected files, locally embedded and cited.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class Conversation:
    """A conversation session with title and messages."""

    id: str
    title: str
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    pinned: bool = False
    archived: bool = False
    message_count: int = 0


@dataclass
class ConversationMessage:
    """A single message within a conversation."""

    id: str
    conversation_id: str
    role: str  # "user" | "assistant" | "system" | "tool"
    content: str
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Memory:
    """Explicit long-term memory item (Agent.md §12B)."""

    id: str
    text: str
    normalized_text: str
    tags: list[str] = field(default_factory=list)
    source_conversation: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    confidence: float = 1.0
    sensitivity: str = "normal"  # "normal" | "sensitive" | "secret"
    expiration: str | None = None  # ISO timestamp or None
    pinned: bool = False
    embedding: list[float] | None = None


@dataclass
class Document:
    """A user-selected document for RAG (Agent.md §12C)."""

    id: str
    source_name: str  # user-visible name
    source_path: str  # canonical path
    source_hash: str  # SHA-256 of file contents for change detection
    mime_type: str
    size_bytes: int
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    chunk_count: int = 0
    indexed: bool = False


@dataclass
class DocumentChunk:
    """A chunk of a document with embedding for vector search."""

    id: str
    document_id: str
    chunk_index: int
    text: str
    embedding: list[float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    """A search result from memory or RAG."""

    id: str
    text: str
    score: float  # cosine similarity, higher = more relevant
    source: str  # "memory" | "document"
    source_name: str  # human-readable source
    metadata: dict[str, Any] = field(default_factory=dict)
