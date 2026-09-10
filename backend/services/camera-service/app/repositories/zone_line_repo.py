import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.zone_line import ZoneLine


class ZoneLineRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_camera_id(self, camera_id: uuid.UUID) -> list[ZoneLine]:
        result = await self._session.execute(select(ZoneLine).where(ZoneLine.camera_id == camera_id))
        return list(result.scalars().all())

    async def get_by_id(self, camera_id: uuid.UUID, zone_line_id: uuid.UUID) -> ZoneLine | None:
        result = await self._session.execute(
            select(ZoneLine).where(ZoneLine.id == zone_line_id, ZoneLine.camera_id == camera_id)
        )
        return result.scalar_one_or_none()

    async def create(self, zone_line: ZoneLine) -> ZoneLine:
        self._session.add(zone_line)
        await self._session.commit()
        await self._session.refresh(zone_line)
        return zone_line

    async def update(
        self, zone_line: ZoneLine, *, name: str | None, point_a: dict | None, point_b: dict | None,
        direction: str | None,
    ) -> ZoneLine:
        # Matches CameraService.update_camera's convention (app/services/
        # camera_service.py): "if provided, set it" -- explicitly clearing
        # `direction` back to null via update isn't supported, same as
        # every other nullable field in this service.
        if name is not None:
            zone_line.name = name
        if point_a is not None:
            zone_line.point_a = point_a
        if point_b is not None:
            zone_line.point_b = point_b
        if direction is not None:
            zone_line.direction = direction
        await self._session.commit()
        await self._session.refresh(zone_line)
        return zone_line

    async def delete(self, zone_line: ZoneLine) -> None:
        await self._session.delete(zone_line)
        await self._session.commit()
