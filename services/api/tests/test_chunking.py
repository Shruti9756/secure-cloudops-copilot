import pytest

from app.services.chunking import chunk_text


def test_chunk_text_returns_no_chunks_for_blank_content() -> None:
    assert chunk_text("   \n\n  ") == []


def test_chunk_text_returns_one_chunk_for_short_content() -> None:
    chunks = chunk_text("Checkout latency runbook")

    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].content == "Checkout latency runbook"
    assert chunks[0].character_count == len("Checkout latency runbook")
    assert len(chunks[0].content_sha256) == 64


def test_chunk_text_splits_long_content_with_overlap() -> None:
    content = ("a" * 1000) + " " + ("b" * 1000)

    chunks = chunk_text(
        content,
        max_chars=1000,
        overlap_chars=200,
    )

    assert [chunk.chunk_index for chunk in chunks] == [0, 1, 2]
    assert all(chunk.character_count <= 1000 for chunk in chunks)

    # The final 200 characters of chunk 0 appear again at the start of chunk 1.
    assert chunks[0].content[-200:] == chunks[1].content[:200]


def test_chunk_text_rejects_invalid_chunk_settings() -> None:
    with pytest.raises(ValueError, match="max_chars"):
        chunk_text("content", max_chars=0)

    with pytest.raises(ValueError, match="overlap_chars"):
        chunk_text("content", max_chars=100, overlap_chars=100)
