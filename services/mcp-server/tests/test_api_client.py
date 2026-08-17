import pytest

from api_client import (
    ApiSource,
    DeploymentContext,
    GuardedApiAnswer,
    JsonHttpResponse,
    RunbookContext,
    SecureCloudOpsApiClient,
    SecureCloudOpsApiProtocolError,
    SecureCloudOpsApiRequestError,
)


class FakeJsonHttpTransport:
    """Fake transport that records adapter calls without starting Docker."""

    def __init__(
        self,
        *,
        post_response: JsonHttpResponse | None = None,
        get_response: JsonHttpResponse | None = None,
    ) -> None:
        self.post_response = post_response
        self.get_response = get_response
        self.post_calls: list[tuple[str, dict[str, object], int]] = []
        self.get_calls: list[tuple[str, int]] = []

    def post_json(
        self,
        *,
        url: str,
        payload: dict[str, object],
        timeout_seconds: int,
    ) -> JsonHttpResponse:
        self.post_calls.append((url, payload, timeout_seconds))

        if self.post_response is None:
            raise AssertionError("Test did not configure a POST response")

        return self.post_response

    def get_json(
        self,
        *,
        url: str,
        timeout_seconds: int,
    ) -> JsonHttpResponse:
        self.get_calls.append((url, timeout_seconds))

        if self.get_response is None:
            raise AssertionError("Test did not configure a GET response")

        return self.get_response


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


def make_deployment_context_response() -> JsonHttpResponse:
    return JsonHttpResponse(
        status_code=200,
        payload={
            "tenant": "nimbuscart",
            "service": "checkout",
            "version": "2.4.0",
            "title": "Deployment Record: checkout 2.4.0",
            "source_identifier": "deployments/checkout-2.4.0.md",
            "content": "The PostgreSQL idle timeout changed from 120 seconds to 5 seconds.",
        },
        headers={},
    )


def make_runbook_context_response() -> JsonHttpResponse:
    return JsonHttpResponse(
        status_code=200,
        payload={
            "tenant": "nimbuscart",
            "runbook_name": "checkout-latency",
            "title": "Runbook: Checkout Latency Investigation",
            "source_identifier": "runbooks/checkout-latency.md",
            "content": "Inspect deployment timing, PostgreSQL, Redis, and downstream services.",
        },
        headers={},
    )


def test_adapter_calls_only_the_fixed_guarded_ask_endpoint() -> None:
    transport = FakeJsonHttpTransport(post_response=make_success_response())
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
    assert transport.post_calls == [
        (
            "http://api.internal/api/v1/ask",
            {
                "question": "What should I investigate if Redis eviction count rises?",
                "limit": 2,
            },
            60,
        )
    ]
    assert transport.get_calls == []


def test_adapter_preserves_a_safe_rate_limit_rejection() -> None:
    transport = FakeJsonHttpTransport(
        post_response=JsonHttpResponse(
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
    malformed_response = JsonHttpResponse(
        status_code=200,
        payload={
            **make_success_response().payload,
            "sources": "not a list",
        },
        headers={},
    )
    client = SecureCloudOpsApiClient(
        transport=FakeJsonHttpTransport(post_response=malformed_response)
    )

    with pytest.raises(SecureCloudOpsApiProtocolError):
        client.ask(question="Why did checkout latency increase?", limit=2)


def test_adapter_rejects_an_empty_base_url() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        SecureCloudOpsApiClient(api_base_url="   ")


def test_adapter_calls_only_the_fixed_deployment_context_endpoint() -> None:
    transport = FakeJsonHttpTransport(get_response=make_deployment_context_response())
    client = SecureCloudOpsApiClient(
        api_base_url="http://api.internal/",
        transport=transport,
    )

    context = client.get_deployment_context(
        service=" checkout ",
        version=" 2.4.0 ",
    )

    assert context == DeploymentContext(
        tenant="nimbuscart",
        service="checkout",
        version="2.4.0",
        title="Deployment Record: checkout 2.4.0",
        source_identifier="deployments/checkout-2.4.0.md",
        content="The PostgreSQL idle timeout changed from 120 seconds to 5 seconds.",
    )
    assert transport.get_calls == [
        (
            "http://api.internal/api/v1/deployments/checkout/2.4.0",
            60,
        )
    ]
    assert transport.post_calls == []


def test_adapter_preserves_a_safe_not_found_rejection() -> None:
    transport = FakeJsonHttpTransport(
        get_response=JsonHttpResponse(
            status_code=404,
            payload={"detail": "Approved deployment context was not found."},
            headers={},
        )
    )
    client = SecureCloudOpsApiClient(transport=transport)

    with pytest.raises(SecureCloudOpsApiRequestError) as error:
        client.get_deployment_context(service="catalog", version="9.9.9")

    assert error.value.status_code == 404
    assert error.value.detail == "Approved deployment context was not found."
    assert error.value.retry_after_seconds is None


def test_adapter_rejects_unsafe_deployment_path_parts_before_network_access() -> None:
    transport = FakeJsonHttpTransport(get_response=make_deployment_context_response())
    client = SecureCloudOpsApiClient(transport=transport)

    with pytest.raises(ValueError, match="lowercase letters"):
        client.get_deployment_context(service="../ask", version="2.4.0")

    with pytest.raises(ValueError, match="major.minor.patch"):
        client.get_deployment_context(service="checkout", version="latest")

    assert transport.get_calls == []


def test_adapter_calls_only_the_fixed_runbook_context_endpoint() -> None:
    transport = FakeJsonHttpTransport(get_response=make_runbook_context_response())
    client = SecureCloudOpsApiClient(
        api_base_url="http://api.internal/",
        transport=transport,
    )

    context = client.get_runbook_context(
        runbook_name=" checkout-latency ",
    )

    assert context == RunbookContext(
        tenant="nimbuscart",
        runbook_name="checkout-latency",
        title="Runbook: Checkout Latency Investigation",
        source_identifier="runbooks/checkout-latency.md",
        content="Inspect deployment timing, PostgreSQL, Redis, and downstream services.",
    )
    assert transport.get_calls == [
        (
            "http://api.internal/api/v1/runbooks/checkout-latency",
            60,
        )
    ]
    assert transport.post_calls == []


def test_adapter_preserves_a_safe_missing_runbook_rejection() -> None:
    transport = FakeJsonHttpTransport(
        get_response=JsonHttpResponse(
            status_code=404,
            payload={"detail": "Approved runbook context was not found."},
            headers={},
        )
    )
    client = SecureCloudOpsApiClient(transport=transport)

    with pytest.raises(SecureCloudOpsApiRequestError) as error:
        client.get_runbook_context(runbook_name="payment-failure")

    assert error.value.status_code == 404
    assert error.value.detail == "Approved runbook context was not found."
    assert error.value.retry_after_seconds is None


def test_adapter_rejects_unsafe_runbook_name_before_network_access() -> None:
    transport = FakeJsonHttpTransport(get_response=make_runbook_context_response())
    client = SecureCloudOpsApiClient(transport=transport)

    with pytest.raises(ValueError, match="lowercase letters"):
        client.get_runbook_context(runbook_name="../deployments")

    assert transport.get_calls == []
