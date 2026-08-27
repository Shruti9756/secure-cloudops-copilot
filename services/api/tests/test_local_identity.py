from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.db.models import Membership, Tenant, User
from app.services.local_identity import (
    LOCAL_DEVELOPMENT_ONLY_MESSAGE,
    LocalDevelopmentIdentityUnavailableError,
    bootstrap_local_development_identity,
    get_local_development_principal,
)


def make_tenant() -> Tenant:
    """Create a tenant owned by one organization for identity tests."""
    return Tenant(
        id=uuid4(),
        organization_id=uuid4(),
        slug="nimbuscart",
        name="NimbusCart",
    )


def test_bootstrap_creates_a_user_and_admin_membership() -> None:
    """Bootstrap creates the development user only when the records are absent."""
    session = Mock()
    tenant = make_tenant()
    session.scalar.side_effect = [None, None]

    result = bootstrap_local_development_identity(
        session,
        tenant=tenant,
        identity_subject="local-demo-admin",
        display_name="Local Demo Administrator",
        role="admin",
    )

    added_models = [call.args[0] for call in session.add.call_args_list]
    created_user = next(model for model in added_models if isinstance(model, User))
    created_membership = next(model for model in added_models if isinstance(model, Membership))

    assert result.user_created is True
    assert result.membership_created is True
    assert created_user.identity_subject == "local-demo-admin"
    assert created_membership.organization_id == tenant.organization_id
    assert created_membership.user is created_user
    assert created_membership.role == "admin"


def test_bootstrap_does_not_overwrite_an_existing_membership() -> None:
    """An existing role remains intact instead of being silently escalated."""
    session = Mock()
    tenant = make_tenant()
    user = User(
        id=uuid4(),
        identity_subject="local-demo-admin",
        display_name="Local Demo Administrator",
    )
    membership = Membership(
        organization_id=tenant.organization_id,
        user_id=user.id,
        role="engineer",
    )
    session.scalar.side_effect = [user, membership]

    result = bootstrap_local_development_identity(
        session,
        tenant=tenant,
        identity_subject="local-demo-admin",
        display_name="Changed Name",
        role="admin",
    )

    assert result.user_created is False
    assert result.membership_created is False
    assert membership.role == "engineer"
    session.add.assert_not_called()


def test_get_local_development_principal_returns_the_bootstrapped_user() -> None:
    """The adapter returns a verified internal principal from the database."""
    session = Mock()
    user = User(
        id=uuid4(),
        identity_subject="local-demo-admin",
        display_name="Local Demo Administrator",
    )
    session.scalar.return_value = user

    principal = get_local_development_principal(
        session,
        app_env="development",
        identity_subject="local-demo-admin",
    )

    assert principal.user_id == user.id
    assert principal.identity_subject == "local-demo-admin"
    assert principal.display_name == "Local Demo Administrator"


def test_local_development_identity_is_denied_outside_development() -> None:
    """A deployment environment must not silently use a hard-coded local user."""
    session = Mock()

    with pytest.raises(
        LocalDevelopmentIdentityUnavailableError,
        match=LOCAL_DEVELOPMENT_ONLY_MESSAGE,
    ):
        get_local_development_principal(
            session,
            app_env="production",
            identity_subject="local-demo-admin",
        )

    session.scalar.assert_not_called()
