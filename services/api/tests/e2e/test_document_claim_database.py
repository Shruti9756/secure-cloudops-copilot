"""Prove queued-document claim rules against local PostgreSQL."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.db.models import KnowledgeDocument, Organization, Tenant
from app.infrastructure.postgres import get_engine
from app.services.document_queue import DocumentProcessingMessage
from app.services.document_retry import DEFAULT_PROCESSING_MAX_ATTEMPTS
from app.worker import claim_document_for_message

pytestmark = pytest.mark.e2e

AVAILABLE_AT = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


def test_queued_claim_enforces_scope_status_and_retry_time_in_postgres() -> None:
    engine = get_engine()

    # Check the destination BEFORE opening a database connection.
    assert engine.url.host in {"127.0.0.1", "localhost"}, (
        "This test must run against local PostgreSQL, never staging."
    )

    suffix = uuid4().hex[:12]
    organization_a = Organization(
        id=uuid4(),
        slug=f"claim-org-a-{suffix}",
        name="Synthetic Claim Organization A",
    )
    organization_b = Organization(
        id=uuid4(),
        slug=f"claim-org-b-{suffix}",
        name="Synthetic Claim Organization B",
    )
    tenant_a = Tenant(
        id=uuid4(),
        organization_id=organization_a.id,
        slug=f"claim-tenant-a-{suffix}",
        name="Synthetic Claim Workspace A",
    )
    tenant_b = Tenant(
        id=uuid4(),
        organization_id=organization_b.id,
        slug=f"claim-tenant-b-{suffix}",
        name="Synthetic Claim Workspace B",
    )
    document = KnowledgeDocument(
        id=uuid4(),
        organization_id=organization_a.id,
        tenant_id=tenant_a.id,
        title="Synthetic Claim Document",
        source_path="uploads/claim-test.md",
        source_sha256="a" * 64,
        content="Synthetic local PostgreSQL test content.",
        ingestion_status="pending",
        processing_attempt_count=0,
        next_processing_attempt_at=None,
        access_level="organization",
        document_metadata={},
    )
    correct_message = DocumentProcessingMessage(
        organization_id=organization_a.id,
        tenant_id=tenant_a.id,
        document_id=document.id,
    )

    with Session(engine, autoflush=False, expire_on_commit=False) as session:
        try:
            session.add_all([organization_a, organization_b])
            session.flush()
            session.add_all([tenant_a, tenant_b])
            session.flush()
            session.add(document)
            session.flush()

            def claim(message: DocumentProcessingMessage) -> KnowledgeDocument | None:
                return claim_document_for_message(
                    session=session,
                    message=message,
                    available_at=AVAILABLE_AT,
                )

            # The exact organization, workspace, and document can be claimed.
            assert claim(correct_message) is document

            # A message with any incorrect ID must not claim this document.
            wrong_messages = (
                DocumentProcessingMessage(
                    organization_id=organization_b.id,
                    tenant_id=tenant_a.id,
                    document_id=document.id,
                ),
                DocumentProcessingMessage(
                    organization_id=organization_a.id,
                    tenant_id=tenant_b.id,
                    document_id=document.id,
                ),
                DocumentProcessingMessage(
                    organization_id=organization_a.id,
                    tenant_id=tenant_a.id,
                    document_id=uuid4(),
                ),
            )
            for wrong_message in wrong_messages:
                assert claim(wrong_message) is None

            # Even if a document row has inconsistent ownership, the tenant
            # organization check must reject it.
            document.organization_id = organization_b.id
            session.flush()
            inconsistent_message = DocumentProcessingMessage(
                organization_id=organization_b.id,
                tenant_id=tenant_a.id,
                document_id=document.id,
            )
            assert claim(inconsistent_message) is None
            document.organization_id = organization_a.id
            session.flush()

            # A duplicate message after processing is complete is harmless.
            document.ingestion_status = "embedded"
            session.flush()
            assert claim(correct_message) is None

            # An exhausted document cannot exceed the attempt limit.
            document.ingestion_status = "pending"
            document.processing_attempt_count = DEFAULT_PROCESSING_MAX_ATTEMPTS
            session.flush()
            assert claim(correct_message) is None

            # A scheduled retry cannot run early.
            document.processing_attempt_count = 0
            document.next_processing_attempt_at = AVAILABLE_AT + timedelta(minutes=1)
            session.flush()
            assert claim(correct_message) is None

            # A due, partially processed document can resume.
            document.ingestion_status = "chunked"
            document.next_processing_attempt_at = AVAILABLE_AT
            session.flush()
            assert claim(correct_message) is document
        finally:
            # No synthetic organization, workspace, or document is committed.
            session.rollback()
