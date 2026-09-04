from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Tenant, User
from app.services.authorization import AuthenticatedPrincipal, MembershipRole
from app.services.identity_provisioning import (
    IdentityProvisioningResult,
    provision_identity_membership,
)

LOCAL_DEVELOPMENT_ONLY_MESSAGE = (
    "The local development identity is unavailable outside the development environment."
)
LOCAL_DEVELOPMENT_USER_NOT_BOOTSTRAPPED_MESSAGE = (
    "The local development identity has not been bootstrapped."
)


class LocalDevelopmentIdentityUnavailableError(RuntimeError):
    """Raised when code tries to use the local identity outside development."""


def bootstrap_local_development_identity(
    session: Session,
    *,
    tenant: Tenant,
    identity_subject: str,
    display_name: str,
    role: MembershipRole,
) -> IdentityProvisioningResult:
    """Provision the explicit local demo identity through the shared safe helper."""

    return provision_identity_membership(
        session,
        tenant=tenant,
        identity_subject=identity_subject,
        display_name=display_name,
        role=role,
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
        authentication_source="local",
    )
