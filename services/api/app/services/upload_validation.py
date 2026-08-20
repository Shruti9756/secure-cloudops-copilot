"""Validation and decoding for safe local text-document uploads."""

import re
from dataclasses import dataclass
from pathlib import Path

ALLOWED_TEXT_UPLOAD_EXTENSIONS = frozenset({".md", ".txt"})
MAX_TEXT_UPLOAD_BYTES = 1_000_000

TEXT_UPLOAD_CONTENT_TYPES = {
    ".md": "text/markdown",
    ".txt": "text/plain",
}

# Source paths become stable database identifiers, so they use a small safe character set.
UNSAFE_SOURCE_COMPONENT_PATTERN = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class ValidatedTextUpload:
    """A UTF-8 text upload that is safe to pass into the ingestion pipeline."""

    original_filename: str
    source_path: str
    content_type: str
    content: str


def validate_and_decode_text_upload(
    *,
    filename: str | None,
    content_bytes: bytes,
) -> ValidatedTextUpload:
    """Validate an allowed text file and create a server-controlled source path."""
    safe_filename = _build_safe_filename(filename)

    if not content_bytes:
        raise ValueError("Uploaded file must not be empty")

    if len(content_bytes) > MAX_TEXT_UPLOAD_BYTES:
        raise ValueError(
            f"Uploaded file exceeds the {MAX_TEXT_UPLOAD_BYTES} byte text-upload limit"
        )

    try:
        content = content_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("Uploaded file must be valid UTF-8 text") from error

    if not content.strip():
        raise ValueError("Uploaded file must not contain only whitespace")

    suffix = Path(safe_filename).suffix

    return ValidatedTextUpload(
        original_filename=filename.strip(),
        source_path=f"uploads/{safe_filename}",
        content_type=TEXT_UPLOAD_CONTENT_TYPES[suffix],
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
    if suffix not in ALLOWED_TEXT_UPLOAD_EXTENSIONS:
        raise ValueError("Only .md and .txt uploads are supported")

    normalized_stem = UNSAFE_SOURCE_COMPONENT_PATTERN.sub(
        "-",
        Path(normalized_filename).stem.lower(),
    ).strip("-")

    if not normalized_stem:
        raise ValueError("Uploaded filename must include a valid name")

    return f"{normalized_stem}{suffix}"
