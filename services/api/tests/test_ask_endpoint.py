from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError

from app.db.models import Tenant
from app.main import (
    app,
    get_authorized_knowledge_tenant,
    get_chat_provider,
    get_current_principal,
    get_database_session,
    get_embedding_provider,
    get_redis_cache,
)
from app.services.authorization import AuthenticatedPrincipal
from app.services.citations import CitationValidationResult
from app.services.metrics import METRICS_REGISTRY
from app.services.rag import GroundedAnswer
from app.services.response_cache import build_ask_response_cache_key
from app.services.retrieval import RetrievedChunk
from app.services.safety import SafetyValidationResult

client = TestClient(app)


class FakeRedisCache:
    """In-memory Redis replacement for endpoint tests."""

    def __init__(
        self,
        *,
        rate_limit_result: object = (1, 60),
        rate_limit_error: Exception | None = None,
    ) -> None:
        self.entries: dict[str, str] = {}
        self.rate_limit_result = rate_limit_result
        self.rate_limit_error = rate_limit_error
        self.rate_limit_calls: list[tuple[str, int, tuple[str, ...]]] = []

    def get(self, name: str) -> str | None:
        return self.entries.get(name)

    def set(self, name: str, value: str, ex: int) -> bool:
        self.entries[name] = value
        return True

    def eval(
        self,
        script: str,
        numkeys: int,
        *keys_and_args: str,
    ) -> object:
        self.rate_limit_calls.append((script, numkeys, keys_and_args))

        if self.rate_limit_error is not None:
            raise self.rate_limit_error

        return self.rate_limit_result


def install_fake_dependencies(
    *,
    redis_cache: FakeRedisCache | None = None,
    database_session: Mock | None = None,
    tenant: Tenant | None = None,
) -> FakeRedisCache:
    """Make endpoint tests independent from PostgreSQL, Redis, and local Ollama."""
    cache = redis_cache or FakeRedisCache()

    if tenant is None:
        tenant = Tenant(
            id=uuid4(),
            organization_id=uuid4(),
            slug="nimbuscart",
            name="NimbusCart",
        )

    if database_session is None:
        database_session = Mock()
        database_session.scalar.return_value = tenant

    app.dependency_overrides[get_database_session] = lambda: database_session
    app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal(
        user_id=uuid4(),
        identity_subject="local-demo-admin",
        display_name="Local Demo Administrator",
    )
    # Endpoint tests focus on RAG behavior; authorization has separate tests.
    app.dependency_overrides[get_authorized_knowledge_tenant] = lambda: tenant
    app.dependency_overrides[get_redis_cache] = lambda: cache
    app.dependency_overrides[get_embedding_provider] = lambda: object()
    app.dependency_overrides[get_chat_provider] = lambda: object()

    return cache


def make_source() -> RetrievedChunk:
    """Create one safe source result without exposing vectors in the API test."""
    return RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        source_path="deployments/checkout-2.4.0.md",
        document_title="Deployment Record: checkout 2.4.0",
        content="The idle timeout changed from 120 seconds to 5 seconds.",
        chunk_index=0,
        cosine_distance=0.12,
    )


def make_grounded_answer() -> GroundedAnswer:
    """Create a valid internal RAG result for endpoint-response testing."""
    return GroundedAnswer(
        answer_text=(
            "The timeout change is a likely hypothesis "
            "[source: deployments/checkout-2.4.0.md#chunk-0]."
        ),
        embedding_model="test-embedding-model-v1",
        generation_model="test-chat-model-v1",
        query_input_token_count=10,
        prompt_token_count=50,
        completion_token_count=20,
        sources=(make_source(),),
        citation_validation=CitationValidationResult(
            is_valid=True,
            cited_source_identifiers=("deployments/checkout-2.4.0.md#chunk-0",),
            errors=(),
        ),
        safety_validation=SafetyValidationResult(
            is_safe=True,
            errors=(),
        ),
    )


