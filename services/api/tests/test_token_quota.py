from uuid import uuid4

from redis.exceptions import ConnectionError as RedisConnectionError

from app.services.token_quota import (
    ORGANIZATION_TOKEN_QUOTA_KEY_VERSION,
    READ_ORGANIZATION_TOKEN_QUOTA_LUA,
    RECORD_ORGANIZATION_TOKEN_USAGE_LUA,
    OrganizationTokenQuotaStatus,
    build_organization_token_quota_key,
    get_organization_token_quota_status,
    record_organization_token_usage,
)


class FakeRedisTokenQuota:
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


class UnavailableRedisTokenQuota:
    def eval(
        self,
        script: str,
        numkeys: int,
        *keys_and_args: str,
    ) -> object:
        raise RedisConnectionError("Redis is unavailable")


def test_organization_token_quota_key_hides_the_organization_id() -> None:
    organization_id = uuid4()

    key = build_organization_token_quota_key(
        organization_id=organization_id,
    )
    equivalent_key = build_organization_token_quota_key(
        organization_id=str(organization_id).upper(),
    )
    other_key = build_organization_token_quota_key(
        organization_id=uuid4(),
    )

    assert key == equivalent_key
    assert key != other_key
    assert str(organization_id) not in key
    assert key.startswith(
        f"securecloudops:token-quota:{ORGANIZATION_TOKEN_QUOTA_KEY_VERSION}:organization:"
    )


def test_token_quota_reports_remaining_capacity() -> None:
    cache = FakeRedisTokenQuota(result=[1200, 3600])

    result = get_organization_token_quota_status(
        cache,  # type: ignore[arg-type]
        cache_key="organization-token-quota-key",
        token_limit=5000,
    )

    assert result == OrganizationTokenQuotaStatus(
        has_capacity=True,
        is_enforced=True,
        token_limit=5000,
        used_tokens=1200,
        remaining_tokens=3800,
        reset_after_seconds=3600,
    )
    assert cache.calls == [
        (
            READ_ORGANIZATION_TOKEN_QUOTA_LUA,
            1,
            ("organization-token-quota-key",),
        )
    ]


def test_token_quota_reports_an_exhausted_budget() -> None:
    cache = FakeRedisTokenQuota(result=[5000, 1800])

    result = get_organization_token_quota_status(
        cache,  # type: ignore[arg-type]
        cache_key="organization-token-quota-key",
        token_limit=5000,
    )

    assert result.has_capacity is False
    assert result.is_enforced is True
    assert result.remaining_tokens == 0


def test_token_quota_records_actual_model_usage() -> None:
    cache = FakeRedisTokenQuota(result=[1450, 86400])

    result = record_organization_token_usage(
        cache,  # type: ignore[arg-type]
        cache_key="organization-token-quota-key",
        token_count=250,
        token_limit=5000,
        window_seconds=86400,
    )

    assert result == OrganizationTokenQuotaStatus(
        has_capacity=True,
        is_enforced=True,
        token_limit=5000,
        used_tokens=1450,
        remaining_tokens=3550,
        reset_after_seconds=86400,
    )
    assert cache.calls == [
        (
            RECORD_ORGANIZATION_TOKEN_USAGE_LUA,
            1,
            (
                "organization-token-quota-key",
                "250",
                "86400",
            ),
        )
    ]


def test_token_quota_safely_represents_an_overrun() -> None:
    cache = FakeRedisTokenQuota(result=[5200, 72000])

    result = record_organization_token_usage(
        cache,  # type: ignore[arg-type]
        cache_key="organization-token-quota-key",
        token_count=400,
        token_limit=5000,
        window_seconds=86400,
    )

    assert result.has_capacity is False
    assert result.used_tokens == 5200
    assert result.remaining_tokens == 0


def test_token_quota_fails_closed_when_redis_is_unavailable() -> None:
    result = get_organization_token_quota_status(
        UnavailableRedisTokenQuota(),  # type: ignore[arg-type]
        cache_key="organization-token-quota-key",
        token_limit=5000,
    )

    assert result == OrganizationTokenQuotaStatus(
        has_capacity=False,
        is_enforced=False,
        token_limit=5000,
        used_tokens=0,
        remaining_tokens=0,
        reset_after_seconds=0,
    )


def test_token_quota_fails_closed_for_malformed_redis_output() -> None:
    cache = FakeRedisTokenQuota(result=["invalid"])

    result = get_organization_token_quota_status(
        cache,  # type: ignore[arg-type]
        cache_key="organization-token-quota-key",
        token_limit=5000,
    )

    assert result.has_capacity is False
    assert result.is_enforced is False
    assert result.remaining_tokens == 0
