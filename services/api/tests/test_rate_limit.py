from redis.exceptions import ConnectionError as RedisConnectionError

from app.services.rate_limit import (
    FIXED_WINDOW_RATE_LIMIT_LUA,
    RateLimitResult,
    build_rate_limit_key,
    check_rate_limit,
)


class FakeRedisRateLimiter:
    """In-memory fake that returns chosen results from Redis EVAL."""

    def __init__(self, result: object) -> None:
        self.result = result
        self.calls: list[tuple[str, int, tuple[str, ...]]] = []

    def eval(
        self,
        script: str,
        numkeys: int,
        *keys_and_args: str,
    ) -> object:
        self.calls.append((script, numkeys, keys_and_args))
        return self.result


class UnavailableRedisRateLimiter:
    """Fake Redis failure used to verify the deliberate fail-closed behavior."""

    def eval(
        self,
        script: str,
        numkeys: int,
        *keys_and_args: str,
    ) -> object:
        raise RedisConnectionError("Redis is unavailable")


def test_rate_limit_key_is_tenant_scoped_and_hides_client_identifier() -> None:
    client_identifier = "127.0.0.1"

    cache_key = build_rate_limit_key(
        tenant_slug="nimbuscart",
        client_identifier=client_identifier,
    )
    equivalent_cache_key = build_rate_limit_key(
        tenant_slug="NIMBUSCART",
        client_identifier="127.0.0.1",
    )
    other_tenant_cache_key = build_rate_limit_key(
        tenant_slug="other-tenant",
        client_identifier=client_identifier,
    )

    assert cache_key == equivalent_cache_key
    assert cache_key != other_tenant_cache_key
    assert client_identifier not in cache_key
    assert cache_key.startswith("securecloudops:rate-limit:v1:nimbuscart:")


def test_rate_limiter_allows_requests_with_remaining_capacity() -> None:
    cache = FakeRedisRateLimiter(result=[1, 60])

    result = check_rate_limit(
        cache,  # type: ignore[arg-type]
        cache_key="rate-limit-key",
        limit=3,
        window_seconds=60,
    )

    assert result == RateLimitResult(
        is_allowed=True,
        is_enforced=True,
        limit=3,
        remaining=2,
        reset_after_seconds=60,
    )
    assert cache.calls == [
        (
            FIXED_WINDOW_RATE_LIMIT_LUA,
            1,
            ("rate-limit-key", "60"),
        )
    ]


def test_rate_limiter_blocks_requests_after_the_limit() -> None:
    cache = FakeRedisRateLimiter(result=[4, 17])

    result = check_rate_limit(
        cache,  # type: ignore[arg-type]
        cache_key="rate-limit-key",
        limit=3,
        window_seconds=60,
    )

    assert result == RateLimitResult(
        is_allowed=False,
        is_enforced=True,
        limit=3,
        remaining=0,
        reset_after_seconds=17,
    )


def test_rate_limiter_fails_closed_when_redis_is_unavailable() -> None:
    result = check_rate_limit(
        UnavailableRedisRateLimiter(),  # type: ignore[arg-type]
        cache_key="rate-limit-key",
        limit=3,
        window_seconds=60,
    )

    assert result == RateLimitResult(
        is_allowed=False,
        is_enforced=False,
        limit=3,
        remaining=0,
        reset_after_seconds=0,
    )


def test_rate_limiter_fails_closed_for_malformed_redis_output() -> None:
    cache = FakeRedisRateLimiter(result=[0, -1])

    result = check_rate_limit(
        cache,  # type: ignore[arg-type]
        cache_key="rate-limit-key",
        limit=3,
        window_seconds=60,
    )

    assert result == RateLimitResult(
        is_allowed=False,
        is_enforced=False,
        limit=3,
        remaining=0,
        reset_after_seconds=0,
    )
