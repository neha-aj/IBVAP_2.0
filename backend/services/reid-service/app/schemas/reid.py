import datetime as dt

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SearchByTrackRequest(_CamelModel):
    """`POST /reid/search` (doc09 §2.2): search using an already-tracked
    person's own stored embedding as the query -- the "Find this person
    elsewhere" context-menu flow (doc10 §2.3). Uploading a fresh reference
    photo instead goes through `POST /reid/search/upload`."""

    track_id: str


class MatchResult(_CamelModel):
    track_id: str
    camera_id: str
    camera_name: str
    timestamp: dt.datetime
    similarity_score: float
    snapshot_id: str | None
    # M24 security review follow-up: see anpr-service's `PlateReadRead`
    # for why this field exists alongside the bare id (frontend `<img
    # src>` needs a fetchable, token-scoped URL, not just an identifier).
    snapshot_url: str | None
