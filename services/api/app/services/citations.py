import re
from collections.abc import Sequence
from dataclasses import dataclass

from app.services.retrieval import RetrievedChunk

# Matches citations such as:
# [source: deployments/checkout-2.4.0.md#chunk-0]
SOURCE_CITATION_PATTERN = re.compile(r"\[source:\s*(?P<source_identifier>[^\]]+?)\s*\]")


@dataclass(frozen=True)
class CitationValidationResult:
    """The deterministic result of checking model citations against retrieved sources."""

    is_valid: bool
    cited_source_identifiers: tuple[str, ...]
    errors: tuple[str, ...]


def source_identifier_for_chunk(chunk: RetrievedChunk) -> str:
    """Build the one citation identifier that a retrieved chunk is allowed to use."""
    return f"{chunk.source_path}#chunk-{chunk.chunk_index}"


def validate_answer_citations(
    answer_text: str,
    retrieved_chunks: Sequence[RetrievedChunk],
) -> CitationValidationResult:
    """Ensure an answer cites only the chunks retrieved for this request."""
    normalized_answer = answer_text.strip()

    if not normalized_answer:
        return CitationValidationResult(
            is_valid=False,
            cited_source_identifiers=(),
            errors=("Answer must not be empty",),
        )

    if not retrieved_chunks:
        return CitationValidationResult(
            is_valid=False,
            cited_source_identifiers=(),
            errors=("At least one retrieved source is required for citation validation",),
        )

    allowed_source_identifiers = {source_identifier_for_chunk(chunk) for chunk in retrieved_chunks}
    cited_source_identifiers = tuple(
        dict.fromkeys(
            match.group("source_identifier").strip()
            for match in SOURCE_CITATION_PATTERN.finditer(normalized_answer)
        )
    )

    errors: list[str] = []

    if not cited_source_identifiers:
        errors.append(
            "Answer must include at least one citation in the form [source: path#chunk-index]"
        )

    for source_identifier in cited_source_identifiers:
        if source_identifier not in allowed_source_identifiers:
            errors.append(f"Answer cites a source that was not retrieved: {source_identifier}")

    return CitationValidationResult(
        is_valid=not errors,
        cited_source_identifiers=cited_source_identifiers,
        errors=tuple(errors),
    )
