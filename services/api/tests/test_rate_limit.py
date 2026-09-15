from uuid import uuid4

from redis.exceptions import ConnectionError as RedisConnectionError

from app.services.rate_limit import (
    FIXED_WINDOW_RATE_LIMIT_LUA,
    LAYERED_FIXED_WINDOW_RATE_LIMIT_LUA,
    LayeredRateLimitResult,
    RateLimitBudget,
    RateLimitResult,
    build_organization_rate_limit_key,
    build_rate_limit_key,
    build_user_rate_limit_key,
    check_layered_rate_limit,
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


def test_user_rate_limit_key_is_organization_scoped_and_hides_identifiers() -> None:
    organization_id = uuid4()
    user_id = uuid4()

    key = build_user_rate_limit_key(
        organization_id=organization_id,
        user_id=user_id,
    )
    equivalent_key = build_user_rate_limit_key(
        organization_id=str(organization_id).upper(),
        user_id=str(user_id).upper(),
    )
    other_user_key = build_user_rate_limit_key(
        organization_id=organization_id,
        user_id=uuid4(),
    )
    other_organization_key = build_user_rate_limit_key(
        organization_id=uuid4(),
        user_id=user_id,
    )

    assert key == equivalent_key
    assert key != other_user_key
    assert key != other_organization_key
    assert str(organization_id) not in key
    assert str(user_id) not in key
    assert key.startswith("securecloudops:rate-limit:v2:user:")


def test_organization_rate_limit_key_hides_and_separates_organizations() -> None:
    organization_id = uuid4()

    key = build_organization_rate_limit_key(
        organization_id=organization_id,
    )
    equivalent_key = build_organization_rate_limit_key(
        organization_id=str(organization_id).upper(),
    )
    other_organization_key = build_organization_rate_limit_key(
        organization_id=uuid4(),
    )

    assert key == equivalent_key
    assert key != other_organization_key
    assert str(organization_id) not in key
    assert key.startswith("securecloudops:rate-limit:v2:organization:")


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


def test_layered_rate_limiter_consumes_both_available_budgets() -> None:
    cache = FakeRedisRateLimiter(result=[1, 1, 60, 1, 60])

    result = check_layered_rate_limit(
        cache,  # type: ignore[arg-type]
        user_cache_key="user-rate-limit-key",
        organization_cache_key="organization-rate-limit-key",
        user_limit=3,
        organization_limit=10,
        window_seconds=60,
    )

    assert result == LayeredRateLimitResult(
        is_allowed=True,
        is_enforced=True,
        user=RateLimitBudget(
            limit=3,
            remaining=2,
            reset_after_seconds=60,
        ),
        organization=RateLimitBudget(
            limit=10,
            remaining=9,
            reset_after_seconds=60,
        ),
        blocked_scope=None,
    )
    assert cache.calls == [
        (
            LAYERED_FIXED_WINDOW_RATE_LIMIT_LUA,
            2,
            (
                "user-rate-limit-key",
                "organization-rate-limit-key",
                "3",
                "10",
                "60",
            ),
        )
    ]


def test_layered_rate_limiter_identifies_a_blocked_user() -> None:
    cache = FakeRedisRateLimiter(result=[0, 3, 17, 5, 31])

    result = check_layered_rate_limit(
        cache,  # type: ignore[arg-type]
        user_cache_key="user-rate-limit-key",
        organization_cache_key="organization-rate-limit-key",
        user_limit=3,
        organization_limit=10,
        window_seconds=60,
    )

    assert result.is_allowed is False
    assert result.is_enforced is True
    assert result.user.remaining == 0
    assert result.organization.remaining == 5
    assert result.blocked_scope == "user"


def test_layered_rate_limiter_identifies_a_blocked_organization() -> None:
    cache = FakeRedisRateLimiter(result=[0, 2, 17, 10, 31])

    result = check_layered_rate_limit(
        cache,  # type: ignore[arg-type]
        user_cache_key="user-rate-limit-key",
        organization_cache_key="organization-rate-limit-key",
        user_limit=3,
        organization_limit=10,
        window_seconds=60,
    )

    assert result.is_allowed is False
    assert result.is_enforced is True
    assert result.user.remaining == 1
    assert result.organization.remaining == 0
    assert result.blocked_scope == "organization"


def test_layered_rate_limiter_fails_closed_when_redis_is_unavailable() -> None:
    result = check_layered_rate_limit(
        UnavailableRedisRateLimiter(),  # type: ignore[arg-type]
        user_cache_key="user-rate-limit-key",
        organization_cache_key="organization-rate-limit-key",
        user_limit=3,
        organization_limit=10,
        window_seconds=60,
    )

    assert result.is_allowed is False
    assert result.is_enforced is False
    assert result.user.remaining == 0
    assert result.organization.remaining == 0
    assert result.blocked_scope is None


def test_layered_rate_limiter_rejects_an_inconsistent_allowed_result() -> None:
    cache = FakeRedisRateLimiter(result=[1, 0, -2, 0, -2])

    result = check_layered_rate_limit(
        cache,  # type: ignore[arg-type]
        user_cache_key="user-rate-limit-key",
        organization_cache_key="organization-rate-limit-key",
        user_limit=3,
        organization_limit=10,
        window_seconds=60,
    )

    assert result.is_allowed is False
    assert result.is_enforced is False
