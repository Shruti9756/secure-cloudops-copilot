from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pytest

from app.services.chunking import ChunkingResult
from app.services.embedding_persistence import DocumentEmbeddingResult
from app.worker import (
    ProcessingCycleResult,
    process_one_cycle,
    process_tenant_documents,
)


def test_process_tenant_documents_chunks_then_embeds_one_tenant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock()
    provider = Mock()

    chunking_results = [
        ChunkingResult(
            document_id=uuid4(),
            source_path="uploads/worker-demo.md",
            chunk_count=2,
        )
    ]
    embedding_results = [
        DocumentEmbeddingResult(
            document_id=uuid4(),
            source_path="uploads/worker-demo.md",
            embedded_chunk_count=2,
            skipped_chunk_count=0,
            total_input_tokens=42,
        )
    ]

    chunk_documents = Mock(return_value=chunking_results)
    embed_documents = Mock(return_value=embedding_results)
    monkeypatch.setattr("app.worker.chunk_pending_documents", chunk_documents)
    monkeypatch.setattr("app.worker.embed_chunked_documents", embed_documents)

    result = process_tenant_documents(
        session=session,
        tenant_slug=" nimbuscart ",
        provider=provider,
    )

    assert result == ProcessingCycleResult(
        chunked_documents=1,
        chunks_created=2,
        embedded_documents=1,
        embedded_chunks=2,
        skipped_chunks=0,
        input_tokens=42,
    )
    session.flush.assert_called_once_with()
    chunk_documents.assert_called_once_with(
        session=session,
        tenant_slug="nimbuscart",
    )
    embed_documents.assert_called_once_with(
        session=session,
        tenant_slug="nimbuscart",
        provider=provider,
    )


def test_process_tenant_documents_rejects_an_empty_tenant_before_database_work() -> None:
    with pytest.raises(
        ValueError,
        match="Document processor tenant slug must not be empty",
    ):
        process_tenant_documents(
            session=Mock(),
            tenant_slug="   ",
            provider=Mock(),
        )


def test_process_one_cycle_uses_one_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock()
    session_factory = MagicMock()
    session_factory.begin.return_value.__enter__.return_value = session
    provider = Mock()
    expected_result = ProcessingCycleResult(
        chunked_documents=1,
        chunks_created=2,
        embedded_documents=1,
        embedded_chunks=2,
        skipped_chunks=0,
        input_tokens=42,
    )
    process_documents = Mock(return_value=expected_result)
    monkeypatch.setattr("app.worker.process_tenant_documents", process_documents)

    result = process_one_cycle(
        session_factory=session_factory,
        tenant_slug="nimbuscart",
        provider=provider,
    )

    assert result == expected_result
    session_factory.begin.assert_called_once_with()
    process_documents.assert_called_once_with(
        session=session,
        tenant_slug="nimbuscart",
        provider=provider,
    )
