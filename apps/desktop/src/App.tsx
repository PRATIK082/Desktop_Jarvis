import { useEffect, useRef, useState, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { useAssistantStore } from "./stores/assistant";
import {
  LeftNav,
  BottomDock,
  RightPanel,
  HomeDashboard,
  TelemetryHeader,
} from "./components/layout/Layout";
import { ApprovalCardDisplay } from "./components/common/ApprovalCard";
import { Card, CardHeader } from "./components/common/Card";
import { Button } from "./components/common/Button";
import { Badge } from "./components/common/Badge";
import type { AssistantEvent } from "../../../packages/contracts/src/index.ts";
import { useAudioLevel } from "./hooks/useAudioLevel";
import { useLayoutPrefs } from "./hooks/useLayoutPrefs";
import {
  ACCENT_PRESETS,
  applyAccent,
  applyStoredAccent,
  loadAccent,
  type AccentSelection,
} from "./theme";

export default function App() {
  const {
    sidecarUrl,
    authToken,
    setSidecarConnected,
    setSidecarUrl,
    setAuthToken,
    setOllamaHealthy,
    setHealth,
    setInstalledModels,
    setSelectedModel,
    selectedModel,
    setEngineActive,
    setAudioStatus,
    speechEnabled,
    setMicPermissionGranted,
    setMicEnabled,
    setState,
    processEvent,
    lastError,
    clearLastError,
    setLastError,
    setStreamingText,
    setLiveTranscript,
    setCurrentTurnId,
    activeScreen,
    pendingApproval,
    setPendingApproval,
  } = useAssistantStore();

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  // Drives store.audioLevel: live mic RMS while listening, synthetic
  // pulse while speaking/thinking, decay to 0 when idle.
  useAudioLevel();
  const { prefs: layoutPrefs } = useLayoutPrefs();

  // Apply the persisted HUD accent (Settings → Appearance) once on mount.
  useEffect(() => {
    applyStoredAccent();
  }, []);

  const [inputValue, setInputValue] = useState("");

  const connectWebSocket = useCallback(
    (url: string, token: string) => {
      const ws = new WebSocket(
        `${url.replace("http", "ws")}/events?token=${encodeURIComponent(token)}`,
      );
      wsRef.current = ws;

      ws.onopen = () => {
        setSidecarConnected(true);
        // Backend runs its own state machine silently; mark UI runnable.
        setState("idle");
        clearTimeout(reconnectTimeoutRef.current!);
        reconnectTimeoutRef.current = null;
        // Fetch initial health to set Ollama status.
        fetch(`${url}/health`, {
          headers: { Authorization: `Bearer ${token}` },
        })
          .then((res) => res.json())
          .then((data) => {
            if (typeof data.ollama_healthy === "boolean") {
              setOllamaHealthy(data.ollama_healthy);
            }
            setHealth(data);
            // Surface engine + audio capability status for Models screen.
            const engine = data?.engine as
              | { active?: unknown }
              | undefined;
            setEngineActive(
              typeof engine?.active === "string" ? engine.active : null,
            );
            const audio = data?.audio as
              | {
                  stt_provider?: unknown;
                  stt_model?: unknown;
                  stt_installed?: unknown;
                  tts_provider?: unknown;
                  tts_installed?: unknown;
                }
              | undefined;
            if (
              audio &&
              typeof audio.stt_provider === "string" &&
              typeof audio.tts_provider === "string"
            ) {
              setAudioStatus({
                stt_provider: audio.stt_provider,
                stt_model:
                  typeof audio.stt_model === "string" ? audio.stt_model : "",
                stt_installed: audio.stt_installed === true,
                tts_provider: audio.tts_provider,
                tts_installed: audio.tts_installed === true,
              });
            }
          })
          .catch(() => {
            // best-effort
          });
        // Fetch installed Ollama models so the dock + Models page can
        // show a real selection instead of "none".
        fetch(`${url}/v1/models`, {
          headers: { Authorization: `Bearer ${token}` },
        })
          .then((res) => res.json())
          .then((data) => {
            const names: string[] = Array.isArray(data.models)
              ? data.models.filter(
                  (m: unknown): m is string =>
                    typeof m === "string" && m.length > 0,
                )
              : [];
            setInstalledModels(names);
            if (typeof data.healthy === "boolean") {
              setOllamaHealthy(data.healthy);
            }
            const preferred: string =
              typeof data.selected === "string" ? data.selected : "";
            if (preferred && names.includes(preferred)) {
              setSelectedModel(preferred);
            } else if (!selectedModel && names.length > 0) {
              // Auto-select: first non-embedding model, else first model.
              const chatModel =
                names.find(
                  (n) =>
                    !/embed|bge-|nomic|e5-/i.test(n),
                ) ?? names[0];
              setSelectedModel(chatModel);
            }
          })
          .catch(() => {
            // best-effort
          });
      };

      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (Array.isArray(payload)) {
            payload.forEach((ev) => processEvent(ev as AssistantEvent));
          } else {
            processEvent(payload as AssistantEvent);
          }
        } catch (_) {
          // ignore malformed frames
        }
      };

      ws.onclose = () => {
        setSidecarConnected(false);
        wsRef.current = null;
        if (!reconnectTimeoutRef.current) {
          reconnectTimeoutRef.current = setTimeout(() => {
            reconnectTimeoutRef.current = null;
            connectWebSocket(url, token);
          }, 3000);
        }
      };

      ws.onerror = () => {
        setSidecarConnected(false);
      };
    },
    [
      setSidecarConnected,
      setState,
      processEvent,
      setOllamaHealthy,
      setHealth,
      setInstalledModels,
      setSelectedModel,
      setEngineActive,
      setAudioStatus,
      selectedModel,
    ],
  );

  // Start the sidecar and connect the WebSocket once the sidecar reports its
  // URL and auth token. This bridges the Tauri command result to the frontend
  // bridge (__jarvisConnectSidecar) so the WebSocket can connect.
  const startSidecar = useCallback(async () => {
    // Guard: only run in Tauri context.
    if (typeof window === "undefined" || !("__TAURI_INTERNALS__" in window)) {
      setLastError({
        code: "not_tauri",
        message: "This app must be run inside the Tauri desktop window, not a browser.",
        recoverable: false,
      });
      return;
    }
    try {
      await invoke("start_sidecar");
      // After the sidecar is up, fetch its config (host/port/token).
      const config = await invoke<{ host: string; port: number; auth_token: string }>("sidecar_config");
      const url = `http://${config.host}:${config.port}`;
      if (typeof (window as any).__jarvisConnectSidecar === "function") {
        (window as any).__jarvisConnectSidecar(url, config.auth_token);
      } else {
        setSidecarUrl(url);
        setAuthToken(config.auth_token);
      }
    } catch (err) {
      setLastError({
        code: "sidecar_start_failed",
        message: `Failed to start sidecar: ${err}`,
        recoverable: true,
      });
      setSidecarConnected(false);
    }
  }, [setSidecarUrl, setAuthToken, setLastError, setSidecarConnected]);

  // Auto-start the sidecar on mount.
  useEffect(() => {
    startSidecar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Request microphone permission on mount.
  useEffect(() => {
    (async () => {
      try {
        if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
          const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
          // Permission granted — stop the stream immediately (we just needed permission).
          stream.getTracks().forEach((t) => t.stop());
          setMicPermissionGranted(true);
          setMicEnabled(true);
        } else {
          setMicPermissionGranted(false);
        }
      } catch {
        setMicPermissionGranted(false);
      }
    })();
  }, [setMicPermissionGranted, setMicEnabled]);

  // Listen for Tauri-sidecar started events as a fallback bridge.
  useEffect(() => {
    if (typeof window === "undefined" || !("__TAURI_INTERNALS__" in window)) return;
    const unlisten = listen<{ url: string; token: string }>("sidecar:started", (event) => {
      const payload = event.payload;
      if (typeof (window as any).__jarvisConnectSidecar === "function") {
        (window as any).__jarvisConnectSidecar(payload.url, payload.token);
      } else {
        setSidecarUrl(payload.url);
        setAuthToken(payload.token);
      }
    });
    return () => {
      unlisten.then((u: () => void) => u());
    };
  }, [setSidecarUrl, setAuthToken]);

  // Connect to sidecar WebSocket when told the URL/token
  useEffect(() => {
    if (!sidecarUrl || !authToken) return;
    connectWebSocket(sidecarUrl, authToken);
    return () => {
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [sidecarUrl, authToken, connectWebSocket]);

  // Expose connect for Tauri command to call after sidecar start
  (window as any).__jarvisConnectSidecar = (url: string, token: string) => {
    setSidecarUrl(url);
    setAuthToken(token);
  };

  const handleSend = useCallback(
    async (textOverride?: string) => {
      const text = (textOverride ?? inputValue).trim();
      if (!text) return;
      const turnId = crypto.randomUUID();
      setCurrentTurnId(turnId);
      setStreamingText("");
      setLiveTranscript(text);
      setInputValue("");
      // Fire-and-forget over WS (backend now loops + streams replies back).
      try {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(
            JSON.stringify({
              type: "user_input",
              text,
              conversation_id: "web-turn",
              request_id: turnId,
            }),
          );
        }
      } catch {
        // best-effort; REST below is authoritative
      }
      // Authoritative path: POST /v1/chat, then feed returned events
      // through the same store reducer the WS path uses.
      try {
        if (!sidecarUrl || !authToken) {
          setLastError({
            code: "sidecar_disconnected",
            message: "Sidecar is not connected yet. Wait for “sidecar connected”.",
            recoverable: true,
          });
          return;
        }
        const postChat = async (token: string) =>
          fetch(`${sidecarUrl}/v1/chat`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify({
              user_input: text,
              conversation_id: "web-turn",
              request_id: turnId,
              model: selectedModel ?? undefined,
            }),
          });
        let res = await postChat(authToken);
        if (res.status === 401) {
          // Token mismatch (stale/rotated sidecar token): refresh the
          // sidecar config once and retry before surfacing an error.
          try {
            const cfg = (await invoke("sidecar_config")) as {
              host: string;
              port: number;
              auth_token: string;
            };
            const freshUrl = `http://${cfg.host}:${cfg.port}`;
            setSidecarUrl(freshUrl);
            setAuthToken(cfg.auth_token);
            res = await postChat(cfg.auth_token);
          } catch {
            // fall through to the status check below with the original 401
          }
        }
        if (!res.ok) throw new Error(`chat HTTP ${res.status}`);
        const data = await res.json();
        const events = Array.isArray(data.events) ? data.events : [];
        for (const ev of events) processEvent(ev as AssistantEvent);
        // Iron-Man touch: speak the assistant's final reply out loud.
        try {
          const reply = [...events]
            .reverse()
            .find(
              (e: { type?: string; role?: string; text?: string }) =>
                e?.type === "transcript" && e?.role === "assistant" && e?.text,
            )?.text as string | undefined;
          if (reply && speechEnabled && "speechSynthesis" in window) {
            speechSynthesis.cancel();
            speechSynthesis.speak(new SpeechSynthesisUtterance(reply));
          }
        } catch {
          // voice output is best-effort
        }
      } catch (err) {
        setLastError({
          code: "chat_failed",
          message: `Typed chat failed: ${err}`,
          recoverable: true,
        });
      }
    },
    [
      inputValue,
      sidecarUrl,
      authToken,
      selectedModel,
      setSidecarUrl,
      setAuthToken,
      setCurrentTurnId,
      setStreamingText,
      setLiveTranscript,
      processEvent,
      setLastError,
      speechEnabled,
    ],
  );

  const handleApprove = useCallback(() => {
    wsRef.current?.send(
      JSON.stringify({
        type: "approval",
        decision: "approved_once",
        request_id: pendingApproval?.request_id ?? crypto.randomUUID(),
      }),
    );
  }, [pendingApproval]);

  const handleDeny = useCallback(() => {
    wsRef.current?.send(
      JSON.stringify({
        type: "approval",
        decision: "denied",
        request_id: pendingApproval?.request_id ?? crypto.randomUUID(),
      }),
    );
  }, [pendingApproval]);

  return (
    <div className="min-h-screen bg-surface-deep text-light font-sans selection:bg-accent-cyan/30">
      <a href="#main-content" id="skip-to-content">
        Skip to content
      </a>

      {/* Left navigation */}
      <LeftNav />

      {/* Main content area */}
      <main
        id="main-content"
        className={`flex-1 p-6 relative min-h-[calc(100vh-80px)] pb-24 ${
          layoutPrefs.navCollapsed ? "md:pl-16" : "md:pl-64"
        }`}
        role="main"
        aria-label="Main content"
      >
        <RightPanel />

        {/* Telemetry header: title + live state, sidecar, Ollama,
            model, mic badges and audio level meter. */}
        <TelemetryHeader
          title={screenTitle(activeScreen)}
          subtitle={screenSubtitle(activeScreen)}
        />

        {renderScreen()}

        {/* Approval card (floating, centered) */}
        {pendingApproval && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none">
            <div className="pointer-events-auto w-full max-w-md">
              <ApprovalCardDisplay
                onApproveOnce={handleApprove}
                onRemember={() => {
                  wsRef.current?.send(
                    JSON.stringify({
                      type: "approval",
                      decision: "remembered",
                      request_id:
                        pendingApproval?.request_id ?? crypto.randomUUID(),
                    }),
                  );
                  setPendingApproval(null);
                }}
                onDeny={handleDeny}
                onCancel={() => {
                  wsRef.current?.send(
                    JSON.stringify({
                      type: "approval",
                      decision: "cancelled",
                      request_id:
                        pendingApproval?.request_id ?? crypto.randomUUID(),
                    }),
                  );
                  setPendingApproval(null);
                }}
              />
            </div>
          </div>
        )}

        {/* Error banner */}
        {lastError && (
          <div className="fixed top-6 left-1/2 -translate-x-1/2 z-50 w-full max-w-lg p-4 rounded-lg border border-status-error/30 bg-status-error/10">
            <div className="flex items-start gap-3">
              <span className="text-status-error">⚠</span>
              <div className="flex-1">
                <p className="text-sm font-medium text-light">
                  {lastError.code}
                </p>
                <p className="text-xs text-surface-panel">
                  {lastError.message}
                </p>
              </div>
              {lastError.recoverable && (
                <Button variant="ghost" size="sm" onClick={clearLastError}>
                  Dismiss
                </Button>
              )}
            </div>
          </div>
        )}
      </main>

      {/* Bottom interaction dock — controlled input lives in App so
          Send always transmits what the user typed. */}
      <BottomDock
        onSendMessage={handleSend}
        inputValue={inputValue}
        onInputChange={setInputValue}
      />
    </div>
  );

  function screenTitle(screen: string) {
    const titles: Record<string, string> = {
      home: "Home",
      conversations: "Conversations",
      memory: "Memory",
      knowledge: "Knowledge",
      automations: "Automations",
      activity: "Activity",
      models: "Models",
      settings: "Settings",
    };
    return titles[screen] || "Home";
  }

  function screenSubtitle(screen: string) {
    const subtitles: Record<string, string> = {
      home: "Assistant status and quick actions",
      conversations: "Your conversation history",
      memory: "Explicit long-term memories",
      knowledge: "Indexed documents and RAG",
      automations: "Reminders, timers, and scheduled tasks",
      activity: "Action history and audit log",
      models: "Ollama models and configuration",
      settings: "Application settings",
    };
    return subtitles[screen] || "";
  }

  function renderScreen() {
    switch (activeScreen) {
      case "home":
        return <HomeDashboard />;
      case "conversations":
        return <ConversationsScreen />;
      case "memory":
        return <MemoryScreen />;
      case "knowledge":
        return <KnowledgeScreen />;
      case "automations":
        return <AutomationsScreen />;
      case "activity":
        return <ActivityScreen />;
      case "models":
        return <ModelsScreen />;
      case "settings":
        return <SettingsScreen />;
      default:
        return <HomeDashboard />;
    }
  }
}

