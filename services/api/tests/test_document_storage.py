"""Tests for disabled-by-default durable document storage configuration."""

import pytest

from app.core.config import Settings
from app.services.document_storage import build_redacted_document_store


def make_settings(
    *,
    document_storage_backend: str,
    document_storage_s3_bucket: str | None = None,
) -> Settings:
    """Create isolated settings without loading the real local environment."""
    return Settings(
        database_url="postgresql+psycopg://example",
        redis_url="redis://example",
        document_storage_backend=document_storage_backend,
        document_storage_s3_bucket=document_storage_s3_bucket,
    )


def test_build_redacted_document_store_returns_none_when_disabled() -> None:
    store = build_redacted_document_store(
        make_settings(document_storage_backend="disabled"),
    )

    assert store is None


def test_build_redacted_document_store_requires_bucket_when_s3_is_enabled() -> None:
    with pytest.raises(ValueError, match="DOCUMENT_STORAGE_S3_BUCKET"):
        build_redacted_document_store(
            make_settings(document_storage_backend="s3"),
        )
