"""Bounded rolling history of recent JPEG frames per camera, sampled at a
low rate -- powers pre-roll evidence capture (event-alert-service's
`RecordingClient`, M-accident-evidence) without the memory cost of
buffering every frame at full `capture_fps`.

Deliberately separate from `frame_cache.py`'s single-latest-frame cache
(used by the live MJPEG preview) -- additive alongside it, not a
replacement; nothing about the live preview changes."""

from __future__ import annotations

import asyncio
import time
from collections import deque


class FrameRingBuffer:
    def __init__(self) -> None:
        self._buffers: dict[str, deque[tuple[float, bytes]]] = {}
        self._lock = asyncio.Lock()

    async def push(self, cache_key: str, jpeg_bytes: bytes, *, max_age_seconds: float) -> None:
        async with self._lock:
            buf = self._buffers.setdefault(cache_key, deque())
            now = time.time()
            buf.append((now, jpeg_bytes))
            cutoff = now - max_age_seconds
            while buf and buf[0][0] < cutoff:
                buf.popleft()

    async def recent(self, cache_key: str, seconds: float) -> list[tuple[float, bytes]]:
        async with self._lock:
            buf = self._buffers.get(cache_key)
            if not buf:
                return []
            cutoff = time.time() - seconds
            # Snapshot the matching entries -- `buf` itself keeps mutating
            # from concurrent `push()` calls after the lock is released.
            return [(ts, data) for ts, data in buf if ts >= cutoff]

    async def clear(self, cache_key: str) -> None:
        async with self._lock:
            self._buffers.pop(cache_key, None)


# Process-wide singleton -- workers write to it, the internal recent-frames
# route reads from it. Mirrors `frame_cache.frame_cache`'s own pattern.
frame_ring_buffer = FrameRingBuffer()
