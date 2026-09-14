"""Exercise R4 Task 2's 0009 upgrade, downgrade and re-upgrade safely."""
import os
from pathlib import Path
import subprocess
import sys

from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.core.database import Database

ROOT = Path(__file__).resolve().parents[1]


def assert_isolated(database_url: str) -> None:
    if os.getenv("GREENCITY_ISOLATED_MIGRATION_PATH_TESTS") != "1":
        raise RuntimeError("Migration-path tests require the isolated runner")
    target = make_url(database_url)
    if target.host not in {"127.0.0.1", "localhost"} or target.username != "test_migrator":
        raise RuntimeError("Migration-path tests refuse a non-isolated database")


def migrate(command: str, revision: str) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "scripts.migrate", command, revision], cwd=ROOT,
        env=os.environ.copy(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    if result.returncode:
        output = (result.stdout or "").replace(os.environ.get("DATABASE_URL", ""), "[REDACTED]")
        raise RuntimeError(f"Migration {command} {revision} failed: {output.strip()}")


def revision(connection) -> str:
    value = connection.scalar(text("SELECT version_num FROM greencity.alembic_version"))
    if not isinstance(value, str):
        raise RuntimeError("Alembic revision is unavailable")
    return value


def columns(connection, table_name: str) -> set[str]:
    return set(connection.scalars(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'greencity' AND table_name = :table_name
    """), {"table_name": table_name}))


def trigger_names(connection) -> set[str]:
    return set(connection.scalars(text("""
        SELECT tgname FROM pg_trigger
        JOIN pg_class ON pg_class.oid = pg_trigger.tgrelid
        JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
        WHERE pg_namespace.nspname = 'greencity' AND NOT tgisinternal
    """)))


def main() -> int:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("Migration-path tests require a temporary database")
    assert_isolated(database_url)
    database = Database(Settings())
    try:
        migrate("upgrade", "0008")
        with database.engine.connect() as connection:
            if revision(connection) != "0008":
                raise RuntimeError("Expected 0008 before Task 2 upgrade")

        migrate("upgrade", "0009")
        with database.engine.connect() as connection:
            required = {
                "billing_runs": {"cutoff_at", "retry_count", "failure_code", "failure_detail", "failed_at", "completed_at"},
                "accounting_periods": {"cutoff_at"},
                "billing_invoice_items": {"basis", "basis_quantity", "unit_rate_vnd_snapshot", "rounding_unit_vnd_snapshot", "source_pending_charge_id"},
                "billing_invoices": {"voided_at", "voided_by_id", "void_reason"},
            }
            if revision(connection) != "0009" or any(not expected.issubset(columns(connection, table))
                                                   for table, expected in required.items()):
                raise RuntimeError("R4 Task 2 upgrade did not create all snapshot and retry fields")
            if not {"trg_billing_invoice_items_immutable", "trg_billing_invoices_snapshot_immutable"}.issubset(trigger_names(connection)):
                raise RuntimeError("R4 invoice snapshot immutability trigger is missing")

        migrate("downgrade", "0008")
        with database.engine.connect() as connection:
            if revision(connection) != "0008" or {"cutoff_at", "retry_count"} & columns(connection, "billing_runs"):
                raise RuntimeError("R4 Task 2 downgrade did not restore 0008")

        migrate("upgrade", "0009")
        with database.engine.connect() as connection:
            if revision(connection) != "0009":
                raise RuntimeError("R4 Task 2 re-upgrade did not return to revision 0009")
    finally:
        database.close()
    print("R4 0009 migration paths: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
