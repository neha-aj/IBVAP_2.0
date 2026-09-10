from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from ibvap_common.stream_auth import build_resource_url

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.models.alert import Alert

Severity = Literal["critical", "high", "medium", "low"]
AlertStatus = Literal["active", "reviewing", "resolved"]


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class AlertRead(_CamelModel):
    """API Spec §5 `AlertCard` shape exactly:
    `{id,type,severity,cameraId,cameraName,objectType,location,timestamp,status}`,
    plus `description` (added post-M11: copied from the originating Event,
    which already carried one -- see `alerts.description` migration 0004)."""

    id: str
    type: str
    severity: Severity
    camera_id: str
    camera_name: str
    object_type: str | None
    location: str | None
    timestamp: dt.datetime
    status: AlertStatus
    description: str | None
    # Phase 2 M23: null until the background post-roll capture completes
    # (recording_client.py) -- see AlertDetails' own frontend handling for
    # the "not ready yet" empty state.
    recording_url: str | None = None


class AlertDetail(AlertRead):
    event_id: str
    acknowledged_by: str | None
    acknowledged_at: dt.datetime | None
    resolved_at: dt.datetime | None


class AlertStatusUpdate(_CamelModel):
    status: AlertStatus


class AlertListResponse(_CamelModel):
    items: list[AlertRead]
    total: int
    page: int
    page_size: int


def to_alert_read(alert: Alert, settings: Settings | None = None) -> AlertRead:
    """`alert.recording_url` is a denormalized raw file path captured at
    recording-capture time -- see `to_event_detail`'s docstring for why
    that's no longer handed to the frontend as-is (M24 security review
    follow-up): rebuilt here as a short-lived signed URL from the stored
    `recording_id` on every read instead. `settings` is optional (falls
    back to no `recordingUrl`, matching the field's own pre-M23 default)
    for the same reason `PubSubPublisher.__init__` treats it as optional --
    existing callers that only care about persistence shouldn't need to
    construct a full `Settings` just to get one."""
    return AlertRead(
        id=str(alert.id),
        type=alert.type,
        severity=alert.severity,  # type: ignore[arg-type]
        camera_id=alert.camera_id,
        camera_name=alert.camera_name,
        object_type=alert.object_type,
        location=alert.location,
        timestamp=alert.created_at,
        status=alert.status,  # type: ignore[arg-type]
        description=alert.description,
        recording_url=build_resource_url(
            path=f"/media/recordings/{alert.recording_id}/file", resource=str(alert.recording_id), settings=settings
        )
        if alert.recording_id and settings
        else None,
    )


def to_alert_detail(alert: Alert, settings: Settings | None = None) -> AlertDetail:
    base = to_alert_read(alert, settings)
    return AlertDetail(
        **base.model_dump(),
        event_id=str(alert.event_id),
        acknowledged_by=str(alert.acknowledged_by) if alert.acknowledged_by else None,
        acknowledged_at=alert.acknowledged_at,
        resolved_at=alert.resolved_at,
    )
