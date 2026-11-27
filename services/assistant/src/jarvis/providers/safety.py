"""Provider-independent error and untrusted-output helpers."""

from __future__ import annotations

import re
from typing import Any


class LLMProviderError(Exception):
    """Stable base error shared by all language-model providers."""

    def __init__(self, message: str, error_code: str = "llm_provider_error") -> None:
        super().__init__(message)
        self.error_code = error_code


def sanitize_untrusted_output(output: Any, max_len: int = 4000) -> str:
    """Redact likely credentials and bound tool output before model exposure."""
    if output is None:
        return ""
    text = str(output)
    secret_pattern = (
        r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*\S+"
    )
    text = re.sub(secret_pattern, r"\1=***REDACTED***", text)
    if len(text) > max_len:
        text = text[:max_len] + "\n...[output truncated by JARVIS]..."
    return text
