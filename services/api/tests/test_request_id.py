from uuid import UUID

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_api_generates_unique_request_ids_and_ignores_client_values() -> None:
    first_response = client.get(
        "/health",
        headers={"X-Request-ID": "untrusted-client-value"},
    )
    second_response = client.get("/health")

    first_request_id = first_response.headers["x-request-id"]
    second_request_id = second_response.headers["x-request-id"]

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_request_id != "untrusted-client-value"
    assert UUID(first_request_id).hex == first_request_id
    assert UUID(second_request_id).hex == second_request_id
    assert first_request_id != second_request_id
