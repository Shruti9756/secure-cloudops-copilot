from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.infrastructure.redis import build_redis_client

DATABASE_URL = "postgresql+psycopg://local:localpass@localhost:5432/localdb"


def test_local_redis_url_still_works() -> None:
    settings = Settings(
        _env_file=None,
        database_url=DATABASE_URL,
        redis_url="redis://localhost:6379/0",
    )

    with patch("app.infrastructure.redis.redis.Redis.from_url") as from_url:
        client = build_redis_client(settings)

    from_url.assert_called_once_with(
        "redis://localhost:6379/0",
        decode_responses=True,
    )
    assert client is from_url.return_value


def test_split_redis_settings_require_tls_and_hide_password() -> None:
    password = "synthetic-redis-password"
    settings = Settings(
        _env_file=None,
        database_url=DATABASE_URL,
        redis_url=None,
        redis_host="cache.example.internal",
        redis_port=6380,
        redis_password=password,
    )

    with patch("app.infrastructure.redis.redis.Redis") as redis_client:
        client = build_redis_client(settings)

    redis_client.assert_called_once_with(
        host="cache.example.internal",
        port=6380,
        password=password,
        ssl=True,
        ssl_cert_reqs="required",
        decode_responses=True,
    )
    assert client is redis_client.return_value
    assert password not in repr(settings)


def test_mixed_redis_settings_are_rejected_without_leaking_password() -> None:
    password = "synthetic-redis-password"

    with pytest.raises(ValidationError) as error:
        Settings(
            _env_file=None,
            database_url=DATABASE_URL,
            redis_url="redis://localhost:6379/0",
            redis_host="cache.example.internal",
            redis_password=password,
        )

    assert password not in str(error.value)


def test_missing_redis_settings_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url=DATABASE_URL,
            redis_url=None,
            redis_host=None,
            redis_password=None,
        )
