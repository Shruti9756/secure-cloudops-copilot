from collections.abc import Sequence
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.services.embeddings import EmbeddingResult
from app.services.hybrid_retrieval import HybridRetrievedChunk
from app.services.lexical_retrieval import LexicalRetrievedChunk
from app.services.retrieval import RetrievedChunk
from app.services.retrieval_evaluation_runner import (
    RetrievalEvaluationCase,
    run_retrieval_evaluation,
)


class FakeEmbeddingProvider:
    """Return deterministic vectors so unit tests never call Ollama."""

    def __init__(self) -> None:
        self.texts: list[str] = []

    def embed(self, text: str) -> EmbeddingResult:
        self.texts.append(text)

        vector = [0.0] * 1024
        vector[0] = float(len(self.texts))

        return EmbeddingResult(
            vector=vector,
            input_text_token_count=3,
            model_id="mxbai-embed-large",
        )


def make_retrieved_chunk(source_path: str, chunk_index: int) -> RetrievedChunk:
    """Create minimal synthetic semantic evidence."""

    return RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        source_path=source_path,
        document_title="Synthetic evaluation document",
        content="Synthetic evaluation content.",
        chunk_index=chunk_index,
        cosine_distance=0.1,
    )


def make_lexical_chunk(source_path: str, chunk_index: int) -> LexicalRetrievedChunk:
    """Create minimal synthetic BM25 evidence."""

    return LexicalRetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        source_path=source_path,
        document_title="Synthetic evaluation document",
        content="Synthetic evaluation content.",
        chunk_index=chunk_index,
        bm25_score=1.2,
    )


def make_hybrid_chunk(source_path: str, chunk_index: int) -> HybridRetrievedChunk:
    """Create minimal synthetic hybrid evidence."""

    return HybridRetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        source_path=source_path,
        document_title="Synthetic evaluation document",
        content="Synthetic evaluation content.",
        chunk_index=chunk_index,
        semantic_cosine_distance=0.1,
        bm25_score=1.2,
        rrf_score=0.03,
        semantic_rank=1,
        lexical_rank=1,
    )


def test_run_retrieval_evaluation_aggregates_semantic_measurements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock()
    embedding_provider = FakeEmbeddingProvider()
    clock = Mock(
        side_effect=(
            10.000,
            10.025,
            20.000,
            20.075,
        )
    )
    monkeypatch.setattr(
        "app.services.retrieval_evaluation_runner.perf_counter",
        clock,
    )

    cases = (
        RetrievalEvaluationCase(
            case_id="RET-EVAL-001",
            category="deployment",
            tenant_slug="nimbuscart",
            question="What changed in the deployment?",
            expected_source_identifiers=("deployments/checkout.md#chunk-0",),
        ),
        RetrievalEvaluationCase(
            case_id="RET-EVAL-002",
            category="runbook",
            tenant_slug="nimbuscart",
            question="When should the runbook be used?",
            expected_source_identifiers=(
                "runbooks/checkout.md#chunk-0",
                "runbooks/checkout.md#chunk-1",
            ),
        ),
    )

    retrieved_by_query_index = {
        1: [make_retrieved_chunk("deployments/checkout.md", 0)],
        2: [
            make_retrieved_chunk("company-overview.md", 0),
            make_retrieved_chunk("runbooks/checkout.md", 1),
        ],
    }

    def fake_retrieve_relevant_chunks(
        *,
        session: object,
        tenant_slug: str,
        query_vector: Sequence[float],
        embedding_model: str,
        limit: int,
    ) -> list[RetrievedChunk]:
        assert session is not None
        assert tenant_slug == "nimbuscart"
        assert embedding_model == "mxbai-embed-large"
        assert limit == 3

        return retrieved_by_query_index[int(query_vector[0])]

    monkeypatch.setattr(
        "app.services.retrieval_evaluation_runner.retrieve_relevant_chunks",
        fake_retrieve_relevant_chunks,
    )

    report = run_retrieval_evaluation(
        session=session,
        cases=cases,
        embedding_provider=embedding_provider,
        limit=3,
    )

    assert embedding_provider.texts == [
        "What changed in the deployment?",
        "When should the runbook be used?",
    ]
    assert report.retrieval_strategy == "semantic"
    assert report.requested_k == 3
    assert report.total_query_input_tokens == 6
    assert report.mean_precision_at_k == pytest.approx(1 / 3)
    assert report.mean_recall_at_k == pytest.approx(0.75)
    assert report.case_results[0].matched_source_identifiers == ("deployments/checkout.md#chunk-0",)
    assert report.case_results[1].matched_source_identifiers == ("runbooks/checkout.md#chunk-1",)
    assert report.case_results[0].retrieval_duration_ms == pytest.approx(25.0)
    assert report.case_results[1].retrieval_duration_ms == pytest.approx(75.0)
    assert report.mean_retrieval_duration_ms == pytest.approx(50.0)
    assert report.p50_retrieval_duration_ms == pytest.approx(50.0)
    assert report.p95_retrieval_duration_ms == pytest.approx(72.5)


