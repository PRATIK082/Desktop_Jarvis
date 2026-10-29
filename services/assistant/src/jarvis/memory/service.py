"""Memory & RAG service layer (Agent.md §12).

High-level service combining:
- Conversation memory (recent turns, search, pin, rename, export, delete)
- Explicit long-term memory (store only when user asks or approves)
- Document RAG (ingest, chunk, embed, search, citations, re-index)
- Prompt-injection boundaries: retrieved text is data, not authority.

Uses the repository pattern over SQLite.
"""

from __future__ import annotations

import os
from typing import Any

from jarvis.config import settings
from jarvis.memory.chunking import chunk_text
from jarvis.memory.database import close_db
from jarvis.memory.embeddings import EmbeddingService
from jarvis.memory.extractors import ExtractionResult, extract_text
from jarvis.memory.models import (
    Conversation,
    ConversationMessage,
    Document,
    DocumentChunk,
    Memory,
    SearchResult,
)
from jarvis.memory.repositories import (
    ConversationMessageRepository,
    ConversationRepository,
    DocumentChunkRepository,
    DocumentRepository,
    MemoryRepository,
    sha256_file,
)
from jarvis.telemetry.logger import get_logger, log_event

logger = get_logger("jarvis.memory.service")


class MemoryService:
    """High-level memory and RAG service."""

    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        self.conv_repo = ConversationRepository()
        self.msg_repo = ConversationMessageRepository()
        self.mem_repo = MemoryRepository()
        self.doc_repo = DocumentRepository()
        self.chunk_repo = DocumentChunkRepository()
        self.embedding = embedding_service or EmbeddingService()

    # ------------------------------------------------------------------ close
    async def close(self) -> None:
        close_db()

    # ============================================================== conversation

    def create_conversation(self, title: str) -> Conversation:
        return self.conv_repo.create(title)

    def get_conversation(self, conv_id: str) -> Conversation | None:
        return self.conv_repo.get(conv_id)

    def list_conversations(
        self, include_archived: bool = False, limit: int = 100
    ) -> list[Conversation]:
        return self.conv_repo.list_all(
            include_archived=include_archived, limit=limit
        )

    def rename_conversation(self, conv_id: str, title: str) -> bool:
        return self.conv_repo.update_title(conv_id, title)

    def pin_conversation(self, conv_id: str, pinned: bool) -> bool:
        return self.conv_repo.set_pinned(conv_id, pinned)

    def archive_conversation(self, conv_id: str, archived: bool) -> bool:
        return self.conv_repo.set_archived(conv_id, archived)

    def delete_conversation(self, conv_id: str) -> bool:
        return self.conv_repo.delete(conv_id)

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> ConversationMessage:
        msg = self.msg_repo.add(
            conversation_id, role, content, metadata
        )
        log_event(
            "jarvis.memory.service",
            "message_added",
            details={
                "conversation_id": conversation_id,
                "role": role,
                "content_length": len(content),
            },
        )
        return msg

    def get_recent_messages(
        self, conversation_id: str, limit: int | None = None
    ) -> list[ConversationMessage]:
        """Return recent messages for a conversation (context window)."""
        lim = limit or settings.memory_max_messages_per_conversation
        return self.msg_repo.list_for_conversation(conversation_id, limit=lim)

    def search_conversations(self, query: str, limit: int = 10) -> list[Conversation]:
        """Search conversations by title (case-insensitive)."""
        # Simple title search via repository list + filter.
        all_convs = self.conv_repo.list_all(limit=1000)
        return [
            c for c in all_convs if query.lower() in c.title.lower()
        ][:limit]

    def export_conversation(self, conv_id: str) -> dict[str, Any] | None:
        """Export a conversation with all messages as a dict (for UI export)."""
        conv = self.conv_repo.get(conv_id)
        if conv is None:
            return None
        messages = self.msg_repo.list_for_conversation(conv_id)
        return {
            "id": conv.id,
            "title": conv.title,
            "created_at": conv.created_at,
            "updated_at": conv.updated_at,
            "pinned": conv.pinned,
            "archived": conv.archived,
            "messages": [
                {
                    "id": m.id,
                    "role": m.role,
                    "content": m.content,
                    "created_at": m.created_at,
                    "metadata": m.metadata,
                }
                for m in messages
            ],
        }

    # =================================================================== memory

    def store_memory(
        self,
        text: str,
        tags: list[str] | None = None,
        source_conversation: str | None = None,
        confidence: float = 1.0,
        sensitivity: str = "normal",
        expiration: str | None = None,
    ) -> Memory:
        """Store an explicit long-term memory (Agent.md §12B).

        Caller is responsible for ensuring the user explicitly asked to
        remember, or approved a proposed memory.
        """
        normalized = text.lower().strip()
        if settings.ollama_embedding_model:
            # Embed synchronously is not available here; embeddings are
            # added later via async add_memory_with_embedding.
            pass
        mem = self.mem_repo.create(
            text=text,
            normalized_text=normalized,
            tags=tags,
            source_conversation=source_conversation,
            confidence=confidence,
            sensitivity=sensitivity,
            expiration=expiration,
        )
        log_event(
            "jarvis.memory.service",
            "memory_stored",
            details={
                "memory_id": mem.id,
                "source_conversation": source_conversation,
                "confidence": confidence,
                "sensitivity": sensitivity,
            },
        )
        return mem

    async def store_memory_with_embedding(
        self,
        text: str,
        tags: list[str] | None = None,
        source_conversation: str | None = None,
        confidence: float = 1.0,
        sensitivity: str = "normal",
        expiration: str | None = None,
    ) -> Memory:
        """Store a memory and generate its embedding (async)."""
        normalized = text.lower().strip()
        embedding = await self.embedding.embed(text)
        mem = self.mem_repo.create(
            text=text,
            normalized_text=normalized,
            tags=tags,
            source_conversation=source_conversation,
            confidence=confidence,
            sensitivity=sensitivity,
            expiration=expiration,
            embedding=embedding,
        )
        log_event(
            "jarvis.memory.service",
            "memory_stored_with_embedding",
            details={
                "memory_id": mem.id,
                "has_embedding": embedding is not None and len(embedding) > 0,
            },
        )
        return mem

    def get_memory(self, mem_id: str) -> Memory | None:
        return self.mem_repo.get(mem_id)

    def list_memories(self, limit: int = 100) -> list[Memory]:
        return self.mem_repo.list_all(limit=limit)

    def search_memories(
        self, query: str, limit: int = 10
    ) -> list[Memory]:
        """Search explicit memories by text (case-insensitive)."""
        return self.mem_repo.search(query=query, limit=limit)

    def update_memory(
        self,
        mem_id: str,
        text: str | None = None,
        tags: list[str] | None = None,
        confidence: float | None = None,
        sensitivity: str | None = None,
        expiration: str | None = None,
    ) -> bool:
        return self.mem_repo.update(
            mem_id=mem_id,
            text=text,
            tags=tags,
            confidence=confidence,
            sensitivity=sensitivity,
            expiration=expiration,
        )

    def delete_memory(self, mem_id: str) -> bool:
        result = self.mem_repo.delete(mem_id)
        if result:
            log_event(
                "jarvis.memory.service",
                "memory_deleted",
                details={"memory_id": mem_id},
            )
        return result

    def delete_all_memories(self) -> int:
        count = self.mem_repo.delete_all()
        log_event(
            "jarvis.memory.service",
            "all_memories_deleted",
            details={"count": count},
        )
        return count

    # ==================================================================== RAG

    def list_documents(self, limit: int = 100) -> list[Document]:
        return self.doc_repo.list_all(limit=limit)

    def get_document(self, doc_id: str) -> Document | None:
        return self.doc_repo.get(doc_id)

    def delete_document(self, doc_id: str) -> bool:
        result = self.doc_repo.delete(doc_id)
        if result:
            log_event(
                "jarvis.memory.service",
                "document_deleted",
                details={"document_id": doc_id},
            )
        return result

    def delete_all_documents(self) -> int:
        count = self.doc_repo.delete_all()
        log_event(
            "jarvis.memory.service",
            "all_documents_deleted",
            details={"count": count},
        )
        return count

    async def ingest_document(
        self,
        source_path: str,
        source_name: str | None = None,
    ) -> Document:
        """Ingest a user-selected document into the RAG index.

        Steps:
        1. Extract text (txt, md, json, csv, PDF).
        2. Compute SHA-256 for change detection.
        3. Skip if identical hash already indexed.
        4. Chunk text with overlap.
        5. Embed each chunk via Ollama.
        6. Store document + chunks.

        Returns the Document. Raises ValueError if extraction fails.
        """
        if not os.path.exists(source_path):
            _msg = f"document not found: {source_path}"
            raise FileNotFoundError(_msg)

        if source_name is None:
            source_name = os.path.basename(source_path)

        # Extract text.
        result: ExtractionResult = extract_text(source_path)
        if not result.text.strip() and result.warning and "failed" in (
            result.warning or ""
        ):
            _msg = f"could not extract text: {result.warning}"
            raise ValueError(_msg)

        source_hash = sha256_file(source_path)

        # Skip if same hash already indexed (idempotent re-ingest).
        existing = self.doc_repo.find_by_hash(source_hash)
        if existing is not None and existing.indexed:
            return existing

        # Remove old version if re-ingesting.
        if existing is not None:
            self.doc_repo.delete(existing.id)

        # Create document record.
        doc = self.doc_repo.create(
            source_name=source_name,
            source_path=source_path,
            source_hash=source_hash,
            mime_type=result.mime_type,
            size_bytes=result.size_bytes,
        )

        # Chunk + embed + store.
        chunks = chunk_text(
            result.text,
            chunk_size=settings.memory_chunk_size,
            overlap=settings.memory_chunk_overlap,
        )
        doc_chunks: list[DocumentChunk] = []
        for idx, chunk_text_str in enumerate(chunks):
            embedding = await self.embedding.embed(chunk_text_str)
            doc_chunks.append(
                DocumentChunk(
                    id=f"{doc.id}-{idx}",
                    document_id=doc.id,
                    chunk_index=idx,
                    text=chunk_text_str,
                    embedding=embedding,
                    metadata={
                        "source_name": source_name,
                        "chunk_index": idx,
                        "warning": result.warning,
                    },
                )
            )
        self.chunk_repo.add_many(doc_chunks)
        self.doc_repo.update_indexed(
            doc.id, len(doc_chunks), indexed=True
        )

        log_event(
            "jarvis.memory.service",
            "document_ingested",
            details={
                "document_id": doc.id,
                "source_name": source_name,
                "chunk_count": len(doc_chunks),
                "size_bytes": result.size_bytes,
                "warning": result.warning,
            },
        )
        return doc

    async def reindex_all(self) -> int:
        """Re-index all documents (for changed files or new embedding model)."""
        docs = self.doc_repo.list_all(limit=10000)
        count = 0
        for doc in docs:
            try:
                await self.ingest_document(doc.source_path, doc.source_name)
                count += 1
            except FileNotFoundError:
                # File no longer exists — mark not indexed.
                self.doc_repo.update_indexed(doc.id, 0, indexed=False)
        return count

    def search_documents(
        self,
        query_embedding: list[float],
        limit: int = 10,
        min_score: float = 0.3,
    ) -> list[SearchResult]:
        """Vector search over document chunks.

        Returns SearchResult objects with citations (source_name, section).
        Retrieved text is treated as data, not authority (prompt-injection
        boundary — see §12C).
        """
        if not query_embedding:
            return []
        matches = self.chunk_repo.search_by_embedding(
            query_embedding=query_embedding,
            limit=limit,
            min_score=min_score,
        )
        results: list[SearchResult] = []
        for chunk, score in matches:
            doc = self.doc_repo.get(chunk.document_id)
            source_name = doc.source_name if doc else "unknown document"
            results.append(
                SearchResult(
                    id=chunk.id,
                    text=chunk.text,
                    score=score,
                    source="document",
                    source_name=source_name,
                    metadata={
                        "document_id": chunk.document_id,
                        "chunk_index": chunk.chunk_index,
                        "source_path": doc.source_path if doc else "",
                    },
                )
            )
        return results

    def search_all(
        self,
        query: str,
        query_embedding: list[float] | None = None,
        limit: int = 10,
    ) -> list[SearchResult]:
        """Combined memory + document search.

        Memory results come from text search; document results come from
        vector search (if query_embedding provided).
        """
        results: list[SearchResult] = []

        # Memory search.
        memories = self.mem_repo.search(query=query, limit=limit)
        results = [
            SearchResult(
                id=m.id,
                text=m.text,
                score=m.confidence,
                source="memory",
                source_name=m.source_conversation or "explicit memory",
                metadata={
                    "tags": m.tags,
                    "sensitivity": m.sensitivity,
                    "created_at": m.created_at,
                },
            )
            for m in memories
        ]

        # Document search.
        if query_embedding:
            doc_results = self.search_documents(
                query_embedding=query_embedding,
                limit=limit,
            )
            results.extend(doc_results)

        # Sort by score descending, cap at limit.
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    def delete_all_data(self) -> dict[str, object]:
        """Delete all memory, conversation, and document data (factory reset).

        Returns a report of what was deleted.
        """
        conv_count = len(self.conv_repo.list_all(limit=100000))
        for c in self.conv_repo.list_all(limit=100000):
            self.conv_repo.delete(c.id)
        mem_count = self.mem_repo.delete_all()
        doc_count = self.doc_repo.delete_all()
        report: dict[str, object] = {
            "conversations_deleted": conv_count,
            "memories_deleted": mem_count,
            "documents_deleted": doc_count,
        }
        log_event(
            "jarvis.memory.service",
            "factory_reset",
            details=report,
        )
        return report
