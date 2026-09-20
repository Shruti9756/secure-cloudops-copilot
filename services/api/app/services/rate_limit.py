"""Redis-backed fixed-window rate limiting for costly AI API endpoints."""

import hashlib
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from redis import Redis
from redis.exceptions import RedisError

# Bump this version if the rate-limit key structure or algorithm changes.
RATE_LIMIT_KEY_VERSION = "v1"
LAYERED_RATE_LIMIT_KEY_VERSION = "v2"

# Redis runs this whole script atomically, preventing INCR/EXPIRE race conditions.
FIXED_WINDOW_RATE_LIMIT_LUA = """
local request_count = redis.call("INCR", KEYS[1])

if request_count == 1 then
    redis.call("EXPIRE", KEYS[1], ARGV[1])
end

local reset_after_seconds = redis.call("TTL", KEYS[1])
return {request_count, reset_after_seconds}
"""
LAYERED_FIXED_WINDOW_RATE_LIMIT_LUA = """
local user_request_count = tonumber(redis.call("GET", KEYS[1])) or 0
local organization_request_count = tonumber(redis.call("GET", KEYS[2])) or 0

local user_limit = tonumber(ARGV[1])
local organization_limit = tonumber(ARGV[2])
local window_seconds = tonumber(ARGV[3])
local is_allowed = 0

if user_request_count < user_limit
    and organization_request_count < organization_limit then
    user_request_count = redis.call("INCR", KEYS[1])

    if user_request_count == 1 then
        redis.call("EXPIRE", KEYS[1], window_seconds)
    end

    organization_request_count = redis.call("INCR", KEYS[2])

    if organization_request_count == 1 then
        redis.call("EXPIRE", KEYS[2], window_seconds)
    end

    is_allowed = 1
end

local user_reset_after_seconds = redis.call("TTL", KEYS[1])
local organization_reset_after_seconds = redis.call("TTL", KEYS[2])

return {
    is_allowed,
    user_request_count,
    user_reset_after_seconds,
    organization_request_count,
    organization_reset_after_seconds
}
"""


@dataclass(frozen=True)
class RateLimitResult:
    """A safe rate-limit decision plus metadata for HTTP response headers."""

    is_allowed: bool
    is_enforced: bool
    limit: int
    remaining: int
    reset_after_seconds: int


type RateLimitBlockedScope = Literal[
    "user",
    "organization",
    "user_and_organization",
]


@dataclass(frozen=True)
class RateLimitBudget:
    """One safe view of a rate-limit counter."""

    limit: int
    remaining: int
    reset_after_seconds: int


@dataclass(frozen=True)
class LayeredRateLimitResult:
    """Combined decision for user and organization request budgets."""

    is_allowed: bool
    is_enforced: bool
    user: RateLimitBudget
    organization: RateLimitBudget
    blocked_scope: RateLimitBlockedScope | None


def build_rate_limit_key(
    *,
    tenant_slug: str,
    client_identifier: str,
) -> str:
    """Build a tenant-scoped key without exposing the client IP in Redis."""
    normalized_tenant = tenant_slug.strip().casefold()
    normalized_client_identifier = client_identifier.strip().casefold()
    client_digest = hashlib.sha256(normalized_client_identifier.encode("utf-8")).hexdigest()

    return f"securecloudops:rate-limit:{RATE_LIMIT_KEY_VERSION}:{normalized_tenant}:{client_digest}"


def build_user_rate_limit_key(
    *,
    organization_id: UUID | str,
    user_id: UUID | str,
) -> str:
    """Build a private per-user key scoped to one organization."""
    organization_identifier = _normalize_rate_limit_identifier(
        organization_id,
        name="Organization ID",
    )
    user_identifier = _normalize_rate_limit_identifier(
        user_id,
        name="User ID",
    )
    identifier_digest = _hash_rate_limit_identifiers(
        organization_identifier,
        user_identifier,
    )

    return f"securecloudops:rate-limit:{LAYERED_RATE_LIMIT_KEY_VERSION}:user:{identifier_digest}"


