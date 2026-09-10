"""Holds the most recent JPEG-encoded frame per camera in memory, so the
MJPEG preview endpoint (`GET /stream/{id}/mjpeg`) always has something to
serve without re-reading from Redis. One process's cache only -- fine for
Phase 1's single-ingestion-replica deployment (SAS §9)."""

from __future__ import annotations

import asyncio


class FrameCache:
    def __init__(self) -> None:
        self._frames: dict[str, bytes] = {}
        self._lock = asyncio.Lock()

    async def set(self, camera_id: str, jpeg_bytes: bytes) -> None:
        async with self._lock:
            self._frames[camera_id] = jpeg_bytes

    async def get(self, camera_id: str) -> bytes | None:
        async with self._lock:
            return self._frames.get(camera_id)

    async def clear(self, camera_id: str) -> None:
        async with self._lock:
            self._frames.pop(camera_id, None)


# Process-wide singleton -- workers write to it, the preview router reads from it.
frame_cache = FrameCache()
