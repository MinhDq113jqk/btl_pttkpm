"""Exercise the parcel Case/Incident/evidence migration and safe downgrade."""
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
from app.models.operations import SecurityIncident
from app.models.parcel import Parcel
from app.models.platform import Attachment
from app.models.service import CaseRecord
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
        migrate("upgrade", "0015")
        with database.engine.connect() as connection:
            inspector = inspect(connection)
            case_columns = {item["name"] for item in inspector.get_columns("cases", schema=SCHEMA)}
            incident_columns = {item["name"] for item in inspector.get_columns("security_incidents", schema=SCHEMA)}
            attachment_columns = {item["name"] for item in inspector.get_columns("attachments", schema=SCHEMA)}
            if revision(connection) != "0015":
                raise RuntimeError("Parcel linkage migration did not advance to 0015")
            if ("source_parcel_id" not in case_columns
                    or "parcel_id" not in incident_columns
                    or "parcel_id" not in attachment_columns):
                raise RuntimeError("Parcel linkage columns are incomplete")
            case_checks = {item["name"] for item in inspector.get_check_constraints("cases", schema=SCHEMA)}
            attachment_checks = {item["name"] for item in inspector.get_check_constraints("attachments", schema=SCHEMA)}
            if "ck_cases_cases_one_source" not in case_checks:
                raise RuntimeError("Case one-source invariant is missing")
            if "ck_attachments_attachments_one_parent" not in attachment_checks:
                raise RuntimeError("Attachment parent invariant is missing")

        with database.get_session() as session:
            tenant = Tenant(name=f"0015 parcel linkage {uuid4()}")
            session.add(tenant)
            session.flush()
            site = Site(tenant_id=tenant.id, code=f"P-{uuid4().hex[:8]}", name="Parcel linkage", address="Synthetic")
            session.add(site)
            session.flush()
            building = Building(site_id=site.id, code="B1", name="Parcel linkage")
            session.add(building)
            session.flush()
            unit = Unit(building_id=building.id, unit_number="P-0101", floor=1, area_m2=50, status="occupied")
            account = Account(tenant_id=tenant.id, username=f"parcel_{uuid4().hex}",
                              full_name="Parcel operator", hashed_password=hash_password("migration-only"))
            session.add_all((unit, account))
            session.flush()
            parcel = Parcel(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id, unit_id=unit.id,
                parcel_code="P-001", recipient_name_snapshot="Parcel recipient", pin_hash="a" * 60,
                received_at=datetime.now(UTC), created_by_id=account.id, updated_by_id=account.id,
            )
            session.add(parcel)
            session.flush()
            case_record = CaseRecord(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                source_parcel_id=parcel.id, reason="Migration evidence", created_by_id=account.id,
                updated_by_id=account.id,
            )
            incident = SecurityIncident(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id, parcel_id=parcel.id,
                code="INC-0015", incident_type="SECURITY", severity="LOW", title="Parcel evidence",
                description="Migration evidence", occurred_at=datetime.now(UTC),
                reported_by_id=account.id, created_by_id=account.id, updated_by_id=account.id,
            )
            attachment = Attachment(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id, parcel_id=parcel.id,
                uploaded_by_id=account.id, original_name="evidence.png", storage_key=f"0015/{uuid4().hex}.png",
                mime_type="image/png", size_bytes=8, sha256="a" * 64,
            )
            session.add_all((case_record, incident, attachment))
            session.commit()
            case_id, incident_id, attachment_id, parcel_id = case_record.id, incident.id, attachment.id, parcel.id

            invalid = CaseRecord(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                source_parcel_id=parcel.id, source_work_order_id=uuid4(), reason="invalid",
                created_by_id=account.id, updated_by_id=account.id,
            )
            session.add(invalid)
            try:
                session.flush()
            except IntegrityError:
                session.rollback()
            else:
                raise RuntimeError("Case source one-of invariant was not enforced")

        migrate("downgrade", "0014", expect_success=False)
        with database.engine.connect() as connection:
            if revision(connection) != "0015":
                raise RuntimeError("Rejected 0015 downgrade changed the active revision")
        with database.get_session() as session:
            session.query(Attachment).filter(Attachment.id == attachment_id).delete()
            session.query(SecurityIncident).filter(SecurityIncident.id == incident_id).delete()
            session.query(CaseRecord).filter(CaseRecord.id == case_id).delete()
            session.query(Parcel).filter(Parcel.id == parcel_id).delete()
            session.commit()
        migrate("downgrade", "0014")
        with database.engine.connect() as connection:
            if revision(connection) != "0014":
                raise RuntimeError("0015 downgrade did not restore 0014")
        migrate("upgrade", "0015")
        with database.engine.connect() as connection:
            if revision(connection) != "0015":
                raise RuntimeError("0015 re-upgrade did not return to 0015")
    finally:
        database.close()
    print("V1 0015 parcel case/evidence migration paths: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
