import { describe, it, expect, beforeEach } from "vitest";
import { useAssistantStore } from "@/stores/assistant";

// Helper to get a fresh store instance (zustand create returns a hook; we use
// the internal state via the hook in a test component would be ideal, but here
// we test by calling the store's set/get through a minimal React-free approach
// using the store's internal `setState`/`getState` exposed by zustand).
// Zustand's create returns a hook with .getState and .setState statics.

describe("AssistantStore", () => {
  beforeEach(() => {
    // Reset store to a known state before each test
    useAssistantStore.setState({
      state: "idle",
      sidecarConnected: false,
      ollamaHealthy: false,
      micEnabled: false,
      messages: [],
      streamingText: "",
      liveTranscript: "",
      pendingApproval: null,
      approvalHistory: [],
      latencyMetrics: [],
      lastError: null,
      audioLevel: 0,
      tools: [],
      reducedMotion: false,
    });
  });

  it("initial state is idle", () => {
    expect(useAssistantStore.getState().state).toBe("idle");
  });

  it("setState updates state", () => {
    useAssistantStore.setState({ state: "recording" });
    expect(useAssistantStore.getState().state).toBe("recording");
  });

  it("setMicEnabled toggles mic", () => {
    useAssistantStore.setState({ micEnabled: true });
    expect(useAssistantStore.getState().micEnabled).toBe(true);
    useAssistantStore.setState({ micEnabled: false });
    expect(useAssistantStore.getState().micEnabled).toBe(false);
  });

  it("addMessage appends a message", () => {
    useAssistantStore.getState().addMessage({
      id: "m1",
      role: "user",
      text: "hello",
      timestamp: new Date().toISOString(),
    });
    const msgs = useAssistantStore.getState().messages;
    expect(msgs.length).toBe(1);
    expect(msgs[0].text).toBe("hello");
  });

  it("setStreamingText updates streaming text", () => {
    useAssistantStore.getState().setStreamingText("partial");
    expect(useAssistantStore.getState().streamingText).toBe("partial");
  });

  it("appendStreamingText appends delta", () => {
    useAssistantStore.getState().setStreamingText("he");
    useAssistantStore.getState().appendStreamingText("llo");
    expect(useAssistantStore.getState().streamingText).toBe("hello");
  });

  it("setPendingApproval sets and clears approval", () => {
    useAssistantStore.getState().setPendingApproval({
      request_id: "r1",
      tool_id: "test_tool",
      arguments: {},
      risk_level: 2,
      reason: "test",
      expected_effect: "effect",
      status: "pending",
    });
    expect(useAssistantStore.getState().pendingApproval?.request_id).toBe("r1");
    useAssistantStore.getState().setPendingApproval(null);
    expect(useAssistantStore.getState().pendingApproval).toBeNull();
  });

  it("addLatencyMetric appends a metric", () => {
    useAssistantStore.getState().addLatencyMetric({
      name: "total_llm",
      duration_ms: 1234,
    });
    const metrics = useAssistantStore.getState().latencyMetrics;
    expect(metrics.length).toBe(1);
    expect(metrics[0].name).toBe("total_llm");
  });

  it("setLastError and clearLastError", () => {
    useAssistantStore.getState().setLastError({
      code: "test_error",
      message: "Something went wrong",
      recoverable: true,
    });
    expect(useAssistantStore.getState().lastError?.code).toBe("test_error");
    useAssistantStore.getState().clearLastError();
    expect(useAssistantStore.getState().lastError).toBeNull();
  });

  it("clearMessages empties messages", () => {
    useAssistantStore.getState().addMessage({
      id: "m1",
      role: "user",
      text: "hi",
      timestamp: new Date().toISOString(),
    });
    useAssistantStore.getState().clearMessages();
    expect(useAssistantStore.getState().messages.length).toBe(0);
    expect(useAssistantStore.getState().streamingText).toBe("");
  });
});
