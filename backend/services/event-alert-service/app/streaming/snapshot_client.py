"""Captures a snapshot at event-creation time (SAS §5.4 step 4, §5.5):
pulls the camera's current frame from Ingestion Service and hands it to
Media Storage Service. Best-effort -- a failure here (camera not currently
streaming, either service briefly down) must never block the event/alert
itself from being persisted (SAS §11 graceful degradation), so this returns
`None` on any failure rather than raising.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from ibvap_common.logging import correlated_headers, get_logger

from app.core.config import Settings

logger = get_logger(__name__)


@dataclass(frozen=True)
class CapturedSnapshot:
    id: str
    url: str


class SnapshotClient:
    def __init__(self, http_client: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http_client
        self._settings = settings

    async def capture(self, *, camera_id: str, event_id: str) -> CapturedSnapshot | None:
        """Returns the stored snapshot's id/URL, or None if capture failed
        for any reason."""
        try:
            frame_response = await self._http.get(
                f"{self._settings.ingestion_service_url}/internal/cameras/{camera_id}/snapshot",
                headers={"X-Internal-Token": self._settings.internal_service_token, **correlated_headers()},
                timeout=self._settings.snapshot_capture_timeout_seconds,
            )
            frame_response.raise_for_status()

            upload_response = await self._http.post(
                f"{self._settings.media_service_url}/media/snapshots",
                params={"camera_id": camera_id, "event_id": event_id},
                files={"file": ("snapshot.jpg", frame_response.content, "image/jpeg")},
                headers={"X-Internal-Token": self._settings.internal_service_token, **correlated_headers()},
                timeout=self._settings.snapshot_capture_timeout_seconds,
            )
            upload_response.raise_for_status()
            payload = upload_response.json()
            return CapturedSnapshot(id=payload["id"], url=payload["url"])
        except httpx.HTTPError as exc:
            logger.info("snapshot_capture_skipped", camera_id=camera_id, error=str(exc))
            return None
