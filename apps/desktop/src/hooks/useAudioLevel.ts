import { useEffect } from "react";
import { useAssistantStore } from "../stores/assistant";

const LISTENING_STATES = new Set([
  "recording",
  "wake_word_listening",
  "transcribing",
]);
const TALKING_STATES = new Set([
  "speaking",
  "thinking",
  "proposing_action",
  "executing",
]);

/**
 * useAudioLevel — drives store.audioLevel from a real source.
 *
 * - While the assistant is listening: opens the microphone via
 *   getUserMedia + AnalyserNode and publishes smoothed RMS (~10 Hz).
 * - While the assistant is speaking/thinking: publishes a gentle
 *   synthetic pulse (static mid value when reduced-motion is on).
 * - Otherwise: decays the level to 0.
 *
 * Mic stream + AudioContext are torn down on every state change and on
 * unmount (StrictMode-safe). Failures are silent by design: the orb and
 * waveform simply rest at 0. Raw audio is never stored.
 */
export function useAudioLevel() {
  const state = useAssistantStore((s) => s.state);
  const micPermissionGranted = useAssistantStore((s) => s.micPermissionGranted);
  const reducedMotion = useAssistantStore((s) => s.reducedMotion);
  const inputDeviceId = useAssistantStore((s) => s.inputDeviceId);
  const micListening = useAssistantStore((s) => s.micListening);

  useEffect(() => {
    const { setAudioLevel } = useAssistantStore.getState();
    let stopped = false;
    let rafId = 0;
    let pulseId: ReturnType<typeof setInterval> | null = null;
    let stream: MediaStream | null = null;
    let ctx: AudioContext | null = null;

    const teardown = () => {
      stopped = true;
      cancelAnimationFrame(rafId);
      if (pulseId !== null) {
        clearInterval(pulseId);
        pulseId = null;
      }
      stream?.getTracks().forEach((t) => t.stop());
      stream = null;
      void ctx?.close().catch(() => undefined);
      ctx = null;
    };

    const listening = LISTENING_STATES.has(state) || micListening;
    if (listening && micPermissionGranted) {
      if (!navigator.mediaDevices?.getUserMedia) {
        setAudioLevel(0);
        return teardown;
      }
      let smoothed = 0;
      let lastPush = 0;
      const constraints: MediaStreamConstraints = {
        audio: inputDeviceId
          ? { deviceId: { exact: inputDeviceId } }
          : true,
      };
      navigator.mediaDevices
        .getUserMedia(constraints)
        .then((s) => {
          if (stopped) {
            s.getTracks().forEach((t) => t.stop());
            return;
          }
          stream = s;
          ctx = new AudioContext();
          const src = ctx.createMediaStreamSource(s);
          const analyser = ctx.createAnalyser();
          analyser.fftSize = 1024;
          src.connect(analyser);
          const buf = new Uint8Array(analyser.fftSize);
          const tick = () => {
            if (stopped) return;
            analyser.getByteTimeDomainData(buf);
            let sum = 0;
            for (let i = 0; i < buf.length; i++) {
              const v = (buf[i] - 128) / 128;
              sum += v * v;
            }
            const rms = Math.min(1, Math.sqrt(sum / buf.length) * 2.2);
            smoothed = smoothed * 0.65 + rms * 0.35;
            const now = performance.now();
            if (now - lastPush > 100) {
              lastPush = now;
              setAudioLevel(Number(smoothed.toFixed(3)));
            }
            rafId = requestAnimationFrame(tick);
          };
          tick();
        })
        .catch(() => setAudioLevel(0));
      return teardown;
    }

    if (TALKING_STATES.has(state)) {
      if (reducedMotion) {
        setAudioLevel(0.4);
      } else {
        pulseId = setInterval(() => {
          if (stopped) return;
          const level = 0.45 + 0.35 * Math.sin(Date.now() / 300);
          setAudioLevel(Number(level.toFixed(3)));
        }, 120);
      }
      return teardown;
    }

    setAudioLevel(0);
    return teardown;
  }, [state, micPermissionGranted, reducedMotion, inputDeviceId, micListening]);
}
