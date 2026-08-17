from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient

from app.main import app, get_database_session

client = TestClient(app)


def install_fake_session(document: object | None) -> Mock:
    """Replace PostgreSQL with a predictable session for endpoint tests."""
    session = Mock()
    session.scalar.return_value = document
    app.dependency_overrides[get_database_session] = lambda: session
    return session


def test_runbook_context_returns_only_the_server_scoped_indexed_record() -> None:
    document = SimpleNamespace(
        title="Runbook: Checkout Latency Investigation",
        source_path="runbooks/checkout-latency.md",
        content="# Runbook: Checkout Latency Investigation\n\nApproved runbook context.",
    )
    session = install_fake_session(document)

    try:
        response = client.get("/api/v1/runbooks/checkout-latency")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "tenant": "nimbuscart",
        "runbook_name": "checkout-latency",
        "title": "Runbook: Checkout Latency Investigation",
        "source_identifier": "runbooks/checkout-latency.md",
        "content": "# Runbook: Checkout Latency Investigation\n\nApproved runbook context.",
    }
    session.scalar.assert_called_once()


def test_runbook_context_returns_404_when_the_approved_record_does_not_exist() -> None:
    session = install_fake_session(None)

    try:
        response = client.get("/api/v1/runbooks/payment-failure")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Approved runbook context was not found.",
    }
    session.scalar.assert_called_once()


def test_runbook_context_rejects_invalid_name_shapes() -> None:
    session = install_fake_session(None)

    try:
        response = client.get("/api/v1/runbooks/Checkout_Latency")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    session.scalar.assert_not_called()
