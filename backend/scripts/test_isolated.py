"""Run security regressions on a fresh local PostgreSQL cluster, never shared DBs.

All connection credentials are random, child-process-only, and never printed.
Only the cluster created under this invocation's temporary directory is stopped
and removed. Requires local PostgreSQL binaries and openssl; no downloads.
"""
import argparse
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

ROOT = Path(__file__).resolve().parents[1]
DEMO_ACCOUNT_USERNAMES = (
    "admin_demo", "director_west", "cskh_west", "cskh_east", "accountant_west",
    "techlead_west", "technician_west", "cleaning_west", "security_west", "resident_west",
)


def run(command, env, label, *, show_output=False):
    print(f"{label}: running", flush=True)
    timeout = 420 if command[:3] == [sys.executable, "-m", "pytest"] else 120
    result = subprocess.run(command, cwd=ROOT, env=env,
                            stdout=subprocess.PIPE if show_output else subprocess.DEVNULL,
                            stderr=subprocess.STDOUT if show_output else subprocess.DEVNULL,
                            text=True, encoding="utf-8", errors="replace", timeout=timeout)
    if show_output:
        output = result.stdout
        for variable in ("DATABASE_URL", "SECRET_KEY", "DEMO_SEED_CREDENTIALS_JSON",
                         "ROTATED_DEMO_CREDENTIALS_JSON"):
            if env.get(variable):
                output = output.replace(env[variable], "[REDACTED]")
        print(output, end="")
    if result.returncode:
        raise RuntimeError(f"{label} failed (exit {result.returncode}); details suppressed")
    print(f"{label}: PASS")


def _port_is_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return True
    except OSError:
        return False


def _print_safe_log_tail(log_path: Path | None, env: dict[str, str], *, lines: int = 80) -> None:
    if log_path is None or not log_path.is_file():
        print("PostgreSQL diagnostic log is unavailable.", flush=True)
        return
    try:
        content = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        print("PostgreSQL diagnostic log could not be read.", flush=True)
        return

    sensitive_values = {
        env.get("DATABASE_URL"),
        env.get("SECRET_KEY"),
        env.get("DEMO_SEED_CREDENTIALS_JSON"),
        env.get("ROTATED_DEMO_CREDENTIALS_JSON"),
    }
    safe_content = content
    for value in sensitive_values:
        if value:
            safe_content = safe_content.replace(value, "[REDACTED]")

    tail = safe_content.splitlines()[-lines:]
    print("--- PostgreSQL diagnostic log tail ---", flush=True)
    for line in tail:
        print(line, flush=True)
    print("--- end PostgreSQL diagnostic log tail ---", flush=True)


