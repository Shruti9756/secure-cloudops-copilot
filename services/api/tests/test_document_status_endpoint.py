from unittest.mock import Mock
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.models import KnowledgeDocument, Tenant
from app.main import (
    app,
    get_authorized_knowledge_access,
    get_database_session,
)
from app.services.authorization import AuthorizedTenant

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
        # This deliberately sensitive-looking content must never reach the API response.
        content="Internal document content must not be exposed by the status endpoint.",
        ingestion_status=ingestion_status,
    )


def test_list_document_statuses_returns_safe_tenant_scoped_lifecycle_data() -> None:
    tenant = Tenant(
        id=uuid4(),
        organization_id=uuid4(),
        slug="nimbuscart",
        name="NimbusCart",
    )
    session = Mock()
    session.scalars.return_value = [
        make_document(
            tenant_id=tenant.id,
            source_path="uploads/redis-investigation.md",
            title="Redis Investigation",
            ingestion_status="pending",
        ),
        make_document(
            tenant_id=tenant.id,
            source_path="runbooks/checkout-latency.md",
            title="Checkout Latency Investigation",
            ingestion_status="embedded",
        ),
    ]
    app.dependency_overrides[get_database_session] = lambda: session
    app.dependency_overrides[get_authorized_knowledge_access] = lambda: AuthorizedTenant(
        tenant=tenant,
        role="engineer",
    )

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
            },
            {
                "source_path": "runbooks/checkout-latency.md",
                "title": "Checkout Latency Investigation",
                "ingestion_status": "embedded",
            },
        ],
    }
    assert "Internal document content" not in response.text

    # The route uses the tenant returned by authorization, not client-supplied scope.
    statement_sql = str(session.scalars.call_args.args[0])
    assert "knowledge_documents.access_level" in statement_sql
    assert "knowledge_documents.organization_id" in statement_sql
    assert "JOIN tenants" not in statement_sql
    session.commit.assert_not_called()
