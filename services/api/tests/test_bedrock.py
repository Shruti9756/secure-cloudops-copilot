import json
from typing import Any

import pytest

from app.core.config import Settings
from app.infrastructure.bedrock import (
    TITAN_TEXT_EMBEDDINGS_V2_DIMENSIONS,
    TITAN_TEXT_EMBEDDINGS_V2_MODEL_ID,
    BedrockEmbeddingClient,
)


class FakeResponseBody:
    """Mimics the streaming response body Boto3 normally returns."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


class FakeBedrockRuntimeClient:
    """Captures requests and returns a controlled response without contacting AWS."""

    def __init__(self, response_payload: dict[str, Any]) -> None:
        self.calls: list[dict[str, Any]] = []
        self._response_payload = response_payload

    def invoke_model(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)

        return {"body": FakeResponseBody(self._response_payload)}


def make_settings() -> Settings:
    """Provide only the settings required by this isolated unit test."""
    return Settings(
        database_url="postgresql+psycopg://unused",
        redis_url="redis://unused",
        aws_region="us-east-1",
    )


def test_embed_uses_titan_v2_and_returns_a_valid_embedding() -> None:
    fake_client = FakeBedrockRuntimeClient(
        {
            "embedding": [0.01] * TITAN_TEXT_EMBEDDINGS_V2_DIMENSIONS,
            "inputTextTokenCount": 7,
        }
    )
    embedding_client = BedrockEmbeddingClient(
        settings=make_settings(),
        client=fake_client,
    )

    result = embedding_client.embed("Investigate checkout latency.")

    assert result.model_id == TITAN_TEXT_EMBEDDINGS_V2_MODEL_ID
    assert len(result.vector) == TITAN_TEXT_EMBEDDINGS_V2_DIMENSIONS
    assert result.input_text_token_count == 7

    request_body = json.loads(fake_client.calls[0]["body"])
    assert fake_client.calls[0]["modelId"] == TITAN_TEXT_EMBEDDINGS_V2_MODEL_ID
    assert request_body["inputText"] == "Investigate checkout latency."
    assert request_body["dimensions"] == TITAN_TEXT_EMBEDDINGS_V2_DIMENSIONS
    assert request_body["normalize"] is True


def test_embed_rejects_empty_text_without_contacting_bedrock() -> None:
    fake_client = FakeBedrockRuntimeClient({})
    embedding_client = BedrockEmbeddingClient(
        settings=make_settings(),
        client=fake_client,
    )

    with pytest.raises(ValueError, match="must not be empty"):
        embedding_client.embed("   ")

    assert fake_client.calls == []
