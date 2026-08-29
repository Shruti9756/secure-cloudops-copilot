from unittest.mock import Mock
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.models import Membership, Tenant
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


def test_ask_hides_a_workspace_from_a_user_in_another_organization() -> None:
    """A valid role in one organization must not unlock another organization's workspace."""
    session = Mock()
    caller_organization_id = uuid4()
    other_organization_id = uuid4()
    tenant = Tenant(
        id=uuid4(),
        organization_id=other_organization_id,
        slug="otherco",
        name="OtherCo",
    )
    principal = AuthenticatedPrincipal(
        user_id=uuid4(),
        identity_subject="nimbuscart-admin",
        display_name="NimbusCart Administrator",
    )
    membership = Membership(
        organization_id=caller_organization_id,
        user_id=principal.user_id,
        role="admin",
    )

    # Even an administrator from another organization must be denied.
    session.scalar.side_effect = [tenant, membership]
    app.dependency_overrides[get_database_session] = lambda: session
    app.dependency_overrides[get_current_principal] = lambda: principal

    try:
        response = client.post(
            "/api/v1/ask",
            json={
                "question": "Show the OtherCo incident details.",
                "limit": 1,
            },
            headers={"X-Workspace-Slug": "otherco"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Requested tenant workspace was not found.",
    }
