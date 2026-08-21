from collections.abc import Awaitable, Callable, Iterator
from typing import Annotated, Literal
from urllib.error import URLError
from uuid import uuid4

from fastapi import (
    Depends,
    FastAPI,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi import Path as ApiPath
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ValidationError
from redis import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import KnowledgeDocument, Tenant
from app.db.session import get_session_factory
from app.infrastructure.ollama import OllamaEmbeddingClient
from app.infrastructure.ollama_chat import OllamaChatClient
from app.infrastructure.postgres import postgres_is_available
from app.infrastructure.redis import get_redis_client, redis_is_available
from app.services.audit import AuditOutcome, record_audit_event
from app.services.ingestion import get_or_create_tenant, ingest_document
from app.services.rag import GroundedAnswer, answer_grounded_question
from app.services.rate_limit import (
    build_rate_limit_key,
    check_rate_limit,
)
from app.services.response_cache import (
    build_ask_response_cache_key,
    load_cached_response,
    store_cached_response,
)
from app.services.retrieval import DEFAULT_RETRIEVAL_LIMIT, MAX_RETRIEVAL_LIMIT
from app.services.upload_validation import (
    MAX_TEXT_UPLOAD_BYTES,
    validate_and_decode_text_upload,
)

APP_VERSION = "0.1.0"

# Temporary development scope. Authentication will derive the tenant later.
DEMO_TENANT_SLUG = "nimbuscart"

# These patterns make the server build the only permitted deployment document path.
SERVICE_NAME_PATTERN = r"^[a-z][a-z0-9-]{0,62}$"
SEMANTIC_VERSION_PATTERN = r"^\d+\.\d+\.\d+$"

RUNBOOK_NAME_PATTERN = r"^[a-z][a-z0-9-]{0,62}$"

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
        "safety_validation_failed",
    ]
    answer: str
    tenant: str
    embedding_model: str
    generation_model: str | None
    sources: list[RetrievedSourceResponse]
    citation_validation_passed: bool | None
    citation_validation_errors: list[str]
    safety_validation_passed: bool | None
    safety_validation_errors: list[str]
    query_input_tokens: int
    prompt_tokens: int | None
    completion_tokens: int | None


class DocumentUploadResponse(BaseModel):
    """Safe API response after a text document enters the ingestion pipeline."""

    status: Literal["accepted"]
    action: Literal["created", "updated", "unchanged"]
    tenant: str
    source_path: str


class DocumentStatusItemResponse(BaseModel):
    """Safe lifecycle information for one tenant-scoped knowledge document."""

    source_path: str
    title: str
    ingestion_status: Literal["pending", "chunked", "embedded"]


class DocumentStatusListResponse(BaseModel):
    """A safe document list for the local tenant; document bodies stay private."""

    tenant: str
    documents: list[DocumentStatusItemResponse]


class DeploymentContextResponse(BaseModel):
    """Approved deployment context returned through a server-scoped read-only route."""

    tenant: str
    service: str
    version: str
    title: str
    source_identifier: str
    content: str


class RunbookContextResponse(BaseModel):
    """Approved runbook context returned through a server-scoped read-only route."""

    tenant: str
    runbook_name: str
    title: str
    source_identifier: str
    content: str


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
    # Allow the approved frontend to display safe cache observability metadata.
    expose_headers=[
        "Retry-After",
        "X-Cache",
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-RateLimit-Reset",
        "X-Request-ID",
    ],
)