def test_ask_endpoint_returns_a_grounded_server_scoped_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_arguments: dict[str, object] = {}

    def fake_answer_grounded_question(**kwargs: object) -> GroundedAnswer:
        captured_arguments.update(kwargs)
        return make_grounded_answer()

    install_fake_dependencies()
    monkeypatch.setattr("app.main.answer_grounded_question", fake_answer_grounded_question)

    try:
        response = client.post(
            "/api/v1/ask",
            json={
                "question": "Why did checkout latency increase?",
                "limit": 2,
            },
        )
    finally:
        # Always remove fakes so they cannot leak into another test.
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "status": "grounded",
        "answer": (
            "The timeout change is a likely hypothesis "
            "[source: deployments/checkout-2.4.0.md#chunk-0]."
        ),
        "tenant": "nimbuscart",
        "embedding_model": "test-embedding-model-v1",
        "generation_model": "test-chat-model-v1",
        "sources": [
            {
                "source_identifier": "deployments/checkout-2.4.0.md#chunk-0",
                "document_title": "Deployment Record: checkout 2.4.0",
                "cosine_distance": 0.12,
            }
        ],
        "citation_validation_passed": True,
        "citation_validation_errors": [],
        "safety_validation_passed": True,
        "safety_validation_errors": [],
        "query_input_tokens": 10,
        "prompt_tokens": 50,
        "completion_tokens": 20,
    }

    # The browser did not choose the tenant; the server enforced the demo tenant.
    assert captured_arguments["tenant_slug"] == "nimbuscart"
    assert captured_arguments["limit"] == 2


