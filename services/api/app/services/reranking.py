import math
from collections.abc import Sequence
from dataclasses import dataclass

from app.services.bm25 import rank_bm25_documents, tokenize_bm25

DEFAULT_BM25_RERANK_WEIGHT = 0.01
STRUCTURED_IDENTIFIER_SEPARATORS = frozenset("._:-")


@dataclass(frozen=True)
class RerankingCandidate:
    """One retrieval candidate plus its original ranking score."""

    source_identifier: str
    search_text: str
    base_score: float


@dataclass(frozen=True)
class RerankedCandidate:
    """One candidate after query-aware BM25 reranking."""

    source_identifier: str
    base_score: float
    bm25_score: float
    normalized_bm25_score: float
    rerank_score: float


def rerank_candidates(
    query: str,
    candidates: Sequence[RerankingCandidate],
    *,
    limit: int,
    bm25_weight: float = DEFAULT_BM25_RERANK_WEIGHT,
) -> tuple[RerankedCandidate, ...]:
    """Rerank candidates when the query contains a structured identifier."""

    query_terms = tokenize_bm25(query)

    if not query_terms:
        raise ValueError("Reranking query must contain at least one searchable term")

    if isinstance(limit, bool) or not isinstance(limit, int):
        raise TypeError("Reranking limit must be an integer")

    if limit < 1:
        raise ValueError("Reranking limit must be at least 1")

    if isinstance(bm25_weight, bool) or not isinstance(bm25_weight, int | float):
        raise TypeError("BM25 reranking weight must be numeric")

    normalized_weight = float(bm25_weight)

    if not math.isfinite(normalized_weight) or normalized_weight < 0:
        raise ValueError("BM25 reranking weight must be finite and non-negative")

    normalized_candidates = _normalize_candidates(candidates)

    if not normalized_candidates:
        return ()

    structured_query_terms = tuple(
        term for term in dict.fromkeys(query_terms) if _is_structured_identifier_token(term)
    )
    bm25_scores: dict[str, float] = {}

    if structured_query_terms:
        ranked_bm25_candidates = rank_bm25_documents(
            query=" ".join(structured_query_terms),
            documents={
                candidate.source_identifier: candidate.search_text
                for candidate in normalized_candidates
            },
            limit=len(normalized_candidates),
        )
        bm25_scores = {
            candidate.source_identifier: candidate.score for candidate in ranked_bm25_candidates
        }

    maximum_bm25_score = max(bm25_scores.values(), default=0.0)
    reranked_candidates: list[RerankedCandidate] = []

    for candidate in normalized_candidates:
        bm25_score = bm25_scores.get(candidate.source_identifier, 0.0)
        normalized_bm25_score = bm25_score / maximum_bm25_score if maximum_bm25_score > 0 else 0.0

        reranked_candidates.append(
            RerankedCandidate(
                source_identifier=candidate.source_identifier,
                base_score=candidate.base_score,
                bm25_score=bm25_score,
                normalized_bm25_score=normalized_bm25_score,
                rerank_score=(candidate.base_score + normalized_weight * normalized_bm25_score),
            )
        )

    return tuple(
        sorted(
            reranked_candidates,
            key=lambda candidate: (
                -candidate.rerank_score,
                -candidate.base_score,
                candidate.source_identifier,
            ),
        )[:limit]
    )


def _normalize_candidates(
    candidates: Sequence[RerankingCandidate],
) -> tuple[RerankingCandidate, ...]:
    """Validate candidate values and reject ambiguous duplicate identifiers."""

    normalized_candidates: list[RerankingCandidate] = []
    seen_source_identifiers: set[str] = set()

    for candidate in candidates:
        if not isinstance(candidate, RerankingCandidate):
            raise TypeError("Reranking candidates must be RerankingCandidate values")

        source_identifier = candidate.source_identifier.strip()

        if not source_identifier:
            raise ValueError("Reranking source identifiers must not be empty")

        if source_identifier in seen_source_identifiers:
            raise ValueError("Reranking source identifiers must be unique")

        if not isinstance(candidate.search_text, str):
            raise TypeError("Reranking candidate search text must be a string")

        if isinstance(candidate.base_score, bool) or not isinstance(
            candidate.base_score,
            int | float,
        ):
            raise TypeError("Reranking candidate base score must be numeric")

        base_score = float(candidate.base_score)

        if not math.isfinite(base_score):
            raise ValueError("Reranking candidate base score must be finite")

        seen_source_identifiers.add(source_identifier)
        normalized_candidates.append(
            RerankingCandidate(
                source_identifier=source_identifier,
                search_text=candidate.search_text,
                base_score=base_score,
            )
        )

    return tuple(normalized_candidates)


def _is_structured_identifier_token(token: str) -> bool:
    """Recognize versions and incident-style identifiers without hard-coding values."""

    contains_digit = any(character.isdigit() for character in token)
    contains_separator = any(separator in token for separator in STRUCTURED_IDENTIFIER_SEPARATORS)

    return contains_digit and contains_separator
