import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.services.document_job_status import (
    DOCUMENT_JOB_STATUS_TTL_SECONDS,
    DocumentJobStatus,
    DocumentJobStatusLookup,
    build_document_job_status_key,
    load_document_job_status,
    load_document_job_statuses,
    store_document_job_status,
)


class FakeDocumentJobStatusRedis:
    """Small in-memory Redis substitute for deterministic unit tests."""

    def __init__(self) -> None:
        self.entries: dict[str, str | bytes] = {}
        self.setex_calls: list[tuple[str, int, str]] = []
        self.mget_calls: list[list[str]] = []

    def setex(self, name: str, time: int, value: str) -> bool:
        self.entries[name] = value
        self.setex_calls.append((name, time, value))
        return True

    def mget(self, keys: list[str]) -> list[str | bytes | None]:
        self.mget_calls.append(keys.copy())
        return [self.entries.get(key) for key in keys]


class UnavailableDocumentJobStatusRedis:
    """Simulate Redis failure without requiring Docker."""

    def __init__(self) -> None:
        self.mget_call_count = 0

    def setex(self, name: str, time: int, value: str) -> bool:
        raise RedisConnectionError("Redis is unavailable")

    def mget(self, keys: list[str]) -> list[str | bytes | None]:
        self.mget_call_count += 1
        raise RedisConnectionError("Redis is unavailable")


def test_document_job_status_key_contains_every_ownership_scope() -> None:
    organization_id = uuid4()
    tenant_id = uuid4()
    document_id = uuid4()

    key = build_document_job_status_key(
        organization_id=organization_id,
        tenant_id=tenant_id,
        document_id=document_id,
    )

    assert key == (
        f"securecloudops:document-job-status:v1:{organization_id}:{tenant_id}:{document_id}"
    )


def test_document_job_status_keys_do_not_cross_organization_boundaries() -> None:
    tenant_id = uuid4()
    document_id = uuid4()

    first_key = build_document_job_status_key(
        organization_id=uuid4(),
        tenant_id=tenant_id,
        document_id=document_id,
    )
    second_key = build_document_job_status_key(
        organization_id=uuid4(),
        tenant_id=tenant_id,
        document_id=document_id,
    )

    assert first_key != second_key


def test_store_document_job_status_uses_safe_json_and_ttl() -> None:
    redis_client = FakeDocumentJobStatusRedis()
    organization_id = uuid4()
    tenant_id = uuid4()
    document_id = uuid4()
    updated_at = datetime(2026, 9, 14, 12, 30, tzinfo=UTC)

    was_stored = store_document_job_status(
        redis_client,
        organization_id=organization_id,
        tenant_id=tenant_id,
        document_id=document_id,
        stage="embedding",
        source_sha256="a" * 64,
        processing_attempt_count=2,
        updated_at=updated_at,
    )

    assert was_stored is True

    key, ttl_seconds, serialized_payload = redis_client.setex_calls[0]

    assert key == build_document_job_status_key(
        organization_id=organization_id,
        tenant_id=tenant_id,
        document_id=document_id,
    )
    assert ttl_seconds == DOCUMENT_JOB_STATUS_TTL_SECONDS
    assert json.loads(serialized_payload) == {
        "processing_attempt_count": 2,
        "source_sha256": "a" * 64,
        "stage": "embedding",
        "updated_at": "2026-09-14T12:30:00+00:00",
    }
    assert "content" not in serialized_payload
    assert "source_path" not in serialized_payload


def test_store_document_job_status_rejects_a_naive_timestamp() -> None:
    redis_client = FakeDocumentJobStatusRedis()

    with pytest.raises(ValueError, match="timezone"):
        store_document_job_status(
            redis_client,
            organization_id=uuid4(),
            tenant_id=uuid4(),
            document_id=uuid4(),
            stage="claimed",
            source_sha256="a" * 64,
            processing_attempt_count=0,
            updated_at=datetime(2026, 9, 14, 12, 30),  # noqa: DTZ001
        )

    assert redis_client.setex_calls == []


