from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_metrics_endpoint_exposes_safe_http_measurements() -> None:
    """The API exposes Prometheus data without request-specific sensitive labels."""
    health_response = client.get("/health")

    assert health_response.status_code == 200

    metrics_response = client.get("/metrics")

    assert metrics_response.status_code == 200
    assert metrics_response.headers["content-type"].startswith("text/plain;")
    assert "secure_cloudops_http_requests_total" in metrics_response.text
    assert "secure_cloudops_http_request_duration_seconds_bucket" in metrics_response.text
    assert (
        'secure_cloudops_http_requests_total{method="GET",route="/health",status_code="200"}'
        in metrics_response.text
    )

    # Metrics must not become a privacy leak or a high-cardinality data store.
    assert 'request_id="' not in metrics_response.text
    assert 'tenant="' not in metrics_response.text
