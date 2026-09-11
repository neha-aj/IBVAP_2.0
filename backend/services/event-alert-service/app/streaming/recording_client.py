"""Captures a pre+post-roll evidence clip for a critical-severity event
(Phase 2 M23 -- the recording-segment producer doc09/doc08 anticipated but
no milestone ever actually wired, see media-service's `Recording` model
docstring: "nothing in the pipeline triggers segment recording yet").

Pre-roll (frames *before* the trigger moment) draws on ingestion-service's
`FrameRingBuffer` -- a later addition than this module's original post-roll-
only version, which was limited by Ingestion Service caching only a single
latest frame per camera at the time. Pre-roll is fetched via `/internal/
cameras/{id}/recent-frames` and prepended to the existing post-roll capture;
best-effort like everything else here (an empty/failed pre-roll fetch just
means the clip starts at the trigger moment, same as the old behavior).

Runs as a background task (see `pubsub_publisher.py`), not awaited inline
like `SnapshotClient` -- capturing `recording_post_roll_frame_count` frames
`recording_post_roll_interval_seconds` apart takes multiple real seconds,
which would otherwise delay every critical event's own persistence and the
WS `event.new`/`alert.new` push that's supposed to reach operators
immediately.
"""

from __future__ import annotations

import asyncio
import base64
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
        """Fetches pre-roll history, then polls Ingestion Service's
        current-frame endpoint at a fixed interval for post-roll, assembles
        whatever frames it got (pre + post) into an MP4, and uploads it.
        Best-effort throughout (SAS §11): a camera that stops streaming
        mid-capture, or either service being briefly down, yields fewer
        frames or `None` -- never raises."""
        pre_roll_frames, pre_roll_start = await self._fetch_pre_roll_frames(camera_id)
        start_time = pre_roll_start or dt.datetime.now(dt.UTC)
        post_roll_frames = await self._collect_frames(camera_id)
        frames = pre_roll_frames + post_roll_frames
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

    async def _fetch_pre_roll_frames(self, camera_id: str) -> tuple[list[np.ndarray], dt.datetime | None]:
        """Best-effort: an empty/failed fetch (ring buffer not warmed up
        yet, camera just added, ingestion-service briefly down) degrades to
        exactly the old post-roll-only behavior, not a capture failure."""
        try:
            response = await self._http.get(
                f"{self._settings.ingestion_service_url}/internal/cameras/{camera_id}/recent-frames",
                params={"seconds": self._settings.recording_pre_roll_seconds},
                headers={"X-Internal-Token": self._settings.internal_service_token, **correlated_headers()},
                timeout=self._settings.recording_capture_timeout_seconds,
            )
            response.raise_for_status()
            entries = response.json().get("frames", [])
        except (httpx.HTTPError, ValueError):
            return [], None

        frames: list[np.ndarray] = []
        earliest_ts: float | None = None
        for entry in entries:
            try:
                jpeg_bytes = base64.b64decode(entry["jpeg"])
                frame = cv2.imdecode(np.frombuffer(jpeg_bytes, np.uint8), cv2.IMREAD_COLOR)
            except Exception:
                continue
            if frame is None:
                continue
            frames.append(frame)
            ts = entry.get("timestamp")
            if isinstance(ts, (int, float)) and (earliest_ts is None or ts < earliest_ts):
                earliest_ts = ts

        start_time = dt.datetime.fromtimestamp(earliest_ts, tz=dt.UTC) if earliest_ts is not None else None
        return frames, start_time

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
            # WebM/VP8, not MP4/mp4v: this container's OpenCV/FFmpeg build has
            # no H.264 encoder available (no libx264, no hardware encoder in a
            # Docker container -- confirmed by hand, VideoWriter.isOpened()
            # returns False for every avc1/h264/H264/X264 fourcc tried), and
            # mp4v (MPEG-4 Part 2) -- while a perfectly valid, readable MP4 to
            # OpenCV/ffmpeg/VLC -- is a codec no browser's <video> element
            # supports at all, so every clip was silently unplayable in the
            # Evidence/Alerts UI (MEDIA_ERR_SRC_NOT_SUPPORTED) despite the
            # file itself being genuinely valid. VP8 in WebM is open,
            # patent-unencumbered, always available in OpenCV's bundled
            # FFmpeg (confirmed working in this exact container), and is
            # natively supported by every browser this app targets.
            tmp_path = Path(tmp_dir) / "clip.webm"
            writer = cv2.VideoWriter(
                str(tmp_path), cv2.VideoWriter_fourcc(*"VP80"), self._settings.recording_clip_fps, (width, height),
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
                files={"file": ("clip.webm", clip_bytes, "video/webm")},
                headers={"X-Internal-Token": self._settings.internal_service_token, **correlated_headers()},
                timeout=self._settings.recording_capture_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            return CapturedRecording(id=payload["id"], url=payload["url"])
        except httpx.HTTPError as exc:
            logger.info("recording_upload_skipped", camera_id=camera_id, error=str(exc))
            return None
