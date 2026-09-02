from unittest.mock import MagicMock, Mock, call
from uuid import uuid4

import pytest

from app.services.chunking import ChunkingResult
from app.services.embedding_persistence import DocumentEmbeddingResult
from app.worker import (
    ProcessingCycleResult,
    list_tenant_slugs_requiring_processing,
    process_all_tenant_documents,
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


def test_list_tenant_slugs_requiring_processing_returns_only_working_tenants() -> None:
    session = Mock()
    session.scalars.return_value = ["nimbuscart", "skyforge"]

    tenant_slugs = list_tenant_slugs_requiring_processing(session)

    statement_sql = str(session.scalars.call_args.args[0])

    assert tenant_slugs == ["nimbuscart", "skyforge"]
    assert "tenants.slug" in statement_sql
    assert "knowledge_documents.ingestion_status" in statement_sql


def test_process_all_tenant_documents_uses_one_transaction_per_tenant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    discovery_session = Mock()
    session_factory = MagicMock()
    session_factory.return_value.__enter__.return_value = discovery_session
    provider = Mock()

    first_result = ProcessingCycleResult(
        chunked_documents=1,
        chunks_created=2,
        embedded_documents=1,
        embedded_chunks=2,
        skipped_chunks=0,
        input_tokens=42,
    )
    second_result = ProcessingCycleResult(
        chunked_documents=1,
        chunks_created=1,
        embedded_documents=1,
        embedded_chunks=1,
        skipped_chunks=1,
        input_tokens=24,
    )

    discover_tenants = Mock(return_value=["nimbuscart", "skyforge"])
    process_tenant_cycle = Mock(side_effect=[first_result, second_result])
    monkeypatch.setattr(
        "app.worker.list_tenant_slugs_requiring_processing",
        discover_tenants,
    )
    monkeypatch.setattr("app.worker.process_one_cycle", process_tenant_cycle)

    result = process_all_tenant_documents(
        session_factory=session_factory,
        provider=provider,
    )

    assert result == ProcessingCycleResult(
        chunked_documents=2,
        chunks_created=3,
        embedded_documents=2,
        embedded_chunks=3,
        skipped_chunks=1,
        input_tokens=66,
    )
    discover_tenants.assert_called_once_with(discovery_session)
    process_tenant_cycle.assert_has_calls(
        [
            call(
                session_factory=session_factory,
                tenant_slug="nimbuscart",
                provider=provider,
            ),
            call(
                session_factory=session_factory,
                tenant_slug="skyforge",
                provider=provider,
            ),
        ]
    )


def test_process_all_tenant_documents_continues_after_one_tenant_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    discovery_session = Mock()
    session_factory = MagicMock()
    session_factory.return_value.__enter__.return_value = discovery_session
    provider = Mock()

    successful_result = ProcessingCycleResult(
        chunked_documents=1,
        chunks_created=1,
        embedded_documents=1,
        embedded_chunks=1,
        skipped_chunks=0,
        input_tokens=16,
    )

    monkeypatch.setattr(
        "app.worker.list_tenant_slugs_requiring_processing",
        Mock(return_value=["nimbuscart", "skyforge"]),
    )
    process_tenant_cycle = Mock(
        side_effect=[RuntimeError("temporary provider failure"), successful_result]
    )
    monkeypatch.setattr("app.worker.process_one_cycle", process_tenant_cycle)

    result = process_all_tenant_documents(
        session_factory=session_factory,
        provider=provider,
    )

    assert result == successful_result
    process_tenant_cycle.assert_has_calls(
        [
            call(
                session_factory=session_factory,
                tenant_slug="nimbuscart",
                provider=provider,
            ),
            call(
                session_factory=session_factory,
                tenant_slug="skyforge",
                provider=provider,
            ),
        ]
    )