def test_store_document_job_status_degrades_safely_when_redis_is_unavailable() -> None:
    was_stored = store_document_job_status(
        UnavailableDocumentJobStatusRedis(),
        organization_id=uuid4(),
        tenant_id=uuid4(),
        document_id=uuid4(),
        stage="claimed",
        source_sha256="a" * 64,
        processing_attempt_count=0,
    )

    assert was_stored is False


def test_load_document_job_status_returns_current_progress() -> None:
    redis_client = FakeDocumentJobStatusRedis()
    organization_id = uuid4()
    tenant_id = uuid4()
    document_id = uuid4()
    updated_at = datetime(2026, 9, 14, 12, 30, tzinfo=UTC)

    store_document_job_status(
        redis_client,
        organization_id=organization_id,
        tenant_id=tenant_id,
        document_id=document_id,
        stage="chunking",
        source_sha256="a" * 64,
        processing_attempt_count=1,
        updated_at=updated_at,
    )

    status = load_document_job_status(
        redis_client,
        organization_id=organization_id,
        tenant_id=tenant_id,
        document_id=document_id,
        expected_source_sha256="a" * 64,
        expected_processing_attempt_count=1,
    )

    assert status == DocumentJobStatus(
        stage="chunking",
        source_sha256="a" * 64,
        processing_attempt_count=1,
        updated_at=updated_at,
    )


def test_load_document_job_status_ignores_an_older_document_version() -> None:
    redis_client = FakeDocumentJobStatusRedis()
    organization_id = uuid4()
    tenant_id = uuid4()
    document_id = uuid4()

    store_document_job_status(
        redis_client,
        organization_id=organization_id,
        tenant_id=tenant_id,
        document_id=document_id,
        stage="embedding",
        source_sha256="a" * 64,
        processing_attempt_count=0,
    )

    status = load_document_job_status(
        redis_client,
        organization_id=organization_id,
        tenant_id=tenant_id,
        document_id=document_id,
        expected_source_sha256="b" * 64,
        expected_processing_attempt_count=0,
    )

    assert status is None


def test_load_document_job_status_ignores_an_older_processing_attempt() -> None:
    redis_client = FakeDocumentJobStatusRedis()
    organization_id = uuid4()
    tenant_id = uuid4()
    document_id = uuid4()

    store_document_job_status(
        redis_client,
        organization_id=organization_id,
        tenant_id=tenant_id,
        document_id=document_id,
        stage="retry_scheduled",
        source_sha256="a" * 64,
        processing_attempt_count=1,
    )

    status = load_document_job_status(
        redis_client,
        organization_id=organization_id,
        tenant_id=tenant_id,
        document_id=document_id,
        expected_source_sha256="a" * 64,
        expected_processing_attempt_count=2,
    )

    assert status is None


@pytest.mark.parametrize(
    "raw_payload",
    [
        "not valid JSON",
        b"\xff",
        json.dumps([]),
        json.dumps(
            {
                "processing_attempt_count": 0,
                "source_sha256": "a" * 64,
                "stage": "unsupported",
                "updated_at": "2026-09-14T12:30:00+00:00",
            }
        ),
        json.dumps(
            {
                "processing_attempt_count": True,
                "source_sha256": "a" * 64,
                "stage": "claimed",
                "updated_at": "2026-09-14T12:30:00+00:00",
            }
        ),
        json.dumps(
            {
                "processing_attempt_count": 0,
                "source_sha256": "a" * 64,
                "stage": "claimed",
                "updated_at": "2026-09-14T12:30:00",
            }
        ),
    ],
)
def test_load_document_job_status_treats_malformed_data_as_absent(
    raw_payload: str | bytes,
) -> None:
    redis_client = FakeDocumentJobStatusRedis()
    organization_id = uuid4()
    tenant_id = uuid4()
    document_id = uuid4()
    key = build_document_job_status_key(
        organization_id=organization_id,
        tenant_id=tenant_id,
        document_id=document_id,
    )
    redis_client.entries[key] = raw_payload

    status = load_document_job_status(
        redis_client,
        organization_id=organization_id,
        tenant_id=tenant_id,
        document_id=document_id,
        expected_source_sha256="a" * 64,
        expected_processing_attempt_count=0,
    )

    assert status is None


