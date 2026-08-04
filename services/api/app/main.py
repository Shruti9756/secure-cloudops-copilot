from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

APP_VERSION = "0.1.0"


class ServiceStatus(BaseModel):
    status: Literal["ok"]
    service: Literal["secure-cloudops-api"]
    version: str


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


@app.get("/", response_model=ServiceStatus, include_in_schema=False)
async def root() -> ServiceStatus:
    return get_status()


@app.get("/health", response_model=ServiceStatus, tags=["system"])
async def health_check() -> ServiceStatus:
    return get_status()


@app.get("/api/v1/status", response_model=ServiceStatus, tags=["system"])
async def api_status() -> ServiceStatus:
    return get_status()