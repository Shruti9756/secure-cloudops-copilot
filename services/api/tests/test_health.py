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