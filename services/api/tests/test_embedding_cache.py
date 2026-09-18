import json

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.services.embedding_cache import (
    EMBEDDING_CACHE_KEY_VERSION,
    EMBEDDING_CACHE_TTL_SECONDS,
    CachedEmbeddingProvider,
    build_embedding_cache_key,
    load_cached_embedding,
    normalize_embedding_text,
    store_cached_embedding,
)
from app.services.embeddings import EmbeddingCacheStatus, EmbeddingResult

TEST_MODEL_ID = "test-embedding-model-v1"
TEST_DIMENSIONS = 4


class FakeRedisEmbeddingCache:
    def __init__(self) -> None:
        self.entries: dict[str, str] = {}
        self.get_calls: list[str] = []
        self.set_calls: list[tuple[str, str, int]] = []

    def get(self, name: str) -> str | None:
        self.get_calls.append(name)
        return self.entries.get(name)

    def set(
        self,
        name: str,
        value: str,
        *,
        ex: int,
    ) -> bool:
        self.entries[name] = value
        self.set_calls.append((name, value, ex))
        return True


class UnavailableRedisEmbeddingCache:
    def get(self, name: str) -> str | None:
        raise RedisConnectionError("Redis is unavailable")

    def set(
        self,
        name: str,
        value: str,
        *,
        ex: int,
    ) -> bool:
        raise RedisConnectionError("Redis is unavailable")


class ReadUnavailableRedisEmbeddingCache:
    def __init__(self) -> None:
        self.set_call_count = 0

    def get(self, name: str) -> str | None:
        raise RedisConnectionError("Redis read is unavailable")

    def set(
        self,
        name: str,
        value: str,
        *,
        ex: int,
    ) -> bool:
        self.set_call_count += 1
        return True


class WriteUnavailableRedisEmbeddingCache(FakeRedisEmbeddingCache):
    def set(
        self,
        name: str,
        value: str,
        *,
        ex: int,
    ) -> bool:
        raise RedisConnectionError("Redis write is unavailable")


class FakeEmbeddingProvider:
    def __init__(
        self,
        result: EmbeddingResult | None = None,
    ) -> None:
        self.result = result or make_embedding_result()
        self.texts: list[str] = []

    def embed(self, text: str) -> EmbeddingResult:
        self.texts.append(text)
        return self.result


def make_embedding_result(
    *,
    cache_status: EmbeddingCacheStatus = "NOT_CHECKED",
) -> EmbeddingResult:
    return EmbeddingResult(
        vector=[0.1, 0.2, 0.3, 0.4],
        input_text_token_count=7,
        model_id=TEST_MODEL_ID,
        cache_status=cache_status,
    )


def test_normalize_embedding_text_collapses_whitespace_without_changing_case() -> None:
    normalized = normalize_embedding_text("  Inspect\r\n the\tPostgreSQL   Pool.  ")

    assert normalized == "Inspect the PostgreSQL Pool."
    assert normalized != "inspect the postgresql pool."


def test_embedding_cache_key_hashes_normalized_text_and_model() -> None:
    raw_text = "  Inspect\r\n the PostgreSQL pool.  "

    cache_key = build_embedding_cache_key(
        model_id=TEST_MODEL_ID,
        text=raw_text,
    )
    equivalent_key = build_embedding_cache_key(
        model_id=TEST_MODEL_ID,
        text="Inspect the PostgreSQL pool.",
    )
    other_model_key = build_embedding_cache_key(
        model_id="other-embedding-model",
        text=raw_text,
    )
    changed_case_key = build_embedding_cache_key(
        model_id=TEST_MODEL_ID,
        text="inspect the PostgreSQL pool.",
    )

    assert cache_key == equivalent_key
    assert cache_key != other_model_key
    assert cache_key != changed_case_key
    assert raw_text.strip() not in cache_key
    assert TEST_MODEL_ID not in cache_key
    assert cache_key.startswith(f"securecloudops:embedding-cache:{EMBEDDING_CACHE_KEY_VERSION}:")


def test_embedding_cache_returns_a_valid_hit() -> None:
    cache = FakeRedisEmbeddingCache()
    cache_key = build_embedding_cache_key(
        model_id=TEST_MODEL_ID,
        text="Inspect the PostgreSQL pool.",
    )
    cache.entries[cache_key] = json.dumps(
        {
            "input_text_token_count": 7,
            "model_id": TEST_MODEL_ID,
            "vector": [0.1, 0.2, 0.3, 0.4],
        }
    )

    lookup = load_cached_embedding(
        cache,
        cache_key=cache_key,
        expected_model_id=TEST_MODEL_ID,
        expected_dimensions=TEST_DIMENSIONS,
    )

    assert lookup.is_available is True
    assert lookup.result == make_embedding_result(cache_status="HIT")
    assert cache.get_calls == [cache_key]


