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
