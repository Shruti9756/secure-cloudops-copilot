"""Create one explicit Cognito-backed local user and organization membership."""

import argparse

from sqlalchemy import select

from app.db.models import Tenant
from app.db.session import get_session_factory
from app.services.identity_provisioning import provision_identity_membership


def parse_arguments() -> argparse.Namespace:
    """Parse operator-supplied Cognito identity data without accepting token content."""

    parser = argparse.ArgumentParser(
        description=(
            "Map one verified Cognito sub claim to a SecureCloudOps user "
            "and organization membership."
        )
    )
    parser.add_argument(
        "subject",
        help="Verified Cognito access-token sub claim.",
    )
    parser.add_argument(
        "--display-name",
        default="Shruti Demo Administrator",
        help="Safe display name stored locally (default: Shruti Demo Administrator).",
    )
    parser.add_argument(
        "--tenant",
        default="nimbuscart",
        help="Tenant workspace to grant access (default: nimbuscart).",
    )
    parser.add_argument(
        "--role",
        choices=("admin", "manager", "engineer"),
        default="admin",
        help="Organization role to grant (default: admin).",
    )
    return parser.parse_args()


def main() -> None:
    """Provision one Cognito identity without modifying existing memberships."""

    arguments = parse_arguments()
    subject = arguments.subject.strip()
    display_name = arguments.display_name.strip()

    if not subject:
        raise ValueError("Cognito subject must not be blank")

    if not display_name:
        raise ValueError("Display name must not be blank")

    with get_session_factory().begin() as session:
        tenant = session.scalar(select(Tenant).where(Tenant.slug == arguments.tenant))

        if tenant is None:
            raise RuntimeError(
                "The requested tenant does not exist. "
                "Run demo-data ingestion before identity provisioning."
            )

        result = provision_identity_membership(
            session,
            tenant=tenant,
            identity_subject=subject,
            display_name=display_name,
            role=arguments.role,
        )

    print(
        "Cognito identity ready: "
        f"user_created={result.user_created}, "
        f"membership_created={result.membership_created}"
    )


if __name__ == "__main__":
    main()
