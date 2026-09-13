"""Redis lease helpers that prevent duplicate document processing."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid4

from redis.exceptions import RedisError

DOCUMENT_LOCK_KEY_VERSION = "v1"
DOCUMENT_LOCK_TTL_SECONDS = 120

RENEW_DOCUMENT_LOCK_LUA = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("EXPIRE", KEYS[1], ARGV[2])
end
return 0
"""

RELEASE_DOCUMENT_LOCK_LUA = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
end
return 0
"""


class DocumentLockClient(Protocol):
    """Small Redis interface required by the lock helper."""

    def set(
        self,
        name: str,
        value: str,
        *,
        ex: int,
        nx: bool,
    ) -> bool | None:
        """Create a lock only when the key does not already exist."""

    def eval(
        self,
        script: str,
        numkeys: int,
        *keys_and_args: str,
    ) -> object:
        """Run an ownership-checking Redis script atomically."""


class DocumentLockUnavailable(RuntimeError):
    """Raised when Redis cannot perform a lock operation."""


class DocumentLockLost(RuntimeError):
    """Raised when the worker no longer owns the document lock."""


@dataclass(frozen=True)
class DocumentLockLease:
    """The key and unique token owned by one worker."""

    key: str
    owner_token: str
    ttl_seconds: int


def build_document_lock_key(document_id: UUID | str) -> str:
    """Build a stable Redis key for one document."""
    document_identifier = str(document_id).strip()

    if not document_identifier:
        raise ValueError("Document ID must not be empty")

    return f"securecloudops:document-lock:{DOCUMENT_LOCK_KEY_VERSION}:{document_identifier}"


def acquire_document_lock(
    redis_client: DocumentLockClient,
    *,
    document_id: UUID | str,
    ttl_seconds: int = DOCUMENT_LOCK_TTL_SECONDS,
) -> DocumentLockLease | None:
    """Acquire a document lock, or return None when another worker owns it."""
    _require_positive_integer(ttl_seconds)

    key = build_document_lock_key(document_id)
    owner_token = uuid4().hex

    try:
        acquired = redis_client.set(
            key,
            owner_token,
            ex=ttl_seconds,
            nx=True,
        )
    except RedisError as error:
        raise DocumentLockUnavailable(
            "Redis is unavailable while acquiring a document lock"
        ) from error

    if not acquired:
        return None

    return DocumentLockLease(
        key=key,
        owner_token=owner_token,
        ttl_seconds=ttl_seconds,
    )


def renew_document_lock(
    redis_client: DocumentLockClient,
    lease: DocumentLockLease,
) -> bool:
    """Extend the TTL only when this worker still owns the lock."""
    result = _run_owner_script(
        redis_client,
        script=RENEW_DOCUMENT_LOCK_LUA,
        lease=lease,
        operation="renewing",
        extra_argument=str(lease.ttl_seconds),
    )
    return _script_succeeded(result)


def release_document_lock(
    redis_client: DocumentLockClient,
    lease: DocumentLockLease,
) -> bool:
    """Delete the lock only when this worker still owns it."""
    result = _run_owner_script(
        redis_client,
        script=RELEASE_DOCUMENT_LOCK_LUA,
        lease=lease,
        operation="releasing",
    )
    return _script_succeeded(result)


def _run_owner_script(
    redis_client: DocumentLockClient,
    *,
    script: str,
    lease: DocumentLockLease,
    operation: str,
    extra_argument: str | None = None,
) -> object:
    arguments = [lease.key, lease.owner_token]

    if extra_argument is not None:
        arguments.append(extra_argument)

    try:
        return redis_client.eval(script, 1, *arguments)
    except RedisError as error:
        raise DocumentLockUnavailable(
            f"Redis is unavailable while {operation} a document lock"
        ) from error


def _script_succeeded(result: object) -> bool:
    """Interpret Redis integer replies without treating the string '0' as true."""
    return result in (1, True, "1", b"1")


def _require_positive_integer(value: int) -> None:
    """Reject invalid TTL configuration before contacting Redis."""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("Document lock TTL must be a positive integer")
