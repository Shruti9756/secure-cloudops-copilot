from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Membership, Tenant, User
from app.services.authorization import MembershipRole


@dataclass(frozen=True)
class IdentityProvisioningResult:
    """Safe summary of an idempotent user-and-membership provisioning action."""

    user_created: bool
    membership_created: bool


def provision_identity_membership(
    session: Session,
    *,
    tenant: Tenant,
    identity_subject: str,
    display_name: str,
    role: MembershipRole,
) -> IdentityProvisioningResult:
    """Create a database user and organization membership only when missing."""

    user = session.scalar(select(User).where(User.identity_subject == identity_subject))
    user_created = user is None

    if user is None:
        user = User(
            # This is Cognito's verified stable `sub`, never an email address.
            identity_subject=identity_subject,
            display_name=display_name,
        )
        session.add(user)
        session.flush()

    membership = session.scalar(
        select(Membership).where(
            Membership.organization_id == tenant.organization_id,
            Membership.user_id == user.id,
        )
    )
    membership_created = membership is None

    if membership is None:
        membership = Membership(
            organization_id=tenant.organization_id,
            user=user,
            role=role,
        )
        session.add(membership)
        session.flush()

    # An existing role is never silently overwritten or escalated.
    return IdentityProvisioningResult(
        user_created=user_created,
        membership_created=membership_created,
    )
