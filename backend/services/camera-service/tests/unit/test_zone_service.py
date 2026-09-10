import uuid

import pytest

from ibvap_common.errors import NotFoundError

# ZoneService/ZoneLineService construct real SQLAlchemy `Zone`/`ZoneLine`
# ORM objects (the fakes below are only for the repository layer) -- the
# first instantiation of any mapped class triggers SQLAlchemy to configure
# every mapper sharing its declarative registry, including `Camera`, whose
# `sector` relationship is a string reference ("Sector") that only resolves
# if `app.models.sector` has actually been imported somewhere first.
import app.models.camera
import app.models.sector  # noqa: F401
from app.schemas.zone import Point, ZoneCreate, ZoneUpdate
from app.schemas.zone_line import ZoneLineCreate, ZoneLineUpdate
from app.services.zone_line_service import ZoneLineService
from app.services.zone_service import ZoneService


class FakeCamera:
    def __init__(self, external_id: str) -> None:
        self.id = uuid.uuid4()
        self.external_id = external_id


class FakeCameraRepo:
    def __init__(self, cameras: list[FakeCamera]) -> None:
        self._by_external_id = {c.external_id: c for c in cameras}

    async def get_by_external_id(self, external_id: str) -> FakeCamera | None:
        return self._by_external_id.get(external_id)


class FakeZone:
    def __init__(
        self, camera_id, name: str, polygon: list, zone_type: str, density_threshold=None, requires_ppe=False,
    ) -> None:
        self.id = uuid.uuid4()
        self.camera_id = camera_id
        self.name = name
        self.polygon = polygon
        self.zone_type = zone_type
        self.density_threshold = density_threshold
        self.requires_ppe = requires_ppe


class FakeZoneRepo:
    def __init__(self) -> None:
        self.zones: dict[uuid.UUID, FakeZone] = {}

    async def list_by_camera_id(self, camera_id) -> list[FakeZone]:
        return [z for z in self.zones.values() if z.camera_id == camera_id]

    async def get_by_id(self, camera_id, zone_id) -> FakeZone | None:
        zone = self.zones.get(zone_id)
        return zone if zone and zone.camera_id == camera_id else None

    async def create(self, zone: FakeZone) -> FakeZone:
        self.zones[zone.id] = zone
        return zone

    async def update(
        self, zone: FakeZone, *, name, polygon, zone_type, density_threshold=None, requires_ppe=None,
    ) -> FakeZone:
        if name is not None:
            zone.name = name
        if polygon is not None:
            zone.polygon = polygon
        if zone_type is not None:
            zone.zone_type = zone_type
        if density_threshold is not None:
            zone.density_threshold = density_threshold
        if requires_ppe is not None:
            zone.requires_ppe = requires_ppe
        return zone

    async def delete(self, zone: FakeZone) -> None:
        self.zones.pop(zone.id, None)


class FakeZoneLine:
    def __init__(self, camera_id, name: str, point_a: dict, point_b: dict, direction: str | None) -> None:
        self.id = uuid.uuid4()
        self.camera_id = camera_id
        self.name = name
        self.point_a = point_a
        self.point_b = point_b
        self.direction = direction


class FakeZoneLineRepo:
    def __init__(self) -> None:
        self.lines: dict[uuid.UUID, FakeZoneLine] = {}

    async def list_by_camera_id(self, camera_id) -> list[FakeZoneLine]:
        return [line for line in self.lines.values() if line.camera_id == camera_id]

    async def get_by_id(self, camera_id, zone_line_id) -> FakeZoneLine | None:
        line = self.lines.get(zone_line_id)
        return line if line and line.camera_id == camera_id else None

    async def create(self, line: FakeZoneLine) -> FakeZoneLine:
        self.lines[line.id] = line
        return line

    async def update(self, line: FakeZoneLine, *, name, point_a, point_b, direction) -> FakeZoneLine:
        if name is not None:
            line.name = name
        if point_a is not None:
            line.point_a = point_a
        if point_b is not None:
            line.point_b = point_b
        if direction is not None:
            line.direction = direction
        return line

    async def delete(self, line: FakeZoneLine) -> None:
        self.lines.pop(line.id, None)


_SQUARE = [Point(x=10, y=10), Point(x=90, y=10), Point(x=90, y=90), Point(x=10, y=90)]


@pytest.mark.asyncio
async def test_create_and_list_zone() -> None:
    camera = FakeCamera("CAM-01")
    service = ZoneService(FakeZoneRepo(), FakeCameraRepo([camera]))

    created = await service.create_zone("CAM-01", ZoneCreate(name="Perimeter", polygon=_SQUARE, zone_type="restricted"))
    assert created.zone_type == "restricted"

    zones = await service.list_zones("CAM-01")
    assert len(zones) == 1
    assert zones[0].name == "Perimeter"


@pytest.mark.asyncio
async def test_create_zone_unknown_camera_raises() -> None:
    service = ZoneService(FakeZoneRepo(), FakeCameraRepo([]))
    with pytest.raises(NotFoundError):
        await service.create_zone("NOPE", ZoneCreate(name="Zone", polygon=_SQUARE))


