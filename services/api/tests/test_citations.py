from uuid import uuid4

from app.services.citations import (
    source_identifier_for_chunk,
    validate_answer_citations,
)
from app.services.retrieval import RetrievedChunk


def make_chunk(
    source_path: str = "deployments/checkout-2.4.0.md",
    chunk_index: int = 0,
) -> RetrievedChunk:
    """Create a minimal retrieved chunk for deterministic citation tests."""
    return RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        source_path=source_path,
        document_title="Deployment Record: checkout 2.4.0",
        content="The idle timeout changed from 120 seconds to 5 seconds.",
        chunk_index=chunk_index,
        cosine_distance=0.12,
    )


def test_validate_answer_citations_accepts_retrieved_source_identifiers() -> None:
    deployment_chunk = make_chunk()
    runbook_chunk = make_chunk(
        source_path="runbooks/checkout-latency.md",
        chunk_index=1,
    )

    result = validate_answer_citations(
        answer_text=(
            "The timeout change is a hypothesis "
            "[source: deployments/checkout-2.4.0.md#chunk-0]. "
            "Validate connection creation rate "
            "[source: runbooks/checkout-latency.md#chunk-1]."
        ),
        retrieved_chunks=[deployment_chunk, runbook_chunk],
    )

    assert result.is_valid is True
    assert result.cited_source_identifiers == (
        "deployments/checkout-2.4.0.md#chunk-0",
        "runbooks/checkout-latency.md#chunk-1",
    )
    assert result.errors == ()


def test_validate_answer_citations_rejects_the_old_missing_source_prefix() -> None:
    chunk = make_chunk()

    result = validate_answer_citations(
        answer_text=("The timeout change is a hypothesis [deployments/checkout-2.4.0.md#chunk-0]."),
        retrieved_chunks=[chunk],
    )

    assert result.is_valid is False
    assert result.cited_source_identifiers == ()
    assert result.errors == (
        "Answer must include at least one citation in the form [source: path#chunk-index]",
    )


def test_validate_answer_citations_rejects_sources_not_in_retrieval_results() -> None:
    chunk = make_chunk()

    result = validate_answer_citations(
        answer_text=(
            "The database was confirmed healthy [source: runbooks/not-retrieved.md#chunk-0]."
        ),
        retrieved_chunks=[chunk],
    )

    assert result.is_valid is False
    assert result.cited_source_identifiers == ("runbooks/not-retrieved.md#chunk-0",)
    assert result.errors == (
        "Answer cites a source that was not retrieved: runbooks/not-retrieved.md#chunk-0",
    )


def test_validate_answer_citations_rejects_validation_without_sources() -> None:
    result = validate_answer_citations(
        answer_text=("No evidence was retrieved [source: deployments/checkout-2.4.0.md#chunk-0]."),
        retrieved_chunks=[],
    )

    assert result.is_valid is False
    assert result.cited_source_identifiers == ()
    assert result.errors == ("At least one retrieved source is required for citation validation",)


def test_source_identifier_for_chunk_uses_path_and_chunk_index() -> None:
    chunk = make_chunk(
        source_path="runbooks/checkout-latency.md",
        chunk_index=2,
    )

    assert source_identifier_for_chunk(chunk) == "runbooks/checkout-latency.md#chunk-2"
