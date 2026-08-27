from app.db.models import Membership, Organization, Tenant, User


def test_tenant_belongs_to_an_organization() -> None:
    """Every workspace must have an organization ownership boundary."""
    tenant_foreign_key = next(iter(Tenant.__table__.foreign_keys))

    assert tenant_foreign_key.target_fullname == "organizations.id"
    assert tenant_foreign_key.ondelete == "RESTRICT"
    assert Tenant.__table__.c.organization_id.nullable is False


def test_membership_connects_one_user_to_one_organization_with_a_safe_role() -> None:
    """Membership is the future authorization record for organization access."""
    foreign_key_targets = {
        foreign_key.target_fullname for foreign_key in Membership.__table__.foreign_keys
    }
    constraint_names = {constraint.name for constraint in Membership.__table__.constraints}

    assert Organization.__tablename__ == "organizations"
    assert User.__tablename__ == "users"
    assert foreign_key_targets == {"organizations.id", "users.id"}
    assert "uq_memberships_organization_user" in constraint_names
    assert "ck_memberships_role" in constraint_names
