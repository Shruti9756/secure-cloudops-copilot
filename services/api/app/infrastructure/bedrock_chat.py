import json
from collections.abc import Sequence
from typing import Any, Protocol

import boto3

from app.core.config import Settings, get_settings
from app.services.chat import ChatCompletion, ChatMessage


class BedrockConverseClient(Protocol):
    """Small interface that lets tests replace AWS with a fake client."""

    def converse(self, **kwargs: Any) -> dict[str, Any]: ...


class BedrockChatClient:
    """Translate our ChatProvider messages to Bedrock Converse messages."""

    def __init__(
        self,
        model_id: str,
        client: BedrockConverseClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._model_id = model_id.strip()
        if not self._model_id:
            raise ValueError("A Bedrock chat model ID is required")

        if client is None:
            selected_settings = settings or get_settings()
            client = boto3.Session(
                profile_name=selected_settings.aws_profile or None,
                region_name=selected_settings.aws_region,
            ).client("bedrock-runtime")

        self._client = client

    def chat(
        self,
        messages: Sequence[ChatMessage],
        response_format: dict[str, Any] | None = None,
    ) -> ChatCompletion:
        if not messages:
            raise ValueError("At least one chat message is required")

        system: list[dict[str, str]] = []
        conversation: list[dict[str, Any]] = []

        for message in messages:
            role = message.role.strip()
            content = message.content.strip()

            if role not in {"system", "user", "assistant"}:
                raise ValueError(f"Unsupported chat role: {role}")
            if not content:
                raise ValueError("Chat message content must not be empty")

            if role == "system":
                if conversation:
                    raise ValueError("System messages must come before conversation messages")
                system.append({"text": content})
            else:
                conversation.append({"role": role, "content": [{"text": content}]})

        if not conversation or conversation[0]["role"] != "user":
            raise ValueError("Chat conversation must start with a user message")

        if response_format is not None:
            schema_text = json.dumps(
                response_format,
                sort_keys=True,
                separators=(",", ":"),
            )
            # This is a prompt hint, NOT Bedrock-native structured output.
            # The RAG service still validates the returned JSON itself.
            system.append({"text": f"Return only JSON matching this schema: {schema_text}"})

        request: dict[str, Any] = {
            "modelId": self._model_id,
            "messages": conversation,
            "inferenceConfig": {"maxTokens": 256},
        }
        if system:
            request["system"] = system

        response = self._client.converse(**request)
        return _parse_completion(response, model_id=self._model_id)


def _parse_completion(
    response: dict[str, Any],
    *,
    model_id: str,
) -> ChatCompletion:
    if not isinstance(response, dict) or response.get("stopReason") != "end_turn":
        raise ValueError("Bedrock did not complete the chat response")

    output = response.get("output")
    message = output.get("message") if isinstance(output, dict) else None
    if not isinstance(message, dict) or message.get("role") != "assistant":
        raise ValueError("Bedrock returned an invalid assistant message")

    blocks = message.get("content")
    if (
        not isinstance(blocks, list)
        or len(blocks) != 1
        or not isinstance(blocks[0], dict)
        or not isinstance(blocks[0].get("text"), str)
        or not blocks[0]["text"].strip()
    ):
        raise ValueError("Bedrock returned an invalid text response")

    usage = response.get("usage")
    if not isinstance(usage, dict):
        raise TypeError("Bedrock returned invalid token usage")

    return ChatCompletion(
        content=blocks[0]["text"].strip(),
        model_id=model_id,
        prompt_token_count=_read_token_count(usage, "inputTokens"),
        completion_token_count=_read_token_count(usage, "outputTokens"),
    )


def _read_token_count(usage: dict[str, Any], name: str) -> int:
    value = usage.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"Bedrock returned an invalid {name}")
    return value
