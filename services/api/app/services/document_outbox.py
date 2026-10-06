"""Record document-processing intent in the current database transaction."""

from sqlalchemy.orm import Session

from app.db.models import DocumentQueueOutbox, KnowledgeDocument


def record_document_processing_intent(
    session: Session,
    document: KnowledgeDocument,
) -> DocumentQueueOutbox:
    if document.id is None:
        raise ValueError("Document ID must be assigned before recording processing intent")

    event = DocumentQueueOutbox(
        organization_id=document.organization_id,
        tenant_id=document.tenant_id,
        document_id=document.id,
    )
    session.add(event)
    return event
