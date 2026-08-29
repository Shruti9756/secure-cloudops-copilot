from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.db.models import KnowledgeDocument, Tenant
from app.infrastructure.s3 import S3DocumentReference
from app.services.ingestion import (
    calculate_content_sha256,
    extract_markdown_title,
    ingest_document,
)


class FakeRedactedDocumentStore:
    """In-memory object store proving ingestion sends only redacted text."""

    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[dict[str, str]] = []
        self.error = error

    def store_redacted_document(
        self,
        *,
        tenant_slug: str,
        source_path: str,
        redacted_content: str,
        content_sha256: str,
    ) -> S3DocumentReference:
        self.calls.append(
            {
                "tenant_slug": tenant_slug,
                "source_path": source_path,
                "redacted_content": redacted_content,
                "content_sha256": content_sha256,
            }
        )

        if self.error is not None:
            raise self.error

        return S3DocumentReference(
            bucket_name="secure-cloudops-test",
            object_key=(
                "tenants/nimbuscart/redacted-documents/uploads/redis-investigation.pdf.txt"
            ),
            version_id="test-version-1",
            e_tag='"test-etag"',
        )


def test_content_hash_is_deterministic() -> None:
    content = "# Checkout latency runbook"

    assert calculate_content_sha256(content) == calculate_content_sha256(content)
    assert len(calculate_content_sha256(content)) == 64


def test_content_hash_changes_when_content_changes() -> None:
    original = calculate_content_sha256("checkout latency")
    changed = calculate_content_sha256("checkout latency increased")

    assert original != changed


def test_extract_markdown_title_uses_first_level_one_heading() -> None:
    content = "Intro text\n\n# Checkout Latency Runbook\n\nMore details"

    assert extract_markdown_title(content, "Fallback") == "Checkout Latency Runbook"


def test_extract_markdown_title_uses_fallback_without_a_heading() -> None:
    assert extract_markdown_title("No heading here", "Fallback Title") == "Fallback Title"


def test_ingest_document_redacts_content_before_storing_it() -> None:
    """The database model must receive safe text and non-sensitive audit metadata."""
    session = Mock()
    session.scalar.return_value = None
    tenant = Tenant(id=uuid4(), slug="nimbuscart", name="NimbusCart")

    result = ingest_document(
        session=session,
        tenant=tenant,
        source_path="runbooks/checkout-latency.md",
        content=(
            "# Checkout Runbook\n\n"
            "AWS_ACCESS_KEY_ID=AKIA1234567890ABCDEF\n"
            "Authorization: Bearer example-token-123"
        ),
        ingestion_source="api-upload",
        content_type="text/markdown",
    )

    stored_document = session.add.call_args.args[0]

    assert result.action == "created"
    assert isinstance(stored_document, KnowledgeDocument)
    assert stored_document.access_level == "organization"
    assert stored_document.title == "Checkout Runbook"
    assert stored_document.content == (
        "# Checkout Runbook\n\n"
        "AWS_ACCESS_KEY_ID=[REDACTED: AWS_ACCESS_KEY_ID]\n"
        "Authorization: Bearer [REDACTED: BEARER_TOKEN]"
    )
    assert "AKIA1234567890ABCDEF" not in stored_document.content
    assert "example-token-123" not in stored_document.content
    assert stored_document.source_sha256 == calculate_content_sha256(stored_document.content)
    assert stored_document.document_metadata == {
        "content_type": "text/markdown",
        "ingestion_source": "api-upload",
        "redaction": {
            "applied": True,
            "count": 2,
            "types": ["AWS_ACCESS_KEY_ID", "BEARER_TOKEN"],
        },
    }


def test_ingest_document_mirrors_only_redacted_content_when_store_is_configured() -> None:
    """Object storage receives safe text before the database receives the document."""
    session = Mock()
    session.scalar.return_value = None
    tenant = Tenant(id=uuid4(), slug="nimbuscart", name="NimbusCart")
    document_store = FakeRedactedDocumentStore()

    result = ingest_document(
        session=session,
        tenant=tenant,
        source_path="uploads/redis-investigation.pdf",
        content=("Authorization: Bearer example-token-123\nInspect Redis eviction policy."),
        ingestion_source="api-upload",
        content_type="application/pdf",
        document_store=document_store,
    )

    stored_document = session.add.call_args.args[0]
    expected_safe_content = (
        "Authorization: Bearer [REDACTED: BEARER_TOKEN]\nInspect Redis eviction policy."
    )

    assert result.action == "created"
    assert document_store.calls == [
        {
            "tenant_slug": "nimbuscart",
            "source_path": "uploads/redis-investigation.pdf",
            "redacted_content": expected_safe_content,
            "content_sha256": calculate_content_sha256(expected_safe_content),
        }
    ]
    assert "example-token-123" not in document_store.calls[0]["redacted_content"]
    assert stored_document.document_metadata["redacted_text_storage"] == {
        "provider": "s3",
        "bucket_name": "secure-cloudops-test",
        "object_key": ("tenants/nimbuscart/redacted-documents/uploads/redis-investigation.pdf.txt"),
        "version_id": "test-version-1",
        "e_tag": '"test-etag"',
    }


def test_ingest_document_does_not_change_database_when_storage_mirror_fails() -> None:
    """A configured durable-storage failure must prevent a partial ingestion write."""
    session = Mock()
    session.scalar.return_value = None
    tenant = Tenant(id=uuid4(), slug="nimbuscart", name="NimbusCart")
    document_store = FakeRedactedDocumentStore(
        error=RuntimeError("S3 is unavailable"),
    )

    with pytest.raises(RuntimeError, match="S3 is unavailable"):
        ingest_document(
            session=session,
            tenant=tenant,
            source_path="uploads/redis-investigation.pdf",
            content="Inspect Redis eviction policy.",
            document_store=document_store,
        )

    session.add.assert_not_called()
