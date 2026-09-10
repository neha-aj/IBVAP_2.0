from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

# "queue" added Phase 2 M14 (Queue Detection).
ZoneType = Literal["restricted", "perimeter", "general", "queue"]


class Point(BaseModel):
    x: float
    y: float


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ZoneRead(_CamelModel):
    id: str
    name: str
    polygon: list[Point]
    zone_type: ZoneType
    # Phase 2 M14 Crowd Density: null unless the operator opted this zone
    # into density alerting.
    density_threshold: float | None = None
    # Phase 2 M21 PPE Detection: opt-in per zone, default off.
    requires_ppe: bool = False


class ZoneCreate(_CamelModel):
    name: str
    polygon: list[Point]
    zone_type: ZoneType = "general"
    density_threshold: float | None = None
    requires_ppe: bool = False


class ZoneUpdate(_CamelModel):
    name: str | None = None
    polygon: list[Point] | None = None
    zone_type: ZoneType | None = None
    density_threshold: float | None = None
    requires_ppe: bool | None = None
