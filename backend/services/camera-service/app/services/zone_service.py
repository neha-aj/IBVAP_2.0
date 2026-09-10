import uuid

from ibvap_common.errors import NotFoundError

from app.models.zone import Zone
from app.repositories.camera_repo import CameraRepository
from app.repositories.zone_repo import ZoneRepository
from app.schemas.zone import ZoneCreate, ZoneRead, ZoneUpdate


def _to_read(zone: Zone) -> ZoneRead:
    return ZoneRead(
        id=str(zone.id), name=zone.name, polygon=zone.polygon, zone_type=zone.zone_type,
        density_threshold=float(zone.density_threshold) if zone.density_threshold is not None else None,
        requires_ppe=zone.requires_ppe,
    )


class ZoneService:
    """M12: the public, writable counterpart to the internal-only zone read
    path the rule engine has used since M6 (app/api/internal.py::list_zones).
    Every method resolves the external_id (e.g. "FILE-C5F172A4") to the
    internal camera row first, since `Zone.camera_id` FKs the internal UUID
    PK, not the external_id string used everywhere else on the public API."""

    def __init__(self, zone_repo: ZoneRepository, camera_repo: CameraRepository) -> None:
        self._zones = zone_repo
        self._cameras = camera_repo

    async def _get_camera_or_404(self, external_id: str):
        camera = await self._cameras.get_by_external_id(external_id)
        if camera is None:
            raise NotFoundError(f"No camera with id {external_id}")
        return camera

    async def list_zones(self, external_id: str) -> list[ZoneRead]:
        camera = await self._get_camera_or_404(external_id)
        zones = await self._zones.list_by_camera_id(camera.id)
        return [_to_read(z) for z in zones]

    async def create_zone(self, external_id: str, data: ZoneCreate) -> ZoneRead:
        camera = await self._get_camera_or_404(external_id)
        zone = await self._zones.create(
            Zone(
                # Assigned here rather than left to the column's `default=
                # uuid.uuid4` (which only fires on an actual DB flush) so
                # the id is a real, distinct value the moment this method
                # returns -- callers need it immediately (the response
                # body), not after a round-trip that hasn't happened yet.
                id=uuid.uuid4(),
                camera_id=camera.id,
                name=data.name,
                polygon=[p.model_dump() for p in data.polygon],
                zone_type=data.zone_type,
                density_threshold=data.density_threshold,
                requires_ppe=data.requires_ppe,
            )
        )
        return _to_read(zone)

    async def update_zone(self, external_id: str, zone_id: uuid.UUID, data: ZoneUpdate) -> ZoneRead:
        camera = await self._get_camera_or_404(external_id)
        zone = await self._zones.get_by_id(camera.id, zone_id)
        if zone is None:
            raise NotFoundError(f"No zone with id {zone_id} on camera {external_id}")
        polygon = [p.model_dump() for p in data.polygon] if data.polygon is not None else None
        zone = await self._zones.update(
            zone, name=data.name, polygon=polygon, zone_type=data.zone_type,
            density_threshold=data.density_threshold, requires_ppe=data.requires_ppe,
        )
        return _to_read(zone)

    async def delete_zone(self, external_id: str, zone_id: uuid.UUID) -> None:
        camera = await self._get_camera_or_404(external_id)
        zone = await self._zones.get_by_id(camera.id, zone_id)
        if zone is None:
            raise NotFoundError(f"No zone with id {zone_id} on camera {external_id}")
        await self._zones.delete(zone)