@pytest.mark.asyncio
async def test_zones_are_scoped_per_camera() -> None:
    cam_a, cam_b = FakeCamera("CAM-A"), FakeCamera("CAM-B")
    service = ZoneService(FakeZoneRepo(), FakeCameraRepo([cam_a, cam_b]))

    await service.create_zone("CAM-A", ZoneCreate(name="A-Zone", polygon=_SQUARE))
    await service.create_zone("CAM-B", ZoneCreate(name="B-Zone", polygon=_SQUARE))

    assert [z.name for z in await service.list_zones("CAM-A")] == ["A-Zone"]
    assert [z.name for z in await service.list_zones("CAM-B")] == ["B-Zone"]


@pytest.mark.asyncio
async def test_update_zone_changes_polygon_and_name() -> None:
    camera = FakeCamera("CAM-01")
    service = ZoneService(FakeZoneRepo(), FakeCameraRepo([camera]))
    created = await service.create_zone("CAM-01", ZoneCreate(name="Zone", polygon=_SQUARE))

    updated = await service.update_zone(
        "CAM-01", uuid.UUID(created.id),
        ZoneUpdate(name="Renamed", polygon=[Point(x=0, y=0), Point(x=1, y=1), Point(x=1, y=0)]),
    )
    assert updated.name == "Renamed"
    assert len(updated.polygon) == 3


@pytest.mark.asyncio
async def test_create_zone_requires_ppe_defaults_false_and_is_settable() -> None:
    camera = FakeCamera("CAM-01")
    service = ZoneService(FakeZoneRepo(), FakeCameraRepo([camera]))

    default_zone = await service.create_zone("CAM-01", ZoneCreate(name="Office", polygon=_SQUARE))
    assert default_zone.requires_ppe is False

    ppe_zone = await service.create_zone(
        "CAM-01", ZoneCreate(name="Construction Area", polygon=_SQUARE, requires_ppe=True)
    )
    assert ppe_zone.requires_ppe is True


@pytest.mark.asyncio
async def test_update_zone_toggles_requires_ppe() -> None:
    camera = FakeCamera("CAM-01")
    service = ZoneService(FakeZoneRepo(), FakeCameraRepo([camera]))
    created = await service.create_zone("CAM-01", ZoneCreate(name="Zone", polygon=_SQUARE))
    assert created.requires_ppe is False

    updated = await service.update_zone("CAM-01", uuid.UUID(created.id), ZoneUpdate(requires_ppe=True))
    assert updated.requires_ppe is True


@pytest.mark.asyncio
async def test_update_zone_not_found_raises() -> None:
    camera = FakeCamera("CAM-01")
    service = ZoneService(FakeZoneRepo(), FakeCameraRepo([camera]))
    with pytest.raises(NotFoundError):
        await service.update_zone("CAM-01", uuid.uuid4(), ZoneUpdate(name="X"))


@pytest.mark.asyncio
async def test_delete_zone_removes_it() -> None:
    camera = FakeCamera("CAM-01")
    service = ZoneService(FakeZoneRepo(), FakeCameraRepo([camera]))
    created = await service.create_zone("CAM-01", ZoneCreate(name="Zone", polygon=_SQUARE))

    await service.delete_zone("CAM-01", uuid.UUID(created.id))
    assert await service.list_zones("CAM-01") == []


@pytest.mark.asyncio
async def test_delete_zone_not_found_raises() -> None:
    camera = FakeCamera("CAM-01")
    service = ZoneService(FakeZoneRepo(), FakeCameraRepo([camera]))
    with pytest.raises(NotFoundError):
        await service.delete_zone("CAM-01", uuid.uuid4())


@pytest.mark.asyncio
async def test_create_and_list_zone_line() -> None:
    camera = FakeCamera("CAM-01")
    service = ZoneLineService(FakeZoneLineRepo(), FakeCameraRepo([camera]))

    created = await service.create_zone_line(
        "CAM-01",
        ZoneLineCreate(name="Boundary", point_a=Point(x=0, y=50), point_b=Point(x=100, y=50), direction="a_to_b"),
    )
    assert created.direction == "a_to_b"

    lines = await service.list_zone_lines("CAM-01")
    assert len(lines) == 1
    assert lines[0].name == "Boundary"


@pytest.mark.asyncio
async def test_update_zone_line_changes_points() -> None:
    camera = FakeCamera("CAM-01")
    service = ZoneLineService(FakeZoneLineRepo(), FakeCameraRepo([camera]))
    created = await service.create_zone_line(
        "CAM-01", ZoneLineCreate(name="Line", point_a=Point(x=0, y=0), point_b=Point(x=1, y=1))
    )

    updated = await service.update_zone_line(
        "CAM-01", uuid.UUID(created.id), ZoneLineUpdate(point_b=Point(x=99, y=99))
    )
    assert updated.point_b.x == 99


@pytest.mark.asyncio
async def test_delete_zone_line_removes_it() -> None:
    camera = FakeCamera("CAM-01")
    service = ZoneLineService(FakeZoneLineRepo(), FakeCameraRepo([camera]))
    created = await service.create_zone_line(
        "CAM-01", ZoneLineCreate(name="Line", point_a=Point(x=0, y=0), point_b=Point(x=1, y=1))
    )

    await service.delete_zone_line("CAM-01", uuid.UUID(created.id))
    assert await service.list_zone_lines("CAM-01") == []
