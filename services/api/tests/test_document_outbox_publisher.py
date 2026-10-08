"""Offline settings, AWS-construction, and publisher-runner tests."""

import os
from unittest.mock import Mock, call, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app import document_outbox_publisher as publisher
from app.core import config as core_config
from app.core.config import DocumentOutboxPublisherSettings
from app.db import session as database_session
from app.infrastructure import postgres
from app.infrastructure.sqs import build_sqs_document_queue
from app.services.document_queue import (
    DocumentProcessingMessage,
    DocumentQueueUnavailableError,
)

FAKE_QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/000000000000/synthetic-test"


def make_settings(**overrides: object) -> DocumentOutboxPublisherSettings:
    values = {
        "database_url": "postgresql+psycopg://local:localpass@localhost/localdb",
    }
    values.update(overrides)
    with patch.dict(os.environ, {}, clear=True):
        return DocumentOutboxPublisherSettings(_env_file=None, **values)


@pytest.fixture
def main_dependencies(monkeypatch: pytest.MonkeyPatch) -> Mock:
    settings = make_settings(
        document_queue_backend="sqs",
        document_queue_sqs_url=FAKE_QUEUE_URL,
        document_outbox_poll_interval_seconds=7,
    )
    dependencies = Mock()
    dependencies.load_settings.return_value = settings
    dependencies.resolve_database_url.return_value = postgres.resolve_database_url(settings)

    for target, replacement in (
        ("get_document_outbox_publisher_settings", dependencies.load_settings),
        ("resolve_database_url", dependencies.resolve_database_url),
        ("create_engine", dependencies.create_engine),
        ("sessionmaker", dependencies.sessionmaker),
        ("build_sqs_document_queue", dependencies.build_sqs_document_queue),
        ("run_publisher", dependencies.run_publisher),
    ):
        monkeypatch.setattr(publisher, target, replacement)

    for module, name in (
        (core_config, "get_settings"),
        (database_session, "get_session_factory"),
        (postgres, "get_engine"),
        (postgres, "get_settings"),
        (database_session, "get_engine"),
    ):
        monkeypatch.setattr(
            module,
            name,
            Mock(side_effect=AssertionError(f"Unexpected global dependency: {name}")),
        )

    for name in ("get_settings", "get_session_factory", "get_engine"):
        monkeypatch.setattr(
            publisher,
            name,
            Mock(side_effect=AssertionError(f"Unexpected publisher dependency: {name}")),
            raising=False,
        )

    return dependencies


def expected_enabled_calls(dependencies: Mock) -> list[object]:
    settings = dependencies.load_settings.return_value
    engine = dependencies.create_engine.return_value
    return [
        call.load_settings(),
        call.resolve_database_url(settings),
        call.create_engine(
            dependencies.resolve_database_url.return_value,
            pool_pre_ping=True,
        ),
        call.sessionmaker(
            bind=engine,
            autoflush=False,
            expire_on_commit=False,
        ),
        call.build_sqs_document_queue(settings),
        call.run_publisher(
            session_factory=dependencies.sessionmaker.return_value,
            queue=dependencies.build_sqs_document_queue.return_value,
            poll_interval_seconds=7,
        ),
        call.create_engine().dispose(),
    ]


def test_queue_publishing_defaults_to_disabled() -> None:
    settings = make_settings()
    assert settings.document_queue_backend == "disabled"
    assert settings.document_queue_sqs_url is None
    assert settings.document_outbox_poll_interval_seconds == 5


@pytest.mark.parametrize("queue_url", [None, "", "   "])
def test_sqs_mode_requires_a_nonblank_queue_url(queue_url: str | None) -> None:
    with pytest.raises(ValidationError, match="DOCUMENT_QUEUE_SQS_URL"):
        make_settings(document_queue_backend="sqs", document_queue_sqs_url=queue_url)


@pytest.mark.parametrize("interval", [0, 301])
def test_publisher_interval_has_bounds(interval: int) -> None:
    with pytest.raises(ValidationError):
        make_settings(document_outbox_poll_interval_seconds=interval)


def test_disabled_builder_does_not_construct_an_aws_session() -> None:
    settings = make_settings()
    with (
        patch("app.infrastructure.sqs.boto3.Session") as create_session,
        pytest.raises(ValueError, match="disabled"),
    ):
        build_sqs_document_queue(settings)
    create_session.assert_not_called()


