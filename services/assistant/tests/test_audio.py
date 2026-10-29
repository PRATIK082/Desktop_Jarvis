"""Audio pipeline tests — mock-based, no live microphone required.

Tests the voice pipeline components (VAD, buffer, devices, providers)
and the end-to-end pipeline using deterministic mock providers.
"""

import asyncio
from collections.abc import AsyncIterator

import pytest

import jarvis.audio.devices as devmod
import jarvis.audio.providers as provmod
from jarvis.audio.buffer import AudioChunk, BoundedAudioBuffer
from jarvis.audio.devices import AudioDevice, AudioDeviceManager
from jarvis.audio.pipeline import VoicePipeline
from jarvis.audio.providers import FasterWhisperSTT, PiperTTS, get_audio_status
from jarvis.audio.vad import VoiceActivityDetector
from jarvis.audio.wake_word import OpenWakeWordProvider
from jarvis.config import settings
from jarvis.orchestration.events import TranscriptEvent
from jarvis.providers.base import MockSTTProvider, MockTTSProvider

# ── VAD tests ──────────────────────────────────────────────────────────

def test_vad_detects_speech_above_threshold():
    vad = VoiceActivityDetector(threshold=0.01)
    # Loud 16-bit PCM chunk (near max amplitude)
    loud = b"\xff\x7f" * 100  # ~16384 amplitude
    assert vad.is_speech(loud) is True


def test_vad_rejects_silence_below_threshold():
    vad = VoiceActivityDetector(threshold=0.5)
    silent = b"\x00\x00" * 100
    assert vad.is_speech(silent) is False


def test_vad_threshold_clamping():
    vad = VoiceActivityDetector(threshold=0.02)
    vad.set_threshold(2.0)  # above 1.0 → clamped
    assert vad.threshold_value == 1.0
    vad.set_threshold(-1.0)  # below 0.0 → clamped
    assert vad.threshold_value == 0.0


# ── Buffer tests ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_buffer_put_and_get():
    buf = BoundedAudioBuffer(max_chunks=2)
    chunk = AudioChunk(data=b"\x00\x00", sample_rate=16000, channels=1, timestamp_ms=0.0)
    await buf.put(chunk)
    assert buf.qsize == 1
    got = await buf.get()
    assert got == chunk


@pytest.mark.asyncio
async def test_buffer_close_unblocks_consumer():
    buf = BoundedAudioBuffer(max_chunks=2)
    await buf.close()
    got = await buf.get()
    assert got is None


# ── Device tests ───────────────────────────────────────────────────────

def test_audio_device_dataclass():
    d = AudioDevice(id="0", name="Mic", is_input=True, sample_rate=16000, channels=1)
    assert d.id == "0"
    assert d.is_input is True


def test_device_manager_no_backend(monkeypatch):
    # Force sounddevice to be unavailable
    monkeypatch.setattr(devmod, "_sd", None)
    mgr = AudioDeviceManager()
    assert mgr.available is False
    assert mgr.input_devices() == []
    assert mgr.output_devices() == []
    assert mgr.default_input() is None


# ── Provider availability tests ────────────────────────────────────────

def test_faster_whisper_available_flag():
    stt = FasterWhisperSTT()
    # available is True/False depending on install; just check it's a bool
    assert isinstance(stt.available, bool)


def test_piper_available_flag():
    tts = PiperTTS()
    assert isinstance(tts.available, bool)


# ── Pipeline tests (mock providers, no live mic) ──────────────────────

class _DummyOrchestrator:
    """Minimal orchestrator stub for pipeline testing."""

    def __init__(self) -> None:
        self.turns = 0

    async def run_turn(self, user_input: str, conversation_id: str, request_id: str):
        self.turns += 1
        # Yield a final transcript event then stop
        yield TranscriptEvent(
            role="assistant",
            text=f"Echo: {user_input}",
            is_final=True,
            turn_id=request_id,
        )


@pytest.mark.asyncio
async def test_pipeline_full_turn_mock():
    stt = MockSTTProvider(transcripts=["hello jarvis"])
    tts = MockTTSProvider()
    orch = _DummyOrchestrator()
    pipe = VoicePipeline(orchestrator=orch, stt_provider=stt, tts_provider=tts)

    await pipe.start()
    assert pipe.current_state == "idle"

    # Feed audio into the buffer and run a turn
    chunk = __import__("jarvis.audio.buffer", fromlist=["AudioChunk"]).AudioChunk(
        data=b"\x00\x00" * 100,
        sample_rate=16000,
        channels=1,
        timestamp_ms=0.0,
    )
    await pipe.buffer.put(chunk)

    await pipe.start_recording()
    await pipe.stop_recording()

    assert orch.turns == 1
    assert pipe.latency_metrics.get("transcription", 0) >= 0

    await pipe.stop()
    assert pipe.current_state == "idle"


