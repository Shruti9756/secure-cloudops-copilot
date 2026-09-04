"""Safe Redis helpers for short-lived API response caching."""

import hashlib
import json
from collections.abc import Collection
from dataclasses import dataclass
from typing import Protocol

from redis.exceptions import RedisError

# Bump this version when the answer pipeline changes in a cache-incompatible way.
ASK_RESPONSE_CACHE_KEY_VERSION = "v2"

# Short TTL limits how long an answer can remain stale after knowledge changes.
ASK_RESPONSE_CACHE_TTL_SECONDS = 300


class RedisCache(Protocol):
    """The small Redis interface required by this module."""

    def get(self, name: str) -> str | None:
        """Return a cached string value, or None when the key is absent."""

    def set(self, name: str, value: str, ex: int) -> bool | None:
        """Store a value with a Redis expiry measured in seconds."""


@dataclass(frozen=True)
class CacheLookup:
    """A cache read result that distinguishes a miss from Redis unavailability."""

    payload: dict[str, object] | None
    is_available: bool


def normalize_question(question: str) -> str:
    """Make harmless whitespace and casing differences share one cache entry."""
    return " ".join(question.split()).casefold()


def build_ask_response_cache_key(
    *,
    tenant_slug: str,
    document_access_levels: Collection[str],
    question: str,
    limit: int,
) -> str:
    """Build a tenant-safe cache key without exposing the raw user question."""
    normalized_question = normalize_question(question)
    normalized_document_access_levels = tuple(sorted(set(document_access_levels)))

    if not normalized_document_access_levels:
        raise ValueError("At least one document access level is required")

    access_scope_digest = hashlib.sha256(
        "\x1f".join(normalized_document_access_levels).encode("utf-8")
    ).hexdigest()
    question_digest = hashlib.sha256(normalized_question.encode("utf-8")).hexdigest()

    return (
        f"securecloudops:ask:{ASK_RESPONSE_CACHE_KEY_VERSION}:"
        f"{tenant_slug}:{access_scope_digest}:{limit}:{question_digest}"
    )


def load_cached_response(
    cache: RedisCache,
    *,
    cache_key: str,
) -> CacheLookup:
    """Read one JSON object safely; cache problems must not break the API."""
    try:
        raw_payload = cache.get(cache_key)
    except RedisError:
        return CacheLookup(payload=None, is_available=False)

    if raw_payload is None:
        return CacheLookup(payload=None, is_available=True)

    try:
        payload = json.loads(raw_payload)
    except TypeError, json.JSONDecodeError:
        # A malformed cache entry is treated as a normal miss.
        return CacheLookup(payload=None, is_available=True)

    if not isinstance(payload, dict):
        return CacheLookup(payload=None, is_available=True)

    return CacheLookup(payload=payload, is_available=True)


def store_cached_response(
    cache: RedisCache,
    *,
    cache_key: str,
    payload: dict[str, object],
    ttl_seconds: int = ASK_RESPONSE_CACHE_TTL_SECONDS,
) -> bool:
    """Store JSON safely; caching failure must not prevent a valid API response."""
    try:
        serialized_payload = json.dumps(
            payload,
            separators=(",", ":"),
            sort_keys=True,
        )
        cache.set(cache_key, serialized_payload, ex=ttl_seconds)
    except RedisError, TypeError, ValueError:
        return False

    return True
