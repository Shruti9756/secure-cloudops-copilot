from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import DocumentChunk, KnowledgeDocument, Tenant
from app.services.ingestion import calculate_content_sha256
from app.services.prompt_injection import detect_prompt_injection

DEFAULT_MAX_CHARS = 1200
DEFAULT_OVERLAP_CHARS = 200


@dataclass(frozen=True)
class TextChunk:
    """A retrieval-sized, deterministic piece of source text."""

    chunk_index: int
    content: str
    character_count: int
    content_sha256: str


@dataclass(frozen=True)
class ChunkingResult:
    """Summary of chunks rebuilt for one source document."""

    document_id: UUID
    source_path: str
    chunk_count: int


def chunk_text(
    content: str,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> list[TextChunk]:
    """Split text into overlapping character-based chunks.

    This strategy is deliberately model-independent. We can improve it later
    after measuring retrieval quality with real embeddings.
    """
    if max_chars <= 0:
        raise ValueError("max_chars must be greater than zero")

    if overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be zero or greater and less than max_chars")

    normalized_content = content.strip()

    if not normalized_content:
        return []

    chunks: list[TextChunk] = []
    start = 0
    chunk_index = 0

    while start < len(normalized_content):
        proposed_end = min(start + max_chars, len(normalized_content))
        end = _find_natural_break(
            normalized_content,
            start,
            proposed_end,
            max_chars,
        )

        chunk_content = normalized_content[start:end].strip()

        # Prevent an infinite loop if source text contains unusual whitespace.
        if not chunk_content:
            end = proposed_end
            chunk_content = normalized_content[start:end].strip()

        chunks.append(
            TextChunk(
                chunk_index=chunk_index,
                content=chunk_content,
                character_count=len(chunk_content),
                content_sha256=calculate_content_sha256(chunk_content),
            )
        )

        if end == len(normalized_content):
            break

        # Preserve context that crosses the previous chunk boundary.
        start = max(end - overlap_chars, start + 1)
        chunk_index += 1

    return chunks


def replace_document_chunks(
    session: Session,
    document: KnowledgeDocument,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> ChunkingResult:
    """Replace derived chunks for one document inside the active transaction."""
    text_chunks = chunk_text(
        document.content,
        max_chars=max_chars,
        overlap_chars=overlap_chars,
    )

    # Old chunks came from an older version of this document, so remove them first.
    session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
    session.flush()

    chunks_to_store: list[DocumentChunk] = []

    for text_chunk in text_chunks:
        prompt_injection_detection = detect_prompt_injection(text_chunk.content)

        chunks_to_store.append(
            DocumentChunk(
                document_id=document.id,
                organization_id=document.organization_id,
                chunk_index=text_chunk.chunk_index,
                content=text_chunk.content,
                content_sha256=text_chunk.content_sha256,
                character_count=text_chunk.character_count,
                chunk_metadata={
                    "chunking_strategy": "character-overlap-v1",
                    "max_chars": max_chars,
                    "overlap_chars": overlap_chars,
                    # Store bounded rule IDs, never duplicate the chunk text here.
                    "prompt_injection": {
                        "detected": prompt_injection_detection.is_suspicious,
                        "rule_ids": list(prompt_injection_detection.matched_rule_ids),
                    },
                },
            )
        )

    session.add_all(chunks_to_store)

    # “chunked” means chunks exist and are ready for the later embedding stage.
    document.ingestion_status = "chunked"

    return ChunkingResult(
        document_id=document.id,
        source_path=document.source_path,
        chunk_count=len(text_chunks),
    )


def chunk_pending_documents(
    session: Session,
    tenant_slug: str,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> list[ChunkingResult]:
    """Chunk only pending documents for one tenant workspace."""
    statement = (
        select(KnowledgeDocument)
        .join(KnowledgeDocument.tenant)
        .where(
            Tenant.slug == tenant_slug,
            KnowledgeDocument.ingestion_status == "pending",
        )
        .order_by(KnowledgeDocument.source_path)
    )
    documents = list(session.scalars(statement))

    return [
        replace_document_chunks(
            session=session,
            document=document,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
        )
        for document in documents
    ]


def _find_natural_break(
    content: str,
    start: int,
    proposed_end: int,
    max_chars: int,
) -> int:
    """Prefer paragraph, line, or word boundaries without making tiny chunks."""
    if proposed_end == len(content):
        return proposed_end

    candidate_breaks = (
        content.rfind("\n\n", start, proposed_end),
        content.rfind("\n", start, proposed_end),
        content.rfind(" ", start, proposed_end),
    )
    natural_break = max(candidate_breaks)

    if natural_break > start + (max_chars // 2):
        return natural_break

    return proposed_end
