from collections.abc import Awaitable, Callable, Iterator
from functools import lru_cache
from time import perf_counter
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
from app.infrastructure.cognito import (
    COGNITO_AUTHENTICATION_FAILURE_MESSAGE,
    COGNITO_IDENTITY_PROVIDER_UNAVAILABLE_MESSAGE,
    CognitoAccessTokenVerifier,
    CognitoInvalidAccessTokenError,
    CognitoJwksUnavailableError,
)
from app.infrastructure.ollama import OllamaEmbeddingClient
from app.infrastructure.ollama_chat import OllamaChatClient
from app.infrastructure.postgres import postgres_is_available
from app.infrastructure.redis import get_redis_client, redis_is_available
from app.infrastructure.s3 import S3DocumentStorageUnavailableError
from app.services.audit import AuditOutcome, record_audit_event
from app.services.authorization import (
    AuthenticatedPrincipal,
    AuthorizationDeniedError,
    authorize_tenant_action,
)
from app.services.cognito_identity import (
    CognitoUserNotProvisionedError,
    get_cognito_principal,
)
from app.services.document_access import DEFAULT_DOCUMENT_ACCESS_LEVELS
from app.services.document_storage import (
    RedactedDocumentStore,
    get_redacted_document_store,
)
from app.services.ingestion import ingest_document
from app.services.local_identity import (
    LocalDevelopmentIdentityUnavailableError,
    get_local_development_principal,
)
from app.services.metrics import (
    metrics_content_type,
    observe_http_request,
    observe_rag_request,
    render_metrics,
)
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
    MAX_DOCUMENT_UPLOAD_BYTES,
    validate_and_extract_upload,
)
from app.services.workspace import (
    WORKSPACE_CONTEXT_HEADER,
    WorkspaceContextError,
    normalize_workspace_slug,
)

APP_VERSION = "0.1.0"


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
    # Browser requests use explicit bearer tokens, never cross-site cookies.
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", WORKSPACE_CONTEXT_HEADER],
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


def _route_template_for_request(request: Request) -> str:
    """Return a bounded route template instead of a user-controlled URL path."""
    route = request.scope.get("route")
    route_template = getattr(route, "path", None)

    return route_template if isinstance(route_template, str) else "unmatched"


