import json
from typing import Any

import pytest

from app.infrastructure.bedrock_chat import BedrockChatClient
from app.services.chat import ChatCompletion, ChatMessage


def valid_response() -> dict[str, Any]:
    return {
        "stopReason": "end_turn",
        "output": {
            "message": {
                "role": "assistant",
                "content": [
                    {"text": '  {"answer":"Check the pool.","citations":["doc#chunk-0"]}  '}
                ],
            }
        },
        "usage": {"inputTokens": 42, "outputTokens": 18},
    }


class FakeConverseClient:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return self.response


def test_chat_translates_messages_and_returns_completion() -> None:
    fake = FakeConverseClient(valid_response())
    client = BedrockChatClient(model_id="test-model", client=fake)
    schema = {"type": "object", "required": ["answer", "citations"]}

    result = client.chat(
        [
            ChatMessage(role="system", content="Use only supplied evidence."),
            ChatMessage(role="user", content="What should I check?"),
        ],
        response_format=schema,
    )

    assert result == ChatCompletion(
        content='{"answer":"Check the pool.","citations":["doc#chunk-0"]}',
        model_id="test-model",
        prompt_token_count=42,
        completion_token_count=18,
    )

    assert len(fake.calls) == 1
    request = fake.calls[0]
    assert request["modelId"] == "test-model"
    assert request["messages"] == [{"role": "user", "content": [{"text": "What should I check?"}]}]
    assert request["system"][0] == {"text": "Use only supplied evidence."}
    assert (
        json.dumps(schema, sort_keys=True, separators=(",", ":")) in (request["system"][1]["text"])
    )
    assert request["inferenceConfig"] == {"maxTokens": 256}
    assert "outputConfig" not in request


@pytest.mark.parametrize(
    "messages",
    [
        [],
        [ChatMessage(role="system", content="Rules only.")],
        [ChatMessage(role="tool", content="Unsupported.")],
        [ChatMessage(role="user", content="  ")],
        [
            ChatMessage(role="user", content="Question."),
            ChatMessage(role="system", content="Too late."),
        ],
    ],
)
def test_invalid_messages_never_call_bedrock(messages: list[ChatMessage]) -> None:
    fake = FakeConverseClient(valid_response())
    client = BedrockChatClient(model_id="test-model", client=fake)

    with pytest.raises(ValueError):
        client.chat(messages)

    assert fake.calls == []


@pytest.mark.parametrize(
    "stop_reason",
    ["max_tokens", "guardrail_intervened", "tool_use"],
)
def test_incomplete_or_blocked_response_is_rejected(stop_reason: str) -> None:
    response = valid_response()
    response["stopReason"] = stop_reason
    client = BedrockChatClient(
        model_id="test-model",
        client=FakeConverseClient(response),
    )

    with pytest.raises(ValueError, match="did not complete"):
        client.chat([ChatMessage(role="user", content="Question.")])


def test_nontext_response_is_rejected() -> None:
    response = valid_response()
    response["output"]["message"]["content"] = [{"toolUse": {"name": "unexpected"}}]
    client = BedrockChatClient(
        model_id="test-model",
        client=FakeConverseClient(response),
    )

    with pytest.raises(ValueError, match="invalid text response"):
        client.chat([ChatMessage(role="user", content="Question.")])


@pytest.mark.parametrize("bad_count", [-1, True, None])
def test_invalid_token_usage_is_rejected(bad_count: Any) -> None:
    response = valid_response()
    response["usage"]["inputTokens"] = bad_count
    client = BedrockChatClient(
        model_id="test-model",
        client=FakeConverseClient(response),
    )

    with pytest.raises(ValueError, match="invalid inputTokens"):
        client.chat([ChatMessage(role="user", content="Question.")])
