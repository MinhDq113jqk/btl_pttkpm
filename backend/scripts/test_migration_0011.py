"""Exercise R5 outbox migration upgrade and fail-closed downgrade paths."""
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.core.database import Database
from app.models.platform import DomainEvent
from app.models.site import Site
from app.models.tenant import Tenant

ROOT = Path(__file__).resolve().parents[1]


def assert_isolated(database_url: str) -> None:
    if os.getenv("GREENCITY_ISOLATED_MIGRATION_PATH_TESTS") != "1":
        raise RuntimeError("Migration-path tests require the isolated runner")
    target = make_url(database_url)
    if target.host not in {"127.0.0.1", "localhost"} or target.username != "test_migrator":
        raise RuntimeError("Migration-path tests refuse a non-isolated database")


def migrate(command: str, revision_name: str, *, expect_success: bool = True) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "scripts.migrate", command, revision_name], cwd=ROOT,
        env=os.environ.copy(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    if bool(result.returncode) != (not expect_success):
        output = (result.stdout or "").replace(os.environ.get("DATABASE_URL", ""), "[REDACTED]")
        raise RuntimeError(f"Migration {command} {revision_name} had an unexpected result: {output.strip()}")


def revision(connection) -> str:
    value = connection.scalar(text("SELECT version_num FROM greencity.alembic_version"))
    if not isinstance(value, str):
        raise RuntimeError("Alembic revision is unavailable")
    return value


def main() -> int:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("Migration-path tests require a temporary database")
    assert_isolated(database_url)
    database = Database(Settings())
    try:
        migrate("upgrade", "0010")
        migrate("upgrade", "0011")
        with database.engine.connect() as connection:
            columns = {column["name"] for column in inspect(connection).get_columns(
                "domain_events", schema="greencity",
            )}
            if revision(connection) != "0011" or not {
                "delivery_status", "attempt_count", "next_attempt_at", "last_error", "delivery_lock_id", "locked_until",
            }.issubset(columns):
                raise RuntimeError("R5 outbox delivery state is missing after 0011 upgrade")
            if "notification_read_models" not in inspect(connection).get_table_names(schema="greencity"):
                raise RuntimeError("R5 notification read model table is missing after 0011 upgrade")

        with database.get_session() as session:
            tenant = Tenant(name=f"0011 downgrade guard {uuid4()}")
            session.add(tenant)
            session.flush()
            site = Site(tenant_id=tenant.id, code=f"M{uuid4().hex[:8]}", name="Migration guard", address="Synthetic")
            session.add(site)
            session.flush()
            event = DomainEvent(
                tenant_id=tenant.id,
                site_id=site.id,
                actor_account_id=None,
                event_type="MigrationGuard",
                resource_type="MigrationGuard",
                resource_id=uuid4(),
                correlation_id=uuid4(),
                payload={},
                delivery_status="DEAD_LETTER",
                attempt_count=3,
            )
            session.add(event)
            session.commit()
        migrate("downgrade", "0010", expect_success=False)
        with database.engine.connect() as connection:
            if revision(connection) != "0011":
                raise RuntimeError("Rejected downgrade changed the active migration revision")
        with database.get_session() as session:
            session.delete(session.get(DomainEvent, event.id))
            session.commit()

        migrate("downgrade", "0010")
        with database.engine.connect() as connection:
            if revision(connection) != "0010":
                raise RuntimeError("R5 downgrade did not restore 0010")
        migrate("upgrade", "0011")
        with database.engine.connect() as connection:
            if revision(connection) != "0011":
                raise RuntimeError("R5 re-upgrade did not return to 0011")
    finally:
        database.close()
    print("R5 0011 migration paths: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
