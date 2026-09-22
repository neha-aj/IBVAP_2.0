"""M25 anomaly detection: flags an unusually large burst of evidence
downloads/verifies by the same actor in a short window, and reports it
through event-alert-service's existing internal event contract (doc08 §4)
-- so it shows up as a normal Alert, the same "no new notification system"
pattern every other Category B AI service already uses.

This is a heuristic, not a real anomaly-detection model: a fixed
count-in-window threshold, the same honest-proxy class the codebase
already uses elsewhere (e.g. fire-smoke-service's color heuristics). It
flags "more activity than usual for one identity", not "this access was
malicious" -- a real investigator reviewing evidence quickly is expected
to trip this occasionally, hence `requiresReview: true` rather than
anything more drastic.
"""

from __future__ import annotations

import datetime as dt

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ibvap_common.logging import correlated_headers, get_logger

from app.core.config import Settings
from app.models.audit_log import AuditLogEntry

logger = get_logger(__name__)

_TRACKED_ACTIONS = ("verify", "download")


async def check_and_report(session: AsyncSession, *, actor: str | None, camera_id: str, settings: Settings) -> None:
    if actor is None:
        return  # nothing to correlate an unattributed access against

    since = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=settings.anomaly_window_seconds)
    result = await session.execute(
        select(func.count())
        .select_from(AuditLogEntry)
        .where(
            AuditLogEntry.actor == actor,
            AuditLogEntry.action.in_(_TRACKED_ACTIONS),
            AuditLogEntry.created_at >= since,
        )
    )
    count = result.scalar_one()
    # Fire exactly once per breach (the call that crosses the line), not on
    # every subsequent access while still over threshold -- a plain `>=`
    # would re-alert on every single request past the first.
    if count != settings.anomaly_burst_threshold:
        return

    description = (
        f"{actor} downloaded or verified evidence {count} times in the last "
        f"{settings.anomaly_window_seconds} seconds -- more than usual, worth a look."
    )
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.post(
                f"{settings.event_alert_service_url}/internal/events",
                json={
                    "sourceService": "media-service",
                    "eventType": "Unusual Evidence Access",
                    "cameraId": camera_id,
                    "objectType": None,
                    "severity": "medium",
                    "requiresReview": True,
                    "description": description,
                },
                headers={"X-Internal-Token": settings.internal_service_token, **correlated_headers()},
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        # Best-effort, same reasoning as every other cross-service event
        # report in this codebase (SAS §11) -- a failed alert must never
        # block the access it's reporting on.
        logger.warning("anomaly_report_failed", actor=actor, error=str(exc))
