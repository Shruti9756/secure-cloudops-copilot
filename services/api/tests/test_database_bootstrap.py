from unittest.mock import MagicMock

import pytest

from app.db import bootstrap
from app.db.base import Base


def test_grants_cover_only_application_tables() -> None:
    assert set(bootstrap.TABLE_GRANTS) == set(Base.metadata.tables)
    assert "alembic_version" not in bootstrap.TABLE_GRANTS
    assert bootstrap.TABLE_GRANTS["audit_events"] == ("SELECT", "INSERT")
    assert bootstrap.TABLE_GRANTS["document_chunks"] == (
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
    )


def test_bootstrap_rejects_non_staging_before_migration(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    migrate = MagicMock()
    monkeypatch.setattr(bootstrap, "migrate", migrate)

    with pytest.raises(RuntimeError, match="only in staging"):
        bootstrap.bootstrap()

    migrate.assert_not_called()


def test_bootstrap_migrates_as_admin_before_granting_role(monkeypatch) -> None:
    values = {
        "APP_ENV": "staging",
        "DATABASE_HOST": "db.internal",
        "DATABASE_PORT": "5432",
        "DATABASE_NAME": "securecloudops",
        "DATABASE_ADMIN_USERNAME": "securecloudops_admin",
        "DATABASE_ADMIN_PASSWORD": "synthetic-admin-secret",
        "DATABASE_APP_USERNAME": "securecloudops_app",
        "DATABASE_APP_PASSWORD": "synthetic-app-secret",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)

    events = []

    def fake_migrate(url) -> None:
        events.append(("migrate", url.username, url.password, url.query["sslmode"]))

    def fake_provision_role(**kwargs) -> None:
        events.append(("provision", kwargs["app_password"]))

    monkeypatch.setattr(bootstrap, "migrate", fake_migrate)
    monkeypatch.setattr(bootstrap, "provision_role", fake_provision_role)

    bootstrap.bootstrap()

    assert events == [
        ("migrate", "securecloudops_admin", "synthetic-admin-secret", "require"),
        ("provision", "synthetic-app-secret"),
    ]


def test_role_sql_does_not_contain_plaintext_password(monkeypatch) -> None:
    connection = MagicMock()
    connection.info.encoding = "utf-8"
    connection.pgconn.encrypt_password.return_value = b"SCRAM-SHA-256$synthetic-verifier"
    cursor = MagicMock()
    cursor.fetchone.side_effect = [None, (False, False)]
    connection.cursor.return_value.__enter__.return_value = cursor
    connector = MagicMock()
    connector.return_value.__enter__.return_value = connection
    monkeypatch.setattr(bootstrap.psycopg, "connect", connector)

    bootstrap.provision_role(
        host="db.internal",
        port=5432,
        database="securecloudops",
        admin_username="securecloudops_admin",
        admin_password="synthetic-admin-secret",
        app_password="synthetic-app-secret",
    )

    assert connector.call_args.kwargs["sslmode"] == "require"
    connection.pgconn.encrypt_password.assert_called_once()
    assert "synthetic-app-secret" not in repr(cursor.execute.call_args_list)


def test_cli_failure_never_prints_secret(monkeypatch, capsys) -> None:
    def fail() -> None:
        raise RuntimeError("synthetic-secret-must-not-appear")

    monkeypatch.setattr(bootstrap, "bootstrap", fail)

    with pytest.raises(SystemExit) as exit_info:
        bootstrap.main()

    assert exit_info.value.code == 1
    assert "synthetic-secret-must-not-appear" not in capsys.readouterr().err
