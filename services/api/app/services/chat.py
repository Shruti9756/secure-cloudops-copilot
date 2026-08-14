from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ChatMessage:
    """One ordered message sent to a generative chat model."""

    role: str
    content: str


@dataclass(frozen=True)
class ChatCompletion:
    """A validated model response plus usage metadata for observability."""

    content: str
    model_id: str
    prompt_token_count: int
    completion_token_count: int


class ChatProvider(Protocol):
    """Any provider that can generate one response from ordered chat messages.

    Ollama, future Bedrock, and test fakes can all follow this contract without
    inheriting from a shared base class.
    """

    def chat(self, messages: Sequence[ChatMessage]) -> ChatCompletion: ...
