"""Assistant events (Python mirror of packages/contracts/src/index.ts).

These are the typed events the sidecar emits to the UI via WebSocket during a
turn. They mirror the TypeScript `AssistantEvent` union for IPC contract
parity between the Tauri/Rust boundary and the Python sidecar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal


def _now() -> str:
    return datetime.now(UTC).isoformat()


# State values mirror AssistantState in packages/contracts.
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

ALL_STATES = frozenset(
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

RequestStatus = Literal["approved_once", "remembered", "denied", "cancelled"]
LatencyName = Literal[
    "wake_detection",
    "transcription",
    "first_llm_token",
    "total_llm",
    "first_audio",
    "total_turn",
]


@dataclass
class StateTransitionEvent:
    type: Literal["state_transition"] = "state_transition"
    from_state: str = IDLE
    to_state: str = IDLE
    timestamp: str = field(default_factory=_now)
    request_id: str | None = None
    conversation_id: str | None = None


@dataclass
class AssistantErrorEvent:
    type: Literal["assistant_error"] = "assistant_error"
    code: str = ""
    message: str = ""
    recoverable: bool = True
    retry_available: bool = False
    request_id: str | None = None
    conversation_id: str | None = None


@dataclass
class LatencyMetricEvent:
    type: Literal["latency_metric"] = "latency_metric"
    name: LatencyName = "total_turn"
    duration_ms: float = 0.0
    turn_id: str | None = None


@dataclass
class AudioLevelEvent:
    type: Literal["audio_level"] = "audio_level"
    level: float = 0.0
    device_id: str | None = None


@dataclass
class ToolProposalEvent:
    type: Literal["tool_proposal"] = "tool_proposal"
    tool_id: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    risk_level: int = 0
    reason: str = ""
    expected_effect: str = ""
    request_id: str = ""
    conversation_id: str | None = None


@dataclass
class ToolResultEvent:
    type: Literal["tool_result"] = "tool_result"
    tool_id: str = ""
    success: bool = False
    result: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: float = 0.0
    request_id: str = ""
    conversation_id: str | None = None
    verdict: str = "done"


@dataclass
class ApprovalEvent:
    type: Literal["approval"] = "approval"
    request_id: str = ""
    decision: RequestStatus = "denied"
    conversation_id: str | None = None


@dataclass
class TranscriptEvent:
    type: Literal["transcript"] = "transcript"
    role: Literal["user", "assistant"] = "user"
    text: str = ""
    is_final: bool = False
    turn_id: str | None = None


@dataclass
class StreamChunkEvent:
    type: Literal["stream_chunk"] = "stream_chunk"
    delta: str = ""
    turn_id: str | None = None


@dataclass
class ModelStatusEvent:
    type: Literal["model_status"] = "model_status"
    installed: list[str] = field(default_factory=list)
    selected: str | None = None
    healthy: bool = False
    error: str | None = None


# Union type for type checking.
AssistantEvent = (
    StateTransitionEvent
    | AssistantErrorEvent
    | LatencyMetricEvent
    | AudioLevelEvent
    | ToolProposalEvent
    | ToolResultEvent
    | ApprovalEvent
    | TranscriptEvent
    | StreamChunkEvent
    | ModelStatusEvent
)


def event_to_dict(event: AssistantEvent) -> dict[str, Any]:
    """Serialize an event to a JSON-friendly dict (camelCase keys for the UI)."""
    d: dict[str, Any] = {"type": event.type}
    for k, v in vars(event).items():
        if k == "type":
            continue
        if v is None:
            continue
        d[k] = v
    return d

