"""Run a browser slice against a disposable PostgreSQL-backed backend.

This is a local evidence runner for GF-01/GF-02 and post-restart source readback. It
creates a random loopback PostgreSQL cluster, migrates, seeds, imports the
12-workbook teaching pack, starts Uvicorn and Vite, then runs Playwright. It
refuses to run unless PHASE3_REAL_BROWSER=1 and never prints credentials or
connection URLs.
"""

from __future__ import annotations

import argparse
from datetime import date
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
from urllib.parse import parse_qs, urlsplit
import urllib.request


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "greencity-app"
SYNTHETIC_PACK = BACKEND / "tests" / "fixtures" / "submission_data" / "synthetic"
SYNTHETIC_MANIFEST = BACKEND / "tests" / "fixtures" / "submission_data" / "synthetic_manifest.json"
SYNTHETIC_EVIDENCE = BACKEND / "tests" / "fixtures" / "submission_data" / "synthetic_evidence"
SYNTHETIC_RESIDENT_LINKS = BACKEND / "tests" / "fixtures" / "submission_data" / "synthetic_resident_links.json"
DEMO_USERS = (
    "admin_demo", "director_west", "cskh_west", "cskh_east", "accountant_west",
    "techlead_west", "technician_west", "cleaning_west", "security_west", "resident_west",
)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.25):
            return True
    except OSError:
        return False


def _wait_http(url: str, process: subprocess.Popen[bytes], timeout: float = 45) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("service exited before becoming ready")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if 200 <= response.status < 500:
                    return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(0.25)
    raise RuntimeError("service did not become ready")


def _wait_database(database_url: str, python: Path, cwd: Path, env: dict[str, str]) -> None:
    probe_env = env | {"PHASE3_PROBE_DATABASE_URL": database_url}
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        probe = subprocess.run(
            [str(python), "-c", "import os, psycopg; c=psycopg.connect(os.environ['PHASE3_PROBE_DATABASE_URL'], connect_timeout=2); c.close()"],
            cwd=cwd, env=probe_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=False,
        )
        if probe.returncode == 0:
            return
        time.sleep(0.25)
    raise RuntimeError("PostgreSQL did not accept a connection")


def _run(command: list[str], *, cwd: Path, env: dict[str, str], label: str,
         log_path: Path, timeout: int = 300) -> None:
    with log_path.open("w", encoding="utf-8") as stream:
        result = subprocess.run(command, cwd=cwd, env=env, stdout=stream,
                                stderr=subprocess.STDOUT, text=True,
                                encoding="utf-8", errors="replace", timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"{label} failed; see evidence log")


