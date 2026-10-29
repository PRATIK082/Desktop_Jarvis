"""SQLite memory database with schema migrations (Agent.md §12).

Tables:
- conversations — conversation sessions
- conversation_messages — messages within conversations
- memories — explicit long-term memories
- documents — user-selected documents for RAG
- document_chunks — document chunks with embeddings
- schema_migrations — migration tracking
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from jarvis.config import settings
from jarvis.telemetry.logger import get_logger, log_event

logger = get_logger("jarvis.memory.database")

# Schema version. Increment when adding a new migration.
SCHEMA_VERSION = 1

MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            pinned INTEGER NOT NULL DEFAULT 0,
            archived INTEGER NOT NULL DEFAULT 0,
            message_count INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS conversation_messages (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            metadata TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS memories (
            id TEXT PRIMARY KEY,
            text TEXT NOT NULL,
            normalized_text TEXT NOT NULL,
            tags TEXT NOT NULL DEFAULT '[]',
            source_conversation TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 1.0,
            sensitivity TEXT NOT NULL DEFAULT 'normal',
            expiration TEXT,
            pinned INTEGER NOT NULL DEFAULT 0,
            embedding TEXT
        );

        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            source_name TEXT NOT NULL,
            source_path TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            mime_type TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            chunk_count INTEGER NOT NULL DEFAULT 0,
            indexed INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS document_chunks (
            id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            text TEXT NOT NULL,
            embedding TEXT,
            metadata TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_conversation_messages_conv
            ON conversation_messages(conversation_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_memories_tags
            ON memories(tags);
        CREATE INDEX IF NOT EXISTS idx_document_chunks_doc
            ON document_chunks(document_id, chunk_index);
        """,
    ),
]


class MemoryDatabase:
    """SQLite database wrapper with migrations and connection management."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = Path(db_path or settings.memory_db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._migrate()

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._conn = conn
        return self._conn

    def _migrate(self) -> None:
        """Run pending schema migrations."""
        conn = self._connect()
        # Ensure migrations table exists.
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        applied = {
            row["version"]
            for row in conn.execute("SELECT version FROM schema_migrations")
        }
        for version, sql in MIGRATIONS:
            if version in applied:
                continue
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (version, datetime_now_iso()),
            )
            applied.add(version)
        conn.commit()
        log_event(
            "jarvis.memory.database",
            "migration_complete",
            details={"schema_version": SCHEMA_VERSION, "db_path": str(self.db_path)},
        )

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        return self._connect().execute(sql, params)

    def executemany(
        self, sql: str, params: list[tuple[Any, ...]]
    ) -> sqlite3.Cursor:
        return self._connect().executemany(sql, params)

    def commit(self) -> None:
        self._connect().commit()

    def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        return self._connect().execute(sql, params).fetchall()

    def fetchone(
        self, sql: str, params: tuple[Any, ...] = ()
    ) -> sqlite3.Row | None:
        return cast(sqlite3.Row | None, self._connect().execute(sql, params).fetchone())


def datetime_now_iso() -> str:
    return datetime.now(UTC).isoformat()


# Module-level singleton.
_db: MemoryDatabase | None = None


def get_db() -> MemoryDatabase:  # noqa: PLW0603 — module-level singleton DB
    global _db  # noqa: PLW0603
    if _db is None:
        _db = MemoryDatabase()
    return _db


def close_db() -> None:  # noqa: PLW0603 — module-level singleton DB
    global _db  # noqa: PLW0603
    if _db is not None:
        _db.close()
        _db = None
