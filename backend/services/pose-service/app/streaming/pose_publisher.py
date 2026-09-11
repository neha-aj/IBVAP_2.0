"""Publishes each sampled frame's posture readings to the Redis Pub/Sub
channel `pose.updated` via `ibvap_common.redis_pubsub.publish_event` --
NOT the `cam:{id}:frames`-style Redis Stream `frame_consumer.py` reads from.
This is deliberately Pub/Sub (fire-and-forget, no history/replay), the same
choice event-alert-service's own `PubSubPublisher` makes for
`event.new`/`alert.new`/`alert.updated`, and for the same reason: this is a
live, ephemeral, cross-consumer broadcast, not something a later reader
should be able to replay -- doubly so here, since a pose reading must NEVER
be persisted anywhere (see `app/core/config.py`), so there is no durable
history to even fall back to.

Realtime Gateway (`services/realtime-gateway/app/streaming/pubsub_bridge.py`)
routes this channel to that camera's own `camera:{id}` WS topic only (added
to `_PER_CAMERA_CHANNELS`), the same per-camera routing `detection.new` and
`camera.status_changed` get -- a posture reading is only relevant to a
client currently viewing that camera, exactly the reasoning that file's own
docstring gives for `detection.new`."""

from __future__ import annotations

import redis.asyncio as redis

from ibvap_common.redis_pubsub import publish_event

from app.schemas.pose import PoseReading

_CHANNEL = "pose.updated"


class PosePublisher:
    def __init__(self, redis_client: redis.Redis) -> None:
        self._redis = redis_client

    async def publish(self, camera_id: str, poses: list[PoseReading]) -> None:
        await publish_event(
            self._redis,
            _CHANNEL,
            {
                "cameraId": camera_id,
                "poses": [p.model_dump(mode="json", by_alias=True) for p in poses],
            },
        )
