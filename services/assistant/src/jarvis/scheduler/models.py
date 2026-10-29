"""Scheduler data models (Agent.md §13).

Reminders and timers are scheduled actions selected from an explicit safe
allowlist. All timestamps are stored as UTC ISO-8601 strings; timezone
conversion is applied at display/trigger time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

# Safe allowlist of scheduled action types (Agent.md §13).
# Scheduled jobs may NOT run arbitrary prompts or arbitrary tools.
SCHEDULED_ACTION_ALLOWLIST: Final[frozenset[str]] = frozenset(
    {
        "show_desktop_notification",
    }
)


@dataclass
class Reminder:
    """A scheduled reminder (one-time or recurring).

    Fields:
        id: stable identifier.
        title: human-readable title.
        message: reminder body text.
        trigger_at: UTC ISO-8601 timestamp when the reminder is due.
        timezone: IANA timezone name for display/recurrence computation.
        recurring: cron-like or interval recurrence spec (None = one-time).
        interval_seconds: for interval-based recurrence (e.g. every 3600s).
        status: active | paused | cancelled | completed | missed.
        created_at: UTC ISO-8601.
        updated_at: UTC ISO-8601.
        last_triggered_at: UTC ISO-8601 of last fire (None if never).
        next_trigger_at: computed next fire time for recurring reminders.
        action_type: must be in SCHEDULED_ACTION_ALLOWLIST.
        action_args: validated action arguments.
        audit_id: link to activity/audit log entry.
    """

    id: str
    title: str
    message: str
    trigger_at: str
    timezone: str = "local"
    recurring: str | None = None
    interval_seconds: int | None = None
    status: str = "active"
    created_at: str = ""
    updated_at: str = ""
    last_triggered_at: str | None = None
    next_trigger_at: str | None = None
    action_type: str = "show_desktop_notification"
    action_args: dict[str, object] = field(default_factory=dict)
    audit_id: str | None = None


@dataclass
class Timer:
    """A countdown timer.

    Fields:
        id: stable identifier.
        title: human-readable title.
        duration_seconds: total timer length.
        started_at: UTC ISO-8601 when started.
        elapsed_seconds: accumulated elapsed time (paused timers).
        status: running | paused | completed | cancelled.
        action_type: must be in SCHEDULED_ACTION_ALLOWLIST.
        action_args: validated action arguments (e.g. notification on complete).
        audit_id: link to activity/audit log entry.
    """

    id: str
    title: str
    duration_seconds: int
    started_at: str = ""
    elapsed_seconds: int = 0
    status: str = "running"
    action_type: str = "show_desktop_notification"
    action_args: dict[str, object] = field(default_factory=dict)
    audit_id: str | None = None


@dataclass
class ScheduleEntry:
    """A view-model entry combining a reminder or timer for UI listing."""

    kind: str  # "reminder" or "timer"
    id: str
    title: str
    status: str
    trigger_at: str | None = None
    remaining_seconds: int | None = None
    updated_at: str = ""
