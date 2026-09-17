"""Exercise resident-identity migration upgrade and fail-closed downgrade paths."""
import os
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
from app.models.person import Person
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
        migrate("upgrade", "0011")
        migrate("upgrade", "0012")
        with database.engine.connect() as connection:
            inspector = inspect(connection)
            columns = {column["name"] for column in inspector.get_columns("accounts", schema="greencity")}
            foreign_keys = {foreign_key["name"] for foreign_key in inspector.get_foreign_keys(
                "accounts", schema="greencity",
            )}
            if revision(connection) != "0012" or "person_id" not in columns:
                raise RuntimeError("Resident identity column is missing after 0012 upgrade")
            if "fk_accounts_person_tenant" not in foreign_keys:
                raise RuntimeError("Resident identity tenant constraint is missing after 0012 upgrade")

        with database.get_session() as session:
            tenant = Tenant(name=f"0012 resident identity {uuid4()}")
            foreign_tenant = Tenant(name=f"0012 resident foreign tenant {uuid4()}")
            session.add_all((tenant, foreign_tenant))
            session.flush()
            person = Person(tenant_id=tenant.id, full_name="Resident fixture",
                            phone_masked="***", email_masked="***@example.invalid")
            foreign_person = Person(tenant_id=foreign_tenant.id, full_name="Foreign fixture",
                                    phone_masked="***", email_masked="***@example.invalid")
            session.add_all((person, foreign_person))
            session.flush()
            account = Account(tenant_id=tenant.id, username=f"resident_{uuid4().hex}",
                              full_name="Resident fixture", hashed_password=hash_password("migration-only"),
                              person_id=person.id)
            session.add(account)
            session.commit()
            account_id, person_id, foreign_person_id = account.id, person.id, foreign_person.id

        with database.get_session() as session:
            account = session.get(Account, account_id)
            account.person_id = foreign_person_id
            try:
                session.flush()
            except IntegrityError:
                session.rollback()
            else:
                raise RuntimeError("0012 allowed an Account to link a foreign-tenant Person")

        with database.get_session() as session:
            duplicate = Account(tenant_id=session.get(Account, account_id).tenant_id,
                                username=f"duplicate_{uuid4().hex}", full_name="Duplicate fixture",
                                hashed_password=hash_password("migration-only"), person_id=person_id)
            session.add(duplicate)
            try:
                session.flush()
            except IntegrityError:
                session.rollback()
            else:
                raise RuntimeError("0012 allowed two accounts to map to one resident Person")

        migrate("downgrade", "0011", expect_success=False)
        with database.engine.connect() as connection:
            if revision(connection) != "0012":
                raise RuntimeError("Rejected resident-identity downgrade changed the active revision")
        with database.get_session() as session:
            session.get(Account, account_id).person_id = None
            session.commit()
        migrate("downgrade", "0011")
        with database.engine.connect() as connection:
            if revision(connection) != "0011":
                raise RuntimeError("Resident-identity downgrade did not restore 0011")
        migrate("upgrade", "0012")
        with database.engine.connect() as connection:
            if revision(connection) != "0012":
                raise RuntimeError("Resident-identity re-upgrade did not return to 0012")
    finally:
        database.close()
    print("R6 0012 resident identity migration paths: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