def build_organization_rate_limit_key(
    *,
    organization_id: UUID | str,
) -> str:
    """Build a private organization-wide rate-limit key."""
    organization_identifier = _normalize_rate_limit_identifier(
        organization_id,
        name="Organization ID",
    )
    identifier_digest = _hash_rate_limit_identifiers(organization_identifier)

    return (
        f"securecloudops:rate-limit:{LAYERED_RATE_LIMIT_KEY_VERSION}:"
        f"organization:{identifier_digest}"
    )


def _normalize_rate_limit_identifier(
    value: UUID | str,
    *,
    name: str,
) -> str:
    """Normalize an identifier before hashing it into a Redis key."""
    if not isinstance(value, UUID | str):
        raise TypeError(f"{name} must be a UUID or string")

    normalized_value = str(value).strip().casefold()

    if not normalized_value:
        raise ValueError(f"{name} must not be empty")

    return normalized_value


def _hash_rate_limit_identifiers(*identifiers: str) -> str:
    """Hash one or more normalized identifiers without exposing them in Redis."""
    digest_input = "\x1f".join(identifiers)
    return hashlib.sha256(digest_input.encode("utf-8")).hexdigest()


def check_rate_limit(
    cache: Redis,
    *,
    cache_key: str,
    limit: int,
    window_seconds: int,
) -> RateLimitResult:
    """Consume one fixed-window request slot with a fail-closed Redis decision."""
    _require_positive_int(limit, name="Rate-limit request limit")
    _require_positive_int(window_seconds, name="Rate-limit window duration")

    try:
        raw_result = cache.eval(
            FIXED_WINDOW_RATE_LIMIT_LUA,
            1,
            cache_key,
            str(window_seconds),
        )
    except RedisError:
        # The API layer converts this unavailable security control into a safe 503.
        return _unavailable_result(limit)

    return _parse_redis_result(raw_result, limit=limit)


def check_layered_rate_limit(
    cache: Redis,
    *,
    user_cache_key: str,
    organization_cache_key: str,
    user_limit: int,
    organization_limit: int,
    window_seconds: int,
) -> LayeredRateLimitResult:
    """Consume one user slot and one organization slot atomically."""
    _require_positive_int(user_limit, name="User rate-limit request limit")
    _require_positive_int(
        organization_limit,
        name="Organization rate-limit request limit",
    )
    _require_positive_int(window_seconds, name="Rate-limit window duration")

    try:
        raw_result = cache.eval(
            LAYERED_FIXED_WINDOW_RATE_LIMIT_LUA,
            2,
            user_cache_key,
            organization_cache_key,
            str(user_limit),
            str(organization_limit),
            str(window_seconds),
        )
    except RedisError:
        return _unavailable_layered_result(
            user_limit=user_limit,
            organization_limit=organization_limit,
        )

    return _parse_layered_redis_result(
        raw_result,
        user_limit=user_limit,
        organization_limit=organization_limit,
    )


