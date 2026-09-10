"""Phase 2 M23: `GET /cameras/{id}/snapshot`'s backing call -- the public,
JWT-protected counterpart to Ingestion Service's own internal-only
`GET /internal/cameras/{id}/snapshot` (M2M-token gated, meant for other
services, not an end user's browser)."""

from __future__ import annotations

import httpx

from ibvap_common.logging import correlated_headers

from app.core.config import Settings


class IngestionClient:
    def __init__(self, http_client: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http_client
        self._settings = settings

    async def get_snapshot(self, camera_id: str) -> bytes | None:
        """Returns the camera's most recently captured JPEG frame, or None
        if it isn't currently streaming (no cached frame yet) or Ingestion
        Service is unreachable."""
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
