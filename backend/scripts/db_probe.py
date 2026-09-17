"""Read-only database preflight. Never prints connection/driver error details."""
import json
import sys
import argparse

from sqlalchemy import text

from app.core.config import Settings
from app.core.database import Database


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only PostgreSQL preflight")
    parser.add_argument(
        "--expected-revision",
        default=None,
        help="Fail when the live Alembic revision differs from this value.",
    )
    args = parser.parse_args(argv)
    database = None
    try:
        database = Database(Settings())
        with database.engine.connect() as conn:
            tls = conn.execute(text("SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()" )).scalar_one()
            revision_table = conn.execute(text(
                "SELECT to_regclass('greencity.alembic_version')"
            )).scalar_one_or_none()
            revision = None
            if revision_table is not None:
                revision = conn.execute(text(
                    "SELECT version_num FROM greencity.alembic_version"
                )).scalar_one_or_none()
            tables = conn.execute(text("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog', 'information_schema') ORDER BY 1, 2")).all()
            role = conn.execute(text("SELECT rolsuper, rolcreaterole, rolcreatedb, rolbypassrls FROM pg_roles WHERE rolname = current_user")).one()
            result = {"database": "connected", "tls": tls, "schema_revision": revision,
                      "timezone": conn.execute(text("SHOW timezone")).scalar_one(),
                              "tables": [list(row) for row in tables],
                              "role_flags": dict(zip(["superuser", "create_role", "create_db", "bypass_rls"], role))}
            print(json.dumps(result))
            expected = args.expected_revision or None
            if expected is not None and revision != expected:
                print("Database schema revision is not the requested head.")
                return 2
    except Exception:
        print("Database preflight failed; connection details suppressed.")
        return 1
    finally:
        if database is not None:
            database.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