def run_pg_ctl(command, env, label, *, port: int, expect_open: bool,
               timeout_seconds: int = 60, diagnostic_log: Path | None = None) -> None:
    print(f"{label}: running", flush=True)
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    deadline = time.monotonic() + timeout_seconds
    try:
        while time.monotonic() < deadline:
            if _port_is_open(port) is expect_open:
                print(f"{label}: PASS")
                return
            if os.name != "nt" and process.poll() is not None:
                break
            time.sleep(0.1)

        _print_safe_log_tail(diagnostic_log, env)
        return_code = process.poll()
        if return_code is None:
            raise RuntimeError(f"{label} timed out after {timeout_seconds}s; details above")
        raise RuntimeError(f"{label} launcher exited {return_code} before expected state; details above")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-bin", type=Path, required=True)
    parser.add_argument("--openssl", type=Path, required=True)
    args = parser.parse_args()
    extension = ".exe" if os.name == "nt" else ""
    binaries = {name: args.pg_bin / (name + extension) for name in ("initdb", "pg_ctl")}
    if not all(path.is_file() for path in [*binaries.values(), args.openssl]):
        parser.error("PostgreSQL initdb/pg_ctl and openssl executables are required")

    env = {key: value for key, value in os.environ.items()
           if not key.upper().startswith(("PG", "DATABASE_", "RUN_DB_", "GREENCITY_ISOLATED_"))}
    demo_credentials = {
        username: secrets.token_urlsafe(32) for username in DEMO_ACCOUNT_USERNAMES
    }
    env.update(
        APP_ENV="test",
        SECRET_KEY=secrets.token_urlsafe(48),
        PYTHONIOENCODING="utf-8",
        GREENCITY_DISABLE_DOTENV="1",
        DEMO_SEED_ENABLED="true",
        DEMO_SEED_CREDENTIALS_JSON=json.dumps(demo_credentials),
    )
    runtime_root = ROOT / ".test-runtime"
    runtime_root.mkdir(exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="security-", dir=runtime_root)).resolve()
    if not workspace.is_relative_to(runtime_root.resolve()):
        raise RuntimeError("Unsafe test workspace")
    data = workspace / "data"
    env["PRIVATE_STORAGE_PATH"] = str(workspace / "private-evidence")
    started = False
    success = False
    server_log = workspace / "server.log"
    try:
        password = secrets.token_urlsafe(32)
        password_file = workspace / "password.txt"
        password_file.write_text(password + "\n", encoding="utf-8")
        data_arg = os.path.relpath(data, ROOT)
        password_file_arg = os.path.relpath(password_file, ROOT)
        run([str(binaries["initdb"]), "-D", data_arg, "-U", "test_migrator",
             "--auth=scram-sha-256", "--encoding=UTF8", "--locale=C",
             "--pwfile", password_file_arg], env, "Fresh cluster init")
        cert, key = workspace / "cert.pem", workspace / "key.pem"
        run([str(args.openssl), "req", "-x509", "-newkey", "rsa:2048", "-nodes",
             "-keyout", str(key), "-out", str(cert), "-days", "1", "-subj", "/CN=localhost",
             "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"], env, "Test TLS certificate")
        if os.name != "nt":
            key.chmod(0o600)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        with (data / "postgresql.conf").open("a", encoding="utf-8") as config:
            config.write(f"\nlisten_addresses='127.0.0.1'\nport={port}\nssl=on\n"
                         f"ssl_cert_file='{cert.as_posix()}'\nssl_key_file='{key.as_posix()}'\n"
                         "unix_socket_directories=''\n")
        started = True
        server_log_arg = os.path.relpath(server_log, ROOT)
        run_pg_ctl([str(binaries["pg_ctl"]), "-D", data_arg, "-l", server_log_arg,
                    "-w", "-t", "60", "start"],
                   env, "Test PostgreSQL startup", port=port, expect_open=True,
                   timeout_seconds=65, diagnostic_log=server_log)
        env["DATABASE_URL"] = f"postgresql://test_migrator:{password}@127.0.0.1:{port}/postgres"
        env["DATABASE_SSL_ROOT_CERT"] = str(cert)
        env["GREENCITY_ISOLATED_MIGRATION_PATH_TESTS"] = "1"
        run([sys.executable, "-m", "scripts.test_migration_0005"], env, "AC-03 migration paths", show_output=True)
        run([sys.executable, "-m", "scripts.test_migration_0007"], env, "R3 migration paths", show_output=True)
        run([sys.executable, "-m", "scripts.test_migration_0008"], env, "R4 migration paths", show_output=True)
        run([sys.executable, "-m", "scripts.test_migration_0009"], env, "R4 Task 2 migration paths", show_output=True)
        run([sys.executable, "-m", "scripts.test_migration_0010"], env, "R4 Task 3 migration paths", show_output=True)
        run([sys.executable, "-m", "scripts.test_migration_0011"], env, "R5 outbox migration paths", show_output=True)
        run([sys.executable, "-m", "scripts.test_migration_0012"], env, "R6 resident identity migration paths", show_output=True)
        run([sys.executable, "-m", "scripts.test_migration_0013"], env, "R6 resident request evidence migration paths", show_output=True)
        run([sys.executable, "-m", "scripts.test_migration_0014"], env, "V1 parcel foundation migration paths", show_output=True)
        run([sys.executable, "-m", "scripts.test_migration_0015"], env, "V1 parcel case/evidence migration paths", show_output=True)
        run([sys.executable, "-m", "scripts.test_migration_0016"], env, "Auth-session and forced-password migration paths", show_output=True)
        run([sys.executable, "-m", "scripts.test_migration_0017"], env, "Login-throttle migration paths", show_output=True)
        run([sys.executable, "-m", "scripts.test_migration_0018"], env, "Submission import migration paths", show_output=True)
        run([sys.executable, "-m", "scripts.migrate", "upgrade", "head"], env, "Empty DB migration")
        run([sys.executable, "-m", "scripts.migrate", "upgrade", "head"], env, "Migration repeat")
        env["GREENCITY_ISOLATED_SECURITY_TESTS"] = "1"
        run([sys.executable, "-m", "scripts.test_submission_pack_isolated"], env,
            "Synthetic submission pack on clean database", show_output=True)
        run([sys.executable, "-m", "scripts.seed"], env, "Demo seed")
        run([sys.executable, "-m", "scripts.seed"], env, "Seed repeat")
        run([sys.executable, "-m", "scripts.migrate", "check"], env,
            "Alembic schema drift", show_output=True)
        env["RUN_DB_INTEGRATION"] = "1"
        env["GREENCITY_ISOLATED_SECURITY_TESTS"] = "1"
        rotated_credentials = {
            username: secrets.token_urlsafe(32) for username in DEMO_ACCOUNT_USERNAMES
        }
        env["ROTATED_DEMO_CREDENTIALS_JSON"] = json.dumps(rotated_credentials)
        run([sys.executable, "-m", "scripts.prepare_test_accounts"], env,
            "Forced demo-password change flow", show_output=True)
        env["DEMO_SEED_CREDENTIALS_JSON"] = env.pop("ROTATED_DEMO_CREDENTIALS_JSON")
        run([sys.executable, "-m", "pytest", "-q", "--tb=short", "-o",
             f"cache_dir={workspace / 'pytest-cache'}", "--basetemp",
             str(workspace / "pytest-temp")], env,
            "Isolated PostgreSQL regression", show_output=True)
        success = True
    except Exception as exc:
        print(f"Isolated verification failed ({type(exc).__name__}); no shared database was used.")
        if type(exc) is RuntimeError:
            print(str(exc))
    finally:
        stopped = not started
        if started:
            try:
                run_pg_ctl([str(binaries["pg_ctl"]), "-D", data_arg, "-w", "-t", "60", "stop"],
                           env, "Test PostgreSQL shutdown", port=port, expect_open=False,
                           timeout_seconds=65, diagnostic_log=server_log)
                stopped = True
            except Exception:
                print("Test cluster shutdown failed; temporary files retained for local cleanup.")
                success = False
        if stopped and workspace.is_relative_to(runtime_root.resolve()) and workspace != runtime_root.resolve():
            try:
                shutil.rmtree(workspace)
            except OSError:
                print("Failed isolated workspace cleanup; temporary files may remain for local cleanup.")
            else:
                if not success:
                    print("Failed isolated verification; temporary workspace removed.")
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
