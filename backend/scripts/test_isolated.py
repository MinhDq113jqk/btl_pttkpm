"""Run security regressions on a fresh local PostgreSQL cluster, never shared DBs.

All connection credentials are random, child-process-only, and never printed.
Only the cluster created under this invocation's temporary directory is stopped
and removed. Requires local PostgreSQL binaries and openssl; no downloads.
"""
import argparse
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


def run(command, env, label, *, show_output=False):
    print(f"{label}: running", flush=True)
    # Background postgres can inherit pipe handles on Windows. Infrastructure
    # commands use DEVNULL so communicate() cannot wait on the server's pipes.
    result = subprocess.run(command, cwd=ROOT, env=env,
                            stdout=subprocess.PIPE if show_output else subprocess.DEVNULL,
                            stderr=subprocess.STDOUT if show_output else subprocess.DEVNULL,
                            text=True, encoding="utf-8", errors="replace", timeout=120)
    # Infrastructure errors can contain connection details: never echo them.
    if show_output:
        output = result.stdout
        for variable in ("DATABASE_URL", "SECRET_KEY"):
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


def run_pg_ctl(command, env, label, *, port: int, expect_open: bool) -> None:
    """Start/stop a local cluster without waiting on inherited Windows handles."""
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
    deadline = time.monotonic() + 30
    try:
        while time.monotonic() < deadline:
            if _port_is_open(port) is expect_open:
                print(f"{label}: PASS")
                return
            # On Windows, pg_ctl can report a non-zero launcher result while
            # its restricted-token child continues starting or stopping the
            # actual server.  The dedicated loopback port is authoritative;
            # failing immediately here makes a healthy disposable cluster
            # look unavailable.
            time.sleep(0.1)
        raise RuntimeError(f"{label} timed out; details suppressed")
    finally:
        # `pg_ctl -w` can retain a wrapper handle in non-interactive Windows
        # hosts even after postgres is ready.  It is only a launcher; the
        # server is identified and stopped later by this exact data directory.
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

    # Never inherit connection/service configuration or an external test target.
    env = {key: value for key, value in os.environ.items()
           if not key.upper().startswith(("PG", "DATABASE_", "RUN_DB_", "GREENCITY_ISOLATED_"))}
    env.update(APP_ENV="test", SECRET_KEY=secrets.token_urlsafe(48), PYTHONIOENCODING="utf-8")
    runtime_root = ROOT / ".test-runtime"
    runtime_root.mkdir(exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="security-", dir=runtime_root)).resolve()
    if not workspace.is_relative_to(runtime_root.resolve()):
        raise RuntimeError("Unsafe test workspace")
    data = workspace / "data"
    env["PRIVATE_STORAGE_PATH"] = str(workspace / "private-evidence")
    started = False
    success = False
    try:
        password = secrets.token_urlsafe(32)
        password_file = workspace / "password.txt"
        password_file.write_text(password + "\n", encoding="utf-8")
        # PostgreSQL's Windows restricted-token re-exec misparses an absolute
        # --pwfile path containing a drive colon under non-interactive hosts.
        # The runner's cwd is ROOT, so a relative path keeps the secret file
        # inside the generated workspace without weakening SCRAM setup.
        data_arg = os.path.relpath(data, ROOT)
        password_file_arg = os.path.relpath(password_file, ROOT)
        run([str(binaries["initdb"]), "-D", data_arg, "-U", "test_migrator",
             "--auth=scram-sha-256", "--encoding=UTF8", "--locale=C",
             "--pwfile", password_file_arg], env, "Fresh cluster init")
        cert, key = workspace / "cert.pem", workspace / "key.pem"
        run([str(args.openssl), "req", "-x509", "-newkey", "rsa:2048", "-nodes",
             "-keyout", str(key), "-out", str(cert), "-days", "1", "-subj", "/CN=localhost",
             "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"], env, "Test TLS certificate")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        with (data / "postgresql.conf").open("a", encoding="utf-8") as config:
            config.write(f"\nlisten_addresses='127.0.0.1'\nport={port}\nssl=on\n"
                         f"ssl_cert_file='{cert.as_posix()}'\nssl_key_file='{key.as_posix()}'\n")
        # `run_pg_ctl` starts just this disposable cluster and verifies its port.
        started = True  # A failed startup may still have launched the child server.
        server_log_arg = os.path.relpath(workspace / "server.log", ROOT)
        run_pg_ctl([str(binaries["pg_ctl"]), "-D", data_arg, "-l", server_log_arg, "start"],
                   env, "Test PostgreSQL startup", port=port, expect_open=True)
        env["DATABASE_URL"] = f"postgresql://test_migrator:{password}@127.0.0.1:{port}/postgres"
        env["DATABASE_SSL_ROOT_CERT"] = str(cert)
        env["GREENCITY_ISOLATED_MIGRATION_PATH_TESTS"] = "1"
        run([sys.executable, "-m", "scripts.test_migration_0005"], env, "AC-03 migration paths",
            show_output=True)
        run([sys.executable, "-m", "scripts.test_migration_0007"], env, "R3 migration paths",
            show_output=True)
        run([sys.executable, "-m", "scripts.test_migration_0008"], env, "R4 migration paths",
            show_output=True)
        run([sys.executable, "-m", "scripts.test_migration_0009"], env, "R4 Task 2 migration paths",
            show_output=True)
        run([sys.executable, "-m", "scripts.test_migration_0010"], env, "R4 Task 3 migration paths",
            show_output=True)
        run([sys.executable, "-m", "scripts.migrate", "upgrade", "head"], env, "Empty DB migration")
        run([sys.executable, "-m", "scripts.migrate", "upgrade", "head"], env, "Migration repeat")
        # Fixtures for legacy regression tests are created only in this new cluster.
        run([sys.executable, "-m", "scripts.seed"], env, "Demo seed")
        run([sys.executable, "-m", "scripts.seed"], env, "Seed repeat")
        run([sys.executable, "-m", "scripts.migrate", "check"], env,
            "Alembic schema drift", show_output=True)
        env["RUN_DB_INTEGRATION"] = "1"
        env["GREENCITY_ISOLATED_SECURITY_TESTS"] = "1"
        run([sys.executable, "-m", "pytest", "-q", "--tb=short", "-o",
             f"cache_dir={workspace / 'pytest-cache'}"], env,
            "Isolated PostgreSQL regression", show_output=True)
        success = True
    except Exception as exc:
        # Messages above are deliberately non-sensitive; no driver/subprocess tracebacks.
        print(f"Isolated verification failed ({type(exc).__name__}); no shared database was used.")
        if type(exc) is RuntimeError:
            print(str(exc))  # Only our labelled, redacted messages above.
    finally:
        # pg_ctl stop uses the exact cluster initialized by this invocation.
        stopped = not started
        if started:
            try:
                run_pg_ctl([str(binaries["pg_ctl"]), "-D", data_arg, "stop"],
                           env, "Test PostgreSQL shutdown", port=port, expect_open=False)
                stopped = True
            except Exception:
                print("Test cluster shutdown failed; temporary files retained for local cleanup.")
                success = False
        if stopped and workspace.is_relative_to(runtime_root.resolve()) and workspace != runtime_root.resolve():
            shutil.rmtree(workspace)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
