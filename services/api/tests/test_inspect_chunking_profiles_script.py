from pathlib import Path

import pytest

from scripts.inspect_chunking_profiles import build_chunking_snapshot


def test_build_chunking_snapshot_compares_both_profiles(
    tmp_path: Path,
) -> None:
    runbook_directory = tmp_path / "runbooks"
    runbook_directory.mkdir()

    source_file = runbook_directory / "checkout.md"
    source_file.write_text(
        "checkout latency investigation " * 100,
        encoding="utf-8",
    )

    snapshot = build_chunking_snapshot(tmp_path)

    assert snapshot["document_count"] == 1

    total_chunks = snapshot["total_chunks_by_profile"]
    assert isinstance(total_chunks, dict)
    assert total_chunks["current-1200-200"] > 0
    assert total_chunks["smaller-600-100"] >= total_chunks["current-1200-200"]

    documents = snapshot["documents"]
    assert isinstance(documents, list)

    document = documents[0]
    assert document["source_path"] == "runbooks/checkout.md"

    profiles = document["profiles"]
    assert [profile["profile_name"] for profile in profiles] == [
        "current-1200-200",
        "smaller-600-100",
    ]


def test_build_chunking_snapshot_rejects_a_missing_directory(
    tmp_path: Path,
) -> None:
    missing_directory = tmp_path / "missing"

    with pytest.raises(
        ValueError,
        match="source directory does not exist",
    ):
        build_chunking_snapshot(missing_directory)
