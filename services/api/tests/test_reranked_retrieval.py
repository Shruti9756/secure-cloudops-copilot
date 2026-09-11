from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.services.hybrid_retrieval import HybridRetrievedChunk
from app.services.reranked_retrieval import (
    retrieve_reranked_hybrid_chunks,
)
from app.services.retrieval import EMBEDDING_DIMENSIONS


def make_hybrid_candidate(
    source_path: str,
    document_title: str,
    content: str,
    rrf_score: float,
) -> HybridRetrievedChunk:
    """Create one synthetic hybrid candidate."""

    return HybridRetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        source_path=source_path,
        document_title=document_title,
        content=content,
        chunk_index=0,
        semantic_cosine_distance=0.1,
        bm25_score=1.0,
        rrf_score=rrf_score,
        semantic_rank=1,
        lexical_rank=1,
    )


def test_reranked_retrieval_promotes_exact_version_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock()
    query_vector = [0.25] * EMBEDDING_DIMENSIONS
    hybrid_retrieval = Mock(
        return_value=[
            make_hybrid_candidate(
                "deployments/checkout-2.4.0.md",
                "Deployment Record: checkout 2.4.0",
                "Changed the PostgreSQL idle timeout to 5 seconds.",
                0.0330,
            ),
            make_hybrid_candidate(
                "deployments/checkout-2.4.1.md",
                "Deployment Record: checkout 2.4.1",
                "Restored the PostgreSQL idle timeout to 120 seconds.",
                0.0328,
            ),
        ]
    )
    monkeypatch.setattr(
        "app.services.reranked_retrieval.retrieve_hybrid_chunks",
        hybrid_retrieval,
    )

    results = retrieve_reranked_hybrid_chunks(
        session=session,
        tenant_slug="nimbuscart",
        query="Which idle timeout did checkout version 2.4.1 restore?",
        query_vector=query_vector,
        embedding_model="mxbai-embed-large",
        limit=1,
    )

    assert results[0].source_path == "deployments/checkout-2.4.1.md"
    hybrid_retrieval.assert_called_once_with(
        session=session,
        tenant_slug="nimbuscart",
        query="Which idle timeout did checkout version 2.4.1 restore?",
        query_vector=query_vector,
        embedding_model="mxbai-embed-large",
        allowed_document_access_levels=frozenset({"organization"}),
        limit=3,
    )


def test_reranked_retrieval_returns_no_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.reranked_retrieval.retrieve_hybrid_chunks",
        Mock(return_value=[]),
    )

    results = retrieve_reranked_hybrid_chunks(
        session=Mock(),
        tenant_slug="nimbuscart",
        query="checkout latency",
        query_vector=[0.25] * EMBEDDING_DIMENSIONS,
        embedding_model="mxbai-embed-large",
    )

    assert results == []


def test_reranked_retrieval_rejects_invalid_limit() -> None:
    with pytest.raises(
        ValueError,
        match="Retrieval limit must be between 1 and 10",
    ):
        retrieve_reranked_hybrid_chunks(
            session=Mock(),
            tenant_slug="nimbuscart",
            query="checkout latency",
            query_vector=[0.25] * EMBEDDING_DIMENSIONS,
            embedding_model="mxbai-embed-large",
            limit=0,
        )
