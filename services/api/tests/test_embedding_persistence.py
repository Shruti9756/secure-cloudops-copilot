from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.db.models import DocumentChunk, KnowledgeDocument
from app.services.embedding_persistence import embed_document_chunks
from app.services.embeddings import EmbeddingResult

TEST_EMBEDDING_DIMENSIONS = 1024


class FakeEmbeddingProvider:
    """Returns a deterministic vector without calling Ollama or Bedrock."""

    def __init__(self) -> None:
        self.texts: list[str] = []

    def embed(self, text: str) -> EmbeddingResult:
        self.texts.append(text)

        return EmbeddingResult(
            vector=[0.25] * TEST_EMBEDDING_DIMENSIONS,
            input_text_token_count=7,
            model_id="test-embedding-provider-v1",
        )


def make_document(
    *,
    ingestion_status: str = "chunked",
    chunk_count: int = 2,
) -> KnowledgeDocument:
    """Build an in-memory document and chunks for isolated service tests."""
    document = KnowledgeDocument(
        id=uuid4(),
        tenant_id=uuid4(),
        title="Checkout Runbook",
        source_path="runbooks/checkout-latency.md",
        source_sha256="a" * 64,
        content="Checkout latency investigation guidance.",
        ingestion_status=ingestion_status,
        document_metadata={},
    )
    document.chunks = [
        DocumentChunk(
            document_id=document.id,
            chunk_index=index,
            content=f"Chunk {index} about checkout latency.",
            content_sha256=f"{index:064x}",
            character_count=32,
            chunk_metadata={},
        )
        for index in range(chunk_count)
    ]

    return document


def test_embed_document_chunks_persists_missing_vectors() -> None:
    session = Mock()
    provider = FakeEmbeddingProvider()
    document = make_document()

    result = embed_document_chunks(
        session=session,
        document=document,
        provider=provider,
    )

    assert provider.texts == [
        "Chunk 0 about checkout latency.",
        "Chunk 1 about checkout latency.",
    ]
    assert result.embedded_chunk_count == 2
    assert result.skipped_chunk_count == 0
    assert result.total_input_tokens == 14
    assert document.ingestion_status == "embedded"
    assert all(chunk.embedding is not None for chunk in document.chunks)
    assert all(chunk.embedding_model == "test-embedding-provider-v1" for chunk in document.chunks)
    assert all(chunk.embedding_token_count == 7 for chunk in document.chunks)
    assert all(
        chunk.embedding_created_at is not None and chunk.embedding_created_at.tzinfo is UTC
        for chunk in document.chunks
    )
    session.flush.assert_called_once()


def test_embed_document_chunks_skips_existing_vectors_on_rerun() -> None:
    session = Mock()
    provider = FakeEmbeddingProvider()
    document = make_document()
    existing_chunk = document.chunks[0]
    existing_chunk.embedding = [0.5] * TEST_EMBEDDING_DIMENSIONS
    existing_chunk.embedding_model = "previous-provider-v1"
    existing_chunk.embedding_token_count = 3
    existing_chunk.embedding_created_at = datetime(2026, 8, 13, tzinfo=UTC)

    result = embed_document_chunks(
        session=session,
        document=document,
        provider=provider,
    )

    assert provider.texts == ["Chunk 1 about checkout latency."]
    assert result.embedded_chunk_count == 1
    assert result.skipped_chunk_count == 1
    assert result.total_input_tokens == 7
    assert existing_chunk.embedding_model == "previous-provider-v1"
    assert document.ingestion_status == "embedded"
    session.flush.assert_called_once()


def test_embed_document_chunks_requires_chunked_document() -> None:
    session = Mock()
    provider = FakeEmbeddingProvider()
    document = make_document(ingestion_status="pending")

    with pytest.raises(ValueError, match="must be chunked"):
        embed_document_chunks(
            session=session,
            document=document,
            provider=provider,
        )

    assert provider.texts == []
    session.flush.assert_not_called()


def test_embed_document_chunks_requires_at_least_one_chunk() -> None:
    session = Mock()
    provider = FakeEmbeddingProvider()
    document = make_document(chunk_count=0)

    with pytest.raises(ValueError, match="at least one chunk"):
        embed_document_chunks(
            session=session,
            document=document,
            provider=provider,
        )

    assert provider.texts == []
    session.flush.assert_not_called()
