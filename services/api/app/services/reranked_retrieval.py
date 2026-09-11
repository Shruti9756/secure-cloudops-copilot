from collections.abc import Collection, Sequence

from sqlalchemy.orm import Session

from app.services.document_access import (
    DEFAULT_DOCUMENT_ACCESS_LEVELS,
    DocumentAccessLevel,
)
from app.services.hybrid_retrieval import (
    HYBRID_CANDIDATE_MULTIPLIER,
    HybridRetrievedChunk,
    retrieve_hybrid_chunks,
)
from app.services.reranking import (
    RerankingCandidate,
    rerank_candidates,
)
from app.services.retrieval import (
    DEFAULT_RETRIEVAL_LIMIT,
    MAX_RETRIEVAL_LIMIT,
)


def retrieve_reranked_hybrid_chunks(
    session: Session,
    tenant_slug: str,
    query: str,
    query_vector: Sequence[float],
    embedding_model: str,
    allowed_document_access_levels: Collection[
        DocumentAccessLevel
    ] = DEFAULT_DOCUMENT_ACCESS_LEVELS,
    limit: int = DEFAULT_RETRIEVAL_LIMIT,
) -> list[HybridRetrievedChunk]:
    """Rerank a wider hybrid candidate set using query-aware metadata."""

    if isinstance(limit, bool) or not isinstance(limit, int):
        raise TypeError("Retrieval limit must be an integer")

    if not 1 <= limit <= MAX_RETRIEVAL_LIMIT:
        raise ValueError(f"Retrieval limit must be between 1 and {MAX_RETRIEVAL_LIMIT}")

    candidate_limit = min(
        MAX_RETRIEVAL_LIMIT,
        limit * HYBRID_CANDIDATE_MULTIPLIER,
    )
    hybrid_candidates = retrieve_hybrid_chunks(
        session=session,
        tenant_slug=tenant_slug,
        query=query,
        query_vector=query_vector,
        embedding_model=embedding_model,
        allowed_document_access_levels=allowed_document_access_levels,
        limit=candidate_limit,
    )
    candidates_by_source_identifier = {
        _source_identifier(candidate): candidate for candidate in hybrid_candidates
    }

    reranked_candidates = rerank_candidates(
        query=query,
        candidates=tuple(
            RerankingCandidate(
                source_identifier=_source_identifier(candidate),
                search_text=(
                    f"{candidate.source_path}\n{candidate.document_title}\n{candidate.content}"
                ),
                base_score=candidate.rrf_score,
            )
            for candidate in hybrid_candidates
        ),
        limit=limit,
    )

    return [
        candidates_by_source_identifier[candidate.source_identifier]
        for candidate in reranked_candidates
    ]


def _source_identifier(candidate: HybridRetrievedChunk) -> str:
    """Build the stable source identifier shared by retrieval stages."""

    return f"{candidate.source_path}#chunk-{candidate.chunk_index}"
