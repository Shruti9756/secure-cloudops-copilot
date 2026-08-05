from functools import lru_cache

import redis
from redis import Redis

from app.core.config import get_settings


@lru_cache
def get_redis_client() -> Redis:
    return redis.Redis.from_url(
        get_settings().redis_url,
        decode_responses=True,
    )


def redis_is_available() -> bool:
    return bool(get_redis_client().ping())
