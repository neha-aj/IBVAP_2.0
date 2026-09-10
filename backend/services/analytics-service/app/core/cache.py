"""Short-TTL Redis cache in front of the (already fast, pre-aggregated)
materialized-view reads (SAS §3: "Redis (cached aggregates, short TTL)") --
absorbs a burst of Dashboard polls from many open browser tabs without
even hitting Postgres."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

import redis.asyncio as redis


async def cached_json(
    redis_client: redis.Redis, key: str, ttl_seconds: int, compute: Callable[[], Awaitable[Any]]
) -> Any:
    cached = await redis_client.get(key)
    if cached is not None:
        return json.loads(cached)

    result = await compute()
    await redis_client.set(key, json.dumps(result), ex=ttl_seconds)
    return result
