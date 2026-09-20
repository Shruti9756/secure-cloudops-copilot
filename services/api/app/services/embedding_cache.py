"""Validated, fail-open Redis caching for embedding results."""

import hashlib
import json
import math
from dataclasses import dataclass, replace
from typing import Protocol

from redis.exceptions import RedisError

from app.services.embeddings import EmbeddingProvider, EmbeddingResult

EMBEDDING_CACHE_KEY_VERSION = "v1"
EMBEDDING_CACHE_TTL_SECONDS = 604_800


class EmbeddingCacheClient(Protocol):
    """Small Redis interface required by the embedding cache."""

    def get(self, name: str) -> str | bytes | None:
        """Return one cached value."""

    def set(
        self,
        name: str,
        value: str,
        *,
        ex: int,
    ) -> bool | None:
        """Store one cached value with a bounded lifetime."""


@dataclass(frozen=True)
class EmbeddingCacheLookup:
    """A cache lookup that distinguishes a miss from Redis failure."""

    result: EmbeddingResult | None
    is_available: bool


class CachedEmbeddingProvider:
    """Reuse validated embeddings while preserving the provider interface."""

    def __init__(
        self,
        *,
        provider: EmbeddingProvider,
        cache: EmbeddingCacheClient,
        model_id: str,
        dimensions: int,
        ttl_seconds: int = EMBEDDING_CACHE_TTL_SECONDS,
    ) -> None:
        self._provider = provider
        self._cache = cache
        self._model_id = _normalize_model_id(model_id)

        _require_positive_integer(
            dimensions,
            name="Expected embedding dimensions",
        )
        _require_positive_integer(
            ttl_seconds,
            name="Embedding cache TTL",
        )

        self._dimensions = dimensions
        self._ttl_seconds = ttl_seconds

    def embed(self, text: str) -> EmbeddingResult:
        """Return a valid cached embedding or call the underlying provider."""
        normalized_text = normalize_embedding_text(text)
        cache_key = build_embedding_cache_key(
            model_id=self._model_id,
            text=normalized_text,
        )

        lookup = load_cached_embedding(
            self._cache,
            cache_key=cache_key,
            expected_model_id=self._model_id,
            expected_dimensions=self._dimensions,
        )

        if lookup.result is not None:
            return lookup.result

        # The provider receives exactly the same normalized text used by the key.
        provider_result = self._provider.embed(normalized_text)
        validated_result = _validate_embedding_result(
            provider_result,
            expected_model_id=self._model_id,
            expected_dimensions=self._dimensions,
        )

        # Do not make a second Redis call after a failed read.

        if lookup.is_available:
            store_cached_embedding(
                self._cache,
                cache_key=cache_key,
                result=validated_result,
                expected_model_id=self._model_id,
                expected_dimensions=self._dimensions,
                ttl_seconds=self._ttl_seconds,
            )
            return replace(
                validated_result,
                cache_status="MISS",
            )

        return replace(
            validated_result,
            cache_status="BYPASS",
        )


def normalize_embedding_text(text: str) -> str:
    """Normalize harmless whitespace differences without changing case."""
    if not isinstance(text, str):
        raise TypeError("Embedding text must be a string")

    normalized_text = " ".join(text.split())

    if not normalized_text:
        raise ValueError("Embedding text must not be empty")

    return normalized_text


def build_embedding_cache_key(
    *,
    model_id: str,
    text: str,
) -> str:
    """Build a versioned key without exposing the model input text."""
    normalized_model_id = _normalize_model_id(model_id)
    normalized_text = normalize_embedding_text(text)

    model_digest = hashlib.sha256(normalized_model_id.encode("utf-8")).hexdigest()
    text_digest = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()

    return (
        f"securecloudops:embedding-cache:{EMBEDDING_CACHE_KEY_VERSION}:{model_digest}:{text_digest}"
    )