@app.middleware("http")
async def add_server_generated_request_id(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Attach one server-generated ID to every request and its response."""
    # Never trust a client-supplied correlation ID in this local security baseline.
    request_id = uuid4().hex
    request.state.request_id = request_id

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id

    return response


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


def get_client_identifier(request: Request) -> str:
    """Return the direct client identity without trusting spoofable proxy headers."""
    if request.client is None:
        return "unknown-client"

    # We will configure trusted proxy handling explicitly before using AWS-forwarded IPs.
    return request.client.host


def get_answer_status(
    answer: GroundedAnswer,
) -> Literal[
    "grounded",
    "insufficient_evidence",
    "citation_validation_failed",
    "safety_validation_failed",
]:
    """Map internal RAG outcomes to a stable, client-safe API status."""
    if not answer.sources:
        return "insufficient_evidence"

    if answer.citation_validation is not None and not answer.citation_validation.is_valid:
        return "citation_validation_failed"

    if answer.safety_validation is not None and not answer.safety_validation.is_safe:
        return "safety_validation_failed"

    return "grounded"


def build_ask_response(answer: GroundedAnswer) -> AskResponse:
    """Convert internal RAG data into the safe JSON response contract."""
    citation_validation = answer.citation_validation
    safety_validation = answer.safety_validation

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
        safety_validation_passed=(
            safety_validation.is_safe if safety_validation is not None else None
        ),
        safety_validation_errors=(
            list(safety_validation.errors) if safety_validation is not None else []
        ),
        query_input_tokens=answer.query_input_token_count,
        prompt_tokens=answer.prompt_token_count,
        completion_tokens=answer.completion_token_count,
    )


def record_ask_audit_event(
    session: Session,
    *,
    request_id: str,
    event_type: str,
    outcome: AuditOutcome,
    audit_status: str,
    cache_status: str | None,
    rate_limit_remaining: int | None,
    ask_response: AskResponse | None = None,
) -> None:
    """Record one safe ask-request outcome without logging raw AI content."""
    audit_tenant = session.scalar(select(Tenant).where(Tenant.slug == DEMO_TENANT_SLUG))

    record_audit_event(
        session,
        tenant=audit_tenant,
        event_type=event_type,
        outcome=outcome,
        actor_type="local_demo",
        actor_id=None,
        request_id=request_id,
        metadata={
            "audit_status": audit_status,
            "cache_status": cache_status,
            "response_status": ask_response.status if ask_response is not None else None,
            "source_count": len(ask_response.sources) if ask_response is not None else 0,
            "embedding_model": ask_response.embedding_model if ask_response is not None else None,
            "generation_model": ask_response.generation_model if ask_response is not None else None,
            "citation_validation_passed": (
                ask_response.citation_validation_passed if ask_response is not None else None
            ),
            "safety_validation_passed": (
                ask_response.safety_validation_passed if ask_response is not None else None
            ),
            "rate_limit_remaining": rate_limit_remaining,
        },
    )

    # The audit event must be durable before this request outcome is considered recorded.
    session.commit()


def record_document_upload_audit_event(
    session: Session,
    *,
    tenant: Tenant | None,
    request_id: str,
    outcome: AuditOutcome,
    upload_status: str,
    source_path: str | None,
    content_type: str | None,
    ingestion_action: str | None,
) -> None:
    """Record a document-upload outcome without storing a filename or document content."""
    record_audit_event(
        session,
        tenant=tenant,
        event_type="document.upload",
        outcome=outcome,
        actor_type="local_demo",
        actor_id=None,
        request_id=request_id,
        metadata={
            "upload_status": upload_status,
            "source_path": source_path,
            "content_type": content_type,
            "ingestion_action": ingestion_action,
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


@app.post(
    "/api/v1/documents",
    response_model=DocumentUploadResponse,
    tags=["documents"],
)
async def upload_text_document(
    http_request: Request,
    uploaded_file: Annotated[
        UploadFile,
        File(
            description=(
                "A UTF-8 Markdown (.md) or plain-text (.txt) knowledge document. "
                "Maximum size: 1 MB."
            )
        ),
    ],
    session: Annotated[Session, Depends(get_database_session)],
) -> DocumentUploadResponse:
    """Validate and ingest one local text document into the server-controlled tenant."""
    # Read one additional byte, allowing validation to reject oversized files safely.
    try:
        content_bytes = await uploaded_file.read(MAX_TEXT_UPLOAD_BYTES + 1)
    finally:
        await uploaded_file.close()

    try:
        validated_upload = validate_and_decode_text_upload(
            filename=uploaded_file.filename,
            content_bytes=content_bytes,
        )
    except ValueError as error:
        record_document_upload_audit_event(
            session,
            tenant=None,
            request_id=http_request.state.request_id,
            outcome="denied",
            upload_status="validation_failed",
            source_path=None,
            content_type=None,
            ingestion_action=None,
        )
        session.commit()

        # Validation details are safe because they never include uploaded file content.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error

    tenant = get_or_create_tenant(
        session,
        slug=DEMO_TENANT_SLUG,
        name="NimbusCart",
    )
    ingestion_result = ingest_document(
        session=session,
        tenant=tenant,
        source_path=validated_upload.source_path,
        content=validated_upload.content,
        ingestion_source="api-upload",
        content_type=validated_upload.content_type,
    )
    record_document_upload_audit_event(
        session,
        tenant=tenant,
        request_id=http_request.state.request_id,
        outcome="succeeded",
        upload_status="accepted",
        source_path=validated_upload.source_path,
        content_type=validated_upload.content_type,
        ingestion_action=ingestion_result.action,
    )
    session.commit()

    return DocumentUploadResponse(
        status="accepted",
        action=ingestion_result.action,
        tenant=DEMO_TENANT_SLUG,
        source_path=ingestion_result.source_path,
    )


@app.get(
    "/api/v1/documents",
    response_model=DocumentStatusListResponse,
    tags=["documents"],
)
def list_document_statuses(
    session: Annotated[Session, Depends(get_database_session)],
) -> DocumentStatusListResponse:
    """List safe processing statuses for documents in the server-controlled tenant."""

    statement = (
        select(KnowledgeDocument)
        .join(Tenant)
        .where(Tenant.slug == DEMO_TENANT_SLUG)
        .order_by(KnowledgeDocument.source_path)
    )
    documents = list(session.scalars(statement))

    # Never expose document content, chunks, vectors, hashes, or redaction metadata here.
    return DocumentStatusListResponse(
        tenant=DEMO_TENANT_SLUG,
        documents=[
            DocumentStatusItemResponse(
                source_path=document.source_path,
                title=document.title,
                ingestion_status=document.ingestion_status,
            )
            for document in documents
        ],
    )


@app.get(
    "/api/v1/deployments/{service}/{version}",
    response_model=DeploymentContextResponse,
    tags=["knowledge"],
)
def get_deployment_context(
    service: Annotated[
        str,
        ApiPath(
            pattern=SERVICE_NAME_PATTERN,
            description="Lowercase deployment service name.",
        ),
    ],
    version: Annotated[
        str,
        ApiPath(
            pattern=SEMANTIC_VERSION_PATTERN,
            description="Deployment semantic version, for example 2.4.0.",
        ),
    ],
    session: Annotated[Session, Depends(get_database_session)],
) -> DeploymentContextResponse:
    """Return one indexed deployment record from the server-controlled tenant."""

    # The caller never supplies a document path; the server constructs the only allowed one.
    source_path = f"deployments/{service}-{version}.md"

    statement = (
        select(KnowledgeDocument)
        .join(Tenant)
        .where(
            Tenant.slug == DEMO_TENANT_SLUG,
            KnowledgeDocument.source_path == source_path,
            # Pending or changed documents must not be exposed as approved context.
            KnowledgeDocument.ingestion_status == "embedded",
        )
    )
    document = session.scalar(statement)

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approved deployment context was not found.",
        )

    return DeploymentContextResponse(
        tenant=DEMO_TENANT_SLUG,
        service=service,
        version=version,
        title=document.title,
        source_identifier=document.source_path,
        content=document.content,
    )


@app.get(
    "/api/v1/runbooks/{runbook_name}",
    response_model=RunbookContextResponse,
    tags=["knowledge"],
)
def get_runbook_context(
    runbook_name: Annotated[
        str,
        ApiPath(
            pattern=RUNBOOK_NAME_PATTERN,
            description="Lowercase runbook identifier.",
        ),
    ],
    session: Annotated[Session, Depends(get_database_session)],
) -> RunbookContextResponse:
    """Return one indexed runbook from the server-controlled tenant."""

    # The caller never supplies a document path; the server constructs the only allowed one.
    source_path = f"runbooks/{runbook_name}.md"

    statement = (
        select(KnowledgeDocument)
        .join(Tenant)
        .where(
            Tenant.slug == DEMO_TENANT_SLUG,
            KnowledgeDocument.source_path == source_path,
            # Pending or changed documents must not be exposed as approved context.
            KnowledgeDocument.ingestion_status == "embedded",
        )
    )
    document = session.scalar(statement)

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approved runbook context was not found.",
        )

    return RunbookContextResponse(
        tenant=DEMO_TENANT_SLUG,
        runbook_name=runbook_name,
        title=document.title,
        source_identifier=document.source_path,
        content=document.content,
    )


@app.post("/api/v1/ask", response_model=AskResponse, tags=["rag"])
def ask_question(
    request: AskRequest,
    http_request: Request,
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
    """Answer one tenant-scoped question through guarded and rate-limited RAG."""
    if not request.question.strip():
        record_ask_audit_event(
            session,
            request_id=http_request.state.request_id,
            event_type="rag.answer_request",
            outcome="denied",
            audit_status="invalid_question",
            cache_status=None,
            rate_limit_remaining=None,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Question must not be empty",
        )

    settings = get_settings()
    rate_limit_key = build_rate_limit_key(
        tenant_slug=DEMO_TENANT_SLUG,
        client_identifier=get_client_identifier(http_request),
    )
    rate_limit = check_rate_limit(
        cache,
        cache_key=rate_limit_key,
        limit=settings.ask_rate_limit_requests,
        window_seconds=settings.ask_rate_limit_window_seconds,
    )

    # Unlike caching, a missing rate limiter is a security failure, so fail closed.
    if not rate_limit.is_enforced:
        record_ask_audit_event(
            session,
            request_id=http_request.state.request_id,
            event_type="rag.answer_request",
            outcome="failed",
            audit_status="rate_limit_unavailable",
            cache_status=None,
            rate_limit_remaining=None,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Request protection is temporarily unavailable. Retry shortly.",
            headers={"Retry-After": "1"},
        )

    if not rate_limit.is_allowed:
        record_ask_audit_event(
            session,
            request_id=http_request.state.request_id,
            event_type="rag.answer_request",
            outcome="denied",
            audit_status="rate_limited",
            cache_status=None,
            rate_limit_remaining=0,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Retry after the current rate-limit window.",
            headers={
                "Retry-After": str(rate_limit.reset_after_seconds),
                "X-RateLimit-Limit": str(rate_limit.limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(rate_limit.reset_after_seconds),
            },
        )

    response.headers["X-RateLimit-Limit"] = str(rate_limit.limit)
    response.headers["X-RateLimit-Remaining"] = str(rate_limit.remaining)
    response.headers["X-RateLimit-Reset"] = str(rate_limit.reset_after_seconds)

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
                and cached_response.safety_validation_passed is True
            ):
                response.headers["X-Cache"] = "HIT"
                record_ask_audit_event(
                    session,
                    event_type="rag.answer_completed",
                    outcome="succeeded",
                    audit_status="cache_hit",
                    cache_status="HIT",
                    rate_limit_remaining=rate_limit.remaining,
                    ask_response=cached_response,
                    request_id=http_request.state.request_id,
                )
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
        record_ask_audit_event(
            session,
            event_type="rag.answer_request",
            outcome="failed",
            audit_status="model_provider_unavailable",
            cache_status=response.headers["X-Cache"],
            rate_limit_remaining=rate_limit.remaining,
            request_id=http_request.state.request_id,
        )
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

    audit_outcome: AuditOutcome = (
        "denied"
        if ask_response.status in {"citation_validation_failed", "safety_validation_failed"}
        else "succeeded"
    )
    record_ask_audit_event(
        session,
        event_type="rag.answer_completed",
        outcome=audit_outcome,
        audit_status="completed",
        cache_status=response.headers["X-Cache"],
        rate_limit_remaining=rate_limit.remaining,
        ask_response=ask_response,
        request_id=http_request.state.request_id,
    )

    return ask_response
