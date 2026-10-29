"""Scheduler SQLite database (Agent.md §13).

Persistence across restarts via SQLite with WAL mode and foreign keys.
Schema versioned with schema_migrations table. All tables store UTC
ISO-8601 timestamps.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, cast

from jarvis.config import settings
from jarvis.telemetry.logger import get_logger, log_event

logger = get_logger("jarvis.scheduler.database")

SCHEMA_VERSION = 1

MIGRATIONS: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS reminders (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        trigger_at TEXT NOT NULL,
        timezone TEXT NOT NULL DEFAULT 'local',
        recurring TEXT,
        interval_seconds INTEGER,
        status TEXT NOT NULL DEFAULT 'active',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        last_triggered_at TEXT,
        next_trigger_at TEXT,
        action_type TEXT NOT NULL DEFAULT 'show_desktop_notification',
        action_args TEXT NOT NULL DEFAULT '{}',
        audit_id TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS timers (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        duration_seconds INTEGER NOT NULL,
        started_at TEXT NOT NULL DEFAULT '',
        elapsed_seconds INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'running',
        action_type TEXT NOT NULL DEFAULT 'show_desktop_notification',
        action_args TEXT NOT NULL DEFAULT '{}',
        audit_id TEXT
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_reminders_status ON reminders(status);
    CREATE INDEX IF NOT EXISTS idx_reminders_trigger_at ON reminders(trigger_at);
    CREATE INDEX IF NOT EXISTS idx_timers_status ON timers(status);
    """,
]


class SchedulerDatabase:
    """SQLite-backed persistence for reminders and timers."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or settings.scheduler_db_path
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            for migration in MIGRATIONS:
                conn.executescript(migration)
            # Record schema version.
            row = conn.execute(
                "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"
            ).fetchone()
            if row is None or row["version"] < SCHEMA_VERSION:
                conn.execute(
                    "INSERT OR REPLACE INTO schema_migrations (version, applied_at) "
                    "VALUES (?, datetime('now'))",
                    (SCHEMA_VERSION,),
                )
            conn.commit()
            log_event(
                "jarvis.scheduler.database",
                "initialized",
                details={"db_path": self.db_path, "schema_version": SCHEMA_VERSION},
            )
        finally:
            conn.close()

    def connect(self) -> sqlite3.Connection:
        """Return a (short-lived) connection. Caller must close it."""
        return self._connect()

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        conn = self._connect()
        try:
            cur = conn.execute(sql, params)
            conn.commit()
            return cur
        finally:
            conn.close()

    def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        conn = self._connect()
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        conn = self._connect()
        try:
            return cast(
                sqlite3.Row | None, conn.execute(sql, params).fetchone()
            )
        finally:
            conn.close()

    def close(self) -> None:
        """No-op (connections are short-lived). Kept for API symmetry."""


# Module-level singleton.
_db: SchedulerDatabase | None = None


def get_db() -> SchedulerDatabase:
    global _db  # noqa: PLW0603 — module-level singleton DB
    if _db is None:
        _db = SchedulerDatabase()
    return _db


def close_db() -> None:
    global _db  # noqa: PLW0603 — module-level singleton DB
    _db = None