@pytest.mark.parametrize("profile", ["securecloudops-dev", None])
def test_builder_uses_profile_or_role_and_sends_only_ids(profile: str | None) -> None:
    settings = make_settings(
        document_queue_backend="sqs",
        document_queue_sqs_url=f"  {FAKE_QUEUE_URL}  ",
        aws_profile=profile,
    )
    message = DocumentProcessingMessage(
        organization_id=uuid4(),
        tenant_id=uuid4(),
        document_id=uuid4(),
    )

    with patch("app.infrastructure.sqs.boto3.Session") as create_session:
        aws_session = create_session.return_value
        sender = aws_session.client.return_value
        sender.send_message.return_value = {"MessageId": "synthetic-message"}

        queue = build_sqs_document_queue(settings)
        assert queue.enqueue(message) == "synthetic-message"

    create_session.assert_called_once_with(profile_name=profile, region_name="us-east-1")
    aws_session.client.assert_called_once()
    assert aws_session.client.call_args.args == ("sqs",)
    configuration = aws_session.client.call_args.kwargs["config"]
    assert configuration.connect_timeout == 5
    assert configuration.read_timeout == 15
    assert configuration.retries == {"mode": "standard", "total_max_attempts": 2}
    sender.send_message.assert_called_once_with(
        QueueUrl=FAKE_QUEUE_URL,
        MessageBody=message.to_json(),
    )


@pytest.mark.parametrize("published", [True, False])
def test_runner_waits_after_success_or_an_empty_outbox(published: bool) -> None:
    factory = Mock()
    queue = Mock()
    sleeper = Mock(side_effect=KeyboardInterrupt)

    with (
        patch.object(publisher, "publish_one_document_intent", return_value=published) as send,
        pytest.raises(KeyboardInterrupt),
    ):
        publisher.run_publisher(
            session_factory=factory,
            queue=queue,
            poll_interval_seconds=5,
            sleep=sleeper,
        )

    send.assert_called_once_with(session_factory=factory, queue=queue)
    sleeper.assert_called_once_with(5)


@pytest.mark.parametrize(
    "error",
    [
        DocumentQueueUnavailableError("synthetic-private-detail"),
        SQLAlchemyError("synthetic-private-detail"),
    ],
)
def test_runner_waits_then_retries_without_logging_error_details(error: Exception) -> None:
    factory = Mock()
    queue = Mock()
    sleeper = Mock(side_effect=[None, KeyboardInterrupt])

    with (
        patch.object(publisher, "publish_one_document_intent", side_effect=[error, False]) as send,
        patch.object(publisher.LOGGER, "warning") as warning,
        pytest.raises(KeyboardInterrupt),
    ):
        publisher.run_publisher(
            session_factory=factory,
            queue=queue,
            poll_interval_seconds=5,
            sleep=sleeper,
        )

    assert send.call_count == 2
    assert sleeper.call_count == 2
    warning.assert_called_once_with(
        "Document outbox publication was not confirmed; retrying later."
    )
    assert "synthetic-private-detail" not in repr(warning.call_args)


def test_unexpected_runner_errors_are_not_swallowed() -> None:
    sleeper = Mock()
    with (
        patch.object(
            publisher,
            "publish_one_document_intent",
            side_effect=RuntimeError("synthetic-programming-error"),
        ),
        pytest.raises(RuntimeError, match="synthetic-programming-error"),
    ):
        publisher.run_publisher(
            session_factory=Mock(),
            queue=Mock(),
            poll_interval_seconds=5,
            sleep=sleeper,
        )
    sleeper.assert_not_called()


def test_disabled_main_constructs_neither_queue_nor_database_factory(
    main_dependencies: Mock,
) -> None:
    main_dependencies.load_settings.return_value = make_settings(database_url=None)

    publisher.main()

    assert main_dependencies.mock_calls == [call.load_settings()]
    main_dependencies.resolve_database_url.assert_not_called()
    main_dependencies.create_engine.assert_not_called()
    main_dependencies.sessionmaker.assert_not_called()
    main_dependencies.build_sqs_document_queue.assert_not_called()
    main_dependencies.run_publisher.assert_not_called()


def test_enabled_main_wires_dependencies_and_handles_keyboard_interrupt(
    main_dependencies: Mock,
) -> None:
    main_dependencies.run_publisher.side_effect = KeyboardInterrupt

    publisher.main()

    assert main_dependencies.mock_calls == expected_enabled_calls(main_dependencies)
    main_dependencies.create_engine.return_value.dispose.assert_called_once_with()


def test_enabled_main_disposes_local_engine_after_normal_return(
    main_dependencies: Mock,
) -> None:
    publisher.main()

    assert main_dependencies.mock_calls == expected_enabled_calls(main_dependencies)
    main_dependencies.create_engine.return_value.dispose.assert_called_once_with()


@pytest.mark.parametrize(
    ("failing_dependency", "expected_call_count"),
    [
        ("sessionmaker", 4),
        ("build_sqs_document_queue", 5),
        ("run_publisher", 6),
    ],
)
def test_enabled_main_disposes_engine_and_propagates_unexpected_failures(
    main_dependencies: Mock,
    failing_dependency: str,
    expected_call_count: int,
) -> None:
    getattr(main_dependencies, failing_dependency).side_effect = RuntimeError(
        "synthetic-programming-error"
    )

    with pytest.raises(RuntimeError, match="synthetic-programming-error"):
        publisher.main()

    expected = expected_enabled_calls(main_dependencies)
    assert main_dependencies.mock_calls == (
        expected[:expected_call_count] + [call.create_engine().dispose()]
    )
    main_dependencies.create_engine.return_value.dispose.assert_called_once_with()
