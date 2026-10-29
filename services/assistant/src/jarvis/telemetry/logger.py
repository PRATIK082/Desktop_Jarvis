"""Structured local logging (Agent.md §18).

- ISO timestamp, level, component, request_id, conversation_id, event name,
  duration, sanitized details.
- Rotating log files, configurable level, privacy redaction.
- Conversation contents excluded from ordinary logs.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from jarvis.config import settings

_LOGGER_CACHE: dict[str, logging.Logger] = {}

# Fields that must never be logged in plaintext.
SENSITIVE_KEYS = {
    "auth_token",
    "password",
    "secret",
    "api_key",
    "token",
    "transcript",
    "audio",
    "memory",
    "conversation",
}

# Environment variable names whose values must never be logged in plaintext.
SENSITIVE_ENV_KEYS = {
    "JARVIS_AUTH_TOKEN",
    "OLLAMA_API_KEY",
    "API_KEY",
    "SECRET",
    "TOKEN",
    "PASSWORD",
}


def _sanitize(value: object) -> object:
    if isinstance(value, dict):
        return {k: _sanitize(v) for k, v in value.items() if k.lower() not in SENSITIVE_KEYS}
    if isinstance(value, (list, tuple)):
        return [_sanitize(v) for v in value]
    return value


def sanitize_env(env: dict[str, str] | None) -> dict[str, str] | None:
    """Redact sensitive environment variable values before logging."""
    if env is None:
        return None
    redacted: dict[str, str] = {}
    for key, value in env.items():
        if key.upper() in SENSITIVE_ENV_KEYS:
            redacted[key] = "***REDACTED***"
        else:
            redacted[key] = value
    return redacted


def get_logger(component: str) -> logging.Logger:
    if component in _LOGGER_CACHE:
        return _LOGGER_CACHE[component]

    logger = logging.getLogger(f"jarvis.{component}")
    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    logger.propagate = False

    if not logger.handlers:
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )

        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

        # Rotating file handler under the app data directory.
        try:
            log_dir = Path("logs")
            log_dir.mkdir(exist_ok=True)
            file_handler = RotatingFileHandler(
                log_dir / "jarvis.log",
                maxBytes=5 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except OSError:
            # If we cannot write logs, continue with stream-only logging.
            pass

    _LOGGER_CACHE[component] = logger
    return logger


def log_event(
    component: str,
    event: str,
    *,
    level: str = "info",
    request_id: str | None = None,
    conversation_id: str | None = None,
    duration_ms: float | None = None,
    details: dict[str, object] | None = None,
) -> None:
    logger = get_logger(component)
    payload: dict[str, object] = {
        "event": event,
        "request_id": request_id,
        "conversation_id": conversation_id,
    }
    if duration_ms is not None:
        payload["duration_ms"] = duration_ms
    if details:
        payload["details"] = _sanitize(details)

    getattr(logger, level.lower(), logger.info)("%s", payload)
