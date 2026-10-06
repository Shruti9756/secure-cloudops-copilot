"""Verify document and outbox writes share a local database transaction."""

from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import DocumentQueueOutbox, KnowledgeDocument, Organization, Tenant
from app.infrastructure.postgres import get_engine
from app.services.ingestion import ingest_document

pytestmark = pytest.mark.e2e


def test_document_and_outbox_insert_and_roll_back_together() -> None:
    engine = get_engine()
    assert engine.url.host in {"127.0.0.1", "localhost"}, "This test requires local PostgreSQL."

    suffix = uuid4().hex[:12]
    organization_id = uuid4()
    tenant_id = uuid4()
    organization = Organization(
        id=organization_id,
        slug=f"outbox-org-{suffix}",
        name="Synthetic Outbox Organization",
    )
    tenant = Tenant(
        id=tenant_id,
        organization_id=organization_id,
        slug=f"outbox-tenant-{suffix}",
        name="Synthetic Outbox Workspace",
    )

    with Session(engine, autoflush=False) as session:
        try:
            session.add(organization)
            session.flush()
            session.add(tenant)
            session.flush()

            result = ingest_document(
                session=session,
                tenant=tenant,
                source_path="uploads/outbox-test.md",
                content="# Outbox Test\n\nInspect the connection pool.",
            )
            session.flush()

            document = session.scalar(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.tenant_id == tenant_id,
                )
            )
            assert result.action == "created"
            assert document is not None

            event = session.scalar(
                select(DocumentQueueOutbox).where(
                    DocumentQueueOutbox.document_id == document.id,
                )
            )
            assert event is not None
            assert event.organization_id == organization_id
            assert event.tenant_id == tenant_id
            assert event.published_at is None
        finally:
            session.rollback()

    with Session(engine) as session:
        assert session.get(Organization, organization_id) is None
        assert session.get(Tenant, tenant_id) is None
        for model in (KnowledgeDocument, DocumentQueueOutbox):
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(
                        model.tenant_id == tenant_id,
                    )
                )
                == 0
            )
