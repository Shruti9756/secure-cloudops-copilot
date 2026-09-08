from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.services.hybrid_retrieval import retrieve_hybrid_chunks
from app.services.lexical_retrieval import LexicalRetrievedChunk
from app.services.retrieval import EMBEDDING_DIMENSIONS, RetrievedChunk


def make_semantic_chunk(
    source_path: str,
    chunk_index: int,
    cosine_distance: float,
) -> RetrievedChunk:
    """Create one synthetic semantic result."""

    return RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        source_path=source_path,
        document_title="Synthetic document",
        content=f"{source_path} chunk {chunk_index}",
        chunk_index=chunk_index,
        cosine_distance=cosine_distance,
    )


def make_lexical_chunk(
    source_path: str,
    chunk_index: int,
    bm25_score: float,
) -> LexicalRetrievedChunk:
    """Create one synthetic BM25 result."""

    return LexicalRetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        source_path=source_path,
        document_title="Synthetic document",
        content=f"{source_path} chunk {chunk_index}",
        chunk_index=chunk_index,
        bm25_score=bm25_score,
    )


def make_query_vector() -> list[float]:
    """Return a valid vector shape for the semantic retrieval contract."""

    return [0.25] * EMBEDDING_DIMENSIONS


def test_hybrid_retrieval_fuses_semantic_and_lexical_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock()
    semantic_chunks = [
        make_semantic_chunk("runbooks/checkout.md", 0, 0.08),
        make_semantic_chunk("deployments/checkout.md", 0, 0.12),
    ]
    lexical_chunks = [
        make_lexical_chunk("runbooks/checkout.md", 0, 2.4),
        make_lexical_chunk("company-overview.md", 0, 1.8),
    ]

    semantic_retrieval = Mock(return_value=semantic_chunks)
    lexical_retrieval = Mock(return_value=lexical_chunks)
    monkeypatch.setattr(
        "app.services.hybrid_retrieval.retrieve_relevant_chunks",
        semantic_retrieval,
    )
    monkeypatch.setattr(
        "app.services.hybrid_retrieval.retrieve_lexical_chunks",
        lexical_retrieval,
    )

    results = retrieve_hybrid_chunks(
        session=session,
        tenant_slug="nimbuscart",
        query="checkout incident",
        query_vector=make_query_vector(),
        embedding_model="mxbai-embed-large",
        limit=3,
    )

    semantic_retrieval.assert_called_once_with(
        session=session,
        tenant_slug="nimbuscart",
        query_vector=make_query_vector(),
        embedding_model="mxbai-embed-large",
        allowed_document_access_levels=frozenset({"organization"}),
        limit=9,
    )
    lexical_retrieval.assert_called_once_with(
        session=session,
        tenant_slug="nimbuscart",
        query="checkout incident",
        allowed_document_access_levels=frozenset({"organization"}),
        limit=9,
    )

    assert [result.source_path for result in results] == [
        "runbooks/checkout.md",
        "deployments/checkout.md",
        "company-overview.md",
    ]

    shared_result = results[0]
    assert shared_result.semantic_cosine_distance == 0.08
    assert shared_result.bm25_score == 2.4
    assert shared_result.semantic_rank == 1
    assert shared_result.lexical_rank == 1

    semantic_only_result = results[1]
    assert semantic_only_result.semantic_cosine_distance == 0.12
    assert semantic_only_result.bm25_score is None

    lexical_only_result = results[2]
    assert lexical_only_result.semantic_cosine_distance is None
    assert lexical_only_result.bm25_score == 1.8


def test_hybrid_retrieval_rejects_an_empty_tenant_before_calling_retrievers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    semantic_retrieval = Mock()
    lexical_retrieval = Mock()
    monkeypatch.setattr(
        "app.services.hybrid_retrieval.retrieve_relevant_chunks",
        semantic_retrieval,
    )
    monkeypatch.setattr(
        "app.services.hybrid_retrieval.retrieve_lexical_chunks",
        lexical_retrieval,
    )

    with pytest.raises(ValueError, match="Tenant slug must not be empty"):
        retrieve_hybrid_chunks(
            session=Mock(),
            tenant_slug="   ",
            query="checkout incident",
            query_vector=make_query_vector(),
            embedding_model="mxbai-embed-large",
        )

    semantic_retrieval.assert_not_called()
    lexical_retrieval.assert_not_called()


def test_hybrid_retrieval_rejects_an_unsearchable_query_before_calling_retrievers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    semantic_retrieval = Mock()
    lexical_retrieval = Mock()
    monkeypatch.setattr(
        "app.services.hybrid_retrieval.retrieve_relevant_chunks",
        semantic_retrieval,
    )
    monkeypatch.setattr(
        "app.services.hybrid_retrieval.retrieve_lexical_chunks",
        lexical_retrieval,
    )

    with pytest.raises(
        ValueError,
        match="Hybrid retrieval query must contain at least one searchable term",
    ):
        retrieve_hybrid_chunks(
            session=Mock(),
            tenant_slug="nimbuscart",
            query="!!!",
            query_vector=make_query_vector(),
            embedding_model="mxbai-embed-large",
        )

    semantic_retrieval.assert_not_called()
    lexical_retrieval.assert_not_called()


def test_hybrid_retrieval_rejects_invalid_access_levels_before_calling_retrievers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    semantic_retrieval = Mock()
    lexical_retrieval = Mock()
    monkeypatch.setattr(
        "app.services.hybrid_retrieval.retrieve_relevant_chunks",
        semantic_retrieval,
    )
    monkeypatch.setattr(
        "app.services.hybrid_retrieval.retrieve_lexical_chunks",
        lexical_retrieval,
    )

    with pytest.raises(ValueError, match="Document access levels must be supported"):
        retrieve_hybrid_chunks(
            session=Mock(),
            tenant_slug="nimbuscart",
            query="checkout incident",
            query_vector=make_query_vector(),
            embedding_model="mxbai-embed-large",
            allowed_document_access_levels={"unsupported"},  # type: ignore[arg-type]
        )

    semantic_retrieval.assert_not_called()
    lexical_retrieval.assert_not_called()
