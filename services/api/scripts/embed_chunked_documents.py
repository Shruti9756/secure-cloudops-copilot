import argparse
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import DocumentChunk, KnowledgeDocument, Tenant
from app.db.session import get_session_factory
from app.infrastructure.ollama import OllamaEmbeddingClient
from app.services.embedding_persistence import (
    DocumentEmbeddingResult,
    embed_chunked_documents,
)

DEFAULT_TENANT_SLUG = "nimbuscart"


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line interface for the local embedding job."""
    parser = argparse.ArgumentParser(
        description="Create local Ollama embeddings for chunked knowledge documents."
    )
    parser.add_argument(
        "--tenant",
        default=DEFAULT_TENANT_SLUG,
        help=f"Tenant workspace to process (default: {DEFAULT_TENANT_SLUG}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show eligible documents without calling Ollama or writing PostgreSQL data.",
    )

    return parser


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse and validate command-line arguments independently of database work."""
    parser = build_parser()
    args = parser.parse_args(argv)
    args.tenant = args.tenant.strip()

    if not args.tenant:
        parser.error("--tenant must not be empty")

    return args


def list_embedding_work(
    session: Session,
    tenant_slug: str,
) -> list[tuple[str, int]]:
    """Return chunked documents and their chunk counts without changing anything."""
    statement = (
        select(
            KnowledgeDocument.source_path,
            func.count(DocumentChunk.id).label("chunk_count"),
        )
        .join(KnowledgeDocument.tenant)
        .outerjoin(KnowledgeDocument.chunks)
        .where(
            Tenant.slug == tenant_slug,
            KnowledgeDocument.ingestion_status == "chunked",
        )
        .group_by(KnowledgeDocument.id, KnowledgeDocument.source_path)
        .order_by(KnowledgeDocument.source_path)
    )

    return [(source_path, chunk_count) for source_path, chunk_count in session.execute(statement)]


def print_dry_run_summary(
    tenant_slug: str,
    documents: list[tuple[str, int]],
) -> None:
    """Print a human-readable preview before any embedding work is allowed."""
    print(f"Dry run for tenant: {tenant_slug}")

    if not documents:
        print("No chunked documents are awaiting embeddings.")
        return

    total_chunks = sum(chunk_count for _, chunk_count in documents)

    for source_path, chunk_count in documents:
        print(f"would embed {source_path} ({chunk_count} chunks)")

    print(f"Summary: documents={len(documents)}, chunks={total_chunks}")


def print_embedding_summary(
    tenant_slug: str,
    results: list[DocumentEmbeddingResult],
) -> None:
    """Print the committed work without showing private document text or vectors."""
    embedded_chunks = sum(result.embedded_chunk_count for result in results)
    skipped_chunks = sum(result.skipped_chunk_count for result in results)
    input_tokens = sum(result.total_input_tokens for result in results)

    print(f"Embedded tenant: {tenant_slug}")
    print(
        "Summary: "
        f"documents={len(results)}, "
        f"embedded_chunks={embedded_chunks}, "
        f"skipped_chunks={skipped_chunks}, "
        f"input_tokens={input_tokens}"
    )


def main(argv: Sequence[str] | None = None) -> None:
    """Run a preview or one all-or-nothing local Ollama embedding transaction."""
    args = parse_arguments(argv)
    session_factory = get_session_factory()

    if args.dry_run:
        # A normal session performs read-only preview work and closes afterward.
        with session_factory() as session:
            documents = list_embedding_work(
                session=session,
                tenant_slug=args.tenant,
            )

        print_dry_run_summary(
            tenant_slug=args.tenant,
            documents=documents,
        )
        return

    provider = OllamaEmbeddingClient()

    # `begin()` commits only if every document embeds successfully; otherwise it rolls back.
    with session_factory.begin() as session:
        results = embed_chunked_documents(
            session=session,
            tenant_slug=args.tenant,
            provider=provider,
        )

    print_embedding_summary(
        tenant_slug=args.tenant,
        results=results,
    )


if __name__ == "__main__":
    main()
