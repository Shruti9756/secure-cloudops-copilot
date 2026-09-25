from functools import lru_cache

import redis
from redis import Redis

from app.core.config import Settings, get_settings


def build_redis_client(settings: Settings) -> Redis:
    if settings.redis_url is not None:
        return redis.Redis.from_url(
            settings.redis_url.get_secret_value(),
            decode_responses=True,
        )

    if settings.redis_host is None or settings.redis_password is None:
        raise ValueError("Split Redis settings are incomplete.")

    return redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        password=settings.redis_password.get_secret_value(),
        ssl=True,
        ssl_cert_reqs="required",
        decode_responses=True,
    )


@lru_cache
def get_redis_client() -> Redis:
    return build_redis_client(get_settings())


def redis_is_available() -> bool:
    return bool(get_redis_client().ping())
