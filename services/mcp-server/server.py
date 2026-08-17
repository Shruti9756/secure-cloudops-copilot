"""Read-only MCP server for SecureCloudOps Copilot."""

from typing import Protocol

from mcp.server import MCPServer

from api_client import (
    GuardedApiAnswer,
    SecureCloudOpsApiClient,
    SecureCloudOpsApiProtocolError,
    SecureCloudOpsApiRequestError,
    SecureCloudOpsApiUnavailableError,
)

SERVER_NAME = "secure-cloudops-mcp"
SERVER_VERSION = "0.1.0"
DEFAULT_RETRIEVAL_LIMIT = 3
MAX_RETRIEVAL_LIMIT = 10
MAX_QUESTION_LENGTH = 2000

# The SDK uses type hints and docstrings to publish MCP tool schemas.
mcp = MCPServer(SERVER_NAME)


class InvestigationApiClient(Protocol):
    """The narrow API capability required by the incident-search tool."""

    def ask(self, *, question: str, limit: int) -> GuardedApiAnswer:
        """Return a validated answer from the guarded SecureCloudOps API."""


def get_investigation_scope_payload() -> dict[str, object]:
    """Build a visible, testable description of this server's security boundary."""
    return {
        "server_name": SERVER_NAME,
        "server_version": SERVER_VERSION,
        "transport": "stdio",
        "mode": "read_only",
        "allowed_operations": [
            "search tenant-scoped incident knowledge",
            "retrieve approved deployment context",
            "retrieve approved runbook context",
        ],
        "prohibited_operations": [
            "arbitrary shell commands",
            "arbitrary SQL queries",
            "unrestricted AWS API calls",
            "production resource changes",
        ],
    }


def get_api_client() -> SecureCloudOpsApiClient:
    """Create the adapter with its fixed, environment-configured API base URL."""
    return SecureCloudOpsApiClient()


def search_incident_knowledge_payload(
    *,
    question: str,
    limit: int,
    api_client: InvestigationApiClient,
) -> dict[str, object]:
    """Validate tool input, call the guarded API, and return only safe metadata."""
    normalized_question = _validate_question(question)
    validated_limit = _validate_limit(limit)

    try:
        answer = api_client.ask(
            question=normalized_question,
            limit=validated_limit,
        )
    except SecureCloudOpsApiRequestError as error:
        # The adapter exposes only a safe upstream error message and retry duration.
        return {
            "status": "request_rejected",
            "message": error.detail,
            "retry_after_seconds": error.retry_after_seconds,
        }
    except SecureCloudOpsApiUnavailableError:
        return {
            "status": "unavailable",
            "message": "The guarded incident API is temporarily unavailable.",
        }
    except SecureCloudOpsApiProtocolError:
        return {
            "status": "invalid_upstream_response",
            "message": "The guarded incident API returned an unexpected response.",
        }

    return _safe_tool_answer(answer)


def _validate_question(question: str) -> str:
    """Enforce the same bounded, non-empty question shape expected by the API."""
    if not isinstance(question, str):
        raise TypeError("Question must be a string")

    normalized_question = question.strip()

    if not normalized_question:
        raise ValueError("Question must not be empty")

    if len(normalized_question) > MAX_QUESTION_LENGTH:
        raise ValueError(f"Question must not exceed {MAX_QUESTION_LENGTH} characters")

    return normalized_question


def _validate_limit(limit: int) -> int:
    """Reject oversized or non-integer tool arguments before any API call."""
    if not isinstance(limit, int) or isinstance(limit, bool):
        raise TypeError("Retrieval limit must be an integer")

    if not 1 <= limit <= MAX_RETRIEVAL_LIMIT:
        raise ValueError(f"Retrieval limit must be between 1 and {MAX_RETRIEVAL_LIMIT}")

    return limit


def _safe_tool_answer(answer: GuardedApiAnswer) -> dict[str, object]:
    """Return source metadata only; raw chunks, vectors, and transport data stay hidden."""
    return {
        "status": answer.status,
        "answer": answer.answer,
        "tenant": answer.tenant,
        "models": {
            "embedding": answer.embedding_model,
            "generation": answer.generation_model,
        },
        "cache_status": answer.cache_status,
        "sources": [
            {
                "source_identifier": source.source_identifier,
                "document_title": source.document_title,
                "cosine_distance": source.cosine_distance,
            }
            for source in answer.sources
        ],
    }


@mcp.tool()
def get_investigation_scope() -> dict[str, object]:
    """Return the capabilities and enforced safety boundaries of this MCP server."""
    return get_investigation_scope_payload()


@mcp.tool()
def search_incident_knowledge(
    question: str,
    limit: int = DEFAULT_RETRIEVAL_LIMIT,
) -> dict[str, object]:
    """Search approved incident knowledge through the guarded SecureCloudOps API.

    Args:
        question: Incident-investigation question. It must be non-empty and at most
            2,000 characters.
        limit: Maximum number of retrieved evidence sources, from 1 through 10.
    """
    return search_incident_knowledge_payload(
        question=question,
        limit=limit,
        api_client=get_api_client(),
    )


if __name__ == "__main__":
    # STDIO carries JSON-RPC messages, so this server must never use print().
    mcp.run(transport="stdio")
