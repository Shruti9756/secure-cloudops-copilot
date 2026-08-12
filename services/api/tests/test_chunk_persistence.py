from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.db.models import DocumentChunk, KnowledgeDocument
from app.services.chunking import replace_document_chunks


def make_document(content: str) -> KnowledgeDocument:
    return KnowledgeDocument(
        id=uuid4(),
        tenant_id=uuid4(),
        title="Checkout Runbook",
        source_path="runbooks/checkout-latency.md",
        source_sha256="a" * 64,
        content=content,
        ingestion_status="pending",
        document_metadata={},
    )


def test_replace_document_chunks_rebuilds_derived_records() -> None:
    session = Mock()
    document = make_document(("checkout latency " * 30).strip())

    result = replace_document_chunks(
        session=session,
        document=document,
        max_chars=50,
        overlap_chars=10,
    )

    created_chunks = session.add_all.call_args.args[0]

    assert result.source_path == "runbooks/checkout-latency.md"
    assert result.chunk_count > 1
    assert document.ingestion_status == "chunked"
    assert session.execute.call_count == 1
    assert session.flush.call_count == 1
    assert [chunk.chunk_index for chunk in created_chunks] == list(range(result.chunk_count))
    assert all(isinstance(chunk, DocumentChunk) for chunk in created_chunks)
    assert all(chunk.document_id == document.id for chunk in created_chunks)


def test_replace_document_chunks_keeps_existing_chunks_when_settings_are_invalid() -> None:
    session = Mock()
    document = make_document("Checkout latency runbook")

    with pytest.raises(ValueError, match="overlap_chars"):
        replace_document_chunks(
            session=session,
            document=document,
            max_chars=100,
            overlap_chars=100,
        )

    # Validate settings before deleting any derived records.
    session.execute.assert_not_called()
    session.flush.assert_not_called()
