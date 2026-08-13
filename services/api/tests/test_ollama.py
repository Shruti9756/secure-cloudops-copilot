from typing import Any

import pytest

from app.core.config import Settings
from app.infrastructure.ollama import (
    OLLAMA_MXBAI_EMBED_LARGE_DIMENSIONS,
    OLLAMA_MXBAI_EMBED_LARGE_MODEL_ID,
    OllamaEmbeddingClient,
)


def make_settings() -> Settings:
    """Provide the local URL without needing a real database or Redis connection."""
    return Settings(
        database_url="postgresql+psycopg://unused",
        redis_url="redis://unused",
        ollama_base_url="http://ollama.test:11434",
    )


def test_embed_uses_mxbai_and_returns_a_valid_embedding() -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
        calls.append((url, payload))

        return {
            "model": OLLAMA_MXBAI_EMBED_LARGE_MODEL_ID,
            "embeddings": [[0.01] * OLLAMA_MXBAI_EMBED_LARGE_DIMENSIONS],
            "prompt_eval_count": 7,
        }

    embedding_client = OllamaEmbeddingClient(
        settings=make_settings(),
        post_json=fake_post_json,
    )

    result = embedding_client.embed("Investigate checkout latency.")

    assert result.model_id == OLLAMA_MXBAI_EMBED_LARGE_MODEL_ID
    assert len(result.vector) == OLLAMA_MXBAI_EMBED_LARGE_DIMENSIONS
    assert result.input_text_token_count == 7
    assert calls == [
        (
            "http://ollama.test:11434/api/embed",
            {
                "model": OLLAMA_MXBAI_EMBED_LARGE_MODEL_ID,
                "input": "Investigate checkout latency.",
                "keep_alive": "5m",
            },
        )
    ]


def test_embed_rejects_empty_text_without_a_local_http_request() -> None:
    def should_not_be_called(url: str, payload: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError(f"Unexpected HTTP request to {url} with {payload}")

    embedding_client = OllamaEmbeddingClient(
        settings=make_settings(),
        post_json=should_not_be_called,
    )

    with pytest.raises(ValueError, match="must not be empty"):
        embedding_client.embed("   ")


def test_embed_rejects_an_embedding_with_the_wrong_dimension() -> None:
    def fake_post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "model": OLLAMA_MXBAI_EMBED_LARGE_MODEL_ID,
            "embeddings": [[0.01] * (OLLAMA_MXBAI_EMBED_LARGE_DIMENSIONS - 1)],
            "prompt_eval_count": 7,
        }

    embedding_client = OllamaEmbeddingClient(
        settings=make_settings(),
        post_json=fake_post_json,
    )

    with pytest.raises(ValueError, match="unexpected dimension"):
        embedding_client.embed("Investigate checkout latency.")
