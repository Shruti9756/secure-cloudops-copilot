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
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Requested tenant workspace was not found.",
    }
    session.add.assert_not_called()
