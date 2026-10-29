"""Engine abstraction (clean-room design).

An *engine* is one named triple — hearing (STT) + thinking (LLM) + speaking
(TTS) — plus a capability declaration. The rest of the sidecar (avatar/HUD
state, tool dispatcher, memory, confirmations) talks to the active engine
through this module and never imports a provider implementation directly.

Rules enforced here:
- Provider implementations are imported lazily, on first selection — never
  at sidecar startup. Selecting an engine is a cached-settings lookup.
- The local engine (on-device STT + Ollama + on-device/system TTS) is the
  default and has zero extra dependencies beyond what the sidecar already
  imports.
- A cloud realtime engine exists only as a *disabled adapter*: selecting it
  without an explicit operator-provided key raises, and no network call is
  ever made on its behalf until then.
- Every engine declares what it can do (vision, barge-in, tool budgets) so
  callers degrade honestly instead of narrating actions that never happened.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

EngineId = Literal["local", "cloud"]

# Capability flags an engine reports about itself. Callers use these to
# decide what to offer (e.g. never offer screen-vision tools to a text-only
# engine) and what to tell the user when something is unavailable.
CAP_VISION = "vision"
CAP_BARGE_IN = "barge_in"
CAP_SERVER_TURN_DETECTION = "server_turn_detection"
CAP_SESSION_RESUMPTION = "session_resumption"


@dataclass(frozen=True)
class EngineDescriptor:
    """Static, import-free description of one engine option."""

    id: EngineId
    label: str
    hearing: str  # e.g. "on-device whisper" / "cloud realtime session"
    thinking: str  # e.g. "ollama (/v1/chat/completions)" / "cloud live model"
    speaking: str  # e.g. "on-device neural voice" / "cloud streamed voice"
    capabilities: frozenset[str] = frozenset()
    max_tool_calls_per_turn: int = 3
    tool_payload_budget_chars: int | None = None  # None = no budget (full tools)
    requires_api_key: bool = False
    offline_capable: bool = True


LOCAL_ENGINE = EngineDescriptor(
    id="local",
    label="On-device (Ollama)",
    hearing="on-device speech recognition",
    thinking="local chat-completions endpoint (Ollama / LM Studio / llama.cpp)",
    speaking="on-device neural voice, system voice fallback",
    capabilities=frozenset(),
    max_tool_calls_per_turn=3,
    tool_payload_budget_chars=12_000,
    requires_api_key=False,
    offline_capable=True,
)

CLOUD_ENGINE = EngineDescriptor(
    id="cloud",
    label="Cloud realtime (opt-in)",
    hearing="cloud realtime session",
    thinking="cloud live model",
    speaking="cloud streamed voice",
    capabilities=frozenset({CAP_BARGE_IN, CAP_SERVER_TURN_DETECTION, CAP_SESSION_RESUMPTION}),
    max_tool_calls_per_turn=3,
    tool_payload_budget_chars=None,
    requires_api_key=True,
    offline_capable=False,
)

_ENGINES: dict[str, EngineDescriptor] = {
    LOCAL_ENGINE.id: LOCAL_ENGINE,
    CLOUD_ENGINE.id: CLOUD_ENGINE,
}


class EngineNotAvailableError(RuntimeError):
    """Raised when an engine is selected but its requirements are unmet."""

    def __init__(self, engine_id: str, reason: str) -> None:
        super().__init__(f"engine '{engine_id}' unavailable: {reason}")
        self.engine_id = engine_id
        self.reason = reason


@dataclass
class EngineRegistry:
    """Selects and tracks the active engine. No provider imports here."""

    _active_id: EngineId = "local"
    _api_key_present: bool = False

    def list(self) -> list[EngineDescriptor]:
        return [LOCAL_ENGINE, CLOUD_ENGINE]

    def active(self) -> EngineDescriptor:
        return _ENGINES[self._active_id]

    def select(self, engine_id: str, api_key_present: bool = False) -> EngineDescriptor:
        """Select an engine. Cloud requires an operator-provided key flag."""
        if engine_id not in _ENGINES:
            raise EngineNotAvailableError(engine_id, "unknown engine")
        descriptor = _ENGINES[engine_id]
        if descriptor.requires_api_key and not api_key_present:
            raise EngineNotAvailableError(
                engine_id, "cloud engine is disabled until the operator provides an API key"
            )
        self._active_id = engine_id  # type: ignore[assignment]
        self._api_key_present = api_key_present
        return descriptor

    def describe_limits(self) -> dict[str, Any]:
        """Human/plain facts about the active engine for status display."""
        active = self.active()
        return {
            "engine": active.id,
            "label": active.label,
            "offline_capable": active.offline_capable,
            "capabilities": sorted(active.capabilities),
            "missing": [
                cap
                for cap in (CAP_VISION, CAP_BARGE_IN, CAP_SERVER_TURN_DETECTION)
                if cap not in active.capabilities
            ],
        }


# Module-level singleton; selection is a sub-millisecond cached lookup.
registry = EngineRegistry()


def get_engine_status() -> dict[str, Any]:
    """Status snapshot for /health and the HUD (no secrets, no imports)."""
    return {
        "active": registry.active().id,
        "available": [e.id for e in registry.list()],
        "limits": registry.describe_limits(),
    }
