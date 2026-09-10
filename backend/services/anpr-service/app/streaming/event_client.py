"""Reports a plate read to Event/Alert Service's shared internal event
contract (Phase 2 doc08 §4) -- this is what actually makes a plate read
show up as a normal event/alert row, riding the existing event.new/
alert.new -> WebSocket -> frontend path with zero frontend changes."""

from __future__ import annotations

import httpx

from ibvap_common.logging import correlated_headers, get_logger

from app.core.config import Settings

logger = get_logger(__name__)


class EventClient:
    def __init__(self, http_client: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http_client
        self._settings = settings

    async def report_plate_read(
        self, *, camera_id: str, plate_text: str, confidence: float, watchlist_match: bool,
    ) -> None:
        severity = self._settings.watchlist_severity if watchlist_match else self._settings.default_severity
        description = (
            f"Watchlisted plate '{plate_text}' detected ({confidence:.0f}% confidence)"
            if watchlist_match
            else f"Plate '{plate_text}' read ({confidence:.0f}% confidence)"
        )
        try:
            response = await self._http.post(
                f"{self._settings.event_alert_service_url}/internal/events",
                json={
                    "sourceService": "anpr-service",
                    "eventType": "Plate Read",
                    "cameraId": camera_id,
                    "objectType": "vehicle",
                    "severity": severity,
                    "requiresReview": watchlist_match,  # a routine read is informational; a watchlist hit isn't
                    "description": description,
                },
                headers={"X-Internal-Token": self._settings.internal_service_token, **correlated_headers()},
                timeout=5.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            # Best-effort, same reasoning as snapshot capture elsewhere (SAS
            # §11): the plate read is already persisted in this service's
            # own DB regardless of whether the event/alert side-channel
            # succeeds.
            logger.info("plate_read_event_report_failed", camera_id=camera_id, error=str(exc))
