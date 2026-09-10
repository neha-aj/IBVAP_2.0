import uuid

import pytest
from pydantic import ValidationError

from ibvap_common.errors import ApiError, ConflictError, NotFoundError

from app.schemas.camera import CameraCreate, CameraUpdate
from app.services.camera_service import CameraService


class FakeSector:
    def __init__(self, name: str) -> None:
        self.id = uuid.uuid4()
        self.name = name
        self.code = name


class FakeCamera:
    def __init__(self, **kwargs) -> None:
        self.id = uuid.uuid4()
        self.external_id = kwargs["external_id"]
        self.name = kwargs["name"]
        self.location = kwargs["location"]
        self.sector_id = kwargs.get("sector_id")
        self.sector = kwargs.get("sector")
        self.type = kwargs["type"]
        self.source_url = kwargs.get("source_url")
        self.status = kwargs.get("status", "offline")
        self.resolution = kwargs.get("resolution")
        self.fps = kwargs.get("fps", 0)
        self.last_active_at = kwargs.get("last_active_at")


class FakeCameraRepo:
    def __init__(self) -> None:
        self.cameras: dict[str, FakeCamera] = {}

    async def get_by_external_id(self, external_id: str) -> FakeCamera | None:
        return self.cameras.get(external_id)

    async def exists_external_id(self, external_id: str) -> bool:
        return external_id in self.cameras

    async def list_paginated(self, *, status, sector, search, page, page_size):
        rows = list(self.cameras.values())
        if status:
            rows = [r for r in rows if r.status == status]
        if search:
            rows = [r for r in rows if search.lower() in r.name.lower()]
        return rows, len(rows)

    async def status_counts(self) -> dict[str, int]:
        counts = {"online": 0, "warning": 0, "offline": 0}
        for r in self.cameras.values():
            counts[r.status] = counts.get(r.status, 0) + 1
        return {**counts, "total": len(self.cameras)}

    async def create(self, camera: FakeCamera) -> FakeCamera:
        self.cameras[camera.external_id] = camera
        return camera

    async def update(self, camera: FakeCamera) -> FakeCamera:
        return camera

    async def delete(self, camera: FakeCamera) -> None:
        self.cameras.pop(camera.external_id, None)


class FakeSectorRepo:
    def __init__(self) -> None:
        self.sectors: dict[str, FakeSector] = {}

    async def get_or_create(self, name_or_code: str) -> FakeSector:
        if name_or_code not in self.sectors:
            self.sectors[name_or_code] = FakeSector(name_or_code)
        return self.sectors[name_or_code]


class FakeRedis:
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    async def publish(self, channel: str, message: str) -> None:
        self.published.append((channel, message))


class FakeCameraHealthRepo:
    def __init__(self) -> None:
        self.records: list[dict] = []

    async def record(self, *, camera_id, status: str, fps: int | None) -> None:
        self.records.append({"camera_id": camera_id, "status": status, "fps": fps})


@pytest.mark.asyncio
async def test_create_camera_generates_external_id_when_omitted() -> None:
    service = CameraService(FakeCameraRepo(), FakeSectorRepo())
    result = await service.create_camera(
        CameraCreate(name="North Gate", location="Sector A", type="file")
    )
    assert result.id.startswith("FILE-")
    assert result.status == "offline"
    assert result.detections.persons == 0


@pytest.mark.parametrize("bad_id", ["../../etc/passwd", "CAM/01", "CAM 01", "CAM\\01"])
def test_camera_create_rejects_unsafe_external_id(bad_id: str) -> None:
    """external_id ends up as a filesystem path segment on upload -- must
    never accept `/`, `..`, or other path-meaningful characters."""
    with pytest.raises(ValidationError):
        CameraCreate(external_id=bad_id, name="Gate", location="A", type="file")


def test_camera_create_accepts_safe_external_id() -> None:
    camera = CameraCreate(external_id="BOP-01_CAM01", name="Gate", location="A", type="file")
    assert camera.external_id == "BOP-01_CAM01"


@pytest.mark.asyncio
async def test_create_camera_rejects_duplicate_external_id() -> None:
    service = CameraService(FakeCameraRepo(), FakeSectorRepo())
    await service.create_camera(
        CameraCreate(external_id="CAM-01", name="Gate", location="A", type="webcam")
    )
    with pytest.raises(ConflictError):
        await service.create_camera(
            CameraCreate(external_id="CAM-01", name="Gate 2", location="B", type="webcam")
        )


