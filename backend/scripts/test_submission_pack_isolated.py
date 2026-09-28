"""Rehearse the synthetic submission pack in a fresh database of the test cluster.

Only scripts.test_isolated may invoke this module.  It creates a second database
inside that runner's disposable loopback PostgreSQL cluster, leaving the main
regression database untouched.  No source rows, credentials or connection URI
are printed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import traceback

from sqlalchemy import create_engine, text

from app.core.config import Settings
from app.services.submission_data_reader import read_submission_pack
from scripts.load_submission_data import _rows, apply, dry_run, verify


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "tests" / "fixtures" / "submission_data" / "synthetic"
MANIFEST = ROOT / "tests" / "fixtures" / "submission_data" / "synthetic_manifest.json"
EVIDENCE = ROOT / "tests" / "fixtures" / "submission_data" / "synthetic_evidence"
TEST_DATABASE = "greencity_submission_rehearsal"


def main() -> int:
    settings = Settings()
    url = settings.sqlalchemy_url()
    if (
        os.getenv("GREENCITY_ISOLATED_SECURITY_TESTS") != "1"
        or settings.app_env != "test"
        or url.host != "127.0.0.1"
        or url.database != "postgres"
        or not settings.database_ssl_root_cert
    ):
        print("SUBMISSION_REHEARSAL=FAIL code=ISOLATED_CLUSTER_REQUIRED")
        return 1
    if not PACK.is_dir() or not EVIDENCE.is_dir():
        print("SUBMISSION_REHEARSAL=FAIL code=SYNTHETIC_FIXTURE_MISSING")
        return 1
    engine = create_engine(url, isolation_level="AUTOCOMMIT", hide_parameters=True)
    try:
        with engine.connect() as connection:
            connection.execute(text(f"CREATE DATABASE {TEST_DATABASE}"))
    except Exception:
        print("SUBMISSION_REHEARSAL=FAIL code=TEST_DATABASE_CREATE_FAILED")
        return 1
    finally:
        engine.dispose()

    os.environ["DATABASE_URL"] = url.set(database=TEST_DATABASE).render_as_string(hide_password=False)
    os.environ["GREENCITY_SUBMISSION_EVIDENCE_DIR"] = str(EVIDENCE)
    os.environ["GREENCITY_SUBMISSION_PIN_SECRET"] = secrets.token_urlsafe(32)
    credential_file = Path(settings.private_storage_path).parent / "submission-rehearsal-credentials.json"
    try:
        credential_file.parent.mkdir(parents=True, exist_ok=True)
        pack = read_submission_pack(PACK)
        credentials = {
            str(row["username"]): secrets.token_urlsafe(32)
            for row in _rows(pack, "02_danh_sach_nhan_vien.xlsx")
        }
        credential_file.write_text(json.dumps(credentials), encoding="utf-8")
        os.environ["GREENCITY_SUBMISSION_CREDENTIALS_FILE"] = str(credential_file)
        migration = subprocess.run(
            [sys.executable, "-m", "scripts.migrate", "upgrade", "head"],
            cwd=ROOT, env=os.environ.copy(), stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=120, check=False,
        )
        if migration.returncode:
            raise RuntimeError("MIGRATION_FAILED")
        preview = dry_run(PACK, stage="all", manifest_path=MANIFEST)
        if preview["rows"] != 101 or preview["database_write"]:
            raise RuntimeError("DRY_RUN_MISMATCH")
        first = apply(PACK, stage="all", manifest_path=MANIFEST)
        if first["status"] != "PASS" or not first["database_write"]:
            raise RuntimeError("APPLY_MISMATCH")
        checked = verify(PACK, stage="all", manifest_path=MANIFEST)
        if checked["status"] != "PASS" or checked["database_write"]:
            raise RuntimeError("VERIFY_MISMATCH")
        second = apply(PACK, stage="all", manifest_path=MANIFEST)
        if second["status"] != "REPLAY" or second["database_write"]:
            raise RuntimeError("RETRY_MISMATCH")
        print("SUBMISSION_REHEARSAL=PASS stage=all workbooks=12 rows=101 dry_run=PASS apply=PASS verify=PASS retry=PASS")
        return 0
    except Exception as exc:
        code = str(exc) if isinstance(exc, RuntimeError) and str(exc) in {
            "MIGRATION_FAILED", "DRY_RUN_MISMATCH", "APPLY_MISMATCH",
            "VERIFY_MISMATCH", "RETRY_MISMATCH",
        } else getattr(exc, "code", "REHEARSAL_FAILED")
        cause = exc.__cause__
        diagnostic = ""
        if cause is not None and cause.__traceback__ is not None:
            frame = traceback.extract_tb(cause.__traceback__)[-1]
            diagnostic = f" cause_type={type(cause).__name__} origin={Path(frame.filename).name}:{frame.lineno}"
            if type(cause).__name__ == "NormalizationError":
                diagnostic += f" cause_code={cause.code} cause_field={cause.field}"
        print(f"SUBMISSION_REHEARSAL=FAIL code={code}{diagnostic}")
        return 1
    finally:
        credential_file.unlink(missing_ok=True)
        os.environ.pop("GREENCITY_SUBMISSION_CREDENTIALS_FILE", None)
        os.environ.pop("GREENCITY_SUBMISSION_PIN_SECRET", None)


if __name__ == "__main__":
    raise SystemExit(main())
