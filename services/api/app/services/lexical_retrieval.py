from collections.abc import Collection
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DocumentChunk, KnowledgeDocument, Tenant
from app.services.bm25 import rank_bm25_documents, tokenize_bm25
from app.services.document_access import (
    DEFAULT_DOCUMENT_ACCESS_LEVELS,
    DocumentAccessLevel,
    normalize_document_access_levels,
)
from app.services.prompt_injection import detect_prompt_injection
from app.services.retrieval import DEFAULT_RETRIEVAL_LIMIT, MAX_RETRIEVAL_LIMIT


@dataclass(frozen=True)
class LexicalRetrievedChunk:
    """One safe document chunk ranked by BM25 lexical relevance."""

    chunk_id: UUID
    document_id: UUID
    source_path: str
    document_title: str
    content: str
    chunk_index: int
    bm25_score: float


def retrieve_lexical_chunks(
    session: Session,
    tenant_slug: str,
    query: str,
    allowed_document_access_levels: Collection[
        DocumentAccessLevel
    ] = DEFAULT_DOCUMENT_ACCESS_LEVELS,
    limit: int = DEFAULT_RETRIEVAL_LIMIT,
) -> list[LexicalRetrievedChunk]:
    """Return safe tenant-scoped chunks ranked by exact-term BM25 relevance."""

    normalized_tenant_slug = tenant_slug.strip()
    query_terms = tokenize_bm25(query)
    normalized_document_access_levels = normalize_document_access_levels(
        allowed_document_access_levels
    )

    if not normalized_tenant_slug:
        raise ValueError("Tenant slug must not be empty")

    if not query_terms:
        raise ValueError("Lexical retrieval query must contain at least one searchable term")

    if isinstance(limit, bool) or not isinstance(limit, int):
        raise TypeError("Retrieval limit must be an integer")

    if not 1 <= limit <= MAX_RETRIEVAL_LIMIT:
        raise ValueError(f"Retrieval limit must be between 1 and {MAX_RETRIEVAL_LIMIT}")

    statement = (
        select(
            DocumentChunk.id.label("chunk_id"),
            DocumentChunk.document_id,
            KnowledgeDocument.source_path,
            KnowledgeDocument.title.label("document_title"),
            DocumentChunk.content,
            DocumentChunk.chunk_index,
        )
        # The database applies the same workspace isolation as semantic retrieval.
        .join(DocumentChunk.document)
        .join(KnowledgeDocument.tenant)
        .where(
            Tenant.slug == normalized_tenant_slug,
            KnowledgeDocument.organization_id == Tenant.organization_id,
            DocumentChunk.organization_id == KnowledgeDocument.organization_id,
            KnowledgeDocument.access_level.in_(normalized_document_access_levels),
            # Compare semantic and lexical strategies using the same ready chunks.
            KnowledgeDocument.ingestion_status == "embedded",
            DocumentChunk.embedding.is_not(None),
        )
        .order_by(KnowledgeDocument.source_path, DocumentChunk.chunk_index)
    )

    candidates = [
        row
        for row in session.execute(statement)
        if not detect_prompt_injection(row.content).is_suspicious
    ]

    scored_documents = rank_bm25_documents(
        query=query,
        documents={
            _source_identifier(row.source_path, row.chunk_index): row.content for row in candidates
        },
        limit=limit,
    )
    candidates_by_source_identifier = {
        _source_identifier(row.source_path, row.chunk_index): row for row in candidates
    }

    return [
        LexicalRetrievedChunk(
            chunk_id=candidates_by_source_identifier[scored_document.source_identifier].chunk_id,
            document_id=candidates_by_source_identifier[
                scored_document.source_identifier
            ].document_id,
            source_path=candidates_by_source_identifier[
                scored_document.source_identifier
            ].source_path,
            document_title=candidates_by_source_identifier[
                scored_document.source_identifier
            ].document_title,
            content=candidates_by_source_identifier[scored_document.source_identifier].content,
            chunk_index=candidates_by_source_identifier[
                scored_document.source_identifier
            ].chunk_index,
            bm25_score=scored_document.score,
        )
        for scored_document in scored_documents
    ]


def _source_identifier(source_path: str, chunk_index: int) -> str:
    """Build the stable source ID used by retrieval and evaluation."""

    return f"{source_path}#chunk-{chunk_index}"
