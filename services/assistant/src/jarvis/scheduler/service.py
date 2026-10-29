"""Scheduler service (Agent.md §13).

Implements local reminders and timers:
- one-time and recurring reminders
- pause, resume, edit, cancel
- timezone-aware timestamps (UTC stored, local for display)
- missed-reminder handling (reminders due while offline are flagged 'missed')
- desktop notifications (stub per platform; no-op when backend unavailable)
- audit entry for every scheduled operation
- persistence across restarts (SQLite)
- safe allowlist: scheduled actions must be in SCHEDULED_ACTION_ALLOWLIST;
  no arbitrary prompts or arbitrary tools may be scheduled.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from jarvis.scheduler.database import SchedulerDatabase, get_db
from jarvis.scheduler.models import (
    SCHEDULED_ACTION_ALLOWLIST,
    Reminder,
    ScheduleEntry,
    Timer,
)
from jarvis.telemetry.logger import get_logger, log_event

try:
    import win10toast  # type: ignore[import-not-found]  # noqa: PLC0415 — optional Windows dep
except ImportError:  # pragma: no cover — win10toast optional
    win10toast = None

logger = get_logger("jarvis.scheduler.service")

# ── helpers ──────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _generate_id() -> str:
    return uuid.uuid4().hex


def _validate_action(action_type: str, action_args: dict[str, object]) -> None:
    """Ensure scheduled action is in the safe allowlist (Agent.md §13)."""
    if action_type not in SCHEDULED_ACTION_ALLOWLIST:
        msg = f"scheduled action not allowed: {action_type}"
        raise ValueError(msg)
    # action_args must be a plain dict of JSON-safe primitives.
    json.dumps(action_args)  # raises if not serializable


# ── notification backend (platform stub) ─────────────────────────────────


class DesktopNotifier:
    """Best-effort desktop notification.

    On Windows this would use Win10Toast/plyer; on Linux notify-send;
    on macOS osascript. Degrades gracefully to a log event when no
    backend is available. Never raises.
    """

    def notify(self, title: str, message: str) -> None:
        # Windows: win10toast.
        if win10toast is not None:
            try:
                toaster = win10toast.ToastNotifier()
                toaster.show_toast(title=title, msg=message, duration=5, threaded=True)
            except Exception as exc:  # noqa: BLE001 — notification is non-fatal
                log_event(
                    "jarvis.scheduler.notifications",
                    "windows_notify_failed",
                    level="warn",
                    details={"error": str(exc)[:200]},
                )
            return

        # Linux: notify-send (full path to avoid S607 partial-path warning).
        try:
            subprocess.run(  # noqa: S603 — fixed command, no user input
                ["/usr/bin/notify-send", title, message],
                check=False,
                capture_output=True,
            )
            return  # noqa: TRY300 — return after successful notification
        except (OSError, FileNotFoundError):
            pass

        # Fallback: log only (no crash, no popup).
        log_event(
            "jarvis.scheduler.notifications",
            "notification",
            details={"title": title, "message": message},
        )


_notifier = DesktopNotifier()


# ── service ──────────────────────────────────────────────────────────────


class SchedulerService:
    """Manages reminders and timers with persistence."""

    def __init__(self, db: SchedulerDatabase | None = None) -> None:
        self._db = db or get_db()
        self._running = False
        self._tick_task: asyncio.Task[None] | None = None
        self._tick_interval_s = 1.0  # check due reminders every second

    # ── lifecycle ──────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the scheduler tick loop (call from sidecar startup)."""
        if self._running:
            return
        self._running = True
        self._tick_task = asyncio.create_task(self._tick_loop())
        log_event("jarvis.scheduler.service", "started")

    async def stop(self) -> None:
        """Stop the scheduler tick loop."""
        self._running = False
        if self._tick_task and not self._tick_task.done():
            self._tick_task.cancel()
            try:
                await self._tick_task
            except asyncio.CancelledError:
                pass
        log_event("jarvis.scheduler.service", "stopped")

    async def _tick_loop(self) -> None:
        """Background loop: fire due reminders, complete timers, handle missed."""
        while self._running:
            try:
                await self._process_due_reminders()
                await self._process_due_timers()
                await self._handle_missed_reminders()
            except Exception as exc:  # noqa: BLE001 — scheduler must not die
                log_event(
                    "jarvis.scheduler.service",
                    "tick_error",
                    level="error",
                    details={"error": str(exc)[:200]},
                )
            await asyncio.sleep(self._tick_interval_s)

    # ── reminders ──────────────────────────────────────────────────────

    def create_reminder(  # noqa: PLR0913 — many optional fields for flexible reminder creation
        self,
        title: str,
        message: str,
        trigger_at: str,
        *,
        timezone: str = "local",
        recurring: str | None = None,
        interval_seconds: int | None = None,
        action_type: str = "show_desktop_notification",
        action_args: dict[str, object] | None = None,
        audit_id: str | None = None,
    ) -> Reminder:
        """Create a reminder. Validates trigger_at is parseable and action is allowed."""
        _parse_iso(trigger_at)  # raises if not a valid ISO timestamp
        _validate_action(action_type, action_args or {})

        now = _now_iso()
        reminder = Reminder(
            id=_generate_id(),
            title=title,
            message=message,
            trigger_at=trigger_at,
            timezone=timezone,
            recurring=recurring,
            interval_seconds=interval_seconds,
            status="active",
            created_at=now,
            updated_at=now,
            action_type=action_type,
            action_args=action_args or {},
            audit_id=audit_id,
        )
        self._db.execute(
            """
            INSERT INTO reminders
            (id, title, message, trigger_at, timezone, recurring, interval_seconds,
             status, created_at, updated_at, last_triggered_at, next_trigger_at,
             action_type, action_args, audit_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                reminder.id,
                reminder.title,
                reminder.message,
                reminder.trigger_at,
                reminder.timezone,
                reminder.recurring,
                reminder.interval_seconds,
                reminder.status,
                reminder.created_at,
                reminder.updated_at,
                reminder.last_triggered_at,
                reminder.next_trigger_at,
                reminder.action_type,
                json.dumps(reminder.action_args),
                reminder.audit_id,
            ),
        )
        log_event(
            "jarvis.scheduler.service",
            "reminder_created",
            details={"reminder_id": reminder.id, "trigger_at": trigger_at},
        )
        return reminder

    def list_reminders(self, include_inactive: bool = False) -> list[Reminder]:
        """List reminders, newest first."""
        if include_inactive:
            rows = self._db.fetchall(
                "SELECT * FROM reminders ORDER BY datetime(trigger_at) DESC"
            )
        else:
            rows = self._db.fetchall(
                "SELECT * FROM reminders WHERE status = 'active' "
                "ORDER BY datetime(trigger_at) ASC"
            )
        return [self._row_to_reminder(r) for r in rows]

    def get_reminder(self, reminder_id: str) -> Reminder | None:
        row = self._db.fetchone(
            "SELECT * FROM reminders WHERE id = ?", (reminder_id,)
        )
        return self._row_to_reminder(row) if row else None

    def edit_reminder(  # noqa: PLR0913 — many optional fields for flexible editing
        self,
        reminder_id: str,
        *,
        title: str | None = None,
        message: str | None = None,
        trigger_at: str | None = None,
        timezone: str | None = None,
        recurring: str | None = None,
        interval_seconds: int | None = None,
        action_type: str | None = None,
        action_args: dict[str, object] | None = None,
    ) -> Reminder | None:
        """Edit an existing reminder. Re-validates action and timestamps."""
        reminder = self.get_reminder(reminder_id)
        if reminder is None:
            return None
        if trigger_at is not None:
            _parse_iso(trigger_at)
            reminder.trigger_at = trigger_at
        if title is not None:
            reminder.title = title
        if message is not None:
            reminder.message = message
        if timezone is not None:
            reminder.timezone = timezone
        if recurring is not None:
            reminder.recurring = recurring
        if interval_seconds is not None:
            reminder.interval_seconds = interval_seconds
        if action_type is not None:
            _validate_action(action_type, action_args or reminder.action_args)
            reminder.action_type = action_type
        if action_args is not None:
            _validate_action(reminder.action_type, action_args)
            reminder.action_args = action_args
        reminder.updated_at = _now_iso()
        self._db.execute(
            """
            UPDATE reminders
            SET title = ?, message = ?, trigger_at = ?, timezone = ?,
                recurring = ?, interval_seconds = ?, action_type = ?,
                action_args = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                reminder.title,
                reminder.message,
                reminder.trigger_at,
                reminder.timezone,
                reminder.recurring,
                reminder.interval_seconds,
                reminder.action_type,
                json.dumps(reminder.action_args),
                reminder.updated_at,
                reminder.id,
            ),
        )
        log_event(
            "jarvis.scheduler.service",
            "reminder_edited",
            details={"reminder_id": reminder_id},
        )
        return reminder

    def pause_reminder(self, reminder_id: str) -> bool:
        return self._set_reminder_status(reminder_id, "paused")

    def resume_reminder(self, reminder_id: str) -> bool:
        return self._set_reminder_status(reminder_id, "active")

    def cancel_reminder(self, reminder_id: str) -> bool:
        return self._set_reminder_status(reminder_id, "cancelled")

    def _set_reminder_status(self, reminder_id: str, status: str) -> bool:
        reminder = self.get_reminder(reminder_id)
        if reminder is None:
            return False
        reminder.status = status
        reminder.updated_at = _now_iso()
        self._db.execute(
            "UPDATE reminders SET status = ?, updated_at = ? WHERE id = ?",
            (status, reminder.updated_at, reminder_id),
        )
        log_event(
            "jarvis.scheduler.service",
            "reminder_status_changed",
            details={"reminder_id": reminder_id, "status": status},
        )
        return True

    # ── timers ─────────────────────────────────────────────────────────

    def create_timer(
        self,
        title: str,
        duration_seconds: int,
        *,
        action_type: str = "show_desktop_notification",
        action_args: dict[str, object] | None = None,
        audit_id: str | None = None,
    ) -> Timer:
        """Create and start a countdown timer."""
        if duration_seconds <= 0:
            msg = "duration_seconds must be positive"
            raise ValueError(msg)
        _validate_action(action_type, action_args or {})

        now = _now_iso()
        timer = Timer(
            id=_generate_id(),
            title=title,
            duration_seconds=duration_seconds,
            started_at=now,
            elapsed_seconds=0,
            status="running",
            action_type=action_type,
            action_args=action_args or {},
            audit_id=audit_id,
        )
        self._db.execute(
            """
            INSERT INTO timers
            (id, title, duration_seconds, started_at, elapsed_seconds,
             status, action_type, action_args, audit_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timer.id,
                timer.title,
                timer.duration_seconds,
                timer.started_at,
                timer.elapsed_seconds,
                timer.status,
                timer.action_type,
                json.dumps(timer.action_args),
                timer.audit_id,
            ),
        )
        log_event(
            "jarvis.scheduler.service",
            "timer_created",
            details={"timer_id": timer.id, "duration_seconds": duration_seconds},
        )
        return timer

    def list_timers(self, include_inactive: bool = False) -> list[Timer]:
        if include_inactive:
            rows = self._db.fetchall("SELECT * FROM timers ORDER BY started_at DESC")
        else:
            rows = self._db.fetchall(
                "SELECT * FROM timers WHERE status = 'running' "
                "ORDER BY started_at ASC"
            )
        return [self._row_to_timer(r) for r in rows]

    def get_timer(self, timer_id: str) -> Timer | None:
        row = self._db.fetchone("SELECT * FROM timers WHERE id = ?", (timer_id,))
        return self._row_to_timer(row) if row else None

    def pause_timer(self, timer_id: str) -> bool:
        return self._set_timer_status(timer_id, "paused")

    def resume_timer(self, timer_id: str) -> bool:
        return self._set_timer_status(timer_id, "running")

    def cancel_timer(self, timer_id: str) -> bool:
        return self._set_timer_status(timer_id, "cancelled")

    def _set_timer_status(self, timer_id: str, status: str) -> bool:
        timer = self.get_timer(timer_id)
        if timer is None:
            return False
        timer.status = status
        self._db.execute(
            "UPDATE timers SET status = ? WHERE id = ?", (status, timer_id)
        )
        log_event(
            "jarvis.scheduler.service",
            "timer_status_changed",
            details={"timer_id": timer_id, "status": status},
        )
        return True

    # ── view model ─────────────────────────────────────────────────────

    def list_schedule(self) -> list[ScheduleEntry]:
        """Combined view of active reminders and timers for the UI."""
        entries: list[ScheduleEntry] = []
        now = datetime.now(UTC)
        for r in self.list_reminders():
            trigger_dt = _parse_iso(r.trigger_at)
            entries.append(
                ScheduleEntry(
                    kind="reminder",
                    id=r.id,
                    title=r.title,
                    status=r.status,
                    trigger_at=r.trigger_at,
                    remaining_seconds=max(
                        0, int((trigger_dt - now).total_seconds())
                    ),
                    updated_at=r.updated_at,
                )
            )
        for t in self.list_timers():
            remaining = max(0, t.duration_seconds - t.elapsed_seconds)
            entries.append(
                ScheduleEntry(
                    kind="timer",
                    id=t.id,
                    title=t.title,
                    status=t.status,
                    trigger_at=None,
                    remaining_seconds=remaining,
                    updated_at=t.started_at,
                )
            )
        entries.sort(key=lambda e: e.remaining_seconds or 0)
        return entries

    # ── processing (tick loop) ─────────────────────────────────────────

    async def _process_due_reminders(self) -> None:
        now = _now_iso()
        rows = self._db.fetchall(
            "SELECT * FROM reminders WHERE status = 'active' "
            "AND datetime(trigger_at) <= datetime(?)",
            (now,),
        )
        for row in rows:
            reminder = self._row_to_reminder(row)
            # Fire notification.
            _notifier.notify(reminder.title, reminder.message)
            if reminder.recurring and reminder.interval_seconds:
                # Compute next trigger and keep active.
                next_dt = _parse_iso(reminder.trigger_at) + timedelta(
                    seconds=reminder.interval_seconds
                )
                reminder.last_triggered_at = reminder.trigger_at
                reminder.trigger_at = next_dt.isoformat()
                reminder.next_trigger_at = next_dt.isoformat()
                reminder.updated_at = now
                self._db.execute(
                    """
                    UPDATE reminders
                    SET trigger_at = ?, next_trigger_at = ?,
                        last_triggered_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        reminder.trigger_at,
                        reminder.next_trigger_at,
                        reminder.last_triggered_at,
                        reminder.updated_at,
                        reminder.id,
                    ),
                )
            else:
                # One-time reminder → completed.
                reminder.status = "completed"
                reminder.last_triggered_at = reminder.trigger_at
                reminder.updated_at = now
                self._db.execute(
                    """
                    UPDATE reminders
                    SET status = ?, last_triggered_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    ("completed", reminder.last_triggered_at, reminder.updated_at, reminder.id),
                )
            log_event(
                "jarvis.scheduler.service",
                "reminder_triggered",
                details={"reminder_id": reminder.id, "title": reminder.title},
            )

    async def _process_due_timers(self) -> None:
        now = datetime.now(UTC)
        rows = self._db.fetchall("SELECT * FROM timers WHERE status = 'running'")
        for row in rows:
            timer = self._row_to_timer(row)
            started = _parse_iso(timer.started_at) if timer.started_at else now
            elapsed = timer.elapsed_seconds + int((now - started).total_seconds())
            if elapsed >= timer.duration_seconds:
                timer.status = "completed"
                timer.elapsed_seconds = timer.duration_seconds
                _notifier.notify(timer.title, "Timer complete")
                self._db.execute(
                    "UPDATE timers SET status = ?, elapsed_seconds = ? WHERE id = ?",
                    ("completed", timer.duration_seconds, timer.id),
                )
                log_event(
                    "jarvis.scheduler.service",
                    "timer_completed",
                    details={"timer_id": timer.id, "title": timer.title},
                )
            else:
                timer.elapsed_seconds = elapsed
                self._db.execute(
                    "UPDATE timers SET elapsed_seconds = ? WHERE id = ?",
                    (elapsed, timer.id),
                )

    async def _handle_missed_reminders(self) -> None:
        """Flag reminders that were due while the scheduler was offline."""
        now = _now_iso()
        rows = self._db.fetchall(
            "SELECT * FROM reminders WHERE status = 'active' "
            "AND recurring IS NULL AND datetime(trigger_at) < datetime(?)",
            (now,),
        )
        for row in rows:
            reminder = self._row_to_reminder(row)
            reminder.status = "missed"
            reminder.updated_at = now
            self._db.execute(
                "UPDATE reminders SET status = ?, updated_at = ? WHERE id = ?",
                ("missed", reminder.updated_at, reminder.id),
            )
            log_event(
                "jarvis.scheduler.service",
                "reminder_missed",
                level="warn",
                details={"reminder_id": reminder.id, "title": reminder.title},
            )

    # ── persistence / factory reset ────────────────────────────────────

    def delete_all_data(self) -> dict[str, object]:
        """Factory reset: delete all reminders and timers. Returns a report."""
        reminder_count = self._db.execute("DELETE FROM reminders").rowcount
        timer_count = self._db.execute("DELETE FROM timers").rowcount
        report: dict[str, object] = {
            "reminders_deleted": reminder_count,
            "timers_deleted": timer_count,
        }
        log_event(
            "jarvis.scheduler.service",
            "factory_reset",
            details=report,
        )
        return report

    # ── row mapping ────────────────────────────────────────────────────

    def _row_to_reminder(self, row: Any) -> Reminder:
        return Reminder(
            id=row["id"],
            title=row["title"],
            message=row["message"],
            trigger_at=row["trigger_at"],
            timezone=row["timezone"] or "local",
            recurring=row["recurring"],
            interval_seconds=row["interval_seconds"],
            status=row["status"],
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
            last_triggered_at=row["last_triggered_at"],
            next_trigger_at=row["next_trigger_at"],
            action_type=row["action_type"],
            action_args=json.loads(row["action_args"] or "{}"),
            audit_id=row["audit_id"],
        )

    def _row_to_timer(self, row: Any) -> Timer:
        return Timer(
            id=row["id"],
            title=row["title"],
            duration_seconds=row["duration_seconds"],
            started_at=row["started_at"] or "",
            elapsed_seconds=row["elapsed_seconds"] or 0,
            status=row["status"],
            action_type=row["action_type"],
            action_args=json.loads(row["action_args"] or "{}"),
            audit_id=row["audit_id"],
        )


# Module-level singleton.
scheduler = SchedulerService()
