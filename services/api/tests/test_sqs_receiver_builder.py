"""Offline tests for opt-in SQS receiver construction."""

import os
from unittest.mock import patch

import pytest

from app.core.config import Settings
from app.infrastructure.sqs import build_sqs_document_receiver
from app.services.document_queue import SqsDocumentReceiver

FAKE_QUEUE_URL = "https://sqs.ap-south-1.amazonaws.com/000000000000/synthetic-test"


def make_settings(**overrides: object) -> Settings:
    values = {
        "database_url": "postgresql+psycopg://local:localpass@localhost/localdb",
        "redis_url": "redis://localhost:6379/0",
    }
    values.update(overrides)

    # Keep tests independent from the real .env and shell environment.
    with patch.dict(os.environ, {}, clear=True):
        return Settings(_env_file=None, **values)


def test_disabled_receiver_builder_does_not_construct_an_aws_session() -> None:
    settings = make_settings(aws_profile="synthetic-missing-profile")

    with (
        patch("app.infrastructure.sqs.boto3.Session") as create_session,
        pytest.raises(ValueError, match="disabled"),
    ):
        build_sqs_document_receiver(settings)

    create_session.assert_not_called()


@pytest.mark.parametrize("queue_url", [None, "", "   "])
def test_receiver_builder_rejects_missing_url_before_aws(
    queue_url: str | None,
) -> None:
    # Bypass Settings validation only to test the builder's own safety check.
    settings = make_settings().model_copy(
        update={
            "document_queue_backend": "sqs",
            "document_queue_sqs_url": queue_url,
        }
    )

    with (
        patch("app.infrastructure.sqs.boto3.Session") as create_session,
        pytest.raises(ValueError, match="DOCUMENT_QUEUE_SQS_URL"),
    ):
        build_sqs_document_receiver(settings)

    create_session.assert_not_called()


@pytest.mark.parametrize("profile", ["securecloudops-dev", None, ""])
def test_receiver_builder_uses_profile_or_role_without_auto_receiving(
    profile: str | None,
) -> None:
    settings = make_settings(
        document_queue_backend="sqs",
        document_queue_sqs_url=f"  {FAKE_QUEUE_URL}  ",
        aws_profile=profile,
        aws_region="ap-south-1",
    )

    with patch("app.infrastructure.sqs.boto3.Session") as create_session:
        aws_session = create_session.return_value
        client = aws_session.client.return_value
        client.receive_message.return_value = {}

        receiver = build_sqs_document_receiver(settings)

        assert isinstance(receiver, SqsDocumentReceiver)
        client.receive_message.assert_not_called()
        client.delete_message.assert_not_called()
        client.send_message.assert_not_called()

        # Receiving happens only when explicitly requested.
        assert receiver.receive_one() is None

    create_session.assert_called_once_with(
        profile_name=profile or None,
        region_name="ap-south-1",
    )
    aws_session.client.assert_called_once()
    assert aws_session.client.call_args.args == ("sqs",)
    assert set(aws_session.client.call_args.kwargs) == {"config"}

    configuration = aws_session.client.call_args.kwargs["config"]
    assert configuration.connect_timeout == 5
    assert configuration.read_timeout == 15
    assert configuration.read_timeout > 10
    assert configuration.retries == {
        "mode": "standard",
        "total_max_attempts": 2,
    }

    client.receive_message.assert_called_once_with(
        QueueUrl=FAKE_QUEUE_URL,
        MaxNumberOfMessages=1,
        WaitTimeSeconds=10,
    )
    client.delete_message.assert_not_called()
    client.send_message.assert_not_called()
