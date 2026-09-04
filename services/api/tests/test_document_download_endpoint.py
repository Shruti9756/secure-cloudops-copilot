from unittest.mock import Mock
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.models import KnowledgeDocument, Tenant
from app.infrastructure.s3 import S3DocumentReference
from app.main import (
    app,
    get_authorized_knowledge_access,
    get_current_principal,
    get_database_session,
)
from app.services.authorization import (
    AuthenticatedPrincipal,
    AuthorizedTenant,
)
from app.services.document_storage import get_redacted_document_store

client = TestClient(app)


class FakeRedactedDocumentStore:
    """Return a synthetic URL without contacting AWS."""

    def __init__(self) -> None:
        self.calls: list[tuple[S3DocumentReference, int]] = []

    def create_presigned_download_url(
        self,
        *,
        reference: S3DocumentReference,
        expires_in_seconds: int,
    ) -> str:
        self.calls.append((reference, expires_in_seconds))
        return "https://example.test/redacted-document?signature=test"


def make_tenant() -> Tenant:
    return Tenant(
        id=uuid4(),
        organization_id=uuid4(),
        slug="nimbuscart",
        name="NimbusCart",
    )


def make_document(tenant: Tenant) -> KnowledgeDocument:
    return KnowledgeDocument(
        id=uuid4(),
        tenant_id=tenant.id,
        organization_id=tenant.organization_id,
        title="Redis Investigation",
        source_path="uploads/redis-investigation.md",
        source_sha256="a" * 64,
        content="Redacted document content is not returned by this endpoint.",
        ingestion_status="embedded",
        access_level="organization",
        document_metadata={
            "redacted_text_storage": {
                "provider": "s3",
                "bucket_name": "secure-cloudops-test",
                "object_key": (
                    "tenants/nimbuscart/redacted-documents/uploads/redis-investigation.md.txt"
                ),
                "version_id": "test-version-1",
                "e_tag": '"test-etag"',
            }
        },
    )


def install_dependencies(
    *,
    session: Mock,
    tenant: Tenant,
    document_store: FakeRedactedDocumentStore | None,
) -> None:
    app.dependency_overrides[get_database_session] = lambda: session
    app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal(
        user_id=uuid4(),
        identity_subject="local-demo-admin",
        display_name="Local Demo Administrator",
    )
    app.dependency_overrides[get_authorized_knowledge_access] = lambda: AuthorizedTenant(
        tenant=tenant,
        role="engineer",
    )
    app.dependency_overrides[get_redacted_document_store] = lambda: document_store


def test_document_download_url_requires_authorized_scoped_s3_reference() -> None:
    tenant = make_tenant()
    document = make_document(tenant)
    session = Mock()
    session.scalar.return_value = document
    document_store = FakeRedactedDocumentStore()
    install_dependencies(
        session=session,
        tenant=tenant,
        document_store=document_store,
    )

    try:
        response = client.get(
            "/api/v1/documents/download",
            params={"source_path": document.source_path},
        )
    finally:
        app.dependency_overrides.clear()

    audit_event = session.add.call_args.args[0]
    statement_sql = str(session.scalar.call_args.args[0])

    assert response.status_code == 200
    assert response.headers["x-request-id"]
    assert response.json() == {
        "source_path": "uploads/redis-investigation.md",
        "download_url": "https://example.test/redacted-document?signature=test",
        "expires_in_seconds": 300,
    }
    assert document_store.calls == [
        (
            S3DocumentReference(
                bucket_name="secure-cloudops-test",
                object_key=(
                    "tenants/nimbuscart/redacted-documents/uploads/redis-investigation.md.txt"
                ),
                version_id="test-version-1",
                e_tag='"test-etag"',
            ),
            300,
        )
    ]
    assert "knowledge_documents.organization_id" in statement_sql
    assert "knowledge_documents.access_level" in statement_sql
    assert audit_event.event_type == "document.download_url_issued"
    assert audit_event.outcome == "succeeded"
    assert audit_event.tenant_id == tenant.id
    assert audit_event.organization_id == tenant.organization_id
    assert audit_event.event_metadata == {
        "download_status": "issued",
        "source_path": "uploads/redis-investigation.md",
        "expires_in_seconds": 300,
    }
    assert "signature=test" not in str(audit_event.event_metadata)
    session.commit.assert_called_once()


def test_document_download_url_fails_closed_without_a_redacted_s3_reference() -> None:
    tenant = make_tenant()
    document = make_document(tenant)
    document.document_metadata = {}
    session = Mock()
    session.scalar.return_value = document
    document_store = FakeRedactedDocumentStore()
    install_dependencies(
        session=session,
        tenant=tenant,
        document_store=document_store,
    )

    try:
        response = client.get(
            "/api/v1/documents/download",
            params={"source_path": document.source_path},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Requested document is not available."}
    assert document_store.calls == []
    session.add.assert_not_called()
    session.commit.assert_not_called()
