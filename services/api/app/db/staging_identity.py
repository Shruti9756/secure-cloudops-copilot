"""Explicit, fixed-scope synthetic staging identity seed; never run on import."""

import argparse
import os
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from typing import NoReturn
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import create_engine, or_, select
from sqlalchemy.orm import Session, SessionTransactionOrigin
from sqlalchemy.pool import NullPool

from app.db.models import Membership, Organization, Tenant, User
from app.infrastructure.postgres import build_staging_database_url

COGNITO_ISSUER = "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_cgRH4viJI"
ORGANIZATION_ID = UUID("00000000-0000-0000-0000-000000000401")
TENANT_ID = UUID("00000000-0000-0000-0000-000000000402")
ORGANIZATION_SLUG = "staging-demo-org"
ORGANIZATION_NAME = "Synthetic Staging Organization"
TENANT_SLUG = "staging-demo"
TENANT_NAME = "Synthetic Staging Workspace"
DISPLAY_NAME = "Synthetic Staging Operator"
MEMBERSHIP_ROLE = "manager"

EXPECTED_ENVIRONMENT = {
    "APP_ENV": "staging",
    "STAGING_IDENTITY_SEED_CONFIRMATION": "synthetic-staging-only",
    "IDENTITY_PROVIDER": "cognito",
    "COGNITO_ISSUER": COGNITO_ISSUER,
    "DATABASE_NAME": "securecloudops",
    "DATABASE_USERNAME": "securecloudops_app",
    "DATABASE_PORT": "5432",
}
DATABASE_HOST_PATTERN = re.compile(
    r"secure-cloudops-staging-db\."
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"\.us-east-1\.rds\.amazonaws\.com"
)


class SeedSafetyError(ValueError):
    """A bounded staging guard or existing-state check did not pass."""


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> NoReturn:
        raise SeedSafetyError("Invalid command-line arguments")


@dataclass(frozen=True)
class SeedResult:
    organization_created: bool
    tenant_created: bool
    user_created: bool
    membership_created: bool


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SeedSafetyError(message)


def validate_subject(subject: str) -> None:
    """Keep the exact opaque subject; syntax checks cannot verify its owner."""
    _require(isinstance(subject, str), "Subject must be a string")
    _require(1 <= len(subject) <= 255, "Subject length is outside the supported bounds")
    _require(subject == subject.strip(), "Subject has boundary whitespace")
    _require("\x00" not in subject, "Subject contains NUL")


def expected_user_id(subject: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"securecloudops:staging-user\n{COGNITO_ISSUER}\n{subject}")


def expected_membership_id(user_id: UUID) -> UUID:
    return uuid5(NAMESPACE_URL, f"securecloudops:staging-membership:{ORGANIZATION_ID}:{user_id}")


