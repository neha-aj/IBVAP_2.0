from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.schemas.zone import Point


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ZoneLineRead(_CamelModel):
    id: str
    name: str
    point_a: Point
    point_b: Point
    direction: str | None


class ZoneLineCreate(_CamelModel):
    name: str
    point_a: Point
    point_b: Point
    direction: str | None = None


class ZoneLineUpdate(_CamelModel):
    name: str | None = None
    point_a: Point | None = None
    point_b: Point | None = None
    direction: str | None = None
