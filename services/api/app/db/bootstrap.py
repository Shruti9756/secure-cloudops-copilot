"""One-off staging database migration and application-role bootstrap."""

import os
import sys
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import URL

from app.db import models  # noqa: F401  # Register the model tables.
from app.infrastructure.postgres import build_staging_database_url

APP_ROLE = "securecloudops_app"

TABLE_GRANTS = {
    "organizations": ("SELECT", "INSERT"),
    "users": ("SELECT", "INSERT"),
    "memberships": ("SELECT", "INSERT"),
    "tenants": ("SELECT", "INSERT", "UPDATE"),
    "knowledge_documents": ("SELECT", "INSERT", "UPDATE"),
    "document_chunks": ("SELECT", "INSERT", "UPDATE", "DELETE"),
    "audit_events": ("SELECT", "INSERT"),
}


def required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def migrate(admin_url: URL) -> None:
    alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"
    config = Config(str(alembic_ini))
    engine = create_engine(admin_url, poolclass=pool.NullPool)

    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
    finally:
        engine.dispose()


def provision_role(
    *,
    host: str,
    port: int,
    database: str,
    admin_username: str,
    admin_password: str,
    app_password: str,
) -> None:
    with psycopg.connect(
        host=host,
        port=port,
        dbname=database,
        user=admin_username,
        password=admin_password,
        sslmode="require",
    ) as connection:
        encoding = connection.info.encoding
        verifier = connection.pgconn.encrypt_password(
            app_password.encode(encoding),
            APP_ROLE.encode(encoding),
            b"scram-sha-256",
        ).decode(encoding)
        role = sql.Identifier(APP_ROLE)

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT rolsuper, rolcreatedb, rolcreaterole,
                       rolreplication, rolbypassrls
                FROM pg_roles WHERE rolname = %s
                """,
                (APP_ROLE,),
            )
            existing_attributes = cursor.fetchone()

            if existing_attributes is not None:
                if any(existing_attributes):
                    raise RuntimeError("Existing application role has elevated privileges")

                cursor.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM pg_auth_members AS membership
                        JOIN pg_roles AS app ON app.oid = membership.member
                        WHERE app.rolname = %s
                    )
                    """,
                    (APP_ROLE,),
                )
                if cursor.fetchone()[0]:
                    raise RuntimeError("Existing application role has role memberships")

                cursor.execute(
                    sql.SQL("ALTER ROLE {} WITH LOGIN NOINHERIT PASSWORD {}").format(
                        role, sql.Literal(verifier)
                    )
                )
            else:
                cursor.execute(
                    sql.SQL("CREATE ROLE {} WITH LOGIN NOINHERIT PASSWORD {}").format(
                        role, sql.Literal(verifier)
                    )
                )

            cursor.execute(
                sql.SQL("REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA {} FROM {}").format(
                    sql.Identifier("public"), role
                )
            )
            cursor.execute(
                sql.SQL("REVOKE ALL PRIVILEGES ON SCHEMA {} FROM {}").format(
                    sql.Identifier("public"), role
                )
            )
            cursor.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(database), role)
            )
            cursor.execute(
                sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(sql.Identifier("public"), role)
            )

            for table, privileges in TABLE_GRANTS.items():
                cursor.execute(
                    sql.SQL("GRANT {} ON TABLE {} TO {}").format(
                        sql.SQL(", ").join(sql.SQL(privilege) for privilege in privileges),
                        sql.Identifier("public", table),
                        role,
                    )
                )

            cursor.execute(
                """
                SELECT has_schema_privilege(%s, 'public', 'CREATE'),
                       has_database_privilege(%s, %s, 'CREATE')
                """,
                (APP_ROLE, APP_ROLE, database),
            )
            if any(cursor.fetchone()):
                raise RuntimeError("Application role unexpectedly has CREATE privilege")


def bootstrap() -> None:
    if required_env("APP_ENV") != "staging":
        raise RuntimeError("Database bootstrap is allowed only in staging")

    host = required_env("DATABASE_HOST")
    port = int(required_env("DATABASE_PORT"))
    database = required_env("DATABASE_NAME")
    admin_username = required_env("DATABASE_ADMIN_USERNAME")
    admin_password = required_env("DATABASE_ADMIN_PASSWORD")

    if required_env("DATABASE_APP_USERNAME") != APP_ROLE:
        raise RuntimeError("DATABASE_APP_USERNAME must be securecloudops_app")

    app_password = required_env("DATABASE_APP_PASSWORD")
    admin_url = build_staging_database_url(
        host=host,
        port=port,
        database=database,
        username=admin_username,
        password=admin_password,
    )

    migrate(admin_url)
    provision_role(
        host=host,
        port=port,
        database=database,
        admin_username=admin_username,
        admin_password=admin_password,
        app_password=app_password,
    )


def main() -> None:
    try:
        bootstrap()
    except Exception as error:  # noqa: BLE001
        # Database errors may contain SQL. Never print the error or traceback.
        print(f"Database bootstrap failed ({type(error).__name__}).", file=sys.stderr)
        raise SystemExit(1) from None

    print("Database bootstrap completed.")


if __name__ == "__main__":
    main()
