"""Local polling worker for asynchronous-style document processing."""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.models import KnowledgeDocument, Tenant
from app.db.session import get_session_factory
from app.infrastructure.ollama import (
    OLLAMA_MXBAI_EMBED_LARGE_DIMENSIONS,
    OLLAMA_MXBAI_EMBED_LARGE_MODEL_ID,
    OllamaEmbeddingClient,
)
from app.infrastructure.redis import get_redis_client
from app.services.chunking import replace_document_chunks
from app.services.document_job_status import (
    DocumentJobStage,
    DocumentJobStatusClient,
    store_document_job_status,
)
from app.services.document_lock import (
    DocumentLockClient,
    DocumentLockLost,
    DocumentLockUnavailable,
    acquire_document_lock,
    release_document_lock,
    renew_document_lock,
)
from app.services.document_retry import (
    DEFAULT_PROCESSING_MAX_ATTEMPTS,
    PROCESSABLE_DOCUMENT_STATUSES,
    classify_processing_failure,
    clear_processing_failure,
    record_processing_failure,
)
from app.services.embedding_cache import (
    CachedEmbeddingProvider,
    EmbeddingCacheClient,
)
from app.services.embedding_persistence import embed_document_chunks
from app.services.embeddings import EmbeddingProvider

LOGGER = logging.getLogger(__name__)


class DocumentWorkerRedisClient(DocumentLockClient, DocumentJobStatusClient, Protocol):
    """Redis operations required by document locking and progress reporting."""


def build_worker_embedding_provider(
    *,
    redis_client: EmbeddingCacheClient,
) -> EmbeddingProvider:
    """Build the worker embedding provider with validated Redis caching."""
    return CachedEmbeddingProvider(
        provider=OllamaEmbeddingClient(),
        cache=redis_client,
        model_id=OLLAMA_MXBAI_EMBED_LARGE_MODEL_ID,
        dimensions=OLLAMA_MXBAI_EMBED_LARGE_DIMENSIONS,
    )


@dataclass(frozen=True)
class ProcessingCycleResult:
    """Safe summary of one worker cycle; raw document content is never logged."""

    chunked_documents: int
    chunks_created: int
    embedded_documents: int
    embedded_chunks: int
    skipped_chunks: int
    input_tokens: int
    embedding_cache_hits: int = 0
    embedding_cache_misses: int = 0
    embedding_cache_bypasses: int = 0

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
    embedding_cache_hits=0,
    embedding_cache_misses=0,
    embedding_cache_bypasses=0,
)


def _utc_now() -> datetime:
    """Return an aware UTC timestamp for queue and retry decisions."""
    return datetime.now(UTC)


def _normalize_tenant_slug(tenant_slug: str) -> str:
    normalized_tenant_slug = tenant_slug.strip()

    if not normalized_tenant_slug:
        raise ValueError("Document processor tenant slug must not be empty")

    return normalized_tenant_slug


def _store_document_progress(
    redis_client: DocumentJobStatusClient,
    *,
    document: KnowledgeDocument,
    stage: DocumentJobStage,
) -> None:
    """Record best-effort progress without interrupting durable processing."""
    try:
        stored = store_document_job_status(
            redis_client,
            organization_id=document.organization_id,
            tenant_id=document.tenant_id,
            document_id=document.id,
            stage=stage,
            source_sha256=document.source_sha256,
            processing_attempt_count=document.processing_attempt_count,
        )
    except TypeError, ValueError:
        LOGGER.exception(
            "Document progress metadata was invalid: tenant_id=%s document_id=%s stage=%s",
            document.tenant_id,
            document.id,
            stage,
        )
        return

    if not stored:
        LOGGER.warning(
            "Document progress could not be stored: tenant_id=%s document_id=%s stage=%s",
            document.tenant_id,
            document.id,
            stage,
        )


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
        embedding_cache_hits=sum(result.embedding_cache_hits for result in results),
        embedding_cache_misses=sum(result.embedding_cache_misses for result in results),
        embedding_cache_bypasses=sum(result.embedding_cache_bypasses for result in results),
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
    lock_heartbeat: Callable[[], None] | None = None,
    job_progress: Callable[[DocumentJobStage], None] | None = None,
) -> ProcessingCycleResult:
    """Chunk and embed exactly one document inside the active savepoint."""
    chunked_documents = 0
    chunks_created = 0

    if document.ingestion_status == "pending":
        if job_progress is not None:
            job_progress("chunking")

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

    if job_progress is not None:
        job_progress("embedding")

    if lock_heartbeat is None:
        embedding_result = embed_document_chunks(
            session=session,
            document=document,
            provider=provider,
        )
    else:
        embedding_result = embed_document_chunks(
            session=session,
            document=document,
            provider=provider,
            before_embed=lock_heartbeat,
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
        embedding_cache_hits=embedding_result.embedding_cache_hit_count,
        embedding_cache_misses=embedding_result.embedding_cache_miss_count,
        embedding_cache_bypasses=embedding_result.embedding_cache_bypass_count,
    )


