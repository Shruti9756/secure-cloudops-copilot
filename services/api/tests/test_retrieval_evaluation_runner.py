from collections.abc import Sequence
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.services.embeddings import EmbeddingResult
from app.services.retrieval import RetrievedChunk
from app.services.retrieval_evaluation_runner import (
    RetrievalEvaluationCase,
    run_retrieval_evaluation,
)


class FakeEmbeddingProvider:
    """Return deterministic vectors so this unit test never calls Ollama."""

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
    """Create minimal synthetic evidence returned by the mocked retriever."""

    return RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        source_path=source_path,
        document_title="Synthetic evaluation document",
        content="Synthetic evaluation content.",
        chunk_index=chunk_index,
        cosine_distance=0.1,
    )


def test_run_retrieval_evaluation_aggregates_real_retrieval_measurements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock()
    embedding_provider = FakeEmbeddingProvider()

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
    assert report.requested_k == 3
    assert report.total_query_input_tokens == 6
    assert report.mean_precision_at_k == pytest.approx(1 / 3)
    assert report.mean_recall_at_k == pytest.approx(0.75)

    assert report.case_results[0].matched_source_identifiers == ("deployments/checkout.md#chunk-0",)
    assert report.case_results[1].matched_source_identifiers == ("runbooks/checkout.md#chunk-1",)


def test_run_retrieval_evaluation_rejects_an_empty_case_list() -> None:
    with pytest.raises(ValueError, match="At least one evaluation case is required"):
        run_retrieval_evaluation(
            session=Mock(),
            cases=(),
            embedding_provider=FakeEmbeddingProvider(),
        )
