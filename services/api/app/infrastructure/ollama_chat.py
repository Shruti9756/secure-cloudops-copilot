import json
from collections.abc import Callable, Sequence
from typing import Any
from urllib.request import Request, urlopen

from app.core.config import Settings, get_settings
from app.services.chat import ChatCompletion, ChatMessage

# The 4B instruct model follows strict citation rules more reliably for this RAG demo.
OLLAMA_QWEN3_4B_INSTRUCT_MODEL_ID = "qwen3:4b-instruct"
OLLAMA_CHAT_TIMEOUT_SECONDS = 300

# Local CPU inference must stay bounded; grounded incident answers should be concise.
OLLAMA_MAX_GENERATION_TOKENS = 64
ALLOWED_CHAT_ROLES = frozenset({"assistant", "system", "user"})

JsonObject = dict[str, Any]
PostJson = Callable[[str, JsonObject], JsonObject]


class OllamaChatClient:
    """Generate one local chat response through Ollama's HTTP API."""

    def __init__(
        self,
        settings: Settings | None = None,
        post_json: PostJson | None = None,
    ) -> None:
        self._settings = settings or get_settings()

        # Tests inject a fake HTTP function; production uses Python's HTTP client.
        self._post_json = post_json or _post_json

    def chat(self, messages: Sequence[ChatMessage]) -> ChatCompletion:
        """Send validated, ordered chat messages and return one complete response."""
        serialized_messages = _serialize_messages(messages)

        response_payload = self._post_json(
            f"{self._settings.ollama_base_url.rstrip('/')}/api/chat",
            {
                "model": OLLAMA_QWEN3_4B_INSTRUCT_MODEL_ID,
                "messages": serialized_messages,
                # One complete response is easier to validate than streamed fragments.
                "stream": False,
                # RAG answers need final conclusions, not a long internal reasoning trace.
                "think": False,
                "keep_alive": "5m",
                "options": {
                    "temperature": 0.2,
                    # A concise incident answer is sufficient and faster on a CPU.
                    "num_predict": OLLAMA_MAX_GENERATION_TOKENS,
                },
            },
        )

        return _parse_chat_completion(response_payload)


def _serialize_messages(messages: Sequence[ChatMessage]) -> list[JsonObject]:
    """Validate message roles/content before any untrusted value reaches Ollama."""
    if not messages:
        raise ValueError("At least one chat message is required")

    serialized_messages: list[JsonObject] = []

    for message in messages:
        role = message.role.strip()
        content = message.content.strip()

        if role not in ALLOWED_CHAT_ROLES:
            raise ValueError(f"Unsupported chat role: {role}")

        if not content:
            raise ValueError("Chat message content must not be empty")

        serialized_messages.append(
            {
                "role": role,
                "content": content,
            }
        )

    return serialized_messages


def _parse_chat_completion(response_payload: JsonObject) -> ChatCompletion:
    """Validate Ollama's response before exposing it to the RAG application."""
    if response_payload.get("done") is not True:
        raise ValueError("Ollama did not return a completed chat response")

    model_id = response_payload.get("model")

    if model_id != OLLAMA_QWEN3_4B_INSTRUCT_MODEL_ID:
        raise ValueError("Ollama returned an unexpected chat model")

    message = response_payload.get("message")

    if not isinstance(message, dict) or message.get("role") != "assistant":
        raise ValueError("Ollama returned an invalid assistant message")

    content = message.get("content")

    if not isinstance(content, str) or not content.strip():
        raise ValueError("Ollama returned an empty assistant response")

    return ChatCompletion(
        content=content.strip(),
        model_id=model_id,
        prompt_token_count=_read_nonnegative_int(response_payload, "prompt_eval_count"),
        completion_token_count=_read_nonnegative_int(response_payload, "eval_count"),
    )


def _read_nonnegative_int(response_payload: JsonObject, field_name: str) -> int:
    """Read Ollama usage fields while rejecting missing, boolean, or negative values."""
    value = response_payload.get(field_name)

    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"Ollama returned an invalid {field_name}")

    return value


def _post_json(url: str, payload: JsonObject) -> JsonObject:
    """Send one JSON request to the local Ollama container."""
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    # CPU generation can take longer than embedding, especially on the first request.
    with urlopen(request, timeout=OLLAMA_CHAT_TIMEOUT_SECONDS) as response:
        response_payload = json.loads(response.read().decode("utf-8"))

    if not isinstance(response_payload, dict):
        raise TypeError("Ollama returned a non-object JSON response")

    return response_payload
