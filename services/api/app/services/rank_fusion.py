from collections.abc import Sequence
from dataclasses import dataclass

DEFAULT_RRF_K = 60


@dataclass(frozen=True)
class FusedRankedSource:
    """One source ranked by reciprocal-rank fusion across retrieval strategies."""

    source_identifier: str
    rrf_score: float
    semantic_rank: int | None
    lexical_rank: int | None


def fuse_ranked_source_identifiers(
    semantic_source_identifiers: Sequence[str],
    lexical_source_identifiers: Sequence[str],
    *,
    limit: int,
    rrf_k: int = DEFAULT_RRF_K,
) -> tuple[FusedRankedSource, ...]:
    """Combine semantic and lexical rankings without comparing raw score scales."""

    if isinstance(limit, bool) or not isinstance(limit, int):
        raise TypeError("Fusion limit must be an integer")

    if limit < 1:
        raise ValueError("Fusion limit must be at least 1")

    if isinstance(rrf_k, bool) or not isinstance(rrf_k, int):
        raise TypeError("RRF k must be an integer")

    if rrf_k < 1:
        raise ValueError("RRF k must be at least 1")

    semantic_sources = _normalize_ranked_source_identifiers(
        semantic_source_identifiers,
        field_name="Semantic source identifiers",
    )
    lexical_sources = _normalize_ranked_source_identifiers(
        lexical_source_identifiers,
        field_name="Lexical source identifiers",
    )

    semantic_ranks = {
        source_identifier: rank for rank, source_identifier in enumerate(semantic_sources, start=1)
    }
    lexical_ranks = {
        source_identifier: rank for rank, source_identifier in enumerate(lexical_sources, start=1)
    }

    fused_sources = [
        FusedRankedSource(
            source_identifier=source_identifier,
            rrf_score=_rrf_score(
                semantic_rank=semantic_ranks.get(source_identifier),
                lexical_rank=lexical_ranks.get(source_identifier),
                rrf_k=rrf_k,
            ),
            semantic_rank=semantic_ranks.get(source_identifier),
            lexical_rank=lexical_ranks.get(source_identifier),
        )
        for source_identifier in set(semantic_ranks) | set(lexical_ranks)
    ]

    return tuple(
        sorted(
            fused_sources,
            key=_fused_source_sort_key,
        )[:limit]
    )


def _normalize_ranked_source_identifiers(
    source_identifiers: Sequence[str],
    *,
    field_name: str,
) -> tuple[str, ...]:
    """Validate, trim, and deduplicate ranked source IDs in first-seen order."""

    if isinstance(source_identifiers, str):
        raise TypeError(f"{field_name} must be a sequence of strings")

    normalized_source_identifiers: list[str] = []

    for source_identifier in source_identifiers:
        if not isinstance(source_identifier, str):
            raise TypeError(f"{field_name} must contain only strings")

        normalized_source_identifier = source_identifier.strip()

        if not normalized_source_identifier:
            raise ValueError(f"{field_name} must not contain empty values")

        normalized_source_identifiers.append(normalized_source_identifier)

    return tuple(dict.fromkeys(normalized_source_identifiers))


def _rrf_score(
    *,
    semantic_rank: int | None,
    lexical_rank: int | None,
    rrf_k: int,
) -> float:
    """Add one reciprocal-rank contribution for each retriever that found a source."""

    score = 0.0

    if semantic_rank is not None:
        score += 1 / (rrf_k + semantic_rank)

    if lexical_rank is not None:
        score += 1 / (rrf_k + lexical_rank)

    return score


def _fused_source_sort_key(
    fused_source: FusedRankedSource,
) -> tuple[float, float, float, str]:
    """Use stable tie-breakers so the same inputs always produce the same order."""

    semantic_rank = (
        float(fused_source.semantic_rank)
        if fused_source.semantic_rank is not None
        else float("inf")
    )
    lexical_rank = (
        float(fused_source.lexical_rank) if fused_source.lexical_rank is not None else float("inf")
    )

    return (
        -fused_source.rrf_score,
        semantic_rank,
        lexical_rank,
        fused_source.source_identifier,
    )
