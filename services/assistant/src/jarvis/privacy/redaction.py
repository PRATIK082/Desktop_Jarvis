"""PII/secrets redaction applied before any persistence.

Design (original implementation, no external dependency):
- A small set of built-in patterns for common PII/secrets.
- User-supplied patterns (regex) layered on top.
- Redaction is deterministic and reports what was removed.
- Raw input is never logged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class RedactionReport:
    redacted_count: int = 0
    categories: dict[str, int] = field(default_factory=dict)
    applied_patterns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "redacted_count": self.redacted_count,
            "categories": dict(self.categories),
            "applied_patterns": list(self.applied_patterns),
        }


# (category, regex). Order matters: more specific first.
_BUILTIN: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("credit_card", re.compile(r"\b(?:\d[ -]*?){13,16}\b")),
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("ipv4", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("phone", re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b")),
    ("api_key", re.compile(r"\b(?:sk|pk|api|token|secret)[-_][A-Za-z0-9]{16,}\b", re.IGNORECASE)),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")),
]


class Redactor:
    """Redact sensitive spans from text before persistence."""

    def __init__(self, extra_patterns: Iterable[str] | None = None) -> None:
        self._extra: list[re.Pattern[str]] = []
        for p in extra_patterns or []:
            self._extra.append(re.compile(p))

    def redact(self, text: str) -> tuple[str, RedactionReport]:
        report = RedactionReport()
        result = text
        for category, pattern in _BUILTIN:
            new, n = pattern.subn(f"[REDACTED:{category}]", result)
            if n:
                result = new
                report.redacted_count += n
                report.categories[category] = report.categories.get(category, 0) + n
                report.applied_patterns.append(category)
        for i, pattern in enumerate(self._extra):
            label = f"custom_{i}"
            new, n = pattern.subn(f"[REDACTED:{label}]", result)
            if n:
                result = new
                report.redacted_count += n
                report.categories[label] = report.categories.get(label, 0) + n
                report.applied_patterns.append(label)
        return result, report

    def redact_many(self, items: Iterable[str]) -> list[tuple[str, RedactionReport]]:
        return [self.redact(x) for x in items]