/* ---- Screen placeholders ---- */
function ConversationsScreen() {
  const messages = useAssistantStore((s) => s.messages);
  const streamingText = useAssistantStore((s) => s.streamingText);
  const liveTranscript = useAssistantStore((s) => s.liveTranscript);
  return (
    <Card>
      <CardHeader title="Conversations" subtitle="Your conversation history" />
      <div className="p-4 space-y-2 text-sm max-h-[60vh] overflow-y-auto">
        {messages.length === 0 && !streamingText && !liveTranscript ? (
          <p className="text-surface-panel">
            No messages yet. Type below or use push-to-talk.
          </p>
        ) : (
          messages.map((m) => (
            <div
              key={m.id}
              className={m.role === "user" ? "text-right" : "text-left"}
            >
              <span
                className={
                  m.role === "user"
                    ? "inline-block bg-accent-blue/20 rounded-lg px-3 py-1.5 text-light"
                    : "inline-block bg-surface-deep border border-surface-panel rounded-lg px-3 py-1.5 text-light"
                }
              >
                {m.text}
              </span>
            </div>
          ))
        )}
        {streamingText ? (
          <div className="text-left">
            <span className="inline-block bg-surface-deep border border-surface-panel rounded-lg px-3 py-1.5 text-light opacity-80">
              {streamingText}
              <span className="typing-cursor" aria-hidden="true" />
            </span>
          </div>
        ) : null}
      </div>
    </Card>
  );
}
function MemoryScreen() {
  return (
    <Card>
      <CardHeader title="Memory" subtitle="Explicit long-term memories" />
      <div className="p-4 text-surface-panel text-sm">
        Memory CRUD will render here. Memories are stored locally and can be
        edited/deleted.
      </div>
    </Card>
  );
}
function KnowledgeScreen() {
  return (
    <Card>
      <CardHeader title="Knowledge" subtitle="Indexed documents and RAG" />
      <div className="p-4 text-surface-panel text-sm">
        Document indexing and retrieval will render here.
      </div>
    </Card>
  );
}
function AutomationsScreen() {
  return (
    <Card>
      <CardHeader title="Automations" subtitle="Reminders and timers" />
      <div className="p-4 text-surface-panel text-sm">
        Scheduler UI will render here (Phase 8 backend ready).
      </div>
    </Card>
  );
}
function ActivityScreen() {
  return (
    <Card>
      <CardHeader title="Activity" subtitle="Action history and audit log" />
      <div className="p-4 text-surface-panel text-sm">
        Activity log will render here with filters and clear history.
      </div>
    </Card>
  );
}
function ModelsScreen() {
  const {
    installedModels,
    setInstalledModels,
    selectedModel,
    setSelectedModel,
    ollamaHealthy,
    sidecarUrl,
    authToken,
    setOllamaHealthy,
    setLastError,
    engineActive,
    audioStatus,
  } = useAssistantStore();
  const [selectError, setSelectError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const refreshModels = useCallback(async () => {
    if (!sidecarUrl || !authToken) return;
    setRefreshing(true);
    setSelectError(null);
    try {
      const res = await fetch(`${sidecarUrl}/v1/models`, {
        headers: { Authorization: `Bearer ${authToken}` },
      });
      if (!res.ok) throw new Error(`models HTTP ${res.status}`);
      const data = await res.json();
      const names: string[] = Array.isArray(data.models)
        ? data.models.filter(
            (m: unknown): m is string =>
              typeof m === "string" && m.length > 0,
          )
        : [];
      setInstalledModels(names);
      if (typeof data.healthy === "boolean") {
        setOllamaHealthy(data.healthy);
      }
      if (typeof data.selected === "string" && data.selected) {
        setSelectedModel(data.selected);
      }
    } catch (err) {
      setSelectError(`Refresh failed: ${err}`);
    } finally {
      setRefreshing(false);
    }
  }, [
    sidecarUrl,
    authToken,
    setInstalledModels,
    setOllamaHealthy,
    setSelectedModel,
  ]);

  const selectModel = useCallback(
    async (name: string) => {
      if (!sidecarUrl || !authToken) return;
      setSelectError(null);
      try {
        const res = await fetch(`${sidecarUrl}/v1/models/select`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${authToken}`,
          },
          body: JSON.stringify({ model: name }),
        });
        if (!res.ok) throw new Error(`select HTTP ${res.status}`);
        const data = await res.json();
        if (typeof data.selected === "string" && data.selected) {
          setSelectedModel(data.selected);
        } else {
          setSelectedModel(name);
        }
      } catch (err) {
        const message = `Could not select ${name}: ${err}`;
        setSelectError(message);
        setLastError({
          code: "model_select_failed",
          message,
          recoverable: true,
        });
      }
    },
    [sidecarUrl, authToken, setSelectedModel, setLastError],
  );

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          title="Models"
          subtitle={
            ollamaHealthy
              ? `${installedModels.length} installed model${installedModels.length === 1 ? "" : "s"}`
              : "Ollama unavailable — start Ollama to load models"
          }
        />
        <div className="p-4 space-y-2">
          <div className="flex items-center justify-between pb-2">
            <span className="text-xs text-surface-panel">
              Active engine: {engineActive ?? "unknown"}
            </span>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                void refreshModels();
              }}
              disabled={refreshing}
            >
              {refreshing ? "Refreshing…" : "Refresh"}
            </Button>
          </div>
          {selectError && (
            <p className="text-xs text-status-error" role="alert">
              {selectError}
            </p>
          )}
          {installedModels.length === 0 ? (
            <p className="text-surface-panel text-sm">
              No models loaded yet. Connect the sidecar with Ollama running and
              models will appear here.
            </p>
          ) : (
            installedModels.map((name) => {
              const active = name === selectedModel;
              return (
                <div
                  key={name}
                  className={`flex items-center justify-between rounded-lg border px-3 py-2 text-sm ${
                    active
                      ? "border-accent-cyan/50 bg-accent-cyan/10 text-light"
                      : "border-surface-panel text-surface-panel"
                  }`}
                >
                  <span className="truncate">{name}</span>
                  {active ? (
                    <Badge variant="ok">selected</Badge>
                  ) : (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        void selectModel(name);
                      }}
                    >
                      Select
                    </Button>
                  )}
                </div>
              );
            })
          )}
        </div>
      </Card>
      <Card>
        <CardHeader
          title="Audio providers"
          subtitle="Local speech pipeline status"
        />
        <div className="p-4 space-y-2 text-sm">
          {audioStatus ? (
            <>
              <div className="flex items-center justify-between">
                <span className="text-surface-panel">
                  STT: {audioStatus.stt_provider} ({audioStatus.stt_model})
                </span>
                <Badge variant={audioStatus.stt_installed ? "ok" : "idle"}>
                  {audioStatus.stt_installed ? "ready" : "not installed"}
                </Badge>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-surface-panel">
                  TTS: {audioStatus.tts_provider}
                </span>
                <Badge variant={audioStatus.tts_installed ? "ok" : "idle"}>
                  {audioStatus.tts_installed ? "ready" : "not installed"}
                </Badge>
              </div>
            </>
          ) : (
            <p className="text-surface-panel text-sm">
              Audio status appears here once the sidecar connects.
            </p>
          )}
        </div>
      </Card>
    </div>
  );
}
function SettingsScreen() {
  const {
    speechEnabled,
    setSpeechEnabled,
    micEnabled,
    setMicEnabled,
    micPermissionGranted,
    reducedMotion,
    setReducedMotion,
  } = useAssistantStore();
  const { prefs: layoutPrefs, update: updateLayout } = useLayoutPrefs();
  const [accentSelection, setAccentSelection] = useState<AccentSelection>(
    () => loadAccent(),
  );
  const updateAccent = (next: AccentSelection) => {
    setAccentSelection(next);
    applyAccent(next);
  };
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader title="Appearance" subtitle="HUD accent color" />
        <div className="p-4 space-y-3 text-sm">
          <div
            className="flex flex-wrap gap-2"
            role="group"
            aria-label="Accent color presets"
          >
            {ACCENT_PRESETS.map((preset) => (
              <button
                key={preset.id}
                type="button"
                onClick={() =>
                  updateAccent({ preset: preset.id, hue: accentSelection.hue })
                }
                aria-pressed={accentSelection.preset === preset.id}
                title={preset.label}
                aria-label={`${preset.label} accent`}
                className={`w-9 h-9 rounded-full border-2 transition-transform ${
                  accentSelection.preset === preset.id
                    ? "border-light scale-110"
                    : "border-transparent"
                }`}
                style={{
                  backgroundColor: `rgb(${preset.accent[0]} ${preset.accent[1]} ${preset.accent[2]})`,
                }}
              />
            ))}
          </div>
          <label className="flex items-center justify-between gap-4">
            <span className="text-light">
              Custom hue
              <span className="block text-xs text-surface-panel">
                Fine-tune the accent; switches to the custom color.
              </span>
            </span>
            <input
              type="range"
              min={0}
              max={359}
              value={accentSelection.hue}
              onChange={(e) =>
                updateAccent({
                  preset: "custom",
                  hue: Number(e.target.value),
                })
              }
              aria-label="Custom accent hue"
            />
          </label>
        </div>
      </Card>
      <Card>
        <CardHeader title="Settings" subtitle="Voice and interface" />
        <div className="p-4 space-y-3 text-sm">
          <label className="flex items-center justify-between gap-4">
            <span className="text-light">
              Speak replies out loud
              <span className="block text-xs text-surface-panel">
                Uses your system voice. Captions always stay on screen.
              </span>
            </span>
            <input
              type="checkbox"
              checked={speechEnabled}
              onChange={(e) => setSpeechEnabled(e.target.checked)}
              aria-label="Speak replies out loud"
            />
          </label>
          <label className="flex items-center justify-between gap-4">
            <span className="text-light">
              Microphone enabled
              <span className="block text-xs text-surface-panel">
                {micPermissionGranted
                  ? "Permission granted by the browser."
                  : "Permission not granted yet — allow it when prompted."}
              </span>
            </span>
            <input
              type="checkbox"
              checked={micEnabled}
              onChange={(e) => setMicEnabled(e.target.checked)}
              aria-label="Microphone enabled"
            />
          </label>
          <label className="flex items-center justify-between gap-4">
            <span className="text-light">
              Reduced motion
              <span className="block text-xs text-surface-panel">
                Still orb and waveform; calms non-essential animation.
              </span>
            </span>
            <input
              type="checkbox"
              checked={reducedMotion}
              onChange={(e) => setReducedMotion(e.target.checked)}
              aria-label="Reduced motion"
            />
          </label>
        </div>
      </Card>
      <Card>
        <CardHeader title="Layout" subtitle="Adaptive workspace" />
        <div className="p-4 space-y-3 text-sm">
          <label className="flex items-center justify-between gap-4">
            <span className="text-light">
              Collapse navigation
              <span className="block text-xs text-surface-panel">
                Icon-only sidebar for more workspace.
              </span>
            </span>
            <input
              type="checkbox"
              checked={layoutPrefs.navCollapsed}
              onChange={(e) =>
                updateLayout({ navCollapsed: e.target.checked })
              }
              aria-label="Collapse navigation"
            />
          </label>
          <label className="flex items-center justify-between gap-4">
            <span className="text-light">
              Compact mode
              <span className="block text-xs text-surface-panel">
                Tighter spacing throughout the UI.
              </span>
            </span>
            <input
              type="checkbox"
              checked={layoutPrefs.compact}
              onChange={(e) => updateLayout({ compact: e.target.checked })}
              aria-label="Compact mode"
            />
          </label>
          <label className="flex flex-col gap-2">
            <span className="text-light">
              Panel transparency
              <span className="block text-xs text-surface-panel">
                Glass effect for side panels (
                {Math.round(layoutPrefs.panelOpacity * 100)}%).
              </span>
            </span>
            <input
              type="range"
              min={40}
              max={100}
              value={Math.round(layoutPrefs.panelOpacity * 100)}
              onChange={(e) =>
                updateLayout({ panelOpacity: Number(e.target.value) / 100 })
              }
              aria-label="Panel transparency"
            />
          </label>
        </div>
      </Card>
      <Card>
        <CardHeader title="Privacy" subtitle="Everything stays on this machine" />
        <div className="p-4 text-sm text-light">
          <p className="text-xs text-surface-panel">
            Microphone audio, transcription, inference, and memory are local.
            Raw audio is never retained. Telemetry is off.
          </p>
        </div>
      </Card>
    </div>
  );
}
