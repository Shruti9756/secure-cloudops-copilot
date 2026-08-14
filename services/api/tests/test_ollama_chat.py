from typing import Any

import pytest

from app.core.config import Settings
from app.infrastructure.ollama_chat import (
    OLLAMA_QWEN3_4B_INSTRUCT_MODEL_ID,
    OllamaChatClient,
)
from app.services.chat import ChatMessage


def make_settings() -> Settings:
    """Provide a fake local URL without calling Docker during unit tests."""
    return Settings(
        database_url="postgresql+psycopg://unused",
        redis_url="redis://unused",
        ollama_base_url="http://ollama.test:11434",
    )


def make_valid_response() -> dict[str, Any]:
    """Return the smallest valid completed Ollama chat response."""
    return {
        "model": OLLAMA_QWEN3_4B_INSTRUCT_MODEL_ID,
        "message": {
            "role": "assistant",
            "content": "The deployment record suggests a connection-pool hypothesis.",
        },
        "prompt_eval_count": 42,
        "eval_count": 18,
        "done": True,
    }


def test_chat_posts_valid_messages_and_returns_completion() -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
        calls.append((url, payload))
        return make_valid_response()

    client = OllamaChatClient(
        settings=make_settings(),
        post_json=fake_post_json,
    )

    result = client.chat(
        [
            ChatMessage(role="system", content="Use only the supplied evidence."),
            ChatMessage(role="user", content="Why is checkout slow?"),
        ]
    )

    assert result.model_id == OLLAMA_QWEN3_4B_INSTRUCT_MODEL_ID
    assert result.content == "The deployment record suggests a connection-pool hypothesis."
    assert result.prompt_token_count == 42
    assert result.completion_token_count == 18
    assert calls == [
        (
            "http://ollama.test:11434/api/chat",
            {
                "model": OLLAMA_QWEN3_4B_INSTRUCT_MODEL_ID,
                "messages": [
                    {
                        "role": "system",
                        "content": "Use only the supplied evidence.",
                    },
                    {
                        "role": "user",
                        "content": "Why is checkout slow?",
                    },
                ],
                "stream": False,
                "think": False,
                "keep_alive": "5m",
                "options": {
                    "temperature": 0.2,
                    "num_predict": 250,
                },
            },
        )
    ]


def test_chat_rejects_empty_messages_without_an_http_request() -> None:
    def should_not_be_called(url: str, payload: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError(f"Unexpected HTTP request to {url} with {payload}")

    client = OllamaChatClient(
        settings=make_settings(),
        post_json=should_not_be_called,
    )

    with pytest.raises(ValueError, match="At least one chat message"):
        client.chat([])


def test_chat_rejects_an_unsupported_message_role() -> None:
    client = OllamaChatClient(
        settings=make_settings(),
        post_json=lambda url, payload: make_valid_response(),
    )

    with pytest.raises(ValueError, match="Unsupported chat role"):
        client.chat(
            [
                ChatMessage(
                    role="tool",
                    content="This role is intentionally unsupported in Version 1.",
                )
            ]
        )


def test_chat_rejects_a_response_from_an_unexpected_model() -> None:
    def fake_post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = make_valid_response()
        response["model"] = "unexpected-model"
        return response

    client = OllamaChatClient(
        settings=make_settings(),
        post_json=fake_post_json,
    )

    with pytest.raises(ValueError, match="unexpected chat model"):
        client.chat(
            [
                ChatMessage(role="user", content="Why is checkout slow?"),
            ]
        )
