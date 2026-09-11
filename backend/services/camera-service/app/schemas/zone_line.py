from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.schemas.zone import Point

# Behavioral analytics: "fence" marks a line as a perimeter barrier rather
# than an ordinary road/lane boundary -- event-alert-service's
# `_check_line_crossing` reports "Fence Climbing Detected" instead of the
# generic "Line Crossing"/"Wrong-Way Movement" for a person crossing one.
# None (the default every pre-existing line has) means "boundary", today's
# only behavior.
LineType = Literal["boundary", "fence"]


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ZoneLineRead(_CamelModel):
    id: str
    name: str
    point_a: Point
    point_b: Point
    direction: str | None
    line_type: LineType | None = None


class ZoneLineCreate(_CamelModel):
    name: str
    point_a: Point
    point_b: Point
    direction: str | None = None
    line_type: LineType | None = None


class ZoneLineUpdate(_CamelModel):
    name: str | None = None
    point_a: Point | None = None
    point_b: Point | None = None
    direction: str | None = None
    line_type: LineType | None = None
