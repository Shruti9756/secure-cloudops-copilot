from functools import lru_cache

from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.postgres import get_engine


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(
        bind=get_engine(),
        autoflush=False,
        expire_on_commit=False,
    )
