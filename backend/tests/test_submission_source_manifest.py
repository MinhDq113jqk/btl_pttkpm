"""Source manifest regeneration emits metadata and never workbook cell values."""

import json
from pathlib import Path

from scripts.refresh_submission_source_manifest import build_manifest, _same_source_metadata


SYNTHETIC = Path(__file__).parent / "fixtures" / "submission_data" / "synthetic"


def test_manifest_rebuild_uses_only_workbook_metadata():
    manifest = build_manifest(SYNTHETIC)
    assert manifest["summary"] == {"workbook_count": 12, "data_row_count": 101}
    assert all(entry["sha256"] and entry["size_bytes"] > 0 for entry in manifest["workbooks"])
    serialized = json.dumps(manifest, ensure_ascii=False)
    assert "Synthetic Account" not in serialized
    assert "example.invalid" not in serialized
    assert "SYN-WORK" not in serialized
    assert all(value is False for value in manifest["redaction_assertions"].values())


def test_manifest_staleness_ignores_generation_time_but_checks_hashes():
    candidate = build_manifest(SYNTHETIC)
    current = json.loads(json.dumps(candidate))
    current["generated_at_utc"] = "2000-01-01T00:00:00Z"
    assert _same_source_metadata(current, candidate)
    current["workbooks"][0]["sha256"] = "0" * 64
    assert not _same_source_metadata(current, candidate)
