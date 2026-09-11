from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

Posture = Literal["standing", "sitting", "sleeping"]


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class PoseReading(_CamelModel):
    """One classified person's posture in one sampled frame. `x`/`y` are the
    pose's center point as percentage coordinates (0-100) relative to frame
    width/height -- the same normalization convention as detection-service's
    `BoundingBox` (`app/schemas/detection.py`), so the frontend can match a
    pose reading to the nearest `person` detection box by simple 2D distance
    against the box's own center (there's no shared track id between this
    service and detection-service to join on directly)."""

    x: float
    y: float
    posture: Posture
    confidence: float