@app.middleware("http")
async def add_server_generated_request_id(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Attach one request ID and record privacy-safe HTTP metrics."""
    # Never trust a client-supplied correlation ID in this local security baseline.
    request_id = uuid4().hex
    request.state.request_id = request_id
    started_at = perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        # Record unexpected failures without logging request content or identifiers.
        observe_http_request(
            method=request.method,
            route=_route_template_for_request(request),
            status_code=500,
            duration_seconds=perf_counter() - started_at,
        )
        raise

    observe_http_request(
        method=request.method,
        route=_route_template_for_request(request),
        status_code=response.status_code,
        duration_seconds=perf_counter() - started_at,
    )
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


COGNITO_AUTHORIZATION_FAILURE_MESSAGE = (
    "The authenticated identity is not authorized to access SecureCloudOps."
)


def _get_bearer_access_token(request: Request) -> str:
    """Extract one bearer token without logging or storing credential contents."""

    authorization_header = request.headers.get("Authorization")

    if authorization_header is None:
        raise CognitoInvalidAccessTokenError(COGNITO_AUTHENTICATION_FAILURE_MESSAGE)

    scheme, separator, access_token = authorization_header.partition(" ")

    if scheme.lower() != "bearer" or not separator or not access_token.strip():
        raise CognitoInvalidAccessTokenError(COGNITO_AUTHENTICATION_FAILURE_MESSAGE)

    return access_token.strip()


@lru_cache
def get_cognito_access_token_verifier(
    issuer: str,
    app_client_id: str,
) -> CognitoAccessTokenVerifier:
    """Reuse Cognito JWKS-key caching for the stable server configuration."""

    return CognitoAccessTokenVerifier(
        issuer=issuer,
        app_client_id=app_client_id,
    )


def get_current_principal(
    request: Request,
    session: Annotated[Session, Depends(get_database_session)],
) -> AuthenticatedPrincipal:
    """Resolve either the local development identity or a verified Cognito user."""

    settings = get_settings()

    if settings.identity_provider == "local":
        try:
            return get_local_development_principal(
                session,
                app_env=settings.app_env,
                identity_subject=settings.local_development_identity_subject,
            )
        except LocalDevelopmentIdentityUnavailableError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Identity service is temporarily unavailable. Try again later.",
            ) from error

    if not settings.cognito_issuer or not settings.cognito_app_client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=COGNITO_IDENTITY_PROVIDER_UNAVAILABLE_MESSAGE,
        )

    try:
        verified_token = get_cognito_access_token_verifier(
            settings.cognito_issuer,
            settings.cognito_app_client_id,
        ).verify(_get_bearer_access_token(request))

        return get_cognito_principal(
            session,
            subject=verified_token.subject,
        )
    except CognitoJwksUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=COGNITO_IDENTITY_PROVIDER_UNAVAILABLE_MESSAGE,
        ) from error
    except CognitoInvalidAccessTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=COGNITO_AUTHENTICATION_FAILURE_MESSAGE,
            headers={"WWW-Authenticate": "Bearer"},
        ) from error
    except CognitoUserNotProvisionedError as error:
        # A verified identity still needs an explicit local user and membership.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=COGNITO_AUTHORIZATION_FAILURE_MESSAGE,
        ) from error


def get_requested_workspace_slug(request: Request) -> str:
    """Read and validate the workspace selector before membership authorization."""
    try:
        return normalize_workspace_slug(request.headers.get(WORKSPACE_CONTEXT_HEADER))
    except WorkspaceContextError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error


def get_authorized_knowledge_tenant(
    session: Annotated[Session, Depends(get_database_session)],
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
    workspace_slug: Annotated[str, Depends(get_requested_workspace_slug)],
) -> Tenant:
    """Return the local tenant only after organization membership permits reading."""
    try:
        return authorize_tenant_action(
            session,
            principal=principal,
            tenant_slug=workspace_slug,
            permission="knowledge:read",
        ).tenant
    except AuthorizationDeniedError as error:
        # A 404 avoids confirming whether a protected tenant exists.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Requested tenant workspace was not found.",
        ) from error


def get_authorized_document_write_tenant(
    session: Annotated[Session, Depends(get_database_session)],
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
    workspace_slug: Annotated[str, Depends(get_requested_workspace_slug)],
) -> Tenant:
    """Return the tenant only when membership permits document uploads."""
    try:
        return authorize_tenant_action(
            session,
            principal=principal,
            tenant_slug=workspace_slug,
            permission="documents:write",
        ).tenant
    except AuthorizationDeniedError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Requested tenant workspace was not found.",
        ) from error


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


def build_ask_response(
    answer: GroundedAnswer,
    *,
    tenant: Tenant,
) -> AskResponse:
    """Convert internal RAG data into the safe JSON response contract."""
    citation_validation = answer.citation_validation
    safety_validation = answer.safety_validation

    return AskResponse(
        status=get_answer_status(answer),
        answer=answer.answer_text,
        # The tenant is server-controlled in this development version.
        tenant=tenant.slug,
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


def get_audit_actor(
    principal: AuthenticatedPrincipal,
) -> tuple[str, str | None]:
    """Return safe audit identity fields without recording credentials or email."""

    if principal.authentication_source == "cognito":
        return "cognito_user", principal.identity_subject

    # Keep the earlier local-demo audit format for local development.
    return "local_demo", None


def record_ask_audit_event(
    session: Session,
    principal: AuthenticatedPrincipal,
    tenant: Tenant,
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
    actor_type, actor_id = get_audit_actor(principal)

    record_audit_event(
        session,
        tenant=tenant,
        event_type=event_type,
        outcome=outcome,
        actor_type=actor_type,
        actor_id=actor_id,
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
    principal: AuthenticatedPrincipal,
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
    actor_type, actor_id = get_audit_actor(principal)
    record_audit_event(
        session,
        tenant=tenant,
        event_type="document.upload",
        outcome=outcome,
        actor_type=actor_type,
        actor_id=actor_id,
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


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    """Expose Prometheus metrics with finite, non-sensitive labels only."""
    return Response(
        content=render_metrics(),
        headers={"Content-Type": metrics_content_type()},
    )


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
async def upload_document(
    http_request: Request,
    uploaded_file: Annotated[
        UploadFile,
        File(
            description=(
                "A Markdown (.md), plain-text (.txt), digital PDF (.pdf), or "
                "Word DOCX (.docx) knowledge document. PDFs must contain "
                "selectable text. Maximum raw file size: 1 MB."
            )
        ),
    ],
    session: Annotated[Session, Depends(get_database_session)],
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
    tenant: Annotated[Tenant, Depends(get_authorized_document_write_tenant)],
    document_store: Annotated[
        RedactedDocumentStore | None,
        Depends(get_redacted_document_store),
    ],
) -> DocumentUploadResponse:
    """Validate and ingest one supported document for the server-controlled tenant."""
    # Read one additional byte, allowing validation to reject oversized files safely.
    try:
        content_bytes = await uploaded_file.read(MAX_DOCUMENT_UPLOAD_BYTES + 1)
    finally:
        await uploaded_file.close()

    try:
        validated_upload = validate_and_extract_upload(
            filename=uploaded_file.filename,
            content_bytes=content_bytes,
        )
    except ValueError as error:
        record_document_upload_audit_event(
            session,
            principal=principal,
            tenant=tenant,
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

    try:
        # The authorization dependency already returned the permitted tenant.
        ingestion_result = ingest_document(
            session=session,
            tenant=tenant,
            source_path=validated_upload.source_path,
            content=validated_upload.content,
            ingestion_source="api-upload",
            content_type=validated_upload.content_type,
            document_store=document_store,
        )
    except S3DocumentStorageUnavailableError as error:
        # A failed mirror must not leave a pending database document behind.
        session.rollback()
        record_document_upload_audit_event(
            session,
            tenant=tenant,
            principal=principal,
            request_id=http_request.state.request_id,
            outcome="failed",
            upload_status="storage_unavailable",
            source_path=None,
            content_type=None,
            ingestion_action=None,
        )
        session.commit()

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document storage is temporarily unavailable. Try again later.",
        ) from error

    record_document_upload_audit_event(
        session,
        principal=principal,
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
        tenant=tenant.slug,
        source_path=ingestion_result.source_path,
    )


@app.get(
    "/api/v1/documents",
    response_model=DocumentStatusListResponse,
    tags=["documents"],
)
def list_document_statuses(
    session: Annotated[Session, Depends(get_database_session)],
    tenant: Annotated[Tenant, Depends(get_authorized_knowledge_tenant)],
) -> DocumentStatusListResponse:
    """List safe processing statuses for documents in the server-controlled tenant."""

    # The authorization dependency resolved this tenant from verified membership.
    statement = (
        select(KnowledgeDocument)
        .where(KnowledgeDocument.tenant_id == tenant.id)
        .order_by(KnowledgeDocument.source_path)
    )
    documents = list(session.scalars(statement))

    # Never expose document content, chunks, vectors, hashes, or redaction metadata here.
    return DocumentStatusListResponse(
        tenant=tenant.slug,
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
    tenant: Annotated[Tenant, Depends(get_authorized_knowledge_tenant)],
) -> DeploymentContextResponse:
    """Return one indexed deployment record from the server-controlled tenant."""

    # The caller never supplies a document path; the server constructs the only allowed one.
    source_path = f"deployments/{service}-{version}.md"

    statement = (
        select(KnowledgeDocument)
        .join(Tenant)
        .where(
            KnowledgeDocument.tenant_id == tenant.id,
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
        tenant=tenant.slug,
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
    tenant: Annotated[Tenant, Depends(get_authorized_knowledge_tenant)],
) -> RunbookContextResponse:
    """Return one indexed runbook from the server-controlled tenant."""

    # The caller never supplies a document path; the server constructs the only allowed one.
    source_path = f"runbooks/{runbook_name}.md"

    statement = (
        select(KnowledgeDocument)
        .join(Tenant)
        .where(
            KnowledgeDocument.tenant_id == tenant.id,
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
        tenant=tenant.slug,
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
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
    tenant: Annotated[Tenant, Depends(get_authorized_knowledge_tenant)],
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
        observe_rag_request(
            status="invalid_question",
            cache_status="NOT_CHECKED",
        )
        record_ask_audit_event(
            session,
            principal=principal,
            tenant=tenant,
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
        tenant_slug=tenant.slug,
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
        observe_rag_request(
            status="rate_limit_unavailable",
            cache_status="NOT_CHECKED",
        )
        record_ask_audit_event(
            session,
            principal=principal,
            tenant=tenant,
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
        observe_rag_request(
            status="rate_limited",
            cache_status="NOT_CHECKED",
        )
        record_ask_audit_event(
            session,
            principal=principal,
            tenant=tenant,
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
        tenant_slug=tenant.slug,
        document_access_levels=DEFAULT_DOCUMENT_ACCESS_LEVELS,
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
                observe_rag_request(
                    status=cached_response.status,
                    cache_status="HIT",
                )
                record_ask_audit_event(
                    session,
                    principal=principal,
                    tenant=tenant,
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
    cache_status = "MISS" if cache_lookup.is_available else "BYPASS"
    response.headers["X-Cache"] = cache_status

    try:
        answer = answer_grounded_question(
            session=session,
            tenant_slug=tenant.slug,
            question=request.question,
            embedding_provider=embedding_provider,
            chat_provider=chat_provider,
            limit=request.limit,
        )
    except (TimeoutError, URLError) as error:
        # Do not expose local network details to an API client.
        observe_rag_request(
            status="model_provider_unavailable",
            cache_status=cache_status,
        )
        record_ask_audit_event(
            session,
            principal=principal,
            tenant=tenant,
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

    ask_response = build_ask_response(
        answer,
        tenant=tenant,
    )

    observe_rag_request(
        status=ask_response.status,
        cache_status=cache_status,
    )

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
        principal=principal,
        tenant=tenant,
        event_type="rag.answer_completed",
        outcome=audit_outcome,
        audit_status="completed",
        cache_status=response.headers["X-Cache"],
        rate_limit_remaining=rate_limit.remaining,
        ask_response=ask_response,
        request_id=http_request.state.request_id,
    )

    return ask_response
