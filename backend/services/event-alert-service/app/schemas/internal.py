"""Shapes for data this service reads from other services -- mirrored
locally per Implementation Guide §3 ("no service imports another service's
package")."""

from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

TrackEventType = Literal["track.started", "track.updated", "track.lost"]
# "animal" added Phase 2 M21 -- doc09 §2.7: flows through the rule engine
# identically to person/vehicle (the zone/intrusion rules already key off
# bbox position, not object_type, so no engine change is needed beyond
# accepting the value here). Count-threshold and Crowd Density stay
# person/vehicle-only by design (see engine.py's own object_type checks).
# "bag" added for Abandoned Object Detection (behavioral analytics) --
# tracked the same way, but only `engine.py`'s new abandoned-object check
# reads it; every other rule ignores a "bag" track exactly like it already
# ignores "animal" tracks it doesn't care about.
ObjectType = Literal["person", "vehicle", "animal", "bag"]


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class BoundingBox(_CamelModel):
    x: float
    y: float
    width: float
    height: float


class TrackEvent(_CamelModel):
    """Mirrors `tracking-service/app/schemas/track.py::TrackEvent` -- what
    arrives on `cam:{id}:tracks`."""

    event: TrackEventType
    track_id: str
    camera_id: str
    object_type: ObjectType
    bbox: BoundingBox | None = None
    # 0 for a live source or a file source's first play-through; increments
    # each time a looping file source restarts. Used to avoid double-
    # counting a short looping test clip's same people once per loop.
    loop_generation: int = 0
    # Traces this event back to the source frame it came from, through every
    # pipeline stage (SAS §10) -- bound for the duration of rule evaluation
    # so any outbound calls made while handling it (zone lookups, snapshot
    # capture) carry it too.
    correlation_id: str = ""


class Point(BaseModel):
    x: float
    y: float


class Zone(_CamelModel):
    """Mirrors `camera-service/app/schemas/zone.py::ZoneRead` (read via
    `GET /internal/cameras/{id}/zones`, which serializes `zone_type` as
    `zoneType` -- this needs the same camelCase handling, not plain
    `BaseModel`, or every response with a configured zone fails to parse."""

    id: str
    name: str
    polygon: list[Point]
    zone_type: Literal["restricted", "perimeter", "general", "queue"]
    # Phase 2 M14 Crowd Density: null unless the operator opted this zone
    # into density alerting.
    density_threshold: float | None = None


class ZoneLine(_CamelModel):
    """Mirrors `camera-service/app/schemas/zone_line.py::ZoneLineRead` (read
    via `GET /internal/cameras/{id}/zone-lines`), for the Line Crossing
    (M13) / Wrong-Way (M14) rules -- a line isn't a polygon, hence its own
    shape rather than reusing `Zone`."""

    id: str
    name: str
    point_a: Point
    point_b: Point
    direction: str | None = None
    # Fence Climbing Detection (behavioral analytics): None/"boundary" (every
    # pre-existing line) behaves exactly as before; "fence" makes
    # `engine.py::_check_line_crossing` report "Fence Climbing Detected"
    # instead of the generic Line Crossing/Wrong-Way labels for a person.
    line_type: str | None = None


class Calibration(_CamelModel):
    """Mirrors `camera-service/app/schemas/camera.py::Calibration`, for the
    Speed Estimation rule (M14)."""

    pixel_distance: float
    real_world_meters: float
    threshold_kmh: float


class ExternalDetectionEvent(_CamelModel):
    """Phase 2 doc08 §4's "shared internal event contract": every Category B
    AI service (ANPR/M15, Re-ID/M16, Face/M18, Tamper/M20, Fire-Smoke/M19,
    PPE/M21) reports a positive detection through this one path rather than
    inventing its own notification system -- posted to `POST /internal/events`
    (M2M-token auth, same as every other internal endpoint), which turns it
    into a normal `events`/`alerts` row via the exact same `EventDraft` ->
    `PubSubPublisher.persist_and_publish` machinery the rule engine itself
    uses, so it rides the existing `event.new`/`alert.new` Pub/Sub -> WS ->
    frontend path with zero frontend changes."""

    source_service: str
    event_type: str
    camera_id: str  # external_id
    object_type: str | None = None
    severity: Literal["critical", "high", "medium", "low"]
    requires_review: bool = True
    description: str | None = None


class CameraInfo(_CamelModel):
    """The subset of `CameraDetail` (camera-service) this service needs to
    denormalize onto events/alerts -- resolved via its public API, not a
    cross-schema DB read (IG §6)."""

    id: str
    name: str
    location: str
    calibration: Calibration | None = None
