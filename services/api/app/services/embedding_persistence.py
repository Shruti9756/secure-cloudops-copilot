from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import KnowledgeDocument, Tenant
from app.services.embeddings import EmbeddingProvider

EMBEDDABLE_DOCUMENT_STATUSES = frozenset({"chunked", "embedded"})


@dataclass(frozen=True)
class DocumentEmbeddingResult:
    """Summary of one document's embedding persistence work."""

    document_id: UUID
    source_path: str
    embedded_chunk_count: int
    skipped_chunk_count: int
    total_input_tokens: int


def embed_document_chunks(
    session: Session,
    document: KnowledgeDocument,
    provider: EmbeddingProvider,
) -> DocumentEmbeddingResult:
    """Embed each missing chunk for one document inside the caller's transaction.

    This function flushes database changes but deliberately does not commit.
    The caller owns the transaction, so an upstream failure can roll back all
    vector writes for this document safely.
    """
    if document.ingestion_status not in EMBEDDABLE_DOCUMENT_STATUSES:
        raise ValueError("Document must be chunked before it can be embedded")

    chunks = sorted(document.chunks, key=lambda chunk: chunk.chunk_index)

    if not chunks:
        raise ValueError("Document must have at least one chunk before it can be embedded")

    embedded_chunk_count = 0
    skipped_chunk_count = 0
    total_input_tokens = 0

    for chunk in chunks:
        # Existing vectors are kept during normal reruns to make the process idempotent.
        if chunk.embedding is not None:
            skipped_chunk_count += 1
            continue

        result = provider.embed(chunk.content)

        # These fields come from one provider response and must be stored together.
        chunk.embedding = result.vector
        chunk.embedding_model = result.model_id
        chunk.embedding_token_count = result.input_text_token_count
        chunk.embedding_created_at = datetime.now(UTC)

        embedded_chunk_count += 1
        total_input_tokens += result.input_text_token_count

    # A document is searchable only after every one of its chunks has a vector.
    document.ingestion_status = "embedded"
    session.flush()

    return DocumentEmbeddingResult(
        document_id=document.id,
        source_path=document.source_path,
        embedded_chunk_count=embedded_chunk_count,
        skipped_chunk_count=skipped_chunk_count,
        total_input_tokens=total_input_tokens,
    )


def embed_chunked_documents(
    session: Session,
    tenant_slug: str,
    provider: EmbeddingProvider,
) -> list[DocumentEmbeddingResult]:
    """Embed every chunked document for one tenant workspace.

    `selectinload` fetches chunks efficiently, while the tenant filter prevents
    one workspace's embedding run from accessing another workspace's documents.
    """
    normalized_tenant_slug = tenant_slug.strip()

    if not normalized_tenant_slug:
        raise ValueError("Tenant slug must not be empty")

    statement = (
        select(KnowledgeDocument)
        .join(KnowledgeDocument.tenant)
        .where(
            Tenant.slug == normalized_tenant_slug,
            KnowledgeDocument.ingestion_status == "chunked",
        )
        # Load all selected documents' chunks in a second efficient query.
        .options(selectinload(KnowledgeDocument.chunks))
        .order_by(KnowledgeDocument.source_path)
    )
    documents = list(session.scalars(statement))

    return [
        embed_document_chunks(
            session=session,
            document=document,
            provider=provider,
        )
        for document in documents
    ]