def test_load_document_job_status_degrades_safely_when_redis_is_unavailable() -> None:
    status = load_document_job_status(
        UnavailableDocumentJobStatusRedis(),
        organization_id=uuid4(),
        tenant_id=uuid4(),
        document_id=uuid4(),
        expected_source_sha256="a" * 64,
        expected_processing_attempt_count=0,
    )

    assert status is None


def test_load_document_job_statuses_reads_multiple_documents_with_one_mget() -> None:
    redis_client = FakeDocumentJobStatusRedis()
    organization_id = uuid4()
    tenant_id = uuid4()
    first_document_id = uuid4()
    second_document_id = uuid4()
    missing_document_id = uuid4()
    updated_at = datetime(2026, 9, 15, 12, 30, tzinfo=UTC)

    store_document_job_status(
        redis_client,
        organization_id=organization_id,
        tenant_id=tenant_id,
        document_id=first_document_id,
        stage="chunking",
        source_sha256="a" * 64,
        processing_attempt_count=1,
        updated_at=updated_at,
    )
    store_document_job_status(
        redis_client,
        organization_id=organization_id,
        tenant_id=tenant_id,
        document_id=second_document_id,
        stage="embedding",
        source_sha256="b" * 64,
        processing_attempt_count=2,
        updated_at=updated_at,
    )

    statuses = load_document_job_statuses(
        redis_client,
        organization_id=organization_id,
        tenant_id=tenant_id,
        lookups=(
            DocumentJobStatusLookup(
                document_id=first_document_id,
                expected_source_sha256="a" * 64,
                expected_processing_attempt_count=1,
            ),
            DocumentJobStatusLookup(
                document_id=second_document_id,
                expected_source_sha256="b" * 64,
                expected_processing_attempt_count=2,
            ),
            DocumentJobStatusLookup(
                document_id=missing_document_id,
                expected_source_sha256="c" * 64,
                expected_processing_attempt_count=0,
            ),
        ),
    )

    assert statuses == [
        DocumentJobStatus(
            stage="chunking",
            source_sha256="a" * 64,
            processing_attempt_count=1,
            updated_at=updated_at,
        ),
        DocumentJobStatus(
            stage="embedding",
            source_sha256="b" * 64,
            processing_attempt_count=2,
            updated_at=updated_at,
        ),
        None,
    ]
    assert redis_client.mget_calls == [
        [
            build_document_job_status_key(
                organization_id=organization_id,
                tenant_id=tenant_id,
                document_id=first_document_id,
            ),
            build_document_job_status_key(
                organization_id=organization_id,
                tenant_id=tenant_id,
                document_id=second_document_id,
            ),
            build_document_job_status_key(
                organization_id=organization_id,
                tenant_id=tenant_id,
                document_id=missing_document_id,
            ),
        ]
    ]


def test_load_document_job_statuses_skips_redis_for_an_empty_batch() -> None:
    redis_client = FakeDocumentJobStatusRedis()

    statuses = load_document_job_statuses(
        redis_client,
        organization_id=uuid4(),
        tenant_id=uuid4(),
        lookups=(),
    )

    assert statuses == []
    assert redis_client.mget_calls == []


def test_load_document_job_statuses_attempts_redis_once_during_an_outage() -> None:
    redis_client = UnavailableDocumentJobStatusRedis()

    statuses = load_document_job_statuses(
        redis_client,
        organization_id=uuid4(),
        tenant_id=uuid4(),
        lookups=(
            DocumentJobStatusLookup(
                document_id=uuid4(),
                expected_source_sha256="a" * 64,
                expected_processing_attempt_count=0,
            ),
            DocumentJobStatusLookup(
                document_id=uuid4(),
                expected_source_sha256="b" * 64,
                expected_processing_attempt_count=0,
            ),
        ),
    )

    assert statuses == [None, None]
    assert redis_client.mget_call_count == 1
