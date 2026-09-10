"""Shapes for data this service reads from other services -- mirrored
locally per Implementation Guide §3 ("no service imports another service's
package")."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

# "animal" added Phase 2 M21 -- this service only ever acts on
# type=="vehicle" detections, but `cam:{id}:detections` carries every
# object type unfiltered, so parsing must still accept the value.
DetectionType = Literal["person", "vehicle", "animal"]


class _CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class BoundingBox(_CamelModel):
    x: float
    y: float
    width: float
    height: float


class Detection(_CamelModel):
    """Mirrors `detection-service/app/schemas/detection.py::Detection` --
    what arrives on `cam:{id}:detections`."""

    id: str
    cameraId: str
    type: DetectionType
    confidence: float
    trackId: str | None = None
    bbox: BoundingBox


class InternalCameraConfig(BaseModel):
    """Mirrors `camera-service/app/schemas/internal.py::InternalCameraConfig`
    (read via `GET /internal/cameras`) -- only the subset this service needs
    for camera discovery."""

    id: str
    name: str
    location: str
