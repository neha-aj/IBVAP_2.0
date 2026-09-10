import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.zone import Zone


class ZoneRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_camera_id(self, camera_id: uuid.UUID) -> list[Zone]:
        result = await self._session.execute(select(Zone).where(Zone.camera_id == camera_id))
        return list(result.scalars().all())

    async def get_by_id(self, camera_id: uuid.UUID, zone_id: uuid.UUID) -> Zone | None:
        result = await self._session.execute(
            select(Zone).where(Zone.id == zone_id, Zone.camera_id == camera_id)
        )
        return result.scalar_one_or_none()

    async def create(self, zone: Zone) -> Zone:
        self._session.add(zone)
        await self._session.commit()
        await self._session.refresh(zone)
        return zone

    async def update(
        self, zone: Zone, *, name: str | None, polygon: list | None, zone_type: str | None,
        density_threshold: float | None = None, requires_ppe: bool | None = None,
    ) -> Zone:
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
        await self._session.commit()
        await self._session.refresh(zone)
        return zone

    async def delete(self, zone: Zone) -> None:
        await self._session.delete(zone)
        await self._session.commit()