def test_ask_endpoint_records_a_bounded_grounded_rag_metric(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful request increments a metric without exposing its question."""
    labels = {
        "status": "grounded",
        "cache_status": "MISS",
    }
    metric_name = "secure_cloudops_rag_requests_total"
    before = METRICS_REGISTRY.get_sample_value(metric_name, labels=labels) or 0

    install_fake_dependencies()
    monkeypatch.setattr(
        "app.main.answer_grounded_question",
        lambda **_: make_grounded_answer(),
    )

    try:
        response = client.post(
            "/api/v1/ask",
            json={"question": "Why did checkout latency increase?"},
        )
    finally:
        app.dependency_overrides.clear()

    after = METRICS_REGISTRY.get_sample_value(metric_name, labels=labels) or 0

    assert response.status_code == 200
    assert response.headers["x-cache"] == "MISS"
    assert after == before + 1


def test_ask_endpoint_rejects_whitespace_question_before_rag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rag_call = Mock()
    install_fake_dependencies()
    monkeypatch.setattr("app.main.answer_grounded_question", rag_call)

    try:
        response = client.post(
            "/api/v1/ask",
            json={
                "question": "   ",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["detail"] == "Question must not be empty"
    rag_call.assert_not_called()


def test_ask_endpoint_returns_insufficient_evidence_without_a_chat_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_answer_grounded_question(**kwargs: object) -> GroundedAnswer:
        return GroundedAnswer(
            answer_text="I don't have enough evidence to answer safely.",
            embedding_model="test-embedding-model-v1",
            generation_model=None,
            query_input_token_count=8,
            prompt_token_count=None,
            completion_token_count=None,
            sources=(),
            citation_validation=None,
            safety_validation=None,
        )

    cache = install_fake_dependencies()
    monkeypatch.setattr("app.main.answer_grounded_question", fake_answer_grounded_question)

    try:
        response = client.post(
            "/api/v1/ask",
            json={
                "question": "What Kubernetes version is running?",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "insufficient_evidence"
    assert response.json()["generation_model"] is None
    assert response.json()["sources"] == []
    assert response.json()["citation_validation_passed"] is None
    assert response.json()["safety_validation_passed"] is None
    # Uncertain responses are deliberately never cached.
    assert cache.entries == {}


def test_ask_endpoint_returns_safe_status_for_invalid_citations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_answer_grounded_question(**kwargs: object) -> GroundedAnswer:
        return GroundedAnswer(
            answer_text="The generated answer did not pass citation validation.",
            embedding_model="test-embedding-model-v1",
            generation_model="test-chat-model-v1",
            query_input_token_count=8,
            prompt_token_count=40,
            completion_token_count=12,
            sources=(make_source(),),
            citation_validation=CitationValidationResult(
                is_valid=False,
                cited_source_identifiers=(),
                errors=("Answer must include at least one valid citation",),
            ),
            safety_validation=SafetyValidationResult(
                is_safe=True,
                errors=(),
            ),
        )

    install_fake_dependencies()
    monkeypatch.setattr("app.main.answer_grounded_question", fake_answer_grounded_question)

    try:
        response = client.post(
            "/api/v1/ask",
            json={
                "question": "Why did checkout latency increase?",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "citation_validation_failed"
    assert response.json()["citation_validation_passed"] is False
    assert response.json()["citation_validation_errors"] == [
        "Answer must include at least one valid citation"
    ]


def test_ask_endpoint_reuses_a_grounded_response_from_redis_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = FakeRedisCache()
    question = "Why did checkout latency increase?"
    rag_call = Mock(return_value=make_grounded_answer())

    install_fake_dependencies(redis_cache=cache)
    monkeypatch.setattr("app.main.answer_grounded_question", rag_call)

    try:
        first_response = client.post(
            "/api/v1/ask",
            json={"question": question, "limit": 2},
        )
        second_response = client.post(
            "/api/v1/ask",
            json={"question": question, "limit": 2},
        )
    finally:
        app.dependency_overrides.clear()

    expected_cache_key = build_ask_response_cache_key(
        tenant_slug="nimbuscart",
        question=question,
        limit=2,
    )

    assert first_response.status_code == 200
    assert first_response.headers["x-cache"] == "MISS"
    assert expected_cache_key in cache.entries

    assert second_response.status_code == 200
    assert second_response.headers["x-cache"] == "HIT"
    assert second_response.json() == first_response.json()

    # The second request used Redis and avoided a duplicate RAG/model call.
    rag_call.assert_called_once()


def test_ask_endpoint_rejects_requests_after_the_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = FakeRedisCache(rate_limit_result=(11, 23))
    rag_call = Mock()

    install_fake_dependencies(redis_cache=cache)
    monkeypatch.setattr("app.main.answer_grounded_question", rag_call)

    try:
        response = client.post(
            "/api/v1/ask",
            json={"question": "Why did checkout latency increase?"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 429
    assert response.json()["detail"] == (
        "Too many requests. Retry after the current rate-limit window."
    )
    assert response.headers["retry-after"] == "23"
    assert response.headers["x-ratelimit-limit"] == "10"
    assert response.headers["x-ratelimit-remaining"] == "0"
    assert response.headers["x-ratelimit-reset"] == "23"
    rag_call.assert_not_called()


def test_ask_endpoint_fails_closed_when_rate_limiting_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = FakeRedisCache(rate_limit_error=RedisConnectionError("Redis is unavailable"))
    rag_call = Mock()

    install_fake_dependencies(redis_cache=cache)
    monkeypatch.setattr("app.main.answer_grounded_question", rag_call)

    try:
        response = client.post(
            "/api/v1/ask",
            json={"question": "Why did checkout latency increase?"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Request protection is temporarily unavailable. Retry shortly."
    )
    assert response.headers["retry-after"] == "1"
    rag_call.assert_not_called()


def test_ask_endpoint_returns_safe_status_for_unsafe_model_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_answer_grounded_question(**kwargs: object) -> GroundedAnswer:
        return GroundedAnswer(
            answer_text=(
                "I couldn't safely return the generated response because it included an "
                "unsafe operational recommendation. Use the retrieved sources for "
                "read-only investigation guidance instead."
            ),
            embedding_model="test-embedding-model-v1",
            generation_model="test-chat-model-v1",
            query_input_token_count=8,
            prompt_token_count=40,
            completion_token_count=12,
            sources=(make_source(),),
            citation_validation=CitationValidationResult(
                is_valid=True,
                cited_source_identifiers=("deployments/checkout-2.4.0.md#chunk-0",),
                errors=(),
            ),
            safety_validation=SafetyValidationResult(
                is_safe=False,
                errors=("Answer must not recommend restarting production.",),
            ),
        )

    cache = install_fake_dependencies()
    monkeypatch.setattr("app.main.answer_grounded_question", fake_answer_grounded_question)

    try:
        response = client.post(
            "/api/v1/ask",
            json={"question": "What should I do next?"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "safety_validation_failed"
    assert response.json()["safety_validation_passed"] is False
    assert response.json()["safety_validation_errors"] == [
        "Answer must not recommend restarting production."
    ]
    # Unsafe model output must never be stored for later reuse.
    assert cache.entries == {}


def test_ask_endpoint_records_safe_audit_metadata_after_a_cache_miss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit_session = Mock()
    tenant = Tenant(
        id=uuid4(),
        slug="nimbuscart",
        name="NimbusCart",
    )

    install_fake_dependencies(
        database_session=audit_session,
        tenant=tenant,
    )
    monkeypatch.setattr(
        "app.main.answer_grounded_question",
        lambda **_: make_grounded_answer(),
    )

    try:
        response = client.post(
            "/api/v1/ask",
            json={
                "question": "Why did checkout latency increase?",
                "limit": 2,
            },
        )
    finally:
        app.dependency_overrides.clear()

    audit_event = audit_session.add.call_args.args[0]

    assert response.status_code == 200
    assert response.headers["x-cache"] == "MISS"
    assert audit_event.tenant_id == tenant.id
    assert audit_event.event_type == "rag.answer_completed"
    assert audit_event.outcome == "succeeded"
    assert audit_event.actor_type == "local_demo"
    assert audit_event.actor_id is None
    assert audit_event.request_id == response.headers["x-request-id"]
    assert audit_event.event_metadata == {
        "audit_status": "completed",
        "cache_status": "MISS",
        "response_status": "grounded",
        "source_count": 1,
        "embedding_model": "test-embedding-model-v1",
        "generation_model": "test-chat-model-v1",
        "citation_validation_passed": True,
        "safety_validation_passed": True,
        "rate_limit_remaining": 9,
    }
    assert "question" not in audit_event.event_metadata
    assert "answer" not in audit_event.event_metadata
    audit_session.commit.assert_called_once()


def test_ask_endpoint_audits_cache_hits_without_repeating_rag_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit_session = Mock()
    audit_session.scalar.return_value = Tenant(
        id=uuid4(),
        slug="nimbuscart",
        name="NimbusCart",
    )
    cache = FakeRedisCache()
    rag_call = Mock(return_value=make_grounded_answer())

    install_fake_dependencies(
        redis_cache=cache,
        database_session=audit_session,
    )
    monkeypatch.setattr("app.main.answer_grounded_question", rag_call)

    try:
        first_response = client.post(
            "/api/v1/ask",
            json={"question": "Why did checkout latency increase?", "limit": 2},
        )
        second_response = client.post(
            "/api/v1/ask",
            json={"question": "Why did checkout latency increase?", "limit": 2},
        )
    finally:
        app.dependency_overrides.clear()

    audit_events = [call.args[0] for call in audit_session.add.call_args_list]

    assert first_response.headers["x-cache"] == "MISS"
    assert second_response.headers["x-cache"] == "HIT"
    assert rag_call.call_count == 1
    assert len(audit_events) == 2
    assert [event.event_metadata["cache_status"] for event in audit_events] == [
        "MISS",
        "HIT",
    ]
    assert [event.event_metadata["audit_status"] for event in audit_events] == [
        "completed",
        "cache_hit",
    ]
    assert audit_session.commit.call_count == 2


def test_ask_endpoint_audits_rate_limit_denials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit_session = Mock()
    tenant = Tenant(
        id=uuid4(),
        slug="nimbuscart",
        name="NimbusCart",
    )

    cache = FakeRedisCache(rate_limit_result=(11, 23))
    rag_call = Mock()

    install_fake_dependencies(
        redis_cache=cache,
        database_session=audit_session,
        tenant=tenant,
    )
    monkeypatch.setattr("app.main.answer_grounded_question", rag_call)

    try:
        response = client.post(
            "/api/v1/ask",
            json={"question": "Why did checkout latency increase?"},
        )
    finally:
        app.dependency_overrides.clear()

    audit_event = audit_session.add.call_args.args[0]

    assert response.status_code == 429
    assert audit_event.tenant_id == tenant.id
    assert audit_event.event_type == "rag.answer_request"
    assert audit_event.outcome == "denied"
    assert audit_event.event_metadata["audit_status"] == "rate_limited"
    assert audit_event.event_metadata["cache_status"] is None
    assert audit_event.event_metadata["rate_limit_remaining"] == 0
    assert "question" not in audit_event.event_metadata
    rag_call.assert_not_called()
    audit_session.commit.assert_called_once()
