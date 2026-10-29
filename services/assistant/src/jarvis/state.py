"""Assistant explicit state machine (Agent.md §6).

Legal transitions are defined in LEGAL_TRANSITIONS. Invalid transitions are
rejected, produce a structured error, are logged without secrets, and recover
to a safe state (idle or error).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

# Required states (Agent.md §6)
BOOTING = "booting"
CHECKING_DEPENDENCIES = "checking_dependencies"
IDLE = "idle"
WAKE_WORD_LISTENING = "wake_word_listening"
RECORDING = "recording"
TRANSCRIBING = "transcribing"
THINKING = "thinking"
PROPOSING_ACTION = "proposing_action"
AWAITING_APPROVAL = "awaiting_approval"
EXECUTING = "executing"
SPEAKING = "speaking"
CANCELLING = "cancelling"
OFFLINE = "offline"
DEGRADED = "degraded"
ERROR = "error"

ALL_STATES: Final[frozenset[str]] = frozenset(
    {
        BOOTING,
        CHECKING_DEPENDENCIES,
        IDLE,
        WAKE_WORD_LISTENING,
        RECORDING,
        TRANSCRIBING,
        THINKING,
        PROPOSING_ACTION,
        AWAITING_APPROVAL,
        EXECUTING,
        SPEAKING,
        CANCELLING,
        OFFLINE,
        DEGRADED,
        ERROR,
    }
)

# Legal transitions: from -> set of allowed to states.
LEGAL_TRANSITIONS: Final[dict[str, set[str]]] = {
    BOOTING: {CHECKING_DEPENDENCIES, ERROR, OFFLINE},
    CHECKING_DEPENDENCIES: {IDLE, DEGRADED, ERROR, OFFLINE},
    IDLE: {
        WAKE_WORD_LISTENING,
        RECORDING,
        THINKING,
        OFFLINE,
        ERROR,
        DEGRADED,
    },
    WAKE_WORD_LISTENING: {IDLE, RECORDING, OFFLINE, ERROR, DEGRADED},
    RECORDING: {TRANSCRIBING, IDLE, CANCELLING, ERROR, DEGRADED},
    TRANSCRIBING: {THINKING, IDLE, CANCELLING, ERROR, DEGRADED},
    THINKING: {
        PROPOSING_ACTION,
        SPEAKING,
        IDLE,
        CANCELLING,
        ERROR,
        DEGRADED,
    },
    PROPOSING_ACTION: {
        AWAITING_APPROVAL,
        THINKING,
        IDLE,
        CANCELLING,
        ERROR,
        DEGRADED,
    },
    AWAITING_APPROVAL: {
        EXECUTING,
        THINKING,
        IDLE,
        CANCELLING,
        ERROR,
        DEGRADED,
    },
    EXECUTING: {
        SPEAKING,
        THINKING,
        IDLE,
        CANCELLING,
        ERROR,
        DEGRADED,
    },
    SPEAKING: {IDLE, CANCELLING, ERROR, DEGRADED},
    CANCELLING: {IDLE, ERROR, DEGRADED},
    OFFLINE: {IDLE, ERROR},
    DEGRADED: {IDLE, ERROR, OFFLINE},
    ERROR: {IDLE, OFFLINE, DEGRADED},
}


@dataclass(frozen=True)
class TransitionResult:
    ok: bool
    from_state: str
    to_state: str
    error_code: str | None = None
    message: str | None = None


class StateMachine:
    """Explicit assistant state machine with legal-transition enforcement."""

    def __init__(self, initial_state: str = BOOTING) -> None:
        if initial_state not in ALL_STATES:
            message = f"unknown initial state: {initial_state}"
            raise ValueError(message)
        self._state: str = initial_state

    @property
    def state(self) -> str:
        return self._state

    def can_transition(self, to_state: str) -> bool:
        if to_state not in ALL_STATES:
            return False
        return to_state in LEGAL_TRANSITIONS.get(self._state, frozenset())

    def transition(self, to_state: str) -> TransitionResult:
        from_state = self._state
        if to_state not in ALL_STATES:
            return TransitionResult(
                ok=False,
                from_state=from_state,
                to_state=to_state,
                error_code="unknown_state",
                message=f"unknown target state: {to_state}",
            )
        allowed: set[str] = LEGAL_TRANSITIONS.get(from_state, set())
        if to_state not in allowed:
            return TransitionResult(
                ok=False,
                from_state=from_state,
                to_state=to_state,
                error_code="illegal_transition",
                message=(
                    f"illegal transition from {from_state} to {to_state}; "
                    f"allowed: {sorted(allowed)}"
                ),
            )
        self._state = to_state
        return TransitionResult(ok=True, from_state=from_state, to_state=to_state)

    def reset(self) -> None:
        self._state = IDLE
