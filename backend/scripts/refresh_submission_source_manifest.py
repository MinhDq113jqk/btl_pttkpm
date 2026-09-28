"""Refresh metadata-only source checksums after an owner edits the raw XLSX files."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
from uuid import uuid4

from openpyxl import load_workbook

from app.services.submission_data_contract import GUIDE_SHEET, SOURCE_SHEET
from app.services.submission_data_reader import SubmissionReaderError, read_submission_pack
from scripts.submission_data_preflight import run_preflight


class SourceManifestError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _sheet_metadata(path: Path, sheet_name: str, role: str) -> dict[str, object]:
    workbook = load_workbook(path, read_only=True, data_only=False, keep_links=True)
    try:
        rows = workbook[sheet_name].values
        nonempty = ((index, tuple(row)) for index, row in enumerate(rows, start=1)
                    if any(value is not None for value in row))
        header_index, header = next(nonempty)
        if header_index != 1:
            raise SourceManifestError("HEADER_ROW_MOVED")
        row_count = sum(1 for _ in nonempty)
        header_bytes = json.dumps(header, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return {
            "sheet_name": sheet_name,
            "sheet_role": role,
            "header_row_index": 1,
            "header_column_count": len(header),
            "header_sha256": sha256(header_bytes).hexdigest(),
            "data_row_count": row_count,
        }
    except StopIteration:
        raise SourceManifestError("SHEET_EMPTY") from None
    finally:
        workbook.close()


def build_manifest(source_dir: Path) -> dict[str, object]:
    pack = read_submission_pack(source_dir)
    entries = []
    for item in pack.workbooks:
        path = source_dir / item.file_name
        data_sheet = _sheet_metadata(path, SOURCE_SHEET, "data")
        guide_sheet = _sheet_metadata(path, GUIDE_SHEET, "guidance")
        if data_sheet["data_row_count"] != item.data_row_count:
            raise SourceManifestError("ROW_COUNT_MISMATCH")
        entries.append({
            "file_name": item.file_name,
            "sha256": item.source_sha256,
            "size_bytes": item.source_size_bytes,
            "observed_schema_version": "raw-inventory-v1",
            "sheets": [data_sheet, guide_sheet],
        })
    return {
        "manifest_format_version": "1.0",
        "provenance_reference": {
            "document": "DATA_PROVENANCE.md",
            "source_id": "greencity-excel-data",
            "classification": "RESTRICTED_REAL_LOCAL_ONLY",
        },
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "counting_convention": "data_row_count excludes the first non-empty header row in each sheet",
        "workbooks": entries,
        "summary": {"workbook_count": len(entries), "data_row_count": pack.total_rows},
        "redaction_assertions": {
            "contains_cell_values": False,
            "contains_header_strings": False,
            "contains_absolute_paths": False,
            "contains_workbook_properties": False,
            "contains_reverse_mapping": False,
        },
    }


def _same_source_metadata(current: dict[str, object], candidate: dict[str, object]) -> bool:
    return all(current.get(key) == candidate[key] for key in (
        "manifest_format_version", "provenance_reference", "counting_convention",
        "workbooks", "summary", "redaction_assertions",
    ))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args()
    try:
        candidate = build_manifest(args.source)
        if args.check:
            current = json.loads(args.manifest.read_text(encoding="utf-8"))
            status = "PASS" if _same_source_metadata(current, candidate) else "STALE"
            print(f"FCS02_MANIFEST={status} workbooks={candidate['summary']['workbook_count']} rows={candidate['summary']['data_row_count']}")
            return 0 if status == "PASS" else 2
        preflight = run_preflight(args.source, as_of_utc=datetime.now(UTC))
        if preflight.status != "PASS" or preflight.orphan_count or preflight.future_terminal_candidates:
            raise SourceManifestError("PREFLIGHT_BLOCKED")
        temporary = args.manifest.with_name(f".{args.manifest.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            verified = run_preflight(args.source, as_of_utc=datetime.now(UTC), manifest_path=temporary)
            if verified.status != "PASS" or not verified.source_checksum_verified:
                raise SourceManifestError("MANIFEST_VERIFY_FAILED")
            os.replace(temporary, args.manifest)
        finally:
            temporary.unlink(missing_ok=True)
        print(f"FCS02_MANIFEST=UPDATED workbooks={candidate['summary']['workbook_count']} rows={candidate['summary']['data_row_count']}")
        return 0
    except (SourceManifestError, SubmissionReaderError, OSError, ValueError, KeyError, TypeError) as error:
        print(f"FCS02_MANIFEST=FAIL code={getattr(error, 'code', 'MANIFEST_ERROR')}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
