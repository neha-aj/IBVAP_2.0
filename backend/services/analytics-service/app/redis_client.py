from functools import lru_cache

import redis.asyncio as redis

from ibvap_common.redis_streams import build_redis_client

from app.core.config import get_settings


@lru_cache
def get_redis_client() -> redis.Redis:
    return build_redis_client(get_settings())
