"""Best-effort Redis helpers for short-lived document-processing progress."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol, cast
from uuid import UUID

from redis.exceptions import RedisError

DOCUMENT_JOB_STATUS_KEY_VERSION = "v1"
DOCUMENT_JOB_STATUS_TTL_SECONDS = 300

type DocumentJobStage = Literal[
    "claimed",
    "chunking",
    "embedding",
    "retry_scheduled",
    "completed",
    "failed",
]

ALLOWED_DOCUMENT_JOB_STAGES = frozenset(
    {
        "claimed",
        "chunking",
        "embedding",
        "retry_scheduled",
        "completed",
        "failed",
    }
)

DOCUMENT_JOB_STATUS_PAYLOAD_FIELDS = frozenset(
    {
        "stage",
        "source_sha256",
        "processing_attempt_count",
        "updated_at",
    }
)


class DocumentJobStatusClient(Protocol):
    """Small Redis interface required by document progress tracking."""

    def setex(
        self,
        name: str,
        time: int,
        value: str,
    ) -> bool | None:
        """Store one value with an expiry measured in seconds."""

    def mget(self, keys: list[str]) -> list[str | bytes | None]:
        """Return stored values in key order; missing entries are None."""


@dataclass(frozen=True)
class DocumentJobStatus:
    """Safe temporary progress for one version of one document."""

    stage: DocumentJobStage
    source_sha256: str
    processing_attempt_count: int
    updated_at: datetime


@dataclass(frozen=True)
class DocumentJobStatusLookup:
    """Expected identity and version information for one progress lookup."""

    document_id: UUID | str
    expected_source_sha256: str
    expected_processing_attempt_count: int


def build_document_job_status_key(
    *,
    organization_id: UUID | str,
    tenant_id: UUID | str,
    document_id: UUID | str,
) -> str:
    """Build a versioned key isolated by organization, tenant, and document."""
    organization_identifier = _normalize_identifier(
        organization_id,
        name="Organization ID",
    )
    tenant_identifier = _normalize_identifier(
        tenant_id,
        name="Tenant ID",
    )
    document_identifier = _normalize_identifier(
        document_id,
        name="Document ID",
    )

    return (
        f"securecloudops:document-job-status:{DOCUMENT_JOB_STATUS_KEY_VERSION}:"
        f"{organization_identifier}:{tenant_identifier}:{document_identifier}"
    )


def store_document_job_status(
    redis_client: DocumentJobStatusClient,
    *,
    organization_id: UUID | str,
    tenant_id: UUID | str,
    document_id: UUID | str,
    stage: DocumentJobStage,
    source_sha256: str,
    processing_attempt_count: int,
    updated_at: datetime | None = None,
    ttl_seconds: int = DOCUMENT_JOB_STATUS_TTL_SECONDS,
) -> bool:
    """Store safe progress without allowing Redis failure to stop processing."""
    if not isinstance(stage, str):
        raise TypeError("Document job stage must be a string")

    if stage not in ALLOWED_DOCUMENT_JOB_STAGES:
        raise ValueError("Document job stage is not supported")

    normalized_source_sha256 = _normalize_source_sha256(source_sha256)
    normalized_attempt_count = _require_nonnegative_integer(
        processing_attempt_count,
        name="Processing attempt count",
    )
    normalized_ttl_seconds = _require_positive_integer(
        ttl_seconds,
        name="Document job status TTL",
    )

    status_updated_at = updated_at or datetime.now(UTC)
    normalized_updated_at = _normalize_aware_datetime(status_updated_at)

    key = build_document_job_status_key(
        organization_id=organization_id,
        tenant_id=tenant_id,
        document_id=document_id,
    )
    payload = json.dumps(
        {
            "processing_attempt_count": normalized_attempt_count,
            "source_sha256": normalized_source_sha256,
            "stage": stage,
            "updated_at": normalized_updated_at.isoformat(),
        },
        separators=(",", ":"),
        sort_keys=True,
    )

    try:
        stored = redis_client.setex(
            key,
            normalized_ttl_seconds,
            payload,
        )
    except RedisError:
        return False

    return stored is True


def load_document_job_status(
    redis_client: DocumentJobStatusClient,
    *,
    organization_id: UUID | str,
    tenant_id: UUID | str,
    document_id: UUID | str,
    expected_source_sha256: str,
    expected_processing_attempt_count: int,
) -> DocumentJobStatus | None:
    """Load one progress item through the shared batch implementation."""
    statuses = load_document_job_statuses(
        redis_client,
        organization_id=organization_id,
        tenant_id=tenant_id,
        lookups=(
            DocumentJobStatusLookup(
                document_id=document_id,
                expected_source_sha256=expected_source_sha256,
                expected_processing_attempt_count=expected_processing_attempt_count,
            ),
        ),
    )

    return statuses[0]


def load_document_job_statuses(
    redis_client: DocumentJobStatusClient,
    *,
    organization_id: UUID | str,
    tenant_id: UUID | str,
    lookups: Sequence[DocumentJobStatusLookup],
) -> list[DocumentJobStatus | None]:
    """Load ordered document progress using one best-effort Redis request."""
    prepared_lookups: list[tuple[str, str, int]] = []

    for lookup in lookups:
        normalized_source_sha256 = _normalize_source_sha256(lookup.expected_source_sha256)
        normalized_attempt_count = _require_nonnegative_integer(
            lookup.expected_processing_attempt_count,
            name="Expected processing attempt count",
        )
        key = build_document_job_status_key(
            organization_id=organization_id,
            tenant_id=tenant_id,
            document_id=lookup.document_id,
        )

        prepared_lookups.append(
            (
                key,
                normalized_source_sha256,
                normalized_attempt_count,
            )
        )

    if not prepared_lookups:
        return []

    keys = [key for key, _, _ in prepared_lookups]

    try:
        raw_payloads = redis_client.mget(keys)
    except RedisError:
        return [None] * len(prepared_lookups)

    if len(raw_payloads) != len(prepared_lookups):
        return [None] * len(prepared_lookups)

    return [
        _parse_document_job_status(
            raw_payload,
            expected_source_sha256=expected_source_sha256,
            expected_processing_attempt_count=expected_attempt_count,
        )
        for raw_payload, (
            _,
            expected_source_sha256,
            expected_attempt_count,
        ) in zip(raw_payloads, prepared_lookups, strict=True)
    ]


def _parse_document_job_status(
    raw_payload: str | bytes | None,
    *,
    expected_source_sha256: str,
    expected_processing_attempt_count: int,
) -> DocumentJobStatus | None:
    """Validate one Redis value without affecting other batch results."""
    if raw_payload is None:
        return None

    try:
        payload = json.loads(raw_payload)
    except TypeError, UnicodeDecodeError, ValueError:
        return None

    if not isinstance(payload, dict):
        return None

    if set(payload) != DOCUMENT_JOB_STATUS_PAYLOAD_FIELDS:
        return None

    stage = payload["stage"]

    if not isinstance(stage, str) or stage not in ALLOWED_DOCUMENT_JOB_STAGES:
        return None

    try:
        source_sha256 = _normalize_source_sha256(payload["source_sha256"])
        processing_attempt_count = _require_nonnegative_integer(
            payload["processing_attempt_count"],
            name="Stored processing attempt count",
        )

        updated_at_value = payload["updated_at"]

        if not isinstance(updated_at_value, str):
            return None

        updated_at = _normalize_aware_datetime(datetime.fromisoformat(updated_at_value))
    except TypeError, ValueError:
        return None

    if source_sha256 != expected_source_sha256:
        return None

    if processing_attempt_count != expected_processing_attempt_count:
        return None

    return DocumentJobStatus(
        stage=cast(DocumentJobStage, stage),
        source_sha256=source_sha256,
        processing_attempt_count=processing_attempt_count,
        updated_at=updated_at,
    )


def _normalize_identifier(value: UUID | str, *, name: str) -> str:
    normalized_value = str(value).strip()

    if not normalized_value:
        raise ValueError(f"{name} must not be empty")

    return normalized_value


def _normalize_source_sha256(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("Source SHA-256 must be a string")

    normalized_value = value.strip().casefold()

    if len(normalized_value) != 64 or any(
        character not in "0123456789abcdef" for character in normalized_value
    ):
        raise ValueError("Source SHA-256 must contain 64 hexadecimal characters")

    return normalized_value


def _normalize_aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Document job status time must include timezone information")

    return value.astimezone(UTC)


def _require_nonnegative_integer(value: object, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")

    if value < 0:
        raise ValueError(f"{name} must be nonnegative")

    return value


def _require_positive_integer(value: object, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")

    if value <= 0:
        raise ValueError(f"{name} must be positive")

    return value
