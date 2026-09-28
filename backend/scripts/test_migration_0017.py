"""Exercise opaque login-throttle state migration and guarded downgrade."""
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
import subprocess
import sys

from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.core.database import Database
from app.models.login_throttle import LoginThrottle

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "greencity"


def assert_isolated(database_url: str) -> None:
    target = make_url(database_url)
    if (os.getenv("GREENCITY_ISOLATED_MIGRATION_PATH_TESTS") != "1"
            or target.host not in {"127.0.0.1", "localhost"}
            or target.username != "test_migrator"):
        raise RuntimeError("Login-throttle migration tests require the isolated runner")


def migrate(command: str, revision_name: str, *, expect_success: bool = True) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "scripts.migrate", command, revision_name], cwd=ROOT,
        env=os.environ.copy(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    if (result.returncode == 0) != expect_success:
        output = (result.stdout or "").replace(os.environ.get("DATABASE_URL", ""), "[REDACTED]")
        raise RuntimeError(f"Login-throttle migration {command} had an unexpected result: {output.strip()}")


def main() -> int:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("Login-throttle migration tests require a temporary database")
    assert_isolated(database_url)
    database = Database(Settings())
    identity_key = "a" * 64
    try:
        migrate("upgrade", "0016")
        migrate("upgrade", "0017")
        with database.engine.connect() as connection:
            inspector = inspect(connection)
            columns = {column["name"] for column in inspector.get_columns("login_throttles", schema=SCHEMA)}
            indexes = {index["name"] for index in inspector.get_indexes("login_throttles", schema=SCHEMA)}
            if not {"identity_key", "failure_count", "last_failure_at", "locked_until"}.issubset(columns):
                raise RuntimeError("Login-throttle storage columns are incomplete")
            if "ix_login_throttles_updated_at" not in indexes:
                raise RuntimeError("Login-throttle retention index is missing")

        with database.get_session() as session:
            session.add(LoginThrottle(
                identity_key=identity_key,
                failure_count=5,
                last_failure_at=datetime.now(UTC),
                locked_until=datetime.now(UTC) + timedelta(minutes=1),
            ))
            session.commit()
        migrate("downgrade", "0016", expect_success=False)
        with database.get_session() as session:
            session.query(LoginThrottle).filter(LoginThrottle.identity_key == identity_key).delete()
            session.commit()
        migrate("downgrade", "0016")
        migrate("upgrade", "0017")
        with database.engine.connect() as connection:
            if connection.scalar(text("SELECT version_num FROM greencity.alembic_version")) != "0017":
                raise RuntimeError("Login-throttle migration did not return to 0017")
        print("Login-throttle migration paths: PASS")
        return 0
    finally:
        database.close()


if __name__ == "__main__":
    raise SystemExit(main())
