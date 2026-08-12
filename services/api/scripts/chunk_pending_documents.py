from argparse import ArgumentParser, Namespace

from app.db.session import get_session_factory
from app.services.chunking import (
    DEFAULT_MAX_CHARS,
    DEFAULT_OVERLAP_CHARS,
    chunk_pending_documents,
)


def parse_args() -> Namespace:
    parser = ArgumentParser(
        description="Create retrieval-sized chunks for pending SecureCloudOps documents."
    )
    parser.add_argument(
        "--tenant-slug",
        default="nimbuscart",
        help="Only process pending documents owned by this tenant.",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=DEFAULT_MAX_CHARS,
        help="Maximum characters per chunk.",
    )
    parser.add_argument(
        "--overlap-chars",
        type=int,
        default=DEFAULT_OVERLAP_CHARS,
        help="Repeated trailing context between adjacent chunks.",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # All chunk replacements either commit together or roll back together.
    with get_session_factory().begin() as session:
        results = chunk_pending_documents(
            session=session,
            tenant_slug=args.tenant_slug,
            max_chars=args.max_chars,
            overlap_chars=args.overlap_chars,
        )

    if not results:
        print("No pending documents to chunk.")
        return 0

    for result in results:
        print(f"chunked {result.source_path} ({result.chunk_count} chunks)")

    total_chunks = sum(result.chunk_count for result in results)
    print(f"Summary: chunked_documents={len(results)}, chunks_created={total_chunks}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
