"""Factories and contracts for optional durable storage of redacted text."""

from collections.abc import Mapping
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

    def create_presigned_download_url(
        self,
        *,
        reference: S3DocumentReference,
        expires_in_seconds: int,
    ) -> str:
        """Create a short-lived URL for a server-authorized redacted text download."""


def redacted_document_reference_from_metadata(
    metadata: Mapping[str, object],
) -> S3DocumentReference | None:
    """Read one validated S3 reference from server-created document metadata."""
    storage = metadata.get("redacted_text_storage")

    if not isinstance(storage, dict) or storage.get("provider") != "s3":
        return None

    bucket_name = storage.get("bucket_name")
    object_key = storage.get("object_key")
    version_id = storage.get("version_id")
    e_tag = storage.get("e_tag")

    if not isinstance(bucket_name, str) or not bucket_name.strip():
        return None

    if not isinstance(object_key, str) or not object_key.startswith("tenants/"):
        return None

    if version_id is not None and not isinstance(version_id, str):
        return None

    if e_tag is not None and not isinstance(e_tag, str):
        return None

    return S3DocumentReference(
        bucket_name=bucket_name,
        object_key=object_key,
        version_id=version_id,
        e_tag=e_tag,
    )


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
