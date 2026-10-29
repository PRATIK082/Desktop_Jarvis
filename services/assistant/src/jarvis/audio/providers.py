"""STT / TTS provider implementations (Agent.md §7).

Real providers (faster-whisper for STT, Piper for TTS) are implemented
behind try/import guards so the sidecar stays operational when they are
not installed (degraded mode). Tests use the deterministic Mock* providers
from `jarvis.providers.base` which require no microphone or model.
"""

from __future__ import annotations

import asyncio
import io
from collections.abc import AsyncIterator
from typing import Any

try:
    import numpy as _np
except ImportError:  # pragma: no cover — numpy optional
    _np = None  # type: ignore[assignment]

try:
    from faster_whisper import WhisperModel
except ImportError:  # pragma: no cover — faster-whisper optional
    WhisperModel = None

try:
    import av as _av
except ImportError:  # pragma: no cover — av optional (pulled by faster-whisper)
    _av = None  # type: ignore[assignment]

try:
    import piper as _piper
except ImportError:  # pragma: no cover — piper optional
    _piper = None

from jarvis.config import settings
from jarvis.telemetry.logger import log_event


class FasterWhisperSTT:
    """STT using faster-whisper (local Whisper via CTranslate2).

    Clean-room implementation. The model is loaded lazily — construction
    never imports heavy packages or downloads anything, so the sidecar
    starts fast and stays operational when faster-whisper is not
    installed (degraded mode). First transcription (or an explicit
    :meth:`warm_up`) triggers the one-time download + load.
    """

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or settings.stt_model
        self._model: Any = None
        self._load_error: str | None = None

    def _ensure_loaded(self) -> bool:
        """Load the model on first use. Returns True when ready."""
        if self._model is not None:
            return True
        if WhisperModel is None:
            self._load_error = "faster-whisper not installed"
            return False
        try:
            self._model = WhisperModel(
                self.model_name,
                device="cpu",
                compute_type="int8",
            )
        except Exception as exc:  # noqa: BLE001 — model load failure is non-fatal
            log_event(
                "jarvis.audio.providers",
                "faster_whisper_load_failed",
                level="warn",
                details={"error": str(exc)},
            )
            self._model = None
            self._load_error = str(exc)
            return False
        return True

    async def warm_up(self) -> bool:
        """Pre-load the model (one-time download) outside a live turn.

        Call once at startup/idle so the first real utterance pays ~1s
        instead of ~9s. Never raises.
        """
        return await asyncio.to_thread(self._ensure_loaded)

    @property
    def available(self) -> bool:
        """True once the model is loaded and ready to transcribe."""
        return self._model is not None

    async def health(self) -> bool:
        """True when the faster-whisper package is importable."""
        return WhisperModel is not None

    async def transcribe_stream(
        self, audio_chunks: AsyncIterator[bytes]
    ) -> AsyncIterator[str]:
        """Transcribe streaming audio chunks into text.

        Buffers chunks into a list, then transcribes the accumulated
        utterance. Yields the final transcript.
        """
        buffer = [chunk async for chunk in audio_chunks]
        if not buffer:
            return
        ready = await asyncio.to_thread(self._ensure_loaded)
        if not ready:
            return
        audio = b"".join(buffer)
        text = await asyncio.to_thread(self._transcribe, audio)
        if text.strip():
            yield text

    async def transcribe_audio(self, audio: bytes, suffix: str = ".webm") -> str:
        """Transcribe a complete audio blob (any format av can decode).

        Writes the blob to a temp file and lets faster-whisper/av decode
        it. Returns the transcript text (empty string on failure).
        """
        if not audio:
            return ""
        ready = await asyncio.to_thread(self._ensure_loaded)
        if not ready:
            return ""
        import os
        import tempfile

        fd, path = tempfile.mkstemp(suffix=suffix)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(audio)
            text = await asyncio.to_thread(self._transcribe_file, path)
            return text
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    def _transcribe_file(self, path: str) -> str:
        """Blocking transcription of an audio file path.

        Decodes the audio with PyAV into a 16 kHz mono float32 PCM array
        and feeds that to faster-whisper, avoiding faster-whisper's own
        av.open(..., metadata_errors=...) call which is incompatible with
        the installed PyAV version.
        """
        if self._model is None:
            return ""
        try:
            samples = self._decode_audio_to_pcm(path)
            if samples is None or len(samples) == 0:
                log_event(
                    "jarvis.audio.providers",
                    "faster_whisper_transcribe_failed",
                    level="warn",
                    details={"error": "no audio samples decoded", "path": path},
                )
                return ""
            duration_s = len(samples) / 16000.0
            segments, _ = self._model.transcribe(
                samples, language=settings.stt_language
            )
            text = "".join(seg.text for seg in segments)
            log_event(
                "jarvis.audio.providers",
                "faster_whisper_transcribed",
                level="info",
                details={"chars": len(text), "duration_s": round(duration_s, 2)},
            )
            return text
        except Exception as exc:  # noqa: BLE001 — transcription failure is non-fatal
            log_event(
                "jarvis.audio.providers",
                "faster_whisper_transcribe_failed",
                level="warn",
                details={"error": str(exc)},
            )
            return ""

    def _decode_audio_to_pcm(self, path: str) -> Any:
        """Decode an audio file to a 16 kHz mono float32 numpy array."""
        if _av is None or _np is None:
            return None
        try:
            container = _av.open(path)
            stream = container.streams.audio[0]
            resampler = _av.AudioResampler(
                format="fltp", layout="mono", rate=16000
            )
            chunks: list[Any] = []
            for frame in container.decode(stream):
                for resampled in resampler.resample(frame):
                    arr = resampled.to_ndarray()
                    if arr.ndim > 1:
                        arr = arr[0]
                    chunks.append(arr)
            container.close()
            if not chunks:
                return None
            return _np.concatenate(chunks).astype(_np.float32)
        except Exception as exc:  # noqa: BLE001
            log_event(
                "jarvis.audio.providers",
                "audio_decode_failed",
                level="warn",
                details={"error": str(exc)},
            )
            return None

    def _transcribe(self, audio: bytes) -> str:
        """Blocking transcription of raw 16-bit PCM audio."""
        if self._model is None or _np is None:
            return ""
        samples = _np.frombuffer(audio, dtype=_np.int16).astype(_np.float32) / 32768.0
        segments, _ = self._model.transcribe(samples, language=settings.stt_language)
        return "".join(seg.text for seg in segments)


