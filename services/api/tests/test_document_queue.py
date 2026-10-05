"""Offline tests for the versioned document-processing queue hint."""

import json
from collections.abc import Mapping
from uuid import UUID

import pytest
from botocore.exceptions import ClientError

from app.services.document_queue import (
    DocumentProcessingMessage,
    DocumentQueueUnavailableError,
    SqsDocumentQueue,
)

ORGANIZATION_ID = UUID("00000000-0000-0000-0000-000000000001")
TENANT_ID = UUID("00000000-0000-0000-0000-000000000002")
DOCUMENT_ID = UUID("00000000-0000-0000-0000-000000000003")
MESSAGE = DocumentProcessingMessage(
    organization_id=ORGANIZATION_ID,
    tenant_id=TENANT_ID,
    document_id=DOCUMENT_ID,
)


class FakeSqsSender:
    def __init__(self, response: Mapping[str, object] | None = None) -> None:
        self.calls: list[dict[str, str]] = []
        self.response = {"MessageId": "fake-message-1"} if response is None else response

    def send_message(self, *, QueueUrl: str, MessageBody: str) -> Mapping[str, object]:
        self.calls.append({"QueueUrl": QueueUrl, "MessageBody": MessageBody})
        return self.response


class FailingSqsSender:
    def send_message(self, *, QueueUrl: str, MessageBody: str) -> Mapping[str, object]:
        raise ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "private account detail"}},
            "SendMessage",
        )


def test_message_round_trips_with_ids_only() -> None:
    body = MESSAGE.to_json()
    assert json.loads(body) == {
        "schema_version": 1,
        "organization_id": str(ORGANIZATION_ID),
        "tenant_id": str(TENANT_ID),
        "document_id": str(DOCUMENT_ID),
    }
    assert DocumentProcessingMessage.from_json(body) == MESSAGE


@pytest.mark.parametrize(
    "body",
    [
        "not json",
        "[]",
        "{}",
        json.dumps({**json.loads(MESSAGE.to_json()), "schema_version": 2}),
        json.dumps({**json.loads(MESSAGE.to_json()), "schema_version": True}),
        json.dumps({**json.loads(MESSAGE.to_json()), "document_id": "invalid"}),
        json.dumps({**json.loads(MESSAGE.to_json()), "document_id": 3}),
        json.dumps({**json.loads(MESSAGE.to_json()), "content": "must-not-travel"}),
        json.dumps(
            {
                key: value
                for key, value in json.loads(MESSAGE.to_json()).items()
                if key != "tenant_id"
            }
        ),
        " " * 513 + MESSAGE.to_json(),
        MESSAGE.to_json().replace(
            '"document_id":',
            f'"document_id":"{DOCUMENT_ID}","document_id":',
            1,
        ),
    ],
)
def test_rejects_invalid_or_unsafe_body(body: str) -> None:
    with pytest.raises(ValueError):
        DocumentProcessingMessage.from_json(body)


def test_rejects_non_uuid_constructor_values() -> None:
    with pytest.raises(TypeError, match="UUID values"):
        DocumentProcessingMessage(
            organization_id="not-a-uuid",
            tenant_id=TENANT_ID,
            document_id=DOCUMENT_ID,
        )


def test_sender_is_injected_and_sends_only_the_contract() -> None:
    sender = FakeSqsSender()
    queue = SqsDocumentQueue(queue_url=" https://sqs.example.test/queue ", sender=sender)
    assert sender.calls == []
    assert queue.enqueue(MESSAGE) == "fake-message-1"
    assert sender.calls == [
        {
            "QueueUrl": "https://sqs.example.test/queue",
            "MessageBody": MESSAGE.to_json(),
        }
    ]


def test_sender_rejects_empty_queue_url_and_missing_acknowledgment() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        SqsDocumentQueue(queue_url=" ", sender=FakeSqsSender())
    with pytest.raises(DocumentQueueUnavailableError, match="did not acknowledge"):
        SqsDocumentQueue(queue_url="test-queue", sender=FakeSqsSender({})).enqueue(MESSAGE)


def test_sender_hides_aws_failure_details() -> None:
    queue = SqsDocumentQueue(queue_url="test-queue", sender=FailingSqsSender())
    with pytest.raises(
        DocumentQueueUnavailableError,
        match="Document queue is unavailable",
    ) as error:
        queue.enqueue(MESSAGE)
    assert "private account detail" not in str(error.value)
