"""Explicit document-outbox publisher; not started by the local worker."""

import logging
import time
from collections.abc import Callable

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.infrastructure.sqs import build_sqs_document_queue
from app.services.document_outbox_dispatcher import publish_one_document_intent
from app.services.document_queue import DocumentQueueUnavailableError, SqsDocumentQueue

LOGGER = logging.getLogger(__name__)


def run_publisher(
    *,
    session_factory: sessionmaker[Session],
    queue: SqsDocumentQueue,
    poll_interval_seconds: int,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    while True:
        try:
            published = publish_one_document_intent(
                session_factory=session_factory,
                queue=queue,
            )
        except DocumentQueueUnavailableError, SQLAlchemyError:
            # Exception details can contain database values or AWS metadata.
            LOGGER.warning("Document outbox publication was not confirmed; retrying later.")
        else:
            if published:
                LOGGER.info("Document outbox publication committed.")

        # Wait after success, an empty outbox, or an expected dependency failure.
        sleep(poll_interval_seconds)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = get_settings()

    if settings.document_queue_backend == "disabled":
        LOGGER.info("Document outbox publisher is disabled.")
        return

    queue = build_sqs_document_queue(settings)
    session_factory = get_session_factory()

    try:
        run_publisher(
            session_factory=session_factory,
            queue=queue,
            poll_interval_seconds=settings.document_outbox_poll_interval_seconds,
        )
    except KeyboardInterrupt:
        LOGGER.info("Document outbox publisher stopped.")


if __name__ == "__main__":
    main()