def process_next_document(
    *,
    session_factory: sessionmaker[Session],
    tenant_slug: str,
    provider: EmbeddingProvider,
    redis_client: DocumentWorkerRedisClient,
    available_at: datetime,
) -> ProcessingCycleResult | None:
    """Claim and process one due document with PostgreSQL and Redis locks."""
    normalized_tenant_slug = _normalize_tenant_slug(tenant_slug)
    result: ProcessingCycleResult | None = None
    final_stage: DocumentJobStage | None = None
    final_status_document: KnowledgeDocument | None = None
    lock_ownership_intact = True

    with session_factory.begin() as session:
        document = claim_next_document(
            session=session,
            tenant_slug=normalized_tenant_slug,
            available_at=available_at,
        )

        if document is None:
            return None

        try:
            lease = acquire_document_lock(
                redis_client,
                document_id=document.id,
            )
        except DocumentLockUnavailable:
            LOGGER.exception(
                "Document processing skipped because Redis lock is unavailable: "
                "tenant=%s document_id=%s",
                normalized_tenant_slug,
                document.id,
            )
            return None

        if lease is None:
            LOGGER.info(
                "Document processing skipped because another worker owns the lock: "
                "tenant=%s document_id=%s",
                normalized_tenant_slug,
                document.id,
            )
            return None

        final_status_document = document
        _store_document_progress(
            redis_client,
            document=document,
            stage="claimed",
        )

        def renew_lock() -> None:
            if not renew_document_lock(redis_client, lease):
                raise DocumentLockLost(
                    f"Document lock ownership was lost for document {document.id}"
                )

        def report_job_progress(stage: DocumentJobStage) -> None:
            # Confirm lock ownership before publishing progress.
            renew_lock()
            _store_document_progress(
                redis_client,
                document=document,
                stage=stage,
            )

        try:
            try:
                with session.begin_nested():
                    renew_lock()

                    result = process_document(
                        session=session,
                        document=document,
                        provider=provider,
                        lock_heartbeat=renew_lock,
                        job_progress=report_job_progress,
                    )

                    renew_lock()
            except DocumentLockLost, DocumentLockUnavailable:
                lock_ownership_intact = False
                LOGGER.warning(
                    "Document processing stopped because lock ownership was lost: "
                    "tenant=%s document_id=%s",
                    normalized_tenant_slug,
                    document.id,
                )
                result = None
            except Exception as error:  # noqa: BLE001
                session.refresh(document)

                failure_reason = classify_processing_failure(error)
                retry_scheduled = record_processing_failure(
                    document,
                    failure_reason=failure_reason,
                    occurred_at=_utc_now(),
                )
                session.flush()

                final_stage = "retry_scheduled" if retry_scheduled else "failed"
                result = EMPTY_PROCESSING_CYCLE_RESULT

                LOGGER.warning(
                    "Document processing attempt failed: "
                    "tenant=%s document_id=%s failure_reason=%s retry_scheduled=%s",
                    normalized_tenant_slug,
                    document.id,
                    failure_reason,
                    retry_scheduled,
                )
            else:
                final_stage = "completed"
        finally:
            try:
                released = release_document_lock(redis_client, lease)
            except DocumentLockUnavailable:
                lock_ownership_intact = False
                LOGGER.exception(
                    "Document lock could not be released: tenant=%s document_id=%s",
                    normalized_tenant_slug,
                    document.id,
                )
            else:
                if not released:
                    lock_ownership_intact = False
                    LOGGER.warning(
                        "Document lock ownership was lost before release: tenant=%s document_id=%s",
                        normalized_tenant_slug,
                        document.id,
                    )

    # Reaching this line proves that the outer PostgreSQL transaction committed.
    if final_stage is not None and final_status_document is not None and lock_ownership_intact:
        _store_document_progress(
            redis_client,
            document=final_status_document,
            stage=final_stage,
        )

    return result


def process_one_cycle(
    *,
    session_factory: sessionmaker[Session],
    tenant_slug: str,
    provider: EmbeddingProvider,
    redis_client: DocumentWorkerRedisClient,
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
            redis_client=redis_client,
        )

        if result is None:
            break

        results.append(result)

    return _summarize_processing_results(results)


def process_all_tenant_documents(
    *,
    session_factory: sessionmaker[Session],
    provider: EmbeddingProvider,
    redis_client: DocumentWorkerRedisClient,
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
                    redis_client=redis_client,
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
    redis_client = get_redis_client()
    provider = build_worker_embedding_provider(
        redis_client=redis_client,
    )
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
                    session_factory=session_factory, provider=provider, redis_client=redis_client
                )
            else:
                result = process_one_cycle(
                    session_factory=session_factory,
                    tenant_slug=tenant_scope,
                    provider=provider,
                    redis_client=redis_client,
                )
        except Exception:
            LOGGER.exception("Document processing cycle failed; it will retry later")
        else:
            if result.has_work:
                LOGGER.info(
                    "Document processing cycle completed: "
                    "chunked_documents=%s chunks_created=%s "
                    "embedded_documents=%s embedded_chunks=%s "
                    "skipped_chunks=%s embedding_cache_hits=%s "
                    "embedding_cache_misses=%s embedding_cache_bypasses=%s "
                    "provider_input_tokens=%s",
                    result.chunked_documents,
                    result.chunks_created,
                    result.embedded_documents,
                    result.embedded_chunks,
                    result.skipped_chunks,
                    result.embedding_cache_hits,
                    result.embedding_cache_misses,
                    result.embedding_cache_bypasses,
                    result.input_tokens,
                )

        time.sleep(settings.document_processor_poll_interval_seconds)


if __name__ == "__main__":
    main()
