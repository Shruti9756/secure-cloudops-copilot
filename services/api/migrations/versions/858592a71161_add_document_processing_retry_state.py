"""add document processing retry state

Revision ID: 858592a71161
Revises: 1e321f401d84
Create Date: 2026-09-13 22:29:05.183780
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "858592a71161"
down_revision: str | Sequence[str] | None = "1e321f401d84"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Store durable retry scheduling and safe failure state per document."""
    op.add_column(
        "knowledge_documents",
        sa.Column(
            "processing_attempt_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column(
            "next_processing_attempt_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column(
            "last_processing_failure_reason",
            sa.String(length=64),
            nullable=True,
        ),
    )

    # Stop with a clear error instead of silently accepting an unknown lifecycle state.
    connection = op.get_bind()
    unexpected_status_count = connection.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM knowledge_documents
            WHERE ingestion_status NOT IN (
                'pending',
                'chunked',
                'embedded',
                'failed'
            )
            """
        )
    ).scalar_one()

    if unexpected_status_count != 0:
        raise RuntimeError(
            "Migration stopped because one or more documents have an unsupported ingestion status."
        )

    op.create_check_constraint(
        "ck_knowledge_documents_ingestion_status",
        "knowledge_documents",
        "ingestion_status IN ('pending', 'chunked', 'embedded', 'failed')",
    )
    op.create_check_constraint(
        "ck_knowledge_documents_processing_attempt_count_nonnegative",
        "knowledge_documents",
        "processing_attempt_count >= 0",
    )


def downgrade() -> None:
    """Remove document retry scheduling and failure state."""
    op.drop_constraint(
        "ck_knowledge_documents_processing_attempt_count_nonnegative",
        "knowledge_documents",
        type_="check",
    )
    op.drop_constraint(
        "ck_knowledge_documents_ingestion_status",
        "knowledge_documents",
        type_="check",
    )
    op.drop_column(
        "knowledge_documents",
        "last_processing_failure_reason",
    )
    op.drop_column(
        "knowledge_documents",
        "next_processing_attempt_at",
    )
    op.drop_column(
        "knowledge_documents",
        "processing_attempt_count",
    )
