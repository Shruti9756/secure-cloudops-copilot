from unittest.mock import Mock
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.models import Membership, Tenant
from app.main import app, get_current_principal, get_database_session
from app.services.authorization import AuthenticatedPrincipal

client = TestClient(app)


def test_engineer_cannot_upload_documents() -> None:
    """A read-only engineer must not reach document ingestion."""
    session = Mock()
    tenant = Tenant(
        id=uuid4(),
        organization_id=uuid4(),
        slug="nimbuscart",
        name="NimbusCart",
    )
    principal = AuthenticatedPrincipal(
        user_id=uuid4(),
        identity_subject="read-only-engineer",
        display_name="Read Only Engineer",
    )
    membership = Membership(
        organization_id=tenant.organization_id,
        user_id=principal.user_id,
        role="engineer",
    )

    # Authorization finds the tenant and engineer membership, then denies write access.
    session.scalar.side_effect = [tenant, membership]
    app.dependency_overrides[get_database_session] = lambda: session
    app.dependency_overrides[get_current_principal] = lambda: principal

    try:
        response = client.post(
            "/api/v1/documents",
            files={
                "uploaded_file": (
                    "redis-note.md",
                    b"# Redis Note\n\nInspect eviction policy.",
                    "text/markdown",
                )
            },
            headers={"X-Workspace-Slug": "nimbuscart"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Requested tenant workspace was not found.",
    }
    audit_event = session.add.call_args.args[0]

    assert audit_event.tenant_id is None
    assert audit_event.organization_id is None
    assert audit_event.event_type == "authorization.workspace_access"
    assert audit_event.outcome == "denied"
    assert audit_event.actor_type == "local_demo"
    assert audit_event.actor_id is None
    assert audit_event.request_id == response.headers["x-request-id"]
    assert audit_event.event_metadata == {
        "authorization_status": "workspace_access_denied",
        "permission": "documents:write",
    }
    session.commit.assert_called_once_with()
