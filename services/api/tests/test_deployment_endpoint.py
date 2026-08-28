from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.models import Tenant
from app.main import (
    app,
    get_authorized_knowledge_tenant,
    get_database_session,
)

client = TestClient(app)


def make_authorized_tenant() -> Tenant:
    """Create the tenant returned by the test authorization override."""
    return Tenant(
        id=uuid4(),
        organization_id=uuid4(),
        slug="nimbuscart",
        name="NimbusCart",
    )


def install_fake_session(document: object | None) -> Mock:
    """Replace PostgreSQL and authorization with predictable test dependencies."""
    session = Mock()
    session.scalar.return_value = document
    tenant = make_authorized_tenant()

    app.dependency_overrides[get_database_session] = lambda: session
    app.dependency_overrides[get_authorized_knowledge_tenant] = lambda: tenant

    return session


def test_deployment_context_returns_only_the_server_scoped_indexed_record() -> None:
    document = SimpleNamespace(
        title="Deployment Record: checkout 2.4.0",
        source_path="deployments/checkout-2.4.0.md",
        content="# Deployment Record: checkout 2.4.0\n\nApproved deployment context.",
    )
    session = install_fake_session(document)

    try:
        response = client.get("/api/v1/deployments/checkout/2.4.0")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "tenant": "nimbuscart",
        "service": "checkout",
        "version": "2.4.0",
        "title": "Deployment Record: checkout 2.4.0",
        "source_identifier": "deployments/checkout-2.4.0.md",
        "content": "# Deployment Record: checkout 2.4.0\n\nApproved deployment context.",
    }
    session.scalar.assert_called_once()


def test_deployment_context_returns_404_when_the_approved_record_does_not_exist() -> None:
    session = install_fake_session(None)

    try:
        response = client.get("/api/v1/deployments/catalog/9.9.9")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Approved deployment context was not found.",
    }
    session.scalar.assert_called_once()


def test_deployment_context_rejects_invalid_service_or_version_shapes() -> None:
    session = install_fake_session(None)

    try:
        response = client.get("/api/v1/deployments/Checkout/not-a-version")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    session.scalar.assert_not_called()
