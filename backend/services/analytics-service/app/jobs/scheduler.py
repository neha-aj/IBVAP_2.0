from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncEngine

from ibvap_common.logging import get_logger

from app.jobs.refresh_views import refresh_all_views

logger = get_logger(__name__)


class RefreshScheduler:
    def __init__(self, engine: AsyncEngine, *, interval_seconds: int) -> None:
        self._engine = engine
        self._interval_seconds = interval_seconds
        self._task: asyncio.Task | None = None
        self._stopped = False

    async def start(self) -> None:
        self._stopped = False
        # Refresh once immediately so a fresh `docker compose up` doesn't
        # serve empty views for a full interval before the first tick.
        await refresh_all_views(self._engine)
        self._task = asyncio.create_task(self._run(), name="analytics-refresh-scheduler")

    async def stop(self) -> None:
        self._stopped = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        while not self._stopped:
            await asyncio.sleep(self._interval_seconds)
            try:
                await refresh_all_views(self._engine)
                logger.info("materialized_views_refreshed")
            except Exception as exc:
                logger.warning("scheduled_refresh_failed", error=str(exc))
