"""Build opt-in SQS publisher and receiver; tests replace the AWS session."""

import boto3
from botocore.config import Config

from app.core.config import DocumentOutboxPublisherSettings, Settings
from app.services.document_queue import SqsDocumentQueue, SqsDocumentReceiver


def build_sqs_document_queue(
    settings: Settings | DocumentOutboxPublisherSettings,
) -> SqsDocumentQueue:
    if settings.document_queue_backend != "sqs":
        raise ValueError("SQS publishing is disabled.")

    queue_url = settings.document_queue_sqs_url
    if queue_url is None or not queue_url.strip():
        raise ValueError("Set DOCUMENT_QUEUE_SQS_URL before enabling SQS publishing.")

    aws_session = boto3.Session(
        profile_name=settings.aws_profile or None,
        region_name=settings.aws_region,
    )
    client = aws_session.client(
        "sqs",
        config=Config(
            connect_timeout=5,
            read_timeout=15,
            retries={"mode": "standard", "total_max_attempts": 2},
        ),
    )
    return SqsDocumentQueue(queue_url=queue_url.strip(), sender=client)


def build_sqs_document_receiver(settings: Settings) -> SqsDocumentReceiver:
    if settings.document_queue_backend != "sqs":
        raise ValueError("SQS receiving is disabled.")

    queue_url = settings.document_queue_sqs_url
    if queue_url is None or not queue_url.strip():
        raise ValueError("Set DOCUMENT_QUEUE_SQS_URL before enabling SQS receiving.")

    aws_session = boto3.Session(
        profile_name=settings.aws_profile or None,
        region_name=settings.aws_region,
    )
    client = aws_session.client(
        "sqs",
        config=Config(
            connect_timeout=5,
            read_timeout=15,
            retries={"mode": "standard", "total_max_attempts": 2},
        ),
    )
    return SqsDocumentReceiver(queue_url=queue_url.strip(), client=client)
