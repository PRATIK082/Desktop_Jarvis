// Shared assistant state machine events and schemas.
// These schemas are mirrored in services/assistant (Python/Pydantic) for
// IPC contract parity between the Tauri Rust boundary and the Python sidecar.

export const AssistantState = {
  booting: "booting",
  checking_dependencies: "checking_dependencies",
  idle: "idle",
  wake_word_listening: "wake_word_listening",
  recording: "recording",
  transcribing: "transcribing",
  thinking: "thinking",
  proposing_action: "proposing_action",
  awaiting_approval: "awaiting_approval",
  executing: "executing",
  speaking: "speaking",
  cancelling: "cancelling",
  offline: "offline",
  degraded: "degraded",
  error: "error",
} as const;

export type AssistantState = (typeof AssistantState)[keyof typeof AssistantState];

export interface StateTransitionEvent {
  type: "state_transition";
  from_state: AssistantState;
  to_state: AssistantState;
  timestamp: string;
  request_id?: string;
}

export interface AssistantErrorEvent {
  type: "assistant_error";
  code: string;
  message: string;
  recoverable: boolean;
  retry_available: boolean;
  request_id?: string;
  conversation_id?: string;
}

export interface LatencyMetricEvent {
  type: "latency_metric";
  name: "wake_detection" | "transcription" | "first_llm_token" | "total_llm" | "first_audio" | "total_turn";
  duration_ms: number;
  turn_id?: string;
}

export interface AudioLevelEvent {
  type: "audio_level";
  level: number; // 0.0 to 1.0
  device_id?: string;
}

export interface ToolProposalEvent {
  type: "tool_proposal";
  tool_id: string;
  arguments: Record<string, unknown>;
  risk_level: number;
  reason: string;
  expected_effect: string;
  request_id: string;
}

export type ToolVerdict = "done" | "unverified" | "failed" | "ask" | "started";

export interface ToolResultEvent {
  type: "tool_result";
  tool_id: string;
  success: boolean;
  result?: unknown;
  error?: string;
  duration_ms: number;
  request_id: string;
  verdict?: ToolVerdict;
}

export interface ApprovalEvent {
  type: "approval";
  request_id: string;
  decision: "approved_once" | "remembered" | "denied" | "cancelled";
}

export interface TranscriptEvent {
  type: "transcript";
  role: "user" | "assistant";
  text: string;
  is_final: boolean;
  turn_id?: string;
}

export interface StreamChunkEvent {
  type: "stream_chunk";
  delta: string;
  turn_id?: string;
}

export interface ModelStatusEvent {
  type: "model_status";
  installed: string[];
  selected?: string;
  healthy: boolean;
  error?: string;
}

export type AssistantEvent =
  | StateTransitionEvent
  | AssistantErrorEvent
  | LatencyMetricEvent
  | AudioLevelEvent
  | ToolProposalEvent
  | ToolResultEvent
  | ApprovalEvent
  | TranscriptEvent
  | StreamChunkEvent
  | ModelStatusEvent;

export interface ToolSchema {
  id: string;
  name: string;
  description: string;
  input_schema: Record<string, unknown>; // JSON Schema (strict)
  result_schema: Record<string, unknown>; // JSON Schema (strict)
  risk_level: 0 | 1 | 2 | 3;
  permission_category: string;
  timeout_ms: number;
  dry_run_capable: boolean;
}

export interface StartSidecarRequest {
  port: number;
  auth_token: string;
}

export interface HealthResponse {
  status: "healthy" | "degraded" | "unhealthy";
  sidecar_uptime_ms?: number;
  ollama_healthy: boolean;
  version: string;
}

export const RISK_LEVEL_DESCRIPTIONS: Record<number, string> = {
  0: "Conversational / read-only calculation — no approval needed.",
  1: "Reads from explicitly approved resources — approval may be remembered per category.",
  2: "Creates or changes local data; opens applications or URLs — preview required unless a narrow remembered rule exists.",
  3: "Destructive, security-sensitive, financial, credential-related, or privacy-sensitive — denied by default in this version.",
};
