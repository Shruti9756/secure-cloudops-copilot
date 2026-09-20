from dataclasses import dataclass

from app.services.chunking import (
    DEFAULT_MAX_CHARS,
    DEFAULT_OVERLAP_CHARS,
    TextChunk,
    chunk_text,
)


@dataclass(frozen=True)
class ChunkingProfile:
    name: str
    max_chars: int
    overlap_chars: int


CURRENT_CHUNKING_PROFILE = ChunkingProfile(
    name="current-1200-200",
    max_chars=DEFAULT_MAX_CHARS,
    overlap_chars=DEFAULT_OVERLAP_CHARS,
)

SMALLER_CHUNKING_PROFILE = ChunkingProfile(
    name="smaller-600-100",
    max_chars=600,
    overlap_chars=100,
)


@dataclass(frozen=True)
class ChunkingProfileResult:
    profile_name: str
    chunk_count: int
    total_characters: int
    average_chunk_characters: float
    chunks: tuple[TextChunk, ...]


def evaluate_chunking_profile(
    *,
    profile: ChunkingProfile,
    content: str,
) -> ChunkingProfileResult:
    chunks = tuple(
        chunk_text(
            content,
            max_chars=profile.max_chars,
            overlap_chars=profile.overlap_chars,
        )
    )

    total_characters = sum(chunk.character_count for chunk in chunks)

    return ChunkingProfileResult(
        profile_name=profile.name,
        chunk_count=len(chunks),
        total_characters=total_characters,
        average_chunk_characters=(total_characters / len(chunks) if chunks else 0.0),
        chunks=chunks,
    )
