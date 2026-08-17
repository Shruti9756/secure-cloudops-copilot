import pytest

from api_client import (
    ApiSource,
    GuardedApiAnswer,
    JsonHttpResponse,
    SecureCloudOpsApiClient,
    SecureCloudOpsApiProtocolError,
    SecureCloudOpsApiRequestError,
)


class FakeJsonHttpTransport:
    """Fake transport that records adapter calls without starting Docker."""

    def __init__(self, response: JsonHttpResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, object], int]] = []

    def post_json(
        self,
        *,
        url: str,
        payload: dict[str, object],
        timeout_seconds: int,
    ) -> JsonHttpResponse:
        self.calls.append((url, payload, timeout_seconds))
        return self.response


def make_success_response() -> JsonHttpResponse:
    return JsonHttpResponse(
        status_code=200,
        payload={
            "status": "grounded",
            "answer": "Inspect the Redis eviction policy.",
            "tenant": "nimbuscart",
            "embedding_model": "mxbai-embed-large",
            "generation_model": "qwen3:4b-instruct",
            "sources": [
                {
                    "source_identifier": "runbooks/checkout-latency.md#chunk-1",
                    "document_title": "Runbook: Checkout Latency Investigation",
                    "cosine_distance": 0.3424,
                }
            ],
        },
        headers={"x-cache": "HIT"},
    )


def test_adapter_calls_only_the_fixed_guarded_ask_endpoint() -> None:
    transport = FakeJsonHttpTransport(make_success_response())
    client = SecureCloudOpsApiClient(
        api_base_url="http://api.internal/",
        transport=transport,
    )

    answer = client.ask(
        question="What should I investigate if Redis eviction count rises?",
        limit=2,
    )

    assert answer == GuardedApiAnswer(
        status="grounded",
        answer="Inspect the Redis eviction policy.",
        tenant="nimbuscart",
        embedding_model="mxbai-embed-large",
        generation_model="qwen3:4b-instruct",
        sources=(
            ApiSource(
                source_identifier="runbooks/checkout-latency.md#chunk-1",
                document_title="Runbook: Checkout Latency Investigation",
                cosine_distance=0.3424,
            ),
        ),
        cache_status="HIT",
    )
    assert transport.calls == [
        (
            "http://api.internal/api/v1/ask",
            {
                "question": "What should I investigate if Redis eviction count rises?",
                "limit": 2,
            },
            60,
        )
    ]


def test_adapter_preserves_a_safe_rate_limit_rejection() -> None:
    transport = FakeJsonHttpTransport(
        JsonHttpResponse(
            status_code=429,
            payload={"detail": "Too many requests. Retry after the current rate-limit window."},
            headers={"Retry-After": "42"},
        )
    )
    client = SecureCloudOpsApiClient(transport=transport)

    with pytest.raises(SecureCloudOpsApiRequestError) as error:
        client.ask(question="Why did checkout latency increase?", limit=2)

    assert error.value.status_code == 429
    assert error.value.detail == ("Too many requests. Retry after the current rate-limit window.")
    assert error.value.retry_after_seconds == 42


def test_adapter_rejects_malformed_success_responses() -> None:
    malformed_response = make_success_response()
    malformed_response = JsonHttpResponse(
        status_code=malformed_response.status_code,
        payload={
            **malformed_response.payload,
            "sources": "not a list",
        },
        headers=malformed_response.headers,
    )
    client = SecureCloudOpsApiClient(transport=FakeJsonHttpTransport(malformed_response))

    with pytest.raises(SecureCloudOpsApiProtocolError):
        client.ask(question="Why did checkout latency increase?", limit=2)


def test_adapter_rejects_an_empty_base_url() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        SecureCloudOpsApiClient(api_base_url="   ")