@pytest.mark.asyncio
async def test_pipeline_cancel_during_turn():
    stt = MockSTTProvider(transcripts=["hello"])
    tts = MockTTSProvider()
    orch = _DummyOrchestrator()
    pipe = VoicePipeline(orchestrator=orch, stt_provider=stt, tts_provider=tts)

    await pipe.start()
    pipe.request_cancel()
    await pipe.stop_recording()
    assert pipe.current_state == "idle"

    await pipe.stop()


# ── Wake-word tests ───────────────────────────────────────────────────


class _DetectingWakeWordProvider:
    """Mock wake-word provider that yields True on first detection."""

    def __init__(self, detections: list[bool] | None = None) -> None:
        self._detections = detections or [True]
        self._index = 0

    async def detect(self, audio_chunks: AsyncIterator[bytes]) -> AsyncIterator[bool]:
        if self._index < len(self._detections):
            value = self._detections[self._index]
            self._index += 1
            yield value
        return

    async def health(self) -> bool:
        return True


class _SilentWakeWordProvider:
    """Mock wake-word provider that never detects."""

    async def detect(self, audio_chunks: AsyncIterator[bytes]) -> AsyncIterator[bool]:
        return
        yield  # pragma: no cover — unreachable

    async def health(self) -> bool:
        return True


class _UnhealthyWakeWordProvider:
    """Mock wake-word provider that reports unhealthy."""

    async def detect(self, audio_chunks: AsyncIterator[bytes]) -> AsyncIterator[bool]:
        return
        yield  # pragma: no cover — unreachable

    async def health(self) -> bool:
        return False


def test_openwakeword_available_flag():
    ww = OpenWakeWordProvider()
    assert isinstance(ww.available, bool)


@pytest.mark.asyncio
async def test_pipeline_wake_word_detected():
    stt = MockSTTProvider(transcripts=["hello jarvis"])
    tts = MockTTSProvider()
    orch = _DummyOrchestrator()
    ww = _DetectingWakeWordProvider(detections=[True])
    pipe = VoicePipeline(
        orchestrator=orch,
        stt_provider=stt,
        tts_provider=tts,
        wake_word_provider=ww,
    )

    await pipe.start()
    assert pipe.current_state == "idle"

    # Feed audio into buffer; wake-word provider will detect.
    chunk = AudioChunk(
        data=b"\x00\x00" * 100,
        sample_rate=16000,
        channels=1,
        timestamp_ms=0.0,
    )
    await pipe.buffer.put(chunk)

    await pipe.start_wake_word_listening()
    # Wake-word detection runs as a task; await briefly for it to process.
    await asyncio.sleep(0.2)

    # After detection, pipeline should have started a turn (orchestrator called).
    assert orch.turns >= 1

    await pipe.stop()


@pytest.mark.asyncio
async def test_pipeline_wake_word_not_detected_returns_to_idle():
    stt = MockSTTProvider(transcripts=["hello"])
    tts = MockTTSProvider()
    orch = _DummyOrchestrator()
    ww = _SilentWakeWordProvider()
    pipe = VoicePipeline(
        orchestrator=orch,
        stt_provider=stt,
        tts_provider=tts,
        wake_word_provider=ww,
    )

    await pipe.start()
    assert pipe.current_state == "idle"

    chunk = AudioChunk(
        data=b"\x00\x00" * 100,
        sample_rate=16000,
        channels=1,
        timestamp_ms=0.0,
    )
    await pipe.buffer.put(chunk)

    await pipe.start_wake_word_listening()
    await asyncio.sleep(0.2)

    # No detection → no turn started, back to idle.
    assert orch.turns == 0
    assert pipe.current_state == "idle"

    await pipe.stop()


