"""Content-free SQS wake-up messages; PostgreSQL remains authoritative."""

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import ClassVar, Protocol, Self
from uuid import UUID

from botocore.exceptions import BotoCoreError, ClientError

_EXPECTED_FIELDS = frozenset({"schema_version", "organization_id", "tenant_id", "document_id"})
_MAX_BODY_BYTES = 512


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Document queue message has duplicate fields")
        result[key] = value
    return result


def _canonical_uuid(value: object) -> UUID:
    if not isinstance(value, str):
        raise TypeError("Document queue IDs must be canonical UUID strings")
    try:
        parsed = UUID(value)
    except ValueError:
        raise ValueError("Document queue IDs must be canonical UUID strings") from None
    if str(parsed) != value:
        raise ValueError("Document queue IDs must be canonical UUID strings")
    return parsed


@dataclass(frozen=True, slots=True, kw_only=True)
class DocumentProcessingMessage:
    organization_id: UUID
    tenant_id: UUID
    document_id: UUID
    schema_version: ClassVar[int] = 1

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, UUID)
            for value in (self.organization_id, self.tenant_id, self.document_id)
        ):
            raise TypeError("Document queue IDs must be UUID values")

    def to_json(self) -> str:
        return json.dumps(
            {
                "schema_version": self.schema_version,
                "organization_id": str(self.organization_id),
                "tenant_id": str(self.tenant_id),
                "document_id": str(self.document_id),
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def from_json(cls, body: str) -> Self:
        if not isinstance(body, str) or len(body.encode()) > _MAX_BODY_BYTES:
            raise ValueError("Document queue message is invalid or too large")
        try:
            payload: object = json.loads(body, object_pairs_hook=_unique_object)
        except ValueError:
            raise ValueError("Document queue message is not valid JSON") from None
        if not isinstance(payload, dict) or set(payload) != _EXPECTED_FIELDS:
            raise ValueError("Document queue message fields are invalid")
        if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
            raise ValueError("Document queue schema version is unsupported")
        try:
            return cls(
                organization_id=_canonical_uuid(payload["organization_id"]),
                tenant_id=_canonical_uuid(payload["tenant_id"]),
                document_id=_canonical_uuid(payload["document_id"]),
            )
        except TypeError:
            raise ValueError("Document queue message fields are invalid") from None


class SqsSender(Protocol):
    def send_message(self, *, QueueUrl: str, MessageBody: str) -> Mapping[str, object]: ...


class DocumentQueueUnavailableError(RuntimeError):
    """The queue did not acknowledge a message without exposing AWS details."""


class SqsDocumentQueue:
    """Use an injected sender; constructing this class makes no AWS call."""

    def __init__(self, *, queue_url: str, sender: SqsSender) -> None:
        if not queue_url.strip():
            raise ValueError("SQS queue URL must not be empty")
        self._queue_url = queue_url.strip()
        self._sender = sender

    def enqueue(self, message: DocumentProcessingMessage) -> str:
        try:
            response = self._sender.send_message(
                QueueUrl=self._queue_url,
                MessageBody=message.to_json(),
            )
        except BotoCoreError, ClientError:
            raise DocumentQueueUnavailableError("Document queue is unavailable") from None
        message_id = response.get("MessageId")
        if not isinstance(message_id, str) or not message_id.strip():
            raise DocumentQueueUnavailableError("Document queue did not acknowledge the message")
        return message_id


@dataclass(frozen=True, slots=True)
class DocumentQueueDelivery:
    message: DocumentProcessingMessage
    receipt_handle: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.receipt_handle, str):
            raise TypeError("SQS receipt handle must be a string")
        if not self.receipt_handle.strip():
            raise ValueError("SQS receipt handle must not be empty")


class SqsReceiverClient(Protocol):
    def receive_message(
        self,
        *,
        QueueUrl: str,
        MaxNumberOfMessages: int,
        WaitTimeSeconds: int,
    ) -> Mapping[str, object]: ...

    def delete_message(
        self,
        *,
        QueueUrl: str,
        ReceiptHandle: str,
    ) -> Mapping[str, object]: ...


class SqsDocumentReceiver:
    """Receive one queue hint without deciding whether processing succeeded."""

    def __init__(self, *, queue_url: str, client: SqsReceiverClient) -> None:
        if not queue_url.strip():
            raise ValueError("SQS queue URL must not be empty")
        self._queue_url = queue_url.strip()
        self._client = client

    def receive_one(self) -> DocumentQueueDelivery | None:
        try:
            response = self._client.receive_message(
                QueueUrl=self._queue_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=10,
            )
        except BotoCoreError, ClientError:
            raise DocumentQueueUnavailableError("Document queue is unavailable") from None

        if not isinstance(response, Mapping):
            raise TypeError("SQS response must be a mapping")

        messages = response.get("Messages", [])
        if not isinstance(messages, list):
            raise TypeError("SQS messages must be a list")
        if len(messages) > 1:
            raise ValueError("SQS returned more than one message")
        if not messages:
            return None

        received = messages[0]
        if not isinstance(received, Mapping):
            raise TypeError("SQS message must be a mapping")

        body = received.get("Body")
        receipt_handle = received.get("ReceiptHandle")
        if not isinstance(body, str) or not isinstance(receipt_handle, str):
            raise TypeError("SQS message body and receipt handle must be strings")

        return DocumentQueueDelivery(
            message=DocumentProcessingMessage.from_json(body),
            receipt_handle=receipt_handle,
        )

    def ack(self, delivery: DocumentQueueDelivery) -> None:
        """Delete a delivery only when a future caller explicitly decides it is safe."""
        if not isinstance(delivery, DocumentQueueDelivery):
            raise TypeError("A received document delivery is required")
        try:
            self._client.delete_message(
                QueueUrl=self._queue_url,
                ReceiptHandle=delivery.receipt_handle,
            )
        except BotoCoreError, ClientError:
            raise DocumentQueueUnavailableError("Document queue is unavailable") from None
