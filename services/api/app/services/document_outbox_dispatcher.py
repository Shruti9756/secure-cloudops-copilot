"""Publish one recorded document-processing intent through an injected queue."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import DocumentQueueOutbox
from app.services.document_queue import DocumentProcessingMessage, SqsDocumentQueue


def publish_one_document_intent(
    *,
    session_factory: sessionmaker[Session],
    queue: SqsDocumentQueue,
) -> bool:
    statement = (
        select(DocumentQueueOutbox)
        .where(DocumentQueueOutbox.published_at.is_(None))
        .order_by(
            DocumentQueueOutbox.created_at.asc(),
            DocumentQueueOutbox.id.asc(),
        )
        .limit(1)
        .with_for_update(of=DocumentQueueOutbox, skip_locked=True)
    )

    with session_factory.begin() as session:
        event = session.scalar(statement)
        if event is None:
            return False

        queue.enqueue(
            DocumentProcessingMessage(
                organization_id=event.organization_id,
                tenant_id=event.tenant_id,
                document_id=event.document_id,
            )
        )
        event.published_at = datetime.now(UTC)

    # Exiting the transaction successfully confirms its commit completed.
    return True
