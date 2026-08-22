"""Validation and metadata creation for safe local document uploads."""

import re
from dataclasses import dataclass
from pathlib import Path

from app.services.document_extraction import extract_document_text

ALLOWED_DOCUMENT_UPLOAD_EXTENSIONS = frozenset({".md", ".txt", ".pdf", ".docx"})
MAX_DOCUMENT_UPLOAD_BYTES = 1_000_000

DOCUMENT_UPLOAD_CONTENT_TYPES = {
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".pdf": "application/pdf",
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
}

# Source paths become stable database identifiers, so they use a small safe character set.
UNSAFE_SOURCE_COMPONENT_PATTERN = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class ValidatedDocumentUpload:
    """A validated document whose extracted text is safe to pass to ingestion."""

    original_filename: str
    source_path: str
    content_type: str
    content: str


def validate_and_extract_upload(
    *,
    filename: str | None,
    content_bytes: bytes,
) -> ValidatedDocumentUpload:
    """Validate metadata and extract bounded plain text from one allowed file."""
    safe_filename = _build_safe_filename(filename)
    original_filename = (filename or "").strip()

    if not content_bytes:
        raise ValueError("Uploaded file must not be empty")

    if len(content_bytes) > MAX_DOCUMENT_UPLOAD_BYTES:
        raise ValueError(
            f"Uploaded file exceeds the {MAX_DOCUMENT_UPLOAD_BYTES} byte document-upload limit"
        )

    suffix = Path(safe_filename).suffix

    # The extension is server-validated before selecting a parser.
    content = extract_document_text(
        suffix=suffix,
        content_bytes=content_bytes,
    )

    return ValidatedDocumentUpload(
        original_filename=original_filename,
        source_path=f"uploads/{safe_filename}",
        content_type=DOCUMENT_UPLOAD_CONTENT_TYPES[suffix],
        content=content,
    )


def _build_safe_filename(filename: str | None) -> str:
    """Reject path-like input and normalize an allowed user filename."""
    if filename is None or not filename.strip():
        raise ValueError("Uploaded file must include a filename")

    normalized_filename = filename.strip()

    # Reject both separator styles because deployment will use Linux but development uses Windows.
    if "/" in normalized_filename or "\\" in normalized_filename:
        raise ValueError("Uploaded filename must not include a path")

    suffix = Path(normalized_filename).suffix.lower()
    if suffix not in ALLOWED_DOCUMENT_UPLOAD_EXTENSIONS:
        raise ValueError("Only .md, .txt, .pdf, and .docx uploads are supported")

    normalized_stem = UNSAFE_SOURCE_COMPONENT_PATTERN.sub(
        "-",
        Path(normalized_filename).stem.lower(),
    ).strip("-")

    if not normalized_stem:
        raise ValueError("Uploaded filename must include a valid name")

    return f"{normalized_stem}{suffix}"
