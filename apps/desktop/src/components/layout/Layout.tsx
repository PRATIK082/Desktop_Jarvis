import { useEffect, useRef, useState } from "react";
import { useAssistantStore } from "../../stores/assistant";
import { VoiceOrb } from "../voice/VoiceOrb";

// Minimal Web Speech API shapes (not in this project's TS DOM lib).
interface SpeechRecognitionInstance {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((ev: SpeechRecognitionResultEvent) => void) | null;
  onerror: ((ev: { error?: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop?: () => void;
}
interface SpeechRecognitionResultEvent {
  results?: ArrayLike<ArrayLike<{ transcript?: string }>>;
}
import { Badge } from "../common/Badge";
import { Button } from "../common/Button";
import { Card, CardHeader } from "../common/Card";

const NAV_ITEMS: { id: string; label: string; icon: string }[] = [
  { id: "home", label: "Home", icon: "🏠" },
  { id: "conversations", label: "Conversations", icon: "💬" },
  { id: "memory", label: "Memory", icon: "🧠" },
  { id: "knowledge", label: "Knowledge", icon: "📚" },
  { id: "automations", label: "Automations", icon: "⚙️" },
  { id: "activity", label: "Activity", icon: "📋" },
  { id: "models", label: "Models", icon: "🤖" },
  { id: "settings", label: "Settings", icon: "⚙️" },
];

import { useLayoutPrefs } from "../../hooks/useLayoutPrefs";

export function LeftNav() {
  const { activeScreen, setActiveScreen, ollamaHealthy, micEnabled } =
    useAssistantStore();
  const { prefs } = useLayoutPrefs();
  const collapsed = prefs.navCollapsed;

  return (
    <nav
      className={`fixed left-0 top-0 bottom-0 z-20 flex flex-col border-r border-surface-panel transition-[width] duration-150 ${
        collapsed ? "w-16" : "w-64"
      }`}
      style={{
        backgroundColor: `rgba(30, 41, 59, ${prefs.panelOpacity})`,
        backdropFilter: prefs.panelOpacity < 0.95 ? "blur(8px)" : undefined,
      }}
      aria-label="Main navigation"
    >
      <div className="p-4 border-b border-surface-panel">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-accent-cyan/20 flex items-center justify-center text-accent-cyan font-bold">
            J
          </div>
          {!collapsed && (
            <span className="font-semibold text-light text-sm">JARVIS</span>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-2 py-3 space-y-1">
        {NAV_ITEMS.map((item) => {
          const active = activeScreen === item.id;
          return (
            <button
              key={item.id}
              onClick={() => setActiveScreen(item.id as any)}
              title={collapsed ? item.label : undefined}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${
                active
                  ? "bg-accent-cyan/20 text-accent-cyan"
                  : "text-surface-panel hover:bg-surface-panel hover:text-light"
              } ${collapsed ? "justify-center" : ""}`}
              aria-pressed={active}
            >
              <span className="w-5 text-center">{item.icon}</span>
              {!collapsed && <span>{item.label}</span>}
            </button>
          );
        })}
      </div>

      <div className="p-3 border-t border-surface-panel">
        <CardStatusRow label="Ollama" healthy={ollamaHealthy} />
        <CardStatusRow label="Microphone" healthy={micEnabled} />
      </div>
    </nav>
  );
}

function CardStatusRow({
  label,
  healthy,
}: {
  label: string;
  healthy: boolean;
}) {
  return (
    <div className="flex items-center justify-between px-3 py-1.5 text-xs">
      <span className="text-surface-panel">{label}</span>
      <Badge variant={healthy ? "ok" : "error"}>
        {healthy ? "ok" : "unavailable"}
      </Badge>
    </div>
  );
}

export function TelemetryHeader({
  title,
  subtitle,
}: {
  title: string;
  subtitle: string;
}) {
  const {
    state,
    sidecarConnected,
    ollamaHealthy,
    selectedModel,
    micEnabled,
    micPermissionGranted,
    audioLevel,
  } = useAssistantStore();

  const level = Math.round(Math.min(1, Math.max(0, audioLevel)) * 100);
  const micReady = micPermissionGranted && micEnabled;

  return (
    <header
      className="hud-panel mb-6 flex flex-wrap items-center gap-x-4 gap-y-3 px-4 py-3"
      aria-label="Assistant telemetry"
    >
      <div className="min-w-0 flex-1">
        <h1 className="truncate font-display text-xl font-semibold text-light">
          {title}
        </h1>
        <p className="text-xs text-surface-panel">{subtitle}</p>
        <div
          className="mt-2 h-1 w-full max-w-xs overflow-hidden rounded bg-surface-deep"
          role="meter"
          aria-valuenow={level}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Audio level"
        >
          <div
            className="h-full bg-accent-cyan transition-[width] duration-100"
            style={{ width: `${level}%` }}
          />
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge variant={isListeningState(state) ? "ok" : "idle"}>
          {state.replace(/_/g, " ")}
        </Badge>
        <Badge variant={sidecarConnected ? "ok" : "error"}>
          {sidecarConnected ? "sidecar" : "no sidecar"}
        </Badge>
        <Badge variant={ollamaHealthy ? "ok" : "error"}>
          {ollamaHealthy ? "ollama" : "ollama down"}
        </Badge>
        <Badge variant={selectedModel ? "idle" : "error"}>
          {selectedModel ?? "no model"}
        </Badge>
        <Badge variant={micReady ? "ok" : "idle"}>
          mic {micReady ? "ready" : "off"}
        </Badge>
      </div>
    </header>
  );
}

function isListeningState(state: string): boolean {
  return (
    state === "recording" ||
    state === "wake_word_listening" ||
    state === "transcribing" ||
    state === "speaking"
  );
}

interface BottomDockProps {
  onSendMessage: (text?: string) => void;
  inputValue: string;
  onInputChange: (value: string) => void;
}

export function BottomDock({
  onSendMessage,
  inputValue,
  onInputChange,
}: BottomDockProps) {
  const {
    state,
    micEnabled,
    micPermissionGranted,
    selectedModel,
    sidecarConnected,
    sidePanelOpen,
    setSidePanelOpen,
    setMicPermissionGranted,
    setMicEnabled,
    setLastError,
  } = useAssistantStore();

  const isListening =
    state === "recording" || state === "transcribing" || state === "speaking";

  const handleInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      onSendMessage();
    }
  };

  // Push-to-talk: browser SpeechRecognition (no sidecar STT endpoint yet).
  // Result transcript is bridged straight into onSendMessage so voice turns
  // work end-to-end today; local faster-whisper can replace this later.
  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null);
  const [isListeningSTT, setIsListeningSTT] = useState(false);

  const startListening = () => {
    const w = window as unknown as {
      SpeechRecognition?: new () => SpeechRecognitionInstance;
      webkitSpeechRecognition?: new () => SpeechRecognitionInstance;
    };
    const SR = w.SpeechRecognition ?? w.webkitSpeechRecognition;
    if (typeof SR !== "function") {
      // Fallback: focus typed input so user can still talk via OS dictation.
      document.getElementById("jarvis-chat-input")?.focus();
      return;
    }
    // If a recognition is already running, abort it first to avoid
    // "aborted" / "already started" errors from the browser.
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop?.();
      } catch {
        // ignore
      }
      recognitionRef.current = null;
    }
    // Barge-in: the user takes the floor — stop any ongoing speech first.
    try {
      window.speechSynthesis?.cancel();
    } catch {
      // Speech synthesis unavailable; continue to recognition.
    }
    try {
      const rec = new SR();
      recognitionRef.current = rec;
      rec.lang = "en-US";
      rec.interimResults = false;
      rec.maxAlternatives = 1;
      setIsListeningSTT(true);
      rec.onresult = (ev: SpeechRecognitionResultEvent) => {
        const transcript: string =
          ev?.results?.[0]?.[0]?.transcript ?? "";
        if (transcript.trim()) onSendMessage(transcript.trim());
        else
          setLastError({
            code: "heard_nothing",
            message: "Heard nothing — try speaking again.",
            recoverable: true,
          });
      };
      rec.onerror = (ev: { error?: string }) => {
        const kind = ev?.error ?? "unknown";
        // "aborted" fires when we (or the browser) stopped recognition
        // mid-flight; treat it as a benign no-op rather than an error.
        if (kind === "aborted" || kind === "no-speech") {
          return;
        }
        const message =
          kind === "not-allowed"
            ? "Microphone blocked — allow access in the browser prompt."
            : kind === "audio-capture"
              ? "No microphone found — check the input device."
              : `Voice input failed (${kind}).`;
        setLastError({ code: `stt_${kind}`, message, recoverable: true });
      };
      rec.onend = () => {
        recognitionRef.current = null;
        setIsListeningSTT(false);
      };
      rec.start();
    } catch {
      recognitionRef.current = null;
      setIsListeningSTT(false);
      document.getElementById("jarvis-chat-input")?.focus();
    }
  };

  // HomeDashboard quick actions dispatch these window events.
  useEffect(() => {
    const focusInput = () =>
      document.getElementById("jarvis-chat-input")?.focus();
    const ptt = () => startListening();
    window.addEventListener("jarvis:focus-input", focusInput);
    window.addEventListener("jarvis:push-to-talk", ptt);
    return () => {
      window.removeEventListener("jarvis:focus-input", focusInput);
      window.removeEventListener("jarvis:push-to-talk", ptt);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onSendMessage]);

  const requestMicPermission = async () => {
    try {
      if (navigator.mediaDevices?.getUserMedia) {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: true,
        });
        stream.getTracks().forEach((t) => t.stop());
        setMicPermissionGranted(true);
        setMicEnabled(true);
      }
    } catch {
      setMicPermissionGranted(false);
    }
  };

  return (
    <div
      className={`fixed bottom-0 left-0 right-0 h-24 bg-surface-graphite border-t border-surface-panel z-20 flex items-center justify-between px-4`}
      aria-label="Interaction dock"
    >
      {/* Left: mic controls */}
      <div className="flex items-center gap-3">
        <MicButtonDock
          onPress={startListening}
          onRelease={() => {}}
          onClick={() => {
            if (!micPermissionGranted) void requestMicPermission();
            else if (!isListeningSTT) startListening();
          }}
          disabled={isListeningSTT}
        />
      </div>

      {/* Center: typed input + model indicator */}
      <div className="flex items-center gap-3 flex-1 max-w-2xl">
        <div className="flex w-full gap-2">
          <input
            id="jarvis-chat-input"
            className="flex-1 rounded-lg border border-surface-panel bg-surface-deep py-2.5 px-3 text-sm text-light placeholder:text-surface-panel/60 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-cyan"
            placeholder={
              sidecarConnected
                ? "Type a message…"
                : "Sidecar starting… you can type, sending waits for connection"
            }
            value={inputValue}
            onChange={(e) => onInputChange(e.target.value)}
            onKeyDown={handleInputKeyDown}
          />
          <Button
            variant="primary"
            onClick={() => {
              onSendMessage();
            }}
            disabled={!inputValue.trim()}
          >
            Send
          </Button>
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-surface-deep border border-surface-panel text-xs">
          <span className="text-surface-panel">Model:</span>
          <span className="text-light truncate max-w-xs">
            {selectedModel ?? "none"}
          </span>
        </div>
      </div>

      {/* Right: stop + privacy + panel toggle */}
      <div className="flex items-center gap-2">
        <span
          className={`text-xs font-medium ${
            isListening ? "text-accent-cyan" : "text-surface-panel"
          }`}
        >
          {state
            .replace(/_/g, " ")
            .replace(/\b\w/g, (c: string) => c.toUpperCase())}
        </span>
        <Button
          variant="danger"
          size="sm"
          onClick={() => {
            try {
              speechSynthesis.cancel();
            } catch {
              // no-op
            }
          }}
          disabled={!isListening}
          title="Stop"
        >
          <span className="sr-only">Stop</span>
          <svg
            className="w-4 h-4"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
        </Button>
        <Badge variant={micEnabled ? "ok" : "idle"}>
          {micEnabled ? "mic on" : "mic off"}
        </Badge>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setSidePanelOpen(!sidePanelOpen)}
          title="Context panel"
        >
          <span className="sr-only">Toggle context panel</span>
          <svg
            className="w-4 h-4"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
            />
          </svg>
        </Button>
      </div>
    </div>
  );
}

function MicButtonDock({
  onPress,
  onRelease,
  onClick,
  disabled,
}: {
  onPress: () => void;
  onRelease: () => void;
  onClick: () => void;
  disabled: boolean;
}) {
  const { state, micPermissionGranted } = useAssistantStore();
  const isActive =
    state === "recording" || state === "transcribing" || state === "speaking";

  return (
    <button
      onMouseDown={(e) => {
        e.preventDefault();
        if (!disabled && micPermissionGranted) onPress();
      }}
      onMouseUp={(e) => {
        e.preventDefault();
        if (!disabled && micPermissionGranted) onRelease();
      }}
      onMouseLeave={(e) => {
        e.preventDefault();
        if (!disabled && micPermissionGranted) onRelease();
      }}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === " " || e.key === "Enter") {
          e.preventDefault();
          if (!disabled && micPermissionGranted) onPress();
        }
      }}
      onKeyUp={(e) => {
        if (e.key === " " || e.key === "Enter") {
          e.preventDefault();
          if (!disabled && micPermissionGranted) onRelease();
        }
      }}
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-pressed={isActive}
      aria-label="Push-to-talk"
      className={`w-12 h-12 rounded-full flex items-center justify-center transition-all duration-200 ${
        isActive
          ? "bg-accent-cyan text-surface-deep shadow-[0_0_30px_rgb(var(--accent)/0.6)]"
          : "bg-surface-panel border border-surface-panel text-light"
      } ${disabled ? "opacity-50 pointer-events-none" : ""}`}
    >
      <svg
        className="w-5 h-5"
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
  );
}

export function RightPanel() {
  const { sidePanelOpen, state, latencyMetrics } = useAssistantStore();
  const { prefs, update } = useLayoutPrefs();
  const [dragging, setDragging] = useState(false);

  if (!sidePanelOpen) return null;

  const startDrag = (e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(true);
    const startX = e.clientX;
    const startWidth = prefs.rightPanelWidth;
    const onMove = (ev: PointerEvent) => {
      const next = startWidth + (startX - ev.clientX);
      update({ rightPanelWidth: Math.min(520, Math.max(240, next)) });
    };
    const onUp = () => {
      setDragging(false);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };

  return (
    <aside
      className="fixed right-0 top-0 bottom-0 z-20 flex flex-col border-l border-surface-panel"
      style={{
        width: prefs.rightPanelWidth,
        backgroundColor: `rgba(30, 41, 59, ${prefs.panelOpacity})`,
        backdropFilter: prefs.panelOpacity < 0.95 ? "blur(8px)" : undefined,
      }}
      aria-label="Context panel"
    >
      {/* Resize handle */}
      <div
        onPointerDown={startDrag}
        className={`absolute left-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-accent-cyan/40 ${
          dragging ? "bg-accent-cyan/60" : ""
        }`}
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize context panel"
      />
      <div className="p-4 border-b border-surface-panel">
        <h2 className="text-sm font-semibold text-light">Context</h2>
        <p className="text-xs text-surface-panel">{state} state</p>
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <div className="space-y-2">
          <h3 className="text-xs font-semibold text-surface-panel uppercase tracking-wider">
            Latency
          </h3>
          {latencyMetrics.length === 0 ? (
            <p className="text-xs text-surface-panel">No metrics yet</p>
          ) : (
            latencyMetrics
              .slice(-5)
              .map((m: { name: string; duration_ms: number }, i: number) => (
                <div key={i} className="flex justify-between text-xs">
                  <span className="text-surface-panel">{m.name}</span>
                  <span className="text-light">
                    {m.duration_ms.toFixed(0)}ms
                  </span>
                </div>
              ))
          )}
        </div>
        <div className="pt-2 border-t border-surface-panel">
          <h3 className="text-xs font-semibold text-surface-panel uppercase tracking-wider">
            Privacy
          </h3>
          <p className="text-xs text-light">All processing local. No cloud.</p>
        </div>
      </div>
    </aside>
  );
}

export function HomeDashboard() {
  const { state, ollamaHealthy, micEnabled, micPermissionGranted } =
    useAssistantStore();

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-light">Home</h1>
        <p className="text-surface-panel">
          Assistant status and quick actions.
        </p>
      </div>

      <div className="hud-panel flex items-center justify-center py-6">
        <VoiceOrb />
      </div>

      <Card padding="lg">
        <CardHeader title="Assistant status" subtitle="Current system state" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <StatusTile
            label="State"
            value={state.replace(/_/g, " ")}
            variant="info"
          />
          <StatusTile
            label="Ollama"
            value={ollamaHealthy ? "healthy" : "unavailable"}
            variant={ollamaHealthy ? "ok" : "error"}
          />
          <StatusTile
            label="Microphone"
            value={
              micPermissionGranted && micEnabled
                ? "ready"
                : micPermissionGranted
                  ? "disabled"
                  : "denied"
            }
            variant={
              micPermissionGranted && micEnabled
                ? "ok"
                : micPermissionGranted
                  ? "warn"
                  : "error"
            }
          />
        </div>
      </Card>

      <Card padding="lg">
        <CardHeader title="Quick actions" subtitle="Start a conversation" />
        <div className="flex flex-col sm:flex-row gap-3">
          <Button
            variant="primary"
            onClick={() =>
              window.dispatchEvent(new Event("jarvis:focus-input"))
            }
          >            <svg
              className="w-4 h-4 mr-2"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M11 5.882V19.24a1.76 1.76 0 01-3.417.592l-2.147-6.15M18 13a3 3 0 100-6M5.436 13.683A4.001 4.001 0 017 6h1.832c4.1 0 7.625-1.234 9.168-3v14c-1.543-1.766-5.067-3-9.168-3H7a3.988 3.988 0 01-1.564-.317z"
              />
            </svg>
            Typed chat
          </Button>
          <Button
            variant="ghost"
            onClick={() =>
              window.dispatchEvent(new Event("jarvis:push-to-talk"))
            }
          >
            <svg
              className="w-4 h-4 mr-2"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M15.536 8.464a5 5 0 010 7.072l2.828 2.829a1 1 0 01-1.414 1.414l-2.829-2.829a1 1 0 010-1.414l0 0L1.415 9.171a1 1 0 010-1.414l14.121-14.121A1 1 0 0115.536 8.464z"
              />
            </svg>
            Push-to-talk
          </Button>
        </div>
      </Card>

      <div className="bg-surface-graphite/50 rounded-xl p-4 border border-surface-panel">
        <h3 className="text-sm font-semibold text-light mb-2">
          Example commands
        </h3>
        <ul className="text-xs text-surface-panel space-y-1 list-disc pl-4">
          <li>"What time is it?"</li>
          <li>"Open my documents folder"</li>
          <li>"Create a reminder to call mom at 6pm"</li>
          <li>"Search my knowledge base for project notes"</li>
        </ul>
      </div>
    </div>
  );
}

function StatusTile({
  label,
  value,
  variant = "idle",
}: {
  label: string;
  value: string;
  variant?: "ok" | "warn" | "error" | "idle" | "info";
}) {
  const colorMap: Record<string, string> = {
    ok: "text-status-ok",
    warn: "text-status-warn",
    error: "text-status-error",
    idle: "text-status-idle",
    info: "text-accent-cyan",
  };
  return (
    <div className="bg-surface-deep rounded-lg p-3 border border-surface-panel/50">
      <p className="text-xs text-surface-panel">{label}</p>
      <p className={`text-sm font-medium ${colorMap[variant]}`}>{value}</p>
    </div>
  );
}
