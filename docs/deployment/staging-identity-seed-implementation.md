# Staging identity seed: manual implementation guide

Prepared 17 October 2026. This is a **documentation-only code handoff**: the two
Python files below have not been created by this guide. The operator copies the
complete code blocks into the exact new paths, then runs the offline checks.
Do not modify existing models, provisioning helpers, grants, Terraform, or CI.

This closes one groundwork gap: the runtime image copies `app/`, but does not
package `scripts/` or the demo corpus. A module under `app/db/` can eventually
provide a deliberately scoped operator entry point without adding demo scripts
to the image. It does not migrate a database, ingest documents, call Cognito,
start workers, or enable models/storage.

For orientation only, the project is approximately **70% groundwork / 50% cloud
proof**. These are rough planning estimates, not measured acceptance scores or
permission to start a live session. Successful image publication and offline
tests do not establish browser sign-in, database membership, or full answers.

## Safety contract

- The fixture is one fixed synthetic organization, one fixed workspace, one
  operator, and one `manager` application membership. `manager` permits document
  uploads without assigning the broader `admin` label; this is not an AWS role.
- Accept Cognito `sub` as an opaque, case-sensitive string, **not a UUID**. The
  length/NUL/boundary-whitespace checks are operational/database bounds, not
  validation of Cognito ownership. An operator must separately verify the exact
  subject against the dedicated staging pool. Never supply an email, JWT, or a
  newly invented subject as a substitute.
- Fixed UUID/slug/name fingerprints and issuer-derived user/membership UUID5s
  prevent adoption of an unmarked existing identity. First creation requires
  **all four rows absent**; a repeat requires **all four exact rows present**.
  Matching-but-partial state is a conflict, not permission to repair it.
- Reject any other workspace/member in the reserved organization, membership
  outside it for the reserved user, changed names/roles, and ID/slug collisions.
  Membership is organization-scoped, so checking the workspace alone is unsafe.
- Use one explicit outer transaction and a clean session. The helper flushes but
  never commits, updates, deletes, creates schema, changes grants, or retries a
  conflict. Run one operator invocation at a time; do not treat this as a general
  concurrent identity-provisioning service.
- The CLI reads only selected `os.environ` values. It never instantiates the
  application's Settings, loads `.env` values, or requires Redis/model settings.
  It uses the existing TLS-required URL builder and the restricted application
  database user. Existing `SELECT`/`INSERT` grants suffice; no elevated role is
  needed. The imported URL helper does not establish a connection by itself.
- The endpoint/database/environment guards prevent common accidental targets.
  They are **not** proof of AWS account ownership, Cognito identity, or server
  hostname verification. Existing `sslmode=require` requires encryption, not
  `verify-full` hostname validation. Future execution still requires independently
  reviewed staging outputs, credentials, network, and explicit approval.

The IDs and UUID5 derivation below are part of the fixture identity. Do not
change them after use to work around a conflict. Inspect conflicting state in a
separately approved session instead of renaming, deleting, or adopting it.

## 1. Create `services/api/app/db/staging_identity.py`

Absolute path:
`C:\Users\Shru\Documents\AI+AWS\services\api\app\db\staging_identity.py`.
Copy this entire block, excluding the Markdown fence.

```python filename=services/api/app/db/staging_identity.py
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
```

## 2. Create `services/api/tests/test_staging_identity.py`

Absolute path:
`C:\Users\Shru\Documents\AI+AWS\services\api\tests\test_staging_identity.py`.
These tests use only temporary in-memory SQLite and mocked CLI boundaries. Only
the four identity tables are created: no pgvector tables, migration, Redis,
PostgreSQL server, Cognito, or AWS calls. SQLite does not prove PostgreSQL grants,
RDS identity, TLS certificate verification, or concurrent-operation behavior.

The subject and password below are **unit-test fixtures only**, not values for
a future live invocation.

