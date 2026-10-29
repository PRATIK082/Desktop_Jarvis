import { create } from "zustand";
import type {
  AssistantEvent,
  HealthResponse,
  ToolSchema,
} from "../../../../packages/contracts/src/index.ts";

export type AssistantStateStrict =
  | "booting"
  | "checking_dependencies"
  | "idle"
  | "wake_word_listening"
  | "recording"
  | "transcribing"
  | "thinking"
  | "proposing_action"
  | "awaiting_approval"
  | "executing"
  | "speaking"
  | "cancelling"
  | "offline"
  | "degraded"
  | "error";

interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  text: string;
  timestamp: string;
  turn_id?: string;
  is_final?: boolean;
  citations?: string[];
}

interface ApprovalCard {
  request_id: string;
  tool_id: string;
  arguments: Record<string, unknown>;
  risk_level: number;
  reason: string;
  expected_effect: string;
  status: "pending" | "approved_once" | "remembered" | "denied" | "cancelled";
}

interface LatencyMetric {
  name: string;
  duration_ms: number;
  turn_id?: string;
}

interface AssistantStore {
  // Connection / sidecar
  sidecarConnected: boolean;
  setSidecarConnected: (connected: boolean) => void;
  sidecarUrl: string | null;
  setSidecarUrl: (url: string | null) => void;
  authToken: string | null;
  setAuthToken: (token: string | null) => void;
  health: HealthResponse | null;
  setHealth: (health: HealthResponse | null) => void;

  // State machine
  state: AssistantStateStrict;
  setState: (state: AssistantStateStrict) => void;
  previousState: AssistantStateStrict | null;

  // Ollama
  ollamaHealthy: boolean;
  setOllamaHealthy: (healthy: boolean) => void;
  installedModels: string[];
  setInstalledModels: (models: string[]) => void;
  selectedModel: string | null;
  setSelectedModel: (model: string | null) => void;

  // Engine + audio capability status (from /health)
  engineActive: string | null;
  setEngineActive: (engine: string | null) => void;
  audioStatus: {
    stt_provider: string;
    stt_model: string;
    stt_installed: boolean;
    tts_provider: string;
    tts_installed: boolean;
  } | null;
  setAudioStatus: (
    status: {
      stt_provider: string;
      stt_model: string;
      stt_installed: boolean;
      tts_provider: string;
      tts_installed: boolean;
    } | null,
  ) => void;
  speechEnabled: boolean;
  setSpeechEnabled: (enabled: boolean) => void;
  continuousListening: boolean;
  setContinuousListening: (enabled: boolean) => void;
  muted: boolean;
  setMuted: (muted: boolean) => void;

  // Mic / audio
  micEnabled: boolean;
  setMicEnabled: (enabled: boolean) => void;
  micPermissionGranted: boolean;
  setMicPermissionGranted: (granted: boolean) => void;
  micListening: boolean;
  setMicListening: (listening: boolean) => void;
  audioLevel: number;
  setAudioLevel: (level: number) => void;
  inputDeviceId: string | null;
  setInputDeviceId: (id: string | null) => void;
  outputDeviceId: string | null;
  setOutputDeviceId: (id: string | null) => void;

  // Conversation
  messages: Message[];
  addMessage: (message: Message) => void;
  setMessages: (messages: Message[]) => void;
  clearMessages: () => void;
  currentTurnId: string | null;
  setCurrentTurnId: (id: string | null) => void;
  streamingText: string;
  setStreamingText: (text: string) => void;
  appendStreamingText: (delta: string) => void;

  // Transcript (live)
  liveTranscript: string;
  setLiveTranscript: (text: string) => void;
  clearLiveTranscript: () => void;

  // Approvals
  pendingApproval: ApprovalCard | null;
  setPendingApproval: (card: ApprovalCard | null) => void;
  approvalHistory: ApprovalCard[];
  addApproval: (card: ApprovalCard) => void;

