"""Camera discovery via Camera Management Service's internal API -- never a
direct cross-schema DB read (IG §6). Same minimal shape as fire-smoke-
service's own CameraClient (M19): this service only needs the id list to
know which cameras to spawn `FrameConsumer`s for.
"""

from __future__ import annotations

import httpx

from ibvap_common.logging import correlated_headers

from app.core.config import Settings


class CameraClient:
    def __init__(self, http_client: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http_client
        self._settings = settings

    async def list_camera_ids(self) -> list[str]:
        response = await self._http.get(
            f"{self._settings.camera_service_url}/internal/cameras",
            headers={"X-Internal-Token": self._settings.internal_service_token, **correlated_headers()},
            timeout=10.0,
        )
        response.raise_for_status()
        return [item["id"] for item in response.json()]
