import argparse
from collections.abc import Sequence

from app.db.session import get_session_factory
from app.infrastructure.ollama import OllamaEmbeddingClient
from app.services.retrieval import (
    DEFAULT_RETRIEVAL_LIMIT,
    MAX_RETRIEVAL_LIMIT,
    RetrievedChunk,
    retrieve_relevant_chunks,
)

DEFAULT_TENANT_SLUG = "nimbuscart"


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line interface for local semantic search."""
    parser = argparse.ArgumentParser(
        description="Search embedded knowledge documents with local Ollama vectors."
    )
    parser.add_argument(
        "query",
        help="Natural-language question to search for.",
    )
    parser.add_argument(
        "--tenant",
        default=DEFAULT_TENANT_SLUG,
        help=f"Tenant workspace to search (default: {DEFAULT_TENANT_SLUG}).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_RETRIEVAL_LIMIT,
        help=(
            "Maximum number of source chunks to return "
            f"(default: {DEFAULT_RETRIEVAL_LIMIT}, maximum: {MAX_RETRIEVAL_LIMIT})."
        ),
    )

    return parser


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse and validate command arguments before calling Ollama or PostgreSQL."""
    parser = build_parser()
    args = parser.parse_args(argv)
    args.query = args.query.strip()
    args.tenant = args.tenant.strip()

    if not args.query:
        parser.error("query must not be empty")

    if not args.tenant:
        parser.error("--tenant must not be empty")

    if not 1 <= args.limit <= MAX_RETRIEVAL_LIMIT:
        parser.error(f"--limit must be between 1 and {MAX_RETRIEVAL_LIMIT}")

    return args


def print_retrieval_results(
    tenant_slug: str,
    embedding_model: str,
    query_input_tokens: int,
    results: list[RetrievedChunk],
) -> None:
    """Print retrieved evidence for local development without generating an AI answer."""
    print(f"Retrieved chunks for tenant: {tenant_slug}")
    print(f"Query embedding model: {embedding_model}")
    print(f"Query input tokens: {query_input_tokens}")

    if not results:
        print("No matching embedded chunks were found.")
        return

    for rank, result in enumerate(results, start=1):
        print()
        print(f"{rank}. {result.source_path} (chunk {result.chunk_index})")
        print(f"   Title: {result.document_title}")
        print(f"   Cosine distance: {result.cosine_distance:.4f}")
        print(f"   Content: {result.content}")


def main(argv: Sequence[str] | None = None) -> None:
    """Embed one question locally, then retrieve matching PostgreSQL chunks."""
    args = parse_arguments(argv)
    provider = OllamaEmbeddingClient()

    # This creates a vector for the question only; it does not write any database data.
    query_embedding = provider.embed(args.query)
    session_factory = get_session_factory()

    # A normal session is enough because semantic search is read-only work.
    with session_factory() as session:
        results = retrieve_relevant_chunks(
            session=session,
            tenant_slug=args.tenant,
            query_vector=query_embedding.vector,
            embedding_model=query_embedding.model_id,
            limit=args.limit,
        )

    print_retrieval_results(
        tenant_slug=args.tenant,
        embedding_model=query_embedding.model_id,
        query_input_tokens=query_embedding.input_text_token_count,
        results=results,
    )


if __name__ == "__main__":
    main()