  // Latency
  latencyMetrics: LatencyMetric[];
  addLatencyMetric: (metric: LatencyMetric) => void;
  clearLatencyMetrics: () => void;

  // Errors
  lastError: { code: string; message: string; recoverable: boolean } | null;
  setLastError: (
    error: { code: string; message: string; recoverable: boolean } | null,
  ) => void;
  clearLastError: () => void;

  // Tools
  tools: ToolSchema[];
  setTools: (tools: ToolSchema[]) => void;

  // UI
  sidePanelOpen: boolean;
  setSidePanelOpen: (open: boolean) => void;
  activeScreen:
    | "home"
    | "conversations"
    | "memory"
    | "knowledge"
    | "automations"
    | "activity"
    | "models"
    | "settings";
  setActiveScreen: (screen: AssistantStore["activeScreen"]) => void;
  reducedMotion: boolean;
  setReducedMotion: (reduced: boolean) => void;

  // Event processing
  processEvent: (event: AssistantEvent) => void;
}

export const useAssistantStore = create<AssistantStore>((set, get) => ({
  // Connection
  sidecarConnected: false,
  setSidecarConnected: (connected) => set({ sidecarConnected: connected }),
  sidecarUrl: null,
  setSidecarUrl: (url) => set({ sidecarUrl: url }),
  authToken: null,
  setAuthToken: (token) => set({ authToken: token }),
  health: null,
  setHealth: (health) => set({ health }),

  // State machine
  state: "booting",
  setState: (state) => set((prev) => ({ state, previousState: prev.state })),
  previousState: null,

  // Ollama
  ollamaHealthy: false,
  setOllamaHealthy: (healthy) => set({ ollamaHealthy: healthy }),
  installedModels: [],
  setInstalledModels: (models) => set({ installedModels: models }),
  selectedModel: null,
  setSelectedModel: (model) => set({ selectedModel: model }),

  // Engine + audio capability status (from /health)
  engineActive: null,
  setEngineActive: (engine) => set({ engineActive: engine }),
  audioStatus: null,
  setAudioStatus: (status) => set({ audioStatus: status }),
  speechEnabled: true,
  setSpeechEnabled: (enabled) => set({ speechEnabled: enabled }),
  continuousListening: false,
  setContinuousListening: (enabled) => set({ continuousListening: enabled }),
  muted: false,
  setMuted: (muted) => set({ muted }),

  // Mic / audio
  micEnabled: false,
  setMicEnabled: (enabled) => set({ micEnabled: enabled }),
  micPermissionGranted: false,
  setMicPermissionGranted: (granted) => set({ micPermissionGranted: granted }),
  micListening: false,
  setMicListening: (listening) => set({ micListening: listening }),
  audioLevel: 0,
  setAudioLevel: (level) => set({ audioLevel: level }),
  inputDeviceId: ((): string | null => {
    try {
      return window.localStorage.getItem("jarvis.inputDeviceId");
    } catch {
      return null;
    }
  })(),
  setInputDeviceId: (id) => set({ inputDeviceId: id }),
  outputDeviceId: null,
  setOutputDeviceId: (id) => set({ outputDeviceId: id }),

  // Conversation
  messages: [],
  addMessage: (message) =>
    set((prev) => ({ messages: [...prev.messages, message] })),
  setMessages: (messages) => set({ messages }),
  clearMessages: () => set({ messages: [], streamingText: "" }),
  currentTurnId: null,
  setCurrentTurnId: (id) => set({ currentTurnId: id }),
  streamingText: "",
  setStreamingText: (text) => set({ streamingText: text }),
  appendStreamingText: (delta) =>
    set((prev) => ({ streamingText: prev.streamingText + delta })),

  // Transcript
  liveTranscript: "",
  setLiveTranscript: (text) => set({ liveTranscript: text }),
  clearLiveTranscript: () => set({ liveTranscript: "" }),

  // Approvals
  pendingApproval: null,
  setPendingApproval: (card) => set({ pendingApproval: card }),
  approvalHistory: [],
  addApproval: (card) =>
    set((prev) => ({ approvalHistory: [...prev.approvalHistory, card] })),

  // Latency
  latencyMetrics: [],
  addLatencyMetric: (metric) =>
    set((prev) => ({ latencyMetrics: [...prev.latencyMetrics, metric] })),
  clearLatencyMetrics: () => set({ latencyMetrics: [] }),

  // Errors
  lastError: null,
  setLastError: (error) => set({ lastError: error }),
  clearLastError: () => set({ lastError: null }),

  // Tools
  tools: [],
  setTools: (tools) => set({ tools }),

  // UI
  sidePanelOpen: false,
  setSidePanelOpen: (open) => set({ sidePanelOpen: open }),
  activeScreen: "home",
  setActiveScreen: (screen) => set({ activeScreen: screen }),
  reducedMotion: false,
  setReducedMotion: (reduced) => set({ reducedMotion: reduced }),

  // Event processing
  processEvent: (event: AssistantEvent) => {
    const state = get();
    switch (event.type) {
      case "state_transition":
        set({
          state: (event.to_state ?? "idle") as AssistantStateStrict,
          previousState: state.state,
        });
        break;
      case "transcript":
        if (event.role === "user" && event.is_final) {
          set({
            liveTranscript: event.text,
            messages: [
              ...state.messages,
              {
                id: crypto.randomUUID(),
                role: "user",
                text: event.text,
                timestamp: new Date().toISOString(),
                turn_id: event.turn_id,
                is_final: true,
              },
            ],
            streamingText: "",
          });
        } else if (event.role === "assistant" && event.is_final) {
          set({
            messages: [
              ...state.messages,
              {
                id: crypto.randomUUID(),
                role: "assistant",
                text: event.text,
                timestamp: new Date().toISOString(),
                turn_id: event.turn_id,
                is_final: true,
              },
            ],
            streamingText: "",
          });
        }
        break;
      case "stream_chunk":
        set((prev) => ({ streamingText: prev.streamingText + event.delta }));
        break;
      case "tool_proposal":
        set({
          pendingApproval: {
            request_id: event.request_id,
            tool_id: event.tool_id,
            arguments: event.arguments,
            risk_level: event.risk_level,
            reason: event.reason,
            expected_effect: event.expected_effect,
            status: "pending",
          },
        });
        break;
      case "tool_result":
        set({
          messages: [
            ...state.messages,
            {
              id: crypto.randomUUID(),
              role: "system",
              text: `Tool ${event.tool_id}: ${
                event.success ? "completed" : "failed"
              }${event.error ? " — " + event.error : ""}`,
              timestamp: new Date().toISOString(),
            },
          ],
        });
        break;
      case "approval":
        set((prev) => ({
          pendingApproval:
            prev.pendingApproval?.request_id === event.request_id
              ? {
                  ...(prev.pendingApproval ?? {
                    request_id: "",
                    tool_id: "",
                    arguments: {},
                    risk_level: 0,
                    reason: "",
                    expected_effect: "",
                  }),
                  status: event.decision,
                }
              : null,
          approvalHistory: [
            ...prev.approvalHistory,
            {
              request_id: event.request_id,
              tool_id: "",
              arguments: {},
              risk_level: 0,
              reason: "",
              expected_effect: "",
              status: event.decision,
            },
          ],
        }));
        break;
      case "assistant_error":
        set({
          lastError: {
            code: event.code,
            message: event.message,
            recoverable: event.recoverable,
          },
          state: event.recoverable ? state.state : "error",
        });
        break;
      case "audio_level":
        set({ audioLevel: event.level });
        break;
      case "latency_metric":
        set((prev) => ({
          latencyMetrics: [...prev.latencyMetrics, event],
        }));
        break;
      case "model_status":
        set({
          ollamaHealthy: event.healthy,
          installedModels: event.installed,
          selectedModel: event.selected ?? state.selectedModel,
        });
        break;
    }
  },
}));
