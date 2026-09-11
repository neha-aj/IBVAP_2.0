"""Mirrors `detection-service/app/schemas/detection.py` field-for-field --
per Implementation Guide §3 ("no service imports another service's
package"), each service that needs this shape defines its own copy. This is
what arrives on `cam:{id}:detections` and what this service republishes
(now with `track_id` populated) to `cam:{id}:current_detections`.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

# "animal" added Phase 2 M21; "bag" added for Abandoned Object Detection
# (behavioral analytics) -- see detection-service's own COCO_TYPE_MAP/
# DetectionType for where this originates.
DetectionType = Literal["person", "vehicle", "animal", "bag"]


class _CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class BoundingBox(_CamelModel):
    x: float
    y: float
    width: float
    height: float


class Detection(_CamelModel):
    id: str
    cameraId: str
    type: DetectionType
    confidence: float
    trackId: str | None = None
    bbox: BoundingBox
