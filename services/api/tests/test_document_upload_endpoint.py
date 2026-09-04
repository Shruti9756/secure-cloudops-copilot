from collections.abc import Iterator
from unittest.mock import Mock
from uuid import uuid4

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.db.models import AuditEvent, KnowledgeDocument, Tenant
from app.infrastructure.s3 import S3DocumentStorageUnavailableError
from app.main import (
    app,
    get_authorized_document_write_tenant,
    get_current_principal,
    get_database_session,
)
from app.services.authorization import AuthenticatedPrincipal
from app.services.document_storage import get_redacted_document_store

client = TestClient(app)


@pytest.fixture(autouse=True)
def install_local_principal() -> Iterator[None]:
    """Keep upload endpoint tests focused on ingestion instead of authentication."""

    app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal(
        user_id=uuid4(),
        identity_subject="local-demo-admin",
        display_name="Local Demo Administrator",
    )

    yield

    app.dependency_overrides.clear()


class UnavailableRedactedDocumentStore:
    """Fake configured storage that proves the endpoint fails safely."""

    def store_redacted_document(
        self,
        *,
        tenant_slug: str,
        source_path: str,
        redacted_content: str,
        content_sha256: str,
    ) -> None:
        raise S3DocumentStorageUnavailableError("S3 document storage is unavailable")


def make_tenant() -> Tenant:
    """Create the tenant returned by the test authorization override."""
    return Tenant(
        id=uuid4(),
        organization_id=uuid4(),
        slug="nimbuscart",
        name="NimbusCart",
    )


def make_pdf_upload_bytes() -> bytes:
    """Build a digital PDF that travels through the real upload endpoint."""
    pdf_document = pymupdf.open()

    try:
        page = pdf_document.new_page()
        page.insert_text((72, 72), "Redis PDF Investigation")
        page.insert_text((72, 92), "Authorization: Bearer example-token-123")
        page.insert_text((72, 112), "Inspect Redis eviction policy and memory usage.")
        return pdf_document.tobytes()
    finally:
        pdf_document.close()


def test_document_upload_validates_redacts_commits_and_audits_safe_text() -> None:
    session = Mock()
    tenant = make_tenant()

    # Ingestion checks whether this document path is new.
    session.scalar.return_value = None
    app.dependency_overrides[get_database_session] = lambda: session
    app.dependency_overrides[get_authorized_document_write_tenant] = lambda: tenant
    app.dependency_overrides[get_redacted_document_store] = lambda: None
    cognito_principal = AuthenticatedPrincipal(
        user_id=uuid4(),
        identity_subject="cognito-subject-123",
        display_name="Cognito Test Administrator",
        authentication_source="cognito",
    )
    app.dependency_overrides[get_current_principal] = lambda: cognito_principal
    try:
        response = client.post(
            "/api/v1/documents",
            files={
                "uploaded_file": (
                    "Checkout Runbook.md",
                    (
                        b"# Checkout Runbook\n\n"
                        b"Authorization: Bearer example-token-123\n"
                        b"Inspect Redis eviction metrics."
                    ),
                    "text/markdown",
                )
            },
        )
    finally:
        app.dependency_overrides.clear()

    stored_objects = [call.args[0] for call in session.add.call_args_list]
    stored_document = next(
        stored_object
        for stored_object in stored_objects
        if isinstance(stored_object, KnowledgeDocument)
    )
    audit_event = next(
        stored_object for stored_object in stored_objects if isinstance(stored_object, AuditEvent)
    )

    assert response.status_code == 200
    assert response.headers["x-request-id"]
    assert response.json() == {
        "status": "accepted",
        "action": "created",
        "tenant": "nimbuscart",
        "source_path": "uploads/checkout-runbook.md",
    }
    assert stored_document.content == (
        "# Checkout Runbook\n\n"
        "Authorization: Bearer [REDACTED: BEARER_TOKEN]\n"
        "Inspect Redis eviction metrics."
    )
    assert stored_document.access_level == "organization"
    assert stored_document.document_metadata == {
        "content_type": "text/markdown",
        "ingestion_source": "api-upload",
        "redaction": {
            "applied": True,
            "count": 1,
            "types": ["BEARER_TOKEN"],
        },
    }
    assert audit_event.tenant_id == tenant.id
    assert audit_event.event_type == "document.upload"
    assert audit_event.outcome == "succeeded"
    assert audit_event.actor_type == "cognito_user"
    assert audit_event.actor_id == "cognito-subject-123"
    assert audit_event.request_id == response.headers["x-request-id"]
    assert audit_event.event_metadata == {
        "upload_status": "accepted",
        "source_path": "uploads/checkout-runbook.md",
        "content_type": "text/markdown",
        "ingestion_action": "created",
    }
    session.commit.assert_called_once()