def _parse_layered_redis_result(
    raw_result: Any,
    *,
    user_limit: int,
    organization_limit: int,
) -> LayeredRateLimitResult:
    """Validate the five values returned by the layered Redis script."""
    if not isinstance(raw_result, (list, tuple)) or len(raw_result) != 5:
        return _unavailable_layered_result(
            user_limit=user_limit,
            organization_limit=organization_limit,
        )

    try:
        is_allowed_value = int(raw_result[0])
        user_request_count = int(raw_result[1])
        user_reset_after_seconds = int(raw_result[2])
        organization_request_count = int(raw_result[3])
        organization_reset_after_seconds = int(raw_result[4])
    except TypeError, ValueError:
        return _unavailable_layered_result(
            user_limit=user_limit,
            organization_limit=organization_limit,
        )

    if is_allowed_value not in {0, 1}:
        return _unavailable_layered_result(
            user_limit=user_limit,
            organization_limit=organization_limit,
        )

    if user_request_count < 0 or organization_request_count < 0:
        return _unavailable_layered_result(
            user_limit=user_limit,
            organization_limit=organization_limit,
        )

    if user_request_count > 0 and user_reset_after_seconds < 0:
        return _unavailable_layered_result(
            user_limit=user_limit,
            organization_limit=organization_limit,
        )

    if organization_request_count > 0 and organization_reset_after_seconds < 0:
        return _unavailable_layered_result(
            user_limit=user_limit,
            organization_limit=organization_limit,
        )

    is_allowed = is_allowed_value == 1
    user_is_blocked = user_request_count >= user_limit
    organization_is_blocked = organization_request_count >= organization_limit

    if is_allowed and (
        user_request_count < 1
        or organization_request_count < 1
        or user_request_count > user_limit
        or organization_request_count > organization_limit
    ):
        return _unavailable_layered_result(
            user_limit=user_limit,
            organization_limit=organization_limit,
        )

    if not is_allowed and not (user_is_blocked or organization_is_blocked):
        return _unavailable_layered_result(
            user_limit=user_limit,
            organization_limit=organization_limit,
        )

    blocked_scope: RateLimitBlockedScope | None = None

    if user_is_blocked and organization_is_blocked:
        blocked_scope = "user_and_organization"
    elif user_is_blocked:
        blocked_scope = "user"
    elif organization_is_blocked:
        blocked_scope = "organization"

    return LayeredRateLimitResult(
        is_allowed=is_allowed,
        is_enforced=True,
        user=RateLimitBudget(
            limit=user_limit,
            remaining=max(user_limit - user_request_count, 0),
            reset_after_seconds=(max(user_reset_after_seconds, 1) if user_request_count > 0 else 0),
        ),
        organization=RateLimitBudget(
            limit=organization_limit,
            remaining=max(organization_limit - organization_request_count, 0),
            reset_after_seconds=(
                max(organization_reset_after_seconds, 1) if organization_request_count > 0 else 0
            ),
        ),
        blocked_scope=blocked_scope,
    )


def _unavailable_layered_result(
    *,
    user_limit: int,
    organization_limit: int,
) -> LayeredRateLimitResult:
    """Fail closed when a trustworthy layered decision is unavailable."""
    return LayeredRateLimitResult(
        is_allowed=False,
        is_enforced=False,
        user=RateLimitBudget(
            limit=user_limit,
            remaining=0,
            reset_after_seconds=0,
        ),
        organization=RateLimitBudget(
            limit=organization_limit,
            remaining=0,
            reset_after_seconds=0,
        ),
        blocked_scope=None,
    )


def _parse_redis_result(
    raw_result: Any,
    *,
    limit: int,
) -> RateLimitResult:
    """Convert Redis script output into a validated application decision."""
    if not isinstance(raw_result, (list, tuple)) or len(raw_result) != 2:
        return _unavailable_result(limit)

    try:
        request_count = int(raw_result[0])
        reset_after_seconds = int(raw_result[1])
    except TypeError, ValueError:
        return _unavailable_result(limit)

    if request_count < 1:
        return _unavailable_result(limit)

    return RateLimitResult(
        is_allowed=request_count <= limit,
        is_enforced=True,
        limit=limit,
        remaining=max(limit - request_count, 0),
        # Redis can report 0 near expiry; HTTP clients need at least one second.
        reset_after_seconds=max(reset_after_seconds, 1),
    )


def _unavailable_result(limit: int) -> RateLimitResult:
    """Represent an unavailable limiter so the API can fail closed."""
    return RateLimitResult(
        is_allowed=False,
        is_enforced=False,
        limit=limit,
        remaining=0,
        reset_after_seconds=0,
    )


def _require_positive_int(value: int, *, name: str) -> None:
    """Reject invalid rate-limit configuration before contacting Redis."""
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
