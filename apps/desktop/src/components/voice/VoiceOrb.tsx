import { useAssistantStore } from "../../stores/assistant";
import { Badge } from "../common/Badge";

interface VoiceOrbProps {
  className?: string;
}

export function VoiceOrb({ className = "" }: VoiceOrbProps) {
  const { state, audioLevel, micEnabled, reducedMotion } = useAssistantStore();

  const isListening =
    state === "recording" ||
    state === "wake_word_listening" ||
    state === "transcribing";
  const isSpeaking = state === "speaking";
  const isThinking = state === "thinking" || state === "proposing_action";
  const isError = state === "error";

  // Base size scales with audio level when listening; scale + glow follow
  // the live level while speaking. Sizes go through inline style because
  // Tailwind cannot generate classes from runtime values.
  const baseSize = 160;
  const levelSize = isListening ? baseSize + audioLevel * 60 : baseSize;
  const scale = isSpeaking ? 1 + audioLevel * 0.12 : 1;
  const glow =
    isListening || isSpeaking
      ? `0 0 ${Math.round(24 + audioLevel * 32)}px rgb(var(--accent) / ${(
          0.25 +
          audioLevel * 0.45
        ).toFixed(2)})`
      : undefined;

  let animationClass = "";
  let borderColor = "border-surface-panel";
  let shadowColor = "shadow-[0_0_30px_rgba(148,163,184,0.15)]";

  if (isError) {
    animationClass = reducedMotion ? "" : "animate-pulse-slow";
    borderColor = "border-status-error/50";
    shadowColor = "shadow-[0_0_30px_rgba(248,113,113,0.2)]";
  } else if (isListening) {
    animationClass = reducedMotion ? "" : "animate-orb-listen";
    borderColor = "border-accent-cyan/60";
    shadowColor = "shadow-[0_0_40px_rgb(var(--accent)/0.35)]";
  } else if (isSpeaking) {
    animationClass = reducedMotion ? "" : "animate-orb-breath";
    borderColor = "border-accent-blue/60";
    shadowColor = "shadow-[0_0_40px_rgb(var(--accent-2)/0.35)]";
  } else if (isThinking) {
    animationClass = reducedMotion ? "" : "animate-pulse-slow";
    borderColor = "border-accent-blue/40";
    shadowColor = "shadow-[0_0_30px_rgb(var(--accent-2)/0.2)]";
  }

  return (
    <div className={`relative flex flex-col items-center gap-2 ${className}`}>
      <div
        className={`voice-orb ${animationClass} ${borderColor} ${shadowColor}`}
        style={{
          width: levelSize,
          height: levelSize,
          transform: `scale(${scale.toFixed(3)})`,
          boxShadow: glow,
        }}
        role="status"
        aria-label={`JARVIS voice orb, state: ${state}`}
        aria-live="polite"
      >
        {/* Inner pulse ring */}
        <div
          className={`absolute inset-0 rounded-full border border-current ${isListening ? "animate-orb-listen opacity-60" : "opacity-30"}`}
        />
        {/* State indicator dot */}
        <div
          className={`absolute -right-1 -top-1 w-3 h-3 rounded-full ${
            isListening
              ? "bg-status-ok animate-pulse"
              : isError
                ? "bg-status-error"
                : "bg-surface-panel"
          }`}
        />
      </div>
      <div className="flex items-center gap-1 text-xs">
        <Badge
          variant={
            isError
              ? "error"
              : isListening || isSpeaking
                ? "ok"
                : state === "idle"
                  ? "idle"
                  : "warn"
          }
        >
          {state
            .replace(/_/g, " ")
            .replace(/\b\w/g, (c: string) => c.toUpperCase())}
        </Badge>
      </div>
      {!micEnabled && (
        <p className="text-xs text-status-idle">Microphone disabled</p>
      )}
    </div>
  );
}