class PiperTTS:
    """TTS using Piper (local neural text-to-speech).

    Clean-room implementation. Falls back gracefully if Piper is not
    installed. The voice model loads lazily on first synthesis (or via
    :meth:`warm_up`) so startup never pays for audio.
    """

    def __init__(self, model_path: str | None = None) -> None:
        self.model_path = model_path if model_path is not None else settings.tts_voice
        self._piper_module: Any = None
        self._voice: Any = None
        if _piper is not None:
            self._piper_module = _piper

    @property
    def available(self) -> bool:
        """True when the Piper package is importable."""
        return self._piper_module is not None

    async def health(self) -> bool:
        """True when the Piper package is importable."""
        return self._piper_module is not None

    async def warm_up(self) -> bool:
        """Pre-load the voice model outside a live turn. Never raises."""
        return await asyncio.to_thread(self._ensure_voice_loaded)

    def _ensure_voice_loaded(self) -> bool:
        if self._piper_module is None:
            return False
        if self._voice is not None or not self.model_path:
            return self._piper_module is not None
        try:
            self._voice = self._piper_module.PiperVoice.load(self.model_path)
        except Exception as exc:  # noqa: BLE001 — voice load failure is non-fatal
            log_event(
                "jarvis.audio.providers",
                "piper_voice_load_failed",
                level="warn",
                details={"error": str(exc)},
            )
            self._voice = None
            return False
        return True

    async def synthesize_stream(
        self, text: str
    ) -> AsyncIterator[bytes]:
        """Synthesize text into streaming PCM audio bytes."""
        if not self.available:
            return
        audio = await asyncio.to_thread(self._synthesize, text)
        # Yield in chunks for streaming playback.
        chunk_size = settings.audio_chunk_size * 2  # 2 bytes per int16 sample
        for i in range(0, len(audio), chunk_size):
            yield audio[i : i + chunk_size]

    def _synthesize(self, text: str) -> bytes:
        """Blocking synthesis of text into 16-bit PCM audio."""
        if not self.available:
            return b""
        # Piper API varies by version; use a best-effort call.
        try:
            voice = self._voice
            if voice is None and self.model_path:
                self._ensure_voice_loaded()
                voice = self._voice
            if voice is not None:
                wav_buf = io.BytesIO()
                voice.synthesize(text, wav_buf)
                return wav_buf.getvalue()
        except Exception as exc:  # noqa: BLE001 — synthesis failure is non-fatal
            log_event(
                "jarvis.audio.providers",
                "piper_synthesize_failed",
                level="warn",
                details={"error": str(exc)},
            )
        return b""


def is_faster_whisper_installed() -> bool:
    """True when the faster-whisper package is importable (no model load)."""
    return WhisperModel is not None


def is_piper_installed() -> bool:
    """True when the piper package is importable."""
    return _piper is not None


def get_audio_status() -> dict[str, object]:
    """Audio provider status for /health (no model downloads, no secrets)."""
    return {
        "stt_provider": settings.stt_provider,
        "stt_model": settings.stt_model,
        "stt_installed": is_faster_whisper_installed(),
        "tts_provider": settings.tts_provider,
        "tts_installed": is_piper_installed(),
    }
