"""Camera discovery, name resolution, and current-frame fetch via Camera/
Ingestion Services' internal (M2M-token) APIs -- never a direct cross-schema
DB read (IG §6)."""

from __future__ import annotations

import time

import httpx

from ibvap_common.logging import correlated_headers

from app.core.config import Settings
from app.schemas.internal import InternalCameraConfig

_INFO_TTL_SECONDS = 60


class CameraClient:
    def __init__(self, http_client: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http_client
        self._settings = settings
        self._info_cache: dict[str, tuple[float, InternalCameraConfig]] = {}

    async def list_camera_ids(self) -> list[str]:
        configs = await self._fetch_all()
        return [c.id for c in configs]

    async def get_camera_info(self, camera_id: str) -> InternalCameraConfig | None:
        cached = self._info_cache.get(camera_id)
        if cached is not None and time.monotonic() - cached[0] < _INFO_TTL_SECONDS:
            return cached[1]
        await self._fetch_all()
        cached = self._info_cache.get(camera_id)
        return cached[1] if cached is not None else None

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
