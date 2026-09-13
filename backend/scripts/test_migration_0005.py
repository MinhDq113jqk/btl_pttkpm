"""Exercise AC-03's 0005 migration paths on the disposable PostgreSQL runner."""
from datetime import date, timedelta
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.core.database import Database


ROOT = Path(__file__).resolve().parents[1]
ISOLATED_FLAG = "GREENCITY_ISOLATED_MIGRATION_PATH_TESTS"


def require_isolated_target() -> None:
    if os.getenv(ISOLATED_FLAG) != "1":
        raise RuntimeError("Migration-path tests require the isolated runner")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("Migration-path tests require a temporary database")
    target = make_url(database_url)
    if target.host not in {"127.0.0.1", "localhost"} or target.username != "test_migrator":
        raise RuntimeError("Migration-path tests refuse a non-isolated database")


def migrate(command: str, revision: str, *, expect_failure: bool = False) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "scripts.migrate", command, revision],
        cwd=ROOT,
        env=os.environ.copy(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if (result.returncode != 0) != expect_failure:
        expectation = "fail" if expect_failure else "pass"
        raise RuntimeError(f"Migration {command} {revision} did not {expectation}")


def in_transaction(callback):
    database = Database(Settings())
    try:
        with database.engine.begin() as connection:
            return callback(connection)
    finally:
        database.close()


def scalar(statement: str, parameters: dict) -> object:
    return in_transaction(lambda connection: connection.scalar(text(statement), parameters))


def revision() -> str:
    value = scalar("SELECT version_num FROM greencity.alembic_version", {})
    if not isinstance(value, str):
        raise RuntimeError("Alembic revision is unavailable")
    return value


def main() -> int:
    require_isolated_target()
    ids = {name: uuid4() for name in (
        "tenant", "site", "building", "unit", "owner_one", "owner_two",
        "owner_one_relation", "owner_two_relation", "expired_relation", "future_relation",
    )}

    migrate("upgrade", "0004")

    def create_legacy_fixture(connection) -> None:
        connection.execute(text("""
            INSERT INTO greencity.tenants (id, name)
            VALUES (:tenant, 'AC-03 migration-path tenant')
        """), ids)
        connection.execute(text("""
            INSERT INTO greencity.sites (id, tenant_id, code, name, address)
            VALUES (:site, :tenant, 'AC03', 'AC-03 migration-path site', 'Synthetic')
        """), ids)
        connection.execute(text("""
            INSERT INTO greencity.buildings (id, site_id, code, name, floors_count)
            VALUES (:building, :site, 'AC03', 'AC-03 migration-path building', 1)
        """), ids)
        connection.execute(text("""
            INSERT INTO greencity.units (id, building_id, unit_number, floor, area_m2, status, version)
            VALUES (:unit, :building, 'AC03-0101', 1, 1.0, 'occupied', 1)
        """), ids)
        for owner in ("owner_one", "owner_two"):
            connection.execute(text("""
                INSERT INTO greencity.persons (id, tenant_id, full_name, phone_masked, email_masked)
                VALUES (:%s, :tenant, 'AC-03 migration-path person', '***', '***@example.invalid')
            """ % owner), ids)
        for relationship, owner in (
            ("owner_one_relation", "owner_one"),
            ("owner_two_relation", "owner_two"),
        ):
            connection.execute(text("""
                INSERT INTO greencity.unit_person_relationships
                    (id, unit_id, person_id, relationship_type, is_active)
                VALUES (:%s, :unit, :%s, 'owner', true)
            """ % (relationship, owner)), ids)

    in_transaction(create_legacy_fixture)

    # Two concurrently-effective legacy owners each become ratio 1.0000, so 0005
    # must reject instead of publishing a relationship set over the ownership cap.
    migrate("upgrade", "0005", expect_failure=True)
    if revision() != "0004":
        raise RuntimeError("Rejected 0005 upgrade changed the Alembic revision")
    columns = in_transaction(lambda connection: set(connection.scalars(text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'greencity' AND table_name = 'unit_person_relationships'
    """))))
    if {"ownership_ratio", "valid_from", "valid_to", "tenant_id", "site_id", "building_id"} & columns:
        raise RuntimeError("Rejected 0005 upgrade left partial relationship columns")

    in_transaction(lambda connection: connection.execute(text("""
        DELETE FROM greencity.unit_person_relationships WHERE id = :owner_two_relation
    """), ids))
    migrate("upgrade", "0005")

    # The ImportRun schema must be reversible on top of the hardened
    # Person--Unit schema.  Check the physical constraint names too: the ORM
    # naming convention is part of Alembic's schema-drift contract.
    migrate("upgrade", "0006")
    if revision() != "0006":
        raise RuntimeError("ImportRun upgrade did not publish revision 0006")
    import_tables = in_transaction(lambda connection: set(connection.scalars(text("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'greencity'
          AND table_name IN ('import_runs', 'import_run_rows')
    """))))
    if import_tables != {"import_runs", "import_run_rows"}:
        raise RuntimeError("ImportRun upgrade did not create both durable tables")
    check_names = in_transaction(lambda connection: set(connection.scalars(text("""
        SELECT constraint_name
        FROM information_schema.table_constraints
        WHERE table_schema = 'greencity'
          AND table_name IN ('import_runs', 'import_run_rows')
          AND constraint_type = 'CHECK'
    """))))
    expected_checks = {
        "ck_import_runs_mode_allowed",
        "ck_import_runs_status_allowed",
        "ck_import_runs_source_size_range",
        "ck_import_runs_counts_nonnegative",
        "ck_import_runs_version_positive",
        "ck_import_run_rows_row_number_positive",
        "ck_import_run_rows_status_allowed",
    }
    if not expected_checks.issubset(check_names):
        raise RuntimeError("ImportRun CHECK constraints do not match the model contract")
    migrate("downgrade", "0005")
    if revision() != "0005":
        raise RuntimeError("ImportRun downgrade did not return to revision 0005")
    remaining_import_tables = in_transaction(lambda connection: set(connection.scalars(text("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'greencity'
          AND table_name IN ('import_runs', 'import_run_rows')
    """))))
    if remaining_import_tables:
        raise RuntimeError("ImportRun downgrade left durable tables behind")

    today = date.today()

    def create_temporal_fixture(connection) -> None:
        connection.execute(text("""
            INSERT INTO greencity.unit_person_relationships
                (id, unit_id, person_id, relationship_type, ownership_ratio, valid_from, valid_to)
            VALUES (:expired_relation, :unit, :owner_two, 'family_member', NULL, :expired_from, :expired_to)
        """), {**ids, "expired_from": today - timedelta(days=10), "expired_to": today - timedelta(days=1)})
        connection.execute(text("""
            INSERT INTO greencity.unit_person_relationships
                (id, unit_id, person_id, relationship_type, ownership_ratio, valid_from, valid_to)
            VALUES (:future_relation, :unit, :owner_two, 'tenant', NULL, :future_from, NULL)
        """), {**ids, "future_from": today + timedelta(days=1)})

    in_transaction(create_temporal_fixture)
    migrate("downgrade", "0004")
    for relationship_id in (ids["expired_relation"], ids["future_relation"]):
        if scalar(
            "SELECT is_active FROM greencity.unit_person_relationships WHERE id = :id",
            {"id": relationship_id},
        ) is not False:
            raise RuntimeError("Downgrade 0005 to 0004 activated an expired or future relationship")

    in_transaction(lambda connection: connection.execute(text("""
        DELETE FROM greencity.tenants WHERE id = :tenant
    """), ids))
    migrate("downgrade", "base")
    print("AC-03 migration paths: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
