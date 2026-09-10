import datetime as dt

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class PlateReadRead(_CamelModel):
    """`GET /anpr/reads` (doc09 §2.1)."""

    id: str
    camera_id: str
    track_id: str | None
    plate_text: str
    confidence: float
    snapshot_id: str | None
    # M24 security review follow-up: the actual fetchable URL for
    # `snapshot_id`, with a short-lived resource token embedded (see
    # `ibvap_common.stream_auth.build_resource_url`) -- the frontend's
    # `<img src>` can't attach an `Authorization` header, so a bare id
    # isn't enough on its own. `snapshot_id` is kept alongside it for
    # any other consumer that only needs the identifier.
    snapshot_url: str | None
    watchlist_match: bool
    created_at: dt.datetime


class PlateReadListResponse(_CamelModel):
    items: list[PlateReadRead]
    total: int
    page: int
    page_size: int
