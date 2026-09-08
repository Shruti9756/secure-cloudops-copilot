from collections.abc import Collection, Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from app.services.bm25 import tokenize_bm25
from app.services.document_access import (
    DEFAULT_DOCUMENT_ACCESS_LEVELS,
    DocumentAccessLevel,
    normalize_document_access_levels,
)
from app.services.lexical_retrieval import (
    LexicalRetrievedChunk,
    retrieve_lexical_chunks,
)
from app.services.rank_fusion import fuse_ranked_source_identifiers
from app.services.retrieval import (
    DEFAULT_RETRIEVAL_LIMIT,
    MAX_RETRIEVAL_LIMIT,
    RetrievedChunk,
    retrieve_relevant_chunks,
)

HYBRID_CANDIDATE_MULTIPLIER = 3


@dataclass(frozen=True)
class HybridRetrievedChunk:
    """One safe chunk ranked by semantic retrieval, BM25, and reciprocal fusion."""

    chunk_id: UUID
    document_id: UUID
    source_path: str
    document_title: str
    content: str
    chunk_index: int
    semantic_cosine_distance: float | None
    bm25_score: float | None
    rrf_score: float
    semantic_rank: int | None
    lexical_rank: int | None


def retrieve_hybrid_chunks(
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
    """Fuse safe semantic and lexical results for one tenant-scoped question."""

    normalized_tenant_slug = tenant_slug.strip()

    if not normalized_tenant_slug:
        raise ValueError("Tenant slug must not be empty")

    if not tokenize_bm25(query):
        raise ValueError("Hybrid retrieval query must contain at least one searchable term")

    if isinstance(limit, bool) or not isinstance(limit, int):
        raise TypeError("Retrieval limit must be an integer")

    if not 1 <= limit <= MAX_RETRIEVAL_LIMIT:
        raise ValueError(f"Retrieval limit must be between 1 and {MAX_RETRIEVAL_LIMIT}")

    normalized_document_access_levels = normalize_document_access_levels(
        allowed_document_access_levels
    )
    candidate_limit = min(
        MAX_RETRIEVAL_LIMIT,
        limit * HYBRID_CANDIDATE_MULTIPLIER,
    )

    semantic_chunks = retrieve_relevant_chunks(
        session=session,
        tenant_slug=normalized_tenant_slug,
        query_vector=query_vector,
        embedding_model=embedding_model,
        allowed_document_access_levels=normalized_document_access_levels,
        limit=candidate_limit,
    )
    lexical_chunks = retrieve_lexical_chunks(
        session=session,
        tenant_slug=normalized_tenant_slug,
        query=query,
        allowed_document_access_levels=normalized_document_access_levels,
        limit=candidate_limit,
    )

    semantic_chunks_by_source = {_source_identifier(chunk): chunk for chunk in semantic_chunks}
    lexical_chunks_by_source = {_source_identifier(chunk): chunk for chunk in lexical_chunks}
    fused_sources = fuse_ranked_source_identifiers(
        semantic_source_identifiers=tuple(semantic_chunks_by_source),
        lexical_source_identifiers=tuple(lexical_chunks_by_source),
        limit=limit,
    )

    return [
        _build_hybrid_chunk(
            source_identifier=fused_source.source_identifier,
            rrf_score=fused_source.rrf_score,
            semantic_rank=fused_source.semantic_rank,
            lexical_rank=fused_source.lexical_rank,
            semantic_chunks_by_source=semantic_chunks_by_source,
            lexical_chunks_by_source=lexical_chunks_by_source,
        )
        for fused_source in fused_sources
    ]


def _build_hybrid_chunk(
    *,
    source_identifier: str,
    rrf_score: float,
    semantic_rank: int | None,
    lexical_rank: int | None,
    semantic_chunks_by_source: dict[str, RetrievedChunk],
    lexical_chunks_by_source: dict[str, LexicalRetrievedChunk],
) -> HybridRetrievedChunk:
    """Join ranking metadata with one source chunk returned by either retriever."""

    semantic_chunk = semantic_chunks_by_source.get(source_identifier)
    lexical_chunk = lexical_chunks_by_source.get(source_identifier)
    source_chunk = semantic_chunk or lexical_chunk

    if source_chunk is None:
        raise RuntimeError("Fused source was not returned by either retriever")

    return HybridRetrievedChunk(
        chunk_id=source_chunk.chunk_id,
        document_id=source_chunk.document_id,
        source_path=source_chunk.source_path,
        document_title=source_chunk.document_title,
        content=source_chunk.content,
        chunk_index=source_chunk.chunk_index,
        semantic_cosine_distance=(
            semantic_chunk.cosine_distance if semantic_chunk is not None else None
        ),
        bm25_score=lexical_chunk.bm25_score if lexical_chunk is not None else None,
        rrf_score=rrf_score,
        semantic_rank=semantic_rank,
        lexical_rank=lexical_rank,
    )


def _source_identifier(
    chunk: RetrievedChunk | LexicalRetrievedChunk,
) -> str:
    """Build the stable document-and-chunk identifier used by all retrieval stages."""

    return f"{chunk.source_path}#chunk-{chunk.chunk_index}"
