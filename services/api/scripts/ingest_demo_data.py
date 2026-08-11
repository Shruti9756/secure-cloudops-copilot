from argparse import ArgumentParser
from collections import Counter
from pathlib import Path

from app.db.session import get_session_factory
from app.services.ingestion import ingest_directory


def parse_args() -> object:
    parser = ArgumentParser(description="Ingest Markdown demo data into SecureCloudOps PostgreSQL.")
    parser.add_argument(
        "--source-dir",
        type=Path,
        required=True,
        help="Directory containing Markdown files to ingest.",
    )
    parser.add_argument(
        "--tenant-slug",
        default="nimbuscart",
        help="Stable tenant identifier.",
    )
    parser.add_argument(
        "--tenant-name",
        default="NimbusCart",
        help="Human-readable tenant name.",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    with get_session_factory().begin() as session:
        results = ingest_directory(
            session=session,
            source_directory=args.source_dir,
            tenant_slug=args.tenant_slug,
            tenant_name=args.tenant_name,
        )

    counts = Counter(result.action for result in results)

    for result in results:
        print(f"{result.action:9} {result.source_path}")

    print(
        "Summary: "
        f"created={counts['created']}, "
        f"updated={counts['updated']}, "
        f"unchanged={counts['unchanged']}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
