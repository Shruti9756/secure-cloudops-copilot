import json

from redis.exceptions import ConnectionError as RedisConnectionError

from app.infrastructure.ollama_chat import OLLAMA_QWEN3_4B_INSTRUCT_MODEL_ID
from app.services.document_access import (
    ALL_DOCUMENT_ACCESS_LEVELS,
    DEFAULT_DOCUMENT_ACCESS_LEVELS,
)
from app.services.response_cache import (
    ASK_RESPONSE_CACHE_TTL_SECONDS,
    CacheLookup,
    build_ask_response_cache_key,
    load_cached_response,
    store_cached_response,
)


class FakeRedisCache:
    """Small in-memory stand-in that makes cache tests independent from Docker."""

    def __init__(self) -> None:
        self.entries: dict[str, str] = {}
        self.set_calls: list[tuple[str, str, int]] = []

    def get(self, name: str) -> str | None:
        return self.entries.get(name)

    def set(self, name: str, value: str, ex: int) -> bool:
        self.entries[name] = value
        self.set_calls.append((name, value, ex))
        return True


class UnavailableRedisCache:
    """Simulate Redis being temporarily unavailable during one API request."""

    def get(self, name: str) -> str | None:
        raise RedisConnectionError("Redis is unavailable")

    def set(self, name: str, value: str, ex: int) -> bool:
        raise RedisConnectionError("Redis is unavailable")


def test_cache_key_is_tenant_revision_and_access_scoped() -> None:
    question = "  Why DID checkout latency increase?  "

    cache_key = build_ask_response_cache_key(
        tenant_slug="nimbuscart",
        knowledge_revision=7,
        document_access_levels=DEFAULT_DOCUMENT_ACCESS_LEVELS,
        question=question,
        limit=2,
        chat_provider="ollama",
        chat_model_id=OLLAMA_QWEN3_4B_INSTRUCT_MODEL_ID,
    )
    equivalent_cache_key = build_ask_response_cache_key(
        tenant_slug="nimbuscart",
        knowledge_revision=7,
        document_access_levels=DEFAULT_DOCUMENT_ACCESS_LEVELS,
        question="why did checkout latency increase?",
        limit=2,
        chat_provider="ollama",
        chat_model_id=OLLAMA_QWEN3_4B_INSTRUCT_MODEL_ID,
    )
    other_tenant_cache_key = build_ask_response_cache_key(
        tenant_slug="other-tenant",
        knowledge_revision=7,
        document_access_levels=DEFAULT_DOCUMENT_ACCESS_LEVELS,
        question=question,
        limit=2,
        chat_provider="ollama",
        chat_model_id=OLLAMA_QWEN3_4B_INSTRUCT_MODEL_ID,
    )
    privileged_cache_key = build_ask_response_cache_key(
        tenant_slug="nimbuscart",
        knowledge_revision=7,
        document_access_levels=ALL_DOCUMENT_ACCESS_LEVELS,
        question=question,
        limit=2,
        chat_provider="ollama",
        chat_model_id=OLLAMA_QWEN3_4B_INSTRUCT_MODEL_ID,
    )
    new_revision_cache_key = build_ask_response_cache_key(
        tenant_slug="nimbuscart",
        knowledge_revision=8,
        document_access_levels=DEFAULT_DOCUMENT_ACCESS_LEVELS,
        question=question,
        limit=2,
        chat_provider="ollama",
        chat_model_id=OLLAMA_QWEN3_4B_INSTRUCT_MODEL_ID,
    )
    bedrock_cache_key = build_ask_response_cache_key(
        tenant_slug="nimbuscart",
        knowledge_revision=7,
        document_access_levels=DEFAULT_DOCUMENT_ACCESS_LEVELS,
        question=question,
        limit=2,
        chat_provider="ollama",
        chat_model_id=OLLAMA_QWEN3_4B_INSTRUCT_MODEL_ID,
        embedding_provider="bedrock",
    )

    assert cache_key == equivalent_cache_key
    assert cache_key != other_tenant_cache_key
    assert cache_key != privileged_cache_key
    assert cache_key != new_revision_cache_key
    assert cache_key != bedrock_cache_key
    assert question not in cache_key
    assert "securecloudops:ask:v6:nimbuscart:7:" in cache_key


def test_cache_key_separates_chat_providers_and_models() -> None:
    def key_for(chat_provider: str, chat_model_id: str) -> str:
        return build_ask_response_cache_key(
            tenant_slug="nimbuscart",
            knowledge_revision=7,
            document_access_levels=DEFAULT_DOCUMENT_ACCESS_LEVELS,
            question="Why did checkout latency increase?",
            limit=2,
            chat_provider=chat_provider,
            chat_model_id=chat_model_id,
        )

    ollama_key = key_for("ollama", OLLAMA_QWEN3_4B_INSTRUCT_MODEL_ID)
    bedrock_model_a_key = key_for("bedrock", "test-model-a")
    bedrock_model_b_key = key_for("bedrock", "test-model-b")
    ollama_model_a_key = key_for("ollama", "test-model-a")

    assert ollama_key != bedrock_model_a_key
    assert bedrock_model_a_key != bedrock_model_b_key
    assert ollama_model_a_key != bedrock_model_a_key
    assert "test-model-a" not in bedrock_model_a_key


def test_load_cached_response_returns_valid_json_payload() -> None:
    cache = FakeRedisCache()
    cache.entries["cache-key"] = json.dumps(
        {
            "status": "grounded",
            "answer": "Investigate the database connection pool.",
        }
    )

    result = load_cached_response(cache, cache_key="cache-key")

    assert result == CacheLookup(
        payload={
            "status": "grounded",
            "answer": "Investigate the database connection pool.",
        },
        is_available=True,
    )


def test_load_cached_response_returns_a_miss_for_an_absent_key() -> None:
    result = load_cached_response(FakeRedisCache(), cache_key="missing-key")

    assert result == CacheLookup(payload=None, is_available=True)


def test_load_cached_response_treats_malformed_json_as_a_miss() -> None:
    cache = FakeRedisCache()
    cache.entries["cache-key"] = "not valid JSON"

    result = load_cached_response(cache, cache_key="cache-key")

    assert result == CacheLookup(payload=None, is_available=True)


def test_load_cached_response_reports_when_redis_is_unavailable() -> None:
    result = load_cached_response(UnavailableRedisCache(), cache_key="cache-key")

    assert result == CacheLookup(payload=None, is_available=False)


def test_store_cached_response_serializes_payload_with_the_expected_ttl() -> None:
    cache = FakeRedisCache()
    payload = {
        "status": "grounded",
        "answer": "Investigate the database connection pool.",
    }

    was_stored = store_cached_response(
        cache,
        cache_key="cache-key",
        payload=payload,
    )

    assert was_stored is True
    assert json.loads(cache.entries["cache-key"]) == payload
    assert cache.set_calls[0][0] == "cache-key"
    assert cache.set_calls[0][2] == ASK_RESPONSE_CACHE_TTL_SECONDS