```python filename=services/api/tests/test_staging_identity.py
from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import staging_identity as seed_module
from app.db.base import Base
from app.db.models import Membership, Organization, Tenant, User

SUBJECT = "synthetic:Opaque-Subject/Case-01"
TABLES = (Organization, Tenant, User, Membership)


@pytest.fixture
def engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine, tables=[model.__table__ for model in TABLES])
    try:
        yield engine
    finally:
        engine.dispose()


def row_counts(engine):
    with Session(engine) as session:
        return tuple(session.scalar(select(func.count()).select_from(model)) for model in TABLES)


def create_fixture(engine):
    with (
        Session(engine, autoflush=False, expire_on_commit=False) as session,
        session.begin(),
    ):
        return seed_module.seed(session, SUBJECT)


def assert_seed_conflict_preserves_rows(engine):
    before = row_counts(engine)
    with (
        Session(engine, autoflush=False) as session,
        pytest.raises(seed_module.SeedSafetyError),
        session.begin(),
    ):
        seed_module.seed(session, SUBJECT)
    assert row_counts(engine) == before


def add_organization(session, **overrides):
    values = {
        "id": seed_module.ORGANIZATION_ID,
        "slug": seed_module.ORGANIZATION_SLUG,
        "name": seed_module.ORGANIZATION_NAME,
    }
    values.update(overrides)
    row = Organization(**values)
    session.add(row)
    session.flush()
    return row


def add_tenant(session, **overrides):
    values = {
        "id": seed_module.TENANT_ID,
        "organization_id": seed_module.ORGANIZATION_ID,
        "slug": seed_module.TENANT_SLUG,
        "name": seed_module.TENANT_NAME,
    }
    values.update(overrides)
    row = Tenant(**values)
    session.add(row)
    session.flush()
    return row


def add_user(session, **overrides):
    values = {
        "id": seed_module.expected_user_id(SUBJECT),
        "identity_subject": SUBJECT,
        "display_name": seed_module.DISPLAY_NAME,
    }
    values.update(overrides)
    row = User(**values)
    session.add(row)
    session.flush()
    return row


def test_new_fixture_creates_exact_scope_and_preserves_unrelated_rows(engine):
    with Session(engine) as session, session.begin():
        session.add(Organization(id=uuid4(), slug="unrelated", name="Unrelated"))
    assert create_fixture(engine) == seed_module.SeedResult(True, True, True, True)
    assert row_counts(engine) == (2, 1, 1, 1)
    with Session(engine) as session:
        tenant = session.get(Tenant, seed_module.TENANT_ID)
        user = session.get(User, seed_module.expected_user_id(SUBJECT))
        membership = session.get(Membership, seed_module.expected_membership_id(user.id))
        assert tenant.organization_id == seed_module.ORGANIZATION_ID
        assert tenant.slug == seed_module.TENANT_SLUG
        assert user.identity_subject == SUBJECT
        assert user.display_name == seed_module.DISPLAY_NAME
        assert membership.organization_id == tenant.organization_id
        assert membership.user_id == user.id
        assert membership.role == "manager"


def test_exact_repeat_is_a_no_op_without_update_or_delete(engine):
    create_fixture(engine)
    statements = []

    def record(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement.lstrip().split()[0].upper())

    event.listen(engine, "before_cursor_execute", record)
    try:
        result = create_fixture(engine)
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert result == seed_module.SeedResult(False, False, False, False)
    assert row_counts(engine) == (1, 1, 1, 1)
    assert not {"INSERT", "UPDATE", "DELETE"}.intersection(statements)


@pytest.mark.parametrize("subject", ["opaque-not-a-uuid", "MixedCase_Subject", SUBJECT])
def test_subject_is_opaque_and_case_sensitive(engine, subject):
    with Session(engine) as session, session.begin():
        seed_module.seed(session, subject)
    with Session(engine) as session:
        user = session.scalar(select(User))
        assert user.identity_subject == subject
        assert user.id == seed_module.expected_user_id(subject)
    if subject != subject.lower():
        assert seed_module.expected_user_id(subject) != seed_module.expected_user_id(
            subject.lower()
        )


@pytest.mark.parametrize("subject", [None, 7, "", " ", "\x00", "a\x00b", " x", "x ", "x" * 256])
def test_invalid_subject_is_rejected_before_session_use(subject):
    session = Mock(spec=Session)
    with pytest.raises(seed_module.SeedSafetyError):
        seed_module.seed(session, subject)
    session.get_transaction.assert_not_called()


@pytest.mark.parametrize("mode", ["missing", "autobegin", "nested"])
def test_helper_requires_explicit_active_outer_transaction(engine, mode):
    with Session(engine) as session:
        if mode == "missing":
            with pytest.raises(seed_module.SeedSafetyError):
                seed_module.seed(session, SUBJECT)
        elif mode == "autobegin":
            session.scalar(select(Organization))
            with pytest.raises(seed_module.SeedSafetyError):
                seed_module.seed(session, SUBJECT)
        else:
            with (
                session.begin(),
                session.begin_nested(),
                pytest.raises(seed_module.SeedSafetyError),
            ):
                seed_module.seed(session, SUBJECT)
    assert row_counts(engine) == (0, 0, 0, 0)


def test_pending_unrelated_changes_are_not_flushed(engine):
    with (
        Session(engine) as session,
        pytest.raises(seed_module.SeedSafetyError),
        session.begin(),
    ):
        session.add(Organization(id=uuid4(), slug="unrelated", name="Unrelated"))
        seed_module.seed(session, SUBJECT)
    assert row_counts(engine) == (0, 0, 0, 0)


@pytest.mark.parametrize("field", ["id", "slug", "name"])
def test_organization_fingerprint_conflicts(engine, field):
    value = uuid4() if field == "id" else "foreign"
    with Session(engine) as session, session.begin():
        add_organization(session, **{field: value})
    assert_seed_conflict_preserves_rows(engine)


@pytest.mark.parametrize("field", ["id", "slug", "name", "organization_id"])
def test_tenant_fingerprint_and_owner_conflicts(engine, field):
    with Session(engine) as session, session.begin():
        add_organization(session)
        value = uuid4() if field in {"id", "organization_id"} else "foreign"
        if field == "organization_id":
            add_organization(session, id=value, slug="other-org", name="Other")
        add_tenant(session, **{field: value})
    assert_seed_conflict_preserves_rows(engine)


@pytest.mark.parametrize(
    "partial", ["organization", "organization_tenant", "without_membership", "user"]
)
def test_matching_partial_state_is_not_repaired(engine, partial):
    with Session(engine) as session, session.begin():
        if partial != "user":
            add_organization(session)
        if partial in {"organization_tenant", "without_membership"}:
            add_tenant(session)
        if partial in {"without_membership", "user"}:
            add_user(session)
    assert_seed_conflict_preserves_rows(engine)


def test_extra_organization_workspace_blocks_seed(engine):
    create_fixture(engine)
    with Session(engine) as session, session.begin():
        add_tenant(session, id=uuid4(), slug="extra-workspace", name="Extra")
    assert_seed_conflict_preserves_rows(engine)


def test_different_organization_member_blocks_seed(engine):
    create_fixture(engine)
    with Session(engine) as session, session.begin():
        other = add_user(session, id=uuid4(), identity_subject="another-subject")
        session.add(
            Membership(
                id=uuid4(),
                organization_id=seed_module.ORGANIZATION_ID,
                user_id=other.id,
                role="engineer",
            )
        )
    assert_seed_conflict_preserves_rows(engine)


def test_membership_in_another_organization_blocks_seed(engine):
    create_fixture(engine)
    with Session(engine) as session, session.begin():
        other = add_organization(session, id=uuid4(), slug="other-org", name="Other")
        session.add(
            Membership(
                id=uuid4(),
                organization_id=other.id,
                user_id=seed_module.expected_user_id(SUBJECT),
                role="engineer",
            )
        )
    assert_seed_conflict_preserves_rows(engine)


@pytest.mark.parametrize("field", ["id", "identity_subject", "display_name"])
def test_existing_user_is_not_adopted_or_renamed(engine, field):
    with Session(engine) as session, session.begin():
        value = uuid4() if field == "id" else "foreign"
        add_user(session, **{field: value})
    assert_seed_conflict_preserves_rows(engine)


@pytest.mark.parametrize("field", ["id", "role"])
def test_existing_membership_is_not_reidentified_or_escalated(engine, field):
    create_fixture(engine)
    with Session(engine) as session, session.begin():
        membership = session.scalar(select(Membership))
        setattr(membership, field, uuid4() if field == "id" else "engineer")
    assert_seed_conflict_preserves_rows(engine)


def test_different_subject_does_not_add_a_second_operator(engine):
    create_fixture(engine)
    with (
        Session(engine) as session,
        pytest.raises(seed_module.SeedSafetyError),
        session.begin(),
    ):
        seed_module.seed(session, "different-opaque-subject")
    assert row_counts(engine) == (1, 1, 1, 1)


@pytest.mark.parametrize("error_type", [RuntimeError, IntegrityError])
def test_error_after_flush_rolls_back_every_created_row(engine, monkeypatch, error_type):
    with Session(engine, autoflush=False) as session:
        original_flush = session.flush
        calls = 0

        def fail_after_first_row(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                if error_type is IntegrityError:
                    raise IntegrityError("synthetic uniqueness race", {}, ValueError("synthetic"))
                raise RuntimeError("synthetic failure after an intermediate flush")
            return original_flush(*args, **kwargs)

        monkeypatch.setattr(session, "flush", fail_after_first_row)
        with pytest.raises(error_type), session.begin():
            seed_module.seed(session, SUBJECT)
    assert row_counts(engine) == (0, 0, 0, 0)


def test_helper_never_calls_commit(engine, monkeypatch):
    with Session(engine, autoflush=False) as session:
        commit = Mock(side_effect=AssertionError("Helper must not commit"))
        monkeypatch.setattr(session, "commit", commit)
        with session.begin():
            seed_module.seed(session, SUBJECT)
            commit.assert_not_called()
    assert row_counts(engine) == (1, 1, 1, 1)


@pytest.fixture
def seed_environment(monkeypatch):
    values = {
        **seed_module.EXPECTED_ENVIRONMENT,
        "DATABASE_HOST": "secure-cloudops-staging-db.synthetic.us-east-1.rds.amazonaws.com",
        "DATABASE_PASSWORD": "synthetic-unit-test-password",
    }
    monkeypatch.setattr(seed_module.os, "environ", values)
    return values


@pytest.mark.parametrize(
    ("name", "bad_value"),
    [
        ("APP_ENV", "production"),
        ("APP_ENV", "development"),
        ("STAGING_IDENTITY_SEED_CONFIRMATION", ""),
        ("IDENTITY_PROVIDER", "local"),
        ("COGNITO_ISSUER", "https://cognito-idp.us-east-1.amazonaws.com/another-pool"),
        ("DATABASE_HOST", "secure-cloudops-production-db.synthetic.us-east-1.rds.amazonaws.com"),
        ("DATABASE_NAME", "another_database"),
        ("DATABASE_USERNAME", "postgres"),
        ("DATABASE_PORT", "5433"),
        ("DATABASE_PASSWORD", ""),
        ("DATABASE_URL", "postgresql://not-an-approved-override"),
    ],
)
def test_cli_environment_guards_run_before_engine(seed_environment, monkeypatch, name, bad_value):
    seed_environment[name] = bad_value
    engine_builder = Mock()
    monkeypatch.setattr(seed_module, "create_engine", engine_builder)
    with pytest.raises(seed_module.SeedSafetyError):
        seed_module.run_seed(SUBJECT)
    engine_builder.assert_not_called()


def test_cli_missing_environment_and_bad_subject_do_not_open_engine(monkeypatch):
    monkeypatch.setattr(seed_module.os, "environ", {})
    engine_builder = Mock()
    monkeypatch.setattr(seed_module, "create_engine", engine_builder)
    for subject in (SUBJECT, "", " trailing "):
        with pytest.raises(seed_module.SeedSafetyError):
            seed_module.run_seed(subject)
    engine_builder.assert_not_called()


@pytest.mark.parametrize("fail", [False, True])
def test_run_seed_uses_one_transaction_tls_and_disposes_engine(seed_environment, monkeypatch, fail):
    engine = Mock()
    engine_builder = Mock(return_value=engine)
    session = MagicMock()
    session.__enter__.return_value = session
    session_builder = Mock(return_value=session)
    result = seed_module.SeedResult(True, True, True, True)
    helper = Mock(side_effect=RuntimeError("synthetic")) if fail else Mock(return_value=result)
    monkeypatch.setattr(seed_module, "create_engine", engine_builder)
    monkeypatch.setattr(seed_module, "Session", session_builder)
    monkeypatch.setattr(seed_module, "seed", helper)
    if fail:
        with pytest.raises(RuntimeError):
            seed_module.run_seed(SUBJECT)
    else:
        assert seed_module.run_seed(SUBJECT) == result
    url = engine_builder.call_args.args[0]
    assert url.host == seed_environment["DATABASE_HOST"]
    assert url.database == "securecloudops"
    assert url.username == "securecloudops_app"
    assert url.port == 5432
    assert url.query["sslmode"] == "require"
    assert engine_builder.call_args.kwargs == {
        "poolclass": seed_module.NullPool,
        "hide_parameters": True,
    }
    session_builder.assert_called_once_with(engine, autoflush=False, expire_on_commit=False)
    session.begin.assert_called_once_with()
    helper.assert_called_once_with(session, SUBJECT)
    engine.dispose.assert_called_once_with()


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["--subject"],
        ["--subject", SUBJECT, "--invalidflag", "synthetic-secret-argument"],
    ],
)
def test_main_argument_errors_do_not_echo_values_or_run_seed(monkeypatch, capsys, arguments):
    helper = Mock()
    monkeypatch.setattr(seed_module, "run_seed", helper)
    assert seed_module.main(arguments) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "Staging identity seed failed (SeedSafetyError).\n"
    assert SUBJECT not in captured.err
    assert "synthetic-secret-argument" not in captured.err
    helper.assert_not_called()


def test_main_errors_are_class_only_without_sensitive_values(monkeypatch, capsys):
    secret = "synthetic-sensitive-password-and-connection-string"
    monkeypatch.setattr(
        seed_module, "run_seed", Mock(side_effect=RuntimeError(f"{secret} {SUBJECT}"))
    )
    assert seed_module.main(["--subject", SUBJECT]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "Staging identity seed failed (RuntimeError).\n"
    assert SUBJECT not in captured.err
    assert secret not in captured.err


def test_main_prints_only_creation_flags_and_fixed_role(monkeypatch, capsys):
    monkeypatch.setattr(
        seed_module,
        "run_seed",
        Mock(return_value=seed_module.SeedResult(False, False, False, False)),
    )
    assert seed_module.main(["--subject", SUBJECT]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert "organization_created=False" in captured.out
    assert "tenant_created=False" in captured.out
    assert "user_created=False" in captured.out
    assert "membership_created=False" in captured.out
    assert "role=manager" in captured.out
    assert SUBJECT not in captured.out
```

