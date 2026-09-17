"""Exercise the V1 parcel foundation migration and its fail-closed downgrade."""
import os
from datetime import UTC, datetime
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.core.database import Database
from app.core.security import hash_password
from app.models.account import Account
from app.models.building import Building
from app.models.enums import ParcelStatusEnum
from app.models.parcel import Parcel
from app.models.person import Person
from app.models.site import Site
from app.models.tenant import Tenant
from app.models.unit import Unit

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "greencity"


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
    succeeded = result.returncode == 0
    if succeeded != expect_success:
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
        migrate("upgrade", "0014")
        with database.engine.connect() as connection:
            inspector = inspect(connection)
            columns = {column["name"]: column["nullable"]
                       for column in inspector.get_columns("parcels", schema=SCHEMA)}
            foreign_keys = {foreign_key["name"]
                            for foreign_key in inspector.get_foreign_keys("parcels", schema=SCHEMA)}
            checks = {check["name"]
                      for check in inspector.get_check_constraints("parcels", schema=SCHEMA)}
            indexes = {index["name"] for index in inspector.get_indexes("parcels", schema=SCHEMA)}
            if revision(connection) != "0014":
                raise RuntimeError("Parcel migration did not advance to 0014")
            required_columns = {
                "tenant_id", "site_id", "building_id", "unit_id", "recipient_person_id",
                "parcel_code", "recipient_name_snapshot", "pin_hash", "pin_attempt_count",
                "status", "received_at", "handed_over_at", "handed_over_by_id",
                "exception_reason", "created_by_id", "updated_by_id", "version",
            }
            if not required_columns.issubset(columns) or columns["pin_hash"] is not False:
                raise RuntimeError("Parcel columns are incomplete or PIN hash is nullable")
            if not {
                "fk_parcels_tenant_id_tenants", "fk_parcels_site_tenant",
                "fk_parcels_building_site", "fk_parcels_unit_building",
                "fk_parcels_recipient_person_tenant", "fk_parcels_created_by_tenant",
                "fk_parcels_updated_by_tenant", "fk_parcels_handed_over_by_tenant",
            }.issubset(foreign_keys):
                raise RuntimeError("Parcel scope/account foreign keys are incomplete")
            if not {
                "ck_parcels_parcel_code_not_blank",
                "ck_parcels_recipient_name_snapshot_not_blank",
                "ck_parcels_pin_hash_min_length",
                "ck_parcels_pin_attempts_range",
                "ck_parcels_version_positive",
                "ck_parcels_status_allowed",
                "ck_parcels_exception_reason_required",
                "ck_parcels_handover_fields_semantics",
            }.issubset(checks):
                raise RuntimeError("Parcel state and input checks are incomplete")
            if not {
                "ix_parcels_scope_status",
                "ix_parcels_unit_status_received",
                "ix_parcels_recipient_status",
            }.issubset(indexes):
                raise RuntimeError("Parcel lookup indexes are incomplete")

        with database.get_session() as session:
            tenant = Tenant(name=f"0014 parcel {uuid4()}")
            foreign_tenant = Tenant(name=f"0014 foreign parcel {uuid4()}")
            session.add_all((tenant, foreign_tenant))
            session.flush()
            site = Site(tenant_id=tenant.id, code=f"P-{uuid4().hex[:8]}",
                        name="Parcel migration", address="Synthetic")
            foreign_site = Site(tenant_id=foreign_tenant.id, code=f"FP-{uuid4().hex[:8]}",
                                name="Foreign parcel migration", address="Synthetic")
            session.add_all((site, foreign_site))
            session.flush()
            building = Building(site_id=site.id, code="B1", name="Parcel migration")
            foreign_building = Building(site_id=foreign_site.id, code="B1", name="Foreign parcel migration")
            session.add_all((building, foreign_building))
            session.flush()
            unit = Unit(building_id=building.id, unit_number="P-0101", floor=1,
                        area_m2=50, status="occupied")
            foreign_unit = Unit(building_id=foreign_building.id, unit_number="P-0101", floor=1,
                                area_m2=50, status="occupied")
            person = Person(tenant_id=tenant.id, full_name="Parcel recipient",
                            phone_masked="***", email_masked="***@example.invalid")
            foreign_person = Person(tenant_id=foreign_tenant.id, full_name="Foreign recipient",
                                    phone_masked="***", email_masked="***@example.invalid")
            account = Account(tenant_id=tenant.id, username=f"parcel_{uuid4().hex}",
                              full_name="Parcel operator", hashed_password=hash_password("migration-only"))
            foreign_account = Account(tenant_id=foreign_tenant.id, username=f"foreign_{uuid4().hex}",
                                      full_name="Foreign operator", hashed_password=hash_password("migration-only"))
            session.add_all((unit, foreign_unit, person, foreign_person, account, foreign_account))
            session.flush()
            valid = Parcel(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id, unit_id=unit.id,
                recipient_person_id=person.id, parcel_code="P-001",
                recipient_name_snapshot="Parcel recipient", recipient_contact_snapshot="***",
                pin_hash="a" * 60, status=ParcelStatusEnum.RECEIVED.value,
                received_at=datetime.now(UTC), created_by_id=account.id, updated_by_id=account.id,
            )
            session.add(valid)
            session.commit()
            parcel_id = valid.id

            def assert_rejected(candidate: Parcel, message: str) -> None:
                session.add(candidate)
                try:
                    session.flush()
                except IntegrityError:
                    session.rollback()
                else:
                    session.rollback()
                    raise RuntimeError(message)

            def candidate(**overrides) -> Parcel:
                values = dict(
                    tenant_id=tenant.id, site_id=site.id, building_id=building.id, unit_id=unit.id,
                    recipient_person_id=person.id, parcel_code=f"P-{uuid4().hex[:12]}",
                    recipient_name_snapshot="Parcel recipient", pin_hash="a" * 60,
                    status=ParcelStatusEnum.RECEIVED.value, received_at=datetime.now(UTC),
                    created_by_id=account.id, updated_by_id=account.id,
                )
                values.update(overrides)
                return Parcel(**values)

            assert_rejected(candidate(status="NOT_A_STATUS"), "0014 allowed an unknown parcel status")
            assert_rejected(candidate(pin_hash="short"), "0014 allowed a short/plain PIN representation")
            assert_rejected(candidate(pin_attempt_count=11), "0014 allowed excessive PIN attempts")
            assert_rejected(candidate(status=ParcelStatusEnum.LOST.value),
                            "0014 allowed LOST without an exception reason")
            assert_rejected(candidate(status=ParcelStatusEnum.HANDED_OVER.value),
                            "0014 allowed HANDED_OVER without handover fields")
            assert_rejected(candidate(recipient_person_id=foreign_person.id),
                            "0014 allowed a recipient from another tenant")
            assert_rejected(candidate(created_by_id=foreign_account.id),
                            "0014 allowed an actor from another tenant")
            assert_rejected(candidate(parcel_code="P-001"),
                            "0014 allowed duplicate parcel code inside a site")

        migrate("downgrade", "0013", expect_success=False)
        with database.engine.connect() as connection:
            if revision(connection) != "0014":
                raise RuntimeError("Rejected parcel downgrade changed the active revision")
        with database.get_session() as session:
            parcel = session.get(Parcel, parcel_id)
            if parcel is None:
                raise RuntimeError("Parcel fixture disappeared before downgrade check")
            session.delete(parcel)
            session.commit()
        migrate("downgrade", "0013")
        with database.engine.connect() as connection:
            if revision(connection) != "0013":
                raise RuntimeError("Parcel downgrade did not restore 0013")
        migrate("upgrade", "0014")
        with database.engine.connect() as connection:
            if revision(connection) != "0014":
                raise RuntimeError("Parcel re-upgrade did not return to 0014")
    finally:
        database.close()
    print("V1 0014 parcel foundation migration paths: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
