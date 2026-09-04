"""Safe, structured creation of append-only application audit events."""

from collections.abc import Mapping
from typing import Literal

from sqlalchemy.orm import Session

from app.db.models import AuditEvent, Tenant

type AuditOutcome = Literal["succeeded", "denied", "failed"]
type AuditMetadataValue = str | int | float | bool | None

# Audit records describe an event; they must not become a second copy of sensitive AI data.
FORBIDDEN_AUDIT_METADATA_KEYS = frozenset(
    {
        "answer",
        "content",
        "credentials",
        "prompt",
        "question",
        "secret",
        "token",
    }
)


def record_audit_event(
    session: Session,
    *,
    tenant: Tenant | None,
    event_type: str,
    outcome: AuditOutcome,
    actor_type: str,
    actor_id: str | None,
    request_id: str | None,
    metadata: Mapping[str, AuditMetadataValue],
) -> AuditEvent:
    """Add one safe audit event to the current database transaction."""
    if not event_type.strip():
        raise ValueError("Audit event type must not be empty")

    if not actor_type.strip():
        raise ValueError("Audit actor type must not be empty")

    _validate_audit_metadata(metadata)

    event = AuditEvent(
        tenant_id=tenant.id if tenant is not None else None,
        organization_id=tenant.organization_id if tenant is not None else None,
        event_type=event_type,
        outcome=outcome,
        actor_type=actor_type,
        actor_id=actor_id,
        request_id=request_id,
        # Make a copy so later caller-side mutation cannot alter the event.
        event_metadata=dict(metadata),
    )
    session.add(event)

    # The caller commits its surrounding transaction after the request is complete.
    return event


def _validate_audit_metadata(metadata: Mapping[str, AuditMetadataValue]) -> None:
    """Keep audit metadata scalar, structured, and free of raw AI content fields."""
    for key, value in metadata.items():
        if not isinstance(key, str):
            raise TypeError("Audit metadata keys must be strings")

        if key.lower() in FORBIDDEN_AUDIT_METADATA_KEYS:
            raise ValueError(f"Audit metadata must not include '{key}'")

        if value is not None and not isinstance(value, str | int | float | bool):
            raise TypeError("Audit metadata values must be JSON scalar values")
