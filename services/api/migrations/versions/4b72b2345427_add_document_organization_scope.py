"""add document organization scope

Revision ID: 4b72b2345427
Revises: 57caa654fcec
Create Date: 2026-08-31 23:32:42.220559
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4b72b2345427"
down_revision: str | Sequence[str] | None = "57caa654fcec"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Backfill direct organization ownership before enforcing it."""
    op.add_column(
        "knowledge_documents",
        sa.Column("organization_id", sa.Uuid(), nullable=True),
    )

    # Existing documents already belong to a tenant, and every tenant belongs
    # to exactly one organization. Copy that trusted relationship safely.
    op.execute(
        sa.text(
            """
            UPDATE knowledge_documents AS document
            SET organization_id = tenant.organization_id
            FROM tenants AS tenant
            WHERE document.tenant_id = tenant.id
              AND document.organization_id IS NULL
            """
        )
    )

    connection = op.get_bind()
    missing_organization_count = connection.execute(
        sa.text("SELECT COUNT(*) FROM knowledge_documents WHERE organization_id IS NULL")
    ).scalar_one()

    if missing_organization_count != 0:
        raise RuntimeError(
            "Migration stopped because one or more knowledge documents "
            "could not be assigned to an organization safely."
        )

    op.alter_column(
        "knowledge_documents",
        "organization_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
    op.create_index(
        op.f("ix_knowledge_documents_organization_id"),
        "knowledge_documents",
        ["organization_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_knowledge_documents_organization_id_organizations",
        "knowledge_documents",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    """Remove direct organization ownership from knowledge documents."""
    op.drop_constraint(
        "fk_knowledge_documents_organization_id_organizations",
        "knowledge_documents",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_knowledge_documents_organization_id"),
        table_name="knowledge_documents",
    )
    op.drop_column("knowledge_documents", "organization_id")
