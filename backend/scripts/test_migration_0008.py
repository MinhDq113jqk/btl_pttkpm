"""Exercise R4's 0008 upgrade, downgrade and re-upgrade on a disposable DB."""
import os
from pathlib import Path
import subprocess
import sys

from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.core.database import Database

ROOT = Path(__file__).resolve().parents[1]
R4_TABLES = {
    "billing_accounts", "billing_fee_policies", "billing_fee_policy_versions",
    "accounting_periods", "billing_runs", "billing_invoices", "billing_invoice_items",
    "payments", "payment_allocations", "unmatched_payments", "overpayment_credits",
    "ar_ledger_entries",
}


def assert_isolated(database_url: str) -> None:
    if os.getenv("GREENCITY_ISOLATED_MIGRATION_PATH_TESTS") != "1":
        raise RuntimeError("Migration-path tests require the isolated runner")
    target = make_url(database_url)
    if target.host not in {"127.0.0.1", "localhost"} or target.username != "test_migrator":
        raise RuntimeError("Migration-path tests refuse a non-isolated database")


def migrate(command: str, revision: str) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "scripts.migrate", command, revision],
        cwd=ROOT,
        env=os.environ.copy(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    if result.returncode:
        output = (result.stdout or "").replace(os.environ.get("DATABASE_URL", ""), "[REDACTED]")
        raise RuntimeError(f"Migration {command} {revision} failed: {output.strip()}")


def table_names(connection) -> set[str]:
    return set(connection.scalars(text("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'greencity'
    """)))


def revision(connection) -> str:
    value = connection.scalar(text("SELECT version_num FROM greencity.alembic_version"))
    if not isinstance(value, str):
        raise RuntimeError("Alembic revision is unavailable")
    return value


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
        migrate("upgrade", "0007")
        with database.engine.connect() as connection:
            if revision(connection) != "0007":
                raise RuntimeError("Expected 0007 before R4 upgrade")

        migrate("upgrade", "0008")
        with database.engine.connect() as connection:
            if revision(connection) != "0008" or not R4_TABLES.issubset(table_names(connection)):
                raise RuntimeError("R4 upgrade did not create its complete schema")
            constraints = set(connection.scalars(text("""
                SELECT constraint_name FROM information_schema.table_constraints
                WHERE table_schema = 'greencity'
            """)))
            expected_constraints = {
                "uq_billing_runs_period_policy",
                "uq_payments_source_reference",
                "uq_payments_receipt_number",
                "uq_ar_ledger_entries_source_type",
                "ck_ar_ledger_entries_ar_ledger_entries_one_sided",
            }
            if not expected_constraints.issubset(constraints):
                raise RuntimeError("R4 idempotency and ledger constraints are missing")
            triggers = trigger_names(connection)
            if not {
                "trg_audit_events_append_only",
                "trg_ar_ledger_entries_append_only",
                "trg_payment_allocations_cap",
            }.issubset(triggers):
                raise RuntimeError("R4 financial integrity trigger is missing")

        migrate("downgrade", "0007")
        with database.engine.connect() as connection:
            if revision(connection) != "0007" or R4_TABLES & table_names(connection):
                raise RuntimeError("R4 downgrade did not restore the 0007 schema")
            triggers = trigger_names(connection)
            if ({"trg_ar_ledger_entries_append_only", "trg_payment_allocations_cap"} & triggers
                    or "trg_audit_events_append_only" not in triggers):
                raise RuntimeError("R4 downgrade changed the pre-existing audit immutability guard")

        migrate("upgrade", "0008")
        with database.engine.connect() as connection:
            if revision(connection) != "0008":
                raise RuntimeError("R4 re-upgrade did not return to revision 0008")
    finally:
        database.close()
    print("R4 0008 migration paths: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
