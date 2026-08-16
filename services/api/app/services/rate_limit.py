"""Redis-backed fixed-window rate limiting for costly AI API endpoints."""

import hashlib
from dataclasses import dataclass
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

# Bump this version if the rate-limit key structure or algorithm changes.
RATE_LIMIT_KEY_VERSION = "v1"

# Redis runs this whole script atomically, preventing INCR/EXPIRE race conditions.
FIXED_WINDOW_RATE_LIMIT_LUA = """
local request_count = redis.call("INCR", KEYS[1])

if request_count == 1 then
    redis.call("EXPIRE", KEYS[1], ARGV[1])
end

local reset_after_seconds = redis.call("TTL", KEYS[1])
return {request_count, reset_after_seconds}
"""


@dataclass(frozen=True)
class RateLimitResult:
    """A safe rate-limit decision plus metadata for HTTP response headers."""

    is_allowed: bool
    is_enforced: bool
    limit: int
    remaining: int
    reset_after_seconds: int


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
