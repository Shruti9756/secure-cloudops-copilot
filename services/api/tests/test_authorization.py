from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.db.models import Membership, Tenant
from app.services.authorization import (
    AUTHORIZATION_DENIED_MESSAGE,
    AuthenticatedPrincipal,
    AuthorizationDeniedError,
    authorize_tenant_action,
)


def make_principal() -> AuthenticatedPrincipal:
    """Create a stable fake authenticated user for authorization tests."""
    return AuthenticatedPrincipal(
        user_id=uuid4(),
        identity_subject="local-test-user-subject",
        display_name="Local Test User",
    )


def make_tenant() -> Tenant:
    """Create a tenant belonging to one organization."""
    return Tenant(
        id=uuid4(),
        organization_id=uuid4(),
        slug="nimbuscart",
        name="NimbusCart",
    )


def test_engineer_can_read_knowledge_in_their_organization() -> None:
    """Engineers may use read-only incident knowledge in their own organization."""
    session = Mock()
    principal = make_principal()
    tenant = make_tenant()
    membership = Membership(
        organization_id=tenant.organization_id,
        user_id=principal.user_id,
        role="engineer",
    )
    session.scalar.side_effect = [tenant, membership]

    authorized_tenant = authorize_tenant_action(
        session,
        principal=principal,
        tenant_slug="nimbuscart",
        permission="knowledge:read",
    )

    assert authorized_tenant.tenant is tenant
    assert authorized_tenant.role == "engineer"


def test_engineer_cannot_upload_documents() -> None:
    """Engineers remain read-only; document uploads require a higher role."""
    session = Mock()
    principal = make_principal()
    tenant = make_tenant()
    membership = Membership(
        organization_id=tenant.organization_id,
        user_id=principal.user_id,
        role="engineer",
    )
    session.scalar.side_effect = [tenant, membership]

    with pytest.raises(AuthorizationDeniedError, match=AUTHORIZATION_DENIED_MESSAGE):
        authorize_tenant_action(
            session,
            principal=principal,
            tenant_slug="nimbuscart",
            permission="documents:write",
        )


def test_manager_can_upload_documents() -> None:
    """Managers may maintain organization knowledge documents."""
    session = Mock()
    principal = make_principal()
    tenant = make_tenant()
    membership = Membership(
        organization_id=tenant.organization_id,
        user_id=principal.user_id,
        role="manager",
    )
    session.scalar.side_effect = [tenant, membership]

    authorized_tenant = authorize_tenant_action(
        session,
        principal=principal,
        tenant_slug="nimbuscart",
        permission="documents:write",
    )

    assert authorized_tenant.role == "manager"


def test_user_membership_in_another_organization_is_denied() -> None:
    """A user cannot cross an organization boundary even with a valid role."""
    session = Mock()
    principal = make_principal()
    tenant = make_tenant()
    membership = Membership(
        organization_id=uuid4(),
        user_id=principal.user_id,
        role="admin",
    )
    session.scalar.side_effect = [tenant, membership]

    with pytest.raises(AuthorizationDeniedError, match=AUTHORIZATION_DENIED_MESSAGE):
        authorize_tenant_action(
            session,
            principal=principal,
            tenant_slug="nimbuscart",
            permission="knowledge:read",
        )


def test_unknown_database_role_is_denied() -> None:
    """Unexpected data must never grant access accidentally."""
    session = Mock()
    principal = make_principal()
    tenant = make_tenant()
    membership = Membership(
        organization_id=tenant.organization_id,
        user_id=principal.user_id,
        role="unexpected-role",
    )
    session.scalar.side_effect = [tenant, membership]

    with pytest.raises(AuthorizationDeniedError, match=AUTHORIZATION_DENIED_MESSAGE):
        authorize_tenant_action(
            session,
            principal=principal,
            tenant_slug="nimbuscart",
            permission="knowledge:read",
        )
