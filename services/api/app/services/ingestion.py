from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import KnowledgeDocument, Tenant
from app.services.redaction import RedactionResult, redact_secrets

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


def _document_metadata_for(redaction_result: RedactionResult) -> dict[str, object]:
    """Build safe ingestion metadata without preserving any original secret values."""
    return {
        "content_type": "text/markdown",
        "ingestion_source": "local-demo-data",
        "redaction": {
            "applied": redaction_result.redaction_count > 0,
            "count": redaction_result.redaction_count,
            "types": list(redaction_result.redaction_types),
        },
    }


def get_or_create_tenant(session: Session, slug: str, name: str) -> Tenant:
    tenant = session.scalar(select(Tenant).where(Tenant.slug == slug))

    if tenant is None:
        tenant = Tenant(slug=slug, name=name)
        session.add(tenant)
        session.flush()

    return tenant


def ingest_document(
    session: Session,
    tenant: Tenant,
    source_path: str,
    content: str,
) -> IngestionResult:
    # Redact before hashing, storing, chunking, embedding, or retrieving document content.
    redaction_result = redact_secrets(content)
    safe_content = redaction_result.content
    content_hash = calculate_content_sha256(safe_content)

    statement = select(KnowledgeDocument).where(
        KnowledgeDocument.tenant_id == tenant.id,
        KnowledgeDocument.source_path == source_path,
    )
    document = session.scalar(statement)

    if document is None:
        fallback_title = Path(source_path).stem.replace("-", " ").replace("_", " ").title()

        session.add(
            KnowledgeDocument(
                tenant_id=tenant.id,
                title=extract_markdown_title(safe_content, fallback_title),
                source_path=source_path,
                source_sha256=content_hash,
                content=safe_content,
                ingestion_status="pending",
                document_metadata=_document_metadata_for(redaction_result),
            )
        )

        return IngestionResult(action="created", source_path=source_path)

    if document.source_sha256 == content_hash:
        return IngestionResult(action="unchanged", source_path=source_path)

    fallback_title = Path(source_path).stem.replace("-", " ").replace("_", " ").title()
    document.title = extract_markdown_title(safe_content, fallback_title)
    document.source_sha256 = content_hash
    document.content = safe_content
    # Existing chunks describe older content and must not be retrieved after an update.
    document.chunks.clear()
    document.ingestion_status = "pending"
    document.document_metadata = _document_metadata_for(redaction_result)

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
