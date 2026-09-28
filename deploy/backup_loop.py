"""Scheduled PostgreSQL and private-evidence backup worker for Compose."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tarfile
import tempfile
import time
from urllib.parse import parse_qs, unquote, urlsplit


BACKUP_ROOT = Path(os.getenv("BACKUP_PATH", "/var/lib/greencity-backups"))
EVIDENCE_ROOT = Path(os.getenv("PRIVATE_STORAGE_PATH", "/srv/private-evidence"))
DATABASE_URL_FILE = Path(os.getenv("DATABASE_URL_SECRET_FILE", "/run/secrets/runtime_database_url"))
MANAGED_SUFFIXES = (".dump", ".evidence.tar.gz", ".manifest.json")


def _database_service(database_url: str, service_name: str) -> str:
    parsed = urlsplit(database_url)
    if parsed.scheme not in {"postgres", "postgresql", "postgresql+psycopg"}:
        raise ValueError("backup worker requires a PostgreSQL connection URI")
    if not parsed.hostname or not parsed.username or parsed.password is None or not parsed.path.strip("/"):
        raise ValueError("backup worker requires host, user, password, and database")
    query = parse_qs(parsed.query)
    sslmode = query.get("sslmode", ["require"])[0]
    if sslmode not in {"require", "verify-ca", "verify-full"}:
        raise ValueError("backup worker requires PostgreSQL TLS")
    fields = {
        "host": parsed.hostname,
        "port": str(parsed.port or 5432),
        "dbname": unquote(parsed.path.lstrip("/")),
        "user": unquote(parsed.username),
        "password": unquote(parsed.password),
        "sslmode": sslmode,
    }
    root_cert = query.get("sslrootcert", [""])[0]
    if root_cert:
        fields["sslrootcert"] = unquote(root_cert)
    lines = [f"[{service_name}]"]
    for key, value in fields.items():
        if any(character in value for character in ("\r", "\n", "#")):
            raise ValueError("database connection setting cannot be represented safely")
        lines.append(f"{key}={value}")
    return "\n".join(lines) + "\n"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prune_expired_backups(backup_root: Path, retention_days: int, *, now: datetime | None = None) -> int:
    """Delete only backup sets created by this worker and past the approved TTL."""
    root = backup_root.resolve()
    cutoff = (now or datetime.now(UTC)) - timedelta(days=retention_days)
    removed = 0
    for manifest in root.glob("greencity-*.manifest.json"):
        try:
            expired = datetime.fromtimestamp(manifest.stat().st_mtime, UTC) < cutoff
        except OSError:
            continue
        if not expired:
            continue
        stem = manifest.name.removesuffix(".manifest.json")
        for suffix in MANAGED_SUFFIXES:
            target = root / f"{stem}{suffix}"
            if target.parent.resolve() != root:
                continue
            try:
                if target.is_file() or target.is_symlink():
                    target.unlink()
                    removed += 1
            except OSError:
                raise RuntimeError("could not prune an expired backup artifact") from None
    return removed


def create_backup(database_url: str, backup_root: Path = BACKUP_ROOT,
                  evidence_root: Path = EVIDENCE_ROOT) -> dict[str, object]:
    """Create a dump, evidence archive, and checksum manifest atomically."""
    backup_root.mkdir(mode=0o770, parents=True, exist_ok=True)
    os.umask(0o027)
    backup_id = f"greencity-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(4)}"
    stage = Path(tempfile.mkdtemp(prefix=f".{backup_id}-", dir=backup_root))
    service_temp = tempfile.TemporaryDirectory(prefix="greencity-backup-service-")
    service_file = Path(service_temp.name) / "pg_service.conf"
    try:
        service_file.write_text(_database_service(database_url, "greencity_backup"), encoding="utf-8")
        os.chmod(service_file, 0o600)
        client_env = dict(os.environ, PGSERVICEFILE=str(service_file))
        staged_dump = stage / f"{backup_id}.dump"
        staged_evidence = stage / f"{backup_id}.evidence.tar.gz"
        subprocess.run(
            ["pg_dump", "--format=custom", "--no-owner", "--no-privileges",
             "--file", str(staged_dump), "service=greencity_backup"],
            env=client_env, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=3600,
        )
        with tarfile.open(staged_evidence, "w:gz") as archive:
            if evidence_root.exists():
                for path in sorted(evidence_root.rglob("*")):
                    if path.is_file():
                        archive.add(path, arcname=path.relative_to(evidence_root).as_posix(), recursive=False)

        artifacts = {
            "database_dump": {"name": staged_dump.name, "size_bytes": staged_dump.stat().st_size,
                              "sha256": _file_sha256(staged_dump)},
            "private_evidence": {"name": staged_evidence.name, "size_bytes": staged_evidence.stat().st_size,
                                 "sha256": _file_sha256(staged_evidence)},
        }
        manifest = {
            "format_version": 1,
            "backup_id": backup_id,
            "created_at": datetime.now(UTC).isoformat(),
            "artifacts": artifacts,
        }
        staged_manifest = stage / f"{backup_id}.manifest.json"
        staged_manifest.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")

        final_paths = []
        for staged in (staged_dump, staged_evidence, staged_manifest):
            final_path = backup_root / staged.name
            os.replace(staged, final_path)
            final_paths.append(final_path)
        return {"status": "PASS", "backup_id": backup_id,
                "database_bytes": artifacts["database_dump"]["size_bytes"],
                "evidence_bytes": artifacts["private_evidence"]["size_bytes"],
                "manifest": str(final_paths[-1])}
    finally:
        service_temp.cleanup()
        for candidate in sorted(stage.rglob("*"), reverse=True):
            if candidate.is_file() or candidate.is_symlink():
                candidate.unlink(missing_ok=True)
            elif candidate.is_dir():
                candidate.rmdir()
        stage.rmdir()


def main() -> int:
    try:
        retention_days = int(os.getenv("BACKUP_RETENTION_DAYS", ""))
        interval_seconds = int(os.getenv("BACKUP_INTERVAL_SECONDS", ""))
        if not 1 <= retention_days <= 3650 or interval_seconds < 60:
            raise ValueError("backup retention and interval must be explicitly configured")
        database_url = DATABASE_URL_FILE.read_text(encoding="utf-8").strip()
        if not database_url:
            raise ValueError("database secret is empty")
    except Exception:
        print("Backup worker is not configured; provide approved retention, interval, and database secret.")
        return 2

    while True:
        started = time.perf_counter()
        try:
            result = create_backup(database_url)
            removed = prune_expired_backups(BACKUP_ROOT, retention_days)
            result.update({"expired_artifacts_removed": removed,
                           "duration_seconds": round(time.perf_counter() - started, 3)})
            (BACKUP_ROOT / "last-success.json").write_text(
                json.dumps(result, sort_keys=True) + "\n", encoding="utf-8",
            )
            print(json.dumps(result, sort_keys=True), flush=True)
        except Exception as exc:
            # Never print the exception text: subprocess/database errors may carry host or credential context.
            print(json.dumps({"status": "FAILED", "error": type(exc).__name__}), flush=True)
        time.sleep(interval_seconds)


if __name__ == "__main__":
    sys.exit(main())
