from collections.abc import Collection, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalEvaluationResult:
    """One deterministic retrieval-quality measurement at a requested rank."""

    requested_k: int
    expected_source_identifiers: tuple[str, ...]
    retrieved_source_identifiers: tuple[str, ...]
    matched_source_identifiers: tuple[str, ...]
    precision_at_k: float
    recall_at_k: float


def evaluate_retrieval_at_k(
    expected_source_identifiers: Collection[str],
    retrieved_source_identifiers: Sequence[str],
    k: int,
) -> RetrievalEvaluationResult:
    """Measure source retrieval without calling a database or model.

    Precision@k uses k as its denominator. This deliberately penalizes a
    retriever that returns fewer than k useful results.
    """

    if isinstance(k, bool) or not isinstance(k, int):
        raise TypeError("k must be an integer")

    if k < 1:
        raise ValueError("k must be at least 1")

    expected_sources = _normalize_source_identifiers(
        expected_source_identifiers,
        field_name="Expected source identifiers",
        allow_empty=False,
    )
    retrieved_sources = _normalize_source_identifiers(
        retrieved_source_identifiers,
        field_name="Retrieved source identifiers",
        allow_empty=True,
    )

    top_retrieved_sources = retrieved_sources[:k]
    expected_source_set = frozenset(expected_sources)
    matched_sources = tuple(
        source_identifier
        for source_identifier in top_retrieved_sources
        if source_identifier in expected_source_set
    )

    return RetrievalEvaluationResult(
        requested_k=k,
        expected_source_identifiers=expected_sources,
        retrieved_source_identifiers=top_retrieved_sources,
        matched_source_identifiers=matched_sources,
        precision_at_k=len(matched_sources) / k,
        recall_at_k=len(matched_sources) / len(expected_sources),
    )


def _normalize_source_identifiers(
    source_identifiers: Collection[str],
    *,
    field_name: str,
    allow_empty: bool,
) -> tuple[str, ...]:
    """Validate, trim, and deduplicate source IDs while keeping their order."""

    if isinstance(source_identifiers, str):
        raise TypeError(f"{field_name} must be a collection of strings")

    normalized_sources: list[str] = []

    for source_identifier in source_identifiers:
        if not isinstance(source_identifier, str):
            raise TypeError(f"{field_name} must contain only strings")

        normalized_source_identifier = source_identifier.strip()

        if not normalized_source_identifier:
            raise ValueError(f"{field_name} must not contain empty values")

        normalized_sources.append(normalized_source_identifier)

    unique_sources = tuple(dict.fromkeys(normalized_sources))

    if not unique_sources and not allow_empty:
        raise ValueError(f"{field_name} must not be empty")

    return unique_sources
