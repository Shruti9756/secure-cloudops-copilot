"""Factories and contracts for optional durable storage of redacted text."""

from functools import lru_cache
from typing import Protocol

from app.core.config import Settings, get_settings
from app.infrastructure.s3 import S3DocumentReference, S3RedactedDocumentStore


class RedactedDocumentStore(Protocol):
    """Store only content that has already passed extraction and redaction."""

    def store_redacted_document(
        self,
        *,
        tenant_slug: str,
        source_path: str,
        redacted_content: str,
        content_sha256: str,
    ) -> S3DocumentReference:
        """Persist one safe text copy and return its non-sensitive reference."""


def build_redacted_document_store(
    settings: Settings,
) -> RedactedDocumentStore | None:
    """Return no store locally, or the configured private S3-backed store."""
    if settings.document_storage_backend == "disabled":
        return None

    bucket_name = settings.document_storage_s3_bucket

    if bucket_name is None or not bucket_name.strip():
        raise ValueError("DOCUMENT_STORAGE_S3_BUCKET must be set when DOCUMENT_STORAGE_BACKEND=s3")

    return S3RedactedDocumentStore(
        bucket_name=bucket_name,
        settings=settings,
    )


@lru_cache
def get_redacted_document_store() -> RedactedDocumentStore | None:
    """Build one reusable store from environment-backed application settings."""
    return build_redacted_document_store(get_settings())
