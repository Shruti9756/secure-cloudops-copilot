from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Membership, Tenant, User
from app.services.authorization import AuthenticatedPrincipal

type LocalDevelopmentRole = Literal["admin", "manager", "engineer"]

LOCAL_DEVELOPMENT_ONLY_MESSAGE = (
    "The local development identity is unavailable outside the development environment."
)
LOCAL_DEVELOPMENT_USER_NOT_BOOTSTRAPPED_MESSAGE = (
    "The local development identity has not been bootstrapped."
)


class LocalDevelopmentIdentityUnavailableError(RuntimeError):
    """Raised when code tries to use the local identity outside development."""


@dataclass(frozen=True)
class LocalIdentityBootstrapResult:
    """Safe summary of whether bootstrap created local identity records."""

    user_created: bool
    membership_created: bool


def bootstrap_local_development_identity(
    session: Session,
    *,
    tenant: Tenant,
    identity_subject: str,
    display_name: str,
    role: LocalDevelopmentRole,
) -> LocalIdentityBootstrapResult:
    """Create the one explicit local demo user and membership when missing."""

    user = session.scalar(select(User).where(User.identity_subject == identity_subject))
    user_created = user is None

    if user is None:
        user = User(
            identity_subject=identity_subject,
            display_name=display_name,
        )
        session.add(user)
        # Flush assigns the database UUID before the membership references this user.
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

    # Existing memberships are deliberately not overwritten by this helper.
    return LocalIdentityBootstrapResult(
        user_created=user_created,
        membership_created=membership_created,
    )


def get_local_development_principal(
    session: Session,
    *,
    app_env: str,
    identity_subject: str,
) -> AuthenticatedPrincipal:
    """Resolve the bootstrap user only for the explicitly local development mode."""

    if app_env != "development":
        raise LocalDevelopmentIdentityUnavailableError(LOCAL_DEVELOPMENT_ONLY_MESSAGE)

    user = session.scalar(select(User).where(User.identity_subject == identity_subject))

    if user is None:
        raise LocalDevelopmentIdentityUnavailableError(
            LOCAL_DEVELOPMENT_USER_NOT_BOOTSTRAPPED_MESSAGE
        )

    return AuthenticatedPrincipal(
        user_id=user.id,
        identity_subject=user.identity_subject,
        display_name=user.display_name,
    )
