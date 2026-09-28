"""Rehearse the submission import manifest/reference migration on an isolated DB."""

import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

from sqlalchemy import inspect, select, text
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.core.database import Database
from app.models.submission_import import SubmissionExternalReference
from app.models.tenant import Tenant
from app.services.submission_data_import import (
    canonical_payload_sha256,
    manifest_summary,
    start_import_run,
    upsert_external_reference,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "greencity"


def _assert_isolated(database_url: str) -> None:
    target = make_url(database_url)
    if (
        os.getenv("GREENCITY_ISOLATED_MIGRATION_PATH_TESTS") != "1"
        or target.host not in {"127.0.0.1", "localhost"}
        or target.username != "test_migrator"
    ):
        raise RuntimeError("Submission import migration tests require the isolated runner")


def _migrate(command: str, revision: str, *, expect_success: bool = True) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "scripts.migrate", command, revision],
        cwd=ROOT, env=os.environ.copy(), stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    if (result.returncode == 0) != expect_success:
        raise RuntimeError(f"Submission import migration {command} failed (exit {result.returncode})")


def main() -> int:
    raw = os.getenv("DATABASE_URL")
    if not raw:
        raise RuntimeError("Submission import migration tests require a temporary database")
    _assert_isolated(raw)
    database = Database(Settings())
    manifest = manifest_summary({
        "schema_version": "fcs05-r2",
        "workbooks": [
            {"file_name": f"{index:02d}.xlsx", "sha256": str(index).zfill(64), "row_count": index}
            for index in range(1, 13)
        ],
    })
    try:
        _migrate("upgrade", "0018")
        with database.engine.connect() as connection:
            inspector = inspect(connection)
            tenant_columns = {item["name"] for item in inspector.get_columns("tenants", schema=SCHEMA)}
            run_columns = {item["name"] for item in inspector.get_columns("submission_import_runs", schema=SCHEMA)}
            reference_columns = {item["name"] for item in inspector.get_columns("submission_external_references", schema=SCHEMA)}
            if "code" not in tenant_columns or not {"manifest_sha256", "stage", "correlation_id"}.issubset(run_columns):
                raise RuntimeError("Submission import run schema is incomplete")
            if not {"source", "entity_type", "source_key", "target_id", "payload_sha256"}.issubset(reference_columns):
                raise RuntimeError("Submission external reference schema is incomplete")
        with database.get_session() as session:
            tenant = Tenant(code=f"MIG-{uuid4().hex[:10].upper()}", name="Migration fixture")
            session.add(tenant)
            session.flush()
            run_result = start_import_run(session, manifest, stage="master")
            reference, replayed = upsert_external_reference(
                session, run_result.run, tenant_id=tenant.id, source="unit", entity_type="Unit",
                source_key="SITE:BUILDING:UNIT-001", target_id=uuid4(), payload={"unit_number": "UNIT-001"},
            )
            session.commit()
            if replayed or reference.payload_sha256 != canonical_payload_sha256({"unit_number": "UNIT-001"}):
                raise RuntimeError("Submission external reference insert failed")
        _migrate("downgrade", "0017", expect_success=False)
        with database.get_session() as session:
            session.execute(text("DELETE FROM greencity.submission_external_references"))
            session.execute(text("DELETE FROM greencity.submission_import_runs"))
            session.execute(text("DELETE FROM greencity.tenants WHERE code LIKE 'MIG-%'"))
            session.commit()
        _migrate("downgrade", "0017")
        _migrate("upgrade", "0018")
        print("Submission import migration paths: PASS")
        return 0
    finally:
        database.close()


if __name__ == "__main__":
    raise SystemExit(main())
