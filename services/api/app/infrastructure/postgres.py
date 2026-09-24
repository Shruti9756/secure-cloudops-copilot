from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine, make_url

from app.core.config import Settings, get_settings


def build_staging_database_url(
    *,
    host: str,
    port: int,
    database: str,
    username: str,
    password: str,
) -> URL:
    return URL.create(
        "postgresql+psycopg",
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
        query={"sslmode": "require"},
    )


def resolve_database_url(settings: Settings) -> URL:
    if settings.database_url is not None:
        return make_url(settings.database_url.get_secret_value())

    if (
        settings.database_host is None
        or settings.database_name is None
        or settings.database_username is None
        or settings.database_password is None
    ):
        raise ValueError("Split database settings are incomplete.")

    return build_staging_database_url(
        host=settings.database_host,
        port=settings.database_port,
        database=settings.database_name,
        username=settings.database_username,
        password=settings.database_password.get_secret_value(),
    )


@lru_cache
def get_engine() -> Engine:
    return create_engine(
        resolve_database_url(get_settings()),
        pool_pre_ping=True,
    )


def postgres_is_available() -> bool:
    with get_engine().connect() as connection:
        return connection.execute(text("SELECT 1")).scalar_one() == 1
