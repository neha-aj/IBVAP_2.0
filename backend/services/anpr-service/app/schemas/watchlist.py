import datetime as dt

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class WatchlistCreate(_CamelModel):
    plate_text: str
    reason: str | None = None


class WatchlistRead(_CamelModel):
    id: str
    plate_text: str
    reason: str | None
    created_at: dt.datetime
