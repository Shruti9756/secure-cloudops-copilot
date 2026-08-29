from unittest.mock import Mock
from uuid import uuid4

from app.db.models import Membership, Tenant, User
from app.services.identity_provisioning import provision_identity_membership


def make_tenant() -> Tenant:
    """Create a tenant owned by one organization for provisioning tests."""

    return Tenant(
        id=uuid4(),
        organization_id=uuid4(),
        slug="nimbuscart",
        name="NimbusCart",
    )


def test_provision_identity_membership_creates_user_and_admin_membership() -> None:
    session = Mock()
    tenant = make_tenant()
    session.scalar.side_effect = [None, None]

    result = provision_identity_membership(
        session,
        tenant=tenant,
        identity_subject="cognito-subject-123",
        display_name="Shruti Demo Administrator",
        role="admin",
    )

    added_models = [call.args[0] for call in session.add.call_args_list]
    user = next(model for model in added_models if isinstance(model, User))
    membership = next(model for model in added_models if isinstance(model, Membership))

    assert result.user_created is True
    assert result.membership_created is True
    assert user.identity_subject == "cognito-subject-123"
    assert membership.organization_id == tenant.organization_id
    assert membership.user is user
    assert membership.role == "admin"


def test_provision_identity_membership_keeps_an_existing_role() -> None:
    session = Mock()
    tenant = make_tenant()
    user = User(
        id=uuid4(),
        identity_subject="cognito-subject-123",
        display_name="Shruti Demo Administrator",
    )
    membership = Membership(
        organization_id=tenant.organization_id,
        user_id=user.id,
        role="engineer",
    )
    session.scalar.side_effect = [user, membership]

    result = provision_identity_membership(
        session,
        tenant=tenant,
        identity_subject="cognito-subject-123",
        display_name="Changed Name",
        role="admin",
    )

    assert result.user_created is False
    assert result.membership_created is False
    assert membership.role == "engineer"
    session.add.assert_not_called()
