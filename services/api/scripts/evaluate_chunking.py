from dataclasses import dataclass, replace
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_session_factory
from app.infrastructure.ollama import OllamaEmbeddingClient
from app.services.chunking import chunk_pending_documents
from app.services.chunking_evaluation import (
    CURRENT_CHUNKING_PROFILE,
    SMALLER_CHUNKING_PROFILE,
    ChunkingProfile,
)
from app.services.chunking_evaluation_catalog import (
    ChunkingLabelCatalog,
    apply_chunking_labels,
    load_chunking_label_catalog,
)
from app.services.embedding_persistence import (
    embed_chunked_documents,
)
from app.services.embeddings import EmbeddingProvider
from app.services.ingestion import ingest_directory
from app.services.retrieval_evaluation_runner import (
    RetrievalEvaluationCase,
    RetrievalEvaluationReport,
    run_retrieval_evaluation,
)
from scripts.evaluate_retrieval import (
    DEFAULT_CATALOG_PATH,
    load_retrieval_evaluation_catalog,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SOURCE_DIRECTORY = REPOSITORY_ROOT / "docs" / "demo-data"
DEFAULT_LABEL_CATALOG_PATH = (
    REPOSITORY_ROOT / "docs" / "evaluation" / "chunking-eval-labels-v1.json"
)

CHUNKING_RETRIEVAL_STRATEGY = "hybrid"
CHUNKING_RETRIEVAL_LIMIT = 3


@dataclass(frozen=True)
class ChunkingProfileEvaluationReport:
    profile: ChunkingProfile
    document_count: int
    chunk_count: int
    document_embedding_input_tokens: int
    retrieval_report: RetrievalEvaluationReport


@dataclass(frozen=True)
class ChunkingComparisonReport:
    current: ChunkingProfileEvaluationReport
    smaller: ChunkingProfileEvaluationReport


def run_chunking_comparison(
    *,
    session: Session,
    source_directory: Path,
    base_cases: tuple[RetrievalEvaluationCase, ...],
    label_catalog: ChunkingLabelCatalog,
    embedding_provider: EmbeddingProvider,
    run_token: str | None = None,
) -> ChunkingComparisonReport:
    _validate_smaller_profile_label_catalog(label_catalog)
    token = run_token or uuid4().hex[:12]

    current_tenant_slug = _temporary_tenant_slug(
        CURRENT_CHUNKING_PROFILE,
        token,
    )
    smaller_tenant_slug = _temporary_tenant_slug(
        SMALLER_CHUNKING_PROFILE,
        token,
    )

    current_cases = tuple(
        replace(
            case,
            tenant_slug=current_tenant_slug,
        )
        for case in base_cases
    )
    smaller_cases = apply_chunking_labels(
        base_cases,
        label_catalog,
        tenant_slug=smaller_tenant_slug,
    )

    current_report = _run_profile_evaluation(
        session=session,
        source_directory=source_directory,
        profile=CURRENT_CHUNKING_PROFILE,
        tenant_slug=current_tenant_slug,
        evaluation_cases=current_cases,
        embedding_provider=embedding_provider,
    )
    smaller_report = _run_profile_evaluation(
        session=session,
        source_directory=source_directory,
        profile=SMALLER_CHUNKING_PROFILE,
        tenant_slug=smaller_tenant_slug,
        evaluation_cases=smaller_cases,
        embedding_provider=embedding_provider,
    )

    return ChunkingComparisonReport(
        current=current_report,
        smaller=smaller_report,
    )


def execute_chunking_comparison(
    *,
    session_factory: sessionmaker[Session],
    source_directory: Path,
    base_cases: tuple[RetrievalEvaluationCase, ...],
    label_catalog: ChunkingLabelCatalog,
    embedding_provider: EmbeddingProvider,
) -> ChunkingComparisonReport:
    with session_factory() as session:
        try:
            return run_chunking_comparison(
                session=session,
                source_directory=source_directory,
                base_cases=base_cases,
                label_catalog=label_catalog,
                embedding_provider=embedding_provider,
            )
        finally:
            # Temporary organizations, workspaces, documents, chunks, and
            # vectors must never survive the local comparison.
            session.rollback()


def _validate_smaller_profile_label_catalog(
    label_catalog: ChunkingLabelCatalog,
) -> None:
    expected_profile = SMALLER_CHUNKING_PROFILE

    if (
        label_catalog.profile_name != expected_profile.name
        or label_catalog.max_chars != expected_profile.max_chars
        or label_catalog.overlap_chars != expected_profile.overlap_chars
    ):
        raise ValueError(
            "Chunking label catalogue profile does not match the smaller profile: "
            f"expected={expected_profile.name}/"
            f"{expected_profile.max_chars}/"
            f"{expected_profile.overlap_chars}, "
            f"actual={label_catalog.profile_name}/"
            f"{label_catalog.max_chars}/"
            f"{label_catalog.overlap_chars}"
        )


def _run_profile_evaluation(
    *,
    session: Session,
    source_directory: Path,
    profile: ChunkingProfile,
    tenant_slug: str,
    evaluation_cases: tuple[RetrievalEvaluationCase, ...],
    embedding_provider: EmbeddingProvider,
) -> ChunkingProfileEvaluationReport:
    ingestion_results = ingest_directory(
        session=session,
        source_directory=source_directory,
        tenant_slug=tenant_slug,
        tenant_name=f"Chunk Evaluation {profile.name}",
    )

    if not ingestion_results:
        raise ValueError(f"Chunking profile {profile.name} ingested no documents")

    # The session disables autoflush, so each pipeline stage must publish its
    # writes to the current transaction before the next query can see them.
    session.flush()

    chunking_results = chunk_pending_documents(
        session=session,
        tenant_slug=tenant_slug,
        max_chars=profile.max_chars,
        overlap_chars=profile.overlap_chars,
    )

    if not chunking_results:
        raise ValueError(f"Chunking profile {profile.name} created no chunks")

    session.flush()
    session.expire_all()

    embedding_results = embed_chunked_documents(
        session=session,
        tenant_slug=tenant_slug,
        provider=embedding_provider,
    )

    if len(embedding_results) != len(ingestion_results):
        raise ValueError(f"Chunking profile {profile.name} did not embed every document")

    session.flush()

    retrieval_report = run_retrieval_evaluation(
        session=session,
        cases=evaluation_cases,
        embedding_provider=embedding_provider,
        strategy=CHUNKING_RETRIEVAL_STRATEGY,
        limit=CHUNKING_RETRIEVAL_LIMIT,
    )

    return ChunkingProfileEvaluationReport(
        profile=profile,
        document_count=len(ingestion_results),
        chunk_count=sum(result.chunk_count for result in chunking_results),
        document_embedding_input_tokens=sum(
            result.total_input_tokens for result in embedding_results
        ),
        retrieval_report=retrieval_report,
    )


def print_chunking_comparison_report(
    report: ChunkingComparisonReport,
) -> None:
    print("Chunking comparison completed")
    print(f"Retrieval strategy: {CHUNKING_RETRIEVAL_STRATEGY}")
    print(f"Retrieval limit: {CHUNKING_RETRIEVAL_LIMIT}")
    print()

    for profile_report in (
        report.current,
        report.smaller,
    ):
        retrieval = profile_report.retrieval_report

        print(f"Profile: {profile_report.profile.name}")
        print(
            "Configuration: "
            f"max_chars={profile_report.profile.max_chars}, "
            f"overlap_chars="
            f"{profile_report.profile.overlap_chars}"
        )
        print(f"Documents: {profile_report.document_count}")
        print(f"Chunks: {profile_report.chunk_count}")
        print(f"Document embedding input tokens: {profile_report.document_embedding_input_tokens}")
        print(f"Mean Precision@{retrieval.requested_k}: {retrieval.mean_precision_at_k:.3f}")
        print(f"Mean Recall@{retrieval.requested_k}: {retrieval.mean_recall_at_k:.3f}")
        print(f"Mean retrieval latency: {retrieval.mean_retrieval_duration_ms:.3f} ms")
        print(f"P50 retrieval latency: {retrieval.p50_retrieval_duration_ms:.3f} ms")
        print(f"P95 retrieval latency: {retrieval.p95_retrieval_duration_ms:.3f} ms")
        print()

    current = report.current.retrieval_report
    smaller = report.smaller.retrieval_report

    print("Smaller minus current:")
    print(f"Precision delta: {smaller.mean_precision_at_k - current.mean_precision_at_k:+.3f}")
    print(f"Recall delta: {smaller.mean_recall_at_k - current.mean_recall_at_k:+.3f}")
    print(
        "Mean latency delta: "
        f"{smaller.mean_retrieval_duration_ms - current.mean_retrieval_duration_ms:+.3f} ms"
    )
    print(f"Chunk-count delta: {report.smaller.chunk_count - report.current.chunk_count:+d}")
    print(
        "Document-embedding-token delta: "
        f"{report.smaller.document_embedding_input_tokens - report.current.document_embedding_input_tokens:+d}"
    )


def _temporary_tenant_slug(
    profile: ChunkingProfile,
    run_token: str,
) -> str:
    normalized_token = run_token.strip().lower()

    if not normalized_token:
        raise ValueError("Chunking evaluation run token must not be empty")

    tenant_slug = f"chunk-eval-{profile.name}-{normalized_token}"

    if len(tenant_slug) > 63:
        raise ValueError("Temporary chunking evaluation tenant slug must not exceed 63 characters")

    return tenant_slug


def main() -> None:
    _, base_cases = load_retrieval_evaluation_catalog(DEFAULT_CATALOG_PATH)
    label_catalog = load_chunking_label_catalog(DEFAULT_LABEL_CATALOG_PATH)

    embedding_provider = OllamaEmbeddingClient()

    # Warm the local model once so first-profile startup does not dominate the
    # measured query-retrieval latency.
    embedding_provider.embed("Warm the local embedding model for chunking evaluation.")

    report = execute_chunking_comparison(
        session_factory=get_session_factory(),
        source_directory=DEFAULT_SOURCE_DIRECTORY,
        base_cases=base_cases,
        label_catalog=label_catalog,
        embedding_provider=embedding_provider,
    )

    print_chunking_comparison_report(report)


if __name__ == "__main__":
    main()
