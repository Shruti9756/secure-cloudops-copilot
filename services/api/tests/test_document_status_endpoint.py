import json
from unittest.mock import Mock
from uuid import uuid4

from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError

from app.db.models import KnowledgeDocument, Tenant
from app.main import (
    app,
    get_authorized_knowledge_access,
    get_database_session,
    get_redis_cache,
)
from app.services.authorization import AuthorizedTenant
from app.services.document_job_status import build_document_job_status_key

client = TestClient(app)


def make_document(
    *,
    tenant_id: object,
    source_path: str,
    title: str,
    ingestion_status: str,
) -> KnowledgeDocument:
    """Create a document-shaped test object without a real database."""
    return KnowledgeDocument(
        id=uuid4(),
        tenant_id=tenant_id,
        title=title,
        source_path=source_path,
        source_sha256="a" * 64,
        content="Internal document content must not be exposed by the status endpoint.",
        ingestion_status=ingestion_status,
        processing_attempt_count=0,
    )


def test_list_document_statuses_returns_safe_tenant_scoped_lifecycle_data() -> None:
    tenant = Tenant(
        id=uuid4(),
        organization_id=uuid4(),
        slug="nimbuscart",
        name="NimbusCart",
    )
    processing_document = make_document(
        tenant_id=tenant.id,
        source_path="uploads/redis-investigation.md",
        title="Redis Investigation",
        ingestion_status="pending",
    )
    embedded_document = make_document(
        tenant_id=tenant.id,
        source_path="runbooks/checkout-latency.md",
        title="Checkout Latency Investigation",
        ingestion_status="embedded",
    )
    failed_document = make_document(
        tenant_id=tenant.id,
        source_path="uploads/failed-document.md",
        title="Failed Document",
        ingestion_status="failed",
    )

    session = Mock()
    session.scalars.return_value = [
        processing_document,
        embedded_document,
        failed_document,
    ]

    progress_keys = [
        build_document_job_status_key(
            organization_id=tenant.organization_id,
            tenant_id=tenant.id,
            document_id=document.id,
        )
        for document in (
            processing_document,
            embedded_document,
            failed_document,
        )
    ]
    progress_payload = json.dumps(
        {
            "stage": "embedding",
            "source_sha256": processing_document.source_sha256,
            "processing_attempt_count": 0,
            "updated_at": "2026-09-15T12:30:00+00:00",
        }
    )

    redis_client = Mock()
    redis_client.mget.return_value = [
        progress_payload,
        None,
        None,
    ]

    app.dependency_overrides[get_database_session] = lambda: session
    app.dependency_overrides[get_authorized_knowledge_access] = lambda: AuthorizedTenant(
        tenant=tenant,
        role="engineer",
    )
    app.dependency_overrides[get_redis_cache] = lambda: redis_client

    try:
        response = client.get("/api/v1/documents")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["x-request-id"]
    assert response.json() == {
        "tenant": "nimbuscart",
        "documents": [
            {
                "source_path": "uploads/redis-investigation.md",
                "title": "Redis Investigation",
                "ingestion_status": "pending",
                "processing_progress": {
                    "stage": "embedding",
                    "updated_at": "2026-09-15T12:30:00Z",
                },
            },
            {
                "source_path": "runbooks/checkout-latency.md",
                "title": "Checkout Latency Investigation",
                "ingestion_status": "embedded",
                "processing_progress": None,
            },
            {
                "source_path": "uploads/failed-document.md",
                "title": "Failed Document",
                "ingestion_status": "failed",
                "processing_progress": None,
            },
        ],
    }
    assert "Internal document content" not in response.text
    redis_client.mget.assert_called_once_with(progress_keys)

    statement = session.scalars.call_args.args[0]
    assert statement.whereclause is not None

    where_sql = str(statement.whereclause)
    assert "knowledge_documents.tenant_id" in where_sql
    assert "knowledge_documents.organization_id" in where_sql
    assert "knowledge_documents.access_level" in where_sql

    assert "JOIN tenants" not in str(statement)
    session.commit.assert_not_called()


def test_list_document_statuses_succeeds_when_progress_redis_is_unavailable() -> None:
    tenant = Tenant(
        id=uuid4(),
        organization_id=uuid4(),
        slug="nimbuscart",
        name="NimbusCart",
    )
    document = make_document(
        tenant_id=tenant.id,
        source_path="uploads/redis-investigation.md",
        title="Redis Investigation",
        ingestion_status="pending",
    )

    session = Mock()
    session.scalars.return_value = [document]

    redis_client = Mock()
    redis_client.mget.side_effect = RedisConnectionError("Redis unavailable")

    app.dependency_overrides[get_database_session] = lambda: session
    app.dependency_overrides[get_authorized_knowledge_access] = lambda: AuthorizedTenant(
        tenant=tenant,
        role="engineer",
    )
    app.dependency_overrides[get_redis_cache] = lambda: redis_client

    try:
        response = client.get("/api/v1/documents")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["documents"][0]["processing_progress"] is None
