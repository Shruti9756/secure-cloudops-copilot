from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.db.models import DocumentChunk, KnowledgeDocument
from app.services.embedding_persistence import embed_chunked_documents
from app.services.embeddings import EmbeddingResult

TEST_EMBEDDING_DIMENSIONS = 1024


class FakeEmbeddingProvider:
    """Returns test vectors and records which chunks the service sends to it."""

    def __init__(self) -> None:
        self.texts: list[str] = []

    def embed(self, text: str) -> EmbeddingResult:
        self.texts.append(text)

        return EmbeddingResult(
            vector=[0.25] * TEST_EMBEDDING_DIMENSIONS,
            input_text_token_count=7,
            model_id="test-embedding-provider-v1",
        )


def make_document(source_path: str) -> KnowledgeDocument:
    """Build one chunked document with two in-memory chunks."""
    document = KnowledgeDocument(
        id=uuid4(),
        tenant_id=uuid4(),
        title="Checkout Runbook",
        source_path=source_path,
        source_sha256="a" * 64,
        content="Checkout latency investigation guidance.",
        ingestion_status="chunked",
        document_metadata={},
    )
    document.chunks = [
        DocumentChunk(
            document_id=document.id,
            chunk_index=index,
            content=f"{source_path} chunk {index}",
            content_sha256=f"{index:064x}",
            character_count=32,
            chunk_metadata={},
        )
        for index in range(2)
    ]

    return document


def test_embed_chunked_documents_scopes_work_to_one_tenant_query() -> None:
    session = Mock()
    provider = FakeEmbeddingProvider()
    document = make_document("runbooks/checkout-latency.md")
    session.scalars.return_value = [document]

    results = embed_chunked_documents(
        session=session,
        tenant_slug="nimbuscart",
        provider=provider,
    )

    statement = session.scalars.call_args.args[0]
    statement_sql = str(statement)

    # The query includes both tenant isolation and the chunked-only status filter.
    assert "JOIN tenants" in statement_sql
    assert "tenants.slug" in statement_sql
    assert "knowledge_documents.ingestion_status" in statement_sql
    assert "ORDER BY knowledge_documents.source_path" in statement_sql

    assert len(results) == 1
    assert results[0].source_path == "runbooks/checkout-latency.md"
    assert provider.texts == [
        "runbooks/checkout-latency.md chunk 0",
        "runbooks/checkout-latency.md chunk 1",
    ]
    assert document.ingestion_status == "embedded"


def test_embed_chunked_documents_returns_empty_when_nothing_is_awaiting_embeddings() -> None:
    session = Mock()
    provider = FakeEmbeddingProvider()
    session.scalars.return_value = []

    results = embed_chunked_documents(
        session=session,
        tenant_slug="nimbuscart",
        provider=provider,
    )

    assert results == []
    assert provider.texts == []
    session.flush.assert_not_called()


def test_embed_chunked_documents_rejects_an_empty_tenant_slug_before_querying() -> None:
    session = Mock()
    provider = FakeEmbeddingProvider()

    with pytest.raises(ValueError, match="Tenant slug must not be empty"):
        embed_chunked_documents(
            session=session,
            tenant_slug="   ",
            provider=provider,
        )

    assert provider.texts == []
    session.scalars.assert_not_called()
