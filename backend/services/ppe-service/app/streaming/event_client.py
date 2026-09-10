"""Reports a PPE violation to Event/Alert Service's shared internal event
contract (Phase 2 doc08 §4) -- same pattern as every other Category B
service's own EventClient. doc09 §2.8: `metadata: {missingItems: [...]}` is
the spec's literal shape, but `ExternalDetectionEvent` (event-alert-
service's schema) has no structured metadata field -- every other service
using this contract (Direction Analysis, Crowd Density, Zone Exit) already
encodes its extra detail into `description` text instead, so this follows
that same established convention rather than requesting a schema change for
one field."""

from __future__ import annotations

import httpx

from ibvap_common.logging import correlated_headers, get_logger

from app.core.config import Settings

logger = get_logger(__name__)


class EventClient:
    def __init__(self, http_client: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http_client
        self._settings = settings

    async def report_violation(
        self, *, camera_id: str, missing_items: list[str], severity: str,
    ) -> None:
        description = f"PPE Violation -- missing: {', '.join(missing_items)}"
        try:
            response = await self._http.post(
                f"{self._settings.event_alert_service_url}/internal/events",
                json={
                    "sourceService": "ppe-service",
                    "eventType": "PPE Violation",
                    "cameraId": camera_id,
                    "objectType": "person",
                    "severity": severity,
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
            # fall back on (this service has no DB), so a failed report
            # just means this one violation is lost, not retried.
            logger.warning("ppe_event_report_failed", camera_id=camera_id, error=str(exc))
