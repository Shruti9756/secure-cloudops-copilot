from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.models import AuditEvent, KnowledgeDocument, Tenant
from app.main import (
    app,
    get_authorized_document_write_tenant,
    get_current_principal,
    get_database_session,
)
from app.services.authorization import AuthenticatedPrincipal

client = TestClient(app)


def make_tenant() -> Tenant:
    return Tenant(
        id=uuid4(),
        organization_id=uuid4(),
        slug="nimbuscart",
        name="NimbusCart",
    )


def make_document(
    *,
    tenant: Tenant,
    ingestion_status: str,
) -> KnowledgeDocument:
    return KnowledgeDocument(
        id=uuid4(),
        tenant_id=tenant.id,
        organization_id=tenant.organization_id,
        title="Failed Retry Document",
        source_path="uploads/failed-retry-document.md",
        source_sha256="a" * 64,
        content="Synthetic retry endpoint test content.",
        ingestion_status=ingestion_status,
        processing_attempt_count=5 if ingestion_status == "failed" else 0,
        next_processing_attempt_at=None,
        last_processing_failure_reason=(
            "provider_unavailable" if ingestion_status == "failed" else None
        ),
        access_level="organization",
        document_metadata={},
    )


def install_authorized_dependencies(
    session: Mock,
    tenant: Tenant,
) -> AuthenticatedPrincipal:
    principal = AuthenticatedPrincipal(
        user_id=uuid4(),
        identity_subject="cognito-retry-admin",
        display_name="Cognito Retry Administrator",
        authentication_source="cognito",
    )

    app.dependency_overrides[get_database_session] = lambda: session
    app.dependency_overrides[get_current_principal] = lambda: principal
    app.dependency_overrides[get_authorized_document_write_tenant] = lambda: tenant

    return principal


def test_retry_failed_document_resets_state_commits_and_audits() -> None:
    session = Mock()
    tenant = make_tenant()
    document = make_document(
        tenant=tenant,
        ingestion_status="failed",
    )
    session.scalar.return_value = document

    principal = install_authorized_dependencies(session, tenant)

    try:
        response = client.post(
            "/api/v1/documents/retry",
            params={"source_path": document.source_path},
        )
    finally:
        app.dependency_overrides.clear()

    audit_event = session.add.call_args.args[0]

    assert response.status_code == 200
    assert response.json() == {
        "status": "accepted",
        "action": "retry_scheduled",
        "tenant": "nimbuscart",
        "source_path": "uploads/failed-retry-document.md",
        "ingestion_status": "pending",
    }

    assert document.ingestion_status == "pending"
    assert document.processing_attempt_count == 0
    assert document.next_processing_attempt_at is None
    assert document.last_processing_failure_reason is None

    assert isinstance(audit_event, AuditEvent)
    assert audit_event.tenant_id == tenant.id
    assert audit_event.organization_id == tenant.organization_id
    assert audit_event.event_type == "document.retry"
    assert audit_event.outcome == "succeeded"
    assert audit_event.actor_type == "cognito_user"
    assert audit_event.actor_id == principal.identity_subject
    assert audit_event.request_id == response.headers["x-request-id"]
    assert audit_event.event_metadata == {
        "retry_status": "accepted",
        "source_path": document.source_path,
    }

    statement_sql = str(session.scalar.call_args.args[0])
    assert "knowledge_documents.tenant_id" in statement_sql
    assert "knowledge_documents.organization_id" in statement_sql
    assert "knowledge_documents.source_path" in statement_sql
    assert "FOR UPDATE" in statement_sql

    session.commit.assert_called_once_with()


@pytest.mark.parametrize(
    "ingestion_status",
    ["pending", "chunked", "embedded"],
)
def test_retry_rejects_documents_that_are_not_failed(
    ingestion_status: str,
) -> None:
    session = Mock()
    tenant = make_tenant()
    document = make_document(
        tenant=tenant,
        ingestion_status=ingestion_status,
    )
    session.scalar.return_value = document

    install_authorized_dependencies(session, tenant)

    try:
        response = client.post(
            "/api/v1/documents/retry",
            params={"source_path": document.source_path},
        )
    finally:
        app.dependency_overrides.clear()

    audit_event = session.add.call_args.args[0]

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Only failed documents can be retried.",
    }
    assert document.ingestion_status == ingestion_status
    assert audit_event.event_type == "document.retry"
    assert audit_event.outcome == "denied"
    assert audit_event.event_metadata == {
        "retry_status": "document_not_failed",
        "source_path": document.source_path,
    }
    session.commit.assert_called_once_with()


def test_retry_returns_safe_not_found_for_unknown_document() -> None:
    session = Mock()
    tenant = make_tenant()
    session.scalar.return_value = None

    install_authorized_dependencies(session, tenant)

    try:
        response = client.post(
            "/api/v1/documents/retry",
            params={"source_path": "uploads/missing-document.md"},
        )
    finally:
        app.dependency_overrides.clear()

    audit_event = session.add.call_args.args[0]

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Requested document is not available.",
    }
    assert audit_event.event_type == "document.retry"
    assert audit_event.outcome == "denied"
    assert audit_event.event_metadata == {
        "retry_status": "document_not_found",
        "source_path": "uploads/missing-document.md",
    }
    session.commit.assert_called_once_with()
