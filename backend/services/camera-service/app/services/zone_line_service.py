import uuid

from ibvap_common.errors import NotFoundError

from app.models.zone_line import ZoneLine
from app.repositories.camera_repo import CameraRepository
from app.repositories.zone_line_repo import ZoneLineRepository
from app.schemas.zone_line import ZoneLineCreate, ZoneLineRead, ZoneLineUpdate


def _to_read(line: ZoneLine) -> ZoneLineRead:
    return ZoneLineRead(
        id=str(line.id), name=line.name, point_a=line.point_a, point_b=line.point_b, direction=line.direction
    )


class ZoneLineService:
    """Same shape as ZoneService, for the line-segment definitions Line
    Crossing/Wrong-Way Detection (M13/M14) need instead of a polygon."""

    def __init__(self, zone_line_repo: ZoneLineRepository, camera_repo: CameraRepository) -> None:
        self._lines = zone_line_repo
        self._cameras = camera_repo

    async def _get_camera_or_404(self, external_id: str):
        camera = await self._cameras.get_by_external_id(external_id)
        if camera is None:
            raise NotFoundError(f"No camera with id {external_id}")
        return camera

    async def list_zone_lines(self, external_id: str) -> list[ZoneLineRead]:
        camera = await self._get_camera_or_404(external_id)
        lines = await self._lines.list_by_camera_id(camera.id)
        return [_to_read(line) for line in lines]

    async def create_zone_line(self, external_id: str, data: ZoneLineCreate) -> ZoneLineRead:
        camera = await self._get_camera_or_404(external_id)
        line = await self._lines.create(
            ZoneLine(
                # See ZoneService.create_zone's comment: assigned eagerly
                # rather than relying on the column's flush-time default.
                id=uuid.uuid4(),
                camera_id=camera.id,
                name=data.name,
                point_a=data.point_a.model_dump(),
                point_b=data.point_b.model_dump(),
                direction=data.direction,
            )
        )
        return _to_read(line)

    async def update_zone_line(self, external_id: str, zone_line_id: uuid.UUID, data: ZoneLineUpdate) -> ZoneLineRead:
        camera = await self._get_camera_or_404(external_id)
        line = await self._lines.get_by_id(camera.id, zone_line_id)
        if line is None:
            raise NotFoundError(f"No zone line with id {zone_line_id} on camera {external_id}")
        point_a = data.point_a.model_dump() if data.point_a is not None else None
        point_b = data.point_b.model_dump() if data.point_b is not None else None
        line = await self._lines.update(
            line, name=data.name, point_a=point_a, point_b=point_b, direction=data.direction,
        )
        return _to_read(line)

    async def delete_zone_line(self, external_id: str, zone_line_id: uuid.UUID) -> None:
        camera = await self._get_camera_or_404(external_id)
        line = await self._lines.get_by_id(camera.id, zone_line_id)
        if line is None:
            raise NotFoundError(f"No zone line with id {zone_line_id} on camera {external_id}")
        await self._lines.delete(line)
