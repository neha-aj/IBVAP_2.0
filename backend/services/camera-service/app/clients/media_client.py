"""Phase 2 M23: proxies a camera source-video upload to Media Service
instead of writing it via this service's own storage backend (the
documented Phase 1 M7 gap -- see `POST /internal/media/sources`'s own
docstring on the Media Service side for the full rationale)."""

from __future__ import annotations

import httpx

from ibvap_common.errors import ApiError
from ibvap_common.logging import correlated_headers

from app.core.config import Settings


class MediaClient:
    def __init__(self, http_client: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http_client
        self._settings = settings

    async def upload_source(self, *, camera_id: str, filename: str, data: bytes) -> str:
        """Returns the stored file's raw filesystem path (not a URL --
        Ingestion Service reads this straight off disk). Raises `ApiError`
        on failure -- unlike snapshot/recording capture, a failed upload
        here has no "best effort, carry on" fallback: the whole point of
        this request was to store the file, so the caller must see the
        failure, not silently end up with a camera pointed at nothing."""
        try:
            response = await self._http.post(
                f"{self._settings.media_service_url}/internal/media/sources",
                params={"camera_id": camera_id},
                files={"file": (filename, data, "application/octet-stream")},
                headers={"X-Internal-Token": self._settings.internal_service_token, **correlated_headers()},
                timeout=self._settings.media_upload_timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ApiError(status_code=502, title="Media Service unavailable", detail=str(exc)) from exc
        return response.json()["path"]
