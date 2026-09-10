"""Wraps `supervision`'s ByteTrack implementation (SAS §5.3: "Tracking
Service consumes detections per camera, runs ByteTrack, assigns/maintains
persistent `track_id`s across frames"). One instance per camera -- ByteTrack
keeps Kalman-filter state across calls, so `track_id` continuity depends on
calling `update` with the same camera's detections in temporal order (that's
`track_manager.TrackManager`'s job, one runner per camera_id).

Detections arrive already normalized to percentage-of-frame coordinates
(Detection Service, M4) -- ByteTrack's math (Kalman filtering, IoU matching)
is unit-agnostic, so tracking directly in percentage space works exactly the
same as pixel space and avoids needing to know the source frame's dimensions
here at all.
"""

from __future__ import annotations

import uuid

import numpy as np
import supervision as sv

from app.schemas.detection import BoundingBox, Detection

# ByteTrack's own internal class ids -- unrelated to COCO's ids (detection-
# service's own concern only), just a local 0/1/2 enum for this tracker.
# "animal": 2 added Phase 2 M21.
_CLASS_BY_TYPE = {"person": 0, "vehicle": 1, "animal": 2}
_TYPE_BY_CLASS = {0: "person", 1: "vehicle", 2: "animal"}


class ByteTrackRunner:
    def __init__(
        self,
        *,
        frame_rate: int,
        track_activation_threshold: float,
        lost_track_buffer_frames: int,
        minimum_matching_threshold: float,
        minimum_consecutive_frames: int = 1,
    ) -> None:
        self._tracker = sv.ByteTrack(
            frame_rate=frame_rate,
            track_activation_threshold=track_activation_threshold,
            lost_track_buffer=lost_track_buffer_frames,
            minimum_matching_threshold=minimum_matching_threshold,
            minimum_consecutive_frames=minimum_consecutive_frames,
        )

    def update(self, camera_id: str, detections: list[Detection]) -> list[Detection]:
        """Feeds one frame's detections in and returns the currently-active
        tracked objects -- NOT necessarily the same list/order/count as the
        input (ByteTrack drops unmatched low-confidence detections and ages
        out tracks with no recent match), so the output is reconstructed
        entirely from the tracker's own returned arrays rather than trying
        to correlate back to the input `Detection` objects by position."""
        if detections:
            xyxy = np.array(
                [
                    [d.bbox.x, d.bbox.y, d.bbox.x + d.bbox.width, d.bbox.y + d.bbox.height]
                    for d in detections
                ],
                dtype=float,
            )
            confidence = np.array([d.confidence for d in detections], dtype=float)
            class_id = np.array([_CLASS_BY_TYPE[d.type] for d in detections], dtype=int)
            sv_detections = sv.Detections(xyxy=xyxy, confidence=confidence, class_id=class_id)
        else:
            sv_detections = sv.Detections.empty()

        tracked = self._tracker.update_with_detections(sv_detections)

        results: list[Detection] = []
        for i in range(len(tracked)):
            if tracked.tracker_id is None:
                break
            track_id = tracked.tracker_id[i]
            x1, y1, x2, y2 = tracked.xyxy[i]
            class_id = int(tracked.class_id[i]) if tracked.class_id is not None else 0
            confidence = float(tracked.confidence[i]) if tracked.confidence is not None else 0.0
            results.append(
                Detection(
                    id=str(uuid.uuid4()),
                    cameraId=camera_id,
                    type=_TYPE_BY_CLASS.get(class_id, "person"),  # type: ignore[arg-type]
                    confidence=round(confidence, 4),
                    trackId=str(int(track_id)),
                    bbox=BoundingBox(x=float(x1), y=float(y1), width=float(x2 - x1), height=float(y2 - y1)),
                )
            )
        return results
