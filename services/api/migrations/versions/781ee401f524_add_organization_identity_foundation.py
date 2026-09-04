"""add organization identity foundation

Revision ID: 781ee401f524
Revises: 3af19eec00a4
Create Date: 2026-08-27 23:10:56.616251

"""

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "781ee401f524"
down_revision: str | Sequence[str] | None = "3af19eec00a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# A stable ID lets this migration safely connect the existing V0.1 demo workspace.
# A fixed UUID lets this migration safely connect the existing demo tenant
# to its initial organization.
NIMBUSCART_ORGANIZATION_ID = UUID("00000000-0000-0000-0000-000000000201")


def upgrade() -> None:
    """Create organization identity tables and safely backfill the V0.1 tenant."""
    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=63), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("identity_subject", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("identity_subject"),
    )
    op.create_table(
        "memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('admin', 'manager', 'engineer')",
            name="ck_memberships_role",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "user_id",
            name="uq_memberships_organization_user",
        ),
    )
    op.create_index(
        op.f("ix_memberships_organization_id"),
        "memberships",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_memberships_user_id",
        "memberships",
        ["user_id"],
        unique=False,
    )

    # Existing V0.1 tenant rows need a value before this becomes a required column.
    op.add_column(
        "tenants",
        sa.Column("organization_id", sa.Uuid(), nullable=True),
    )

    op.execute(
        sa.text(
            """
            INSERT INTO organizations (id, slug, name)
            VALUES (:organization_id, 'nimbuscart', 'NimbusCart')
            ON CONFLICT (slug) DO NOTHING
            """
        ).bindparams(organization_id=NIMBUSCART_ORGANIZATION_ID)
    )
    op.execute(
        sa.text(
            """
            UPDATE tenants
            SET organization_id = :organization_id
            WHERE slug = 'nimbuscart' AND organization_id IS NULL
            """
        ).bindparams(organization_id=NIMBUSCART_ORGANIZATION_ID)
    )

    # Fail closed instead of silently assigning an unknown tenant to NimbusCart.
    connection = op.get_bind()
    unassigned_tenant_count = connection.execute(
        sa.text("SELECT COUNT(*) FROM tenants WHERE organization_id IS NULL")
    ).scalar_one()

    if unassigned_tenant_count != 0:
        raise RuntimeError(
            "Migration stopped because one or more tenants could not be assigned "
            "to an organization safely."
        )

    op.alter_column(
        "tenants",
        "organization_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
    op.create_index(
        op.f("ix_tenants_organization_id"),
        "tenants",
        ["organization_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_tenants_organization_id_organizations",
        "tenants",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    """Remove the organization identity foundation in reverse dependency order."""
    op.drop_constraint(
        "fk_tenants_organization_id_organizations",
        "tenants",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_tenants_organization_id"), table_name="tenants")
    op.drop_column("tenants", "organization_id")
    op.drop_index("ix_memberships_user_id", table_name="memberships")
    op.drop_index(
        op.f("ix_memberships_organization_id"),
        table_name="memberships",
    )
    op.drop_table("memberships")
    op.drop_table("users")
    op.drop_table("organizations")
