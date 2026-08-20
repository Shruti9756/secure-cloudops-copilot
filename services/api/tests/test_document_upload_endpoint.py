from unittest.mock import Mock
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.models import AuditEvent, KnowledgeDocument, Tenant
from app.main import app, get_database_session

client = TestClient(app)


def test_document_upload_validates_redacts_commits_and_audits_safe_text() -> None:
    session = Mock()
    tenant = Tenant(
        id=uuid4(),
        slug="nimbuscart",
        name="NimbusCart",
    )
    # First query finds the tenant; second query confirms this source path is new.
    session.scalar.side_effect = [tenant, None]
    app.dependency_overrides[get_database_session] = lambda: session

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
    assert stored_document.ingestion_status == "pending"
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
    app.dependency_overrides[get_database_session] = lambda: session

    try:
        response = client.post(
            "/api/v1/documents",
            files={
                "uploaded_file": (
                    "deployment-record.pdf",
                    b"not a supported file type",
                    "application/pdf",
                )
            },
        )
    finally:
        app.dependency_overrides.clear()

    audit_event = session.add.call_args.args[0]

    assert response.status_code == 400
    assert response.json()["detail"] == "Only .md and .txt uploads are supported"
    assert audit_event.tenant_id is None
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
