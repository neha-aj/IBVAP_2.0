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

# Same "plain module constant, not a Settings field" convention as
# `onnx_runner.py`'s own `_NMS_IOU_THRESHOLD` -- see
# `_suppress_contained_duplicates`'s docstring for what this gates. 0.5
# (just below the ~0.56 containment ratio measured on the one real case
# this was tuned against, so that real case is actually caught) rather
# than a rounder-looking but untested 0.6 -- comfortably above what two
# genuinely distinct objects merely touching/adjacent would ever measure
# (their smaller box wouldn't be even half-covered by the other).
_DUPLICATE_CONTAINMENT_THRESHOLD = 0.5


def _clamp_percent(value: float) -> float:
    return max(0.0, min(100.0, value))


def _overlap_over_smaller_area(a: RawDetection, b: RawDetection) -> float:
    """Intersection area divided by the *smaller* of the two boxes' own
    areas -- not standard IoU (intersection / union). Two boxes at very
    different scales covering the same real object (see
    `_suppress_contained_duplicates`'s docstring) can have a low IoU purely
    from the size mismatch even when the smaller box sits almost entirely
    inside the larger one; this metric is what actually captures "mostly
    contained," which is the shape of the real failure mode being
    suppressed here."""
    ix1, iy1 = max(a.x1, b.x1), max(a.y1, b.y1)
    ix2, iy2 = min(a.x2, b.x2), min(a.y2, b.y2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    intersection = iw * ih
    if intersection <= 0:
        return 0.0
    area_a = (a.x2 - a.x1) * (a.y2 - a.y1)
    area_b = (b.x2 - b.x1) * (b.y2 - b.y1)
    smaller = min(area_a, area_b)
    return intersection / smaller if smaller > 0 else 0.0


def _suppress_contained_duplicates(
    raw_detections: list[RawDetection], *, containment_threshold: float
) -> list[RawDetection]:
    """Removes a lower-confidence detection that's mostly contained inside
    a higher-confidence one of a *different raw COCO class mapping to the
    same merged type* -- confirmed live: a single real vehicle (a car with
    its trunk open) was scored highly as both YOLO's raw "car" class and
    its raw "truck" class in the same frame, `COCO_TYPE_MAP` merges both
    into "vehicle" (by design, same as it merges 8 raw species into
    "animal" -- see that map's own docstring), and the two raw boxes --
    one tight around just the car body, one much larger spanning
    car+open-trunk -- overlapped at only ~10% IoU (too low for any
    standard IoU-based NMS/`agnostic_nms` threshold to catch, confirmed by
    testing several) despite the smaller box sitting ~56% inside the
    larger one.

    Deliberately scoped to *cross-class* pairs only (`candidate.class_id !=
    already_kept.class_id`), not merely "same merged type": two same-raw-
    class boxes have already been through YOLO's own per-class NMS
    upstream, so if they still both survived, that's real evidence they're
    genuinely separate objects, not the same one -- confirmed live on this
    deployment's own footage, where an earlier, broader version of this
    function (comparing same-type regardless of raw class) wrongly deleted
    a real, distinct second vehicle (a dark SUV parked beside a white one,
    both raw class "car") purely because its smaller box's rectangle fell
    within the larger SUV's rectangle -- geometric containment alone does
    not imply "same object" the way a cross-class collision does."""
    by_type: dict[str, list[RawDetection]] = {}
    for raw in raw_detections:
        object_type = COCO_TYPE_MAP.get(raw.class_id)
        if object_type is None:
            continue
        by_type.setdefault(object_type, []).append(raw)

    kept: list[RawDetection] = []
    for group in by_type.values():
        accepted: list[RawDetection] = []
        for candidate in sorted(group, key=lambda r: r.confidence, reverse=True):
            if any(
                already_kept.class_id != candidate.class_id
                and _overlap_over_smaller_area(candidate, already_kept) >= containment_threshold
                for already_kept in accepted
            ):
                continue
            accepted.append(candidate)
        kept.extend(accepted)
    return kept


def to_detections(
    *, camera_id: str, raw_detections: list[RawDetection], frame_width: int, frame_height: int,
    containment_threshold: float = _DUPLICATE_CONTAINMENT_THRESHOLD,
) -> list[Detection]:
    """Converts pixel-space `RawDetection`s to percentage-space `Detection`s
    matching the frontend contract exactly (Frontend Analysis Report §5:
    "normalized 0-100 coordinates, not pixels"). Applies
    `_suppress_contained_duplicates` first -- see that function's own
    docstring for the real, observed duplicate-vehicle case this fixes."""
    raw_detections = _suppress_contained_duplicates(raw_detections, containment_threshold=containment_threshold)
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
