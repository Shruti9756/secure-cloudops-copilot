"""Transactional workspace knowledge revisions for answer-cache invalidation."""

from uuid import UUID

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.db.models import Tenant


def increment_knowledge_revision(
    session: Session,
    *,
    organization_id: UUID,
    tenant_id: UUID,
) -> int:
    """Increment a workspace revision inside the caller's transaction."""
    statement = (
        update(Tenant)
        .where(
            Tenant.id == tenant_id,
            Tenant.organization_id == organization_id,
        )
        .values(
            knowledge_revision=Tenant.knowledge_revision + 1,
        )
        .returning(Tenant.knowledge_revision)
    )

    return session.execute(statement).scalar_one()
