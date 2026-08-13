import math
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DocumentChunk, KnowledgeDocument, Tenant

# The database schema uses vector(1024), so every query vector must match it.
EMBEDDING_DIMENSIONS = 1024
DEFAULT_RETRIEVAL_LIMIT = 3
MAX_RETRIEVAL_LIMIT = 10


@dataclass(frozen=True)
class RetrievedChunk:
    """A retrieval result plus the source details needed for a grounded answer."""

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
    limit: int = DEFAULT_RETRIEVAL_LIMIT,
) -> list[RetrievedChunk]:
    """Return the closest embedded chunks for one tenant and embedding model.

    The caller embeds the user's question first. This service then performs the
    database search only—it never calls Ollama, Bedrock, or an LLM itself.
    """
    normalized_tenant_slug = tenant_slug.strip()
    normalized_embedding_model = embedding_model.strip()
    normalized_query_vector = _normalize_query_vector(query_vector)

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
    cosine_distance = DocumentChunk.embedding.cosine_distance(normalized_query_vector).label(
        "cosine_distance"
    )

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
            # Never retrieve incomplete documents or chunks without vectors.
            KnowledgeDocument.ingestion_status == "embedded",
            DocumentChunk.embedding.is_not(None),
            # Prevent comparison of vectors produced by different embedding models.
            DocumentChunk.embedding_model == normalized_embedding_model,
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
