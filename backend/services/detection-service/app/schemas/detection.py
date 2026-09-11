from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

# "animal" added Phase 2 M21; "bag" added for Abandoned Object Detection
# (behavioral analytics) -- see app/inference/base.py::COCO_TYPE_MAP.
DetectionType = Literal["person", "vehicle", "animal", "bag"]


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class BoundingBox(_CamelModel):
    """Percentage coordinates (0-100) relative to frame width/height -- the
    exact frontend `DetectionOverlay` contract (Frontend Analysis Report §5),
    not pixels."""

    x: float
    y: float
    width: float
    height: float


class Detection(_CamelModel):
    """One detected object in one frame, matching API Spec §2
    `GET /cameras/{id}/detections/current` and §8 `detection.new` shapes
    exactly. `track_id` stays null until the Tracking Service (M5) exists."""

    id: str
    camera_id: str
    type: DetectionType
    confidence: float
    track_id: str | None = None
    bbox: BoundingBox
    # M11: cross-modal agreement (0-1 IoU) for a 'dual' camera's fused
    # detections -- set only when a thermal counterpart was actually found
    # and used to boost this detection's confidence (SAS M11 §6 step 2).
    # None for every other camera type, and for thermal-only/unmatched
    # detections that had nothing to compare against.
    fusion_score: float | None = None
