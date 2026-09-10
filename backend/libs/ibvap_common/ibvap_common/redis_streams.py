"""Thin helpers around redis-py's async client for the pipeline's Redis
Streams transport (SAS §4, §5). The producer side (`xadd_capped`) has been
used since M3 (Stream Ingestion); the consumer-group side below is added in
M4 (Detection Service) and reused by every later pipeline stage (Tracking,
Event/Alert) that reads a Redis Stream.
"""

from __future__ import annotations

from typing import Any

import redis.asyncio as redis

from ibvap_common.settings import CommonSettings

# Redis stream entry IDs are returned as bytes when decode_responses=False.
StreamMessage = tuple[bytes, dict[bytes, bytes]]


def build_redis_client(settings: CommonSettings) -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=False)


async def xadd_capped(
    client: redis.Redis,
    stream_key: str,
    fields: dict[str, Any],
    *,
    maxlen: int = 500,
) -> str:
    """Appends to a stream, trimming approximately to `maxlen` entries so the
    pipeline never grows unbounded if a downstream consumer falls behind
    (SAS §11 backpressure)."""
    return await client.xadd(stream_key, fields, maxlen=maxlen, approximate=True)


async def ensure_consumer_group(
    client: redis.Redis, stream_key: str, group_name: str
) -> None:
    """Creates `group_name` on `stream_key` if it doesn't already exist,
    creating the stream itself if needed (`mkstream=True`) so a consumer can
    start before any producer has published (SAS §5.2/§11 at-least-once
    processing via consumer groups)."""
    try:
        await client.xgroup_create(stream_key, group_name, id="$", mkstream=True)
    except redis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def xread_group(
    client: redis.Redis,
    *,
    group_name: str,
    consumer_name: str,
    stream_key: str,
    count: int = 10,
    block_ms: int = 2000,
) -> list[StreamMessage]:
    """Reads up to `count` new (undelivered) entries for this consumer group,
    blocking up to `block_ms` if none are available yet. Returns a flat list
    of `(message_id, fields)` for the single stream requested."""
    response = await client.xreadgroup(
        group_name, consumer_name, {stream_key: ">"}, count=count, block=block_ms
    )
    if not response:
        return []
    # redis-py shape: [(stream_key, [(message_id, fields), ...])]
    _, messages = response[0]
    return list(messages)


async def xack(client: redis.Redis, stream_key: str, group_name: str, message_id: bytes) -> None:
    await client.xack(stream_key, group_name, message_id)
