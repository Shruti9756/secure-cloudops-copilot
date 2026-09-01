"""add chunk organization scope

Revision ID: 1e321f401d84
Revises: d09c9a1ccb00
Create Date: 2026-09-01 22:26:58.925450
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "1e321f401d84"
down_revision: str | Sequence[str] | None = "d09c9a1ccb00"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Backfill direct organization ownership for derived document chunks."""
    op.add_column(
        "document_chunks",
        sa.Column("organization_id", sa.Uuid(), nullable=True),
    )

    # A chunk belongs to exactly one document, whose organization is already
    # required. Copy that trusted scope before enforcing the new column.
    op.execute(
        sa.text(
            """
            UPDATE document_chunks AS chunk
            SET organization_id = document.organization_id
            FROM knowledge_documents AS document
            WHERE chunk.document_id = document.id
              AND chunk.organization_id IS NULL
            """
        )
    )

    connection = op.get_bind()
    missing_organization_count = connection.execute(
        sa.text("SELECT COUNT(*) FROM document_chunks WHERE organization_id IS NULL")
    ).scalar_one()

    if missing_organization_count != 0:
        raise RuntimeError(
            "Migration stopped because one or more document chunks "
            "could not be assigned to an organization safely."
        )

    op.alter_column(
        "document_chunks",
        "organization_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
    op.create_index(
        op.f("ix_document_chunks_organization_id"),
        "document_chunks",
        ["organization_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_document_chunks_organization_id_organizations",
        "document_chunks",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    """Remove direct organization ownership from document chunks."""
    op.drop_constraint(
        "fk_document_chunks_organization_id_organizations",
        "document_chunks",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_document_chunks_organization_id"),
        table_name="document_chunks",
    )
    op.drop_column("document_chunks", "organization_id")
