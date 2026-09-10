"""Shapes for data this service reads from other services -- mirrored
locally per Implementation Guide §3 ("no service imports another service's
package")."""

from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

TrackEventType = Literal["track.started", "track.updated", "track.lost"]
# `cam:{id}:tracks` carries every object type unfiltered -- this service
# only ever acts on "person", but parsing the stream message must still
# succeed for "vehicle"/"animal" too.
ObjectType = Literal["person", "vehicle", "animal"]


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
    loop_generation: int = 0
    correlation_id: str = ""


class Point(BaseModel):
    x: float
    y: float


class Zone(_CamelModel):
    """Mirrors `camera-service/app/schemas/zone.py::ZoneRead` (read via
    `GET /internal/cameras/{id}/zones`) -- only the fields this service
    actually uses, plus `requires_ppe` (Phase 2 M21's own DB addition)."""

    id: str
    name: str
    polygon: list[Point]
    zone_type: Literal["restricted", "perimeter", "general", "queue"]
    requires_ppe: bool = False


class InternalCameraConfig(BaseModel):
    """Mirrors `camera-service/app/schemas/internal.py::InternalCameraConfig`
    -- only the subset this service needs for camera discovery."""

    id: str
    name: str
    location: str
