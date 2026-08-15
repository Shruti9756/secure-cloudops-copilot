from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import (
    app,
    get_chat_provider,
    get_database_session,
    get_embedding_provider,
)
from app.services.citations import CitationValidationResult
from app.services.rag import GroundedAnswer
from app.services.retrieval import RetrievedChunk

client = TestClient(app)


def install_fake_dependencies() -> None:
    """Make endpoint tests independent from PostgreSQL and local Ollama."""
    app.dependency_overrides[get_database_session] = lambda: object()
    app.dependency_overrides[get_embedding_provider] = lambda: object()
    app.dependency_overrides[get_chat_provider] = lambda: object()


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
        "query_input_tokens": 10,
        "prompt_tokens": 50,
        "completion_tokens": 20,
    }

    # The browser did not choose the tenant; the server enforced the demo tenant.
    assert captured_arguments["tenant_slug"] == "nimbuscart"
    assert captured_arguments["limit"] == 2


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
        )

    install_fake_dependencies()
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
