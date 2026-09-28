"""Exercise auth-session/bootstrap migration and guarded downgrade in isolation."""
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.core.database import Database

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "greencity"


def assert_isolated(database_url: str) -> None:
    target = make_url(database_url)
    if (os.getenv("GREENCITY_ISOLATED_MIGRATION_PATH_TESTS") != "1"
            or target.host not in {"127.0.0.1", "localhost"}
            or target.username != "test_migrator"):
        raise RuntimeError("Auth-session migration tests require the isolated runner")


def migrate(command: str, revision_name: str, *, expect_success: bool = True) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "scripts.migrate", command, revision_name], cwd=ROOT,
        env=os.environ.copy(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    if (result.returncode == 0) != expect_success:
        output = (result.stdout or "").replace(os.environ.get("DATABASE_URL", ""), "[REDACTED]")
        raise RuntimeError(f"Auth-session migration {command} had an unexpected result: {output.strip()}")


def main() -> int:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("Auth-session migration tests require a temporary database")
    assert_isolated(database_url)
    database = Database(Settings())
    demo_id, ordinary_id, tenant_id = uuid4(), uuid4(), uuid4()
    try:
        migrate("upgrade", "0015")
        with database.engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO greencity.tenants (id, name) VALUES (:id, :name)"
            ), {"id": tenant_id, "name": f"Auth session migration {tenant_id}"})
            for account_id, username in ((demo_id, "admin_demo"), (ordinary_id, "internal_operator")):
                connection.execute(text(
                    "INSERT INTO greencity.accounts "
                    "(id, tenant_id, username, hashed_password, full_name, is_active) "
                    "VALUES (:id, :tenant_id, :username, :password, :name, TRUE)"
                ), {"id": account_id, "tenant_id": tenant_id, "username": username,
                    "password": "legacy-hash-placeholder", "name": "Migration fixture"})

        migrate("upgrade", "0016")
        with database.engine.connect() as connection:
            inspector = inspect(connection)
            account_columns = {column["name"] for column in inspector.get_columns("accounts", schema=SCHEMA)}
            if not {"session_version", "must_change_password"}.issubset(account_columns):
                raise RuntimeError("Account security columns are missing")
            if "auth_sessions" not in inspector.get_table_names(schema=SCHEMA):
                raise RuntimeError("Auth session table is missing")
            states = dict(connection.execute(text(
                "SELECT username, must_change_password FROM greencity.accounts "
                "WHERE id IN (:demo, :ordinary)"
            ), {"demo": demo_id, "ordinary": ordinary_id}).all())
            if states != {"admin_demo": True, "internal_operator": False}:
                raise RuntimeError("Forced password-change backfill is incorrect")

        migrate("downgrade", "0015", expect_success=False)
        with database.engine.begin() as connection:
            connection.execute(text(
                "UPDATE greencity.accounts SET must_change_password = FALSE WHERE id = :id"
            ), {"id": demo_id})
        migrate("downgrade", "0015")
        migrate("upgrade", "0016")
        with database.engine.connect() as connection:
            if connection.scalar(text("SELECT version_num FROM greencity.alembic_version")) != "0016":
                raise RuntimeError("Auth-session migration did not return to 0016")
        with database.engine.begin() as connection:
            connection.execute(text(
                "DELETE FROM greencity.accounts WHERE id IN (:demo, :ordinary)"
            ), {"demo": demo_id, "ordinary": ordinary_id})
            connection.execute(text(
                "DELETE FROM greencity.tenants WHERE id = :tenant"
            ), {"tenant": tenant_id})
        print("Auth-session and forced-password migration paths: PASS")
        return 0
    finally:
        database.close()


if __name__ == "__main__":
    raise SystemExit(main())
