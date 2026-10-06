"""Verify local outbox publication without AWS or existing document changes."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from app.db.base import Base
from app.db.models import DocumentQueueOutbox, KnowledgeDocument, Organization, Tenant
from app.infrastructure.postgres import get_engine
from app.services.document_outbox_dispatcher import publish_one_document_intent
from app.services.document_queue import (
    DocumentProcessingMessage,
    DocumentQueueUnavailableError,
    SqsDocumentQueue,
)

pytestmark = pytest.mark.e2e

FAKE_QUEUE_URL = "https://queue.invalid/outbox-test"


@pytest.fixture
def outbox_sessions() -> Iterator[sessionmaker[Session]]:
    url = get_engine().url
    assert url.get_backend_name() == "postgresql"
    assert url.host in {"127.0.0.1", "localhost"}, "This test requires local PostgreSQL."

    schema_name = f"test_outbox_publish_{uuid4().hex}"
    test_engine = create_engine(
        url,
        connect_args={"options": "-c statement_timeout=5000 -c lock_timeout=2000"},
    )
    isolated_engine = test_engine.execution_options(
        schema_translate_map={None: schema_name},
    )
    schema_created = False

    try:
        with isolated_engine.begin() as connection:
            connection.execute(CreateSchema(schema_name))
            Base.metadata.create_all(
                connection,
                tables=[
                    Organization.__table__,
                    Tenant.__table__,
                    KnowledgeDocument.__table__,
                    DocumentQueueOutbox.__table__,
                ],
            )
        schema_created = True

        yield sessionmaker(
            bind=isolated_engine,
            autoflush=False,
            expire_on_commit=False,
        )
    finally:
        try:
            if schema_created:
                with test_engine.begin() as connection:
                    connection.execute(DropSchema(schema_name, cascade=True))
        finally:
            test_engine.dispose()


def seed_events(
    factory: sessionmaker[Session],
    *,
    count: int,
) -> list[DocumentQueueOutbox]:
    organization_id = uuid4()
    tenant_id = uuid4()
    events: list[DocumentQueueOutbox] = []

    with factory.begin() as session:
        session.add(
            Organization(
                id=organization_id,
                slug="publisher-test-org",
                name="Synthetic Publisher Organization",
            )
        )
        session.flush()
        session.add(
            Tenant(
                id=tenant_id,
                organization_id=organization_id,
                slug="publisher-test-workspace",
                name="Synthetic Publisher Workspace",
            )
        )
        session.flush()

        for index in range(count):
            document = KnowledgeDocument(
                id=uuid4(),
                organization_id=organization_id,
                tenant_id=tenant_id,
                title=f"Synthetic Publisher Document {index}",
                source_path=f"uploads/publisher-test-{index}.md",
                source_sha256="a" * 64,
                content="# Local publisher test",
                ingestion_status="pending",
                access_level="organization",
            )
            session.add(document)
            session.flush()

            event = DocumentQueueOutbox(
                id=uuid4(),
                organization_id=organization_id,
                tenant_id=tenant_id,
                document_id=document.id,
                created_at=datetime(2026, 10, 6, tzinfo=UTC) + timedelta(seconds=index),
            )
            session.add(event)
            events.append(event)

    return events


def make_queue() -> tuple[SqsDocumentQueue, Mock]:
    sender = Mock()
    sender.send_message.return_value = {"MessageId": "synthetic-message"}
    queue = SqsDocumentQueue(queue_url=FAKE_QUEUE_URL, sender=sender)
    return queue, sender


def expected_body(event: DocumentQueueOutbox) -> str:
    return DocumentProcessingMessage(
        organization_id=event.organization_id,
        tenant_id=event.tenant_id,
        document_id=event.document_id,
    ).to_json()


def test_publication_commits_and_does_not_send_twice(
    outbox_sessions: sessionmaker[Session],
) -> None:
    event = seed_events(outbox_sessions, count=1)[0]
    queue, sender = make_queue()

    assert publish_one_document_intent(session_factory=outbox_sessions, queue=queue) is True
    sender.send_message.assert_called_once_with(
        QueueUrl=FAKE_QUEUE_URL,
        MessageBody=expected_body(event),
    )

    with outbox_sessions() as session:
        stored = session.get(DocumentQueueOutbox, event.id)
        assert stored is not None
        assert stored.published_at is not None
        assert stored.published_at.utcoffset() is not None

    assert publish_one_document_intent(session_factory=outbox_sessions, queue=queue) is False
    assert sender.send_message.call_count == 1


def test_unacknowledged_send_leaves_event_available_for_retry(
    outbox_sessions: sessionmaker[Session],
) -> None:
    event = seed_events(outbox_sessions, count=1)[0]
    queue, sender = make_queue()
    sender.send_message.return_value = {}

    with pytest.raises(DocumentQueueUnavailableError, match="did not acknowledge"):
        publish_one_document_intent(session_factory=outbox_sessions, queue=queue)

    with outbox_sessions() as session:
        stored = session.get(DocumentQueueOutbox, event.id)
        assert stored is not None
        assert stored.published_at is None

    sender.send_message.return_value = {"MessageId": "accepted-on-retry"}
    assert publish_one_document_intent(session_factory=outbox_sessions, queue=queue) is True
    assert sender.send_message.call_count == 2

    with outbox_sessions() as session:
        stored = session.get(DocumentQueueOutbox, event.id)
        assert stored is not None
        assert stored.published_at is not None


def test_publisher_skips_a_row_locked_by_another_transaction(
    outbox_sessions: sessionmaker[Session],
) -> None:
    oldest, newer = seed_events(outbox_sessions, count=2)
    queue, sender = make_queue()

    with outbox_sessions.begin() as locker:
        locked = locker.scalar(
            select(DocumentQueueOutbox).where(DocumentQueueOutbox.id == oldest.id).with_for_update()
        )
        assert locked is not None

        assert publish_one_document_intent(session_factory=outbox_sessions, queue=queue) is True
        sender.send_message.assert_called_once_with(
            QueueUrl=FAKE_QUEUE_URL,
            MessageBody=expected_body(newer),
        )

        with outbox_sessions() as reader:
            stored_oldest = reader.get(DocumentQueueOutbox, oldest.id)
            stored_newer = reader.get(DocumentQueueOutbox, newer.id)
            assert stored_oldest is not None
            assert stored_newer is not None
            assert stored_oldest.published_at is None
            assert stored_newer.published_at is not None

        assert publish_one_document_intent(session_factory=outbox_sessions, queue=queue) is False
        assert sender.send_message.call_count == 1

    assert publish_one_document_intent(session_factory=outbox_sessions, queue=queue) is True
    assert sender.send_message.call_count == 2
    sender.send_message.assert_called_with(
        QueueUrl=FAKE_QUEUE_URL,
        MessageBody=expected_body(oldest),
    )

    with outbox_sessions() as session:
        stored = session.get(DocumentQueueOutbox, oldest.id)
        assert stored is not None
        assert stored.published_at is not None
