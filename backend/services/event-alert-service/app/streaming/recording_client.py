"""Captures a short post-roll clip for a critical-severity event (Phase 2
M23 -- the recording-segment producer doc09/doc08 anticipated but no
milestone ever actually wired, see media-service's `Recording` model
docstring: "nothing in the pipeline triggers segment recording yet").

Post-roll only, not the full pre/post-roll SAS concept: Ingestion Service
caches only a single latest frame per camera (`frame_cache.py`), not a
rolling buffer, so a true pre-roll clip (frames *before* the trigger
moment) isn't possible without new buffering infrastructure -- a
deliberate, documented scope reduction, same discipline as this project's
other honestly-scoped deviations (e.g. Re-ID's "first frame, not best
frame" simplification).

Runs as a background task (see `pubsub_publisher.py`), not awaited inline
like `SnapshotClient` -- capturing `recording_post_roll_frame_count` frames
`recording_post_roll_interval_seconds` apart takes multiple real seconds,
which would otherwise delay every critical event's own persistence and the
WS `event.new`/`alert.new` push that's supposed to reach operators
immediately.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import tempfile
from dataclasses import dataclass
from pathlib import Path

import cv2
import httpx
import numpy as np

from ibvap_common.logging import correlated_headers, get_logger

from app.core.config import Settings

logger = get_logger(__name__)


@dataclass(frozen=True)
class CapturedRecording:
    id: str
    url: str


class RecordingClient:
    def __init__(self, http_client: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http_client
        self._settings = settings

    async def capture_clip(self, *, camera_id: str, event_id: str) -> CapturedRecording | None:
        """Polls Ingestion Service's current-frame endpoint at a fixed
        interval, assembles whatever frames it got into an MP4, and
        uploads it. Best-effort throughout (SAS §11): a camera that stops
        streaming mid-capture, or either service being briefly down,
        yields fewer frames or `None` -- never raises."""
        start_time = dt.datetime.now(dt.UTC)
        frames = await self._collect_frames(camera_id)
        if not frames:
            logger.info("recording_capture_skipped", camera_id=camera_id, reason="no_frames")
            return None
        end_time = dt.datetime.now(dt.UTC)

        try:
            clip_bytes = self._encode_clip(frames)
        except Exception as exc:
            logger.warning("recording_encode_failed", camera_id=camera_id, error=str(exc))
            return None

        return await self._upload(
            camera_id=camera_id, event_id=event_id, clip_bytes=clip_bytes,
            start_time=start_time, end_time=end_time,
        )

    async def _collect_frames(self, camera_id: str) -> list[np.ndarray]:
        frames: list[np.ndarray] = []
        for _ in range(self._settings.recording_post_roll_frame_count):
            try:
                response = await self._http.get(
                    f"{self._settings.ingestion_service_url}/internal/cameras/{camera_id}/snapshot",
                    headers={"X-Internal-Token": self._settings.internal_service_token, **correlated_headers()},
                    timeout=self._settings.recording_capture_timeout_seconds,
                )
                response.raise_for_status()
                frame = cv2.imdecode(np.frombuffer(response.content, np.uint8), cv2.IMREAD_COLOR)
                if frame is not None:
                    frames.append(frame)
            except httpx.HTTPError:
                pass  # camera not currently streaming -- skip this tick, keep trying
            await asyncio.sleep(self._settings.recording_post_roll_interval_seconds)
        return frames

    def _encode_clip(self, frames: list[np.ndarray]) -> bytes:
        height, width = frames[0].shape[:2]
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / "clip.mp4"
            writer = cv2.VideoWriter(
                str(tmp_path), cv2.VideoWriter_fourcc(*"mp4v"), self._settings.recording_clip_fps, (width, height),
            )
            try:
                for frame in frames:
                    if frame.shape[:2] != (height, width):
                        frame = cv2.resize(frame, (width, height))
                    writer.write(frame)
            finally:
                writer.release()
            return tmp_path.read_bytes()

    async def _upload(
        self, *, camera_id: str, event_id: str, clip_bytes: bytes, start_time: dt.datetime, end_time: dt.datetime,
    ) -> CapturedRecording | None:
        try:
            response = await self._http.post(
                f"{self._settings.media_service_url}/media/recordings",
                params={
                    "camera_id": camera_id,
                    "event_id": event_id,
                    "start_time": start_time.isoformat(),
                    "end_time": end_time.isoformat(),
                    "duration_seconds": round((end_time - start_time).total_seconds()),
                },
                files={"file": ("clip.mp4", clip_bytes, "video/mp4")},
                headers={"X-Internal-Token": self._settings.internal_service_token, **correlated_headers()},
                timeout=self._settings.recording_capture_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            return CapturedRecording(id=payload["id"], url=payload["url"])
        except httpx.HTTPError as exc:
            logger.info("recording_upload_skipped", camera_id=camera_id, error=str(exc))
            return None
