"""Measure a local PostgreSQL dump/restore and private-evidence restore.

Database operations require loopback URLs and an explicit opt-in. The restore
database must be an empty disposable database prepared by the operator.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time

from sqlalchemy.engine import make_url
import psycopg
from psycopg import sql

from scripts.phase3_storage_rehearsal import run_rehearsal


def _loopback(raw: str) -> bool:
    return bool(raw) and make_url(raw).host in {"127.0.0.1", "localhost", "::1"}


def _run(command: list[str], timeout: int = 300, env: dict[str, str] | None = None) -> None:
    result = subprocess.run(command, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                            errors="replace", timeout=timeout)
    if result.returncode:
        if env and env.get("PHASE3_VERBOSE") == "1":
            print(f"backup command {Path(command[0]).name} exited {result.returncode}")
            print((result.stdout or "")[-2000:])
        raise RuntimeError("backup command failed")


def _service_entry(name: str, database_url: str) -> str:
    parsed = make_url(database_url)
    values = {
        "host": parsed.host or "",
        "port": str(parsed.port or 5432),
        "dbname": parsed.database or "",
        "user": parsed.username or "",
        "password": parsed.password or "",
        "sslmode": dict(parsed.query).get("sslmode", "require"),
    }
    root_cert = dict(parsed.query).get("sslrootcert", "")
    if root_cert:
        values["sslrootcert"] = root_cert
    lines = [f"[{name}]"]
    for key, value in values.items():
        if any(character in value for character in ("\r", "\n", "#")):
            raise ValueError("connection setting cannot be represented in the temporary libpq service file")
        lines.append(f"{key}={value}")
    return "\n".join(lines) + "\n"


def _database_integrity(database_url: str) -> dict[str, object]:
    """Build structural metadata and per-table logical row checksums."""
    with psycopg.connect(database_url) as connection:
        columns = connection.execute(
            """SELECT table_name, column_name, data_type, udt_name,
                      is_nullable, character_maximum_length, numeric_precision, numeric_scale
               FROM information_schema.columns WHERE table_schema = 'greencity'
               ORDER BY table_name, column_name"""
        ).fetchall()
        constraints = connection.execute(
            """SELECT conrelid::regclass::text, conname, contype, convalidated,
                      condeferrable, condeferred,
                      ARRAY(SELECT a.attname FROM unnest(c.conkey) WITH ORDINALITY AS k(attnum, position)
                            JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
                            ORDER BY k.position),
                      confrelid::regclass::text,
                      ARRAY(SELECT a.attname FROM unnest(c.confkey) WITH ORDINALITY AS k(attnum, position)
                            JOIN pg_attribute a ON a.attrelid = c.confrelid AND a.attnum = k.attnum
                            ORDER BY k.position),
                      confupdtype, confdeltype, confmatchtype
               FROM pg_constraint c WHERE connamespace = 'greencity'::regnamespace
               ORDER BY conrelid::regclass::text, conname"""
        ).fetchall()
        indexes = connection.execute(
            """SELECT i.indexrelid::regclass::text, i.indisunique, i.indisprimary, i.indisvalid,
                      i.indnkeyatts, i.indnatts,
                      ARRAY(SELECT COALESCE(a.attname, '')
                            FROM unnest(i.indkey::smallint[]) WITH ORDINALITY AS k(attnum, position)
                            LEFT JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.attnum
                            ORDER BY k.position),
                      i.indpred IS NOT NULL, i.indexprs IS NOT NULL
               FROM pg_index i WHERE i.indrelid IN (
                   SELECT c.oid FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                   WHERE n.nspname = 'greencity'
               ) ORDER BY i.indexrelid::regclass::text"""
        ).fetchall()
        triggers = connection.execute(
            """SELECT t.tgname, c.relname, t.tgtype, t.tgenabled, t.tgfoid::regprocedure::text
               FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
               JOIN pg_namespace n ON n.oid = c.relnamespace
               WHERE n.nspname = 'greencity' AND NOT t.tgisinternal
               ORDER BY t.tgname"""
        ).fetchall()
        tables = connection.execute(
            """SELECT table_name FROM information_schema.tables
               WHERE table_schema = 'greencity' AND table_type = 'BASE TABLE'
               ORDER BY table_name"""
        ).fetchall()
        sequences = connection.execute(
            """SELECT schemaname, sequencename, data_type, start_value, min_value,
                      max_value, increment_by, cycle, cache_size
               FROM pg_sequences WHERE schemaname = 'greencity'
               ORDER BY schemaname, sequencename"""
        ).fetchall()
        row_checksums: dict[str, str] = {}
        row_counts: dict[str, int] = {}
        for (table_name,) in tables:
            schema_identifier = sql.Identifier("greencity")
            table_identifier = sql.Identifier(table_name)
            row_counts[table_name] = connection.execute(
                sql.SQL("SELECT count(*) FROM {}.{}").format(schema_identifier, table_identifier)
            ).fetchone()[0]
            statement = sql.SQL(
                "COPY (SELECT to_jsonb(row_data)::text FROM {}.{} AS row_data "
                "ORDER BY to_jsonb(row_data)::text) TO STDOUT"
            ).format(schema_identifier, table_identifier)
            digest = sha256()
            with connection.cursor().copy(statement) as copy:
                for block in copy:
                    digest.update(block)
            row_checksums[table_name] = digest.hexdigest()
    structure = {
        "columns": columns,
        "constraints": constraints,
        "indexes": indexes,
        "triggers": triggers,
        "sequences": sequences,
        "tables": [name for (name,) in tables],
    }
    for component in ("columns", "constraints", "indexes", "triggers", "sequences"):
        structure[component] = sorted(
            structure[component],
            key=lambda row: json.dumps(row, ensure_ascii=True, sort_keys=True, default=str),
        )
    canonical = json.dumps(structure, ensure_ascii=True, sort_keys=True, default=str)
    return {
        "schema_sha256": sha256(canonical.encode("utf-8")).hexdigest(),
        "rows_sha256": sha256(json.dumps(row_checksums, sort_keys=True).encode("utf-8")).hexdigest(),
        "schema_components": structure,
        "row_counts": row_counts,
        "table_count": len(tables),
        "row_count": sum(row_counts.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", ""))
    parser.add_argument("--restore-database-url", default=os.getenv("PHASE3_RESTORE_DATABASE_URL", ""))
    parser.add_argument("--database-url-file", type=Path)
    parser.add_argument("--control-database-url-file", type=Path)
    parser.add_argument("--restore-database-url-file", type=Path)
    parser.add_argument("--pg-bin", type=Path)
    parser.add_argument("--storage-root", type=Path)
    parser.add_argument("--backup-root", type=Path)
    parser.add_argument("--restore-root", type=Path)
    args = parser.parse_args()
    if args.database_url_file:
        args.database_url = args.database_url_file.read_text(encoding="utf-8").strip()
    args.control_database_url = args.database_url
    if args.control_database_url_file:
        args.control_database_url = args.control_database_url_file.read_text(encoding="utf-8").strip()
    if args.restore_database_url_file:
        args.restore_database_url = args.restore_database_url_file.read_text(encoding="utf-8").strip()
    if os.getenv("PHASE3_BACKUP_REHEARSAL") != "1":
        print("Set PHASE3_BACKUP_REHEARSAL=1 for the disposable backup rehearsal.")
        return 2

    result: dict[str, object] = {"status": "PASS"}
    temporary = tempfile.TemporaryDirectory(prefix="greencity-phase3-backup-")
    stage = "initialization"
    try:
        if args.storage_root and args.backup_root and args.restore_root:
            storage_result = run_rehearsal(args.storage_root, args.backup_root, args.restore_root)
            result["storage"] = storage_result
        if args.database_url or args.restore_database_url or args.pg_bin:
            if not (_loopback(args.database_url) and _loopback(args.control_database_url)
                    and _loopback(args.restore_database_url) and args.pg_bin):
                print("Database backup requires loopback source/control/restore URLs and --pg-bin; no shared DB was used.")
                return 2
            pg_dump = args.pg_bin / ("pg_dump.exe" if os.name == "nt" else "pg_dump")
            pg_restore = args.pg_bin / ("pg_restore.exe" if os.name == "nt" else "pg_restore")
            if not pg_dump.is_file() or not pg_restore.is_file():
                print("pg_dump and pg_restore are required; details suppressed.")
                return 2
            archive = Path(temporary.name) / "greencity.dump"
            marker_name = f"phase3_restore_marker_{secrets.token_hex(6)}"
            stage = "source marker transaction"
            with psycopg.connect(args.control_database_url) as connection:
                connection.execute("SET ROLE greencity_owner")
                connection.execute(sql.SQL(
                    "CREATE TABLE greencity.{} (marker text PRIMARY KEY, committed_at timestamptz NOT NULL DEFAULT now())"
                ).format(sql.Identifier(marker_name)))
                connection.execute(sql.SQL(
                    "INSERT INTO greencity.{} (marker) VALUES ('latest-committed-before-backup')"
                ).format(sql.Identifier(marker_name)))
            service_file = Path(temporary.name) / "pg_service.conf"
            service_file.write_text(
                _service_entry("phase3_source", args.database_url)
                + _service_entry("phase3_restore", args.restore_database_url),
                encoding="utf-8",
            )
            try:
                os.chmod(service_file, 0o600)
            except OSError:
                pass
            service_env = dict(os.environ, PGSERVICEFILE=str(service_file))
            stage = "pg_dump"
            backup_started = time.perf_counter()
            _run([str(pg_dump), "--format=custom", "--no-owner", "--file", str(archive),
                  "service=phase3_source"], env=service_env)
            backup_ms = (time.perf_counter() - backup_started) * 1000
            stage = "pg_restore"
            restore_started = time.perf_counter()
            _run([str(pg_restore), "--exit-on-error", "--no-owner", "--dbname",
                  "service=phase3_restore", str(archive)], env=service_env)
            restore_ms = (time.perf_counter() - restore_started) * 1000
            stage = "database structure and data checksum comparison"
            source_integrity = _database_integrity(args.control_database_url)
            restore_integrity = _database_integrity(args.restore_database_url)
            stage = "restored database integrity marker"
            with psycopg.connect(args.restore_database_url) as connection:
                connection.execute("SELECT 1")
                marker = connection.execute(sql.SQL(
                    "SELECT marker FROM greencity.{}"
                ).format(sql.Identifier(marker_name))).fetchone()[0]
                if marker != "latest-committed-before-backup":
                    raise RuntimeError("the committed restore marker is missing")
            restore_ms = (time.perf_counter() - restore_started) * 1000
            result["database"] = {
                "dump_restore": "PASS",
                "schema_integrity": "PASS" if source_integrity["schema_sha256"] == restore_integrity["schema_sha256"] else "FAIL",
                "row_integrity": "PASS" if source_integrity["rows_sha256"] == restore_integrity["rows_sha256"] else "FAIL",
                "tables_verified": source_integrity["table_count"],
                "rows_verified": source_integrity["row_count"],
                "backup_ms": round(backup_ms, 1),
                "restore_ms": round(restore_ms, 1),
                "rpo_observed_seconds": 0.0,
                "rto_observed_seconds": round(restore_ms / 1000, 3),
                "latest_committed_marker": "restored",
            }
            stage = "source marker cleanup"
            with psycopg.connect(args.control_database_url) as connection:
                connection.execute("SET ROLE greencity_owner")
                connection.execute(sql.SQL("DROP TABLE greencity.{}").format(sql.Identifier(marker_name)))
            if (source_integrity["schema_sha256"] != restore_integrity["schema_sha256"]
                    or source_integrity["rows_sha256"] != restore_integrity["rows_sha256"]):
                if os.getenv("PHASE3_VERBOSE") == "1":
                    print(f"schema integrity: {source_integrity['schema_sha256'] == restore_integrity['schema_sha256']}")
                    print(f"row integrity: {source_integrity['rows_sha256'] == restore_integrity['rows_sha256']}")
                    for component in ("columns", "constraints", "indexes", "triggers", "sequences", "tables"):
                        source_values = source_integrity["schema_components"][component]
                        restore_values = restore_integrity["schema_components"][component]
                        if source_values != restore_values:
                            print(f"schema component differs: {component}; source={len(source_values)} restore={len(restore_values)}")
                            for index, (source_item, restore_item) in enumerate(zip(source_values, restore_values)):
                                if source_item != restore_item:
                                    print(f"first mismatch at {index}: source={source_item} restore={restore_item}")
                                    break
                return 1
        if len(result) == 1:
            print("Provide storage paths or database arguments for the rehearsal.")
            return 2
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:
        if os.getenv("PHASE3_VERBOSE") == "1":
            diagnostic = str(exc).replace(args.database_url, "[REDACTED]")
            diagnostic = diagnostic.replace(args.restore_database_url, "[REDACTED]")
            print(f"backup rehearsal diagnostic at {stage}: {type(exc).__name__}: {diagnostic[-2000:]}")
        print("Backup/restore rehearsal failed; details suppressed and no shared DB was used.")
        return 1
    finally:
        temporary.cleanup()


if __name__ == "__main__":
    sys.exit(main())