@pytest.mark.asyncio
async def test_create_camera_accepts_thermal_type() -> None:
    """M11: a thermal-only camera is accepted through the existing
    create-camera path with no ingestion/detection changes needed yet."""
    service = CameraService(FakeCameraRepo(), FakeSectorRepo())
    result = await service.create_camera(
        CameraCreate(
            external_id="CAM-THERMAL-01", name="North Fence IR", location="A",
            type="thermal", source_url="rtsp://thermal-cam-1/stream",
        )
    )
    assert result.type == "thermal"


@pytest.mark.asyncio
async def test_create_camera_accepts_dual_type_with_both_urls() -> None:
    service = CameraService(FakeCameraRepo(), FakeSectorRepo())
    result = await service.create_camera(
        CameraCreate(
            external_id="CAM-DUAL-01", name="North Fence Dual", location="A", type="dual",
            source_url="rtsp://rgb-cam-1/stream", thermal_source_url="rtsp://thermal-cam-1/stream",
        )
    )
    assert result.type == "dual"
    assert result.thermal_source_url == "rtsp://thermal-cam-1/stream"


@pytest.mark.asyncio
async def test_create_camera_rejects_dual_type_missing_thermal_url() -> None:
    service = CameraService(FakeCameraRepo(), FakeSectorRepo())
    with pytest.raises(ApiError):
        await service.create_camera(
            CameraCreate(
                external_id="CAM-DUAL-02", name="Bad Dual", location="A", type="dual",
                source_url="rtsp://rgb-cam-1/stream",
            )
        )


@pytest.mark.asyncio
async def test_create_camera_rejects_dual_type_missing_rgb_url() -> None:
    service = CameraService(FakeCameraRepo(), FakeSectorRepo())
    with pytest.raises(ApiError):
        await service.create_camera(
            CameraCreate(
                external_id="CAM-DUAL-03", name="Bad Dual", location="A", type="dual",
                thermal_source_url="rtsp://thermal-cam-1/stream",
            )
        )


@pytest.mark.asyncio
async def test_create_camera_accepts_dual_type_with_neither_url() -> None:
    """M11 revision: a 'dual' camera can also be created with neither URL
    set, to be filled in later via two POST /upload calls (?slot=rgb /
    ?slot=thermal) -- same precedent as 'file' cameras, which have always
    been creatable with no source_url up front."""
    service = CameraService(FakeCameraRepo(), FakeSectorRepo())
    result = await service.create_camera(
        CameraCreate(external_id="CAM-DUAL-05", name="Dual (upload flow)", location="A", type="dual")
    )
    assert result.type == "dual"


@pytest.mark.asyncio
async def test_set_uploaded_source_default_slot_sets_rgb_url_on_dual_camera() -> None:
    service = CameraService(FakeCameraRepo(), FakeSectorRepo())
    await service.create_camera(
        CameraCreate(external_id="CAM-DUAL-06", name="Dual", location="A", type="dual")
    )
    updated = await service.set_uploaded_source("CAM-DUAL-06", "/data/media/uploads/CAM-DUAL-06/rgb.mp4")
    assert updated.id == "CAM-DUAL-06"


@pytest.mark.asyncio
async def test_set_uploaded_source_thermal_slot_sets_thermal_url_on_dual_camera() -> None:
    service = CameraService(FakeCameraRepo(), FakeSectorRepo())
    await service.create_camera(
        CameraCreate(external_id="CAM-DUAL-07", name="Dual", location="A", type="dual")
    )
    updated = await service.set_uploaded_source(
        "CAM-DUAL-07", "/data/media/uploads/CAM-DUAL-07/thermal.mp4", slot="thermal"
    )
    assert updated.thermal_source_url == "/data/media/uploads/CAM-DUAL-07/thermal.mp4"


@pytest.mark.asyncio
async def test_set_uploaded_source_thermal_slot_rejects_non_dual_camera() -> None:
    service = CameraService(FakeCameraRepo(), FakeSectorRepo())
    await service.create_camera(
        CameraCreate(external_id="CAM-THERMAL-02", name="Thermal-only", location="A", type="thermal")
    )
    with pytest.raises(ConflictError):
        await service.set_uploaded_source("CAM-THERMAL-02", "/x.mp4", slot="thermal")


@pytest.mark.asyncio
async def test_set_uploaded_source_accepts_thermal_type_camera() -> None:
    """A thermal-only (non-dual) camera also uses the upload flow --
    default slot fills its own single source_url."""
    service = CameraService(FakeCameraRepo(), FakeSectorRepo())
    await service.create_camera(
        CameraCreate(external_id="CAM-THERMAL-03", name="Thermal-only", location="A", type="thermal")
    )
    updated = await service.set_uploaded_source("CAM-THERMAL-03", "/data/media/uploads/CAM-THERMAL-03/x.mp4")
    assert updated.id == "CAM-THERMAL-03"


