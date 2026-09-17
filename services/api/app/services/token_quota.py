"""Redis-backed organization token-quota accounting."""

import hashlib
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from redis import Redis
from redis.exceptions import RedisError

ORGANIZATION_TOKEN_QUOTA_KEY_VERSION = "v1"

READ_ORGANIZATION_TOKEN_QUOTA_LUA = """
local used_tokens = tonumber(redis.call("GET", KEYS[1])) or 0
local reset_after_seconds = redis.call("TTL", KEYS[1])
return {used_tokens, reset_after_seconds}
"""

RECORD_ORGANIZATION_TOKEN_USAGE_LUA = """
local token_count = tonumber(ARGV[1])
local window_seconds = tonumber(ARGV[2])

local used_tokens = redis.call("INCRBY", KEYS[1], token_count)

if used_tokens == token_count then
    redis.call("EXPIRE", KEYS[1], window_seconds)
end

local reset_after_seconds = redis.call("TTL", KEYS[1])
return {used_tokens, reset_after_seconds}
"""


@dataclass(frozen=True)
class OrganizationTokenQuotaStatus:
    """Safe view of one organization's model-token budget."""

    has_capacity: bool
    is_enforced: bool
    token_limit: int
    used_tokens: int
    remaining_tokens: int
    reset_after_seconds: int


def build_organization_token_quota_key(
    *,
    organization_id: UUID | str,
) -> str:
    """Build a private Redis key without exposing the organization ID."""
    if not isinstance(organization_id, UUID | str):
        raise TypeError("Organization ID must be a UUID or string")

    normalized_identifier = str(organization_id).strip().casefold()

    if not normalized_identifier:
        raise ValueError("Organization ID must not be empty")

    identifier_digest = hashlib.sha256(normalized_identifier.encode("utf-8")).hexdigest()

    return (
        f"securecloudops:token-quota:"
        f"{ORGANIZATION_TOKEN_QUOTA_KEY_VERSION}:"
        f"organization:{identifier_digest}"
    )


def get_organization_token_quota_status(
    cache: Redis,
    *,
    cache_key: str,
    token_limit: int,
) -> OrganizationTokenQuotaStatus:
    """Read the current organization quota before starting model work."""
    _require_positive_int(token_limit, name="Organization token limit")

    try:
        raw_result = cache.eval(
            READ_ORGANIZATION_TOKEN_QUOTA_LUA,
            1,
            cache_key,
        )
    except RedisError:
        return _unavailable_quota_status(token_limit=token_limit)

    return _parse_quota_result(
        raw_result,
        token_limit=token_limit,
    )


def record_organization_token_usage(
    cache: Redis,
    *,
    cache_key: str,
    token_count: int,
    token_limit: int,
    window_seconds: int,
) -> OrganizationTokenQuotaStatus:
    """Atomically add actual model-token usage to the organization quota."""
    _require_positive_int(token_count, name="Token usage")
    _require_positive_int(token_limit, name="Organization token limit")
    _require_positive_int(window_seconds, name="Token quota window")

    try:
        raw_result = cache.eval(
            RECORD_ORGANIZATION_TOKEN_USAGE_LUA,
            1,
            cache_key,
            str(token_count),
            str(window_seconds),
        )
    except RedisError:
        return _unavailable_quota_status(token_limit=token_limit)

    return _parse_quota_result(
        raw_result,
        token_limit=token_limit,
    )


def _parse_quota_result(
    raw_result: Any,
    *,
    token_limit: int,
) -> OrganizationTokenQuotaStatus:
    """Validate Redis output before trusting the quota decision."""
    if not isinstance(raw_result, (list, tuple)) or len(raw_result) != 2:
        return _unavailable_quota_status(token_limit=token_limit)

    try:
        used_tokens = int(raw_result[0])
        reset_after_seconds = int(raw_result[1])
    except TypeError, ValueError:
        return _unavailable_quota_status(token_limit=token_limit)

    if used_tokens < 0:
        return _unavailable_quota_status(token_limit=token_limit)

    if used_tokens > 0 and reset_after_seconds < 0:
        return _unavailable_quota_status(token_limit=token_limit)

    normalized_reset = (
        max(reset_after_seconds, 1) if used_tokens > 0 else max(reset_after_seconds, 0)
    )

    return OrganizationTokenQuotaStatus(
        has_capacity=used_tokens < token_limit,
        is_enforced=True,
        token_limit=token_limit,
        used_tokens=used_tokens,
        remaining_tokens=max(token_limit - used_tokens, 0),
        reset_after_seconds=normalized_reset,
    )


def _unavailable_quota_status(
    *,
    token_limit: int,
) -> OrganizationTokenQuotaStatus:
    """Fail closed when Redis cannot provide trustworthy quota state."""
    return OrganizationTokenQuotaStatus(
        has_capacity=False,
        is_enforced=False,
        token_limit=token_limit,
        used_tokens=0,
        remaining_tokens=0,
        reset_after_seconds=0,
    )


def _require_positive_int(value: int, *, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
