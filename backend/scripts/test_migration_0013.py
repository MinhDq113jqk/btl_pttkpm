"""Exercise resident-request evidence migration upgrade and safe downgrade paths."""
import os
from datetime import UTC, datetime
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.core.database import Database
from app.core.security import hash_password
from app.models.account import Account
from app.models.building import Building
from app.models.service import ServiceCategory, ServiceRequest
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
        migrate("upgrade", "0012")
        migrate("upgrade", "0013")
        with database.engine.connect() as connection:
            inspector = inspect(connection)
            columns = {
                column["name"]: column["nullable"]
                for column in inspector.get_columns("attachments", schema=SCHEMA)
            }
            foreign_keys = {foreign_key["name"] for foreign_key in inspector.get_foreign_keys(
                "attachments", schema=SCHEMA,
            )}
            checks = {check["name"] for check in inspector.get_check_constraints("attachments", schema=SCHEMA)}
            indexes = {index["name"] for index in inspector.get_indexes("attachments", schema=SCHEMA)}
            if revision(connection) != "0013" or columns.get("service_request_id") is not True:
                raise RuntimeError("Resident evidence column is missing after 0013 upgrade")
            if columns.get("work_order_id") is not True:
                raise RuntimeError("0013 did not make the Work Order parent optional")
            if "fk_attachments_service_request_id_service_requests" not in foreign_keys:
                raise RuntimeError("Resident evidence foreign key is missing")
            if "ck_attachments_attachments_one_parent" not in checks:
                raise RuntimeError("Attachment parent consistency constraint is missing")
            if "ix_attachments_service_request_created" not in indexes:
                raise RuntimeError("Resident evidence lookup index is missing")

        with database.get_session() as session:
            tenant = Tenant(name=f"0013 resident evidence {uuid4()}")
            session.add(tenant)
            session.flush()
            site = Site(tenant_id=tenant.id, code=f"R6-{uuid4().hex[:8]}",
                        name="Resident migration", address="Synthetic")
            session.add(site)
            session.flush()
            building = Building(site_id=site.id, code="B1", name="Resident migration")
            session.add(building)
            session.flush()
            unit = Unit(building_id=building.id, unit_number="R6-0101", floor=1,
                        area_m2=50, status="occupied")
            account = Account(tenant_id=tenant.id, username=f"resident_{uuid4().hex}",
                              full_name="Migration resident", hashed_password=hash_password("migration-only"))
            category = ServiceCategory(tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                                       code="R6", name="Resident evidence", sla_minutes=60)
            session.add_all((unit, account, category))
            session.flush()
            service_request = ServiceRequest(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id, unit_id=unit.id,
                category_id=category.id, code=f"SR-{uuid4().hex[:12].upper()}",
                title="Resident migration request", description="Synthetic migration evidence",
                priority="MEDIUM", status="NEW", sla_started_at=datetime.now(UTC), sla_duration_minutes=60,
                owner_account_id=account.id, created_by_id=account.id, updated_by_id=account.id,
            )
            session.add(service_request)
            session.flush()
            # Keep this migration-path test runnable at revision 0013. The
            # current ORM model has later 0015 parcel_id metadata, so use a
            # revision-local INSERT rather than asking SQLAlchemy to select a
            # column that does not exist yet.
            attachment_id = uuid4()
            session.execute(text(
                """INSERT INTO greencity.attachments
                   (id, tenant_id, site_id, building_id, work_order_id,
                    service_request_id, uploaded_by_id, original_name,
                    storage_key, mime_type, size_bytes, sha256,
                    is_quarantined, version)
                   VALUES (:id, :tenant_id, :site_id, :building_id, NULL,
                           :service_request_id, :uploaded_by_id, :original_name,
                           :storage_key, :mime_type, :size_bytes, :sha256,
                           FALSE, 1)"""
            ), {
                "id": attachment_id, "tenant_id": tenant.id, "site_id": site.id,
                "building_id": building.id, "service_request_id": service_request.id,
                "uploaded_by_id": account.id, "original_name": "migration.png",
                "storage_key": f"migration/{uuid4().hex}.png", "mime_type": "image/png",
                "size_bytes": 1, "sha256": "0" * 64,
            })
            session.commit()

        migrate("downgrade", "0012", expect_success=False)
        with database.engine.connect() as connection:
            if revision(connection) != "0013":
                raise RuntimeError("Rejected resident evidence downgrade changed the active revision")
        with database.get_session() as session:
            session.execute(text("DELETE FROM greencity.attachments WHERE id = :id"), {"id": attachment_id})
            session.commit()
        migrate("downgrade", "0012")
        with database.engine.connect() as connection:
            if revision(connection) != "0012":
                raise RuntimeError("Resident evidence downgrade did not restore 0012")
        migrate("upgrade", "0013")
        with database.engine.connect() as connection:
            if revision(connection) != "0013":
                raise RuntimeError("Resident evidence re-upgrade did not return to 0013")
    finally:
        database.close()
    print("R6 0013 resident request evidence migration paths: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
