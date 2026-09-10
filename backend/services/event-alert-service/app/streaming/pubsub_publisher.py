"""Turns a fired rule (`RuleEngine.EventDraft`) into persisted `events`/
`alerts` rows and publishes `event.new`/`alert.new` to Redis Pub/Sub
(SAS §5.4 steps 3 and 5; API Spec §8 payload shapes). Also used by the
alerts API for `alert.updated` on a status transition.
"""

from __future__ import annotations

import asyncio

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ibvap_common.logging import get_logger
from ibvap_common.redis_pubsub import publish_event

from app.core.config import Settings
from app.models.alert import Alert
from app.models.event import Event
from app.repositories.alert_repo import AlertRepository
from app.repositories.event_repo import EventRepository
from app.rules.engine import EventDraft
from app.schemas.alert import to_alert_read
from app.schemas.event import to_event_read
from app.streaming.camera_client import CameraClient
from app.streaming.recording_client import RecordingClient
from app.streaming.snapshot_client import SnapshotClient

logger = get_logger(__name__)

# Ordering for `Settings.alert_min_severity` -- higher rank means "more
# severe", so a draft only clears the bar when its rank is >= the
# configured floor's rank.
_SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


class PubSubPublisher:
    def __init__(
        self,
        redis_client: redis.Redis,
        camera_client: CameraClient,
        snapshot_client: SnapshotClient,
        recording_client: RecordingClient,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings | None = None,
    ) -> None:
        self._redis = redis_client
        self._camera_client = camera_client
        self._snapshot_client = snapshot_client
        self._recording_client = recording_client
        self._session_factory = session_factory
        self._settings = settings
        # Optional (defaults to "medium", matching Settings.alert_min_severity's
        # own default) so existing tests/callers that only care about
        # persistence, not the alert threshold, don't need to construct a
        # full Settings (whose other fields have no defaults) just to get one.
        self._alert_min_rank = _SEVERITY_RANK.get(settings.alert_min_severity, 1) if settings else 1
        # Phase 2 M23: holds references to in-flight background recording
        # captures so asyncio doesn't garbage-collect a task nothing else
        # is awaiting -- each entry discards itself via `add_done_callback`.
        self._background_tasks: set[asyncio.Task] = set()

    async def persist_and_publish(self, session: AsyncSession, draft: EventDraft) -> None:
        camera_info = await self._camera_client.get_camera_info(draft.camera_id)
        event_repo = EventRepository(session)

        event = await event_repo.create(
            Event(
                camera_id=draft.camera_id,
                camera_name=camera_info.name,
                event_type=draft.event_type,
                object_type=draft.object_type,
                severity=draft.severity,
                location=camera_info.location,
                status="active",
                description=draft.description,
                requires_review=draft.requires_review,
                direction=draft.direction,
            )
        )

        # Best-effort (SAS §5.4 step 4, §11): a failed/skipped capture must
        # never block the event itself, which is already persisted above.
        captured = await self._snapshot_client.capture(camera_id=draft.camera_id, event_id=str(event.id))
        if captured is not None:
            event = await event_repo.set_snapshot(event, snapshot_id=captured.id, snapshot_url=captured.url)

        await publish_event(self._redis, "event.new", to_event_read(event).model_dump(mode="json", by_alias=True))

        alert: Alert | None = None
        meets_alert_threshold = _SEVERITY_RANK.get(draft.severity, 0) >= self._alert_min_rank
        if draft.requires_review and meets_alert_threshold:
            alert = await AlertRepository(session).create(
                Alert(
                    event_id=event.id,
                    camera_id=draft.camera_id,
                    camera_name=camera_info.name,
                    type=draft.event_type,
                    object_type=draft.object_type,
                    severity=draft.severity,
                    location=camera_info.location,
                    status="active",
                    description=draft.description,
                )
            )
            await publish_event(
                self._redis, "alert.new", to_alert_read(alert, self._settings).model_dump(mode="json", by_alias=True)
            )

        # Phase 2 M23: critical-severity events only (doc09/doc08's own
        # "critical-severity recording trigger" concept) -- a multi-second
        # post-roll capture must never delay this method returning (see
        # recording_client.py's own docstring), so it's a tracked
        # fire-and-forget task, not awaited here.
        if draft.severity == "critical":
            task = asyncio.create_task(
                self._capture_recording(event_id=str(event.id), alert_id=str(alert.id) if alert else None,
                                         camera_id=draft.camera_id),
                name=f"recording-capture-{event.id}",
            )
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

    async def _capture_recording(self, *, event_id: str, alert_id: str | None, camera_id: str) -> None:
        captured = await self._recording_client.capture_clip(camera_id=camera_id, event_id=event_id)
        if captured is None:
            return
        try:
            async with self._session_factory() as session:
                event = await EventRepository(session).get_by_id(event_id)
                if event is not None:
                    await EventRepository(session).set_recording(
                        event, recording_id=captured.id, recording_url=captured.url
                    )
                if alert_id is not None:
                    alert_repo = AlertRepository(session)
                    alert = await alert_repo.get_by_id(alert_id)
                    if alert is not None:
                        alert = await alert_repo.set_recording(
                            alert, recording_id=captured.id, recording_url=captured.url
                        )
                        await self.publish_alert_updated(alert)
        except Exception as exc:  # noqa: BLE001
            # Best-effort (SAS §11): the clip is captured and stored either
            # way; a failure here only means the event/alert row's own
            # recording_url stays unset, not that anything upstream broke.
            logger.warning("recording_attach_failed", event_id=event_id, error=str(exc))

    async def publish_alert_updated(self, alert: Alert) -> None:
        await publish_event(
            self._redis, "alert.updated", to_alert_read(alert, self._settings).model_dump(mode="json", by_alias=True)
        )
