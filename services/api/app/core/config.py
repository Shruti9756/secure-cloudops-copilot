from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
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
    # Temporary local identity used only while APP_ENV is development.
    # Cognito JWT validation will replace this adapter in a later V0.2 step.
    local_development_identity_subject: str = "local-demo-admin"
    local_development_identity_display_name: str = "Local Demo Administrator"
    local_development_identity_role: Literal["admin", "manager", "engineer"] = "admin"
    database_url: str
    redis_url: str
    # Limit costly AI requests without hard-coding environment-specific policy.
    ask_rate_limit_requests: int = 10
    ask_rate_limit_window_seconds: int = 60
    # Local worker scope; production will derive this from authenticated job data.
    document_processor_tenant_slug: str = "nimbuscart"
    document_processor_poll_interval_seconds: int = Field(
        default=5,
        ge=1,
        le=300,
    )
    # Local Python uses loopback; Docker Compose overrides this with the ollama service name.
    ollama_base_url: str = "http://127.0.0.1:11434"
    # Local development uses an AWS CLI profile; AWS deployments will use an IAM role.
    aws_profile: str | None = None
    aws_region: str = "us-east-1"
    # Disabled keeps Docker and local tests independent from AWS credentials.
    document_storage_backend: Literal["disabled", "s3"] = "disabled"
    document_storage_s3_bucket: str | None = None
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
