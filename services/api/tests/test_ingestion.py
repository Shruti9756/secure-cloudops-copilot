from unittest.mock import Mock
from uuid import uuid4

from app.db.models import KnowledgeDocument, Tenant
from app.services.ingestion import (
    calculate_content_sha256,
    extract_markdown_title,
    ingest_document,
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
