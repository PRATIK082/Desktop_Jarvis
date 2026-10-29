"""Scheduler tests — no live notifications, no real clock manipulation.

Tests use a temp SQLite DB path and the SchedulerService(db=...) constructor
for injectable persistence. DesktopNotifier degrades gracefully to logging.
"""

from __future__ import annotations

import os
import tempfile
import pytest

from jarvis.scheduler.database import SchedulerDatabase, close_db, get_db
from jarvis.scheduler.models import (
    Reminder,
    SCHEDULED_ACTION_ALLOWLIST,
    ScheduleEntry,
    Timer,
)
from jarvis.scheduler.service import SchedulerService


# ── fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def temp_db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)  # remove so SQLite creates it fresh
    yield path
    if os.path.exists(path):
        os.unlink(path)
    close_db()


@pytest.fixture
def db(temp_db_path):
    return SchedulerDatabase(db_path=temp_db_path)


@pytest.fixture
def service(db):
    return SchedulerService(db=db)


# ── model tests ──────────────────────────────────────────────────────────


def test_reminder_dataclass():
    r = Reminder(
        id="r1",
        title="Take medicine",
        message="Take your daily medication",
        trigger_at="2026-10-28T08:00:00+00:00",
        timezone="America/New_York",
        status="active",
    )
    assert r.id == "r1"
    assert r.title == "Take medicine"
    assert r.action_type == "show_desktop_notification"
    assert r.action_args == {}


def test_timer_dataclass():
    t = Timer(
        id="t1",
        title="Pasta timer",
        duration_seconds=600,
        started_at="2026-10-28T12:00:00+00:00",
        status="running",
    )
    assert t.id == "t1"
    assert t.duration_seconds == 600
    assert t.elapsed_seconds == 0
    assert t.status == "running"


def test_schedule_entry():
    e = ScheduleEntry(
        kind="reminder",
        id="r1",
        title="Test reminder",
        status="active",
        trigger_at="2026-10-28T08:00:00+00:00",
        remaining_seconds=3600,
    )
    assert e.kind == "reminder"
    assert e.remaining_seconds == 3600


def test_action_allowlist_contains_notification():
    assert "show_desktop_notification" in SCHEDULED_ACTION_ALLOWLIST


# ── service tests ────────────────────────────────────────────────────────


def test_create_and_list_reminder(service):
    r = service.create_reminder(
        title="Meeting",
        message="Team standup",
        trigger_at="2026-10-28T09:00:00+00:00",
    )
    assert r.id is not None
    assert r.title == "Meeting"
    assert r.status == "active"

    reminders = service.list_reminders()
    assert len(reminders) == 1
    assert reminders[0].id == r.id


def test_get_reminder(service):
    r = service.create_reminder(
        title="Drink water",
        message="Hydrate",
        trigger_at="2026-10-28T10:00:00+00:00",
    )
    found = service.get_reminder(r.id)
    assert found is not None
    assert found.title == "Drink water"

    assert service.get_reminder("nonexistent") is None


def test_edit_reminder(service):
    r = service.create_reminder(
        title="Old title",
        message="Old message",
        trigger_at="2026-10-28T11:00:00+00:00",
    )
    updated = service.edit_reminder(r.id, title="New title", message="New message")
    assert updated is not None
    assert updated.title == "New title"
    assert updated.message == "New message"
    assert updated.updated_at != r.updated_at

    assert service.edit_reminder("nonexistent", title="x") is None


def test_pause_resume_cancel_reminder(service):
    r = service.create_reminder(
        title="Pause test",
        message="msg",
        trigger_at="2026-10-28T12:00:00+00:00",
    )
    assert service.pause_reminder(r.id) is True
    assert service.get_reminder(r.id).status == "paused"

    assert service.resume_reminder(r.id) is True
    assert service.get_reminder(r.id).status == "active"

    assert service.cancel_reminder(r.id) is True
    assert service.get_reminder(r.id).status == "cancelled"

    assert service.pause_reminder("nonexistent") is False


def test_create_and_list_timer(service):
    t = service.create_timer(title="Pasta", duration_seconds=300)
    assert t.id is not None
    assert t.duration_seconds == 300
    assert t.status == "running"

    timers = service.list_timers()
    assert len(timers) == 1
    assert timers[0].id == t.id


def test_pause_resume_cancel_timer(service):
    t = service.create_timer(title="Timer test", duration_seconds=60)
    assert service.pause_timer(t.id) is True
    assert service.get_timer(t.id).status == "paused"

    assert service.resume_timer(t.id) is True
    assert service.get_timer(t.id).status == "running"

    assert service.cancel_timer(t.id) is True
    assert service.get_timer(t.id).status == "cancelled"

    assert service.pause_timer("nonexistent") is False


def test_delete_all_data(service):
    service.create_reminder(title="R1", message="m", trigger_at="2026-10-28T13:00:00+00:00")
    service.create_timer(title="T1", duration_seconds=30)

    report = service.delete_all_data()
    assert report["reminders_deleted"] == 1
    assert report["timers_deleted"] == 1
    assert service.list_reminders() == []
    assert service.list_timers() == []


def test_list_schedule(service):
    service.create_reminder(title="R1", message="m", trigger_at="2026-10-28T14:00:00+00:00")
    service.create_timer(title="T1", duration_seconds=120)

    entries = service.list_schedule()
    kinds = {e.kind for e in entries}
    assert "reminder" in kinds
    assert "timer" in kinds
    assert all(e.status == "active" or e.status == "running" for e in entries)


def test_validate_action_rejects_disallowed():
    from jarvis.scheduler.service import _validate_action

    # Allowed action should not raise.
    _validate_action("show_desktop_notification", {})

    # Disallowed action should raise.
    with pytest.raises(ValueError):
        _validate_action("arbitrary_shell_command", {})

    # Non-serializable args should raise.
    with pytest.raises((ValueError, TypeError)):
        _validate_action("show_desktop_notification", {"obj": object()})


def test_service_uses_custom_db(db):
    """Verify SchedulerService(db=...) uses the injected database."""
    svc = SchedulerService(db=db)
    r = svc.create_reminder(
        title="Injected DB test",
        message="msg",
        trigger_at="2026-10-28T15:00:00+00:00",
    )
    assert svc.get_reminder(r.id) is not None
    # Verify via direct DB query.
    row = db.fetchone("SELECT * FROM reminders WHERE id = ?", (r.id,))
    assert row is not None
    assert row["title"] == "Injected DB test"
