from unittest.mock import Mock
from uuid import uuid4

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.services.document_lock import (
    DOCUMENT_LOCK_TTL_SECONDS,
    RELEASE_DOCUMENT_LOCK_LUA,
    RENEW_DOCUMENT_LOCK_LUA,
    DocumentLockLease,
    DocumentLockUnavailable,
    acquire_document_lock,
    build_document_lock_key,
    release_document_lock,
    renew_document_lock,
)


def test_build_document_lock_key_contains_the_document_id() -> None:
    document_id = uuid4()

    key = build_document_lock_key(document_id)

    assert str(document_id) in key
    assert key.startswith("securecloudops:document-lock:v1:")


def test_acquire_document_lock_uses_unique_token_and_ttl() -> None:
    redis_client = Mock()
    redis_client.set.return_value = True
    document_id = uuid4()

    lease = acquire_document_lock(
        redis_client,
        document_id=document_id,
        ttl_seconds=45,
    )

    assert lease is not None
    assert lease.key == build_document_lock_key(document_id)
    assert lease.owner_token
    assert lease.ttl_seconds == 45
    redis_client.set.assert_called_once_with(
        lease.key,
        lease.owner_token,
        ex=45,
        nx=True,
    )


def test_acquire_document_lock_returns_none_when_another_worker_owns_it() -> None:
    redis_client = Mock()
    redis_client.set.return_value = None

    lease = acquire_document_lock(
        redis_client,
        document_id=uuid4(),
    )

    assert lease is None


def test_acquire_document_lock_rejects_invalid_ttl() -> None:
    redis_client = Mock()

    with pytest.raises(ValueError, match="positive integer"):
        acquire_document_lock(
            redis_client,
            document_id=uuid4(),
            ttl_seconds=0,
        )

    redis_client.set.assert_not_called()


def test_acquire_document_lock_reports_redis_unavailability() -> None:
    redis_client = Mock()
    redis_client.set.side_effect = RedisConnectionError("Redis is unavailable")

    with pytest.raises(DocumentLockUnavailable):
        acquire_document_lock(
            redis_client,
            document_id=uuid4(),
        )


def test_renew_document_lock_succeeds_for_the_owner() -> None:
    redis_client = Mock()
    redis_client.eval.return_value = 1
    lease = DocumentLockLease(
        key="document-lock",
        owner_token="owner-token",
        ttl_seconds=120,
    )

    assert renew_document_lock(redis_client, lease) is True
    redis_client.eval.assert_called_once_with(
        RENEW_DOCUMENT_LOCK_LUA,
        1,
        "document-lock",
        "owner-token",
        "120",
    )


def test_renew_document_lock_fails_when_ownership_was_lost() -> None:
    redis_client = Mock()
    redis_client.eval.return_value = 0
    lease = DocumentLockLease(
        key="document-lock",
        owner_token="owner-token",
        ttl_seconds=DOCUMENT_LOCK_TTL_SECONDS,
    )

    assert renew_document_lock(redis_client, lease) is False


def test_release_document_lock_deletes_only_for_the_owner() -> None:
    redis_client = Mock()
    redis_client.eval.return_value = 1
    lease = DocumentLockLease(
        key="document-lock",
        owner_token="owner-token",
        ttl_seconds=DOCUMENT_LOCK_TTL_SECONDS,
    )

    assert release_document_lock(redis_client, lease) is True
    redis_client.eval.assert_called_once_with(
        RELEASE_DOCUMENT_LOCK_LUA,
        1,
        "document-lock",
        "owner-token",
    )
    redis_client.delete.assert_not_called()


def test_release_document_lock_does_not_delete_another_workers_lock() -> None:
    redis_client = Mock()
    redis_client.eval.return_value = 0
    lease = DocumentLockLease(
        key="document-lock",
        owner_token="stale-owner-token",
        ttl_seconds=DOCUMENT_LOCK_TTL_SECONDS,
    )

    assert release_document_lock(redis_client, lease) is False
    redis_client.delete.assert_not_called()
