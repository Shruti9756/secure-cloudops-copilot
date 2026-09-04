"""add audit event organization scope

Revision ID: d09c9a1ccb00
Revises: 4b72b2345427
Create Date: 2026-09-01 00:16:21.459795
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d09c9a1ccb00"
down_revision: str | Sequence[str] | None = "4b72b2345427"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Backfill known audit-event organization ownership safely."""
    op.add_column(
        "audit_events",
        sa.Column("organization_id", sa.Uuid(), nullable=True),
    )

    # Only events with a known tenant can be assigned a trusted organization.
    # Events such as failed authentication may correctly remain unscoped.
    op.execute(
        sa.text(
            """
            UPDATE audit_events AS event
            SET organization_id = tenant.organization_id
            FROM tenants AS tenant
            WHERE event.tenant_id = tenant.id
              AND event.organization_id IS NULL
            """
        )
    )

    connection = op.get_bind()
    missing_scoped_organization_count = connection.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM audit_events
            WHERE tenant_id IS NOT NULL
              AND organization_id IS NULL
            """
        )
    ).scalar_one()

    if missing_scoped_organization_count != 0:
        raise RuntimeError(
            "Migration stopped because one or more tenant-scoped audit events "
            "could not be assigned to an organization safely."
        )

    op.create_index(
        "ix_audit_events_organization_created_at",
        "audit_events",
        ["organization_id", "created_at"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_audit_events_organization_id_organizations",
        "audit_events",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Remove direct organization ownership from audit events."""
    op.drop_constraint(
        "fk_audit_events_organization_id_organizations",
        "audit_events",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_audit_events_organization_created_at",
        table_name="audit_events",
    )
    op.drop_column("audit_events", "organization_id")
