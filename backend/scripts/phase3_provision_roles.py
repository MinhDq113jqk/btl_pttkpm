"""Provision the deployment's PostgreSQL roles from mounted Docker secrets."""

from __future__ import annotations

import os
from pathlib import Path
import re
import sys

import psycopg
from psycopg import sql


ROLE_NAME = re.compile(r"[a-z_][a-z0-9_]{0,62}\Z")


def _secret(variable: str) -> str:
    path = Path(os.environ[variable])
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise ValueError("empty secret")
    return value


def _ensure_login_role(connection, name: str, password: str) -> None:
    exists = connection.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (name,)).fetchone()
    role = sql.Identifier(name)
    literal = sql.Literal(password)
    if exists:
        connection.execute(sql.SQL("ALTER ROLE {} LOGIN NOINHERIT PASSWORD {}").format(role, literal))
    else:
        connection.execute(sql.SQL("CREATE ROLE {} LOGIN NOINHERIT PASSWORD {}").format(role, literal))


def main() -> int:
    admin_role = os.getenv("PHASE3_ADMIN_ROLE", "greencity_admin")
    owner_role = os.getenv("PHASE3_OWNER_ROLE", "greencity_owner")
    migrator_role = os.getenv("PHASE3_MIGRATOR_ROLE", "greencity_migrator")
    runtime_role = os.getenv("PHASE3_RUNTIME_ROLE", "greencity_runtime")
    if any(ROLE_NAME.fullmatch(name) is None for name in (admin_role, owner_role, migrator_role, runtime_role)):
        print("Invalid Phase 3 role name.")
        return 2
    try:
        with psycopg.connect(
            host=os.getenv("PHASE3_ADMIN_HOST", "db"),
            port=int(os.getenv("PHASE3_ADMIN_PORT", "5432")),
            dbname=os.getenv("PHASE3_ADMIN_DATABASE", "greencity"),
            user=admin_role,
            password=_secret("PHASE3_ADMIN_PASSWORD_FILE"),
            sslmode="require",
            connect_timeout=10,
        ) as connection:
            connection.execute("SET ROLE NONE")
            owner_exists = connection.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (owner_role,)).fetchone()
            if not owner_exists:
                connection.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOINHERIT").format(sql.Identifier(owner_role)))
            _ensure_login_role(connection, migrator_role, _secret("PHASE3_MIGRATOR_PASSWORD_FILE"))
            _ensure_login_role(connection, runtime_role, _secret("PHASE3_RUNTIME_PASSWORD_FILE"))
            connection.execute(sql.SQL("GRANT {} TO {}").format(
                sql.Identifier(owner_role), sql.Identifier(migrator_role),
            ))
            connection.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS greencity AUTHORIZATION {}").format(
                sql.Identifier(owner_role),
            ))
            connection.execute(sql.SQL("ALTER SCHEMA greencity OWNER TO {}").format(sql.Identifier(owner_role)))

            tables = connection.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'greencity'"
            ).fetchall()
            for (table_name,) in tables:
                connection.execute(sql.SQL("ALTER TABLE greencity.{} OWNER TO {}").format(
                    sql.Identifier(table_name), sql.Identifier(owner_role),
                ))
            sequences = connection.execute(
                "SELECT sequencename FROM pg_sequences WHERE schemaname = 'greencity'"
            ).fetchall()
            for (sequence_name,) in sequences:
                connection.execute(sql.SQL("ALTER SEQUENCE greencity.{} OWNER TO {}").format(
                    sql.Identifier(sequence_name), sql.Identifier(owner_role),
                ))
            functions = connection.execute(
                """SELECT p.proname, pg_get_function_identity_arguments(p.oid)
                   FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                   WHERE n.nspname = 'greencity'"""
            ).fetchall()
            for function_name, arguments in functions:
                connection.execute(sql.SQL("ALTER FUNCTION greencity.{}({}) OWNER TO {}").format(
                    sql.Identifier(function_name), sql.SQL(arguments), sql.Identifier(owner_role),
                ))

            connection.execute(sql.SQL("REVOKE ALL ON SCHEMA greencity FROM PUBLIC"))
            connection.execute(sql.SQL("GRANT USAGE ON SCHEMA greencity TO {}").format(sql.Identifier(runtime_role)))
            connection.execute(sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA greencity TO {}").format(
                sql.Identifier(runtime_role),
            ))
            connection.execute(sql.SQL("GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA greencity TO {}").format(
                sql.Identifier(runtime_role),
            ))
            connection.execute(sql.SQL("ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA greencity "
                                       "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}").format(
                sql.Identifier(owner_role), sql.Identifier(runtime_role),
            ))
            connection.execute(sql.SQL("ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA greencity "
                                       "GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO {}").format(
                sql.Identifier(owner_role), sql.Identifier(runtime_role),
            ))
        print("GreenCity owner, migrator and runtime roles provisioned; runtime has DML only.")
        return 0
    except Exception:
        print("Phase 3 role provisioning failed; details suppressed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
