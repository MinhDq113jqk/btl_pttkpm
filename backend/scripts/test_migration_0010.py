"""Exercise R4 payment-reconciliation migration paths on the disposable DB."""
import os
from pathlib import Path
import subprocess
import sys
from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.core.database import Database
from app.models.billing import AccountingPeriod, Payment, UnmatchedPayment
from app.models.building import Building
from app.models.site import Site
from app.models.tenant import Tenant

ROOT = Path(__file__).resolve().parents[1]


def assert_isolated(database_url: str) -> None:
    if os.getenv("GREENCITY_ISOLATED_MIGRATION_PATH_TESTS") != "1":
        raise RuntimeError("Migration-path tests require the isolated runner")
    target = make_url(database_url)
    if target.host not in {"127.0.0.1", "localhost"} or target.username != "test_migrator":
        raise RuntimeError("Migration-path tests refuse a non-isolated database")


def migrate(command: str, revision: str, *, expect_success: bool = True) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "scripts.migrate", command, revision], cwd=ROOT,
        env=os.environ.copy(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    if bool(result.returncode) != (not expect_success):
        output = (result.stdout or "").replace(os.environ.get("DATABASE_URL", ""), "[REDACTED]")
        raise RuntimeError(f"Migration {command} {revision} had an unexpected result: {output.strip()}")


def revision(connection) -> str:
    value = connection.scalar(text("SELECT version_num FROM greencity.alembic_version"))
    if not isinstance(value, str):
        raise RuntimeError("Alembic revision is unavailable")
    return value


def payment_account_nullable(connection) -> bool:
    return connection.scalar(text("""
        SELECT is_nullable = 'YES' FROM information_schema.columns
        WHERE table_schema = 'greencity' AND table_name = 'payments' AND column_name = 'billing_account_id'
    """)) is True


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
        migrate("upgrade", "0009")
        migrate("upgrade", "0010")
        with database.engine.connect() as connection:
            if revision(connection) != "0010" or not payment_account_nullable(connection):
                raise RuntimeError("R4 payment reconciliation did not allow unmatched payment rows")
            if "trg_payment_allocations_cap" not in trigger_names(connection):
                raise RuntimeError("R4 allocation-cap trigger is missing after 0010 upgrade")

        # Downgrade must fail closed instead of mutating or losing an unmatched
        # receipt that 0009 has no way to represent.
        with database.get_session() as session:
            tenant = Tenant(name=f"0010 downgrade guard {uuid4()}")
            session.add(tenant)
            session.flush()
            site = Site(tenant_id=tenant.id, code=f"M{uuid4().hex[:8]}", name="Migration guard", address="Synthetic")
            session.add(site)
            session.flush()
            building = Building(site_id=site.id, code="B1", name="Migration building")
            session.add(building)
            session.flush()
            period = AccountingPeriod(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id, period_key="M-0010",
                period_start=date(2030, 1, 1), period_end=date(2030, 1, 31), cutoff_at=datetime(2030, 1, 15, tzinfo=UTC),
            )
            session.add(period)
            session.flush()
            payment = Payment(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id, billing_account_id=None,
                accounting_period_id=period.id, payment_source="BANK_TRANSFER", source_reference=f"migrate-{uuid4().hex}",
                receipt_number=f"migrate-{uuid4().hex}", amount_vnd=1, received_at=datetime.now(UTC), status="UNMATCHED",
            )
            session.add(payment)
            session.flush()
            unmatched = UnmatchedPayment(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id, payment_id=payment.id,
                amount_vnd=1, reason="Migration downgrade guard",
            )
            session.add(unmatched)
            session.commit()
        migrate("downgrade", "0009", expect_success=False)
        with database.engine.connect() as connection:
            if revision(connection) != "0010":
                raise RuntimeError("Rejected downgrade changed the active migration revision")
        with database.get_session() as session:
            session.delete(session.get(UnmatchedPayment, unmatched.id))
            session.delete(session.get(Payment, payment.id))
            session.commit()

        migrate("downgrade", "0009")
        with database.engine.connect() as connection:
            if revision(connection) != "0009" or payment_account_nullable(connection):
                raise RuntimeError("R4 payment reconciliation downgrade did not restore 0009")

        migrate("upgrade", "0010")
        with database.engine.connect() as connection:
            if revision(connection) != "0010":
                raise RuntimeError("R4 payment reconciliation re-upgrade did not return to 0010")
    finally:
        database.close()
    print("R4 0010 migration paths: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
