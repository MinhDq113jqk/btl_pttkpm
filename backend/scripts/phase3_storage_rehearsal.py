"""Exercise private-evidence durability, checksum and tenant-path boundaries.

The rehearsal uses a temporary directory by default and never deletes a caller
supplied path. It models the mounted durable volume used by deploy/compose.yml.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import os
import secrets
import sys
import tempfile
import time
from zipfile import ZIP_DEFLATED, ZipFile


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _target(root: Path, key: str) -> Path:
    resolved_root = root.resolve()
    target = (resolved_root / key).resolve()
    if resolved_root not in target.parents:
        raise ValueError("storage key escapes the private storage root")
    return target


def run_rehearsal(storage_root: Path, backup_root: Path, restore_root: Path) -> dict[str, object]:
    token = secrets.token_hex(5)
    storage_root = storage_root.resolve()
    backup_root = backup_root.resolve()
    restore_root = restore_root.resolve()
    storage_root.mkdir(parents=True, exist_ok=True)
    backup_root.mkdir(parents=True, exist_ok=True)
    restore_root.mkdir(parents=True, exist_ok=True)

    samples = {
        f"tenant-a/site-1/{token}/evidence.bin": b"tenant-a-private-evidence",
        f"tenant-b/site-1/{token}/evidence.bin": b"tenant-b-private-evidence",
    }
    manifest: list[dict[str, object]] = []
    captured_at = time.time()
    for key, content in samples.items():
        destination = _target(storage_root, key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        try:
            os.chmod(destination, 0o600)
        except OSError:
            pass
        manifest.append({"key": key, "size_bytes": len(content), "sha256": _sha256(content)})

    backup_path = backup_root / f"private-evidence-{token}.zip"
    backup_started = time.perf_counter()
    with ZipFile(backup_path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps({"captured_at": captured_at, "objects": manifest}, sort_keys=True))
        for item in manifest:
            archive.write(_target(storage_root, str(item["key"])), arcname=str(item["key"]))
    backup_ms = (time.perf_counter() - backup_started) * 1000

    restore_started = time.perf_counter()
    with ZipFile(backup_path) as archive:
        restored_manifest = json.loads(archive.read("manifest.json"))
        for member in archive.namelist():
            if member == "manifest.json":
                continue
            destination = _target(restore_root, member)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.read(member))
    restore_ms = (time.perf_counter() - restore_started) * 1000

    for item in restored_manifest["objects"]:
        content = _target(restore_root, str(item["key"])).read_bytes()
        if len(content) != item["size_bytes"] or _sha256(content) != item["sha256"]:
            raise RuntimeError("restored evidence checksum mismatch")
    try:
        _target(storage_root, "../tenant-b/escape.bin")
    except ValueError:
        traversal_denied = True
    else:
        traversal_denied = False
    if not traversal_denied:
        raise RuntimeError("tenant storage traversal was not rejected")

    return {
        "status": "PASS",
        "objects": len(manifest),
        "checksum": "PASS",
        "tenant_path_isolation": "PASS",
        "backup_ms": round(backup_ms, 1),
        "restore_ms": round(restore_ms, 1),
        "rpo_observed_seconds": round(max(0.0, time.time() - captured_at), 3),
        "rto_observed_seconds": round(restore_ms / 1000, 3),
        "backup_archive": str(backup_path),
        "filesystem_encryption": "delegated to encrypted deployment volume/provider policy",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--storage-root", type=Path)
    parser.add_argument("--backup-root", type=Path)
    parser.add_argument("--restore-root", type=Path)
    args = parser.parse_args()
    if os.getenv("PHASE3_STORAGE_REHEARSAL") != "1":
        print("Set PHASE3_STORAGE_REHEARSAL=1 for the disposable storage rehearsal.")
        return 2
    temporary = None
    try:
        if args.storage_root and args.backup_root and args.restore_root:
            roots = (args.storage_root, args.backup_root, args.restore_root)
        else:
            temporary = tempfile.TemporaryDirectory(prefix="greencity-phase3-storage-")
            root = Path(temporary.name)
            roots = (root / "storage", root / "backup", root / "restore")
        print(json.dumps(run_rehearsal(*roots), sort_keys=True))
        return 0
    except Exception:
        print("Storage rehearsal failed; details suppressed.")
        return 1
    finally:
        if temporary is not None:
            temporary.cleanup()


if __name__ == "__main__":
    sys.exit(main())
