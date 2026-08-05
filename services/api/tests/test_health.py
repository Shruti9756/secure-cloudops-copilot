import pytest
from fastapi.testclient import TestClient

from app.main import APP_VERSION, app

client = TestClient(app)


def test_health_endpoint_returns_expected_status() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "secure-cloudops-api",
        "version": APP_VERSION,
    }


def test_versioned_status_endpoint_returns_expected_status() -> None:
    response = client.get("/api/v1/status")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "secure-cloudops-api"


def test_ready_endpoint_returns_ready_when_dependencies_are_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.main.postgres_is_available", lambda: True)
    monkeypatch.setattr("app.main.redis_is_available", lambda: True)

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "dependencies": {
            "postgres": "ok",
            "redis": "ok",
        },
    }


def test_ready_endpoint_returns_503_when_a_dependency_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.main.postgres_is_available", lambda: False)
    monkeypatch.setattr("app.main.redis_is_available", lambda: True)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "dependencies": {
            "postgres": "unavailable",
            "redis": "ok",
        },
    }
