"""Exercise R3's 0007 upgrade, downgrade and re-upgrade on a disposable DB."""
import os
from pathlib import Path
import subprocess
import sys

from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.core.database import Database

ROOT = Path(__file__).resolve().parents[1]
R3_TABLES = {
    "cleaning_routes", "cleaning_areas", "cleaning_route_stops", "cleaning_shifts",
    "cleaning_tasks", "cleaning_checklist_results", "security_shifts",
    "security_shift_handoffs", "security_visitor_logs", "patrol_points", "patrol_windows", "patrol_logs",
    "security_incidents", "incident_escalations",
    "incident_escalation_acknowledgements", "security_incident_evidence",
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


def main() -> int:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("Migration-path tests require a temporary database")
    assert_isolated(database_url)
    database = Database(Settings())
    try:
        migrate("upgrade", "0006")
        with database.engine.connect() as connection:
            if revision(connection) != "0006":
                raise RuntimeError("Expected 0006 before R3 upgrade")

        migrate("upgrade", "0007")
        with database.engine.connect() as connection:
            if revision(connection) != "0007" or not R3_TABLES.issubset(table_names(connection)):
                raise RuntimeError("R3 upgrade did not create its complete schema")
            checks = set(connection.scalars(text("""
                SELECT constraint_name FROM information_schema.table_constraints
                WHERE table_schema = 'greencity' AND constraint_type = 'CHECK'
            """)))
            expected_checks = {
                "ck_cleaning_tasks_cleaning_tasks_status",
                "ck_patrol_windows_patrol_windows_status",
                "ck_patrol_windows_patrol_windows_missed_reason",
                "ck_security_incidents_security_incidents_severity",
                "ck_security_incidents_security_incidents_status",
            }
            if not expected_checks.issubset(checks):
                raise RuntimeError("R3 state constraints do not match the model contract")
            work_order_columns = set(connection.scalars(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'greencity' AND table_name = 'work_orders'
            """)))
            if "cleaning_task_id" not in work_order_columns:
                raise RuntimeError("WorkOrder does not support a CleaningTask source")
            triggers = set(connection.scalars(text("""
                SELECT tgname FROM pg_trigger
                JOIN pg_class ON pg_class.oid = pg_trigger.tgrelid
                JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
                WHERE pg_namespace.nspname = 'greencity' AND NOT tgisinternal
            """)))
            expected_triggers = {
                "trg_security_shift_handoffs_append_only",
                "trg_security_visitor_logs_append_only",
                "trg_patrol_logs_append_only",
                "trg_incident_escalations_append_only",
                "trg_incident_escalation_acknowledgements_append_only",
                "trg_security_incident_evidence_append_only",
            }
            if not expected_triggers.issubset(triggers):
                raise RuntimeError("R3 append-only timelines are not protected")

        migrate("downgrade", "0006")
        with database.engine.connect() as connection:
            if revision(connection) != "0006" or R3_TABLES & table_names(connection):
                raise RuntimeError("R3 downgrade did not restore the 0006 schema")
            work_order_columns = set(connection.scalars(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'greencity' AND table_name = 'work_orders'
            """)))
            if "cleaning_task_id" in work_order_columns:
                raise RuntimeError("R3 downgrade left WorkOrder's cleaning source behind")

        migrate("upgrade", "0007")
        with database.engine.connect() as connection:
            if revision(connection) != "0007":
                raise RuntimeError("R3 re-upgrade did not return to revision 0007")
    finally:
        database.close()
    print("R3 0007 migration paths: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
