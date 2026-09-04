from unittest.mock import Mock
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app, get_current_principal, get_database_session
from app.services.authorization import AuthenticatedPrincipal

client = TestClient(app)


def make_principal() -> AuthenticatedPrincipal:
    """Create one authenticated caller without requiring Cognito in this unit test."""
    return AuthenticatedPrincipal(
        user_id=uuid4(),
        identity_subject="workspace-test-user",
        display_name="Workspace Test User",
    )


def test_workspace_endpoint_returns_only_membership_derived_workspaces() -> None:
    """Workspace discovery joins memberships to tenants through organization ownership."""
    principal = make_principal()
    session = Mock()
    session.execute.return_value = [
        ("nimbuscart", "NimbusCart", "admin"),
        ("platform", "Platform Engineering", "engineer"),
    ]

    app.dependency_overrides[get_database_session] = lambda: session
    app.dependency_overrides[get_current_principal] = lambda: principal

    try:
        response = client.get("/api/v1/workspaces")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "workspaces": [
            {
                "slug": "nimbuscart",
                "name": "NimbusCart",
                "role": "admin",
            },
            {
                "slug": "platform",
                "name": "Platform Engineering",
                "role": "engineer",
            },
        ]
    }

    statement_sql = str(session.execute.call_args.args[0])
    assert "memberships.organization_id = tenants.organization_id" in statement_sql
    assert "memberships.user_id" in statement_sql


def test_workspace_endpoint_returns_an_empty_list_for_a_user_without_memberships() -> None:
    """A signed-in user with no memberships must not infer any workspace details."""
    session = Mock()
    session.execute.return_value = []

    app.dependency_overrides[get_database_session] = lambda: session
    app.dependency_overrides[get_current_principal] = make_principal

    try:
        response = client.get("/api/v1/workspaces")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"workspaces": []}


def test_authenticated_session_endpoint_records_safe_cognito_audit_event() -> None:
    """A verified Cognito session creates an audit record without token data."""
    principal = AuthenticatedPrincipal(
        user_id=uuid4(),
        identity_subject="cognito-session-test-user",
        display_name="Cognito Session Test User",
        authentication_source="cognito",
    )
    session = Mock()

    app.dependency_overrides[get_database_session] = lambda: session
    app.dependency_overrides[get_current_principal] = lambda: principal

    try:
        response = client.post("/api/v1/identity/session")
    finally:
        app.dependency_overrides.clear()

    audit_event = session.add.call_args.args[0]

    assert response.status_code == 200
    assert response.json() == {"status": "authenticated"}
    assert audit_event.tenant_id is None
    assert audit_event.organization_id is None
    assert audit_event.event_type == "identity.api_session_started"
    assert audit_event.outcome == "succeeded"
    assert audit_event.actor_type == "cognito_user"
    assert audit_event.actor_id == "cognito-session-test-user"
    assert audit_event.request_id == response.headers["x-request-id"]
    assert audit_event.event_metadata == {
        "authentication_status": "access_token_accepted",
    }
    session.commit.assert_called_once_with()
