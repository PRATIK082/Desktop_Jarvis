"""Voice Activity Detection (Agent.md §7).

Simple energy-based VAD. Configurable threshold and silence timeout.
Designed to be testable without a real microphone (inject synthetic audio
energy levels).
"""

from __future__ import annotations

import math


class VoiceActivityDetector:
    """Detects speech vs silence from audio chunk energy.

    Energy is computed as RMS of 16-bit PCM samples. A chunk is "speech"
    when its normalized energy exceeds the threshold.
    """

    def __init__(self, threshold: float = 0.02, sample_rate: int = 16000) -> None:
        self.threshold = threshold
        self.sample_rate = sample_rate
        self._speech_frames = 0
        self._silence_frames = 0

    @property
    def threshold_value(self) -> float:
        return self.threshold

    def set_threshold(self, value: float) -> None:
        self.threshold = max(0.0, min(1.0, value))

    def _energy(self, data: bytes) -> float:
        """Compute normalized RMS energy of 16-bit PCM data (0.0-1.0)."""
        if not data:
            return 0.0
        # Interpret as little-endian int16 samples.
        sample_count = len(data) // 2
        if sample_count == 0:
            return 0.0
        total = 0.0
        for i in range(sample_count):
            offset = i * 2
            sample = int.from_bytes(data[offset : offset + 2], "little", signed=True)
            total += (sample / 32768.0) ** 2
        rms = math.sqrt(total / sample_count)
        return min(rms, 1.0)

    def is_speech(self, data: bytes) -> bool:
        """Return True if the chunk contains speech energy above threshold."""
        energy = self._energy(data)
        is_speech = energy >= self.threshold
        if is_speech:
            self._speech_frames += 1
            self._silence_frames = 0
        else:
            self._silence_frames += 1
        return is_speech

    def reset(self) -> None:
        self._speech_frames = 0
        self._silence_frames = 0

    @property
    def speech_frame_count(self) -> int:
        return self._speech_frames

    @property
    def silence_frame_count(self) -> int:
        return self._silence_frames