def load_cached_embedding(
    cache: EmbeddingCacheClient,
    *,
    cache_key: str,
    expected_model_id: str,
    expected_dimensions: int,
) -> EmbeddingCacheLookup:
    """Load and validate one cached embedding; malformed data becomes a miss."""
    normalized_cache_key = _normalize_cache_key(cache_key)
    normalized_model_id = _normalize_model_id(expected_model_id)
    _require_positive_integer(
        expected_dimensions,
        name="Expected embedding dimensions",
    )

    try:
        raw_payload = cache.get(normalized_cache_key)
    except RedisError:
        return EmbeddingCacheLookup(
            result=None,
            is_available=False,
        )

    if raw_payload is None:
        return EmbeddingCacheLookup(
            result=None,
            is_available=True,
        )

    try:
        payload = json.loads(raw_payload)
    except TypeError, UnicodeDecodeError, json.JSONDecodeError:
        return EmbeddingCacheLookup(
            result=None,
            is_available=True,
        )

    result = _parse_embedding_payload(
        payload,
        expected_model_id=normalized_model_id,
        expected_dimensions=expected_dimensions,
    )
    if result is not None:
        result = replace(
            result,
            cache_status="HIT",
        )
    return EmbeddingCacheLookup(
        result=result,
        is_available=True,
    )


def store_cached_embedding(
    cache: EmbeddingCacheClient,
    *,
    cache_key: str,
    result: EmbeddingResult,
    expected_model_id: str,
    expected_dimensions: int,
    ttl_seconds: int = EMBEDDING_CACHE_TTL_SECONDS,
) -> bool:
    """Validate and store one embedding without allowing cache failure to block work."""
    normalized_cache_key = _normalize_cache_key(cache_key)
    normalized_model_id = _normalize_model_id(expected_model_id)
    _require_positive_integer(
        expected_dimensions,
        name="Expected embedding dimensions",
    )
    _require_positive_integer(
        ttl_seconds,
        name="Embedding cache TTL",
    )

    validated_result = _validate_embedding_result(
        result,
        expected_model_id=normalized_model_id,
        expected_dimensions=expected_dimensions,
    )

    payload: dict[str, object] = {
        "input_text_token_count": validated_result.input_text_token_count,
        "model_id": validated_result.model_id,
        "vector": validated_result.vector,
    }

    serialized_payload = json.dumps(
        payload,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )

    try:
        stored = cache.set(
            normalized_cache_key,
            serialized_payload,
            ex=ttl_seconds,
        )
    except RedisError:
        return False

    return bool(stored)


def _validate_embedding_result(
    result: EmbeddingResult,
    *,
    expected_model_id: str,
    expected_dimensions: int,
) -> EmbeddingResult:
    payload: dict[str, object] = {
        "input_text_token_count": result.input_text_token_count,
        "model_id": result.model_id,
        "vector": result.vector,
    }

    validated_result = _parse_embedding_payload(
        payload,
        expected_model_id=expected_model_id,
        expected_dimensions=expected_dimensions,
    )

    if validated_result is None:
        raise ValueError("Embedding result does not match the cache configuration")

    return validated_result


def _parse_embedding_payload(
    payload: object,
    *,
    expected_model_id: str,
    expected_dimensions: int,
) -> EmbeddingResult | None:
    if not isinstance(payload, dict):
        return None

    if set(payload) != {
        "input_text_token_count",
        "model_id",
        "vector",
    }:
        return None

    model_id = payload["model_id"]

    if model_id != expected_model_id:
        return None

    token_count = payload["input_text_token_count"]

    if isinstance(token_count, bool) or not isinstance(token_count, int) or token_count < 0:
        return None

    vector = payload["vector"]

    if not isinstance(vector, list) or len(vector) != expected_dimensions:
        return None

    normalized_vector: list[float] = []

    for value in vector:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None

        try:
            normalized_value = float(value)
        except OverflowError:
            return None

        if not math.isfinite(normalized_value):
            return None

        normalized_vector.append(normalized_value)

    return EmbeddingResult(
        vector=normalized_vector,
        input_text_token_count=token_count,
        model_id=model_id,
    )


def _normalize_model_id(model_id: str) -> str:
    if not isinstance(model_id, str):
        raise TypeError("Embedding model ID must be a string")

    normalized_model_id = model_id.strip()

    if not normalized_model_id:
        raise ValueError("Embedding model ID must not be empty")

    return normalized_model_id


def _normalize_cache_key(cache_key: str) -> str:
    if not isinstance(cache_key, str):
        raise TypeError("Embedding cache key must be a string")

    normalized_cache_key = cache_key.strip()

    if not normalized_cache_key:
        raise ValueError("Embedding cache key must not be empty")

    return normalized_cache_key


def _require_positive_integer(value: int, *, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