def test_document_upload_rejects_and_audits_unsupported_files() -> None:
    session = Mock()
    tenant = make_tenant()

    app.dependency_overrides[get_database_session] = lambda: session
    app.dependency_overrides[get_authorized_document_write_tenant] = lambda: tenant
    app.dependency_overrides[get_redacted_document_store] = lambda: None

    try:
        response = client.post(
            "/api/v1/documents",
            files={
                "uploaded_file": (
                    "deployment-record.exe",
                    b"not a supported file type",
                    "application/pdf",
                )
            },
        )
    finally:
        app.dependency_overrides.clear()

    audit_event = session.add.call_args.args[0]

    assert response.status_code == 400
    assert response.json()["detail"] == "Only .md, .txt, .pdf, and .docx uploads are supported"
    assert audit_event.tenant_id == tenant.id
    assert audit_event.event_type == "document.upload"
    assert audit_event.outcome == "denied"
    assert audit_event.request_id == response.headers["x-request-id"]
    assert audit_event.event_metadata == {
        "upload_status": "validation_failed",
        "source_path": None,
        "content_type": None,
        "ingestion_action": None,
    }
    session.scalar.assert_not_called()
    session.commit.assert_called_once()


def test_document_upload_extracts_redacts_and_audits_pdf_content() -> None:
    """PDF uploads use the same redaction, ingestion, and audit boundaries as text."""
    session = Mock()
    tenant = make_tenant()

    session.scalar.return_value = None
    app.dependency_overrides[get_database_session] = lambda: session
    app.dependency_overrides[get_authorized_document_write_tenant] = lambda: tenant
    app.dependency_overrides[get_redacted_document_store] = lambda: None

    try:
        response = client.post(
            "/api/v1/documents",
            files={
                "uploaded_file": (
                    "Redis Investigation.pdf",
                    make_pdf_upload_bytes(),
                    "application/pdf",
                )
            },
        )
    finally:
        app.dependency_overrides.clear()

    stored_objects = [call.args[0] for call in session.add.call_args_list]
    stored_document = next(
        stored_object
        for stored_object in stored_objects
        if isinstance(stored_object, KnowledgeDocument)
    )
    audit_event = next(
        stored_object for stored_object in stored_objects if isinstance(stored_object, AuditEvent)
    )

    assert response.status_code == 200
    assert response.json()["source_path"] == "uploads/redis-investigation.pdf"

    # The PDF page marker is retained, but the bearer token never reaches storage.
    assert "[PDF page 1]" in stored_document.content
    assert "Redis PDF Investigation" in stored_document.content
    assert "Authorization: Bearer [REDACTED: BEARER_TOKEN]" in stored_document.content
    assert "example-token-123" not in stored_document.content

    assert stored_document.document_metadata["content_type"] == "application/pdf"
    assert stored_document.document_metadata["redaction"] == {
        "applied": True,
        "count": 1,
        "types": ["BEARER_TOKEN"],
    }

    assert audit_event.tenant_id == tenant.id
    assert audit_event.event_type == "document.upload"
    assert audit_event.outcome == "succeeded"
    assert audit_event.event_metadata == {
        "upload_status": "accepted",
        "source_path": "uploads/redis-investigation.pdf",
        "content_type": "application/pdf",
        "ingestion_action": "created",
    }


def test_document_upload_returns_safe_503_when_configured_storage_is_unavailable() -> None:
    session = Mock()
    tenant = make_tenant()

    session.scalar.return_value = None
    app.dependency_overrides[get_database_session] = lambda: session
    app.dependency_overrides[get_authorized_document_write_tenant] = lambda: tenant
    app.dependency_overrides[get_redacted_document_store] = lambda: (
        UnavailableRedactedDocumentStore()
    )

    try:
        response = client.post(
            "/api/v1/documents",
            files={
                "uploaded_file": (
                    "redis-investigation.md",
                    b"# Redis Investigation\n\nInspect eviction policy.",
                    "text/markdown",
                )
            },
        )
    finally:
        app.dependency_overrides.clear()

    audit_event = session.add.call_args.args[0]

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Document storage is temporarily unavailable. Try again later."
    }
    assert audit_event.tenant_id == tenant.id
    assert audit_event.event_type == "document.upload"
    assert audit_event.outcome == "failed"
    assert audit_event.request_id == response.headers["x-request-id"]
    assert audit_event.event_metadata == {
        "upload_status": "storage_unavailable",
        "source_path": None,
        "content_type": None,
        "ingestion_action": None,
    }
    session.rollback.assert_called_once()
    session.commit.assert_called_once()


def test_document_upload_accepts_a_restricted_access_level() -> None:
    """Authorized uploaders may explicitly classify a new document as restricted."""
    session = Mock()
    tenant = make_tenant()
    session.scalar.return_value = None

    app.dependency_overrides[get_database_session] = lambda: session
    app.dependency_overrides[get_authorized_document_write_tenant] = lambda: tenant
    app.dependency_overrides[get_redacted_document_store] = lambda: None

    try:
        response = client.post(
            "/api/v1/documents",
            data={"access_level": "restricted"},
            files={
                "uploaded_file": (
                    "restricted-runbook.md",
                    b"# Restricted Runbook\n\nInspect the connection pool.",
                    "text/markdown",
                )
            },
        )
    finally:
        app.dependency_overrides.clear()

    stored_document = next(
        call.args[0]
        for call in session.add.call_args_list
        if isinstance(call.args[0], KnowledgeDocument)
    )

    assert response.status_code == 200
    assert stored_document.access_level == "restricted"
