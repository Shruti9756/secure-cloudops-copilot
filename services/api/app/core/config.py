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
    # Local mode remains the default until Cognito browser login is configured.
    identity_provider: Literal["local", "cognito"] = "local"
    cognito_issuer: str | None = None
    cognito_app_client_id: str | None = None
    # Temporary local identity used only while APP_ENV is development.
    # Cognito JWT validation will replace this adapter in a later V0.2 step.
    local_development_identity_subject: str = "local-demo-admin"
    local_development_identity_display_name: str = "Local Demo Administrator"
    local_development_identity_role: Literal["admin", "manager", "engineer"] = "admin"
    database_url: str
    redis_url: str
    # Exact browser origins allowed to call the API. Multiple origins are
    # separated by commas so local .env files and ECS can supply the value.
    cors_allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    # Limit costly AI requests without hard-coding environment-specific policy.
    ask_user_rate_limit_requests: int = 10
    ask_organization_rate_limit_requests: int = 100
    ask_rate_limit_window_seconds: int = 60
    # Track actual chat-model usage in a fixed local-development quota window.
    ask_organization_token_quota_tokens: int = 50_000
    ask_token_quota_window_seconds: int = 86_400
    # Local worker scope; production will derive this from authenticated job data.
    # None means the worker processes pending work across all tenant workspaces.
    document_processor_tenant_slug: str | None = None
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
    document_storage_presigned_download_expiry_seconds: int = Field(
        default=300,
        ge=60,
        le=900,
    )
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_allowed_origin_list(self) -> list[str]:
        """Convert the comma-separated setting into Starlette's origin list."""
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
