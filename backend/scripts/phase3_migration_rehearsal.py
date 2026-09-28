"""Run the Phase 3 migration policy on a fresh loopback PostgreSQL database."""

from __future__ import annotations

import os
import subprocess
import sys

import psycopg
from sqlalchemy.engine import make_url


def main() -> int:
    if os.getenv("PHASE3_MIGRATION_REHEARSAL") != "1":
        print("Set PHASE3_MIGRATION_REHEARSAL=1 for a disposable migration rehearsal.")
        return 2
    raw = os.getenv("DATABASE_URL", "")
    host = make_url(raw).host if raw else None
    if host not in {"127.0.0.1", "localhost", "::1"}:
        print("Migration rehearsal requires a loopback DATABASE_URL; no shared DB was used.")
        return 2

    env = dict(os.environ)
    command = [sys.executable, "-m", "scripts.migrate"]
    steps = [
        ("repeat upgrade", [*command, "upgrade", "head"]),
        ("drift check before rollback", [*command, "check"]),
        ("rollback to base", [*command, "downgrade", "base"]),
        ("re-upgrade", [*command, "upgrade", "head"]),
        ("drift check after re-upgrade", [*command, "check"]),
    ]
    try:
        for label, step in steps:
            print(f"Phase 3 migration step: {label}", flush=True)
            result = subprocess.run(step, cwd=os.path.dirname(os.path.dirname(__file__)), env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace", timeout=180)
            if result.returncode:
                if os.getenv("PHASE3_VERBOSE") == "1":
                    output = (result.stdout or "").replace(raw, "[REDACTED]")
                    print(output[-4000:])
                    if "drift check" in label:
                        with psycopg.connect(raw) as connection:
                            connection.execute("SET ROLE greencity_owner")
                            revisions = connection.execute(
                                "SELECT version_num FROM greencity.alembic_version ORDER BY version_num"
                            ).fetchall()
                        print(f"migration revision rows: {[row[0] for row in revisions]}")
                        heads = subprocess.run([*command, "heads"], cwd=os.path.dirname(os.path.dirname(__file__)),
                                               env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                               text=True, encoding="utf-8", errors="replace", timeout=60)
                        print((heads.stdout or "")[-1000:])
                raise RuntimeError("migration step failed")
        with psycopg.connect(raw) as connection:
            connection.execute("SET ROLE greencity_owner")
            revision = connection.execute(
                "SELECT version_num FROM greencity.alembic_version"
            ).fetchone()[0]
        if revision != "0018":
            raise RuntimeError("final revision mismatch")
        print("Phase 3 migration rehearsal: PASS (empty upgrade, drift check, base rollback, re-upgrade)")
        return 0
    except Exception as exc:
        if os.getenv("PHASE3_VERBOSE") == "1":
            print(f"migration rehearsal diagnostic: {type(exc).__name__}: {exc}")
        print("Migration rehearsal failed; details suppressed and no shared database was used.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
