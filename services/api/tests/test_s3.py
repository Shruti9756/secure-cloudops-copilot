"""Tests for the redacted-document S3 adapter."""

from typing import Any

import pytest
from botocore.exceptions import ClientError

from app.infrastructure.s3 import (
    S3_REDACTED_DOCUMENT_CONTENT_TYPE,
    S3_SERVER_SIDE_ENCRYPTION,
    S3DocumentReference,
    S3DocumentStorageUnavailableError,
    S3RedactedDocumentStore,
    build_redacted_document_object_key,
)

TEST_DOCUMENT_HASH = "a" * 64


class FakeS3Client:
    """In-memory S3 replacement proving unit tests never contact AWS."""

    def __init__(self) -> None:
        self.put_object_calls: list[dict[str, Any]] = []

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        self.put_object_calls.append(kwargs)

        return {
            "VersionId": "test-version-1",
            "ETag": '"test-etag"',
        }


class FailingS3Client:
    """Fake AWS client that returns a structured AWS access failure."""

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        raise ClientError(
            {
                "Error": {
                    "Code": "AccessDenied",
                    "Message": "Access denied",
                }
            },
            "PutObject",
        )


def test_build_redacted_document_object_key_uses_server_controlled_prefix() -> None:
    object_key = build_redacted_document_object_key(
        tenant_slug="nimbuscart",
        source_path="uploads/redis-investigation.pdf",
    )

    assert object_key == (
        "tenants/nimbuscart/redacted-documents/uploads/redis-investigation.pdf.txt"
    )


@pytest.mark.parametrize(
    "source_path",
    [
        "../private.md",
        "/private.md",
        "uploads\\private.md",
    ],
)
def test_build_redacted_document_object_key_rejects_unsafe_paths(
    source_path: str,
) -> None:
    with pytest.raises(ValueError, match="safe relative POSIX path"):
        build_redacted_document_object_key(
            tenant_slug="nimbuscart",
            source_path=source_path,
        )


def test_s3_store_uploads_only_safe_text_with_explicit_encryption() -> None:
    client = FakeS3Client()
    store = S3RedactedDocumentStore(
        bucket_name="secure-cloudops-test",
        client=client,
    )

    result = store.store_redacted_document(
        tenant_slug="nimbuscart",
        source_path="uploads/redis-investigation.pdf",
        redacted_content=(
            "[PDF page 1]\n"
            "Authorization: Bearer [REDACTED: BEARER_TOKEN]\n"
            "Inspect Redis eviction policy."
        ),
        content_sha256=TEST_DOCUMENT_HASH,
    )

    assert result == S3DocumentReference(
        bucket_name="secure-cloudops-test",
        object_key=("tenants/nimbuscart/redacted-documents/uploads/redis-investigation.pdf.txt"),
        version_id="test-version-1",
        e_tag='"test-etag"',
    )
    assert client.put_object_calls == [
        {
            "Bucket": "secure-cloudops-test",
            "Key": ("tenants/nimbuscart/redacted-documents/uploads/redis-investigation.pdf.txt"),
            "Body": (
                b"[PDF page 1]\n"
                b"Authorization: Bearer [REDACTED: BEARER_TOKEN]\n"
                b"Inspect Redis eviction policy."
            ),
            "ContentType": S3_REDACTED_DOCUMENT_CONTENT_TYPE,
            "ServerSideEncryption": S3_SERVER_SIDE_ENCRYPTION,
            "Metadata": {
                "document-sha256": TEST_DOCUMENT_HASH,
                "storage-format": "redacted-utf8-text",
            },
        }
    ]


def test_s3_store_rejects_empty_content_before_calling_s3() -> None:
    client = FakeS3Client()
    store = S3RedactedDocumentStore(
        bucket_name="secure-cloudops-test",
        client=client,
    )

    with pytest.raises(ValueError, match="must not be empty"):
        store.store_redacted_document(
            tenant_slug="nimbuscart",
            source_path="uploads/empty.md",
            redacted_content="   ",
            content_sha256=TEST_DOCUMENT_HASH,
        )

    assert client.put_object_calls == []


def test_s3_store_rejects_invalid_content_hash_before_calling_s3() -> None:
    client = FakeS3Client()
    store = S3RedactedDocumentStore(
        bucket_name="secure-cloudops-test",
        client=client,
    )

    with pytest.raises(ValueError, match="SHA-256 hexadecimal"):
        store.store_redacted_document(
            tenant_slug="nimbuscart",
            source_path="uploads/invalid-hash.md",
            redacted_content="# Safe document",
            content_sha256="not-a-hash",
        )

    assert client.put_object_calls == []


def test_s3_store_hides_aws_errors_behind_a_safe_application_error() -> None:
    store = S3RedactedDocumentStore(
        bucket_name="secure-cloudops-test",
        client=FailingS3Client(),
    )

    with pytest.raises(
        S3DocumentStorageUnavailableError,
        match="S3 document storage is unavailable",
    ):
        store.store_redacted_document(
            tenant_slug="nimbuscart",
            source_path="uploads/redis-investigation.pdf",
            redacted_content="# Safe content",
            content_sha256=TEST_DOCUMENT_HASH,
        )
