"""Publishes this service's outputs (SAS §5.3 steps 1-2):

- overwrites the `cam:{id}:current_detections` cache key (the same one
  Detection Service, M4, writes) with track-enriched detections, so
  `GET /cameras/{id}/detections/current` and the live overlay now carry a
  stable `trackId` instead of always `null`. Detection Service keeps writing
  its own (trackId=null) version too -- if this service falls behind or
  crashes, the overlay still degrades gracefully to M4's behavior rather
  than going stale/empty (SAS §11).
- appends lifecycle events to `cam:{id}:tracks`.
- publishes `detection.new` to Redis Pub/Sub (API Spec §8) -- this is the
  final, track-enriched detections list, so it doubles as the WebSocket
  push for both M4's raw detections and M5's trackId enrichment; nothing
  published this before the Realtime Gateway (M8) existed to consume it.
"""

from __future__ import annotations

import json

import redis.asyncio as redis

from ibvap_common.redis_pubsub import publish_event
from ibvap_common.redis_streams import xadd_capped

from app.schemas.detection import Detection
from app.schemas.track import TrackEvent


class TrackPublisher:
    def __init__(
        self, redis_client: redis.Redis, *, tracks_stream_maxlen: int, current_detections_ttl_seconds: int
    ) -> None:
        self._redis = redis_client
        self._tracks_stream_maxlen = tracks_stream_maxlen
        self._current_detections_ttl_seconds = current_detections_ttl_seconds

    async def publish(
        self, camera_id: str, *, tracked_detections: list[Detection], events: list[TrackEvent]
    ) -> None:
        current_key = f"cam:{camera_id}:current_detections"
        detection_dicts = [d.model_dump() for d in tracked_detections]
        await self._redis.set(current_key, json.dumps(detection_dicts), ex=self._current_detections_ttl_seconds)

        # Only publish when there's something to show -- an empty batch
        # every idle frame would be pure noise for a connected WS client.
        if detection_dicts:
            await publish_event(
                self._redis, "detection.new", {"cameraId": camera_id, "detections": detection_dicts}
            )

        tracks_stream_key = f"cam:{camera_id}:tracks"
        for event in events:
            await xadd_capped(
                self._redis,
                tracks_stream_key,
                {"cameraId": camera_id, "event": json.dumps(event.model_dump(by_alias=True))},
                maxlen=self._tracks_stream_maxlen,
            )
