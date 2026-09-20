import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from app.services.chunking_evaluation import (
    CURRENT_CHUNKING_PROFILE,
    SMALLER_CHUNKING_PROFILE,
    ChunkingProfile,
    evaluate_chunking_profile,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SOURCE_DIRECTORY = REPOSITORY_ROOT / "docs" / "demo-data"

CHUNKING_PROFILES: tuple[ChunkingProfile, ...] = (
    CURRENT_CHUNKING_PROFILE,
    SMALLER_CHUNKING_PROFILE,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect how evaluation documents are split by each chunking profile."
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=DEFAULT_SOURCE_DIRECTORY,
        help=f"Markdown corpus directory (default: {DEFAULT_SOURCE_DIRECTORY}).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON output path. Prints JSON when omitted.",
    )
    return parser


def parse_arguments(
    argv: Sequence[str] | None = None,
) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def build_chunking_snapshot(
    source_directory: Path,
) -> dict[str, object]:
    if not source_directory.is_dir():
        raise ValueError(f"Chunking source directory does not exist: {source_directory}")

    source_files = tuple(sorted(source_directory.rglob("*.md")))

    if not source_files:
        raise ValueError(
            f"Chunking source directory contains no Markdown files: {source_directory}"
        )

    documents: list[dict[str, object]] = []
    total_chunks_by_profile = {profile.name: 0 for profile in CHUNKING_PROFILES}

    for source_file in source_files:
        source_path = source_file.relative_to(source_directory).as_posix()
        content = source_file.read_text(encoding="utf-8")
        profile_snapshots: list[dict[str, object]] = []

        for profile in CHUNKING_PROFILES:
            result = evaluate_chunking_profile(
                profile=profile,
                content=content,
            )
            total_chunks_by_profile[profile.name] += result.chunk_count

            profile_snapshots.append(
                {
                    "profile_name": profile.name,
                    "max_chars": profile.max_chars,
                    "overlap_chars": profile.overlap_chars,
                    "chunk_count": result.chunk_count,
                    "average_chunk_characters": result.average_chunk_characters,
                    "chunks": [
                        {
                            "chunk_index": chunk.chunk_index,
                            "character_count": chunk.character_count,
                            "content_sha256": chunk.content_sha256,
                            "content": chunk.content,
                        }
                        for chunk in result.chunks
                    ],
                }
            )

        documents.append(
            {
                "source_path": source_path,
                "profiles": profile_snapshots,
            }
        )

    return {
        "document_count": len(documents),
        "total_chunks_by_profile": total_chunks_by_profile,
        "documents": documents,
    }


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_arguments(argv)
    snapshot = build_chunking_snapshot(args.source_dir)
    serialized_snapshot = json.dumps(
        snapshot,
        indent=2,
        ensure_ascii=False,
    )

    if args.output is None:
        print(serialized_snapshot)
        return

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        f"{serialized_snapshot}\n",
        encoding="utf-8",
    )
    print(f"Chunking inspection written to: {args.output}")


if __name__ == "__main__":
    main()
