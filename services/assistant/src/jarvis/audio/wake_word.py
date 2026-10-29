"""Wake-word detection provider (Agent.md §7).

openWakeWord implementation behind the WakeWordProvider interface, with a
deterministic mock for tests. Degrades gracefully when openWakeWord is not
installed; push-to-talk remains the reliable fallback.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import numpy as _np

try:
    from openwakeword import Model  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover — openWakeWord optional
    Model = None


class OpenWakeWordProvider:
    """Wake-word detection using openWakeWord (local, on-device).

    Streams audio chunks and yields True when the wake word is detected.
    Sensitivity is configurable via the model's detection threshold.
    """

    def __init__(
        self,
        wake_word: str = "jarvis",
        sensitivity: float = 0.5,
        sample_rate: int = 16000,
    ) -> None:
        self.wake_word = wake_word
        self.sensitivity = max(0.0, min(1.0, sensitivity))
        self.sample_rate = sample_rate
        self._model: Any = None
        self._available = False
        self._load()

    def _load(self) -> None:
        if Model is None:
            self._available = False
            return
        try:
            self._model = Model(wakeword_models=[self.wake_word])
            self._available = True
        except Exception:  # noqa: BLE001 — model load failure is non-fatal
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    async def detect(self, audio_chunks: AsyncIterator[bytes]) -> AsyncIterator[bool]:
        """Yield True when the wake word is detected in the audio stream."""
        if not self._available:
            return
        # openWakeWord expects 16-bit PCM at 16kHz; 1280 samples = 80ms frame.
        frame_size = 1280
        buffer: list[bytes] = []
        async for chunk in audio_chunks:
            buffer.append(chunk)
            accumulated = b"".join(buffer)
            while len(accumulated) >= frame_size * 2:  # 2 bytes per sample
                frame = accumulated[: frame_size * 2]
                accumulated = accumulated[frame_size * 2 :]
                prediction = self._predict(frame)
                if prediction >= self.sensitivity:
                    yield True
                    # Reset buffer after detection to avoid repeated triggers.
                    buffer = []
                    accumulated = b""
            # Keep leftover partial frame for next iteration.
            buffer = [accumulated] if accumulated else []

    def _predict(self, frame: bytes) -> float:
        """Run openWakeWord prediction on a single frame. Returns 0.0-1.0."""
        if self._model is None or _np is None:
            return 0.0
        samples = _np.frombuffer(frame, dtype=_np.int16).astype(_np.float32) / 32768.0
        try:
            results = self._model.predict(samples)
            # openWakeWord returns a dict of {model_name: score_list}.
            max_score = 0.0
            for scores in results.values():
                if scores:
                    max_score = max(max_score, float(scores[-1]))
        except Exception:  # noqa: BLE001 — prediction failure is non-fatal
            return 0.0
        return max_score

    async def health(self) -> bool:
        return self._available