def _terminate(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _pg_start(pg_ctl: Path, data: Path, log_path: Path, port: int, cwd: Path) -> subprocess.Popen[bytes]:
    relative_data = os.path.relpath(data, cwd)
    process = subprocess.Popen(
        [str(pg_ctl), "-D", relative_data, "-l", os.path.relpath(log_path, cwd),
         "-w", "-t", "60", "start"],
        cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    deadline = time.monotonic() + 65
    while time.monotonic() < deadline:
        if _open(port):
            return process
        if os.name != "nt" and process.poll() is not None:
            break
        time.sleep(0.15)
    _terminate(process)
    raise RuntimeError("PostgreSQL did not become ready; see evidence log")


def _imported_targets(database_url: str) -> dict[str, object]:
    """Capture opaque source-to-DB IDs for browser/API readback, without workbook values."""
    import psycopg

    references: dict[str, list[str]] = {}
    finance: dict[str, list[str]] = {}
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT DISTINCT reference.tenant_id::text
               FROM greencity.submission_external_references AS reference
               JOIN greencity.submission_import_runs AS run ON run.id = reference.import_run_id
               WHERE run.stage = 'all' AND run.status = 'APPLIED'"""
        )
        tenant_ids = [row[0] for row in cursor.fetchall()]
        if len(tenant_ids) != 1:
            raise RuntimeError("synthetic import must resolve to one tenant")
        cursor.execute(
            """SELECT reference.entity_type, reference.target_id::text
               FROM greencity.submission_external_references AS reference
               JOIN greencity.submission_import_runs AS run ON run.id = reference.import_run_id
               WHERE run.stage = 'all' AND run.status = 'APPLIED'
               ORDER BY reference.entity_type, reference.target_id"""
        )
        for entity_type, target_id in cursor.fetchall():
            references.setdefault(entity_type, []).append(target_id)
        for label, table in (
            ("fee_policies", "billing_fee_policies"),
            ("periods", "accounting_periods"),
            ("invoices", "billing_invoices"),
            ("payments", "payments"),
            ("unmatched", "unmatched_payments"),
            ("credits", "overpayment_credits"),
        ):
            cursor.execute(f"SELECT id::text FROM greencity.{table} WHERE tenant_id = %s::uuid ORDER BY id", (tenant_ids[0],))
            finance[label] = [row[0] for row in cursor.fetchall()]
    if not all(references.get(entity) for entity in ("Asset", "CleaningShift", "SecurityShift", "SecurityIncident", "Parcel")):
        raise RuntimeError("synthetic import reference targets are incomplete")
    return {"references": references, "finance": finance}


def _provision_synthetic_resident_links(database_url: str, app_env: dict[str, str]) -> tuple[int, int]:
    """Apply explicit test-only identity links after import, never to a source pack."""
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app.models.account import Account, AccountRole
    from app.models.billing import BillingAccount
    from app.models.person import Person, UnitPersonRelationship
    from app.models.site import Site
    from app.models.building import Building
    from app.models.submission_import import SubmissionExternalReference
    from app.models.tenant import Tenant

    parsed_url = urlsplit(database_url)
    if (os.getenv("PHASE3_REAL_BROWSER") != "1"
            or app_env.get("APP_ENV") != "test"
            or app_env.get("GREENCITY_DISABLE_DOTENV") != "1"
            or app_env.get("DATABASE_URL") != database_url
            or parsed_url.scheme != "postgresql"
            or parsed_url.hostname != "127.0.0.1"
            or parsed_url.port is None
            or parsed_url.path != "/postgres"
            or parse_qs(parsed_url.query).get("sslmode") != ["require"]):
        raise RuntimeError("synthetic provisioning requires the disposable test database")
    manifest = json.loads(SYNTHETIC_MANIFEST.read_text(encoding="utf-8"))
    sidecar = json.loads(SYNTHETIC_RESIDENT_LINKS.read_text(encoding="utf-8"))
    links = sidecar.get("links")
    if (manifest.get("classification") != "SYNTHETIC_TEST_ONLY"
            or sidecar.get("classification") != "SYNTHETIC_TEST_ONLY"
            or not isinstance(links, list) or len(links) != 7):
        raise RuntimeError("synthetic resident identity sidecar is invalid")
    for field, prefix in (("username", "syn_resident_"),
                          ("resident_code", "SYN-RES-"),
                          ("billing_account_number", "SYN-BA-")):
        values = [item.get(field) for item in links]
        if any(not isinstance(value, str) or not value.startswith(prefix)
               for value in values) or len(set(values)) != len(values):
            raise RuntimeError("synthetic resident identity sidecar has invalid keys")

    engine = create_engine(database_url.replace("postgresql://", "postgresql+psycopg://", 1),
                           hide_parameters=True)
    linked = 0
    try:
        with Session(engine) as session:
            tenant = session.scalar(select(Tenant).where(Tenant.code == "SYN-TENANT"))
            site = session.scalar(select(Site).where(Site.tenant_id == tenant.id, Site.code == "SYN-SITE")) if tenant else None
            building = session.scalar(select(Building).where(
                Building.site_id == site.id, Building.code == "SYN-B1")) if site else None
            if tenant is None or site is None or building is None:
                raise RuntimeError("synthetic resident scope is missing")
            for link in links:
                account = session.scalar(select(Account).where(
                    Account.tenant_id == tenant.id, Account.username == link["username"]).with_for_update())
                reference = session.scalar(select(SubmissionExternalReference).where(
                    SubmissionExternalReference.tenant_id == tenant.id,
                    SubmissionExternalReference.source == "resident",
                    SubmissionExternalReference.entity_type == "Person",
                    SubmissionExternalReference.source_key == link["resident_code"],
                ))
                person = session.get(Person, reference.target_id) if reference else None
                billing = session.scalar(select(BillingAccount).where(
                    BillingAccount.tenant_id == tenant.id,
                    BillingAccount.site_id == site.id,
                    BillingAccount.building_id == building.id,
                    BillingAccount.account_number == link["billing_account_number"],
                ))
                grant = session.scalar(select(AccountRole.id).where(
                    AccountRole.account_id == account.id,
                    AccountRole.role == "resident",
                    AccountRole.site_id == site.id,
                    AccountRole.building_id == building.id,
                )) if account else None
                relationship = session.scalar(select(UnitPersonRelationship.id).where(
                    UnitPersonRelationship.person_id == person.id,
                    UnitPersonRelationship.tenant_id == tenant.id,
                    UnitPersonRelationship.site_id == site.id,
                    UnitPersonRelationship.building_id == building.id,
                    UnitPersonRelationship.unit_id == billing.unit_id,
                    UnitPersonRelationship.valid_from <= date.today(),
                    (UnitPersonRelationship.valid_to.is_(None))
                    | (UnitPersonRelationship.valid_to > date.today()),
                )) if person and billing else None
                if (account is None or not account.is_active or person is None
                        or person.tenant_id != tenant.id or billing is None
                        or grant is None or relationship is None):
                    raise RuntimeError("synthetic resident identity link lacks a scoped source")
                prior_owner = session.scalar(select(Account.id).where(
                    Account.tenant_id == tenant.id, Account.person_id == person.id,
                    Account.id != account.id,
                ))
                if prior_owner is not None or account.person_id not in (None, person.id):
                    raise RuntimeError("synthetic resident identity conflicts with an existing link")
                if account.person_id is None:
                    account.person_id = person.id
                    linked += 1
            session.commit()
    finally:
        engine.dispose()
    return len(links), linked


def main() -> int:
    if os.getenv("PHASE3_REAL_BROWSER") != "1":
        print("Set PHASE3_REAL_BROWSER=1 for the disposable real-backend browser rehearsal.")
        return 2
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-bin", type=Path, required=True)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--node", type=Path, default=Path("node"))
    parser.add_argument("--openssl", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args()
    extension = ".exe" if os.name == "nt" else ""
    initdb = args.pg_bin / f"initdb{extension}"
    pg_ctl = args.pg_bin / f"pg_ctl{extension}"
    if not initdb.is_file() or not pg_ctl.is_file():
        print("PostgreSQL initdb/pg_ctl executables are required.")
        return 2
    if not args.python.is_file() or not args.openssl.is_file():
        print("The requested Python/OpenSSL executable is not available.")
        return 2
    node = args.node if args.node.is_absolute() else Path(shutil.which(str(args.node)) or "")
    if not node.is_file():
        print("The requested Node.js executable is not available.")
        return 2

    evidence = args.evidence_dir.resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    runtime_root = BACKEND / ".test-runtime"
    runtime_root.mkdir(exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="real-browser-", dir=runtime_root)).resolve()
    if not workspace.is_relative_to(runtime_root.resolve()):
        raise RuntimeError("unsafe disposable workspace")
    data = workspace / "data"
    credential_file = workspace / "demo-credentials.json"
    import_credential_file = workspace / "submission-credentials.json"
    imported_browser_credential_file = workspace / "submission-browser-credentials.json"
    pg_process: subprocess.Popen[bytes] | None = None
    backend_process: subprocess.Popen[bytes] | None = None
    frontend_process: subprocess.Popen[bytes] | None = None
    env = {
        key: value for key, value in os.environ.items()
        if not key.upper().startswith(("PG", "DATABASE_", "RUN_DB_", "GREENCITY_ISOLATED_"))
    }
    try:
        db_password = secrets.token_urlsafe(32)
        initial = {username: secrets.token_urlsafe(24) for username in DEMO_USERS}
        rotated = {username: secrets.token_urlsafe(24) for username in DEMO_USERS}
        credentials = {
            username: {"initial_password": password, "new_password": rotated[username]}
            for username, password in initial.items()
        }
        seed_credentials = {username: item["initial_password"] for username, item in credentials.items()}
        credential_file.write_text(json.dumps(credentials), encoding="utf-8")
        try:
            os.chmod(credential_file, 0o600)
        except OSError:
            pass
        password_file = workspace / "postgres-password.txt"
        password_file.write_text(db_password + "\n", encoding="utf-8")
        data_arg = os.path.relpath(data, BACKEND)
        password_arg = os.path.relpath(password_file, BACKEND)
        pg_init_log = evidence / "postgres-init.log"
        _run([str(initdb), "-D", data_arg, "-U", "test_migrator",
              "--auth=scram-sha-256", "--encoding=UTF8", "--locale=C", "--pwfile", password_arg],
             cwd=BACKEND, env=env, label="PostgreSQL init", log_path=pg_init_log)
        pg_port = _free_port()
        cert, key = workspace / "cert.pem", workspace / "key.pem"
        _run([str(args.openssl), "req", "-x509", "-newkey", "rsa:2048", "-nodes",
              "-keyout", str(key), "-out", str(cert), "-days", "1", "-subj", "/CN=localhost",
              "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"],
             cwd=BACKEND, env=env, label="PostgreSQL TLS certificate",
             log_path=evidence / "postgres-tls.log")
        if os.name != "nt":
            key.chmod(0o600)
        with (data / "postgresql.conf").open("a", encoding="utf-8") as config:
            config.write(
                f"\nlisten_addresses='127.0.0.1'\nport={pg_port}\nssl=on\n"
                f"ssl_cert_file='{cert.as_posix()}'\nssl_key_file='{key.as_posix()}'\n"
            )
            if os.name != "nt":
                # Hosted Linux runners do not own /var/run/postgresql. This
                # disposable cluster only needs loopback TCP, so do not create
                # a system Unix-domain socket.
                config.write("unix_socket_directories=''\n")
        pg_log = workspace / "postgres.log"
        pg_process = _pg_start(pg_ctl, data, pg_log, pg_port, BACKEND)
        database_url = f"postgresql://test_migrator:{db_password}@127.0.0.1:{pg_port}/postgres?sslmode=require"
        _wait_database(database_url, args.python, BACKEND, env)
        frontend_port = _free_port()
        backend_port = _free_port()
        app_env = env | {
            "APP_ENV": "test",
            "GREENCITY_DISABLE_DOTENV": "1",
            "DATABASE_URL": database_url,
            "SECRET_KEY": secrets.token_urlsafe(48),
            "CORS_ORIGINS": json.dumps([f"http://127.0.0.1:{frontend_port}"]),
            "PRIVATE_STORAGE_PATH": str(workspace / "private-evidence"),
            "ASSISTANT_ENABLED": "false",
            "DEMO_SEED_ENABLED": "true",
            "DEMO_SEED_CREDENTIALS_JSON": json.dumps(seed_credentials),
            "GREENCITY_SUBMISSION_CREDENTIALS_FILE": str(import_credential_file),
            "GREENCITY_SUBMISSION_PIN_SECRET": secrets.token_urlsafe(32),
            "GREENCITY_SUBMISSION_EVIDENCE_DIR": str(SYNTHETIC_EVIDENCE),
        }
        _run([str(args.python), "-m", "scripts.migrate", "upgrade", "head"], cwd=BACKEND,
             env=app_env, label="Database migration", log_path=evidence / "migrate.log")
        _run([str(args.python), "-m", "scripts.seed"], cwd=BACKEND, env=app_env,
             label="Demo seed", log_path=evidence / "seed.log")

        if not (SYNTHETIC_PACK.is_dir() and SYNTHETIC_MANIFEST.is_file() and SYNTHETIC_EVIDENCE.is_dir()):
            raise RuntimeError("synthetic submission pack is missing")
        sys.path.insert(0, str(BACKEND))
        from app.services.submission_data_reader import read_submission_pack
        from scripts.load_submission_data import _rows

        synthetic_pack = read_submission_pack(SYNTHETIC_PACK)
        usernames = (str(row["username"]) for row in _rows(synthetic_pack, "02_danh_sach_nhan_vien.xlsx"))
        imported_browser_credentials = {
            username: {"initial_password": secrets.token_urlsafe(32), "new_password": secrets.token_urlsafe(32)}
            for username in usernames
        }
        import_credential_file.write_text(json.dumps({
            username: item["initial_password"] for username, item in imported_browser_credentials.items()
        }), encoding="utf-8")
        imported_browser_credential_file.write_text(json.dumps(imported_browser_credentials), encoding="utf-8")
        try:
            os.chmod(import_credential_file, 0o600)
            os.chmod(imported_browser_credential_file, 0o600)
        except OSError:
            pass
        _run([str(args.python), "-m", "scripts.submission_data_preflight", "--source", str(SYNTHETIC_PACK),
              "--manifest", str(SYNTHETIC_MANIFEST), "--report-dir", str(workspace / "preflight")],
             cwd=BACKEND, env=app_env, label="Synthetic preflight", log_path=evidence / "submission-preflight.log")
        for action in ("dry-run", "apply", "verify"):
            _run([str(args.python), "-m", "scripts.load_submission_data", "--source", str(SYNTHETIC_PACK),
                  "--manifest", str(SYNTHETIC_MANIFEST), "--stage", "all", f"--{action}"], cwd=BACKEND, env=app_env,
                 label=f"Synthetic {action}", log_path=evidence / f"submission-{action}.log")

        backend_log_stream = (evidence / "backend.log").open("w", encoding="utf-8")
        backend_process = subprocess.Popen(
            [str(args.python), "-m", "uvicorn", "app.main:create_app", "--factory",
             "--host", "127.0.0.1", "--port", str(backend_port)],
            cwd=BACKEND, env=app_env, stdout=backend_log_stream,
            stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        _wait_http(f"http://127.0.0.1:{backend_port}/api/v1/health", backend_process)
        vite = FRONTEND / "node_modules" / "vite" / "bin" / "vite.js"
        frontend_env = app_env | {
            "VITE_DEV_API_PROXY_TARGET": f"http://127.0.0.1:{backend_port}",
        }
        frontend_log_stream = (evidence / "frontend.log").open("w", encoding="utf-8")
        frontend_process = subprocess.Popen(
            [str(node), str(vite), "--configLoader", "runner", "--host", "127.0.0.1", "--port", str(frontend_port)],
            cwd=FRONTEND, env=frontend_env, stdout=frontend_log_stream,
            stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        _wait_http(f"http://127.0.0.1:{frontend_port}/", frontend_process)
        runner_env = app_env | {
            "REAL_BROWSER_BASE_URL": f"http://127.0.0.1:{frontend_port}",
            "REAL_BROWSER_BACKEND_URL": f"http://127.0.0.1:{backend_port}",
            "REAL_BROWSER_CREDENTIALS_FILE": str(credential_file),
            "REAL_BROWSER_EVIDENCE_DIR": str(evidence),
        }
        browser_result = subprocess.run(
            [str(node), str(FRONTEND / "tests" / "real-backend-golden-flow.cjs")],
            cwd=FRONTEND, env=runner_env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", timeout=300,
        )
        (evidence / "browser.log").write_text(browser_result.stdout, encoding="utf-8")
        print(browser_result.stdout.encode("ascii", "backslashreplace").decode("ascii"), end="")
        _terminate(backend_process)
        backend_log_stream.close()
        backend_log_stream = (evidence / "backend-restart.log").open("w", encoding="utf-8")
        backend_process = subprocess.Popen(
            [str(args.python), "-m", "uvicorn", "app.main:create_app", "--factory",
             "--host", "127.0.0.1", "--port", str(backend_port)],
            cwd=BACKEND, env=app_env, stdout=backend_log_stream,
            stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        _wait_http(f"http://127.0.0.1:{backend_port}/api/v1/health", backend_process)
        _run([str(args.python), "-m", "scripts.load_submission_data", "--source", str(SYNTHETIC_PACK),
              "--manifest", str(SYNTHETIC_MANIFEST), "--stage", "all", "--verify"], cwd=BACKEND, env=app_env,
             label="Synthetic post-restart verify", log_path=evidence / "submission-post-restart-verify.log")
        first_links = _provision_synthetic_resident_links(database_url, app_env)
        replay_links = _provision_synthetic_resident_links(database_url, app_env)
        if first_links != (7, 7) or replay_links != (7, 0):
            raise RuntimeError("synthetic resident provisioning was not idempotent")
        print("SYNTHETIC_RESIDENT_PROVISION: PASS mapped=7 idempotent=PASS")
        target_path = workspace / "imported-targets.json"
        target_path.write_text(json.dumps(_imported_targets(database_url)), encoding="utf-8")
        readback_env = runner_env | {
            "REAL_BROWSER_IMPORTED_TARGETS_FILE": str(target_path),
            "REAL_BROWSER_IMPORTED_CREDENTIALS_FILE": str(imported_browser_credential_file),
            "REAL_BROWSER_SYNTHETIC_RESIDENT_LINKS_FILE": str(SYNTHETIC_RESIDENT_LINKS),
        }
        readback_result = subprocess.run(
            [str(node), str(FRONTEND / "tests" / "real-backend-imported-readback.cjs")],
            cwd=FRONTEND, env=readback_env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", timeout=300,
        )
        (evidence / "imported-readback.log").write_text(readback_result.stdout, encoding="utf-8")
        print(readback_result.stdout.encode("ascii", "backslashreplace").decode("ascii"), end="")
        if readback_result.returncode:
            raise RuntimeError("synthetic imported readback failed")
        if browser_result.returncode:
            raise RuntimeError("GF01/GF02 real-backend browser runner failed")
        print("REAL_BACKEND_BROWSER_REHEARSAL: PASS synthetic_import=PASS restart_verify=PASS browser=GF01_GF02 readback=GF03_GF08")
        return 0
    except Exception as exc:
        print(f"Real-backend browser rehearsal failed ({type(exc).__name__}); see evidence logs.")
        return 1
    finally:
        _terminate(frontend_process)
        _terminate(backend_process)
        if pg_process is not None:
            try:
                subprocess.run([str(pg_ctl), "-D", os.path.relpath(data, BACKEND), "-w", "-t", "60", "stop"],
                               cwd=BACKEND, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=65, check=False)
            except Exception:
                pass
        pg_log = workspace / "postgres.log"
        if pg_log.is_file():
            shutil.copyfile(pg_log, evidence / "postgres.log")
        shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
