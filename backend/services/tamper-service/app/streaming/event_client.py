"""Reports a camera tamper detection to Event/Alert Service's shared
internal event contract (Phase 2 doc08 §4) -- same pattern as ANPR's and
Fire/Smoke's own EventClient. doc09 §2.5: severity is always `critical`
and `requiresReview` is always true -- an operator must always confirm
whether a flagged camera was actually tampered with."""

from __future__ import annotations

import httpx

from ibvap_common.logging import correlated_headers, get_logger

from app.core.config import Settings

logger = get_logger(__name__)

_CATEGORY_DESCRIPTIONS = {
    "covered": "Camera appears covered or blacked out (sudden full-frame color shift)",
    "defocused": "Camera appears covered or defocused (loss of image detail)",
    "redirected": "Camera view appears to have changed (possible redirection)",
}


class EventClient:
    def __init__(self, http_client: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http_client
        self._settings = settings

    async def report_tamper(self, *, camera_id: str, category: str) -> None:
        description = _CATEGORY_DESCRIPTIONS.get(category, "Camera tamper detected") + \
            " -- confirm visually before acting"
        try:
            response = await self._http.post(
                f"{self._settings.event_alert_service_url}/internal/events",
                json={
                    "sourceService": "tamper-service",
                    "eventType": "Camera Tamper",
                    "cameraId": camera_id,
                    "objectType": None,
                    "severity": "critical",
                    "requiresReview": True,
                    "description": description,
                },
                headers={"X-Internal-Token": self._settings.internal_service_token, **correlated_headers()},
                timeout=5.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            # Best-effort, same reasoning as every other service's event
            # reporting (SAS §11) -- there's no local persistence here to
            # fall back on (this service has no DB).
            logger.warning("tamper_event_report_failed", camera_id=camera_id, error=str(exc))
