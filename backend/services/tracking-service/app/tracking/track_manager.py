"""Owns one `ByteTrackRunner` per camera (track continuity is per-camera
Kalman-filter state, so cameras must never share a tracker instance) and
derives lifecycle events from the set of active track ids before/after each
update (SAS §5.3: `track.started` / `track.updated` / `track.lost`)."""

from __future__ import annotations

from ibvap_common.logging import get_correlation_id

from app.core.config import Settings
from app.schemas.detection import Detection
from app.schemas.track import TrackEvent
from app.tracking.bytetrack_runner import ByteTrackRunner


class TrackManager:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._runners: dict[str, ByteTrackRunner] = {}
        self._active_track_ids: dict[str, set[str]] = {}
        # Remembers each active track's object type so a `track.lost` event
        # (which has no fresh detection to read a type from) can still
        # report the right one -- consumers (e.g. the Event/Alert Service's
        # per-type active-count rule) need this to be correct, not a
        # hardcoded guess.
        self._track_types: dict[str, dict[str, str]] = {}

    def remove_camera(self, camera_id: str) -> None:
        self._runners.pop(camera_id, None)
        self._active_track_ids.pop(camera_id, None)
        self._track_types.pop(camera_id, None)

    def update(
        self, camera_id: str, detections: list[Detection], *, loop_generation: int = 0
    ) -> tuple[list[Detection], list[TrackEvent]]:
        """Returns the currently-tracked detections (for the overlay cache)
        and the lifecycle events this update produced (for `cam:{id}:tracks`)."""
        runner = self._runners.setdefault(camera_id, self._build_runner())
        tracked = runner.update(camera_id, detections)

        previous_ids = self._active_track_ids.get(camera_id, set())
        current_ids = {d.trackId for d in tracked if d.trackId is not None}
        known_types = self._track_types.setdefault(camera_id, {})

        events: list[TrackEvent] = []
        tracked_by_id = {d.trackId: d for d in tracked}
        for track_id in current_ids - previous_ids:
            known_types[track_id] = tracked_by_id[track_id].type
            events.append(self._event("track.started", tracked_by_id[track_id], loop_generation))
        for track_id in current_ids & previous_ids:
            known_types[track_id] = tracked_by_id[track_id].type
            events.append(self._event("track.updated", tracked_by_id[track_id], loop_generation))
        for track_id in previous_ids - current_ids:
            object_type = known_types.pop(track_id, "person")
            events.append(
                TrackEvent(
                    event="track.lost",
                    track_id=track_id,
                    camera_id=camera_id,
                    object_type=object_type,
                    bbox=None,
                    loop_generation=loop_generation,
                    correlation_id=get_correlation_id(),
                )
            )

        self._active_track_ids[camera_id] = current_ids
        return tracked, events

    def _event(self, event_type: str, detection: Detection, loop_generation: int) -> TrackEvent:
        return TrackEvent(
            event=event_type,  # type: ignore[arg-type]
            track_id=detection.trackId,  # type: ignore[arg-type]
            camera_id=detection.cameraId,
            object_type=detection.type,
            bbox=detection.bbox,
            loop_generation=loop_generation,
            correlation_id=get_correlation_id(),
        )

    def _build_runner(self) -> ByteTrackRunner:
        return ByteTrackRunner(
            frame_rate=self._settings.track_frame_rate,
            track_activation_threshold=self._settings.track_activation_threshold,
            lost_track_buffer_frames=self._settings.lost_track_buffer_frames,
            minimum_matching_threshold=self._settings.minimum_matching_threshold,
            minimum_consecutive_frames=self._settings.minimum_consecutive_frames,
        )
