from datetime import UTC, datetime, timedelta
from unittest.mock import ANY, MagicMock, Mock, call
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.db.models import KnowledgeDocument
from app.services.chunking import ChunkingResult
from app.services.document_lock import DocumentLockLease
from app.services.embedding_persistence import DocumentEmbeddingResult
from app.worker import (
    EMPTY_PROCESSING_CYCLE_RESULT,
    ProcessingCycleResult,
    claim_next_document,
    list_tenant_slugs_requiring_processing,
    process_all_tenant_documents,
    process_document,
    process_next_document,
    process_one_cycle,
)

AVAILABLE_AT = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
FAILURE_AT = datetime(2026, 9, 13, 12, 1, tzinfo=UTC)


def make_document(
    *,
    ingestion_status: str = "pending",
    processing_attempt_count: int = 0,
    next_processing_attempt_at: datetime | None = None,
    failure_reason: str | None = None,
) -> KnowledgeDocument:
    return KnowledgeDocument(
        id=uuid4(),
        tenant_id=uuid4(),
        organization_id=uuid4(),
        title="Worker Test",
        source_path="uploads/worker-test.md",
        source_sha256="a" * 64,
        content="Synthetic worker test content.",
        ingestion_status=ingestion_status,
        processing_attempt_count=processing_attempt_count,
        next_processing_attempt_at=next_processing_attempt_at,
        last_processing_failure_reason=failure_reason,
        access_level="organization",
        document_metadata={},
    )


