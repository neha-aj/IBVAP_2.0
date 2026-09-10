"""Implements the `system.health` WS topic (API Spec §8: `{service, status}`,
"service health change, optional, ops use") -- documented since Phase 1 but
never actually wired to anything, per M24's own audit (no publisher existed
anywhere in the codebase). Polls every monitored service's own `/health`
endpoint (the same one Docker's own healthcheck and Prometheus already use)
on a fixed interval and publishes to Redis Pub/Sub only on an actual status
*change* -- not every poll -- so a healthy, unchanging fleet produces no
WS traffic at all, matching every other channel's "fires on a real event"
contract (SAS §5.4/§8), not a polling firehose."""

from __future__ import annotations

import asyncio

import httpx
import redis.asyncio as redis

from ibvap_common.logging import get_logger
from ibvap_common.redis_pubsub import publish_event

from app.core.config import Settings

logger = get_logger(__name__)

_CHANNEL = "system.health"


class HealthPoller:
    def __init__(self, redis_client: redis.Redis, settings: Settings) -> None:
        self._redis = redis_client
        self._settings = settings
        self._http = httpx.AsyncClient()
        self._last_status: dict[str, str] = {}
        self._task: asyncio.Task | None = None
        self._stop_requested = False

    def start(self) -> None:
        self._stop_requested = False
        self._task = asyncio.create_task(self._run(), name="system-health-poller")

    async def stop(self) -> None:
        self._stop_requested = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._http.aclose()

    def snapshot(self) -> dict[str, str]:
        """Current known status per monitored service, as of the last
        completed poll -- for `GET /api/v1/system/health`'s initial-load
        case (a client connecting to the WS topic only ever sees *future*
        changes, per the module docstring, so this is the only way a
        freshly-opened page can know current state rather than assuming
        "Operational" until told otherwise, which could be wrong if a
        service was already down before the page loaded)."""
        return dict(self._last_status)

    async def _run(self) -> None:
        while not self._stop_requested:
            # `return_exceptions=True` + the per-service timeout in
            # `_check_one` are two independent safety nets around the same
            # failure mode: neither a hang nor an unexpected exception in
            # one service's check may ever stop this loop from reaching
            # `sleep` and trying again -- a poller that can silently freeze
            # is worse than useless, since `snapshot()`/the WS topic would
            # then serve a stale reading forever with no visible sign
            # anything's wrong.
            results = await asyncio.gather(
                *(self._check_one(name) for name in self._settings.monitored_services),
                return_exceptions=True,
            )
            for service_name, result in zip(self._settings.monitored_services, results, strict=True):
                if isinstance(result, Exception):
                    logger.warning("health_check_failed", service=service_name, error=str(result))
            await asyncio.sleep(self._settings.health_poll_interval_seconds)

    async def _check_one(self, service_name: str) -> None:
        try:
            await asyncio.wait_for(
                self._check_one_inner(service_name),
                timeout=self._settings.health_check_overall_timeout_seconds,
            )
        except TimeoutError:
            logger.warning("health_check_timed_out", service=service_name)

    async def _check_one_inner(self, service_name: str) -> None:
        status = await self._probe(service_name)
        if self._last_status.get(service_name) == status:
            return  # no change -- nothing to publish (see module docstring)
        self._last_status[service_name] = status
        await publish_event(self._redis, _CHANNEL, {"service": service_name, "status": status})
        logger.info("system_health_changed", service=service_name, status=status)

    async def _probe(self, service_name: str) -> str:
        try:
            response = await self._http.get(
                f"http://{service_name}:8000/health", timeout=self._settings.health_check_timeout_seconds,
            )
            return "up" if response.status_code == 200 else "down"
        except httpx.HTTPError:
            return "down"
