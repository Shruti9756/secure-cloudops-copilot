from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Membership, Tenant

# These are the only roles and permissions supported by the V0.2 baseline.
type MembershipRole = Literal["admin", "manager", "engineer"]
type Permission = Literal["knowledge:read", "documents:write"]
type AuthenticationSource = Literal["local", "cognito"]

# Keep permissions in code, rather than trusting a role name sent by a browser.
ROLE_PERMISSIONS: dict[MembershipRole, frozenset[Permission]] = {
    "admin": frozenset({"knowledge:read", "documents:write"}),
    "manager": frozenset({"knowledge:read", "documents:write"}),
    "engineer": frozenset({"knowledge:read"}),
}

# All authorization failures use one safe message. This avoids revealing whether
# a different tenant exists or whether another user has membership there.
AUTHORIZATION_DENIED_MESSAGE = "Tenant access is not permitted"


class AuthorizationDeniedError(PermissionError):
    """Raised when a user lacks the required organization and role access."""


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    """A verified caller; database memberships remain the authorization source."""

    user_id: UUID
    identity_subject: str
    display_name: str
    # Existing unit-test and local-demo principals remain local by default.
    authentication_source: AuthenticationSource = "local"


@dataclass(frozen=True)
class AuthorizedTenant:
    """The tenant and role returned only after a successful authorization decision."""

    tenant: Tenant
    role: MembershipRole


def authorize_tenant_action(
    session: Session,
    *,
    principal: AuthenticatedPrincipal,
    tenant_slug: str,
    permission: Permission,
) -> AuthorizedTenant:
    """Allow an action only when the user belongs to the tenant's organization."""

    # The tenant comes from server-side routing or configuration, not browser trust.
    tenant = session.scalar(select(Tenant).where(Tenant.slug == tenant_slug))

    if tenant is None:
        raise AuthorizationDeniedError(AUTHORIZATION_DENIED_MESSAGE)

    # A membership must connect this exact user to this tenant's organization.
    membership = session.scalar(
        select(Membership).where(
            Membership.user_id == principal.user_id,
            Membership.organization_id == tenant.organization_id,
        )
    )

    if membership is None or membership.organization_id != tenant.organization_id:
        raise AuthorizationDeniedError(AUTHORIZATION_DENIED_MESSAGE)

    role_permissions = ROLE_PERMISSIONS.get(membership.role)

    # Fail closed if database data contains an unexpected role.
    if role_permissions is None or permission not in role_permissions:
        raise AuthorizationDeniedError(AUTHORIZATION_DENIED_MESSAGE)

    return AuthorizedTenant(
        tenant=tenant,
        role=membership.role,
    )
