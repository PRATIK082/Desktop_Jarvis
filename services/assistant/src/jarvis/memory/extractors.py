"""Text extraction from user-selected documents (Agent.md §12C).

Supports: txt, md, json, csv, and PDF (when a parser is available).
Never indexes an entire home directory; callers select specific files.
Detects and warns about very large or binary files.
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass
from typing import Any

MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB warning threshold
TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".json", ".csv"}


@dataclass
class ExtractionResult:
    """Result of extracting text from a document."""

    text: str
    mime_type: str
    size_bytes: int
    warning: str | None = None  # e.g. "file is very large", "binary detected"


def detect_mime_type(path: str) -> str:
    """Best-effort MIME type detection from file extension."""
    ext = os.path.splitext(path)[1].lower()
    mapping = {
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".markdown": "text/markdown",
        ".json": "application/json",
        ".csv": "text/csv",
        ".pdf": "application/pdf",
    }
    return mapping.get(ext, "application/octet-stream")


def is_text_extension(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in TEXT_EXTENSIONS


def extract_text(path: str) -> ExtractionResult:
    """Extract text from a user-selected document.

    Reads the file once. For PDF, uses pypdf if available; otherwise
    returns a warning that PDF parsing is unavailable.
    """
    size_bytes = os.path.getsize(path)
    mime_type = detect_mime_type(path)
    warning: str | None = None

    if size_bytes > MAX_FILE_BYTES:
        warning = f"file is very large ({size_bytes / (1024*1024):.1f} MB)"

    ext = os.path.splitext(path)[1].lower()

    try:
        if ext == ".pdf":
            text = _extract_pdf(path)
        elif ext == ".json":
            text = _extract_json(path)
        elif ext == ".csv":
            text = _extract_csv(path)
        else:
            # txt, md, markdown — read as text with error handling.
            text = _extract_plain_text(path)
    except UnicodeDecodeError:
        text = ""
        warning = (warning + "; " if warning else "") + "binary or non-UTF-8 file"
    except Exception as exc:  # noqa: BLE001 — extraction failures are non-fatal
        text = ""
        warning = (warning + "; " if warning else "") + f"extraction failed: {exc}"

    return ExtractionResult(
        text=text,
        mime_type=mime_type,
        size_bytes=size_bytes,
        warning=warning,
    )


def _extract_plain_text(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _extract_json(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    # Flatten JSON into a readable text form.
    return _json_to_text(data)


def _json_to_text(obj: Any, indent: int = 0) -> str:
    prefix = "  " * indent
    if isinstance(obj, dict):
        lines = []
        for k, v in obj.items():
            lines.append(f"{prefix}{k}: {_json_to_text(v, indent + 1)}")
        return "\n".join(lines)
    if isinstance(obj, list):
        lines = [f"{prefix}- {_json_to_text(item, indent + 1)}" for item in obj]
        return "\n".join(lines)
    return str(obj)


def _extract_csv(path: str) -> str:
    rows: list[str] = []
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        rows.extend(" | ".join(row) for row in reader)
    return "\n".join(rows)


def _extract_pdf(path: str) -> str:
    """Extract text from PDF using pypdf if available."""
    pdf_reader_cls: type[Any] | None = None
    try:
        from pypdf import PdfReader as _PR  # noqa: PLC0415,I001 — optional PDF dep, lazy import
        pdf_reader_cls = _PR
    except ImportError:
        try:
            from PyPDF2 import PdfReader as _PR2  # type: ignore[import-not-found]  # noqa: PLC0415,I001 — optional PDF dep, lazy import
            pdf_reader_cls = _PR2
        except ImportError:
            pass
    if pdf_reader_cls is None:
        return (
            "[PDF parsing not available: install pypdf or PyPDF2 "
            "to extract text from PDF files.]"
        )

    reader = pdf_reader_cls(path)
    parts: list[str] = []
    for i, page in enumerate(reader.pages):
        try:
            page_text = page.extract_text() or ""
        except Exception:  # noqa: BLE001 — per-page failure is non-fatal
            page_text = ""
        if page_text.strip():
            parts.append(f"--- Page {i + 1} ---\n{page_text}")
    return "\n\n".join(parts)
