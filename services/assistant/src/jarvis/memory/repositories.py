"""Repository pattern for memory & RAG (Agent.md §12).

Repositories encapsulate all SQL access for conversations, messages,
memories, documents, and document chunks.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from jarvis.memory.database import get_db
from jarvis.memory.models import (
    Conversation,
    ConversationMessage,
    Document,
    DocumentChunk,
    Memory,
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _row_to_dict(row: Any) -> dict[str, object]:
    return {k: row[k] for k in row.keys()}


# ── Conversation repository ──────────────────────────────────────────


class ConversationRepository:
    """CRUD for conversations."""

    def create(self, title: str) -> Conversation:
        conv_id = str(uuid.uuid4())
        now = _now()
        db = get_db()
        db.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at, "
            "pinned, archived, message_count) "
            "VALUES (?, ?, ?, ?, 0, 0, 0)",
            (conv_id, title, now, now),
        )
        db.commit()
        return Conversation(
            id=conv_id, title=title, created_at=now, updated_at=now
        )

    def get(self, conv_id: str) -> Conversation | None:
        row = get_db().fetchone(
            "SELECT * FROM conversations WHERE id = ?", (conv_id,)
        )
        if row is None:
            return None
        return Conversation(
            id=row["id"],
            title=row["title"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            pinned=bool(row["pinned"]),
            archived=bool(row["archived"]),
            message_count=row["message_count"],
        )

    def list_all(
        self, include_archived: bool = False, limit: int = 100
    ) -> list[Conversation]:
        if include_archived:
            rows = get_db().fetchall(
                "SELECT * FROM conversations "
                "ORDER BY pinned DESC, updated_at DESC LIMIT ?",
                (limit,),
            )
        else:
            rows = get_db().fetchall(
                "SELECT * FROM conversations WHERE archived = 0 "
                "ORDER BY pinned DESC, updated_at DESC LIMIT ?",
                (limit,),
            )
        return [
            Conversation(
                id=r["id"],
                title=r["title"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                pinned=bool(r["pinned"]),
                archived=bool(r["archived"]),
                message_count=r["message_count"],
            )
            for r in rows
        ]

    def update_title(self, conv_id: str, title: str) -> bool:
        result = get_db().execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
            (title, _now(), conv_id),
        )
        get_db().commit()
        return result.rowcount > 0

    def set_pinned(self, conv_id: str, pinned: bool) -> bool:
        result = get_db().execute(
            "UPDATE conversations SET pinned = ?, updated_at = ? WHERE id = ?",
            (1 if pinned else 0, _now(), conv_id),
        )
        get_db().commit()
        return result.rowcount > 0

    def set_archived(self, conv_id: str, archived: bool) -> bool:
        result = get_db().execute(
            "UPDATE conversations SET archived = ?, updated_at = ? WHERE id = ?",
            (1 if archived else 0, _now(), conv_id),
        )
        get_db().commit()
        return result.rowcount > 0

    def delete(self, conv_id: str) -> bool:
        result = get_db().execute(
            "DELETE FROM conversations WHERE id = ?", (conv_id,)
        )
        get_db().commit()
        return result.rowcount > 0

    def increment_message_count(self, conv_id: str) -> None:
        get_db().execute(
            "UPDATE conversations SET message_count = message_count + 1, "
            "updated_at = ? WHERE id = ?",
            (_now(), conv_id),
        )
        get_db().commit()


# ── Conversation message repository ──────────────────────────────────


class ConversationMessageRepository:
    """CRUD for conversation messages."""

    def add(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> ConversationMessage:
        msg_id = str(uuid.uuid4())
        now = _now()
        db = get_db()
        db.execute(
            "INSERT INTO conversation_messages (id, conversation_id, role, "
            "content, created_at, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                msg_id,
                conversation_id,
                role,
                content,
                now,
                json.dumps(metadata or {}),
            ),
        )
        get_db().execute(
            "UPDATE conversations SET message_count = message_count + 1 WHERE id = ?",
            (conversation_id,),
        )
        db.commit()
        return ConversationMessage(
            id=msg_id,
            conversation_id=conversation_id,
            role=role,
            content=content,
            created_at=now,
            metadata=metadata or {},
        )

    def list_for_conversation(
        self, conversation_id: str, limit: int = 50
    ) -> list[ConversationMessage]:
        rows = get_db().fetchall(
            "SELECT * FROM conversation_messages WHERE conversation_id = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (conversation_id, limit),
        )
        # Reverse to chronological order.
        rows = list(reversed(rows))
        return [
            ConversationMessage(
                id=r["id"],
                conversation_id=r["conversation_id"],
                role=r["role"],
                content=r["content"],
                created_at=r["created_at"],
                metadata=json.loads(r["metadata"] or "{}"),
            )
            for r in rows
        ]

    def delete_for_conversation(self, conversation_id: str) -> int:
        result = get_db().execute(
            "DELETE FROM conversation_messages WHERE conversation_id = ?",
            (conversation_id,),
        )
        get_db().commit()
        return result.rowcount


# ── Memory repository ────────────────────────────────────────────────


class MemoryRepository:
    """CRUD for explicit long-term memories (Agent.md §12B)."""

    def create(
        self,
        text: str,
        normalized_text: str,
        tags: list[str] | None = None,
        source_conversation: str | None = None,
        confidence: float = 1.0,
        sensitivity: str = "normal",
        expiration: str | None = None,
        embedding: list[float] | None = None,
    ) -> Memory:
        mem_id = str(uuid.uuid4())
        now = _now()
        db = get_db()
        db.execute(
            "INSERT INTO memories (id, text, normalized_text, tags, source_conversation, "
            "created_at, updated_at, confidence, sensitivity, expiration, pinned, embedding) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)",
            (
                mem_id,
                text,
                normalized_text,
                json.dumps(tags or []),
                source_conversation,
                now,
                now,
                confidence,
                sensitivity,
                expiration,
                json.dumps(embedding) if embedding is not None else None,
            ),
        )
        db.commit()
        return Memory(
            id=mem_id,
            text=text,
            normalized_text=normalized_text,
            tags=tags or [],
            source_conversation=source_conversation,
            created_at=now,
            updated_at=now,
            confidence=confidence,
            sensitivity=sensitivity,
            expiration=expiration,
            embedding=embedding,
        )

    def get(self, mem_id: str) -> Memory | None:
        row = get_db().fetchone("SELECT * FROM memories WHERE id = ?", (mem_id,))
        if row is None:
            return None
        return self._row_to_memory(row)

    def list_all(
        self, limit: int = 100, include_expired: bool = False
    ) -> list[Memory]:
        now = _now()
        if include_expired:
            rows = get_db().fetchall(
                "SELECT * FROM memories ORDER BY pinned DESC, updated_at DESC LIMIT ?",
                (limit,),
            )
        else:
            rows = get_db().fetchall(
                "SELECT * FROM memories "
                "WHERE (expiration IS NULL OR expiration > ?) "
                "ORDER BY pinned DESC, updated_at DESC LIMIT ?",
                (now, limit),
            )
        return [self._row_to_memory(r) for r in rows]

    def search(
        self,
        query: str,
        limit: int = 10,
        min_confidence: float = 0.0,
    ) -> list[Memory]:
        """Simple text search over memories (case-insensitive LIKE)."""
        like = f"%{query.lower()}%"
        rows = get_db().fetchall(
            "SELECT * FROM memories "
            "WHERE lower(normalized_text) LIKE ? "
            "AND confidence >= ? "
            "ORDER BY confidence DESC, updated_at DESC LIMIT ?",
            (like, min_confidence, limit),
        )
        return [self._row_to_memory(r) for r in rows]

    def update(
        self,
        mem_id: str,
        text: str | None = None,
        tags: list[str] | None = None,
        confidence: float | None = None,
        sensitivity: str | None = None,
        expiration: str | None = None,
    ) -> bool:
        # Allowed updatable column names — validated to prevent SQL injection.
        _ALLOWED_FIELDS = {
            "text",
            "normalized_text",
            "tags",
            "confidence",
            "sensitivity",
            "expiration",
            "updated_at",
        }
        fields: list[str] = []
        params: list[object] = []
        if text is not None:
            fields.append("text = ?")
            params.append(text)
            fields.append("normalized_text = ?")
            params.append(text.lower())
        if tags is not None:
            fields.append("tags = ?")
            params.append(json.dumps(tags))
        if confidence is not None:
            fields.append("confidence = ?")
            params.append(confidence)
        if sensitivity is not None:
            fields.append("sensitivity = ?")
            params.append(sensitivity)
        if expiration is not None:
            fields.append("expiration = ?")
            params.append(expiration)
        if not fields:
            return False
        fields.append("updated_at = ?")
        params.append(_now())
        params.append(mem_id)
        # All field names are from _ALLOWED_FIELDS (hardcoded above), so this
        # is safe — no user-controlled column names enter the SQL. Build the
        # SET clause via concatenation (not f-string) to avoid S608.
        set_parts: list[str] = []
        for field in fields:
            col = field.split(" = ")[0]
            if col in _ALLOWED_FIELDS:
                set_parts.append(field)
        set_clause = ", ".join(set_parts)
        # Column names validated against _ALLOWED_FIELDS whitelist above;
        # no user-controlled identifiers enter the SQL.
        sql = "UPDATE memories SET " + set_clause + " WHERE id = ?"  # noqa: S608
        result = get_db().execute(sql, tuple(params))
        get_db().commit()
        return result.rowcount > 0

    def delete(self, mem_id: str) -> bool:
        result = get_db().execute("DELETE FROM memories WHERE id = ?", (mem_id,))
        get_db().commit()
        return result.rowcount > 0

    def delete_all(self) -> int:
        result = get_db().execute("DELETE FROM memories")
        count = result.rowcount
        get_db().commit()
        return count

    def _row_to_memory(self, row: Any) -> Memory:
        embedding = None
        if row["embedding"] is not None:
            try:
                embedding = json.loads(row["embedding"])
            except (json.JSONDecodeError, TypeError):
                embedding = None
        return Memory(
            id=row["id"],
            text=row["text"],
            normalized_text=row["normalized_text"],
            tags=json.loads(row["tags"] or "[]"),
            source_conversation=row["source_conversation"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            confidence=row["confidence"],
            sensitivity=row["sensitivity"],
            expiration=row["expiration"],
            pinned=bool(row["pinned"]),
            embedding=embedding,
        )


# ── Document repository ──────────────────────────────────────────────


class DocumentRepository:
    """CRUD for documents (Agent.md §12C)."""

    def create(
        self,
        source_name: str,
        source_path: str,
        source_hash: str,
        mime_type: str,
        size_bytes: int,
    ) -> Document:
        doc_id = str(uuid.uuid4())
        now = _now()
        db = get_db()
        db.execute(
            "INSERT INTO documents (id, source_name, source_path, source_hash, mime_type, "
            "size_bytes, created_at, updated_at, chunk_count, indexed) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0)",
            (doc_id, source_name, source_path, source_hash, mime_type, size_bytes, now, now),
        )
        db.commit()
        return Document(
            id=doc_id,
            source_name=source_name,
            source_path=source_path,
            source_hash=source_hash,
            mime_type=mime_type,
            size_bytes=size_bytes,
            created_at=now,
            updated_at=now,
        )

    def get(self, doc_id: str) -> Document | None:
        row = get_db().fetchone("SELECT * FROM documents WHERE id = ?", (doc_id,))
        if row is None:
            return None
        return self._row_to_document(row)

    def find_by_hash(self, source_hash: str) -> Document | None:
        row = get_db().fetchone(
            "SELECT * FROM documents WHERE source_hash = ?", (source_hash,)
        )
        if row is None:
            return None
        return self._row_to_document(row)

    def list_all(self, limit: int = 100) -> list[Document]:
        rows = get_db().fetchall(
            "SELECT * FROM documents ORDER BY updated_at DESC LIMIT ?", (limit,)
        )
        return [self._row_to_document(r) for r in rows]

    def update_indexed(self, doc_id: str, chunk_count: int, indexed: bool) -> bool:
        result = get_db().execute(
            "UPDATE documents SET chunk_count = ?, indexed = ?, updated_at = ? WHERE id = ?",
            (chunk_count, 1 if indexed else 0, _now(), doc_id),
        )
        get_db().commit()
        return result.rowcount > 0

    def delete(self, doc_id: str) -> bool:
        get_db().execute(
            "DELETE FROM document_chunks WHERE document_id = ?", (doc_id,)
        )
        result = get_db().execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        get_db().commit()
        return result.rowcount > 0

    def delete_all(self) -> int:
        get_db().execute("DELETE FROM document_chunks")
        result = get_db().execute("DELETE FROM documents")
        count = result.rowcount
        get_db().commit()
        return count

    def _row_to_document(self, row: Any) -> Document:
        return Document(
            id=row["id"],
            source_name=row["source_name"],
            source_path=row["source_path"],
            source_hash=row["source_hash"],
            mime_type=row["mime_type"],
            size_bytes=row["size_bytes"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            chunk_count=row["chunk_count"],
            indexed=bool(row["indexed"]),
        )


# ── Document chunk repository ────────────────────────────────────────


class DocumentChunkRepository:
    """CRUD for document chunks with embeddings."""

    def add(self, chunk: DocumentChunk) -> None:
        db = get_db()
        db.execute(
            "INSERT INTO document_chunks (id, document_id, chunk_index, text, embedding, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                chunk.id,
                chunk.document_id,
                chunk.chunk_index,
                chunk.text,
                json.dumps(chunk.embedding) if chunk.embedding is not None else None,
                json.dumps(chunk.metadata),
            ),
        )

    def add_many(self, chunks: list[DocumentChunk]) -> None:
        db = get_db()
        db.executemany(
            "INSERT INTO document_chunks (id, document_id, chunk_index, text, embedding, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    c.id,
                    c.document_id,
                    c.chunk_index,
                    c.text,
                    json.dumps(c.embedding) if c.embedding is not None else None,
                    json.dumps(c.metadata),
                )
                for c in chunks
            ],
        )
        db.commit()

    def list_for_document(self, document_id: str) -> list[DocumentChunk]:
        rows = get_db().fetchall(
            "SELECT * FROM document_chunks WHERE document_id = ? "
            "ORDER BY chunk_index",
            (document_id,),
        )
        return [self._row_to_chunk(r) for r in rows]

    def search_by_embedding(
        self,
        query_embedding: list[float],
        limit: int = 10,
        min_score: float = 0.0,
    ) -> list[tuple[DocumentChunk, float]]:
        """Cosine similarity search over document chunks.

        Returns (chunk, score) pairs sorted by score descending.
        """
        rows = get_db().fetchall(
            "SELECT * FROM document_chunks WHERE embedding IS NOT NULL"
        )
        results: list[tuple[DocumentChunk, float]] = []
        for row in rows:
            try:
                emb = json.loads(row["embedding"] or "[]")
            except (json.JSONDecodeError, TypeError):
                continue
            if not emb or len(emb) != len(query_embedding):
                continue
            score = _cosine_similarity(query_embedding, emb)
            if score < min_score:
                continue
            results.append((self._row_to_chunk(row), score))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    def delete_for_document(self, document_id: str) -> int:
        result = get_db().execute(
            "DELETE FROM document_chunks WHERE document_id = ?", (document_id,)
        )
        get_db().commit()
        return result.rowcount

    def _row_to_chunk(self, row: Any) -> DocumentChunk:
        embedding = None
        if row["embedding"] is not None:
            try:
                embedding = json.loads(row["embedding"])
            except (json.JSONDecodeError, TypeError):
                embedding = None
        return DocumentChunk(
            id=row["id"],
            document_id=row["document_id"],
            chunk_index=row["chunk_index"],
            text=row["text"],
            embedding=embedding,
            metadata=json.loads(row["metadata"] or "{}"),
        )


# ── Utility ──────────────────────────────────────────────────────────


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(dot) / float(norm_a * norm_b)


def sha256_file(path: str) -> str:
    """Return SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()
