from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class EmbeddingResult:
    """A validated vector and the metadata needed to store it safely."""

    vector: list[float]
    input_text_token_count: int
    model_id: str


class EmbeddingProvider(Protocol):
    """Any provider that can embed one non-empty piece of text.

    Bedrock, Ollama, and test fakes all satisfy this contract without
    inheriting from a shared base class.
    """

    def embed(self, text: str) -> EmbeddingResult: ...
