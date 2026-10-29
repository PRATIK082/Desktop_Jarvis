"""Text chunking with overlap for RAG (Agent.md §12C).

Splits document text into overlapping chunks so that retrieval context
is preserved across chunk boundaries.
"""

from __future__ import annotations


def chunk_text(
    text: str, chunk_size: int = 500, overlap: int = 50
) -> list[str]:
    """Split `text` into overlapping chunks of approximately `chunk_size` chars.

    Chunks are split on whitespace where possible to avoid breaking words.
    Returns an empty list for empty input.
    """
    if not text or not text.strip():
        return []

    if chunk_size <= 0:
        _msg = "chunk_size must be positive"
        raise ValueError(_msg)
    if overlap < 0 or overlap >= chunk_size:
        _msg = "overlap must be >= 0 and < chunk_size"
        raise ValueError(_msg)

    words = text.split()
    chunks: list[str] = []
    start = 0
    while start < len(words):
        # Take up to chunk_size worth of characters from `start`.
        end = start
        char_count = 0
        while end < len(words) and char_count < chunk_size:
            char_count += len(words[end]) + (1 if end > start else 0)
            end += 1
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        if end >= len(words):
            break
        # Advance start by chunk_size minus overlap worth of characters.
        # Recompute the next start position based on character count.
        target_skip = chunk_size - overlap
        skipped = 0
        next_start = start
        while next_start < end and skipped < target_skip:
            skipped += len(words[next_start]) + 1
            next_start += 1
        start = max(next_start, start + 1)

    return chunks


def chunk_with_sections(
    text: str, chunk_size: int = 500, overlap: int = 50
) -> list[dict[str, object]]:
    """Like chunk_text but returns chunks with section metadata.

    Each returned dict has: text, start_char, end_char, section_index.
    Sections are approximated by paragraph breaks.
    """
    if not text or not text.strip():
        return []

    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    chunks: list[dict[str, object]] = []
    section_index = 0
    char_offset = 0

    for para in paragraphs:
        para_chunks = chunk_text(para, chunk_size=chunk_size, overlap=overlap)
        for c in para_chunks:
            chunks.append(
                {
                    "text": c,
                    "start_char": char_offset,
                    "end_char": char_offset + len(c),
                    "section_index": section_index,
                }
            )
            char_offset += len(c) + 2  # +2 for the "\n\n" separator
        section_index += 1

    return chunks
