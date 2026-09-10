import datetime as dt

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class RecordingRead(_CamelModel):
    """API Spec §6: "Recording metadata + playback URL"."""

    id: str
    camera_id: str
    start_time: dt.datetime
    end_time: dt.datetime
    duration_seconds: int
    playback_url: str


class RecordingCreated(_CamelModel):
    """Phase 2 M23: `POST /media/recordings` returns `{id, url}` -- same
    shape as `SnapshotCreated`, for the same reason (the caller only ever
    needs these two fields at capture time)."""

    id: str
    url: str
