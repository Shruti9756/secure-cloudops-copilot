from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.services.retrieval import (
    EMBEDDING_DIMENSIONS,
    MAX_RETRIEVAL_COSINE_DISTANCE,
    RetrievedChunk,
    retrieve_relevant_chunks,
)

TEST_EMBEDDING_MODEL = "mxbai-embed-large"


def make_query_vector() -> list[float]:
    """Return a valid 1,024-dimension query vector for isolated tests."""
    return [0.25] * EMBEDDING_DIMENSIONS


def make_retrieval_row() -> SimpleNamespace:
    """Represent one database row returned by the retrieval SQL query."""
    return SimpleNamespace(
        chunk_id=uuid4(),
        document_id=uuid4(),
        source_path="runbooks/checkout-latency.md",
        document_title="Runbook: Checkout Latency Investigation",
        content="Check database connections after a checkout deployment.",
        chunk_index=1,
        cosine_distance=0.08,
    )


def test_retrieve_relevant_chunks_scopes_query_and_maps_results() -> None:
    session = Mock()
    row = make_retrieval_row()
    session.execute.return_value = [row]

    results = retrieve_relevant_chunks(
        session=session,
        tenant_slug="nimbuscart",
        query_vector=make_query_vector(),
        embedding_model=TEST_EMBEDDING_MODEL,
    )

    statement = session.execute.call_args.args[0]
    statement_sql = str(statement)

    # These SQL checks protect tenant and embedding-model isolation.
    assert "JOIN knowledge_documents" in statement_sql
    assert "JOIN tenants" in statement_sql
    assert "tenants.slug" in statement_sql
    assert "knowledge_documents.ingestion_status" in statement_sql
    assert "knowledge_documents.access_level" in statement_sql
    assert "document_chunks.embedding IS NOT NULL" in statement_sql
    assert "document_chunks.embedding_model" in statement_sql

    # pgvector renders cosine distance with the <=> operator.
    # The SQL query rejects weak semantic matches before returning RAG evidence.
    assert "<=" in statement_sql
    assert MAX_RETRIEVAL_COSINE_DISTANCE in statement.compile().params.values()

    assert results == [
        RetrievedChunk(
            chunk_id=row.chunk_id,
            document_id=row.document_id,
            source_path="runbooks/checkout-latency.md",
            document_title="Runbook: Checkout Latency Investigation",
            content="Check database connections after a checkout deployment.",
            chunk_index=1,
            cosine_distance=0.08,
        )
    ]


def test_retrieve_relevant_chunks_returns_empty_when_no_chunks_match() -> None:
    session = Mock()
    session.execute.return_value = []

    results = retrieve_relevant_chunks(
        session=session,
        tenant_slug="nimbuscart",
        query_vector=make_query_vector(),
        embedding_model=TEST_EMBEDDING_MODEL,
    )

    assert results == []


def test_retrieve_relevant_chunks_rejects_empty_tenant_before_querying() -> None:
    session = Mock()

    with pytest.raises(ValueError, match="Tenant slug must not be empty"):
        retrieve_relevant_chunks(
            session=session,
            tenant_slug="   ",
            query_vector=make_query_vector(),
            embedding_model=TEST_EMBEDDING_MODEL,
        )

    session.execute.assert_not_called()


def test_retrieve_relevant_chunks_rejects_wrong_vector_dimension() -> None:
    session = Mock()

    with pytest.raises(ValueError, match="exactly 1024 dimensions"):
        retrieve_relevant_chunks(
            session=session,
            tenant_slug="nimbuscart",
            query_vector=[0.25, 0.5],
            embedding_model=TEST_EMBEDDING_MODEL,
        )

    session.execute.assert_not_called()


def test_retrieve_relevant_chunks_rejects_invalid_limit_before_querying() -> None:
    session = Mock()

    with pytest.raises(TypeError, match="must be an integer"):
        retrieve_relevant_chunks(
            session=session,
            tenant_slug="nimbuscart",
            query_vector=make_query_vector(),
            embedding_model=TEST_EMBEDDING_MODEL,
            limit="three",  # type: ignore[arg-type]
        )

    session.execute.assert_not_called()


def test_retrieve_relevant_chunks_rejects_an_invalid_relevance_threshold() -> None:
    session = Mock()

    with pytest.raises(
        ValueError,
        match="Maximum cosine distance must be between 0 and 2",
    ):
        retrieve_relevant_chunks(
            session=session,
            tenant_slug="nimbuscart",
            query_vector=make_query_vector(),
            embedding_model=TEST_EMBEDDING_MODEL,
            max_cosine_distance=2.1,
        )

    session.execute.assert_not_called()


def test_retrieve_relevant_chunks_rejects_unknown_document_access_levels() -> None:
    session = Mock()

    with pytest.raises(ValueError, match="Document access levels must be supported"):
        retrieve_relevant_chunks(
            session=session,
            tenant_slug="nimbuscart",
            query_vector=make_query_vector(),
            embedding_model=TEST_EMBEDDING_MODEL,
            allowed_document_access_levels={"unexpected"},
        )

    session.execute.assert_not_called()
