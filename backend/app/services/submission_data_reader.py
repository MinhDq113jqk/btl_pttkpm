"""Bounded, read-only XLSX reader for the FCS-06 submission pack.

The reader validates the workbook envelope before returning any rows.  It does
not import SQLAlchemy, open a database connection, persist raw cells, or write
an error report.  Callers receive values in memory and must redact before
writing evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Iterator

from openpyxl import load_workbook
from openpyxl.cell.cell import Cell

from app.services.submission_data_contract import (
    GUIDE_SHEET,
    SOURCE_SHEET,
    WORKBOOK_CONTRACTS,
    WorkbookContract,
)


READER_VERSION = "fcs06-r1"
MAX_WORKBOOK_BYTES = 10 * 1024 * 1024
MAX_DATA_ROWS = 10_000
MAX_GUIDE_ROWS = 1_000
MAX_COLUMNS = 64
MAX_CELLS = 500_000
GUIDE_COLUMN_COUNT = 4
ALLOWED_SUFFIX = ".xlsx"


class SubmissionReaderError(ValueError):
    """Stable, redacted reader error; the message never contains a cell value."""

    def __init__(self, code: str, path: str | None = None) -> None:
        self.code = code
        self.path = path
        super().__init__(f"{code}{': ' + path if path else ''}")


@dataclass(frozen=True)
class ReadLimits:
    max_workbook_bytes: int = MAX_WORKBOOK_BYTES
    max_data_rows: int = MAX_DATA_ROWS
    max_guide_rows: int = MAX_GUIDE_ROWS
    max_columns: int = MAX_COLUMNS
    max_cells: int = MAX_CELLS


@dataclass(frozen=True)
class SubmissionWorkbook:
    file_name: str
    source_path: str
    source_sha256: str
    source_size_bytes: int
    data_sheet: str
    guide_sheet: str
    headers: tuple[str, ...]
    rows: tuple[tuple[object, ...], ...]

    @property
    def data_row_count(self) -> int:
        return len(self.rows)


@dataclass(frozen=True)
class SubmissionPack:
    source_dir: str
    workbooks: tuple[SubmissionWorkbook, ...]

    @property
    def total_rows(self) -> int:
        return sum(workbook.data_row_count for workbook in self.workbooks)


def _contract_by_name() -> dict[str, WorkbookContract]:
    return {contract.file_name: contract for contract in WORKBOOK_CONTRACTS}


def _source_path(path: Path, root: Path) -> Path:
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root.resolve(strict=True))
    except (FileNotFoundError, OSError, ValueError):
        raise SubmissionReaderError("SOURCE_PATH_INVALID", path.name) from None
    return resolved


def _read_bounded_bytes(path: Path, limits: ReadLimits) -> bytes:
    """Keep the parsed workbook identical to the bytes checked by the manifest."""

    chunks: list[bytes] = []
    size = 0
    try:
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(64 * 1024), b""):
                size += len(chunk)
                if size > limits.max_workbook_bytes:
                    raise SubmissionReaderError("WORKBOOK_TOO_LARGE", path.name)
                chunks.append(chunk)
    except OSError:
        raise SubmissionReaderError("SOURCE_UNREADABLE", path.name) from None
    if size == 0:
        raise SubmissionReaderError("WORKBOOK_EMPTY", path.name)
    return b"".join(chunks)


def _cell_value(cell: Cell, path: Path) -> object:
    if cell.data_type == "f" or (isinstance(cell.value, str) and cell.value.startswith("=")):
        raise SubmissionReaderError("FORMULA_NOT_ALLOWED", path.name)
    return cell.value


def _read_sheet_rows(
    worksheet,
    *,
    path: Path,
    expected_columns: int,
    max_rows: int,
    limits: ReadLimits,
) -> tuple[tuple[object, ...], ...]:
    if worksheet.max_column > limits.max_columns:
        raise SubmissionReaderError("COLUMN_LIMIT_EXCEEDED", path.name)
    if worksheet.max_row > max_rows + 1:
        raise SubmissionReaderError("ROW_LIMIT_EXCEEDED", path.name)
    if worksheet.max_column != expected_columns:
        raise SubmissionReaderError("COLUMN_COUNT_MISMATCH", path.name)

    rows: list[tuple[object, ...]] = []
    cells_seen = 0
    for row in worksheet.iter_rows(min_row=1, max_row=worksheet.max_row, max_col=worksheet.max_column):
        cells_seen += len(row)
        if cells_seen > limits.max_cells:
            raise SubmissionReaderError("CELL_LIMIT_EXCEEDED", path.name)
        values = tuple(_cell_value(cell, path) for cell in row)
        if all(value is None for value in values):
            continue
        if len(rows) >= max_rows + 1:
            raise SubmissionReaderError("ROW_LIMIT_EXCEEDED", path.name)
        rows.append(values)
    if not rows:
        raise SubmissionReaderError("SHEET_EMPTY", path.name)
    return tuple(rows)


def read_submission_workbook(
    path: str | Path,
    *,
    contract: WorkbookContract | None = None,
    limits: ReadLimits = ReadLimits(),
) -> SubmissionWorkbook:
    """Read one contract workbook after validating its complete envelope."""

    candidate = Path(path)
    contracts = _contract_by_name()
    if contract is None:
        contract = contracts.get(candidate.name)
    if contract is None or candidate.name != contract.file_name:
        raise SubmissionReaderError("WORKBOOK_NOT_ALLOWED", candidate.name)
    if candidate.suffix.lower() != ALLOWED_SUFFIX:
        raise SubmissionReaderError("WORKBOOK_SUFFIX_NOT_ALLOWED", candidate.name)
    root = candidate.parent
    resolved = _source_path(candidate, root)
    source_bytes = _read_bounded_bytes(resolved, limits)
    digest = sha256(source_bytes).hexdigest()
    size = len(source_bytes)
    snapshot = BytesIO(source_bytes)

    try:
        workbook = load_workbook(
            snapshot,
            read_only=True,
            data_only=False,
            # Keep relationship metadata long enough to reject external
            # workbook links before any cell is returned to the caller.
            keep_links=True,
        )
    except Exception:
        snapshot.close()
        raise SubmissionReaderError("WORKBOOK_PARSE_FAILED", candidate.name) from None
    try:
        if getattr(workbook, "vba_archive", None) is not None:
            raise SubmissionReaderError("MACRO_NOT_ALLOWED", candidate.name)
        if getattr(workbook, "_external_links", ()):
            raise SubmissionReaderError("EXTERNAL_LINK_NOT_ALLOWED", candidate.name)
        if tuple(workbook.sheetnames) != (SOURCE_SHEET, GUIDE_SHEET):
            raise SubmissionReaderError("SHEET_SET_MISMATCH", candidate.name)
        for sheet_name in workbook.sheetnames:
            if workbook[sheet_name].sheet_state != "visible":
                raise SubmissionReaderError("HIDDEN_SHEET_NOT_ALLOWED", candidate.name)

        data_rows = _read_sheet_rows(
            workbook[SOURCE_SHEET],
            path=resolved,
            expected_columns=len(contract.fields),
            max_rows=limits.max_data_rows,
            limits=limits,
        )
        guide_rows = _read_sheet_rows(
            workbook[GUIDE_SHEET],
            path=resolved,
            expected_columns=GUIDE_COLUMN_COUNT,
            max_rows=limits.max_guide_rows,
            limits=limits,
        )
        del guide_rows
        headers = tuple(data_rows[0])
        expected_headers = tuple(field.source_name for field in contract.fields)
        if headers != expected_headers or any(not isinstance(header, str) or not header for header in headers):
            raise SubmissionReaderError("HEADER_MISMATCH", candidate.name)
        rows = tuple(data_rows[1:])
        if len(rows) != contract.expected_data_rows:
            raise SubmissionReaderError("ROW_COUNT_MISMATCH", candidate.name)
        if any(len(row) != len(headers) for row in rows):
            raise SubmissionReaderError("ROW_WIDTH_MISMATCH", candidate.name)
        return SubmissionWorkbook(
            file_name=contract.file_name,
            source_path=str(resolved),
            source_sha256=digest,
            source_size_bytes=size,
            data_sheet=SOURCE_SHEET,
            guide_sheet=GUIDE_SHEET,
            headers=headers,
            rows=rows,
        )
    finally:
        workbook.close()
        snapshot.close()


def read_submission_pack(
    source_dir: str | Path,
    *,
    limits: ReadLimits = ReadLimits(),
) -> SubmissionPack:
    """Read exactly the 12 contract workbooks and reject extras/missing files."""

    root = Path(source_dir)
    if not root.is_dir():
        raise SubmissionReaderError("SOURCE_DIR_INVALID", str(root))
    contracts = _contract_by_name()
    try:
        files = tuple(sorted(path for path in root.iterdir() if path.is_file()))
    except OSError:
        raise SubmissionReaderError("SOURCE_DIR_UNREADABLE", str(root)) from None
    names = {path.name for path in files}
    expected = set(contracts)
    missing = expected - names
    extra = names - expected
    if missing:
        raise SubmissionReaderError("WORKBOOK_MISSING", ",".join(sorted(missing)))
    if extra:
        raise SubmissionReaderError("WORKBOOK_EXTRA", ",".join(sorted(extra)))
    workbooks = tuple(
        read_submission_workbook(root / contract.file_name, contract=contract, limits=limits)
        for contract in WORKBOOK_CONTRACTS
    )
    return SubmissionPack(source_dir=str(root.resolve()), workbooks=workbooks)


def iter_submission_rows(pack: SubmissionPack) -> Iterator[tuple[SubmissionWorkbook, int, dict[str, object]]]:
    """Yield 1-based data row numbers and in-memory mappings without persisting them."""

    for workbook in pack.workbooks:
        for row_number, row in enumerate(workbook.rows, start=2):
            yield workbook, row_number, dict(zip(workbook.headers, row, strict=True))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Read-only GreenCity submission XLSX envelope check")
    parser.add_argument("source_dir", type=Path)
    args = parser.parse_args()
    pack = read_submission_pack(args.source_dir)
    print(
        f"FCS06_READER=PASS workbooks={len(pack.workbooks)} "
        f"rows={pack.total_rows} version={READER_VERSION}",
    )