@pytest.mark.asyncio
async def test_update_camera_sets_thermal_source_url() -> None:
    service = CameraService(FakeCameraRepo(), FakeSectorRepo())
    await service.create_camera(
        CameraCreate(
            external_id="CAM-DUAL-04", name="Dual", location="A", type="dual",
            source_url="rtsp://rgb-cam-1/stream", thermal_source_url="rtsp://thermal-cam-1/stream",
        )
    )
    updated = await service.update_camera(
        "CAM-DUAL-04", CameraUpdate(thermal_source_url="rtsp://thermal-cam-2/stream")
    )
    assert updated.thermal_source_url == "rtsp://thermal-cam-2/stream"


@pytest.mark.asyncio
async def test_get_camera_not_found_raises() -> None:
    service = CameraService(FakeCameraRepo(), FakeSectorRepo())
    with pytest.raises(NotFoundError):
        await service.get_camera("NOPE-01")


@pytest.mark.asyncio
async def test_update_camera_changes_name_and_sector() -> None:
    service = CameraService(FakeCameraRepo(), FakeSectorRepo())
    await service.create_camera(
        CameraCreate(external_id="CAM-02", name="Old Name", location="A", type="ip")
    )
    updated = await service.update_camera("CAM-02", CameraUpdate(name="New Name", sector="Bravo"))
    assert updated.name == "New Name"
    assert updated.sector == "Bravo"


@pytest.mark.asyncio
async def test_set_uploaded_source_requires_file_type() -> None:
    service = CameraService(FakeCameraRepo(), FakeSectorRepo())
    await service.create_camera(
        CameraCreate(external_id="CAM-03", name="Webcam", location="A", type="webcam")
    )
    with pytest.raises(ConflictError):
        await service.set_uploaded_source("CAM-03", "/data/media/uploads/x.mp4")


@pytest.mark.asyncio
async def test_set_uploaded_source_sets_path_for_file_camera() -> None:
    service = CameraService(FakeCameraRepo(), FakeSectorRepo())
    await service.create_camera(
        CameraCreate(external_id="CAM-04", name="Uploaded Clip", location="A", type="file")
    )
    updated = await service.set_uploaded_source("CAM-04", "/data/media/uploads/CAM-04/x.mp4")
    assert updated.id == "CAM-04"


@pytest.mark.asyncio
async def test_update_status_publishes_on_real_transition_only() -> None:
    repo = FakeCameraRepo()
    redis = FakeRedis()
    service = CameraService(repo, FakeSectorRepo(), redis)
    await service.create_camera(CameraCreate(external_id="CAM-05", name="Gate", location="A", type="ip"))

    await service.update_status("CAM-05", status="online", fps=15)
    assert len(redis.published) == 1
    channel, payload = redis.published[0]
    assert channel == "camera.status_changed"
    assert '"cameraId": "CAM-05"' in payload
    assert '"status": "online"' in payload

    # Same status again (a routine heartbeat, not a transition) must not
    # re-publish -- only actual status changes matter downstream.
    await service.update_status("CAM-05", status="online", fps=15)
    assert len(redis.published) == 1


@pytest.mark.asyncio
async def test_update_status_records_health_on_every_call_not_just_transitions() -> None:
    repo = FakeCameraRepo()
    health_repo = FakeCameraHealthRepo()
    service = CameraService(repo, FakeSectorRepo(), camera_health_repo=health_repo)
    await service.create_camera(CameraCreate(external_id="CAM-06", name="Gate", location="A", type="ip"))

    await service.update_status("CAM-06", status="online", fps=15)
    await service.update_status("CAM-06", status="online", fps=14)  # same status, still a heartbeat

    assert len(health_repo.records) == 2
    assert all(r["status"] == "online" for r in health_repo.records)
    assert [r["fps"] for r in health_repo.records] == [15, 14]


@pytest.mark.asyncio
async def test_status_summary_counts_by_status() -> None:
    repo = FakeCameraRepo()
    service = CameraService(repo, FakeSectorRepo())
    await service.create_camera(CameraCreate(name="A", location="A", type="ip"))
    await service.create_camera(CameraCreate(name="B", location="A", type="ip"))
    repo.cameras[next(iter(repo.cameras.keys()))].status = "online"

    summary = await service.status_summary()
    assert summary.total == 2
    assert summary.online == 1
    assert summary.offline == 1
