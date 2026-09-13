from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.db.models import KnowledgeDocument
from app.services.document_retry import (
    calculate_retry_delay_seconds,
    clear_processing_failure,
    record_processing_failure,
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
