"""Local polling worker for asynchronous-style document processing."""

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.models import KnowledgeDocument, Tenant
from app.db.session import get_session_factory
from app.infrastructure.ollama import OllamaEmbeddingClient
from app.services.chunking import replace_document_chunks
from app.services.document_retry import (
    DEFAULT_PROCESSING_MAX_ATTEMPTS,
    PROCESSABLE_DOCUMENT_STATUSES,
    classify_processing_failure,
    clear_processing_failure,
    record_processing_failure,
)
from app.services.embedding_persistence import embed_document_chunks
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


EMPTY_PROCESSING_CYCLE_RESULT = ProcessingCycleResult(
    chunked_documents=0,
    chunks_created=0,
    embedded_documents=0,
    embedded_chunks=0,
    skipped_chunks=0,
    input_tokens=0,
)


def _utc_now() -> datetime:
    """Return an aware UTC timestamp for queue and retry decisions."""
    return datetime.now(UTC)


def _normalize_tenant_slug(tenant_slug: str) -> str:
    normalized_tenant_slug = tenant_slug.strip()

    if not normalized_tenant_slug:
        raise ValueError("Document processor tenant slug must not be empty")

    return normalized_tenant_slug


def _summarize_processing_results(
    results: list[ProcessingCycleResult],
) -> ProcessingCycleResult:
    """Combine individual document results into one worker-cycle summary."""
    return ProcessingCycleResult(
        chunked_documents=sum(result.chunked_documents for result in results),
        chunks_created=sum(result.chunks_created for result in results),
        embedded_documents=sum(result.embedded_documents for result in results),
        embedded_chunks=sum(result.embedded_chunks for result in results),
        skipped_chunks=sum(result.skipped_chunks for result in results),
        input_tokens=sum(result.input_tokens for result in results),
    )


def list_tenant_slugs_requiring_processing(
    session: Session,
    *,
    available_at: datetime,
) -> list[str]:
    """Return tenants that currently have due document-processing work."""
    statement = (
        select(Tenant.slug)
        .join(Tenant.documents)
        .where(
            KnowledgeDocument.ingestion_status.in_(PROCESSABLE_DOCUMENT_STATUSES),
            KnowledgeDocument.processing_attempt_count < DEFAULT_PROCESSING_MAX_ATTEMPTS,
            or_(
                KnowledgeDocument.next_processing_attempt_at.is_(None),
                KnowledgeDocument.next_processing_attempt_at <= available_at,
            ),
        )
        .distinct()
        .order_by(Tenant.slug)
    )

    return list(session.scalars(statement))


def claim_next_document(
    *,
    session: Session,
    tenant_slug: str,
    available_at: datetime,
) -> KnowledgeDocument | None:
    """Lock and return at most one due document for one tenant."""
    normalized_tenant_slug = _normalize_tenant_slug(tenant_slug)

    statement = (
        select(KnowledgeDocument)
        .join(KnowledgeDocument.tenant)
        .where(
            Tenant.slug == normalized_tenant_slug,
            KnowledgeDocument.ingestion_status.in_(PROCESSABLE_DOCUMENT_STATUSES),
            KnowledgeDocument.processing_attempt_count < DEFAULT_PROCESSING_MAX_ATTEMPTS,
            or_(
                KnowledgeDocument.next_processing_attempt_at.is_(None),
                KnowledgeDocument.next_processing_attempt_at <= available_at,
            ),
        )
        .order_by(KnowledgeDocument.source_path)
        .limit(1)
        .with_for_update(of=KnowledgeDocument, skip_locked=True)
    )

    return session.scalar(statement)


def process_document(
    *,
    session: Session,
    document: KnowledgeDocument,
    provider: EmbeddingProvider,
) -> ProcessingCycleResult:
    """Chunk and embed exactly one document inside the active savepoint."""
    chunked_documents = 0
    chunks_created = 0

    if document.ingestion_status == "pending":
        chunking_result = replace_document_chunks(
            session=session,
            document=document,
        )
        chunked_documents = 1
        chunks_created = chunking_result.chunk_count

        # The session disables autoflush. Persist the new chunks before loading
        # the relationship that the embedding stage reads.
        session.flush()
        session.expire(document, ["chunks"])
    elif document.ingestion_status != "chunked":
        raise ValueError("Document must be pending or chunked before processing")

    embedding_result = embed_document_chunks(
        session=session,
        document=document,
        provider=provider,
    )

    # A successful complete embedding invalidates old consecutive-failure state.
    clear_processing_failure(document)

    return ProcessingCycleResult(
        chunked_documents=chunked_documents,
        chunks_created=chunks_created,
        embedded_documents=1,
        embedded_chunks=embedding_result.embedded_chunk_count,
        skipped_chunks=embedding_result.skipped_chunk_count,
        input_tokens=embedding_result.total_input_tokens,
    )


def process_next_document(
    *,
    session_factory: sessionmaker[Session],
    tenant_slug: str,
    provider: EmbeddingProvider,
    available_at: datetime,
) -> ProcessingCycleResult | None:
    """Claim and process one due document without affecting sibling documents."""
    normalized_tenant_slug = _normalize_tenant_slug(tenant_slug)

    with session_factory.begin() as session:
        document = claim_next_document(
            session=session,
            tenant_slug=normalized_tenant_slug,
            available_at=available_at,
        )

        if document is None:
            return None

        try:
            # PostgreSQL implements SQLAlchemy's nested transaction as a SAVEPOINT.
            with session.begin_nested():
                result = process_document(
                    session=session,
                    document=document,
                    provider=provider,
                )
        except Exception as error:  # noqa: BLE001
            # The savepoint has rolled back document processing, while the outer
            # transaction still owns the document's row lock.
            session.refresh(document)

            failure_reason = classify_processing_failure(error)
            retry_scheduled = record_processing_failure(
                document,
                failure_reason=failure_reason,
                occurred_at=_utc_now(),
            )
            session.flush()

            LOGGER.warning(
                "Document processing attempt failed: "
                "tenant=%s document_id=%s failure_reason=%s retry_scheduled=%s",
                normalized_tenant_slug,
                document.id,
                failure_reason,
                retry_scheduled,
            )

            # Returning normally commits only the failure/retry state.
            return EMPTY_PROCESSING_CYCLE_RESULT

        # Returning normally commits the successfully processed document.
        return result


def process_one_cycle(
    *,
    session_factory: sessionmaker[Session],
    tenant_slug: str,
    provider: EmbeddingProvider,
) -> ProcessingCycleResult:
    """Process each currently due document in its own transaction."""
    normalized_tenant_slug = _normalize_tenant_slug(tenant_slug)
    available_at = _utc_now()
    results: list[ProcessingCycleResult] = []

    while True:
        result = process_next_document(
            session_factory=session_factory,
            tenant_slug=normalized_tenant_slug,
            provider=provider,
            available_at=available_at,
        )

        if result is None:
            break

        results.append(result)

    return _summarize_processing_results(results)


def process_all_tenant_documents(
    *,
    session_factory: sessionmaker[Session],
    provider: EmbeddingProvider,
) -> ProcessingCycleResult:
    """Process all tenants while isolating each individual document attempt."""
    available_at = _utc_now()

    with session_factory() as session:
        tenant_slugs = list_tenant_slugs_requiring_processing(
            session,
            available_at=available_at,
        )

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
            # Failure bookkeeping or database errors for one tenant must not stop
            # processing for every other tenant.
            LOGGER.exception(
                "Document processing failed for tenant=%s; continuing with other tenants",
                tenant_slug,
            )

    return _summarize_processing_results(results)


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
