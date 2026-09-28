"""End-to-end Phase 3 rehearsal on a disposable local PostgreSQL cluster."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import sys
import tempfile

import psycopg
from sqlalchemy.engine import make_url

from scripts.test_isolated import run, run_pg_ctl


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-bin", type=Path, required=True)
    parser.add_argument("--openssl", type=Path, required=True)
    args = parser.parse_args()
    extension = ".exe" if os.name == "nt" else ""
    initdb = args.pg_bin / f"initdb{extension}"
    pg_ctl = args.pg_bin / f"pg_ctl{extension}"
    if not initdb.is_file() or not pg_ctl.is_file() or not args.openssl.is_file():
        print("PostgreSQL initdb/pg_ctl and OpenSSL are required; details suppressed.")
        return 2

    root = Path(__file__).resolve().parents[1]
    runtime_root = root / ".test-runtime"
    runtime_root.mkdir(exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="phase3-", dir=runtime_root)).resolve()
    data = workspace / "data"
    env = {key: value for key, value in os.environ.items()
           if not key.upper().startswith(("PG", "DATABASE_", "PHASE3_", "GREENCITY_ISOLATED_"))}
    env.update(APP_ENV="test", SECRET_KEY=secrets.token_urlsafe(48),
               GREENCITY_DISABLE_DOTENV="1", PYTHONIOENCODING="utf-8")
    password = secrets.token_urlsafe(32)
    migrator_password = secrets.token_urlsafe(32)
    runtime_password = secrets.token_urlsafe(32)
    password_file = workspace / "password.txt"
    password_file.write_text(password + "\n", encoding="utf-8")
    migrator_password_file = workspace / "migrator-password.txt"
    runtime_password_file = workspace / "runtime-password.txt"
    migrator_password_file.write_text(migrator_password + "\n", encoding="utf-8")
    runtime_password_file.write_text(runtime_password + "\n", encoding="utf-8")
    data_arg = os.path.relpath(data, root)
    password_arg = os.path.relpath(password_file, root)
    port = _free_port()
    started = False
    restore_db = None
    admin = None
    stage = "initialize disposable PostgreSQL"
    try:
        run([str(initdb), "-D", data_arg, "-U", "test_migrator", "--auth=scram-sha-256",
             "--encoding=UTF8", "--locale=C", "--pwfile", password_arg], env, "Phase 3 fresh cluster")
        cert, key = workspace / "cert.pem", workspace / "key.pem"
        run([str(args.openssl), "req", "-x509", "-newkey", "rsa:2048", "-nodes",
             "-keyout", str(key), "-out", str(cert), "-days", "1", "-subj", "/CN=localhost",
             "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"], env, "Phase 3 test TLS")
        with (data / "postgresql.conf").open("a", encoding="utf-8") as config:
            config.write(f"\nlisten_addresses='127.0.0.1'\nport={port}\nssl=on\n"
                         f"ssl_cert_file='{cert.as_posix()}'\nssl_key_file='{key.as_posix()}'\n")
        started = True
        run_pg_ctl([str(pg_ctl), "-D", data_arg, "-l", os.path.relpath(workspace / "server.log", root), "start"],
                   env, "Phase 3 PostgreSQL startup", port=port, expect_open=True)
        admin_url = f"postgresql://test_migrator:{password}@127.0.0.1:{port}/postgres?sslmode=require"
        env.update(
            DATABASE_URL=admin_url,
            DATABASE_SSL_ROOT_CERT=str(cert),
            PHASE3_ADMIN_HOST="127.0.0.1",
            PHASE3_ADMIN_PORT=str(port),
            PHASE3_ADMIN_DATABASE="postgres",
            PHASE3_ADMIN_ROLE="test_migrator",
            PHASE3_ADMIN_PASSWORD_FILE=str(password_file),
            PHASE3_MIGRATOR_PASSWORD_FILE=str(migrator_password_file),
            PHASE3_RUNTIME_PASSWORD_FILE=str(runtime_password_file),
        )
        stage = "provision database roles"
        run([sys.executable, "-m", "scripts.phase3_provision_roles"], env,
            "Phase 3 owner/migrator/runtime provisioning")
        migration_url = f"postgresql://greencity_migrator:{migrator_password}@127.0.0.1:{port}/postgres?sslmode=require"
        runtime_url = f"postgresql://greencity_runtime:{runtime_password}@127.0.0.1:{port}/postgres?sslmode=require"
        env.update(DATABASE_URL=migration_url, MIGRATION_ROLE="greencity_owner")

        stage = "initial migration"
        run([sys.executable, "-m", "scripts.migrate", "upgrade", "head"], env,
            "Phase 3 initial migration under owner role", show_output=True)
        with psycopg.connect(admin_url) as verification:
            version_table = verification.execute("SELECT to_regclass('greencity.alembic_version')").fetchone()[0]
            print(f"Phase 3 migrated version table: {'present' if version_table else 'missing'}")
            if version_table is None:
                raise RuntimeError("migration completed without its revision table")
        env["PHASE3_MIGRATION_REHEARSAL"] = "1"
        env["PHASE3_VERBOSE"] = "1"
        stage = "migration rollback and drift rehearsal"
        run([sys.executable, "-m", "scripts.phase3_migration_rehearsal"], env,
            "Phase 3 migration rollback/drift rehearsal", show_output=True)
        env.pop("PHASE3_MIGRATION_REHEARSAL", None)
        env.update(
            DATABASE_URL=runtime_url,
            PHASE3_OWNER_DATABASE_URL=migration_url,
            PHASE3_RUNTIME_ROLE_TEST="1",
        )
        stage = "runtime role DML and DDL test"
        run([sys.executable, "-m", "scripts.phase3_runtime_role_test"], env,
            "Phase 3 production runtime-role test", show_output=True)
        env.pop("PHASE3_RUNTIME_ROLE_TEST", None)

        admin = psycopg.connect(admin_url, autocommit=True)
        restore_db = f"greencity_restore_{secrets.token_hex(5)}"
        admin.execute(f'CREATE DATABASE "{restore_db}"')
        restore_url = make_url(admin_url).set(database=restore_db).render_as_string(hide_password=False)
        admin_url_file = workspace / "backup-source-dsn.txt"
        runtime_url_file = workspace / "backup-runtime-dsn.txt"
        restore_url_file = workspace / "backup-restore-dsn.txt"
        admin_url_file.write_text(admin_url + "\n", encoding="utf-8")
        runtime_url_file.write_text(runtime_url + "\n", encoding="utf-8")
        restore_url_file.write_text(restore_url + "\n", encoding="utf-8")
        try:
            os.chmod(admin_url_file, 0o600)
            os.chmod(runtime_url_file, 0o600)
            os.chmod(restore_url_file, 0o600)
        except OSError:
            pass
        env["PHASE3_BACKUP_REHEARSAL"] = "1"
        stage = "database backup and restore"
        run([sys.executable, "-m", "scripts.phase3_backup_restore", "--pg-bin", str(args.pg_bin),
             "--database-url-file", str(runtime_url_file),
             "--control-database-url-file", str(admin_url_file),
             "--restore-database-url-file", str(restore_url_file)], env,
            "Phase 3 PostgreSQL backup/restore", show_output=True)
        env.pop("PHASE3_BACKUP_REHEARSAL", None)
        env["PHASE3_STORAGE_REHEARSAL"] = "1"
        stage = "private evidence backup and restore"
        run([sys.executable, "-m", "scripts.phase3_storage_rehearsal"], env,
            "Phase 3 evidence backup/restore", show_output=True)
        print(json.dumps({"status": "PASS", "scope": "disposable local PostgreSQL/TLS cluster"}))
        return 0
    except Exception as exc:
        if env.get("PHASE3_VERBOSE") == "1":
            detail = str(exc)
            for name in ("admin_url", "migration_url", "runtime_url", "restore_url"):
                value = locals().get(name)
                if value:
                    detail = detail.replace(value, "[REDACTED]")
            print(f"Phase 3 local diagnostic at {stage}: {type(exc).__name__}: {detail[-1000:]}")
        print("Phase 3 local rehearsal failed; details suppressed and no shared DB was used.")
        return 1
    finally:
        if admin is not None and restore_db:
            try:
                admin.execute(f'REVOKE CONNECT ON DATABASE "{restore_db}" FROM PUBLIC')
                admin.execute(f'ALTER DATABASE "{restore_db}" CONNECTION LIMIT 0')
                admin.execute(f'DROP DATABASE IF EXISTS "{restore_db}"')
            except Exception:
                pass
        if admin is not None:
            admin.close()
        if started:
            try:
                run_pg_ctl([str(pg_ctl), "-D", data_arg, "stop"], env,
                           "Phase 3 PostgreSQL shutdown", port=port, expect_open=False)
            except Exception:
                print("Phase 3 cluster shutdown failed; temporary files retained for local cleanup.")
        if workspace.is_relative_to(runtime_root.resolve()):
            shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
