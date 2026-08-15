from collections.abc import Iterator
from typing import Annotated, Literal
from urllib.error import URLError

from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ValidationError
from redis import Redis
from sqlalchemy.orm import Session

from app.db.session import get_session_factory
from app.infrastructure.ollama import OllamaEmbeddingClient
from app.infrastructure.ollama_chat import OllamaChatClient
from app.infrastructure.postgres import postgres_is_available
from app.infrastructure.redis import get_redis_client, redis_is_available
from app.services.rag import GroundedAnswer, answer_grounded_question
from app.services.response_cache import (
    build_ask_response_cache_key,
    load_cached_response,
    store_cached_response,
)
from app.services.retrieval import DEFAULT_RETRIEVAL_LIMIT, MAX_RETRIEVAL_LIMIT

APP_VERSION = "0.1.0"

# Temporary development scope. Authentication will derive the tenant later.
DEMO_TENANT_SLUG = "nimbuscart"

# Explicit local browser origins; CORS is tightened further for production.
DEVELOPMENT_FRONTEND_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


class ServiceStatus(BaseModel):
    status: Literal["ok"]
    service: Literal["secure-cloudops-api"]
    version: str


class ReadinessStatus(BaseModel):
    status: Literal["ready", "not_ready"]
    dependencies: dict[str, Literal["ok", "unavailable"]]


class AskRequest(BaseModel):
    """Untrusted client input for one read-only RAG question."""

    question: str = Field(
        min_length=1,
        max_length=2000,
        description="Incident-investigation question to answer from indexed evidence.",
    )
    limit: int = Field(
        default=DEFAULT_RETRIEVAL_LIMIT,
        ge=1,
        le=MAX_RETRIEVAL_LIMIT,
        description="Maximum number of relevant evidence chunks to use.",
    )


class RetrievedSourceResponse(BaseModel):
    """Safe source metadata returned to a client; raw vector data is never exposed."""

    source_identifier: str
    document_title: str
    cosine_distance: float


class AskResponse(BaseModel):
    """A grounded RAG answer plus traceability and local-model usage metadata."""

    status: Literal[
        "grounded",
        "insufficient_evidence",
        "citation_validation_failed",
    ]
    answer: str
    tenant: str
    embedding_model: str
    generation_model: str | None
    sources: list[RetrievedSourceResponse]
    citation_validation_passed: bool | None
    citation_validation_errors: list[str]
    query_input_tokens: int
    prompt_tokens: int | None
    completion_tokens: int | None


app = FastAPI(
    title="SecureCloudOps Copilot API",
    description="API for secure RAG, incident investigation, and controlled MCP tools.",
    version=APP_VERSION,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=DEVELOPMENT_FRONTEND_ORIGINS,
    # No cookies or authorization headers exist yet, so credentials remain disabled.
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def get_status() -> ServiceStatus:
    """Return application liveness without checking external dependencies."""
    return ServiceStatus(
        status="ok",
        service="secure-cloudops-api",
        version=APP_VERSION,
    )


def get_readiness_status() -> ReadinessStatus:
    """Return readiness based on the dependencies needed by the API."""
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


def get_database_session() -> Iterator[Session]:
    """Provide one PostgreSQL session per request and close it after the response."""
    session_factory = get_session_factory()

    with session_factory() as session:
        yield session


def get_embedding_provider() -> OllamaEmbeddingClient:
    """Provide the local embedding client; tests can override this dependency."""
    return OllamaEmbeddingClient()


def get_chat_provider() -> OllamaChatClient:
    """Provide the local chat client; tests can override this dependency."""
    return OllamaChatClient()


def get_redis_cache() -> Redis:
    """Provide Redis for short-lived response caching; tests override it."""
    return get_redis_client()


def get_answer_status(
    answer: GroundedAnswer,
) -> Literal["grounded", "insufficient_evidence", "citation_validation_failed"]:
    """Map internal RAG outcomes to a stable, client-safe API status."""
    if not answer.sources:
        return "insufficient_evidence"

    if answer.citation_validation is not None and not answer.citation_validation.is_valid:
        return "citation_validation_failed"

    return "grounded"


def build_ask_response(answer: GroundedAnswer) -> AskResponse:
    """Convert internal RAG data into the safe JSON response contract."""
    citation_validation = answer.citation_validation

    return AskResponse(
        status=get_answer_status(answer),
        answer=answer.answer_text,
        # The tenant is server-controlled in this development version.
        tenant=DEMO_TENANT_SLUG,
        embedding_model=answer.embedding_model,
        generation_model=answer.generation_model,
        sources=[
            RetrievedSourceResponse(
                source_identifier=f"{source.source_path}#chunk-{source.chunk_index}",
                document_title=source.document_title,
                cosine_distance=source.cosine_distance,
            )
            for source in answer.sources
        ],
        citation_validation_passed=(
            citation_validation.is_valid if citation_validation is not None else None
        ),
        citation_validation_errors=(
            list(citation_validation.errors) if citation_validation is not None else []
        ),
        query_input_tokens=answer.query_input_token_count,
        prompt_tokens=answer.prompt_token_count,
        completion_tokens=answer.completion_token_count,
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


@app.post("/api/v1/ask", response_model=AskResponse, tags=["rag"])
def ask_question(
    request: AskRequest,
    response: Response,
    session: Annotated[Session, Depends(get_database_session)],
    cache: Annotated[Redis, Depends(get_redis_cache)],
    embedding_provider: Annotated[
        OllamaEmbeddingClient,
        Depends(get_embedding_provider),
    ],
    chat_provider: Annotated[
        OllamaChatClient,
        Depends(get_chat_provider),
    ],
) -> AskResponse:
    """Answer one tenant-scoped question through the guarded local RAG pipeline."""
    if not request.question.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Question must not be empty",
        )

    # The key is tenant-scoped and hashes the question instead of exposing it in Redis.
    cache_key = build_ask_response_cache_key(
        tenant_slug=DEMO_TENANT_SLUG,
        question=request.question,
        limit=request.limit,
    )
    cache_lookup = load_cached_response(cache, cache_key=cache_key)

    if cache_lookup.payload is not None:
        try:
            cached_response = AskResponse.model_validate(cache_lookup.payload)
        except ValidationError:
            # A corrupted or outdated entry becomes a miss instead of breaking RAG.
            pass
        else:
            # Never trust a cache entry unless it is still a safe grounded response.
            if (
                cached_response.status == "grounded"
                and cached_response.sources
                and cached_response.citation_validation_passed is True
            ):
                response.headers["X-Cache"] = "HIT"
                return cached_response

    # Redis problems never block incident investigation; they only disable caching.
    response.headers["X-Cache"] = "MISS" if cache_lookup.is_available else "BYPASS"

    try:
        answer = answer_grounded_question(
            session=session,
            tenant_slug=DEMO_TENANT_SLUG,
            question=request.question,
            embedding_provider=embedding_provider,
            chat_provider=chat_provider,
            limit=request.limit,
        )
    except (TimeoutError, URLError) as error:
        # Do not expose local network details to an API client.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The local AI provider is unavailable. Check Ollama and retry.",
        ) from error

    ask_response = build_ask_response(answer)

    # Cache only successful evidence-backed answers, never uncertainty or validation failure.
    if ask_response.status == "grounded" and cache_lookup.is_available:
        store_cached_response(
            cache,
            cache_key=cache_key,
            payload=ask_response.model_dump(mode="json"),
        )

    return ask_response
