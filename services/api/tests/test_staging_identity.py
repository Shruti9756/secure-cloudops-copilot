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
