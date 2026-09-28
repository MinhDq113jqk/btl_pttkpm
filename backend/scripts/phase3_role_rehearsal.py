"""Rehearse owner/migrator/runtime boundaries on one disposable loopback DB.

This script creates only a random, temporary schema and three random roles. It
refuses non-loopback hosts and requires PHASE3_ROLE_REHEARSAL=1, so it cannot be
mistaken for a production provisioning command.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import time

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url


def _dsn_with_credentials(raw: str, username: str, password: str) -> str:
    parsed = make_url(raw)
    return str(parsed.set(username=username, password=password))


def _loopback(raw: str) -> bool:
    host = make_url(raw).host
    return host in {"127.0.0.1", "localhost", "::1"}


def main() -> int:
    if os.getenv("PHASE3_ROLE_REHEARSAL") != "1":
        print("Set PHASE3_ROLE_REHEARSAL=1 for the disposable role rehearsal.")
        return 2
    raw_admin_dsn = os.getenv("DATABASE_URL", "")
    if not raw_admin_dsn or not _loopback(raw_admin_dsn):
        print("Role rehearsal requires a loopback DATABASE_URL; no shared DB was used.")
        return 2

    token = secrets.token_hex(5)
    owner = f"gc_p3_owner_{token}"
    migrator = f"gc_p3_migrator_{token}"
    runtime = f"gc_p3_runtime_{token}"
    schema = f"phase3_rehearsal_{token}"
    migrator_password = secrets.token_urlsafe(24)
    runtime_password = secrets.token_urlsafe(24)
    started = time.perf_counter()
    admin = None
    try:
        admin = psycopg.connect(raw_admin_dsn, autocommit=True)
        admin.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOINHERIT").format(sql.Identifier(owner)))
        admin.execute(sql.SQL("CREATE ROLE {} LOGIN NOINHERIT PASSWORD {}").format(
            sql.Identifier(migrator), sql.Literal(migrator_password),
        ))
        admin.execute(sql.SQL("CREATE ROLE {} LOGIN NOINHERIT PASSWORD {}").format(
            sql.Identifier(runtime), sql.Literal(runtime_password),
        ))
        admin.execute(sql.SQL("GRANT {} TO {}").format(sql.Identifier(owner), sql.Identifier(migrator)))
        admin.execute(sql.SQL("CREATE SCHEMA {} AUTHORIZATION {}").format(sql.Identifier(schema), sql.Identifier(owner)))

        migrator_conn = psycopg.connect(_dsn_with_credentials(raw_admin_dsn, migrator, migrator_password))
        try:
            migrator_conn.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(owner)))
            migrator_conn.execute(sql.SQL("CREATE TABLE {}.records (id integer PRIMARY KEY, value text NOT NULL)").format(sql.Identifier(schema)))
            migrator_conn.commit()
        finally:
            migrator_conn.close()

        admin.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(sql.Identifier(schema), sql.Identifier(runtime)))
        admin.execute(sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {} TO {}").format(sql.Identifier(schema), sql.Identifier(runtime)))

        runtime_conn = psycopg.connect(_dsn_with_credentials(raw_admin_dsn, runtime, runtime_password))
        ddl_denied = False
        try:
            runtime_conn.execute(sql.SQL("INSERT INTO {}.records (id, value) VALUES (1, 'ok')").format(sql.Identifier(schema)))
            runtime_conn.commit()
            runtime_conn.execute(sql.SQL("CREATE TABLE {}.should_fail (id integer)").format(sql.Identifier(schema)))
            runtime_conn.commit()
        except psycopg.errors.InsufficientPrivilege:
            runtime_conn.rollback()
            ddl_denied = True
        finally:
            runtime_conn.close()
        if not ddl_denied:
            raise RuntimeError("runtime role unexpectedly executed DDL")

        admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
        admin.execute(sql.SQL("DROP ROLE {}\n").format(sql.Identifier(runtime)))
        admin.execute(sql.SQL("DROP ROLE {}\n").format(sql.Identifier(migrator)))
        admin.execute(sql.SQL("DROP ROLE {}\n").format(sql.Identifier(owner)))
        print(json.dumps({
            "status": "PASS",
            "runtime_dml": "allowed",
            "runtime_ddl": "denied",
            "schema_isolation": "random disposable schema",
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        }))
        return 0
    except Exception as exc:
        if os.getenv("PHASE3_VERBOSE") == "1":
            print(f"role rehearsal diagnostic: {type(exc).__name__}: {exc}")
        print("Role rehearsal failed; details suppressed and no shared database was used.")
        return 1
    finally:
        if admin is not None:
            try:
                admin.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
                for role in (runtime, migrator, owner):
                    admin.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
            except Exception:
                pass
            admin.close()


if __name__ == "__main__":
    sys.exit(main())
