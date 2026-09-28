"""Export an exact working-tree submission candidate without local data."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.services.submission_data_contract import WORKBOOK_CONTRACTS  # noqa: E402

SYNTHETIC_ROOT = PurePosixPath("backend/tests/fixtures/submission_data/synthetic")
HISTORICAL_EVIDENCE_ROOT = PurePosixPath("documents/greencity-project/phase-3/evidence")
SYNTHETIC_WORKBOOKS = frozenset(
    SYNTHETIC_ROOT / workbook.file_name for workbook in WORKBOOK_CONTRACTS
)
if len(SYNTHETIC_WORKBOOKS) != 12:
    raise ValueError("Canonical synthetic workbook contract must contain 12 unique files")
FORBIDDEN_PARTS = {
    ".git", ".local", ".venv", ".pytest_cache", ".test-runtime", ".review",
    "__pycache__", "node_modules", "dist", "excel-data", "data_that",
    "local_validation_pack", "approved_pack",
}


def candidate_paths() -> tuple[list[Path], int]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    names = [os.fsdecode(name) for name in result.stdout.split(b"\0") if name]
    files: list[Path] = []
    deleted_count = 0
    for name in sorted(set(names)):
        relative = PurePosixPath(name.replace("\\", "/"))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Unsafe Git candidate path")
        if any(
            part in FORBIDDEN_PARTS
            or part.startswith(".pytest-temp")
            or part.startswith(".approved_pack_tmp_")
            for part in relative.parts
        ):
            raise ValueError("Forbidden local directory in candidate")
        if relative.name in {"local_validation_manifest.json", "approved_manifest.json"}:
            raise ValueError("Raw-derived manifest in candidate")
        if relative.name == ".env" or (
            relative.name.startswith(".env.") and not relative.name.endswith(".example")
        ):
            raise ValueError("Local environment file in candidate")
        if relative.suffix.lower() in {".pyc", ".pyo"}:
            raise ValueError("Generated file in candidate")
        if relative.suffix.lower() in {".log", ".result"} or (
            relative.is_relative_to(HISTORICAL_EVIDENCE_ROOT)
            and relative.suffix.lower() == ".txt"
        ):
            # Historical machine logs can contain local paths and environment
            # details. Their reviewed Markdown summaries remain in the package.
            continue
        source = ROOT.joinpath(*relative.parts)
        if not source.exists() and not source.is_symlink():
            deleted_count += 1
            continue
        if relative.suffix.lower() in {".xlsx", ".xls", ".xlsm", ".xlsb", ".ods"}:
            if relative not in SYNTHETIC_WORKBOOKS:
                raise ValueError("Spreadsheet outside allowlisted synthetic fixture path")
        if relative.suffix.lower() == ".csv" and relative.as_posix() != (
            "backend/tests/fixtures/submission_data/synthetic_scale_200_units.csv"
        ):
            raise ValueError("CSV outside allowlisted synthetic fixture path")
        if not source.resolve().is_relative_to(ROOT.resolve()):
            raise ValueError("Git candidate path resolves outside repository")
        if source.is_symlink() or not source.is_file():
            raise ValueError("Non-regular Git candidate path")
        files.append(Path(*relative.parts))
    present = {PurePosixPath(*relative.parts) for relative in files}
    if not SYNTHETIC_WORKBOOKS.issubset(present):
        raise ValueError("Candidate is missing canonical synthetic workbooks")
    return files, deleted_count


def export(destination: Path) -> dict[str, object]:
    destination = destination.resolve()
    if destination.exists():
        raise FileExistsError("Candidate destination already exists")
    files, deleted_count = candidate_paths()
    destination.mkdir(parents=True)
    digest = hashlib.sha256()
    for relative in files:
        source = ROOT / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        content_digest = hashlib.sha256(target.read_bytes()).hexdigest()
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(content_digest.encode("ascii"))
        digest.update(b"\0")
    return {
        "file_count": len(files),
        "deleted_tracked_count": deleted_count,
        "candidate_sha256": digest.hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.destination), sort_keys=True))


if __name__ == "__main__":
    main()
