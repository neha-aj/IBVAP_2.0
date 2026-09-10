"""Camera discovery + current-frame fetch via Camera/Ingestion Services'
internal (M2M-token) APIs -- never a direct cross-schema DB read (IG §6).
"""

from __future__ import annotations

import httpx

from ibvap_common.logging import correlated_headers

from app.core.config import Settings
from app.schemas.internal import InternalCameraConfig


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
        return [InternalCameraConfig(**item).id for item in response.json()]

    async def get_current_frame(self, camera_id: str) -> bytes | None:
        """Raw JPEG bytes of this camera's most recent frame (Ingestion
        Service's frame cache), or None if not currently streaming --
        best-effort, same as event-alert-service's own snapshot_client."""
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
