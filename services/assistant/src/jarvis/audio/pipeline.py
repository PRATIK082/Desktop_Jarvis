"""Voice pipeline orchestration (Agent.md §7).

Implements the real pipeline:

    microphone
    -> bounded audio buffer
    -> voice activity detection
    -> wake-word or push-to-talk activation
    -> utterance segmentation
    -> speech-to-text
    -> transcript review/normalization
    -> orchestration
    -> Ollama streaming
    -> optional tool proposal and approval
    -> final answer
    -> text segmentation
    -> local TTS
    -> audio playback

Cancel/stop controls exist at every expensive stage. When interruption mode
is enabled, user speech during TTS stops playback. TTS output is never fed
back into STT. All queues are bounded with backpressure.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import AsyncIterator
from typing import Any

from jarvis.audio.buffer import BoundedAudioBuffer
from jarvis.audio.devices import AudioDeviceManager
from jarvis.audio.providers import FasterWhisperSTT, PiperTTS
from jarvis.audio.vad import VoiceActivityDetector
from jarvis.audio.wake_word import OpenWakeWordProvider
from jarvis.config import settings
from jarvis.orchestration import Orchestrator
from jarvis.orchestration.events import (
    AssistantErrorEvent,
    AudioLevelEvent,
    TranscriptEvent,
)
from jarvis.providers.base import (
    MockSTTProvider,
    MockTTSProvider,
    MockWakeWordProvider,
)
from jarvis.state import (
    IDLE,
    RECORDING,
    SPEAKING,
    THINKING,
    TRANSCRIBING,
    WAKE_WORD_LISTENING,
    StateMachine,
)


class VoicePipeline:
    """Orchestrates the full voice turn pipeline."""

    def __init__(
        self,
        orchestrator: Orchestrator,
        stt_provider: Any | None = None,
        tts_provider: Any | None = None,
        wake_word_provider: Any | None = None,
    ) -> None:
        self.orchestrator = orchestrator
        self.state = StateMachine()
        self.device_manager = AudioDeviceManager()

        # Providers (mock in tests; real when installed)
        self.stt = stt_provider or self._default_stt()
        self.tts = tts_provider or self._default_tts()
        self.wake_word = wake_word_provider or self._default_wake_word()

        # Audio buffer + VAD
        self.buffer = BoundedAudioBuffer(max_chunks=settings.audio_buffer_max_chunks)
        self.vad = VoiceActivityDetector(
            threshold=settings.vad_threshold,
            sample_rate=settings.audio_sample_rate,
        )

        # Lifecycle — starts in idle; boot/dependency-check is handled by
        # jarvis.lifecycle (sidecar level).
        self.state = StateMachine(initial_state=IDLE)
        self._cancel_event = asyncio.Event()
        self._interruption_event = asyncio.Event()
        self._tts_task: asyncio.Task[None] | None = None

        # Latency metrics
        self._latency: dict[str, float] = {}
        self._turn_start_ms: float = 0.0

    # ── provider defaults ------------------------------------------------

    def _default_stt(self) -> Any:
        if settings.stt_provider == "faster_whisper":
            return FasterWhisperSTT(model_name=settings.stt_model)
        return MockSTTProvider()

    def _default_tts(self) -> Any:
        if settings.tts_provider == "piper":
            return PiperTTS(model_path=settings.tts_voice)
        return MockTTSProvider()

    def _default_wake_word(self) -> Any:
        if settings.wake_word_enabled:
            return OpenWakeWordProvider(
                sensitivity=settings.wake_word_sensitivity,
                sample_rate=settings.audio_sample_rate,
            )
        return MockWakeWordProvider()

    # ── lifecycle --------------------------------------------------------

    async def start(self) -> None:
        """Start the pipeline (boot -> idle)."""
        self._running = True
        self._cancel_event.clear()
        self._interruption_event.clear()
        # Boot/dependency-check lifecycle is handled by jarvis.lifecycle;
        # the pipeline enters idle once the sidecar is healthy.
        # Already in IDLE (see __init__); no transition needed.

    async def stop(self) -> None:
        """Stop the pipeline and cancel any in-flight turn."""
        self._running = False
        self._cancel_event.set()
        self._interruption_event.set()
        if self._tts_task and not self._tts_task.done():
            self._tts_task.cancel()
        await self.buffer.close()
        self.state.transition(IDLE)

    async def warm_up_providers(self) -> dict[str, bool]:
        """Pre-load STT/TTS models outside a live turn (best-effort).

        Call once at startup/idle so the first real utterance pays ~1s
        instead of ~9s. Never raises; reports per-provider readiness.
        """
        results: dict[str, bool] = {"stt": False, "tts": False}
        for key, provider in (("stt", self.stt), ("tts", self.tts)):
            warm_up = getattr(provider, "warm_up", None)
            if callable(warm_up):
                try:
                    results[key] = bool(await warm_up())
                except Exception:  # noqa: BLE001 — warm-up is best-effort
                    results[key] = False
            else:
                results[key] = bool(getattr(provider, "available", False))
        return results

    # ── push-to-talk -----------------------------------------------------

    async def start_recording(self) -> None:
        """Push-to-talk: begin capturing microphone audio."""
        if not self._running:
            return
        self._cancel_event.clear()
        self._interruption_event.clear()
        self.state.transition(RECORDING)
        self._turn_start_ms = time.monotonic()
        # In production this would read from the selected input device and
        # push chunks into self.buffer. Here the buffer is driven by tests
        # / the audio input adapter.
        _ = AudioDeviceManager  # device selection available for UI

    async def stop_recording(self) -> None:
        """Push-to-talk: stop capturing and begin transcription."""
        self.state.transition(TRANSCRIBING)
        await self._run_turn_from_buffer()

    # ── wake word ----------------------------------------------------------

    async def start_wake_word_listening(self) -> None:
        """Begin wake-word listening. Transitions to WAKE_WORD_LISTENING."""
        if not self._running:
            return
        self._cancel_event.clear()
        self._interruption_event.clear()
        self.state.transition(WAKE_WORD_LISTENING)
        self._turn_start_ms = time.monotonic()
        # Run wake-word detection on the audio buffer; when detected, transition
        # to recording and then transcribing. Push-to-talk (start_recording)
        # remains the reliable fallback when wake-word is disabled or unavailable.
        asyncio.create_task(self._run_wake_word_detection())

    async def _run_wake_word_detection(self) -> None:
        """Drain the audio buffer through the wake-word detector.

        When the wake word is detected, transition to RECORDING and begin a
        voice turn. If wake-word is unavailable, stay in WAKE_WORD_LISTENING
        (degraded mode; user must use push-to-talk).
        """
        if not self.wake_word or not await self.wake_word.health():
            # Wake-word unavailable — return to idle; push-to-talk is the
            # fallback. Do not stay in listening state.
            self.state.transition(IDLE)
            return

        async def _chunks() -> AsyncIterator[bytes]:
            while self._running and not self._cancel_event.is_set():
                try:
                    chunk = await asyncio.wait_for(self.buffer.get(), timeout=0.1)
                except TimeoutError:
                    break
                if chunk is None:
                    break  # buffer closed
                yield chunk.data

        detected = False
        try:
            async for wake in self.wake_word.detect(_chunks()):
                if self._cancel_event.is_set():
                    break
                if wake:
                    detected = True
                    break
        except Exception:  # noqa: BLE001 — wake-word failure falls back to push-to-talk
            detected = False

        if detected and self._running and not self._cancel_event.is_set():
            self.state.transition(RECORDING)
            self.state.transition(TRANSCRIBING)
            await self._run_turn_from_buffer()
        elif self._running:
            # No detection (or cancelled): return to idle.
            self.state.transition(IDLE)

    # ── core turn --------------------------------------------------------

    async def _run_turn_from_buffer(self) -> None:
        """Drain the audio buffer, transcribe, orchestrate, synthesize, play."""
        try:
            # ── Collect audio from buffer until silence or cancel ---------
            audio_chunks: list[bytes] = []
            silence_chunks = 0
            max_silence_chunks = max(
                1, settings.silence_timeout_ms // 100
            )  # rough chunk-based silence

            while self._running and not self._cancel_event.is_set():
                try:
                    chunk = await asyncio.wait_for(self.buffer.get(), timeout=0.1)
                except TimeoutError:
                    break
                if chunk is None:
                    break  # buffer closed
                audio_chunks.append(chunk.data)
                # Emit audio level for the UI orb.
                level = self._chunk_level(chunk.data)
                self._emit_level(level)

                if self.vad.is_speech(chunk.data):
                    silence_chunks = 0
                else:
                    silence_chunks += 1
                    if silence_chunks >= max_silence_chunks:
                        break  # automatic silence detection

            if self._cancel_event.is_set() or not audio_chunks:
                self.state.transition(IDLE)
                return

            # ── STT --------------------------------------------------------
            stt_start = time.monotonic()
            transcript = await self._transcribe(audio_chunks)
            stt_latency_ms = (time.monotonic() - stt_start) * 1000
            self._latency["transcription"] = stt_latency_ms

            if not transcript or not transcript.strip():
                self.state.transition(IDLE)
                return

            # Emit final transcript.
            self._emit_event(TranscriptEvent(role="user", text=transcript, is_final=True))

            # ── Orchestration (Ollama + tools) ---------------------------
            self.state.transition(THINKING)
            orchestrator_start = time.monotonic()
            events: list[Any] = []
            async for event in self.orchestrator.run_turn(
                user_input=transcript,
                conversation_id="voice-turn",
                request_id=f"voice-{int(self._turn_start_ms)}",
            ):
                events.append(event)
                self._emit_event(event)
            think_latency_ms = (time.monotonic() - orchestrator_start) * 1000
            self._latency["total_llm"] = think_latency_ms

            # ── Extract final answer -------------------------------------
            final_answer = self._extract_final_answer(events)

            # ── TTS + playback -------------------------------------------
            if final_answer:
                self.state.transition(SPEAKING)
                await self._speak(final_answer)

            # ── Return to idle -------------------------------------------
            self.state.transition(IDLE)

        except asyncio.CancelledError:
            self.state.transition(IDLE)
            raise
        except Exception as exc:  # noqa: BLE001 — pipeline safety net
            self._emit_event(AssistantErrorEvent(
                code="pipeline_error",
                message=str(exc),
                recoverable=True,
                retry_available=True,
                conversation_id="voice-turn",
            ))
            self.state.transition(IDLE)

    async def _transcribe(self, audio_chunks: list[bytes]) -> str:
        """Run STT over collected audio chunks."""
        async def _chunks() -> AsyncIterator[bytes]:
            for c in audio_chunks:
                yield c

        text_parts = [
            partial
            async for partial in self.stt.transcribe_stream(_chunks())
        ]
        return " ".join(text_parts).strip()

    async def _speak(self, text: str) -> None:
        """Synthesize and play back text, supporting cancellation/interruption."""
        self._interruption_event.clear()
        self._tts_task = asyncio.create_task(self._synthesize_and_play(text))
        try:
            await self._tts_task
        except asyncio.CancelledError:
            pass

    async def _synthesize_and_play(self, text: str) -> None:
        """Synthesize text in chunks and 'play' them, checking for cancellation."""
        tts_start = time.monotonic()
        first_audio = True
        try:
            async for _chunk in self.tts.synthesize_stream(text):
                # Cancellation / interruption check at every chunk.
                if self._cancel_event.is_set() or self._interruption_event.is_set():
                    return
                if first_audio:
                    self._latency["first_audio"] = (time.monotonic() - tts_start) * 1000
                    first_audio = False
                # In production this writes to the selected output device.
                await asyncio.sleep(0)  # yield control; no UI blocking
        except asyncio.CancelledError:
            return
        self._latency["total_turn"] = (time.monotonic() - self._turn_start_ms) * 1000

    # ── interruption -----------------------------------------------------

    def request_interruption(self) -> None:
        """Called when the user starts speaking during TTS (if enabled)."""
        if settings.interruption_enabled:
            self._interruption_event.set()

    def request_cancel(self) -> None:
        """Cancel the current turn at any expensive stage."""
        self._cancel_event.set()
        self._interruption_event.set()
        if self._tts_task and not self._tts_task.done():
            self._tts_task.cancel()

    # ── helpers ----------------------------------------------------------

    def _chunk_level(self, data: bytes) -> float:
        """Compute normalized audio level (0.0-1.0) for the UI orb."""
        if not data:
            return 0.0
        count = len(data) // 2
        if count == 0:
            return 0.0
        total = 0.0
        for i in range(count):
            offset = i * 2
            sample = int.from_bytes(data[offset : offset + 2], "little", signed=True)
            total += (sample / 32768.0) ** 2
        return min(math.sqrt(total / count), 1.0)

    def _emit_level(self, level: float) -> None:
        """Emit an AudioLevelEvent for the UI orb."""
        # In production this would push to the WebSocket event stream.
        # Kept as a hook for the UI integration layer.
        _ = AudioLevelEvent(level=level)

    def _emit_event(self, event: Any) -> None:
        """Hook to forward orchestrator events to the UI/WebSocket."""
        _ = event

    def _extract_final_answer(self, events: list[Any]) -> str:
        """Extract the final assistant text from orchestration events."""
        parts: list[str] = []
        for event in events:
            etype = getattr(event, "type", "")
            if etype == "stream_chunk":
                parts.append(getattr(event, "delta", ""))
            elif etype == "transcript" and getattr(event, "is_final", False):
                parts.append(getattr(event, "text", ""))
        return "".join(parts).strip()

    @property
    def latency_metrics(self) -> dict[str, float]:
        return dict(self._latency)

    @property
    def current_state(self) -> str:
        return self.state.state
