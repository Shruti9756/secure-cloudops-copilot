"""Local polling worker for asynchronous-style document processing."""

import logging
import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.models import KnowledgeDocument, Tenant
from app.db.session import get_session_factory
from app.infrastructure.ollama import OllamaEmbeddingClient
from app.services.chunking import chunk_pending_documents
from app.services.embedding_persistence import embed_chunked_documents
from app.services.embeddings import EmbeddingProvider

LOGGER = logging.getLogger(__name__)

PROCESSABLE_DOCUMENT_STATUSES = frozenset({"pending", "chunked"})


@dataclass(frozen=True)
class ProcessingCycleResult:
    """Safe summary of one worker cycle; raw document content is never logged."""

    chunked_documents: int
    chunks_created: int
    embedded_documents: int
    embedded_chunks: int
    skipped_chunks: int
    input_tokens: int

    @property
    def has_work(self) -> bool:
        """Return whether this cycle changed any document-processing state."""

        return self.chunked_documents > 0 or self.embedded_documents > 0


def list_tenant_slugs_requiring_processing(session: Session) -> list[str]:
    """Return only tenant slugs that currently have document-processing work."""

    statement = (
        select(Tenant.slug)
        .join(Tenant.documents)
        .where(KnowledgeDocument.ingestion_status.in_(PROCESSABLE_DOCUMENT_STATUSES))
        .distinct()
        .order_by(Tenant.slug)
    )

    return list(session.scalars(statement))


def process_tenant_documents(
    *,
    session: Session,
    tenant_slug: str,
    provider: EmbeddingProvider,
) -> ProcessingCycleResult:
    """Chunk and embed pending documents for one tenant in the active transaction."""

    normalized_tenant_slug = tenant_slug.strip()

    if not normalized_tenant_slug:
        raise ValueError("Document processor tenant slug must not be empty")

    chunking_results = chunk_pending_documents(
        session=session,
        tenant_slug=normalized_tenant_slug,
    )

    # Newly chunked documents become eligible for embedding in this same transaction.
    session.flush()

    embedding_results = embed_chunked_documents(
        session=session,
        tenant_slug=normalized_tenant_slug,
        provider=provider,
    )

    return ProcessingCycleResult(
        chunked_documents=len(chunking_results),
        chunks_created=sum(result.chunk_count for result in chunking_results),
        embedded_documents=len(embedding_results),
        embedded_chunks=sum(result.embedded_chunk_count for result in embedding_results),
        skipped_chunks=sum(result.skipped_chunk_count for result in embedding_results),
        input_tokens=sum(result.total_input_tokens for result in embedding_results),
    )


def process_one_cycle(
    *,
    session_factory: sessionmaker[Session],
    tenant_slug: str,
    provider: EmbeddingProvider,
) -> ProcessingCycleResult:
    """Run one tenant's all-or-nothing PostgreSQL processing transaction."""

    with session_factory.begin() as session:
        return process_tenant_documents(
            session=session,
            tenant_slug=tenant_slug,
            provider=provider,
        )


def process_all_tenant_documents(
    *,
    session_factory: sessionmaker[Session],
    provider: EmbeddingProvider,
) -> ProcessingCycleResult:
    """Process every tenant with work, isolating each tenant in its own transaction."""

    with session_factory() as session:
        tenant_slugs = list_tenant_slugs_requiring_processing(session)

    results: list[ProcessingCycleResult] = []

    for tenant_slug in tenant_slugs:
        try:
            results.append(
                process_one_cycle(
                    session_factory=session_factory,
                    tenant_slug=tenant_slug,
                    provider=provider,
                )
            )
        except Exception:
            # One tenant's malformed document or temporary model failure must not
            # block processing for every other tenant.
            LOGGER.exception(
                "Document processing failed for tenant=%s; continuing with other tenants",
                tenant_slug,
            )

    return ProcessingCycleResult(
        chunked_documents=sum(result.chunked_documents for result in results),
        chunks_created=sum(result.chunks_created for result in results),
        embedded_documents=sum(result.embedded_documents for result in results),
        embedded_chunks=sum(result.embedded_chunks for result in results),
        skipped_chunks=sum(result.skipped_chunks for result in results),
        input_tokens=sum(result.input_tokens for result in results),
    )


def main() -> None:
    """Run the local worker forever; Docker restarts it only if the process exits."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    settings = get_settings()
    session_factory = get_session_factory()
    provider = OllamaEmbeddingClient()
    tenant_scope = settings.document_processor_tenant_slug

    if tenant_scope is not None:
        tenant_scope = tenant_scope.strip() or None

    LOGGER.info(
        "Document worker started for tenant_scope=%s with poll_interval_seconds=%s",
        tenant_scope or "all",
        settings.document_processor_poll_interval_seconds,
    )

    while True:
        try:
            if tenant_scope is None:
                result = process_all_tenant_documents(
                    session_factory=session_factory,
                    provider=provider,
                )
            else:
                result = process_one_cycle(
                    session_factory=session_factory,
                    tenant_slug=tenant_scope,
                    provider=provider,
                )
        except Exception:
            LOGGER.exception("Document processing cycle failed; it will retry later")
        else:
            if result.has_work:
                LOGGER.info(
                    "Document processing cycle completed: "
                    "chunked_documents=%s chunks_created=%s "
                    "embedded_documents=%s embedded_chunks=%s "
                    "skipped_chunks=%s input_tokens=%s",
                    result.chunked_documents,
                    result.chunks_created,
                    result.embedded_documents,
                    result.embedded_chunks,
                    result.skipped_chunks,
                    result.input_tokens,
                )

        time.sleep(settings.document_processor_poll_interval_seconds)


if __name__ == "__main__":
    main()
