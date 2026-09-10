import datetime as dt
import uuid

from redis.asyncio import Redis

from ibvap_common.errors import ApiError, ConflictError, NotFoundError
from ibvap_common.redis_pubsub import publish_event

from app.models.camera import Camera
from app.repositories.camera_health_repo import CameraHealthRepository
from app.repositories.camera_repo import CameraRepository
from app.repositories.sector_repo import SectorRepository
from app.schemas.camera import (
    Calibration,
    CameraCreate,
    CameraDetail,
    CameraListResponse,
    CameraRead,
    CameraStatusSummary,
    CameraUpdate,
    DetectionCounts,
)


def _generate_external_id(camera_type: str) -> str:
    return f"{camera_type.upper()}-{uuid.uuid4().hex[:8].upper()}"


def _to_read(camera: Camera) -> CameraRead:
    return CameraRead(
        id=camera.external_id,
        name=camera.name,
        location=camera.location,
        sector=camera.sector.name if camera.sector else None,
        status=camera.status,  # type: ignore[arg-type]
        resolution=camera.resolution,
        fps=camera.fps,
        last_active=camera.last_active_at.strftime("%H:%M:%S") if camera.last_active_at else None,
        # Detection Service (M4) doesn't exist yet -- always zero for now,
        # matching the frontend's shape exactly so no component changes are needed.
        detections=DetectionCounts(persons=0, vehicles=0),
        # Alert field is populated by the Event/Alert Service (M6); always
        # null until then.
        alert=None,
        type=camera.type,  # type: ignore[arg-type]
        thermal_source_url=camera.thermal_source_url,
    )


def _to_detail(camera: Camera) -> CameraDetail:
    base = _to_read(camera)
    return CameraDetail(
        **base.model_dump(by_alias=False),
        source_url=camera.source_url,
        connection="Disconnected" if camera.status == "offline" else "Stable",
        calibration=Calibration(**camera.calibration) if camera.calibration else None,
    )


