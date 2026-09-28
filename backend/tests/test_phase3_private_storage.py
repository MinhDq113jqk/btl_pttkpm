import hashlib
import os

import pytest

from app.services.private_storage import (
    private_storage_target,
    verified_private_path,
    write_private_bytes,
)


def test_private_file_is_atomic_restricted_and_checksum_verified(tmp_path):
    content = b"phase 3 private evidence"
    digest = hashlib.sha256(content).hexdigest()

    target = write_private_bytes(tmp_path, "tenant-a/site-1/evidence.bin", content)

    assert target.read_bytes() == content
    assert verified_private_path(tmp_path, "tenant-a/site-1/evidence.bin", digest, len(content)) == target
    assert verified_private_path(tmp_path, "tenant-a/site-1/evidence.bin", "0" * 64, len(content)) is None
    assert verified_private_path(tmp_path, "tenant-a/site-1/evidence.bin", digest, len(content) + 1) is None
    if os.name != "nt":
        assert target.stat().st_mode & 0o777 == 0o640
        assert (tmp_path / "tenant-a").stat().st_mode & 0o777 == 0o750
        assert (tmp_path / "tenant-a" / "site-1").stat().st_mode & 0o777 == 0o750


@pytest.mark.parametrize("key", ["../outside.bin", "tenant/../../outside.bin", r"C:\outside.bin", r"..\outside.bin"])
def test_private_file_rejects_traversal(tmp_path, key):
    with pytest.raises(ValueError):
        private_storage_target(tmp_path, key)


def test_private_file_rejects_symlink_escape(tmp_path):
    outside = tmp_path.parent / "outside-evidence.bin"
    outside.write_bytes(b"outside")
    link = tmp_path / "tenant-link"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is not available in this Windows test context")
    assert verified_private_path(tmp_path, "tenant-link", hashlib.sha256(b"outside").hexdigest()) is None
