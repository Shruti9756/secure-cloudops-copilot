from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import KnowledgeDocument, Organization, Tenant
from app.infrastructure.s3 import S3DocumentReference
from app.services.document_access import (
    ALL_DOCUMENT_ACCESS_LEVELS,
    ORGANIZATION_DOCUMENT_ACCESS,
    DocumentAccessLevel,
)
from app.services.document_storage import RedactedDocumentStore
from app.services.redaction import RedactionResult, redact_sensitive_content

IngestionAction = Literal["created", "updated", "unchanged"]


@dataclass(frozen=True)
class IngestionResult:
    action: IngestionAction
    source_path: str


def calculate_content_sha256(content: str) -> str:
    return sha256(content.encode("utf-8")).hexdigest()


def extract_markdown_title(content: str, fallback: str) -> str:
    for line in content.splitlines():
        stripped_line = line.strip()

        if stripped_line.startswith("# "):
            return stripped_line.removeprefix("# ").strip()

    return fallback


def _document_metadata_for(
    redaction_result: RedactionResult,
    *,
    ingestion_source: str,
    content_type: str,
    storage_reference: S3DocumentReference | None,
) -> dict[str, object]:
    """Build safe metadata without preserving raw secrets or raw source files."""
    metadata: dict[str, object] = {
        "content_type": content_type,
        "ingestion_source": ingestion_source,
        "redaction": {
            "applied": redaction_result.redaction_count > 0,
            "count": redaction_result.redaction_count,
            "types": list(redaction_result.redaction_types),
        },
    }

    if storage_reference is not None:
        # This identifies a redacted text copy, never the original binary upload.
        metadata["redacted_text_storage"] = {
            "provider": "s3",
            "bucket_name": storage_reference.bucket_name,
            "object_key": storage_reference.object_key,
            "version_id": storage_reference.version_id,
            "e_tag": storage_reference.e_tag,
        }

    return metadata


def get_or_create_organization(session: Session, slug: str, name: str) -> Organization:
    """Create the local demo organization once, or return its existing record."""
    organization = session.scalar(select(Organization).where(Organization.slug == slug))

    if organization is None:
        organization = Organization(slug=slug, name=name)
        session.add(organization)
        session.flush()

    return organization


def get_or_create_tenant(session: Session, slug: str, name: str) -> Tenant:
    """Create a tenant workspace that is always owned by an organization."""
    tenant = session.scalar(select(Tenant).where(Tenant.slug == slug))

    if tenant is None:
        # V0.2 keeps the V0.1 demo simple: NimbusCart owns its nimbuscart workspace.
        organization = get_or_create_organization(session, slug, name)
        tenant = Tenant(slug=slug, name=name, organization=organization)
        session.add(tenant)
        session.flush()

    return tenant


def ingest_document(
    session: Session,
    tenant: Tenant,
    source_path: str,
    content: str,
    access_level: DocumentAccessLevel | None = None,
    ingestion_source: str = "local-demo-data",
    content_type: str = "text/markdown",
    document_store: RedactedDocumentStore | None = None,
) -> IngestionResult:
    """Redact, optionally mirror, and persist one tenant-scoped knowledge document."""
    if access_level is not None and access_level not in ALL_DOCUMENT_ACCESS_LEVELS:
        raise ValueError("Document access level is not supported")
    # Redact before hashing, storing, chunking, embedding, or retrieving document content.
    redaction_result = redact_sensitive_content(content)
    safe_content = redaction_result.content
    content_hash = calculate_content_sha256(safe_content)

    statement = select(KnowledgeDocument).where(
        KnowledgeDocument.tenant_id == tenant.id,
        KnowledgeDocument.source_path == source_path,
    )
    document = session.scalar(statement)

    # Identical content normally needs no write or new S3 version. An explicit
    # visibility change is still a meaningful metadata update.
    if document is not None and document.source_sha256 == content_hash:
        if access_level is None or document.access_level == access_level:
            return IngestionResult(action="unchanged", source_path=source_path)

        document.access_level = access_level
        return IngestionResult(action="updated", source_path=source_path)

    storage_reference: S3DocumentReference | None = None

    if document_store is not None:
        # A configured mirror must succeed before database state is changed.
        storage_reference = document_store.store_redacted_document(
            tenant_slug=tenant.slug,
            source_path=source_path,
            redacted_content=safe_content,
            content_sha256=content_hash,
        )

    document_metadata = _document_metadata_for(
        redaction_result,
        ingestion_source=ingestion_source,
        content_type=content_type,
        storage_reference=storage_reference,
    )

    if document is None:
        fallback_title = Path(source_path).stem.replace("-", " ").replace("_", " ").title()
        resolved_access_level = access_level or ORGANIZATION_DOCUMENT_ACCESS
        session.add(
            KnowledgeDocument(
                tenant_id=tenant.id,
                organization_id=tenant.organization_id,
                title=extract_markdown_title(safe_content, fallback_title),
                source_path=source_path,
                source_sha256=content_hash,
                content=safe_content,
                ingestion_status="pending",
                access_level=resolved_access_level,
                document_metadata=document_metadata,
            )
        )

        return IngestionResult(action="created", source_path=source_path)

    fallback_title = Path(source_path).stem.replace("-", " ").replace("_", " ").title()
    if access_level is not None:
        document.access_level = access_level
    document.title = extract_markdown_title(safe_content, fallback_title)
    document.source_sha256 = content_hash
    document.content = safe_content
    # Existing chunks describe older content and must not be retrieved after an update.
    document.chunks.clear()
    document.ingestion_status = "pending"
    document.document_metadata = document_metadata

    return IngestionResult(action="updated", source_path=source_path)


def ingest_directory(
    session: Session,
    source_directory: Path,
    tenant_slug: str,
    tenant_name: str,
) -> list[IngestionResult]:
    if not source_directory.is_dir():
        raise ValueError(f"Source directory does not exist: {source_directory}")

    tenant = get_or_create_tenant(session, tenant_slug, tenant_name)
    results: list[IngestionResult] = []

    for file_path in sorted(source_directory.rglob("*.md")):
        content = file_path.read_text(encoding="utf-8")
        source_path = file_path.relative_to(source_directory).as_posix()

        results.append(
            ingest_document(
                session=session,
                tenant=tenant,
                source_path=source_path,
                content=content,
            )
        )

    return results
