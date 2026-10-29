"""JARVIS audio package (Agent.md §7).

Voice pipeline: microphone -> bounded buffer -> VAD -> wake-word/push-to-talk
-> segmentation -> STT -> orchestration -> TTS -> playback.
"""

from jarvis.audio.buffer import AudioChunk, BoundedAudioBuffer
from jarvis.audio.devices import AudioDevice, AudioDeviceManager
from jarvis.audio.pipeline import VoicePipeline
from jarvis.audio.providers import FasterWhisperSTT, PiperTTS
from jarvis.audio.vad import VoiceActivityDetector
from jarvis.audio.wake_word import OpenWakeWordProvider

__all__ = [
    "AudioChunk",
    "AudioDevice",
    "AudioDeviceManager",
    "BoundedAudioBuffer",
    "FasterWhisperSTT",
    "OpenWakeWordProvider",
    "PiperTTS",
    "VoiceActivityDetector",
    "VoicePipeline",
]
