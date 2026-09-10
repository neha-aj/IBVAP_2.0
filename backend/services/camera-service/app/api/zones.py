"""Zone/Line Polygon Editor (Phase 2 M12) -- the confirmed gap doc14 calls
out: `camera.zones` has existed since Phase 1 M2, but was never exposed via
a public API (only the internal `/internal/cameras/{id}/zones` read path
the rule engine uses, app/api/internal.py). This is that public, writable
surface, plus the new `zone_lines` table for line-crossing/wrong-way rules
(M13/M14).
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ibvap_common.auth import TokenPayload, require_role

from app.db.session import get_db
from app.repositories.camera_repo import CameraRepository
from app.repositories.zone_line_repo import ZoneLineRepository
from app.repositories.zone_repo import ZoneRepository
from app.schemas.zone import ZoneCreate, ZoneRead, ZoneUpdate
from app.schemas.zone_line import ZoneLineCreate, ZoneLineRead, ZoneLineUpdate
from app.services.zone_line_service import ZoneLineService
from app.services.zone_service import ZoneService

router = APIRouter(prefix="/api/v1/cameras/{camera_id}", tags=["zones"])


def get_zone_service(session: AsyncSession = Depends(get_db)) -> ZoneService:
    return ZoneService(ZoneRepository(session), CameraRepository(session))


def get_zone_line_service(session: AsyncSession = Depends(get_db)) -> ZoneLineService:
    return ZoneLineService(ZoneLineRepository(session), CameraRepository(session))


# --- Zones (polygons) ---


@router.get("/zones", response_model=list[ZoneRead])
async def list_zones(
    camera_id: str,
    service: ZoneService = Depends(get_zone_service),
    _user: TokenPayload = Depends(require_role("viewer")),
) -> list[ZoneRead]:
    return await service.list_zones(camera_id)


@router.post("/zones", response_model=ZoneRead, status_code=201)
async def create_zone(
    camera_id: str,
    payload: ZoneCreate,
    service: ZoneService = Depends(get_zone_service),
    _user: TokenPayload = Depends(require_role("admin")),
) -> ZoneRead:
    return await service.create_zone(camera_id, payload)


@router.put("/zones/{zone_id}", response_model=ZoneRead)
async def update_zone(
    camera_id: str,
    zone_id: uuid.UUID,
    payload: ZoneUpdate,
    service: ZoneService = Depends(get_zone_service),
    _user: TokenPayload = Depends(require_role("admin")),
) -> ZoneRead:
    return await service.update_zone(camera_id, zone_id, payload)


@router.delete("/zones/{zone_id}", status_code=204)
async def delete_zone(
    camera_id: str,
    zone_id: uuid.UUID,
    service: ZoneService = Depends(get_zone_service),
    _user: TokenPayload = Depends(require_role("admin")),
) -> None:
    await service.delete_zone(camera_id, zone_id)


# --- Zone lines (line-crossing / wrong-way) ---


@router.get("/zone-lines", response_model=list[ZoneLineRead])
async def list_zone_lines(
    camera_id: str,
    service: ZoneLineService = Depends(get_zone_line_service),
    _user: TokenPayload = Depends(require_role("viewer")),
) -> list[ZoneLineRead]:
    return await service.list_zone_lines(camera_id)


@router.post("/zone-lines", response_model=ZoneLineRead, status_code=201)
async def create_zone_line(
    camera_id: str,
    payload: ZoneLineCreate,
    service: ZoneLineService = Depends(get_zone_line_service),
    _user: TokenPayload = Depends(require_role("admin")),
) -> ZoneLineRead:
    return await service.create_zone_line(camera_id, payload)


@router.put("/zone-lines/{zone_line_id}", response_model=ZoneLineRead)
async def update_zone_line(
    camera_id: str,
    zone_line_id: uuid.UUID,
    payload: ZoneLineUpdate,
    service: ZoneLineService = Depends(get_zone_line_service),
    _user: TokenPayload = Depends(require_role("admin")),
) -> ZoneLineRead:
    return await service.update_zone_line(camera_id, zone_line_id, payload)


@router.delete("/zone-lines/{zone_line_id}", status_code=204)
async def delete_zone_line(
    camera_id: str,
    zone_line_id: uuid.UUID,
    service: ZoneLineService = Depends(get_zone_line_service),
    _user: TokenPayload = Depends(require_role("admin")),
) -> None:
    await service.delete_zone_line(camera_id, zone_line_id)
