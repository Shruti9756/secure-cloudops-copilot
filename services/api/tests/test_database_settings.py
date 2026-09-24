import pytest
from pydantic import ValidationError
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.infrastructure.postgres import resolve_database_url


def test_local_database_url_still_works() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://local:localpass@localhost:5432/localdb",
        redis_url="redis://localhost:6379/0",
    )

    url = resolve_database_url(settings)

    assert url.host == "localhost"
    assert url.database == "localdb"
    assert url.password == "localpass"


def test_split_database_settings_preserve_password_and_require_tls() -> None:
    password = "synthetic@:/%#password"
    settings = Settings(
        _env_file=None,
        database_url=None,
        database_host="db.example.internal",
        database_name="securecloudops",
        database_username="app_user",
        database_password=password,
        redis_url="redis://localhost:6379/0",
    )

    url = resolve_database_url(settings)

    assert url.query["sslmode"] == "require"
    assert make_url(url.render_as_string(hide_password=False)).password == password
    assert password not in repr(settings)
    assert password not in str(url)


def test_mixed_database_settings_are_rejected_without_exposing_password() -> None:
    password = "synthetic-secret-password"

    with pytest.raises(ValidationError) as error:
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://local:localpass@localhost/localdb",
            database_host="db.example.internal",
            database_password=password,
            redis_url="redis://localhost:6379/0",
        )

    assert password not in str(error.value)


def test_incomplete_split_database_settings_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url=None,
            database_host="db.example.internal",
            redis_url="redis://localhost:6379/0",
        )
