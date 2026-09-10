import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.camera_health import CameraHealth


class CameraHealthRepository:
    """Heartbeat history (DB Spec §2 `camera.camera_health`) -- scaffolded
    since M2 but nothing wrote to it until now; the Analytics Service (M9)
    needs a real time-series to compute per-camera uptime %% from."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self, *, camera_id: uuid.UUID, status: str, fps: int | None, latency_ms: int | None = None
    ) -> None:
        self._session.add(
            CameraHealth(camera_id=camera_id, status=status, fps=fps, latency_ms=latency_ms)
        )
        await self._session.commit()
