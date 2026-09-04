from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.db.models import AuditEvent, Tenant
from app.services.audit import record_audit_event


def make_tenant() -> Tenant:
    """Build an in-memory tenant without needing a live database."""
    return Tenant(
        id=uuid4(),
        organization_id=uuid4(),
        slug="nimbuscart",
        name="NimbusCart",
    )


def test_record_audit_event_adds_safe_structured_metadata() -> None:
    session = Mock()
    tenant = make_tenant()
    metadata = {
        "cache_status": "MISS",
        "response_status": "grounded",
        "safety_validation_passed": True,
        "source_count": 2,
    }

    event = record_audit_event(
        session,
        tenant=tenant,
        event_type="rag.answer_requested",
        outcome="succeeded",
        actor_type="local_demo",
        actor_id="local-browser",
        request_id="request-123",
        metadata=metadata,
    )

    metadata["cache_status"] = "changed-after-recording"

    assert isinstance(event, AuditEvent)
    assert event.tenant_id == tenant.id
    assert event.organization_id == tenant.organization_id
    assert event.event_type == "rag.answer_requested"
    assert event.outcome == "succeeded"
    assert event.actor_type == "local_demo"
    assert event.actor_id == "local-browser"
    assert event.request_id == "request-123"
    assert event.event_metadata == {
        "cache_status": "MISS",
        "response_status": "grounded",
        "safety_validation_passed": True,
        "source_count": 2,
    }
    session.add.assert_called_once_with(event)


@pytest.mark.parametrize(
    "forbidden_key",
    [
        "question",
        "answer",
        "content",
        "prompt",
    ],
)
def test_record_audit_event_rejects_raw_ai_content_fields(
    forbidden_key: str,
) -> None:
    session = Mock()

    with pytest.raises(ValueError, match=f"must not include '{forbidden_key}'"):
        record_audit_event(
            session,
            tenant=make_tenant(),
            event_type="rag.answer_requested",
            outcome="succeeded",
            actor_type="local_demo",
            actor_id=None,
            request_id=None,
            metadata={forbidden_key: "sensitive text"},
        )

    session.add.assert_not_called()


def test_record_audit_event_rejects_non_scalar_metadata_values() -> None:
    session = Mock()

    with pytest.raises(TypeError, match="JSON scalar values"):
        record_audit_event(
            session,
            tenant=make_tenant(),
            event_type="rag.answer_requested",
            outcome="succeeded",
            actor_type="local_demo",
            actor_id=None,
            request_id=None,
            metadata={"source_identifiers": ["runbooks/checkout-latency.md#chunk-1"]},
        )

    session.add.assert_not_called()


def test_record_audit_event_allows_events_before_organization_scope_is_known() -> None:
    """Authentication failures can be recorded before a workspace is resolved."""
    session = Mock()

    event = record_audit_event(
        session,
        tenant=None,
        event_type="identity.authentication_failed",
        outcome="denied",
        actor_type="anonymous",
        actor_id=None,
        request_id="request-unauthenticated",
        metadata={"audit_status": "invalid_credentials"},
    )

    assert event.tenant_id is None
    assert event.organization_id is None
    session.add.assert_called_once_with(event)
