from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

MAX_ANSWER_LENGTH = 600
MAX_CITATIONS_PER_ANSWER = 10

SourceIdentifier = Annotated[str, Field(min_length=1, max_length=1024)]


class StructuredAnswer(BaseModel):
    """The only answer shape that the RAG model may return."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    answer: str = Field(min_length=1, max_length=MAX_ANSWER_LENGTH)
    citations: list[SourceIdentifier] = Field(
        min_length=1,
        max_length=MAX_CITATIONS_PER_ANSWER,
    )

    @field_validator("answer")
    @classmethod
    def answer_must_not_render_its_own_citations(cls, answer: str) -> str:
        """Keep citation rendering under deterministic server control."""
        if "[source:" in answer.casefold():
            raise ValueError("Answer text must not include rendered source citations")

        return answer

    @field_validator("citations")
    @classmethod
    def citations_must_be_unique(cls, citations: list[str]) -> list[str]:
        """One source identifier should appear only once in model output."""
        if len(citations) != len(set(citations)):
            raise ValueError("Citation source identifiers must be unique")

        return citations


def parse_structured_answer(content: str) -> StructuredAnswer:
    """Parse and validate one complete model response without exposing its errors."""
    try:
        return StructuredAnswer.model_validate_json(content)
    except ValidationError as error:
        raise ValueError(
            "The generated response did not match the required answer schema"
        ) from error


def render_answer_with_citations(answer: StructuredAnswer) -> str:
    """Create the existing user-facing citation syntax from validated JSON data."""
    rendered_citations = " ".join(
        f"[source: {source_identifier}]" for source_identifier in answer.citations
    )

    return f"{answer.answer} {rendered_citations}"
