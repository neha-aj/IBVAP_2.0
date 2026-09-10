"""Normalizes raw pixel-space detections to the frontend's percentage-based
`DetectionOverlay` contract and publishes them (SAS §5.2 step 2-3):

- appends to the `cam:{id}:detections` Redis Stream (history / future
  Tracking Service input), and
- overwrites a short-TTL `cam:{id}:current_detections` key (a JSON array)
  that `GET /cameras/{id}/detections/current` and the live overlay read.
"""

from __future__ import annotations

import json
import uuid

import redis.asyncio as redis

from ibvap_common.logging import CORRELATION_ID_FIELD, get_correlation_id
from ibvap_common.redis_streams import xadd_capped

from app.inference.base import COCO_TYPE_MAP, RawDetection
from app.schemas.detection import BoundingBox, Detection


def _clamp_percent(value: float) -> float:
    return max(0.0, min(100.0, value))


def to_detections(
    *, camera_id: str, raw_detections: list[RawDetection], frame_width: int, frame_height: int
) -> list[Detection]:
    """Converts pixel-space `RawDetection`s to percentage-space `Detection`s
    matching the frontend contract exactly (Frontend Analysis Report §5:
    "normalized 0-100 coordinates, not pixels")."""
    detections: list[Detection] = []
    for raw in raw_detections:
        object_type = COCO_TYPE_MAP.get(raw.class_id)
        if object_type is None:
            continue
        bbox = BoundingBox(
            x=_clamp_percent(raw.x1 / frame_width * 100),
            y=_clamp_percent(raw.y1 / frame_height * 100),
            width=_clamp_percent((raw.x2 - raw.x1) / frame_width * 100),
            height=_clamp_percent((raw.y2 - raw.y1) / frame_height * 100),
        )
        detections.append(
            Detection(
                id=str(uuid.uuid4()),
                camera_id=camera_id,
                type=object_type,  # type: ignore[arg-type]
                confidence=round(raw.confidence, 4),
                track_id=None,  # Tracking Service (M5) assigns this later.
                bbox=bbox,
            )
        )
    return detections


class DetectionPublisher:
    def __init__(
        self, redis_client: redis.Redis, *, stream_maxlen: int, current_ttl_seconds: int
    ) -> None:
        self._redis = redis_client
        self._stream_maxlen = stream_maxlen
        self._current_ttl_seconds = current_ttl_seconds

    async def publish(self, camera_id: str, detections: list[Detection], *, loop_generation: int = 0) -> None:
        payload = json.dumps([d.model_dump(by_alias=True) for d in detections])

        await xadd_capped(
            self._redis,
            f"cam:{camera_id}:detections",
            {
                "cameraId": camera_id,
                "detections": payload,
                "loopGeneration": str(loop_generation),
                # Propagates the id bound by FrameConsumer from the source
                # frame (SAS §10) so Tracking/Event-Alert can keep tracing
                # this same frame's journey -- not generated fresh here.
                CORRELATION_ID_FIELD: get_correlation_id(),
            },
            maxlen=self._stream_maxlen,
        )

        current_key = f"cam:{camera_id}:current_detections"
        if detections:
            await self._redis.set(current_key, payload, ex=self._current_ttl_seconds)
        else:
            # No objects this frame -- still refresh the TTL with an empty
            # array so the overlay clears promptly rather than showing the
            # last-seen boxes, but the key still expires (and reads as "no
            # data") the moment the camera stops publishing frames at all.
            await self._redis.set(current_key, "[]", ex=self._current_ttl_seconds)
