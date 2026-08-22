"""Local polling worker for asynchronous-style document processing."""

import logging
import time
from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.infrastructure.ollama import OllamaEmbeddingClient
from app.services.chunking import chunk_pending_documents
from app.services.embedding_persistence import embed_chunked_documents
from app.services.embeddings import EmbeddingProvider

LOGGER = logging.getLogger(__name__)


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

    # Newly chunked documents become eligible for embedding in this same transaction.
    chunking_results = chunk_pending_documents(
        session=session,
        tenant_slug=normalized_tenant_slug,
    )
    # The session deliberately disables autoflush. Flush here so the embedding
    # query can see this cycle's newly chunked documents without committing yet.
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
    """Run one all-or-nothing PostgreSQL processing transaction."""
    # If chunking or embedding fails, `begin()` rolls back every derived database change.
    with session_factory.begin() as session:
        return process_tenant_documents(
            session=session,
            tenant_slug=tenant_slug,
            provider=provider,
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

    LOGGER.info(
        "Document worker started for tenant=%s with poll_interval_seconds=%s",
        settings.document_processor_tenant_slug,
        settings.document_processor_poll_interval_seconds,
    )

    while True:
        try:
            result = process_one_cycle(
                session_factory=session_factory,
                tenant_slug=settings.document_processor_tenant_slug,
                provider=provider,
            )
        except Exception:
            # The transaction rolls back. Keep the worker alive so a later cycle can retry.
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
