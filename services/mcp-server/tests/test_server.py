import pytest

from api_client import (
    ApiSource,
    GuardedApiAnswer,
    SecureCloudOpsApiRequestError,
)
from server import (
    SERVER_NAME,
    SERVER_VERSION,
    get_investigation_scope_payload,
    search_incident_knowledge_payload,
)


class FakeInvestigationApiClient:
    """Fake guarded API used to test MCP tool behavior without Docker."""

    def __init__(
        self,
        *,
        answer: GuardedApiAnswer | None = None,
        error: Exception | None = None,
    ) -> None:
        self.answer = answer
        self.error = error
        self.calls: list[tuple[str, int]] = []

    def ask(self, *, question: str, limit: int) -> GuardedApiAnswer:
        self.calls.append((question, limit))

        if self.error is not None:
            raise self.error

        assert self.answer is not None
        return self.answer


def make_grounded_answer() -> GuardedApiAnswer:
    return GuardedApiAnswer(
        status="grounded",
        answer="Inspect the Redis eviction policy and recent cache changes.",
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


def test_investigation_scope_describes_the_server_identity() -> None:
    scope = get_investigation_scope_payload()

    assert scope["server_name"] == SERVER_NAME
    assert scope["server_version"] == SERVER_VERSION
    assert scope["transport"] == "stdio"
    assert scope["mode"] == "read_only"


def test_investigation_scope_denies_dangerous_operations() -> None:
    scope = get_investigation_scope_payload()

    assert scope["allowed_operations"] == [
        "search tenant-scoped incident knowledge",
        "retrieve approved deployment context",
        "retrieve approved runbook context",
    ]
    assert scope["prohibited_operations"] == [
        "arbitrary shell commands",
        "arbitrary SQL queries",
        "unrestricted AWS API calls",
        "production resource changes",
    ]


def test_search_tool_returns_only_safe_guarded_api_metadata() -> None:
    api_client = FakeInvestigationApiClient(answer=make_grounded_answer())

    result = search_incident_knowledge_payload(
        question="  What should I investigate if Redis eviction count rises?  ",
        limit=2,
        api_client=api_client,
    )

    assert api_client.calls == [("What should I investigate if Redis eviction count rises?", 2)]
    assert result == {
        "status": "grounded",
        "answer": "Inspect the Redis eviction policy and recent cache changes.",
        "tenant": "nimbuscart",
        "models": {
            "embedding": "mxbai-embed-large",
            "generation": "qwen3:4b-instruct",
        },
        "cache_status": "HIT",
        "sources": [
            {
                "source_identifier": "runbooks/checkout-latency.md#chunk-1",
                "document_title": "Runbook: Checkout Latency Investigation",
                "cosine_distance": 0.3424,
            }
        ],
    }


def test_search_tool_rejects_invalid_input_before_calling_the_api() -> None:
    api_client = FakeInvestigationApiClient(answer=make_grounded_answer())

    with pytest.raises(ValueError, match="Question must not be empty"):
        search_incident_knowledge_payload(
            question="   ",
            limit=2,
            api_client=api_client,
        )

    with pytest.raises(ValueError, match="Retrieval limit must be between"):
        search_incident_knowledge_payload(
            question="Why did checkout latency increase?",
            limit=11,
            api_client=api_client,
        )

    assert api_client.calls == []


def test_search_tool_returns_a_safe_rate_limit_rejection() -> None:
    api_client = FakeInvestigationApiClient(
        error=SecureCloudOpsApiRequestError(
            status_code=429,
            detail="Too many requests. Retry after the current rate-limit window.",
            retry_after_seconds=42,
        )
    )

    result = search_incident_knowledge_payload(
        question="Why did checkout latency increase?",
        limit=2,
        api_client=api_client,
    )

    assert result == {
        "status": "request_rejected",
        "message": "Too many requests. Retry after the current rate-limit window.",
        "retry_after_seconds": 42,
    }