class CameraService:
    def __init__(
        self,
        camera_repo: CameraRepository,
        sector_repo: SectorRepository,
        redis_client: Redis | None = None,
        camera_health_repo: CameraHealthRepository | None = None,
    ) -> None:
        self._cameras = camera_repo
        self._sectors = sector_repo
        self._redis = redis_client
        self._camera_health = camera_health_repo

    async def list_cameras(
        self,
        *,
        status: str | None,
        sector: str | None,
        search: str | None,
        page: int,
        page_size: int,
    ) -> CameraListResponse:
        rows, total = await self._cameras.list_paginated(
            status=status, sector=sector, search=search, page=page, page_size=page_size
        )
        return CameraListResponse(
            items=[_to_read(row) for row in rows], total=total, page=page, page_size=page_size
        )

    async def get_camera(self, external_id: str) -> CameraDetail:
        camera = await self._cameras.get_by_external_id(external_id)
        if camera is None:
            raise NotFoundError(f"No camera with id {external_id}")
        return _to_detail(camera)

    async def create_camera(self, data: CameraCreate) -> CameraDetail:
        external_id = data.external_id or _generate_external_id(data.type)
        if await self._cameras.exists_external_id(external_id):
            raise ConflictError(f"Camera id '{external_id}' already exists")

        sector = await self._sectors.get_or_create(data.sector) if data.sector else None

        if data.type == "file" and data.source_url is None:
            # File-type cameras are typically created via POST /cameras then
            # POST /cameras/{id}/upload; source_url is filled in by that step.
            pass

        # M11 revision: a 'dual' camera is one logical row backing two
        # simultaneous capture workers (RGB + thermal). Originally required
        # both URLs up front (matching the design doc's real-camera-stream
        # assumption); relaxed to "both or neither" so a dual camera can
        # also be created empty and filled in via two separate
        # POST /cameras/{id}/upload calls (?slot=rgb / ?slot=thermal),
        # matching 'file's own upload-after-create precedent -- this
        # project's whole test/demo workflow has no real camera hardware.
        # A *partial* pair (one URL set, the other not) is still rejected:
        # there's no valid in-between state for a camera that needs both
        # streams to function.
        if data.type == "dual" and (data.source_url is None) != (data.thermal_source_url is None):
            raise ApiError(
                status_code=422,
                title="Invalid camera configuration",
                detail="type='dual' requires both source_url and thermal_source_url, or neither "
                "(upload them separately after creation)",
            )

        camera = Camera(
            external_id=external_id,
            name=data.name,
            location=data.location,
            sector_id=sector.id if sector else None,
            sector=sector,
            type=data.type,
            source_url=data.source_url,
            thermal_source_url=data.thermal_source_url,
            status="offline",  # ingestion (M3) flips this once it connects
            fps=0,
        )
        camera = await self._cameras.create(camera)
        return _to_detail(camera)

    async def update_camera(self, external_id: str, data: CameraUpdate) -> CameraDetail:
        camera = await self._cameras.get_by_external_id(external_id)
        if camera is None:
            raise NotFoundError(f"No camera with id {external_id}")

        if data.name is not None:
            camera.name = data.name
        if data.location is not None:
            camera.location = data.location
        if data.source_url is not None:
            camera.source_url = data.source_url
        if data.thermal_source_url is not None:
            camera.thermal_source_url = data.thermal_source_url
        if data.sector is not None:
            sector = await self._sectors.get_or_create(data.sector)
            camera.sector_id = sector.id
            camera.sector = sector
        if data.calibration is not None:
            camera.calibration = data.calibration.model_dump()

        camera = await self._cameras.update(camera)
        return _to_detail(camera)

    async def delete_camera(self, external_id: str) -> None:
        camera = await self._cameras.get_by_external_id(external_id)
        if camera is None:
            raise NotFoundError(f"No camera with id {external_id}")
        await self._cameras.delete(camera)

    async def set_uploaded_source(
        self, external_id: str, stored_path: str, *, slot: str = "rgb"
    ) -> CameraDetail:
        """Called after a video upload completes; wires the file as this
        camera's source (Stream Ingestion Service, M3, will read from it).

        M11: `slot` defaults to "rgb" (source_url) for the original
        'file'-type flow, unchanged. 'thermal'/'dual' cameras also accept
        uploads now (see ingestion-service's `capture/factory.py` M11
        revision docstring for why -- no real thermal hardware exists, so
        testing needs an uploaded, looping file, not a live stream URL);
        `slot="thermal"` on a 'dual' camera fills thermal_source_url
        instead."""
        camera = await self._cameras.get_by_external_id(external_id)
        if camera is None:
            raise NotFoundError(f"No camera with id {external_id}")
        if camera.type not in ("file", "thermal", "dual"):
            raise ConflictError(f"Camera '{external_id}' does not accept file uploads")
        if slot == "thermal":
            if camera.type != "dual":
                raise ConflictError(f"Camera '{external_id}' has no thermal slot (type='{camera.type}')")
            camera.thermal_source_url = stored_path
        else:
            camera.source_url = stored_path
        camera = await self._cameras.update(camera)
        return _to_detail(camera)

    async def status_summary(self) -> CameraStatusSummary:
        counts = await self._cameras.status_counts()
        return CameraStatusSummary(**counts)

    async def list_internal_configs(self) -> list[Camera]:
        """Used by the Stream Ingestion Service to discover which cameras to
        open and how (SAS §5.1). Returns raw ORM rows -- the internal schema
        maps them, keeping the public `CameraRead` shape unaware of this."""
        return await self._cameras.list_all()

    async def update_status(self, external_id: str, *, status: str, fps: int | None) -> None:
        camera = await self._cameras.get_by_external_id(external_id)
        if camera is None:
            raise NotFoundError(f"No camera with id {external_id}")
        status_changed = camera.status != status
        camera.status = status
        if fps is not None:
            camera.fps = fps
        camera.last_active_at = dt.datetime.now(dt.UTC)
        await self._cameras.update(camera)

        # Every heartbeat, not just transitions -- this is the time-series
        # the Analytics Service (M9) computes per-camera uptime % from
        # (`camera.camera_health`, scaffolded since M2, unpopulated until now).
        if self._camera_health is not None:
            await self._camera_health.record(camera_id=camera.id, status=status, fps=fps)

        # Only on an actual transition, not every heartbeat ping (SAS §5.1
        # step 5 / API Spec §8) -- this is what the Event/Alert Service's
        # camera-offline rule (M6) and, later, the Realtime Gateway (M8)
        # subscribe to.
        if status_changed and self._redis is not None:
            await publish_event(
                self._redis, "camera.status_changed", {"cameraId": external_id, "status": status}
            )
