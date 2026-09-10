"""Camera discovery, current-frame fetch, and configured-zone lookup via
Camera/Ingestion Services' internal (M2M-token) APIs -- never a direct
cross-schema DB read (IG §6). Merges reid-service's `get_current_frame`
pattern with event-alert-service's `get_zones` pattern -- this service is
the first to need both."""

from __future__ import annotations

import time

import httpx

from ibvap_common.logging import correlated_headers

from app.core.config import Settings
from app.schemas.internal import InternalCameraConfig, Zone

_INFO_TTL_SECONDS = 60


class CameraClient:
    def __init__(self, http_client: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http_client
        self._settings = settings
        self._info_cache: dict[str, tuple[float, InternalCameraConfig]] = {}
        self._zones_cache: dict[str, tuple[float, list[Zone]]] = {}

    async def list_camera_ids(self) -> list[str]:
        configs = await self._fetch_all()
        return [c.id for c in configs]

    async def _fetch_all(self) -> list[InternalCameraConfig]:
        response = await self._http.get(
            f"{self._settings.camera_service_url}/internal/cameras",
            headers={"X-Internal-Token": self._settings.internal_service_token, **correlated_headers()},
            timeout=10.0,
        )
        response.raise_for_status()
        now = time.monotonic()
        configs = [InternalCameraConfig(**item) for item in response.json()]
        for config in configs:
            self._info_cache[config.id] = (now, config)
        return configs

    async def get_current_frame(self, camera_id: str) -> bytes | None:
        try:
            response = await self._http.get(
                f"{self._settings.ingestion_service_url}/internal/cameras/{camera_id}/snapshot",
                headers={"X-Internal-Token": self._settings.internal_service_token, **correlated_headers()},
                timeout=5.0,
            )
            response.raise_for_status()
            return response.content
        except httpx.HTTPError:
            return None

    async def get_zones(self, camera_id: str) -> list[Zone]:
        cached = self._zones_cache.get(camera_id)
        if cached is not None and time.monotonic() - cached[0] < self._settings.zones_refresh_interval_seconds:
            return cached[1]

        response = await self._http.get(
            f"{self._settings.camera_service_url}/internal/cameras/{camera_id}/zones",
            headers={"X-Internal-Token": self._settings.internal_service_token, **correlated_headers()},
            timeout=5.0,
        )
        response.raise_for_status()
        zones = [Zone(**item) for item in response.json()]
        self._zones_cache[camera_id] = (time.monotonic(), zones)
        return zones
