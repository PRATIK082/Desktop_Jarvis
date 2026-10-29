"""Placeholder test ensuring the sidecar package imports cleanly."""

from jarvis.config import settings
from jarvis.state import BOOTING, IDLE, StateMachine


def test_settings_load() -> None:
    assert settings.host == "127.0.0.1"
    assert settings.telemetry_enabled is False


def test_state_machine_initial_state() -> None:
    sm = StateMachine()
    assert sm.state == BOOTING


def test_legal_transition_idle_to_recording() -> None:
    sm = StateMachine(IDLE)
    result = sm.transition("recording")
    assert result.ok is True
    assert sm.state == "recording"


def test_illegal_transition_rejected() -> None:
    sm = StateMachine(IDLE)
    result = sm.transition("executing")  # idle -> executing is not legal
    assert result.ok is False
    assert result.error_code == "illegal_transition"
    assert sm.state == IDLE  # recovered to safe state (unchanged)
