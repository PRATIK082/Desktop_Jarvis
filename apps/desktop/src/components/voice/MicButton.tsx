import { useAssistantStore } from "../../stores/assistant";

interface WaveformProps {
  className?: string;
}

export function Waveform({ className = "" }: WaveformProps) {
  const { audioLevel, state } = useAssistantStore();
  const isActive =
    state === "recording" ||
    state === "wake_word_listening" ||
    state === "transcribing" ||
    state === "speaking";

  // Generate deterministic-ish bars based on audio level
  const barCount = 20;
  const bars = Array.from({ length: barCount }, (_, i) => {
    const phase = (i / barCount) * Math.PI * 2;
    const base = Math.abs(Math.sin(phase + audioLevel * 4));
    const height = Math.max(4, base * (audioLevel * 60 + 8));
    return (
      <div
        key={i}
        className={`wave-bar w-1.5 bg-accent-cyan/60 rounded-full ${isActive ? "animate-pulse" : ""}`}
        style={{ height: `${height}px`, opacity: Math.min(1, base + 0.3) }}
      />
    );
  });

  return (
    <div
      className={`flex items-end gap-1 h-12 ${className}`}
      role="meter"
      aria-label="Audio level"
      aria-valuenow={Math.round(audioLevel * 100)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      {bars}
    </div>
  );
}

interface MicButtonProps {
  onPress: () => void;
  onRelease: () => void;
  onClick: () => void;
  disabled?: boolean;
}

export function MicButton({
  onPress,
  onRelease,
  onClick,
  disabled = false,
}: MicButtonProps) {
  const { state, micEnabled, micPermissionGranted } = useAssistantStore();
  const isActive =
    state === "recording" || state === "transcribing" || state === "speaking";
  const showMic = state === "idle" || state === "wake_word_listening";

  return (
    <div className="flex flex-col items-center gap-2">
      {showMic ? (
        <div
          className="relative group"
          onMouseDown={(e) => {
            e.preventDefault();
            if (!disabled && micEnabled) onPress();
          }}
          onMouseUp={(e) => {
            e.preventDefault();
            if (!disabled && micEnabled) onRelease();
          }}
          onMouseLeave={(e) => {
            e.preventDefault();
            if (!disabled && micEnabled) onRelease();
          }}
          onClick={onClick}
          onKeyDown={(e) => {
            if (e.key === " " || e.key === "Enter") {
              e.preventDefault();
              if (!disabled && micEnabled) onPress();
            }
          }}
          onKeyUp={(e) => {
            if (e.key === " " || e.key === "Enter") {
              e.preventDefault();
              if (!disabled && micEnabled) onRelease();
            }
          }}
          role="button"
          tabIndex={disabled ? -1 : 0}
          aria-pressed={isActive}
          aria-label="Push-to-talk microphone"
        >
          <button
            className={`w-20 h-20 rounded-full flex items-center justify-center transition-all duration-200 ${
              isActive
                ? "bg-accent-cyan text-surface-deep scale-105 shadow-[0_0_40px_rgb(var(--accent)/0.6)]"
                : "bg-surface-graphite border border-surface-panel text-light hover:border-accent-cyan/50"
            } ${disabled ? "opacity-50 pointer-events-none" : ""}`}
            disabled={disabled || !micEnabled}
          >
            <svg
              className="w-8 h-8"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M15.536 8.464a5 5 0 010 7.072l2.828 2.829a1 1 0 01-1.414 1.414l-2.829-2.829a1 1 0 010-1.414l0 0L1.415 9.171a1 1 0 010-1.414l14.121-14.121A1 1 0 0115.536 8.464z"
              ></path>
            </svg>
          </button>
          <span
            className={`absolute -top-3 left-1/2 -translate-x-1/2 px-2 py-0.5 rounded text-xs font-medium ${
              isActive
                ? "bg-accent-cyan text-surface-deep"
                : "bg-surface-graphite text-surface-panel border border-surface-panel"
            }`}
          >
            {isActive ? "Hold to speak" : "Push-to-talk"}
          </span>
        </div>
      ) : (
        <div className="flex items-center gap-2 text-xs">
          <span className="w-2 h-2 rounded-full bg-status-idle" />
          <span className="text-surface-panel">{state.replace(/_/g, " ")}</span>
        </div>
      )}
      {!micPermissionGranted && (
        <p className="text-xs text-status-error">
          Microphone permission denied
        </p>
      )}
      {!micEnabled && micPermissionGranted && (
        <p className="text-xs text-status-idle">
          Microphone disabled in settings
        </p>
      )}
    </div>
  );
}
