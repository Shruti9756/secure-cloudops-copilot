"""Offline tests for the Redis-free document outbox publisher settings."""

import os
from unittest.mock import patch

import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy.engine import make_url

from app.core.config import DocumentOutboxPublisherSettings, Settings
from app.infrastructure.postgres import resolve_database_url

FAKE_QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/000000000000/synthetic-test"
LOCAL_DATABASE_URL = "postgresql+psycopg://publisher:localpass@localhost/publisherdb"
SYNTHETIC_PASSWORD = "synthetic@:/%#password"


def make_settings(**overrides: object) -> DocumentOutboxPublisherSettings:
    with patch.dict(os.environ, {}, clear=True):
        return DocumentOutboxPublisherSettings(_env_file=None, **overrides)


def make_enabled_settings(**overrides: object) -> DocumentOutboxPublisherSettings:
    values = {
        "document_queue_backend": "sqs",
        "document_queue_sqs_url": FAKE_QUEUE_URL,
        "database_url": LOCAL_DATABASE_URL,
    }
    values.update(overrides)
    return make_settings(**values)


def test_disabled_defaults_require_neither_database_nor_redis() -> None:
    settings = make_settings()

    assert settings.document_queue_backend == "disabled"
    assert settings.document_queue_sqs_url is None
    assert settings.document_outbox_poll_interval_seconds == 5
    assert settings.database_url is None
    assert settings.database_host is None
    assert settings.database_password is None
    assert settings.aws_profile is None
    assert settings.aws_region == "us-east-1"


def test_enabled_publisher_accepts_local_database_url_without_redis() -> None:
    settings = make_enabled_settings()
    url = resolve_database_url(settings)

    assert isinstance(settings.database_url, SecretStr)
    assert url.drivername == "postgresql+psycopg"
    assert url.host == "localhost"
    assert url.database == "publisherdb"
    assert url.username == "publisher"
    assert url.password == "localpass"
    assert LOCAL_DATABASE_URL not in repr(settings)


def test_enabled_split_database_settings_preserve_password_and_require_tls() -> None:
    settings = make_enabled_settings(
        database_url=None,
        database_host="db.example.internal",
        database_port=5432,
        database_name="securecloudops",
        database_username="securecloudops_app",
        database_password=SYNTHETIC_PASSWORD,
    )
    url = resolve_database_url(settings)

    assert isinstance(settings.database_password, SecretStr)
    assert url.host == "db.example.internal"
    assert url.port == 5432
    assert url.database == "securecloudops"
    assert url.username == "securecloudops_app"
    assert url.query["sslmode"] == "require"
    assert make_url(url.render_as_string(hide_password=False)).password == SYNTHETIC_PASSWORD
    assert SYNTHETIC_PASSWORD not in repr(settings)
    assert SYNTHETIC_PASSWORD not in str(url)


@pytest.mark.parametrize(
    "overrides",
    [
        {"database_url": None},
        {"database_url": ""},
        {"database_url": "   "},
        {"database_url": None, "database_host": "db.example.internal"},
        {
            "database_host": "db.example.internal",
            "database_password": SYNTHETIC_PASSWORD,
        },
    ],
    ids=["missing", "empty-url", "blank-url", "incomplete-split", "mixed"],
)
def test_enabled_publisher_rejects_invalid_database_settings(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValidationError) as error:
        make_enabled_settings(**overrides)

    assert SYNTHETIC_PASSWORD not in str(error.value)
    assert LOCAL_DATABASE_URL not in str(error.value)


@pytest.mark.parametrize("queue_url", [None, "", "   "])
def test_enabled_publisher_requires_a_nonblank_queue_url(queue_url: str | None) -> None:
    with pytest.raises(ValidationError, match="DOCUMENT_QUEUE_SQS_URL"):
        make_enabled_settings(document_queue_sqs_url=queue_url)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("document_outbox_poll_interval_seconds", 0),
        ("document_outbox_poll_interval_seconds", 301),
        ("database_port", 0),
        ("database_port", 65536),
        ("document_queue_backend", "unsupported"),
    ],
)
def test_publisher_rejects_invalid_bounded_fields(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        make_enabled_settings(**{field: value})


def test_publisher_ignores_unrelated_redis_and_ollama_environment() -> None:
    unrelated_environment = {
        "REDIS_PASSWORD": "synthetic-unused-redis-password",
        "OLLAMA_BASE_URL": "http://synthetic-unused-model.internal",
        "EMBEDDING_PROVIDER": "unsupported-unused-provider",
    }

    with patch.dict(os.environ, unrelated_environment, clear=True):
        settings = DocumentOutboxPublisherSettings(_env_file=None)

    fields = DocumentOutboxPublisherSettings.model_fields
    assert "redis_url" not in fields
    assert "redis_host" not in fields
    assert "redis_password" not in fields
    assert "ollama_base_url" not in fields
    assert "embedding_provider" not in fields
    assert "synthetic-unused-redis-password" not in repr(settings)
    assert settings.document_queue_backend == "disabled"


def test_shared_api_and_worker_settings_still_require_redis() -> None:
    with (
        patch.dict(os.environ, {}, clear=True),
        pytest.raises(ValidationError, match="Redis"),
    ):
        Settings(_env_file=None, database_url=LOCAL_DATABASE_URL)
