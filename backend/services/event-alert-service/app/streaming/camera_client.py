"""Resolves camera name/location (for denormalizing onto events/alerts) and
configured zones (for the intrusion rule) via Camera Management Service's
API -- never a direct cross-schema DB read (IG §6). Both are cached briefly
in-memory: this gets called on every track event, and neither a camera's
name/location nor its zones change at a rate that needs a fresh call each
time.
"""

from __future__ import annotations

import time

import httpx

from ibvap_common.logging import correlated_headers

from app.core.config import Settings
from app.schemas.internal import CameraInfo, Zone, ZoneLine

_CAMERA_INFO_TTL_SECONDS = 60


class CameraClient:
    def __init__(self, http_client: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http_client
        self._settings = settings
        self._info_cache: dict[str, tuple[float, CameraInfo]] = {}
        self._zones_cache: dict[str, tuple[float, list[Zone]]] = {}
        self._zone_lines_cache: dict[str, tuple[float, list[ZoneLine]]] = {}

    async def get_camera_info(self, camera_id: str) -> CameraInfo:
        """Uses the internal (M2M-token) camera list, not the public JWT-
        protected `GET /cameras/{id}` -- this service only carries the
        shared internal token, same as Ingestion/Detection/Tracking's own
        camera discovery calls."""
        cached = self._info_cache.get(camera_id)
        if cached is not None and time.monotonic() - cached[0] < _CAMERA_INFO_TTL_SECONDS:
            return cached[1]

        response = await self._http.get(
            f"{self._settings.camera_service_url}/internal/cameras",
            headers={"X-Internal-Token": self._settings.internal_service_token, **correlated_headers()},
            timeout=5.0,
        )
        response.raise_for_status()
        now = time.monotonic()
        for item in response.json():
            # CameraInfo(**item) rather than picking fields by hand -- this
            # payload also carries `calibration` (M14 Speed Estimation) now,
            # and letting Pydantic parse the whole thing means a future
            # field addition here doesn't need a matching edit in this loop.
            self._info_cache[item["id"]] = (now, CameraInfo(**item))

        cached = self._info_cache.get(camera_id)
        if cached is None:
            raise ValueError(f"Unknown camera '{camera_id}'")
        return cached[1]

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

    async def get_zone_lines(self, camera_id: str) -> list[ZoneLine]:
        cached = self._zone_lines_cache.get(camera_id)
        if cached is not None and time.monotonic() - cached[0] < self._settings.zones_refresh_interval_seconds:
            return cached[1]

        response = await self._http.get(
            f"{self._settings.camera_service_url}/internal/cameras/{camera_id}/zone-lines",
            headers={"X-Internal-Token": self._settings.internal_service_token, **correlated_headers()},
            timeout=5.0,
        )
        response.raise_for_status()
        lines = [ZoneLine(**item) for item in response.json()]
        self._zone_lines_cache[camera_id] = (time.monotonic(), lines)
        return lines
