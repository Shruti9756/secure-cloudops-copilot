from app.services.chunking import (
    DEFAULT_MAX_CHARS,
    DEFAULT_OVERLAP_CHARS,
)
from app.services.chunking_evaluation import (
    CURRENT_CHUNKING_PROFILE,
    SMALLER_CHUNKING_PROFILE,
    ChunkingProfile,
    evaluate_chunking_profile,
)


def test_current_chunking_profile_uses_existing_defaults() -> None:
    assert CURRENT_CHUNKING_PROFILE.name == "current-1200-200"
    assert CURRENT_CHUNKING_PROFILE.max_chars == DEFAULT_MAX_CHARS
    assert CURRENT_CHUNKING_PROFILE.overlap_chars == DEFAULT_OVERLAP_CHARS


def test_smaller_chunks_create_at_least_as_many_chunks() -> None:
    content = "checkout latency " * 200

    current_result = evaluate_chunking_profile(
        profile=CURRENT_CHUNKING_PROFILE,
        content=content,
    )

    smaller_result = evaluate_chunking_profile(
        profile=SMALLER_CHUNKING_PROFILE,
        content=content,
    )

    assert smaller_result.chunk_count >= current_result.chunk_count


def test_empty_content_returns_zero_statistics() -> None:
    result = evaluate_chunking_profile(
        profile=ChunkingProfile(
            name="current",
            max_chars=1200,
            overlap_chars=200,
        ),
        content="   ",
    )

    assert result.chunk_count == 0
    assert result.total_characters == 0
    assert result.average_chunk_characters == 0.0
    assert result.chunks == ()


def test_chunks_have_content_hashes() -> None:
    result = evaluate_chunking_profile(
        profile=ChunkingProfile(
            name="current",
            max_chars=1200,
            overlap_chars=200,
        ),
        content="A document containing searchable knowledge.",
    )

    assert result.chunk_count == 1
    assert len(result.chunks[0].content_sha256) == 64
