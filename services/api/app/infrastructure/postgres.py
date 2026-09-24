from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine

from app.core.config import get_settings


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


@lru_cache
def get_engine() -> Engine:
    return create_engine(
        get_settings().database_url,
        pool_pre_ping=True,
    )


def postgres_is_available() -> bool:
    with get_engine().connect() as connection:
        return connection.execute(text("SELECT 1")).scalar_one() == 1
