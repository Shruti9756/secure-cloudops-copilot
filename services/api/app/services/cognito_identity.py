from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import User
from app.services.authorization import AuthenticatedPrincipal

COGNITO_USER_NOT_PROVISIONED_MESSAGE = (
    "The authenticated user is not provisioned for SecureCloudOps."
)


class CognitoUserNotProvisionedError(PermissionError):
    """Raised when a verified Cognito identity has no local user record."""


def get_cognito_principal(
    session: Session,
    *,
    subject: str,
) -> AuthenticatedPrincipal:
    """Map a verified Cognito `sub` claim to our database-backed principal."""

    user = session.scalar(select(User).where(User.identity_subject == subject))

    if user is None:
        raise CognitoUserNotProvisionedError(COGNITO_USER_NOT_PROVISIONED_MESSAGE)

    # Display name and memberships come from our database—not token claims.
    return AuthenticatedPrincipal(
        user_id=user.id,
        identity_subject=user.identity_subject,
        display_name=user.display_name,
    )
