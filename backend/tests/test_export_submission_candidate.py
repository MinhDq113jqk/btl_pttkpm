"""The exported demo contains only the canonical synthetic workbook set."""

from pathlib import Path, PurePosixPath
from types import SimpleNamespace

import pytest

from scripts import export_submission_candidate as exporter


def _fake_git(monkeypatch, root: Path, names: set[PurePosixPath]) -> None:
    monkeypatch.setattr(exporter, "ROOT", root)
    for name in names:
        target = root.joinpath(*name.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"fixture")
    listing = b"\0".join(name.as_posix().encode() for name in sorted(names)) + b"\0"
    monkeypatch.setattr(
        exporter.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=listing),
    )


def test_canonical_synthetic_workbook_set_is_accepted(tmp_path, monkeypatch):
    _fake_git(monkeypatch, tmp_path, set(exporter.SYNTHETIC_WORKBOOKS))
    paths, deleted = exporter.candidate_paths()
    assert len(paths) == 12
    assert deleted == 0


@pytest.mark.parametrize("extra", [
    "backend/tests/fixtures/submission_data/synthetic/13_extra.xlsx",
    "backend/tests/fixtures/submission_data/synthetic/nested/01_cong_viec.xlsx",
    "backend/tests/fixtures/submission_data/other/01_cong_viec.xlsx",
])
def test_extra_or_nested_spreadsheet_is_rejected(tmp_path, monkeypatch, extra):
    names = set(exporter.SYNTHETIC_WORKBOOKS) | {PurePosixPath(extra)}
    _fake_git(monkeypatch, tmp_path, names)
    with pytest.raises(ValueError, match="Spreadsheet outside allowlisted"):
        exporter.candidate_paths()


def test_missing_canonical_workbook_is_rejected(tmp_path, monkeypatch):
    names = set(exporter.SYNTHETIC_WORKBOOKS)
    names.remove(next(iter(names)))
    _fake_git(monkeypatch, tmp_path, names)
    with pytest.raises(ValueError, match="missing canonical synthetic workbooks"):
        exporter.candidate_paths()


def test_historical_machine_logs_are_not_exported(tmp_path, monkeypatch):
    evidence = PurePosixPath("documents/greencity-project/phase-3/evidence")
    summary = evidence / "FCS-16-20_EXECUTION_EVIDENCE.md"
    local_outputs = {
        evidence / "n1-clean-clone/npm-ci.log",
        evidence / "n6-n10/https-recovery.result",
        evidence / "n1-clean-clone/copy-result.txt",
    }
    _fake_git(
        monkeypatch,
        tmp_path,
        set(exporter.SYNTHETIC_WORKBOOKS) | local_outputs | {summary},
    )
    paths, deleted = exporter.candidate_paths()
    assert deleted == 0
    assert summary in {PurePosixPath(*path.parts) for path in paths}
    assert not local_outputs.intersection(PurePosixPath(*path.parts) for path in paths)
