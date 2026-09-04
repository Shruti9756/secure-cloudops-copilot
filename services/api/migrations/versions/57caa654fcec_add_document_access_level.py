"""add document access level

Revision ID: 57caa654fcec
Revises: 781ee401f524
Create Date: 2026-08-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "57caa654fcec"
down_revision: str | Sequence[str] | None = "781ee401f524"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add a safe document visibility default and database-level allowlist."""
    op.add_column(
        "knowledge_documents",
        sa.Column(
            "access_level",
            sa.String(length=32),
            server_default=sa.text("'organization'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_knowledge_documents_access_level",
        "knowledge_documents",
        "access_level IN ('organization', 'restricted')",
    )


def downgrade() -> None:
    """Remove document visibility controls in reverse order."""
    op.drop_constraint(
        "ck_knowledge_documents_access_level",
        "knowledge_documents",
        type_="check",
    )
    op.drop_column("knowledge_documents", "access_level")
