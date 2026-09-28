from datetime import UTC, datetime, timedelta
import importlib.util
import os
from pathlib import Path


BACKUP_WORKER = Path(__file__).resolve().parents[2] / "deploy" / "backup_loop.py"
SPEC = importlib.util.spec_from_file_location("phase3_backup_loop", BACKUP_WORKER)
backup_loop = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(backup_loop)


def test_retention_removes_only_expired_generated_backup_sets(tmp_path):
    now = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)
    expired_manifest = tmp_path / "greencity-old.manifest.json"
    expired_dump = tmp_path / "greencity-old.dump"
    expired_evidence = tmp_path / "greencity-old.evidence.tar.gz"
    current_manifest = tmp_path / "greencity-current.manifest.json"
    unrelated = tmp_path / "keep-me.txt"
    for path in (expired_manifest, expired_dump, expired_evidence, current_manifest, unrelated):
        path.write_text("fixture", encoding="utf-8")
    old_timestamp = (now - timedelta(days=31)).timestamp()
    os.utime(expired_manifest, (old_timestamp, old_timestamp))

    removed = backup_loop.prune_expired_backups(tmp_path, 30, now=now)

    assert removed == 3
    assert not expired_manifest.exists()
    assert not expired_dump.exists()
    assert not expired_evidence.exists()
    assert current_manifest.exists()
    assert unrelated.read_text(encoding="utf-8") == "fixture"