@pytest.mark.asyncio
async def test_pipeline_wake_word_unhealthy_stays_idle():
    stt = MockSTTProvider(transcripts=["hello"])
    tts = MockTTSProvider()
    orch = _DummyOrchestrator()
    ww = _UnhealthyWakeWordProvider()
    pipe = VoicePipeline(
        orchestrator=orch,
        stt_provider=stt,
        tts_provider=tts,
        wake_word_provider=ww,
    )

    await pipe.start()
    assert pipe.current_state == "idle"

    chunk = AudioChunk(
        data=b"\x00\x00" * 100,
        sample_rate=16000,
        channels=1,
        timestamp_ms=0.0,
    )
    await pipe.buffer.put(chunk)

    await pipe.start_wake_word_listening()
    await asyncio.sleep(0.2)

    # Unhealthy → no turn, back to idle (push-to-talk fallback).
    assert orch.turns == 0
    assert pipe.current_state == "idle"

    await pipe.stop()


@pytest.mark.asyncio
async def test_wake_word_disabled_uses_mock():
    """When wake_word_enabled is False, default provider is MockWakeWordProvider."""
    original = settings.wake_word_enabled
    settings.wake_word_enabled = False
    try:
        pipe = VoicePipeline(orchestrator=_DummyOrchestrator())
        assert pipe.wake_word is not None
        assert await pipe.wake_word.health() is not None  # Mock health works
    finally:
        settings.wake_word_enabled = original


# ── E2: lazy provider wiring tests ─────────────────────────────────────

def test_e2_stt_lazy_init_never_downloads():
    """Construction must not load models or require packages."""
    stt = FasterWhisperSTT()
    assert stt.model_name == settings.stt_model
    assert stt.available is False  # nothing loaded at construction
    assert isinstance(stt._load_error, (str, type(None)))


@pytest.mark.asyncio
async def test_e2_stt_health_is_bool():
    stt = FasterWhisperSTT()
    assert isinstance(await stt.health(), bool)


@pytest.mark.asyncio
async def test_e2_stt_warm_up_never_raises():
    stt = FasterWhisperSTT(model_name="tiny")
    assert isinstance(await stt.warm_up(), bool)


@pytest.mark.asyncio
async def test_e2_stt_transcribe_without_package_yields_nothing(monkeypatch):
    """Without faster-whisper installed, streaming yields no text (degraded)."""
    monkeypatch.setattr(provmod, "WhisperModel", None)
    stt = FasterWhisperSTT()

    async def _chunks() -> AsyncIterator[bytes]:
        yield b"\x00\x00" * 160

    out = [t async for t in stt.transcribe_stream(_chunks())]
    assert out == []


@pytest.mark.asyncio
async def test_e2_tts_health_and_warm_up():
    tts = PiperTTS()
    assert isinstance(await tts.health(), bool)
    assert isinstance(await tts.warm_up(), bool)


@pytest.mark.asyncio
async def test_e2_tts_synthesize_without_package_yields_nothing(monkeypatch):
    monkeypatch.setattr(provmod, "_piper", None)
    tts = PiperTTS()
    assert tts.available is False
    out = [c async for c in tts.synthesize_stream("hello")]
    assert out == []


def test_e2_audio_status_shape():
    """get_audio_status reports provider names + install flags, no secrets."""
    status = get_audio_status()
    assert set(status) == {
        "stt_provider", "stt_model", "stt_installed",
        "tts_provider", "tts_installed",
    }
    assert isinstance(status["stt_installed"], bool)
    assert isinstance(status["tts_installed"], bool)


@pytest.mark.asyncio
async def test_e2_pipeline_warm_up_never_raises():
    """warm_up_providers works with mock providers (no warm_up method)."""
    pipe = VoicePipeline(
        orchestrator=_DummyOrchestrator(),
        stt_provider=MockSTTProvider(),
        tts_provider=MockTTSProvider(),
    )
    results = await pipe.warm_up_providers()
    assert set(results) == {"stt", "tts"}


def test_e2_pipeline_defaults_follow_settings():
    """Default providers follow settings selection (E2: faster_whisper/piper)."""
    orig_stt = settings.stt_provider
    orig_tts = settings.tts_provider
    settings.stt_provider = "faster_whisper"
    settings.tts_provider = "piper"
    try:
        pipe = VoicePipeline(orchestrator=_DummyOrchestrator())
        assert isinstance(pipe.stt, FasterWhisperSTT)
        assert isinstance(pipe.tts, PiperTTS)
        # Lazy: construction alone loads nothing.
        assert pipe.stt.available is False
    finally:
        settings.stt_provider = orig_stt
        settings.tts_provider = orig_tts
