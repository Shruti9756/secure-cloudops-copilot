from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def find_env_file() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        env_file = parent / ".env"

        if env_file.is_file():
            return env_file

    return None


ENV_FILE = find_env_file()


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str
    redis_url: str
    # Local development uses an AWS CLI profile; AWS deployments will use an IAM role.
    aws_profile: str | None = None
    aws_region: str = "us-east-1"
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
