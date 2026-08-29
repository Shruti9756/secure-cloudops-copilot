from unittest.mock import Mock
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.models import Tenant
from app.main import app, get_current_principal, get_database_session
from app.services.authorization import AuthenticatedPrincipal

client = TestClient(app)


def test_ask_hides_a_tenant_when_the_user_has_no_membership() -> None:
    """A valid identity without organization membership cannot reach RAG."""
    session = Mock()
    tenant = Tenant(
        id=uuid4(),
        organization_id=uuid4(),
        slug="nimbuscart",
        name="NimbusCart",
    )
    principal = AuthenticatedPrincipal(
        user_id=uuid4(),
        identity_subject="unassigned-local-user",
        display_name="Unassigned Local User",
    )

    # Authorization finds the tenant, then finds no matching membership.
    session.scalar.side_effect = [tenant, None]
    app.dependency_overrides[get_database_session] = lambda: session
    app.dependency_overrides[get_current_principal] = lambda: principal

    try:
        response = client.post(
            "/api/v1/ask",
            json={
                "question": "Why did checkout latency increase?",
                "limit": 1,
            },
            headers={"X-Workspace-Slug": "nimbuscart"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Requested tenant workspace was not found.",
    }
