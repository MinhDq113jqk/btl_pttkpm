"""Prove the configured runtime database role can use DML but cannot run DDL."""

from __future__ import annotations

import os
import secrets
import sys

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url


def main() -> int:
    owner_url = os.getenv("PHASE3_OWNER_DATABASE_URL", "")
    runtime_url = os.getenv("DATABASE_URL", "")
    if os.getenv("PHASE3_RUNTIME_ROLE_TEST") != "1":
        print("Set PHASE3_RUNTIME_ROLE_TEST=1 for the loopback runtime-role check.")
        return 2
    if any(not raw or make_url(raw).host not in {"127.0.0.1", "localhost", "::1"}
           for raw in (owner_url, runtime_url)):
        print("Runtime-role check requires loopback owner/runtime URLs; no shared DB was used.")
        return 2

    token = secrets.token_hex(5)
    table = f"phase3_runtime_check_{token}"
    owner = None
    try:
        owner = psycopg.connect(owner_url, autocommit=True)
        owner.execute("SET ROLE greencity_owner")
        owner.execute(sql.SQL("CREATE TABLE greencity.{} (value integer NOT NULL)").format(sql.Identifier(table)))
        runtime = psycopg.connect(runtime_url)
        denied = False
        try:
            runtime.execute(sql.SQL("INSERT INTO greencity.{} (value) VALUES (1)").format(sql.Identifier(table)))
            runtime.commit()
            runtime.execute(sql.SQL("CREATE TABLE greencity.{} (id integer)").format(sql.Identifier(f"{table}_ddl")))
            runtime.commit()
        except psycopg.errors.InsufficientPrivilege:
            runtime.rollback()
            denied = True
        finally:
            runtime.close()
        if not denied:
            raise RuntimeError("runtime DDL was allowed")
        owner.execute(sql.SQL("DROP TABLE IF EXISTS greencity.{} CASCADE").format(sql.Identifier(table)))
        print("Runtime role DML: PASS; runtime DDL denial: PASS.")
        return 0
    except Exception:
        print("Runtime role check failed; details suppressed.")
        return 1
    finally:
        if owner is not None:
            try:
                owner.execute(sql.SQL("DROP TABLE IF EXISTS greencity.{} CASCADE").format(sql.Identifier(table)))
                owner.execute(sql.SQL("DROP TABLE IF EXISTS greencity.{} CASCADE").format(sql.Identifier(f"{table}_ddl")))
            except Exception:
                pass
            owner.close()


if __name__ == "__main__":
    sys.exit(main())
