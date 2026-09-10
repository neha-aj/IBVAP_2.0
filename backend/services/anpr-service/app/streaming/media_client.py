"""Stores a plate crop via Media Storage Service's existing internal
contract -- same pattern as event-alert-service's snapshot_client, no new
storage service (doc08 §7: every new service reuses this one)."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from ibvap_common.logging import correlated_headers, get_logger

from app.core.config import Settings

logger = get_logger(__name__)


@dataclass(frozen=True)
class StoredSnapshot:
    id: str
    url: str


class MediaClient:
    def __init__(self, http_client: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http_client
        self._settings = settings

    async def store_plate_crop(self, *, camera_id: str, jpeg_bytes: bytes) -> StoredSnapshot | None:
        try:
            response = await self._http.post(
                f"{self._settings.media_service_url}/media/snapshots",
                params={"camera_id": camera_id},
                files={"file": ("plate.jpg", jpeg_bytes, "image/jpeg")},
                headers={"X-Internal-Token": self._settings.internal_service_token, **correlated_headers()},
                timeout=5.0,
            )
            response.raise_for_status()
            payload = response.json()
            return StoredSnapshot(id=payload["id"], url=payload["url"])
        except httpx.HTTPError as exc:
            logger.info("plate_crop_store_skipped", camera_id=camera_id, error=str(exc))
            return None
