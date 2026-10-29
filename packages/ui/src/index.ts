// Shared UI primitives barrel (placeholder).
export * from "./voice-orb";

export interface VoiceOrbProps {
  amplitude: number;
  state: "idle" | "listening" | "thinking" | "speaking" | "error";
  reducedMotion?: boolean;
}
