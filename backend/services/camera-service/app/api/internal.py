from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from ibvap_common.errors import NotFoundError
from ibvap_common.internal_auth import verify_internal_token

from app.db.session import get_db
from app.redis_client import get_redis_client
from app.repositories.camera_health_repo import CameraHealthRepository
from app.repositories.camera_repo import CameraRepository
from app.repositories.sector_repo import SectorRepository
from app.repositories.zone_line_repo import ZoneLineRepository
from app.repositories.zone_repo import ZoneRepository
from app.schemas.camera import Calibration
from app.schemas.internal import CameraStatusUpdate, InternalCameraConfig
from app.schemas.zone import ZoneRead
from app.schemas.zone_line import ZoneLineRead
from app.services.camera_service import CameraService

router = APIRouter(
    prefix="/internal/cameras",
    tags=["internal"],
    dependencies=[Depends(verify_internal_token)],
)


def get_camera_service(
    session: AsyncSession = Depends(get_db), redis_client: Redis = Depends(get_redis_client)
) -> CameraService:
    return CameraService(
        CameraRepository(session), SectorRepository(session), redis_client, CameraHealthRepository(session)
    )


@router.get("", response_model=list[InternalCameraConfig])
async def list_internal_configs(
    service: CameraService = Depends(get_camera_service),
) -> list[InternalCameraConfig]:
    """Consumed by the Stream Ingestion Service on startup and on a polling
    interval to discover which cameras exist and how to open them."""
    cameras = await service.list_internal_configs()
    return [
        InternalCameraConfig(
            id=c.external_id, name=c.name, location=c.location, type=c.type, source_url=c.source_url,
            thermal_source_url=c.thermal_source_url,
            calibration=Calibration(**c.calibration) if c.calibration else None,
        )
        for c in cameras
    ]


@router.patch("/{camera_id}/status", status_code=204)
async def update_status(
    camera_id: str,
    payload: CameraStatusUpdate,
    service: CameraService = Depends(get_camera_service),
) -> None:
    """Pushed by the Stream Ingestion Service on connect/disconnect/degraded
    FPS (SAS §5.1 heartbeat). Also bumps `lastActiveAt`."""
    await service.update_status(camera_id, status=payload.status, fps=payload.fps)


@router.get("/{camera_id}/zones", response_model=list[ZoneRead])
async def list_zones(
    camera_id: str,
    session: AsyncSession = Depends(get_db),
) -> list[ZoneRead]:
    """Consumed by the Event/Alert Service's zone-crossing/intrusion rules
    (SAS §5.4) -- returns whatever zones (if any) are configured for this
    camera. Empty until zones get a public create/edit API (Phase 2)."""
    camera = await CameraRepository(session).get_by_external_id(camera_id)
    if camera is None:
        raise NotFoundError(f"No camera with id {camera_id}")
    zones = await ZoneRepository(session).list_by_camera_id(camera.id)
    return [
        ZoneRead(
            id=str(z.id), name=z.name, polygon=z.polygon, zone_type=z.zone_type,
            density_threshold=float(z.density_threshold) if z.density_threshold is not None else None,
            requires_ppe=z.requires_ppe,
        )
        for z in zones
    ]


@router.get("/{camera_id}/zone-lines", response_model=list[ZoneLineRead])
async def list_zone_lines(
    camera_id: str,
    session: AsyncSession = Depends(get_db),
) -> list[ZoneLineRead]:
    """Consumed by the Event/Alert Service's Line Crossing/Wrong-Way rules
    (Phase 2 M13/M14) -- same shape as `list_zones` above, for the
    line-segment definitions a polygon can't express."""
    camera = await CameraRepository(session).get_by_external_id(camera_id)
    if camera is None:
        raise NotFoundError(f"No camera with id {camera_id}")
    lines = await ZoneLineRepository(session).list_by_camera_id(camera.id)
    return [
        ZoneLineRead(
            id=str(line.id), name=line.name, point_a=line.point_a, point_b=line.point_b, direction=line.direction,
        )
        for line in lines
    ]
