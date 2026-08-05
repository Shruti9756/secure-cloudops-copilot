from typing import Literal

from fastapi import FastAPI, Response, status
from pydantic import BaseModel

from app.infrastructure.postgres import postgres_is_available
from app.infrastructure.redis import redis_is_available

APP_VERSION = "0.1.0"


class ServiceStatus(BaseModel):
    status: Literal["ok"]
    service: Literal["secure-cloudops-api"]
    version: str


class ReadinessStatus(BaseModel):
    status: Literal["ready", "not_ready"]
    dependencies: dict[str, Literal["ok", "unavailable"]]


app = FastAPI(
    title="SecureCloudOps Copilot API",
    description="API for secure RAG, incident investigation, and controlled MCP tools.",
    version=APP_VERSION,
)


def get_status() -> ServiceStatus:
    return ServiceStatus(
        status="ok",
        service="secure-cloudops-api",
        version=APP_VERSION,
    )


def get_readiness_status() -> ReadinessStatus:
    postgres_status = "ok" if postgres_is_available() else "unavailable"
    redis_status = "ok" if redis_is_available() else "unavailable"

    is_ready = postgres_status == "ok" and redis_status == "ok"

    return ReadinessStatus(
        status="ready" if is_ready else "not_ready",
        dependencies={
            "postgres": postgres_status,
            "redis": redis_status,
        },
    )


@app.get("/", response_model=ServiceStatus, include_in_schema=False)
def root() -> ServiceStatus:
    return get_status()


@app.get("/health", response_model=ServiceStatus, tags=["system"])
def health_check() -> ServiceStatus:
    return get_status()


@app.get("/ready", response_model=ReadinessStatus, tags=["system"])
def readiness_check(response: Response) -> ReadinessStatus:
    readiness = get_readiness_status()

    if readiness.status == "not_ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return readiness


@app.get("/api/v1/status", response_model=ServiceStatus, tags=["system"])
def api_status() -> ServiceStatus:
    return get_status()
