import json

import pytest

from app.core.cache import cached_json


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int) -> None:
        self.store[key] = value


@pytest.mark.asyncio
async def test_cache_miss_computes_and_stores() -> None:
    redis = FakeRedis()
    calls = 0

    async def compute():
        nonlocal calls
        calls += 1
        return {"value": 42}

    result = await cached_json(redis, "k", 15, compute)

    assert result == {"value": 42}
    assert calls == 1
    assert json.loads(redis.store["k"]) == {"value": 42}


@pytest.mark.asyncio
async def test_cache_hit_does_not_recompute() -> None:
    redis = FakeRedis()
    redis.store["k"] = json.dumps({"value": 99})
    calls = 0

    async def compute():
        nonlocal calls
        calls += 1
        return {"value": 1}

    result = await cached_json(redis, "k", 15, compute)

    assert result == {"value": 99}
    assert calls == 0
