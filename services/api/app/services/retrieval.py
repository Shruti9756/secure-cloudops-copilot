import math
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DocumentChunk, KnowledgeDocument, Tenant
from app.services.document_access import (
    ALL_DOCUMENT_ACCESS_LEVELS,
    DEFAULT_DOCUMENT_ACCESS_LEVELS,
    DocumentAccessLevel,
)

# The database schema uses vector(1024), so every query vector must match it.
EMBEDDING_DIMENSIONS = 1024
DEFAULT_RETRIEVAL_LIMIT = 3
MAX_RETRIEVAL_LIMIT = 10

# Initial value measured from our evaluation queries:
# relevant examples: 0.2322 and 0.3424; unrelated example: 0.4926.
MAX_RETRIEVAL_COSINE_DISTANCE = 0.40


@dataclass(frozen=True)
class RetrievedChunk:
    """A retrieval result plus source details needed for a grounded answer."""

    chunk_id: UUID
    document_id: UUID
    source_path: str
    document_title: str
    content: str
    chunk_index: int
    cosine_distance: float


def retrieve_relevant_chunks(
    session: Session,
    tenant_slug: str,
    query_vector: Sequence[float],
    embedding_model: str,
    allowed_document_access_levels: Collection[
        DocumentAccessLevel
    ] = DEFAULT_DOCUMENT_ACCESS_LEVELS,
    limit: int = DEFAULT_RETRIEVAL_LIMIT,
    max_cosine_distance: float = MAX_RETRIEVAL_COSINE_DISTANCE,
) -> list[RetrievedChunk]:
    """Return relevant embedded chunks for one tenant and embedding model.

    The maximum distance filter is applied inside PostgreSQL before ranking.
    This prevents unrelated "nearest" chunks from reaching the RAG model.
    """
    normalized_tenant_slug = tenant_slug.strip()
    normalized_embedding_model = embedding_model.strip()
    normalized_query_vector = _normalize_query_vector(query_vector)
    normalized_max_cosine_distance = _normalize_max_cosine_distance(max_cosine_distance)
    normalized_document_access_levels = _normalize_document_access_levels(
        allowed_document_access_levels
    )

    if not normalized_tenant_slug:
        raise ValueError("Tenant slug must not be empty")

    if not normalized_embedding_model:
        raise ValueError("Embedding model must not be empty")

    if not isinstance(limit, int) or isinstance(limit, bool):
        raise TypeError("Retrieval limit must be an integer")

    if not 1 <= limit <= MAX_RETRIEVAL_LIMIT:
        raise ValueError(f"Retrieval limit must be between 1 and {MAX_RETRIEVAL_LIMIT}")

    # pgvector translates this into PostgreSQL cosine-distance SQL.
    # Lower distance means the chunk is more semantically relevant.
    distance_expression = DocumentChunk.embedding.cosine_distance(normalized_query_vector)
    cosine_distance = distance_expression.label("cosine_distance")

    statement = (
        select(
            DocumentChunk.id.label("chunk_id"),
            DocumentChunk.document_id,
            KnowledgeDocument.source_path,
            KnowledgeDocument.title.label("document_title"),
            DocumentChunk.content,
            DocumentChunk.chunk_index,
            cosine_distance,
        )
        # Follow chunk -> document -> tenant, so the tenant filter happens in SQL.
        .join(DocumentChunk.document)
        .join(KnowledgeDocument.tenant)
        .where(
            Tenant.slug == normalized_tenant_slug,
            # The document must still belong to the tenant's organization.
            KnowledgeDocument.organization_id == Tenant.organization_id,
            KnowledgeDocument.access_level.in_(normalized_document_access_levels),
            # Never retrieve incomplete documents or chunks without vectors.
            KnowledgeDocument.ingestion_status == "embedded",
            DocumentChunk.embedding.is_not(None),
            # Prevent comparison of vectors produced by different embedding models.
            DocumentChunk.embedding_model == normalized_embedding_model,
            # Reject weak semantic matches before they can become RAG evidence.
            distance_expression <= normalized_max_cosine_distance,
        )
        # Stable tie-breakers keep results predictable if distances are equal.
        .order_by(
            cosine_distance,
            KnowledgeDocument.source_path,
            DocumentChunk.chunk_index,
        )
        .limit(limit)
    )

    return [
        RetrievedChunk(
            chunk_id=row.chunk_id,
            document_id=row.document_id,
            source_path=row.source_path,
            document_title=row.document_title,
            content=row.content,
            chunk_index=row.chunk_index,
            cosine_distance=float(row.cosine_distance),
        )
        for row in session.execute(statement)
    ]


def _normalize_query_vector(query_vector: Sequence[float]) -> list[float]:
    """Validate untrusted vector input before it reaches the database query."""
    normalized_vector = list(query_vector)

    if len(normalized_vector) != EMBEDDING_DIMENSIONS:
        raise ValueError(f"Query vector must contain exactly {EMBEDDING_DIMENSIONS} dimensions")

    if any(
        isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value)
        for value in normalized_vector
    ):
        raise ValueError("Query vector must contain only finite numeric values")

    if not any(normalized_vector):
        raise ValueError("Query vector must not contain only zeroes")

    return [float(value) for value in normalized_vector]


def _normalize_max_cosine_distance(max_cosine_distance: float) -> float:
    """Validate the relevance threshold before using it in SQL."""
    if isinstance(max_cosine_distance, bool) or not isinstance(
        max_cosine_distance,
        int | float,
    ):
        raise TypeError("Maximum cosine distance must be numeric")

    normalized_distance = float(max_cosine_distance)

    if not math.isfinite(normalized_distance):
        raise ValueError("Maximum cosine distance must be finite")

    # Cosine distance theoretically ranges from 0 (same direction) to 2 (opposite).
    if not 0 <= normalized_distance <= 2:
        raise ValueError("Maximum cosine distance must be between 0 and 2")

    return normalized_distance


def _normalize_document_access_levels(
    allowed_document_access_levels: Collection[DocumentAccessLevel],
) -> frozenset[DocumentAccessLevel]:
    """Reject unknown or empty document-visibility rules before SQL executes."""
    normalized_access_levels = frozenset(allowed_document_access_levels)

    if not normalized_access_levels:
        raise ValueError("At least one document access level is required")

    if not normalized_access_levels.issubset(ALL_DOCUMENT_ACCESS_LEVELS):
        raise ValueError("Document access levels must be supported")

    return normalized_access_levels
