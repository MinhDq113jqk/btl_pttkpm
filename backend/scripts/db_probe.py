"""Read-only database preflight. Never prints connection/driver error details."""
import json
import sys

from sqlalchemy import text

from app.core.config import Settings
from app.core.database import Database


def main():
    database = None
    try:
        database = Database(Settings())
        with database.engine.connect() as conn:
            tls = conn.execute(text("SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()" )).scalar_one()
            tables = conn.execute(text("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog', 'information_schema') ORDER BY 1, 2")).all()
            role = conn.execute(text("SELECT rolsuper, rolcreaterole, rolcreatedb, rolbypassrls FROM pg_roles WHERE rolname = current_user")).one()
            print(json.dumps({"database": "connected", "tls": tls, "timezone": conn.execute(text("SHOW timezone")).scalar_one(),
                              "tables": [list(row) for row in tables],
                              "role_flags": dict(zip(["superuser", "create_role", "create_db", "bypass_rls"], role))}))
    except Exception:
        print("Database preflight failed; connection details suppressed.")
        return 1
    finally:
        if database is not None:
            database.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