def test_embedding_cache_reports_a_normal_miss() -> None:
    cache = FakeRedisEmbeddingCache()
    cache_key = build_embedding_cache_key(
        model_id=TEST_MODEL_ID,
        text="Inspect the PostgreSQL pool.",
    )

    lookup = load_cached_embedding(
        cache,
        cache_key=cache_key,
        expected_model_id=TEST_MODEL_ID,
        expected_dimensions=TEST_DIMENSIONS,
    )

    assert lookup.is_available is True
    assert lookup.result is None


@pytest.mark.parametrize(
    "payload",
    [
        "{not-valid-json",
        json.dumps(
            {
                "input_text_token_count": 7,
                "model_id": TEST_MODEL_ID,
                "vector": [10**400, 0.2, 0.3, 0.4],
            }
        ),
        json.dumps([]),
        json.dumps(
            {
                "input_text_token_count": 7,
                "model_id": "wrong-model",
                "vector": [0.1, 0.2, 0.3, 0.4],
            }
        ),
        json.dumps(
            {
                "input_text_token_count": -1,
                "model_id": TEST_MODEL_ID,
                "vector": [0.1, 0.2, 0.3, 0.4],
            }
        ),
        json.dumps(
            {
                "input_text_token_count": 7,
                "model_id": TEST_MODEL_ID,
                "vector": [0.1],
            }
        ),
        json.dumps(
            {
                "input_text_token_count": 7,
                "model_id": TEST_MODEL_ID,
                "vector": [0.1, True, 0.3, 0.4],
            }
        ),
        json.dumps(
            {
                "input_text_token_count": 7,
                "model_id": TEST_MODEL_ID,
                "vector": [0.1, float("nan"), 0.3, 0.4],
            }
        ),
    ],
)
def test_embedding_cache_treats_untrusted_payloads_as_misses(
    payload: str,
) -> None:
    cache = FakeRedisEmbeddingCache()
    cache_key = "embedding-cache-key"
    cache.entries[cache_key] = payload

    lookup = load_cached_embedding(
        cache,
        cache_key=cache_key,
        expected_model_id=TEST_MODEL_ID,
        expected_dimensions=TEST_DIMENSIONS,
    )

    assert lookup.is_available is True
    assert lookup.result is None


def test_embedding_cache_read_failure_is_nonfatal() -> None:
    lookup = load_cached_embedding(
        UnavailableRedisEmbeddingCache(),
        cache_key="embedding-cache-key",
        expected_model_id=TEST_MODEL_ID,
        expected_dimensions=TEST_DIMENSIONS,
    )

    assert lookup.is_available is False
    assert lookup.result is None


def test_embedding_cache_stores_validated_json_without_raw_text() -> None:
    cache = FakeRedisEmbeddingCache()
    cache_key = build_embedding_cache_key(
        model_id=TEST_MODEL_ID,
        text="Private redacted document text.",
    )

    stored = store_cached_embedding(
        cache,
        cache_key=cache_key,
        result=make_embedding_result(),
        expected_model_id=TEST_MODEL_ID,
        expected_dimensions=TEST_DIMENSIONS,
    )

    assert stored is True
    assert len(cache.set_calls) == 1

    stored_key, stored_payload, stored_ttl = cache.set_calls[0]
    decoded_payload = json.loads(stored_payload)

    assert stored_key == cache_key
    assert stored_ttl == EMBEDDING_CACHE_TTL_SECONDS
    assert decoded_payload == {
        "input_text_token_count": 7,
        "model_id": TEST_MODEL_ID,
        "vector": [0.1, 0.2, 0.3, 0.4],
    }
    assert "Private redacted document text." not in stored_payload


def test_embedding_cache_write_failure_is_nonfatal() -> None:
    stored = store_cached_embedding(
        UnavailableRedisEmbeddingCache(),
        cache_key="embedding-cache-key",
        result=make_embedding_result(),
        expected_model_id=TEST_MODEL_ID,
        expected_dimensions=TEST_DIMENSIONS,
    )

    assert stored is False


def test_embedding_cache_rejects_a_mismatched_result_before_writing() -> None:
    cache = FakeRedisEmbeddingCache()
    mismatched_result = EmbeddingResult(
        vector=[0.1, 0.2, 0.3, 0.4],
        input_text_token_count=7,
        model_id="wrong-model",
    )

    with pytest.raises(ValueError, match="does not match"):
        store_cached_embedding(
            cache,
            cache_key="embedding-cache-key",
            result=mismatched_result,
            expected_model_id=TEST_MODEL_ID,
            expected_dimensions=TEST_DIMENSIONS,
        )

    assert cache.set_calls == []


