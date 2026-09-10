"""Thin helpers around redis-py's async Pub/Sub for the small, fixed set of
global event channels the SAS names directly by their WebSocket event names
(`camera.status_changed`, `event.new`, `alert.new`, `alert.updated` --
API Spec §8): unlike the per-camera Redis Streams (`cam:{id}:frames`,
`cam:{id}:detections`, `cam:{id}:tracks`), these are cross-camera broadcast
channels, so Pub/Sub (fire-and-forget, no history/replay) fits better than
a Stream -- the Realtime Gateway (M8) is the eventual final subscriber, but
the Event/Alert Service (M6) is the first consumer that needs one.
"""

from __future__ import annotations

import json
from typing import Any

import redis.asyncio as redis


async def publish_event(client: redis.Redis, channel: str, payload: dict[str, Any]) -> None:
    await client.publish(channel, json.dumps(payload))


async def subscribe(client: redis.Redis, *channels: str) -> redis.client.PubSub:
    pubsub = client.pubsub()
    await pubsub.subscribe(*channels)
    return pubsub