def test_run_retrieval_evaluation_uses_lexical_search_without_embedding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock()
    embedding_provider = FakeEmbeddingProvider()
    lexical_retrieval = Mock(return_value=[make_lexical_chunk("runbooks/checkout.md", 1)])
    monkeypatch.setattr(
        "app.services.retrieval_evaluation_runner.retrieve_lexical_chunks",
        lexical_retrieval,
    )

    report = run_retrieval_evaluation(
        session=session,
        cases=(
            RetrievalEvaluationCase(
                case_id="RET-EVAL-LEXICAL",
                category="runbook",
                tenant_slug="nimbuscart",
                question="What should Redis eviction investigate?",
                expected_source_identifiers=("runbooks/checkout.md#chunk-1",),
            ),
        ),
        embedding_provider=embedding_provider,
        strategy="lexical",
        limit=3,
    )

    assert embedding_provider.texts == []
    assert report.retrieval_strategy == "lexical"
    assert report.total_query_input_tokens == 0
    assert report.case_results[0].embedding_model is None
    assert report.case_results[0].recall_at_k == 1.0
    lexical_retrieval.assert_called_once_with(
        session=session,
        tenant_slug="nimbuscart",
        query="What should Redis eviction investigate?",
        limit=3,
    )


def test_run_retrieval_evaluation_uses_hybrid_search_after_embedding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock()
    embedding_provider = FakeEmbeddingProvider()
    hybrid_retrieval = Mock(return_value=[make_hybrid_chunk("deployments/checkout.md", 0)])
    monkeypatch.setattr(
        "app.services.retrieval_evaluation_runner.retrieve_hybrid_chunks",
        hybrid_retrieval,
    )

    report = run_retrieval_evaluation(
        session=session,
        cases=(
            RetrievalEvaluationCase(
                case_id="RET-EVAL-HYBRID",
                category="deployment",
                tenant_slug="nimbuscart",
                question="What changed in checkout?",
                expected_source_identifiers=("deployments/checkout.md#chunk-0",),
            ),
        ),
        embedding_provider=embedding_provider,
        strategy="hybrid",
        limit=3,
    )

    assert embedding_provider.texts == ["What changed in checkout?"]
    assert report.retrieval_strategy == "hybrid"
    assert report.total_query_input_tokens == 3
    assert report.case_results[0].embedding_model == "mxbai-embed-large"
    assert report.case_results[0].recall_at_k == 1.0
    hybrid_retrieval.assert_called_once_with(
        session=session,
        tenant_slug="nimbuscart",
        query="What changed in checkout?",
        query_vector=[1.0] + [0.0] * 1023,
        embedding_model="mxbai-embed-large",
        limit=3,
    )


def test_run_retrieval_evaluation_uses_reranked_hybrid_search_after_embedding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock()
    embedding_provider = FakeEmbeddingProvider()
    reranked_retrieval = Mock(return_value=[make_hybrid_chunk("deployments/checkout.md", 0)])
    monkeypatch.setattr(
        "app.services.retrieval_evaluation_runner.retrieve_reranked_hybrid_chunks",
        reranked_retrieval,
    )

    report = run_retrieval_evaluation(
        session=session,
        cases=(
            RetrievalEvaluationCase(
                case_id="RET-EVAL-RERANKED",
                category="deployment",
                tenant_slug="nimbuscart",
                question="What changed in checkout?",
                expected_source_identifiers=("deployments/checkout.md#chunk-0",),
            ),
        ),
        embedding_provider=embedding_provider,
        strategy="hybrid-reranked",
        limit=3,
    )

    assert embedding_provider.texts == ["What changed in checkout?"]
    assert report.retrieval_strategy == "hybrid-reranked"
    assert report.total_query_input_tokens == 3
    assert report.case_results[0].embedding_model == "mxbai-embed-large"
    assert report.case_results[0].recall_at_k == 1.0
    reranked_retrieval.assert_called_once_with(
        session=session,
        tenant_slug="nimbuscart",
        query="What changed in checkout?",
        query_vector=[1.0] + [0.0] * 1023,
        embedding_model="mxbai-embed-large",
        limit=3,
    )


def test_run_retrieval_evaluation_rejects_an_unknown_strategy() -> None:
    with pytest.raises(
        ValueError,
        match="Retrieval strategy must be semantic, lexical, hybrid, or hybrid-reranked",
    ):
        run_retrieval_evaluation(
            session=Mock(),
            cases=(
                RetrievalEvaluationCase(
                    case_id="RET-EVAL-INVALID",
                    category="test",
                    tenant_slug="nimbuscart",
                    question="Test question",
                    expected_source_identifiers=("test.md#chunk-0",),
                ),
            ),
            embedding_provider=FakeEmbeddingProvider(),
            strategy="unsupported",  # type: ignore[arg-type]
        )


def test_run_retrieval_evaluation_rejects_an_empty_case_list() -> None:
    with pytest.raises(ValueError, match="At least one evaluation case is required"):
        run_retrieval_evaluation(
            session=Mock(),
            cases=(),
            embedding_provider=FakeEmbeddingProvider(),
        )
