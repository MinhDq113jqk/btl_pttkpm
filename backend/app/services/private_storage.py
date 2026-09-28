"""Private evidence operations for the deployment's mounted durable volume."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import secrets


def private_storage_target(storage_root: Path, storage_key: str) -> Path:
    """Resolve a relative object key while rejecting traversal and symlink escape."""
    posix_key = PurePosixPath(storage_key)
    windows_key = PureWindowsPath(storage_key)
    if (not storage_key or posix_key.is_absolute() or windows_key.is_absolute()
            or windows_key.drive or ".." in posix_key.parts or ".." in windows_key.parts):
        raise ValueError("private storage key must be a safe relative path")
    root = storage_root.resolve()
    target = (root / Path(*posix_key.parts)).resolve()
    if root not in target.parents:
        raise ValueError("private storage key escapes its root")
    return target


def write_private_bytes(storage_root: Path, storage_key: str, content: bytes) -> Path:
    """Atomically write for the app owner and its restricted backup group."""
    target = private_storage_target(storage_root, storage_key)
    root = storage_root.resolve()
    root.mkdir(mode=0o750, parents=True, exist_ok=True)
    try:
        os.chmod(root, 0o750)
    except OSError:
        pass
    directory = root
    for component in PurePosixPath(storage_key).parts[:-1]:
        directory = directory / component
        try:
            directory.mkdir(mode=0o750)
        except FileExistsError:
            if not directory.is_dir():
                raise ValueError("private storage path contains a non-directory component") from None
        try:
            os.chmod(directory, 0o750)
        except OSError:
            pass
    temporary = target.with_name(f".{target.name}.{secrets.token_hex(8)}.tmp")
    try:
        with temporary.open("xb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        try:
            os.chmod(temporary, 0o640)
        except OSError:
            pass
        os.replace(temporary, target)
        return target
    finally:
        temporary.unlink(missing_ok=True)


def verified_private_path(
    storage_root: Path,
    storage_key: str,
    expected_sha256: str,
    expected_size_bytes: int | None = None,
) -> Path | None:
    """Return a file only when its size and SHA-256 match the DB manifest."""
    try:
        target = private_storage_target(storage_root, storage_key)
        if not target.is_file():
            return None
        if expected_size_bytes is not None and target.stat().st_size != expected_size_bytes:
            return None
        digest = hashlib.sha256()
        with target.open("rb") as source:
            for chunk in iter(lambda: source.read(64 * 1024), b""):
                digest.update(chunk)
        return target if digest.hexdigest() == expected_sha256 else None
    except (OSError, RuntimeError, ValueError):
        return None
