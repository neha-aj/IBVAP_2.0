"""Track lifecycle event shape published to `cam:{id}:tracks`
(SAS §5.3: "Emits track lifecycle events (`track.started`, `track.updated`,
`track.lost`)")."""

from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.schemas.detection import BoundingBox, DetectionType

TrackEventType = Literal["track.started", "track.updated", "track.lost"]


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class TrackEvent(_CamelModel):
    event: TrackEventType
    track_id: str
    camera_id: str
    object_type: DetectionType
    # Bounding box is omitted for `track.lost` -- the object is no longer
    # detected, so there's nothing current to report a position for.
    bbox: BoundingBox | None = None
    # 0 for a live source or a file source's first play-through; increments
    # each time a looping file source restarts (threaded through from
    # ingestion-service's frame publisher). Lets the Event/Alert Service
    # recognize "this is a replay of already-counted footage" rather than
    # inflating `peopleDetectedToday` once per loop of a short test clip.
    loop_generation: int = 0
    # Traces this event back to the source frame it came from, through every
    # pipeline stage (SAS §10) -- bound from the incoming detections stream
    # message's own correlation id, not generated here.
    correlation_id: str = ""