def seed(session: Session, subject: str) -> SeedResult:
    """Create all four fixed rows, or confirm an exact repeat, without committing."""
    validate_subject(subject)
    transaction = session.get_transaction()
    _require(
        transaction is not None
        and transaction.is_active
        and transaction.origin is SessionTransactionOrigin.BEGIN
        and not session.in_nested_transaction(),
        "An explicit active outer transaction is required",
    )
    _require(
        not (session.new or session.dirty or session.deleted),
        "The seed requires a clean session",
    )
    user_id = expected_user_id(subject)
    membership_id = expected_membership_id(user_id)

    organizations = session.scalars(
        select(Organization).where(
            or_(Organization.id == ORGANIZATION_ID, Organization.slug == ORGANIZATION_SLUG)
        )
    ).all()
    _require(len(organizations) <= 1, "Organization fingerprint collision")
    organization = organizations[0] if organizations else None
    if organization is not None:
        _require(
            organization.id == ORGANIZATION_ID
            and organization.slug == ORGANIZATION_SLUG
            and organization.name == ORGANIZATION_NAME,
            "Organization fingerprint mismatch",
        )

    tenants = session.scalars(
        select(Tenant).where(or_(Tenant.id == TENANT_ID, Tenant.slug == TENANT_SLUG))
    ).all()
    _require(len(tenants) <= 1, "Workspace fingerprint collision")
    tenant = tenants[0] if tenants else None
    if tenant is not None:
        _require(
            tenant.id == TENANT_ID
            and tenant.slug == TENANT_SLUG
            and tenant.name == TENANT_NAME
            and tenant.organization_id == ORGANIZATION_ID,
            "Workspace fingerprint or organization mismatch",
        )
    extra_tenant_id = session.scalar(
        select(Tenant.id)
        .where(Tenant.organization_id == ORGANIZATION_ID, Tenant.id != TENANT_ID)
        .limit(1)
    )
    _require(extra_tenant_id is None, "Reserved organization has another workspace")

    users = session.scalars(
        select(User).where(or_(User.id == user_id, User.identity_subject == subject))
    ).all()
    _require(len(users) <= 1, "User fingerprint collision")
    user = users[0] if users else None
    if user is not None:
        _require(
            user.id == user_id
            and user.identity_subject == subject
            and user.display_name == DISPLAY_NAME,
            "User fingerprint or display name mismatch",
        )

    memberships = session.scalars(
        select(Membership).where(
            or_(
                Membership.id == membership_id,
                Membership.organization_id == ORGANIZATION_ID,
                Membership.user_id == user_id,
            )
        )
    ).all()
    _require(len(memberships) <= 1, "Reserved membership scope conflict")
    membership = memberships[0] if memberships else None
    if membership is not None:
        _require(
            membership.id == membership_id
            and membership.organization_id == ORGANIZATION_ID
            and membership.user_id == user_id
            and membership.role == MEMBERSHIP_ROLE,
            "Membership fingerprint, organization, user, or role mismatch",
        )

    existing = tuple(row is not None for row in (organization, tenant, user, membership))
    _require(
        not any(existing) or all(existing), "Matching but partial fixture state is not adopted"
    )
    if all(existing):
        return SeedResult(False, False, False, False)

    session.add(Organization(id=ORGANIZATION_ID, slug=ORGANIZATION_SLUG, name=ORGANIZATION_NAME))
    session.flush()
    session.add(
        Tenant(
            id=TENANT_ID,
            organization_id=ORGANIZATION_ID,
            slug=TENANT_SLUG,
            name=TENANT_NAME,
        )
    )
    session.flush()
    session.add(User(id=user_id, identity_subject=subject, display_name=DISPLAY_NAME))
    session.flush()
    session.add(
        Membership(
            id=membership_id,
            organization_id=ORGANIZATION_ID,
            user_id=user_id,
            role=MEMBERSHIP_ROLE,
        )
    )
    session.flush()
    return SeedResult(True, True, True, True)


def run_seed(subject: str) -> SeedResult:
    """Validate explicit environment guards before constructing a database engine."""
    validate_subject(subject)
    for name, expected in EXPECTED_ENVIRONMENT.items():
        _require(os.environ.get(name) == expected, "A required staging environment guard failed")
    _require(not os.environ.get("DATABASE_URL"), "DATABASE_URL overrides are not accepted")
    host = os.environ.get("DATABASE_HOST", "")
    password = os.environ.get("DATABASE_PASSWORD", "")
    _require(
        DATABASE_HOST_PATTERN.fullmatch(host) is not None, "Staging database host guard failed"
    )
    _require(bool(password), "A database password is required")

    url = build_staging_database_url(
        host=host,
        port=5432,
        database="securecloudops",
        username="securecloudops_app",
        password=password,
    )
    engine = create_engine(url, poolclass=NullPool, hide_parameters=True)
    try:
        with (
            Session(engine, autoflush=False, expire_on_commit=False) as session,
            session.begin(),
        ):
            result = seed(session, subject)
        return result
    finally:
        engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    parser = _SafeArgumentParser(
        description="Seed the fixed synthetic staging identity only.", allow_abbrev=False
    )
    parser.add_argument(
        "--subject", required=True, help="Operator-verified opaque staging Cognito sub"
    )
    try:
        arguments = parser.parse_args(argv)
        result = run_seed(arguments.subject)
    except Exception as error:  # noqa: BLE001 -- never expose SQL, credentials, or subjects.
        print(f"Staging identity seed failed ({type(error).__name__}).", file=sys.stderr)
        return 1
    print(
        "Staging identity seed completed: "
        f"organization_created={result.organization_created}, "
        f"tenant_created={result.tenant_created}, "
        f"user_created={result.user_created}, "
        f"membership_created={result.membership_created}, "
        f"role={MEMBERSHIP_ROLE}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
