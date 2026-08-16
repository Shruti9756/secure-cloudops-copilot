from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_cors_allows_the_local_nextjs_origin_to_post_json() -> None:
    response = client.options(
        "/api/v1/ask",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "POST" in response.headers["access-control-allow-methods"]
    assert "content-type" in response.headers["access-control-allow-headers"].lower()


def test_cors_rejects_an_unapproved_browser_origin() -> None:
    response = client.options(
        "/api/v1/ask",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_cors_exposes_the_cache_header_to_approved_browsers() -> None:
    response = client.get(
        "/health",
        headers={"Origin": "http://localhost:3000"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    exposed_headers = response.headers["access-control-expose-headers"].lower()

    assert "retry-after" in exposed_headers
    assert "x-cache" in exposed_headers
    assert "x-ratelimit-limit" in exposed_headers
    assert "x-ratelimit-remaining" in exposed_headers
    assert "x-ratelimit-reset" in exposed_headers
