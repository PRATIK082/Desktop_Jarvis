"""Bounded audio buffer with backpressure (Agent.md §7).

Holds raw microphone audio chunks in a bounded async queue. When the buffer
is full, producers apply backpressure (await space) rather than dropping or
blocking the UI thread. Raw audio is never persisted to disk by default.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass(frozen=True)
class AudioChunk:
    """A single chunk of raw PCM audio."""
    data: bytes
    sample_rate: int
    channels: int
    timestamp_ms: float


class BoundedAudioBuffer:
    """Thread-safe bounded buffer for raw audio chunks.

    Uses an asyncio.Queue with a max size. When full, `put` awaits space
    (backpressure). Consumers use `get` to drain chunks.
    """

    def __init__(self, max_chunks: int = 100) -> None:
        self._max_chunks = max_chunks
        self._queue: asyncio.Queue[AudioChunk | None] = asyncio.Queue(maxsize=max_chunks)
        self._dropped = 0
        self._closed = False

    @property
    def max_chunks(self) -> int:
        return self._max_chunks

    @property
    def dropped_count(self) -> int:
        return self._dropped

    @property
    def qsize(self) -> int:
        return self._queue.qsize()

    @property
    def closed(self) -> bool:
        return self._closed

    async def put(self, chunk: AudioChunk) -> None:
        """Add a chunk, applying backpressure when full."""
        if self._closed:
            _msg = "buffer is closed"
            raise RuntimeError(_msg)
        await self._queue.put(chunk)

    async def get(self) -> AudioChunk | None:
        """Remove and return the next chunk, or None when closed/drained."""
        return await self._queue.get()

    async def close(self) -> None:
        """Close the buffer and unblock any waiting consumers."""
        self._closed = True
        # Unblock consumers by putting a sentinel.
        try:
            self._queue.put_nowait(None)
        except asyncio.QueueFull:
            pass

    def drop(self) -> None:
        """Record a dropped chunk (called when backpressure can't be applied)."""
        self._dropped += 1
