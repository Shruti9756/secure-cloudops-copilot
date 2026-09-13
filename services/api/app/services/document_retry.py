"""Deterministic retry policy for document-processing failures."""

from datetime import datetime, timedelta
from typing import Literal

from app.db.models import KnowledgeDocument

DEFAULT_PROCESSING_RETRY_BASE_DELAY_SECONDS = 5
DEFAULT_PROCESSING_RETRY_MAX_DELAY_SECONDS = 60
DEFAULT_PROCESSING_MAX_ATTEMPTS = 5

type DocumentProcessingFailureReason = Literal[
    "provider_unavailable",
    "invalid_document",
    "unexpected_error",
]

ALLOWED_PROCESSING_FAILURE_REASONS = frozenset(
    {
        "provider_unavailable",
        "invalid_document",
        "unexpected_error",
    }
)

PROCESSABLE_DOCUMENT_STATUSES = frozenset({"pending", "chunked"})


def calculate_retry_delay_seconds(
    failure_count: int,
    *,
    base_delay_seconds: int = DEFAULT_PROCESSING_RETRY_BASE_DELAY_SECONDS,
    max_delay_seconds: int = DEFAULT_PROCESSING_RETRY_MAX_DELAY_SECONDS,
) -> int:
    """Return a bounded exponential delay for one consecutive failure."""
    _require_positive_integer(failure_count, name="Failure count")
    _require_positive_integer(base_delay_seconds, name="Base retry delay")
    _require_positive_integer(max_delay_seconds, name="Maximum retry delay")

    if base_delay_seconds > max_delay_seconds:
        raise ValueError("Base retry delay must not exceed maximum retry delay")

    exponential_delay = base_delay_seconds * 2 ** (failure_count - 1)

    return min(exponential_delay, max_delay_seconds)


def record_processing_failure(
    document: KnowledgeDocument,
    *,
    failure_reason: DocumentProcessingFailureReason,
    occurred_at: datetime,
    max_attempts: int = DEFAULT_PROCESSING_MAX_ATTEMPTS,
    base_delay_seconds: int = DEFAULT_PROCESSING_RETRY_BASE_DELAY_SECONDS,
    max_delay_seconds: int = DEFAULT_PROCESSING_RETRY_MAX_DELAY_SECONDS,
) -> bool:
    """Record one failure and return whether another attempt was scheduled."""
    if failure_reason not in ALLOWED_PROCESSING_FAILURE_REASONS:
        raise ValueError("Document processing failure reason is not supported")

    if document.ingestion_status not in PROCESSABLE_DOCUMENT_STATUSES:
        raise ValueError("Only pending or chunked documents can record a processing failure")

    if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
        raise ValueError("Processing failure time must include timezone information")

    _require_positive_integer(max_attempts, name="Maximum processing attempts")
    _require_positive_integer(base_delay_seconds, name="Base retry delay")
    _require_positive_integer(max_delay_seconds, name="Maximum retry delay")

    if base_delay_seconds > max_delay_seconds:
        raise ValueError("Base retry delay must not exceed maximum retry delay")

    current_attempt_count = document.processing_attempt_count

    if (
        isinstance(current_attempt_count, bool)
        or not isinstance(current_attempt_count, int)
        or current_attempt_count < 0
    ):
        raise ValueError("Document processing attempt count must be a nonnegative integer")

    if current_attempt_count >= max_attempts:
        raise ValueError("Document has already exhausted its processing attempts")

    next_attempt_count = current_attempt_count + 1

    document.processing_attempt_count = next_attempt_count
    document.last_processing_failure_reason = failure_reason

    if next_attempt_count >= max_attempts:
        document.ingestion_status = "failed"
        document.next_processing_attempt_at = None
        return False

    retry_delay_seconds = calculate_retry_delay_seconds(
        next_attempt_count,
        base_delay_seconds=base_delay_seconds,
        max_delay_seconds=max_delay_seconds,
    )
    document.next_processing_attempt_at = occurred_at + timedelta(seconds=retry_delay_seconds)

    return True


def clear_processing_failure(document: KnowledgeDocument) -> None:
    """Clear previous failure information after successful processing."""
    document.processing_attempt_count = 0
    document.next_processing_attempt_at = None
    document.last_processing_failure_reason = None


def _require_positive_integer(value: int, *, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