def test_process_document_chunks_then_embeds_pending_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock()
    provider = Mock()
    document = make_document(
        processing_attempt_count=2,
        next_processing_attempt_at=AVAILABLE_AT,
        failure_reason="provider_unavailable",
    )

    chunking_result = ChunkingResult(
        document_id=document.id,
        source_path=document.source_path,
        chunk_count=2,
    )
    embedding_result = DocumentEmbeddingResult(
        document_id=document.id,
        source_path=document.source_path,
        embedded_chunk_count=2,
        skipped_chunk_count=0,
        total_input_tokens=42,
    )

    chunk_document = Mock(return_value=chunking_result)
    embed_document = Mock(return_value=embedding_result)

    monkeypatch.setattr("app.worker.replace_document_chunks", chunk_document)
    monkeypatch.setattr("app.worker.embed_document_chunks", embed_document)

    result = process_document(
        session=session,
        document=document,
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
    chunk_document.assert_called_once_with(
        session=session,
        document=document,
    )
    session.flush.assert_called_once_with()
    session.expire.assert_called_once_with(document, ["chunks"])
    embed_document.assert_called_once_with(
        session=session,
        document=document,
        provider=provider,
    )
    assert document.processing_attempt_count == 0
    assert document.next_processing_attempt_at is None
    assert document.last_processing_failure_reason is None


def test_process_document_embeds_chunked_document_without_rechunking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock()
    provider = Mock()
    document = make_document(
        ingestion_status="chunked",
        processing_attempt_count=1,
        next_processing_attempt_at=AVAILABLE_AT,
        failure_reason="provider_unavailable",
    )

    chunk_document = Mock()
    embed_document = Mock(
        return_value=DocumentEmbeddingResult(
            document_id=document.id,
            source_path=document.source_path,
            embedded_chunk_count=1,
            skipped_chunk_count=1,
            total_input_tokens=20,
        )
    )

    monkeypatch.setattr("app.worker.replace_document_chunks", chunk_document)
    monkeypatch.setattr("app.worker.embed_document_chunks", embed_document)

    result = process_document(
        session=session,
        document=document,
        provider=provider,
    )

    assert result == ProcessingCycleResult(
        chunked_documents=0,
        chunks_created=0,
        embedded_documents=1,
        embedded_chunks=1,
        skipped_chunks=1,
        input_tokens=20,
    )
    chunk_document.assert_not_called()
    session.expire.assert_not_called()
    embed_document.assert_called_once_with(
        session=session,
        document=document,
        provider=provider,
    )
    assert document.processing_attempt_count == 0
    assert document.next_processing_attempt_at is None
    assert document.last_processing_failure_reason is None


def test_claim_next_document_rejects_an_empty_tenant_before_database_work() -> None:
    session = Mock()

    with pytest.raises(
        ValueError,
        match="Document processor tenant slug must not be empty",
    ):
        claim_next_document(
            session=session,
            tenant_slug="   ",
            available_at=AVAILABLE_AT,
        )

    session.scalar.assert_not_called()


def test_list_tenant_slugs_requiring_processing_selects_only_due_work() -> None:
    session = Mock()
    session.scalars.return_value = ["nimbuscart", "skyforge"]

    tenant_slugs = list_tenant_slugs_requiring_processing(
        session,
        available_at=AVAILABLE_AT,
    )

    statement = session.scalars.call_args.args[0]
    compiled_statement = statement.compile(dialect=postgresql.dialect())
    statement_sql = str(compiled_statement)

    assert tenant_slugs == ["nimbuscart", "skyforge"]
    assert "knowledge_documents.ingestion_status" in statement_sql
    assert "knowledge_documents.processing_attempt_count" in statement_sql
    assert "knowledge_documents.next_processing_attempt_at IS NULL" in statement_sql
    assert "knowledge_documents.next_processing_attempt_at <=" in statement_sql
    assert AVAILABLE_AT in compiled_statement.params.values()


def test_claim_next_document_uses_a_due_row_lock() -> None:
    session = Mock()
    document = make_document()
    session.scalar.return_value = document

    claimed_document = claim_next_document(
        session=session,
        tenant_slug=" nimbuscart ",
        available_at=AVAILABLE_AT,
    )

    statement = session.scalar.call_args.args[0]
    compiled_statement = statement.compile(dialect=postgresql.dialect())
    statement_sql = str(compiled_statement)

    assert claimed_document is document
    assert "tenants.slug" in statement_sql
    assert "knowledge_documents.ingestion_status" in statement_sql
    assert "knowledge_documents.processing_attempt_count" in statement_sql
    assert "knowledge_documents.next_processing_attempt_at IS NULL" in statement_sql
    assert "knowledge_documents.next_processing_attempt_at <=" in statement_sql
    assert "LIMIT" in statement_sql
    assert "FOR UPDATE OF knowledge_documents SKIP LOCKED" in statement_sql
    assert "nimbuscart" in compiled_statement.params.values()
    assert AVAILABLE_AT in compiled_statement.params.values()


def test_process_next_document_skips_a_row_locked_by_another_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock()
    session_factory = MagicMock()
    session_factory.begin.return_value.__enter__.return_value = session
    provider = Mock()

    claim_document = Mock(return_value=None)
    process_claimed_document = Mock()

    monkeypatch.setattr("app.worker.claim_next_document", claim_document)
    monkeypatch.setattr("app.worker.process_document", process_claimed_document)

    result = process_next_document(
        session_factory=session_factory,
        tenant_slug="nimbuscart",
        provider=provider,
        available_at=AVAILABLE_AT,
        redis_client=Mock(),
    )

    assert result is None
    session_factory.begin.assert_called_once_with()
    claim_document.assert_called_once_with(
        session=session,
        tenant_slug="nimbuscart",
        available_at=AVAILABLE_AT,
    )
    session.begin_nested.assert_not_called()
    process_claimed_document.assert_not_called()


def test_process_next_document_skips_when_redis_lock_is_held(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock()
    session_factory = MagicMock()
    session_factory.begin.return_value.__enter__.return_value = session
    provider = Mock()
    redis_client = Mock()
    document = make_document()

    monkeypatch.setattr(
        "app.worker.claim_next_document",
        Mock(return_value=document),
    )
    monkeypatch.setattr(
        "app.worker.acquire_document_lock",
        Mock(return_value=None),
    )

    process_claimed_document = Mock()
    record_failure = Mock()
    monkeypatch.setattr("app.worker.process_document", process_claimed_document)
    monkeypatch.setattr("app.worker.record_processing_failure", record_failure)

    result = process_next_document(
        session_factory=session_factory,
        tenant_slug="nimbuscart",
        provider=provider,
        redis_client=redis_client,
        available_at=AVAILABLE_AT,
    )

    assert result is None
    process_claimed_document.assert_not_called()
    record_failure.assert_not_called()


def test_process_next_document_releases_redis_lock_after_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock()
    session_factory = MagicMock()
    session_factory.begin.return_value.__enter__.return_value = session
    provider = Mock()
    redis_client = Mock()
    redis_client.eval.return_value = 1
    document = make_document()

    lease = DocumentLockLease(
        key="document-lock",
        owner_token="worker-token",
        ttl_seconds=120,
    )

    result_value = ProcessingCycleResult(
        chunked_documents=1,
        chunks_created=1,
        embedded_documents=1,
        embedded_chunks=1,
        skipped_chunks=0,
        input_tokens=10,
    )

    acquire_lock = Mock(return_value=lease)
    release_lock = Mock(return_value=True)

    monkeypatch.setattr("app.worker.claim_next_document", Mock(return_value=document))
    monkeypatch.setattr("app.worker.acquire_document_lock", acquire_lock)
    monkeypatch.setattr("app.worker.release_document_lock", release_lock)
    monkeypatch.setattr(
        "app.worker.process_document",
        Mock(return_value=result_value),
    )

    result = process_next_document(
        session_factory=session_factory,
        tenant_slug="nimbuscart",
        provider=provider,
        redis_client=redis_client,
        available_at=AVAILABLE_AT,
    )

    assert result == result_value
    acquire_lock.assert_called_once_with(
        redis_client,
        document_id=document.id,
    )
    release_lock.assert_called_once_with(redis_client, lease)


@pytest.mark.parametrize(
    (
        "initial_attempt_count",
        "expected_status",
        "expected_next_attempt_at",
    ),
    [
        (0, "pending", FAILURE_AT + timedelta(seconds=5)),
        (4, "failed", None),
    ],
)
def test_process_next_document_rolls_back_processing_and_commits_failure_state(
    monkeypatch: pytest.MonkeyPatch,
    initial_attempt_count: int,
    expected_status: str,
    expected_next_attempt_at: datetime | None,
) -> None:
    session = MagicMock()
    session_factory = MagicMock()
    outer_transaction = session_factory.begin.return_value
    outer_transaction.__enter__.return_value = session
    nested_transaction = session.begin_nested.return_value
    nested_transaction.__exit__.return_value = False
    provider = Mock()

    document = make_document(
        processing_attempt_count=initial_attempt_count,
    )

    claim_document = Mock(return_value=document)
    process_claimed_document = Mock(
        side_effect=TimeoutError("raw provider failure must not be stored")
    )

    monkeypatch.setattr("app.worker.claim_next_document", claim_document)
    monkeypatch.setattr("app.worker.process_document", process_claimed_document)
    monkeypatch.setattr("app.worker._utc_now", Mock(return_value=FAILURE_AT))

    redis_client = Mock()
    redis_client.eval.return_value = 1

    result = process_next_document(
        session_factory=session_factory,
        tenant_slug="nimbuscart",
        provider=provider,
        available_at=AVAILABLE_AT,
        redis_client=redis_client,
    )

    assert result == EMPTY_PROCESSING_CYCLE_RESULT
    claim_document.assert_called_once_with(
        session=session,
        tenant_slug="nimbuscart",
        available_at=AVAILABLE_AT,
    )
    session.begin_nested.assert_called_once_with()
    process_claimed_document.assert_called_once_with(
        session=session,
        document=document,
        provider=provider,
        lock_heartbeat=ANY,
    )

    # The processing exception reached the savepoint, so it rolled back.
    nested_exit_arguments = nested_transaction.__exit__.call_args.args
    assert nested_exit_arguments[0] is TimeoutError

    # The outer transaction exited normally, so the retry state committed.
    outer_transaction.__exit__.assert_called_once_with(None, None, None)

    session.refresh.assert_called_once_with(document)
    session.flush.assert_called_once_with()
    assert document.ingestion_status == expected_status
    assert document.processing_attempt_count == initial_attempt_count + 1
    assert document.next_processing_attempt_at == expected_next_attempt_at
    assert document.last_processing_failure_reason == "provider_unavailable"


def test_process_one_cycle_continues_after_one_document_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory = MagicMock()
    provider = Mock()
    redis_client = Mock()

    successful_result = ProcessingCycleResult(
        chunked_documents=1,
        chunks_created=2,
        embedded_documents=1,
        embedded_chunks=2,
        skipped_chunks=0,
        input_tokens=42,
    )

    process_next = Mock(
        side_effect=[
            EMPTY_PROCESSING_CYCLE_RESULT,
            successful_result,
            None,
        ]
    )

    monkeypatch.setattr("app.worker._utc_now", Mock(return_value=AVAILABLE_AT))
    monkeypatch.setattr("app.worker.process_next_document", process_next)

    result = process_one_cycle(
        session_factory=session_factory,
        tenant_slug=" nimbuscart ",
        provider=provider,
        redis_client=redis_client,
    )

    assert result == successful_result
    process_next.assert_has_calls(
        [
            call(
                session_factory=session_factory,
                tenant_slug="nimbuscart",
                provider=provider,
                redis_client=redis_client,
                available_at=AVAILABLE_AT,
            ),
            call(
                session_factory=session_factory,
                tenant_slug="nimbuscart",
                provider=provider,
                redis_client=redis_client,
                available_at=AVAILABLE_AT,
            ),
            call(
                session_factory=session_factory,
                tenant_slug="nimbuscart",
                provider=provider,
                redis_client=redis_client,
                available_at=AVAILABLE_AT,
            ),
        ]
    )


def test_process_all_tenant_documents_aggregates_tenant_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    discovery_session = Mock()
    session_factory = MagicMock()
    session_factory.return_value.__enter__.return_value = discovery_session
    provider = Mock()
    redis_client = Mock()

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

    monkeypatch.setattr("app.worker._utc_now", Mock(return_value=AVAILABLE_AT))
    monkeypatch.setattr(
        "app.worker.list_tenant_slugs_requiring_processing",
        discover_tenants,
    )
    monkeypatch.setattr("app.worker.process_one_cycle", process_tenant_cycle)

    result = process_all_tenant_documents(
        session_factory=session_factory,
        provider=provider,
        redis_client=redis_client,
    )

    assert result == ProcessingCycleResult(
        chunked_documents=2,
        chunks_created=3,
        embedded_documents=2,
        embedded_chunks=3,
        skipped_chunks=1,
        input_tokens=66,
    )
    discover_tenants.assert_called_once_with(
        discovery_session,
        available_at=AVAILABLE_AT,
    )
    process_tenant_cycle.assert_has_calls(
        [
            call(
                session_factory=session_factory,
                tenant_slug="nimbuscart",
                provider=provider,
                redis_client=redis_client,
            ),
            call(
                session_factory=session_factory,
                tenant_slug="skyforge",
                provider=provider,
                redis_client=redis_client,
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
    redis_client = Mock()

    successful_result = ProcessingCycleResult(
        chunked_documents=1,
        chunks_created=1,
        embedded_documents=1,
        embedded_chunks=1,
        skipped_chunks=0,
        input_tokens=16,
    )

    monkeypatch.setattr("app.worker._utc_now", Mock(return_value=AVAILABLE_AT))
    monkeypatch.setattr(
        "app.worker.list_tenant_slugs_requiring_processing",
        Mock(return_value=["nimbuscart", "skyforge"]),
    )

    process_tenant_cycle = Mock(
        side_effect=[
            RuntimeError("database bookkeeping failure"),
            successful_result,
        ]
    )
    monkeypatch.setattr("app.worker.process_one_cycle", process_tenant_cycle)

    result = process_all_tenant_documents(
        session_factory=session_factory,
        provider=provider,
        redis_client=redis_client,
    )

    assert result == successful_result
    process_tenant_cycle.assert_has_calls(
        [
            call(
                session_factory=session_factory,
                tenant_slug="nimbuscart",
                provider=provider,
                redis_client=redis_client,
            ),
            call(
                session_factory=session_factory,
                tenant_slug="skyforge",
                provider=provider,
                redis_client=redis_client,
            ),
        ]
    )
