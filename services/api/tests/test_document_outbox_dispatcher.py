"""Offline tests for publishing recorded document-processing intent."""

from datetime import UTC
from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.db.models import DocumentQueueOutbox
from app.services.document_outbox_dispatcher import publish_one_document_intent
from app.services.document_queue import (
    DocumentProcessingMessage,
    DocumentQueueUnavailableError,
    SqsDocumentQueue,
)


def make_event() -> DocumentQueueOutbox:
    return DocumentQueueOutbox(
        id=uuid4(),
        organization_id=uuid4(),
        tenant_id=uuid4(),
        document_id=uuid4(),
        published_at=None,
    )


def make_environment(
    event: DocumentQueueOutbox | None,
) -> tuple[Mock, Mock, MagicMock, Mock]:
    session = Mock()
    session.scalar.return_value = event

    transaction = MagicMock()
    transaction.__enter__.return_value = session
    transaction.__exit__.return_value = False

    session_factory = Mock()
    session_factory.begin.return_value = transaction

    queue = Mock(spec=SqsDocumentQueue)
    queue.enqueue.return_value = "fake-message-1"

    return session_factory, session, transaction, queue


def test_empty_outbox_returns_false_and_claims_only_unpublished_rows() -> None:
    session_factory, session, _, queue = make_environment(None)

    assert (
        publish_one_document_intent(
            session_factory=session_factory,
            queue=queue,
        )
        is False
    )
    queue.enqueue.assert_not_called()

    statement = session.scalar.call_args.args[0]
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "document_queue_outbox.published_at IS NULL" in sql
    assert ("ORDER BY document_queue_outbox.created_at ASC, document_queue_outbox.id ASC") in sql
    assert "LIMIT 1" in sql
    assert "FOR UPDATE OF document_queue_outbox SKIP LOCKED" in sql


def test_publication_sends_ids_before_marking_the_event_published() -> None:
    event = make_event()
    session_factory, _, transaction, queue = make_environment(event)

    expected_message = DocumentProcessingMessage(
        organization_id=event.organization_id,
        tenant_id=event.tenant_id,
        document_id=event.document_id,
    )

    def acknowledge(message: DocumentProcessingMessage) -> str:
        assert message == expected_message
        assert event.published_at is None
        return "fake-message-1"

    def finish_transaction(exc_type, _exception, _traceback) -> bool:
        assert exc_type is None
        assert event.published_at is not None
        assert event.published_at.tzinfo is UTC
        return False

    queue.enqueue.side_effect = acknowledge
    transaction.__exit__.side_effect = finish_transaction

    assert (
        publish_one_document_intent(
            session_factory=session_factory,
            queue=queue,
        )
        is True
    )
    queue.enqueue.assert_called_once_with(expected_message)
    transaction.__exit__.assert_called_once()


def test_send_failure_does_not_mark_the_event_published() -> None:
    event = make_event()
    session_factory, _, transaction, queue = make_environment(event)
    queue.enqueue.side_effect = DocumentQueueUnavailableError("Document queue is unavailable")

    with pytest.raises(DocumentQueueUnavailableError):
        publish_one_document_intent(
            session_factory=session_factory,
            queue=queue,
        )

    assert event.published_at is None
    assert transaction.__exit__.call_args.args[0] is DocumentQueueUnavailableError


def test_commit_failure_after_sending_is_not_reported_as_success() -> None:
    event = make_event()
    session_factory, _, transaction, queue = make_environment(event)
    transaction.__exit__.side_effect = RuntimeError("Simulated commit failure")

    with pytest.raises(RuntimeError, match="Simulated commit failure"):
        publish_one_document_intent(
            session_factory=session_factory,
            queue=queue,
        )

    queue.enqueue.assert_called_once()
