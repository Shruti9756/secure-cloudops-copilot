from datetime import UTC, datetime, timedelta
from urllib.error import URLError
from uuid import uuid4

import pytest

from app.db.models import KnowledgeDocument
from app.services.document_retry import (
    calculate_retry_delay_seconds,
    classify_processing_failure,
    clear_processing_failure,
    record_processing_failure,
    reset_failed_document_for_retry,
)


def make_document(
    *,
    ingestion_status: str = "pending",
    processing_attempt_count: int = 0,
) -> KnowledgeDocument:
    return KnowledgeDocument(
        id=uuid4(),
        tenant_id=uuid4(),
        organization_id=uuid4(),
        title="Retry Test",
        source_path="uploads/retry-test.md",
        source_sha256="a" * 64,
        content="Synthetic retry test content.",
        ingestion_status=ingestion_status,
        processing_attempt_count=processing_attempt_count,
        next_processing_attempt_at=None,
        last_processing_failure_reason=None,
        access_level="organization",
        document_metadata={},
    )


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError("request timed out"),
        ConnectionError("connection refused"),
        URLError("provider unavailable"),
    ],
)
def test_classify_processing_failure_maps_connection_errors_to_provider_unavailable(
    error: Exception,
) -> None:
    assert classify_processing_failure(error) == "provider_unavailable"


def test_classify_processing_failure_uses_a_safe_code_for_unexpected_errors() -> None:
    error = ValueError("raw details must not be persisted")

    assert classify_processing_failure(error) == "unexpected_error"


@pytest.mark.parametrize(
    ("failure_count", "expected_delay_seconds"),
    [
        (1, 5),
        (2, 10),
        (3, 20),
        (4, 40),
        (5, 60),
        (6, 60),
    ],
)
def test_calculate_retry_delay_uses_bounded_exponential_backoff(
    failure_count: int,
    expected_delay_seconds: int,
) -> None:
    assert calculate_retry_delay_seconds(failure_count) == expected_delay_seconds


@pytest.mark.parametrize("failure_count", [0, -1, True])
def test_calculate_retry_delay_rejects_invalid_failure_count(
    failure_count: int,
) -> None:
    with pytest.raises(ValueError, match="Failure count"):
        calculate_retry_delay_seconds(failure_count)


def test_record_processing_failure_schedules_another_attempt() -> None:
    document = make_document()
    occurred_at = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)

    retry_scheduled = record_processing_failure(
        document,
        failure_reason="provider_unavailable",
        occurred_at=occurred_at,
    )

    assert retry_scheduled is True
    assert document.ingestion_status == "pending"
    assert document.processing_attempt_count == 1
    assert document.next_processing_attempt_at == occurred_at + timedelta(seconds=5)
    assert document.last_processing_failure_reason == "provider_unavailable"


def test_record_processing_failure_preserves_chunked_stage_during_retry() -> None:
    document = make_document(
        ingestion_status="chunked",
        processing_attempt_count=1,
    )
    occurred_at = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)

    retry_scheduled = record_processing_failure(
        document,
        failure_reason="provider_unavailable",
        occurred_at=occurred_at,
    )

    assert retry_scheduled is True
    assert document.ingestion_status == "chunked"
    assert document.processing_attempt_count == 2
    assert document.next_processing_attempt_at == occurred_at + timedelta(seconds=10)


def test_record_processing_failure_marks_document_failed_at_attempt_limit() -> None:
    document = make_document(
        ingestion_status="chunked",
        processing_attempt_count=4,
    )
    occurred_at = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)

    retry_scheduled = record_processing_failure(
        document,
        failure_reason="provider_unavailable",
        occurred_at=occurred_at,
    )

    assert retry_scheduled is False
    assert document.ingestion_status == "failed"
    assert document.processing_attempt_count == 5
    assert document.next_processing_attempt_at is None
    assert document.last_processing_failure_reason == "provider_unavailable"


def test_record_processing_failure_rejects_unsafe_raw_reason() -> None:
    document = make_document()

    with pytest.raises(ValueError, match="failure reason"):
        record_processing_failure(
            document,
            failure_reason="AWS credential contents",  # type: ignore[arg-type]
            occurred_at=datetime(2026, 9, 13, 12, 0, tzinfo=UTC),
        )


def test_clear_processing_failure_resets_retry_metadata() -> None:
    document = make_document(
        ingestion_status="chunked",
        processing_attempt_count=3,
    )
    document.next_processing_attempt_at = datetime(
        2026,
        9,
        13,
        12,
        1,
        tzinfo=UTC,
    )
    document.last_processing_failure_reason = "provider_unavailable"

    clear_processing_failure(document)

    assert document.processing_attempt_count == 0
    assert document.next_processing_attempt_at is None
    assert document.last_processing_failure_reason is None
    assert document.ingestion_status == "chunked"


def test_reset_failed_document_for_retry_requeues_and_clears_failure_state() -> None:
    document = make_document(
        ingestion_status="failed",
        processing_attempt_count=5,
    )
    document.next_processing_attempt_at = datetime(
        2026,
        9,
        13,
        12,
        1,
        tzinfo=UTC,
    )
    document.last_processing_failure_reason = "provider_unavailable"

    reset_failed_document_for_retry(document)

    assert document.ingestion_status == "pending"
    assert document.processing_attempt_count == 0
    assert document.next_processing_attempt_at is None
    assert document.last_processing_failure_reason is None


@pytest.mark.parametrize("status", ["pending", "chunked", "embedded"])
def test_reset_failed_document_for_retry_rejects_non_failed_documents(
    status: str,
) -> None:
    document = make_document(ingestion_status=status)

    with pytest.raises(ValueError, match="Only failed documents"):
        reset_failed_document_for_retry(document)
