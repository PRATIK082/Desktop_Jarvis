"""JARVIS sidecar configuration (Pydantic v2).

All settings are loaded from environment variables with sane defaults.
The sidecar binds to 127.0.0.1 only and requires a per-launch ephemeral
auth token passed by the Tauri host.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_prefix="JARVIS_",
    )

    # Sidecar network (loopback only, ephemeral port chosen by Tauri host)
    host: str = Field("127.0.0.1", description="Bind address (loopback only)")
    port: int = Field(0, description="0 = ephemeral free port chosen by Tauri")
    auth_token: str = Field("", description="Per-launch ephemeral auth token (set by Tauri host)")

    # Ollama
    ollama_base_url: str = Field("http://127.0.0.1:11434", description="Ollama base URL")
    ollama_chat_model: str = Field("", description="User-selected chat model")
    ollama_embedding_model: str = Field("", description="User-selected embedding model")
    ollama_timeout_s: float = Field(120.0, description="Ollama request timeout (seconds)")

    # Audio / VAD
    vad_aggressiveness: int = Field(2, description="VAD aggressiveness (0-3)")
    silence_timeout_ms: int = Field(800, description="Automatic silence detection timeout (ms)")
    interruption_enabled: bool = Field(
        True, description="Stop TTS playback when user starts speaking"
    )

    # Wake word (optional)
    wake_word_enabled: bool = Field(False, description="Enable optional local wake-word detection")
    wake_word_sensitivity: float = Field(0.5, description="Wake-word sensitivity (0.0-1.0)")

    # Privacy
    telemetry_enabled: bool = Field(False, description="Telemetry disabled by default")
    retain_raw_audio: bool = Field(False, description="Raw audio not retained by default")

    # Audio devices
    audio_input_device: str | None = Field(
        None, description="Selected microphone device id (None = system default)"
    )
    audio_output_device: str | None = Field(
        None, description="Selected speaker device id (None = system default)"
    )
    audio_sample_rate: int = Field(16000, description="Audio sample rate (Hz)")
    audio_chunk_size: int = Field(1024, description="Audio chunk size (samples)")
    audio_buffer_max_chunks: int = Field(
        100, description="Bounded audio buffer max chunks (backpressure)"
    )

    # STT / TTS provider selection (E2: real local providers are the default;
    # both degrade gracefully when their package/model is not installed)
    stt_provider: str = Field("faster_whisper", description="STT provider: faster_whisper or mock")
    stt_model: str = Field("base", description="faster-whisper model size (tiny/base/small/medium)")
    stt_language: str = Field("en", description="STT recognition language code")
    tts_provider: str = Field("piper", description="TTS provider: piper or mock")
    tts_voice: str | None = Field(None, description="Piper voice model path (None = default voice)")

    # Engine selection (clean-room engine abstraction)
    engine: str = Field("local", description="Active engine: local or cloud")
    cloud_api_key: str = Field("", description="Operator-provided cloud engine key (never logged)")

    # VAD
    vad_enabled: bool = Field(True, description="Enable voice activity detection")
    vad_threshold: float = Field(0.02, description="VAD energy threshold (0.0-1.0)")

    # Memory / RAG
    memory_db_path: str = Field(
        ".jarvis/jarvis_memory.db", description="Path to SQLite memory database"
    )
    memory_max_conversations: int = Field(
        1000, description="Maximum stored conversations"
    )
    memory_max_messages_per_conversation: int = Field(
        50, description="Maximum recent messages kept in context"
    )
    memory_chunk_size: int = Field(
        500, description="Document chunk size (characters)"
    )
    memory_chunk_overlap: int = Field(
        50, description="Document chunk overlap (characters)"
    )
    memory_max_search_results: int = Field(
        10, description="Maximum memory/RAG search results"
    )

    # Scheduler (reminders/timers)
    scheduler_db_path: str = Field(
        ".jarvis/jarvis_scheduler.db", description="Path to SQLite scheduler database"
    )
    scheduler_default_timezone: str = Field(
        "local", description="Default timezone for reminders (IANA name or 'local')"
    )
    scheduler_notification_enabled: bool = Field(
        True, description="Enable desktop notifications for reminders/timers"
    )

    # Security
    max_request_body_bytes: int = Field(
        1_048_576, description="Maximum request body size in bytes (default 1 MB)"
    )

    # Logging
    log_level: str = Field("info", description="Structured log level")


settings = Settings()  # type: ignore[call-arg]  # pydantic BaseSettings fields use Field() defaults mypy can't infer
