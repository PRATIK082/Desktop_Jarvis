"""Scheduler (reminders, timers, notifications) — Agent.md §13.

Public API:
    SchedulerService — create/list/edit/pause/resume/cancel reminders &
    timers, tick loop, missed handling, factory reset.
    Reminder / Timer / ScheduleEntry — data models.
    SCHEDULED_ACTION_ALLOWLIST — safe scheduled-action types.
    scheduler — module-level singleton.
"""

from jarvis.scheduler.database import close_db, get_db
from jarvis.scheduler.models import (
    SCHEDULED_ACTION_ALLOWLIST,
    Reminder,
    ScheduleEntry,
    Timer,
)
from jarvis.scheduler.service import SchedulerService, scheduler

__all__ = [
    "Reminder",
    "SCHEDULED_ACTION_ALLOWLIST",
    "ScheduleEntry",
    "SchedulerService",
    "Timer",
    "close_db",
    "get_db",
    "scheduler",
]