def test_cached_provider_normalizes_a_miss_and_reuses_the_stored_result() -> None:
    cache = FakeRedisEmbeddingCache()
    provider = FakeEmbeddingProvider()
    cached_provider = CachedEmbeddingProvider(
        provider=provider,
        cache=cache,
        model_id=TEST_MODEL_ID,
        dimensions=TEST_DIMENSIONS,
    )

    first_result = cached_provider.embed("  Inspect\r\n the\tPostgreSQL   Pool.  ")
    second_result = cached_provider.embed("Inspect the PostgreSQL Pool.")

    expected_cache_key = build_embedding_cache_key(
        model_id=TEST_MODEL_ID,
        text="Inspect the PostgreSQL Pool.",
    )

    assert first_result == make_embedding_result(cache_status="MISS")
    assert second_result == make_embedding_result(cache_status="HIT")
    assert provider.texts == ["Inspect the PostgreSQL Pool."]
    assert cache.get_calls == [
        expected_cache_key,
        expected_cache_key,
    ]
    assert len(cache.set_calls) == 1


def test_cached_provider_fails_open_without_writing_after_a_read_failure() -> None:
    cache = ReadUnavailableRedisEmbeddingCache()
    provider = FakeEmbeddingProvider()
    cached_provider = CachedEmbeddingProvider(
        provider=provider,
        cache=cache,
        model_id=TEST_MODEL_ID,
        dimensions=TEST_DIMENSIONS,
    )

    result = cached_provider.embed("Inspect the PostgreSQL Pool.")

    assert result == make_embedding_result(cache_status="BYPASS")
    assert provider.texts == ["Inspect the PostgreSQL Pool."]
    assert cache.set_call_count == 0


def test_cached_provider_returns_the_result_when_cache_writing_fails() -> None:
    cache = WriteUnavailableRedisEmbeddingCache()
    provider = FakeEmbeddingProvider()
    cached_provider = CachedEmbeddingProvider(
        provider=provider,
        cache=cache,
        model_id=TEST_MODEL_ID,
        dimensions=TEST_DIMENSIONS,
    )

    result = cached_provider.embed("Inspect the PostgreSQL Pool.")

    assert result == make_embedding_result(cache_status="MISS")
    assert provider.texts == ["Inspect the PostgreSQL Pool."]


def test_cached_provider_replaces_a_malformed_cache_entry() -> None:
    cache = FakeRedisEmbeddingCache()
    provider = FakeEmbeddingProvider()
    cached_provider = CachedEmbeddingProvider(
        provider=provider,
        cache=cache,
        model_id=TEST_MODEL_ID,
        dimensions=TEST_DIMENSIONS,
    )
    cache_key = build_embedding_cache_key(
        model_id=TEST_MODEL_ID,
        text="Inspect the PostgreSQL Pool.",
    )
    cache.entries[cache_key] = "{invalid-json"

    result = cached_provider.embed("Inspect the PostgreSQL Pool.")

    assert result == make_embedding_result(cache_status="MISS")
    assert provider.texts == ["Inspect the PostgreSQL Pool."]
    assert len(cache.set_calls) == 1

    corrected_payload = json.loads(cache.entries[cache_key])
    assert corrected_payload["model_id"] == TEST_MODEL_ID
    assert corrected_payload["vector"] == [0.1, 0.2, 0.3, 0.4]


@pytest.mark.parametrize(
    "provider_result",
    [
        EmbeddingResult(
            vector=[0.1, 0.2, 0.3, 0.4],
            input_text_token_count=7,
            model_id="wrong-model",
        ),
        EmbeddingResult(
            vector=[0.1],
            input_text_token_count=7,
            model_id=TEST_MODEL_ID,
        ),
        EmbeddingResult(
            vector=[0.1, True, 0.3, 0.4],
            input_text_token_count=7,
            model_id=TEST_MODEL_ID,
        ),
        EmbeddingResult(
            vector=[0.1, float("nan"), 0.3, 0.4],
            input_text_token_count=7,
            model_id=TEST_MODEL_ID,
        ),
        EmbeddingResult(
            vector=[0.1, 0.2, 0.3, 0.4],
            input_text_token_count=-1,
            model_id=TEST_MODEL_ID,
        ),
    ],
)
def test_cached_provider_rejects_invalid_provider_results(
    provider_result: EmbeddingResult,
) -> None:
    cache = FakeRedisEmbeddingCache()
    provider = FakeEmbeddingProvider(result=provider_result)
    cached_provider = CachedEmbeddingProvider(
        provider=provider,
        cache=cache,
        model_id=TEST_MODEL_ID,
        dimensions=TEST_DIMENSIONS,
    )

    with pytest.raises(ValueError, match="does not match"):
        cached_provider.embed("Inspect the PostgreSQL Pool.")

    assert len(cache.set_calls) == 0


def test_cached_provider_rejects_empty_text_before_redis_or_provider() -> None:
    cache = FakeRedisEmbeddingCache()
    provider = FakeEmbeddingProvider()
    cached_provider = CachedEmbeddingProvider(
        provider=provider,
        cache=cache,
        model_id=TEST_MODEL_ID,
        dimensions=TEST_DIMENSIONS,
    )

    with pytest.raises(ValueError, match="must not be empty"):
        cached_provider.embed("   \r\n\t ")

    assert cache.get_calls == []
    assert provider.texts == []