## Offline draft verification — 17 October 2026

The exact Python blocks in this guide were loaded as modules directly from
Markdown, without creating either proposed `.py` file. Both passed the existing
API Ruff lint and format checks. Running the existing API unit suite together
with the proposed tests produced **675 passed, 6 deselected**, including **60 new
identity-seed cases**. End-to-end tests remained deselected under the existing
API pytest configuration. The new database tests used in-memory SQLite; CLI
connection boundaries were mocked. No application PostgreSQL connection, AWS
request, identity creation, or image publication was performed by this check.

This is draft QA, not confirmation that the operator has added the source or
that the published image contains it. Run the commands below again after
copying the files to catch any copy/paste differences.

## 3. Offline review and tests only

After manually creating exactly those two files, paste this entire block once.
It stops immediately if a check fails. Formatting writes only the two newly created files.
The pytest commands run local unit tests; the new tests create only temporary
in-memory SQLite identity tables. They do not run the CLI against an application
database. Do not add a dependency merely to make a test pass.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location -LiteralPath 'C:\Users\Shru\Documents\AI+AWS\services\api'

    uv run --locked ruff format app/db/staging_identity.py tests/test_staging_identity.py
    if ($LASTEXITCODE -ne 0) { throw 'Formatting failed. Stop and paste the error.' }

    uv run --locked ruff check app/db/staging_identity.py tests/test_staging_identity.py
    if ($LASTEXITCODE -ne 0) { throw 'Identity lint failed. Stop and paste the error.' }

    uv run --locked python -m pytest -q tests/test_staging_identity.py
    if ($LASTEXITCODE -ne 0) { throw 'Identity tests failed. Stop and paste the error.' }

    uv run --locked python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Full unit suite failed. Stop and paste the error.' }

    uv run --locked ruff format --check .
    if ($LASTEXITCODE -ne 0) { throw 'Repository format check failed. Stop and paste the error.' }

    uv run --locked ruff check .
    if ($LASTEXITCODE -ne 0) { throw 'Repository lint failed. Stop and paste the error.' }

    Set-Location -LiteralPath 'C:\Users\Shru\Documents\AI+AWS'
    git diff --check
    if ($LASTEXITCODE -ne 0) { throw 'Whitespace check failed. Stop and paste the error.' }

    git status --short
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect Git status. Stop here.' }
}
```

Review the diff: the source changes are exactly the two intended new Python
files; the separately reviewed documentation updates are also expected. No
existing helper needs editing.
Outside the mocked unit tests, do **not** invoke `run_seed` or execute
`python -m app.db.staging_identity --subject`. Do not open an application
database connection, create live identities, publish an
image, alter Terraform, or start a staging session in this batch. Parsing
`--help` is not seeding, but it is not a substitute for the tests.

The previously verified/published image does **not** contain this new module.
After source review and offline tests, a separate bounded build/scan/publication
batch must produce and verify a new immutable image before any approved cloud
seed task can reference it. This guide intentionally supplies no live subject,
password, environment setup, RunTask, migration, or AWS command.

Any future live seed runner must use only the restricted application database
credentials and receive its own review. Do **not** reuse the administrator
bootstrap task with a command override. No Terraform or IAM change belongs to
this implementation batch.

## Limits and review notes

- The seed proves a fixed database mapping was created or exactly repeated; it
  does not authenticate the supplied subject or sign a user into the browser.
- A matching partial state is rejected even if it looks repairable. There is no
  delete/reset/role-change mode and no automatic retry after an uncertain result.
- SQLite unit tests do not validate PostgreSQL permissions or live task wiring.
  The implementation deliberately uses no `SELECT ... FOR UPDATE`, since the
  restricted application role has no update privilege on identity tables.
- The existing migration/bootstrap must already have completed in any future
  live session. This module does not grant privileges or repair schemas.
- This seed creates no documents or queue intents. Provider/topology, private S3
  storage, SQS proof, browser authorization, and full answer/citation checks remain
  separate gates in the controlled-session runbook.
- Cognito subject-format guidance: [AWS standard attributes](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-settings-attributes.html).
