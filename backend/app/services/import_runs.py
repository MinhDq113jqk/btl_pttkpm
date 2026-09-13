"""Durable, scoped CSV import runs for Units.

The legacy JSON ``/units/import`` receipt remains available.  This module owns
the file-backed upload -> mapping -> preview -> apply flow without accepting
tenant, role, site, or database IDs from the client.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
from pathlib import Path, PureWindowsPath
import re
from uuid import UUID, uuid4

from fastapi import Request
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.policy import UserContext, scope_not_found
from app.core.security import create_token, decode_token
from app.models.building import Building
from app.models.enums import UnitStatusEnum
from app.models.import_run import ImportRun, ImportRunRow
from app.models.platform import AuditEvent, DomainEvent, IdempotencyRecord
from app.models.site import Site
from app.models.unit import Unit
from app.schemas.import_run import (
    ImportRowIssue,
    ImportRunApplyRequest,
    ImportRunPreviewRequest,
    ImportRunView,
    UnitCsvMapping,
)


IMPORT_RUN_ROLES = ("admin", "cskh")
UPLOAD_OPERATION = "import-run.upload.v1"
PREVIEW_OPERATION = "import-run.preview.v1"
APPLY_OPERATION = "import-run.apply.v1"
RESOURCE_TYPE = "ImportRun"
MAX_IMPORT_CSV_BYTES = 10 * 1024 * 1024
MAX_IMPORT_ROWS = 10_000
MAX_IMPORT_COLUMNS = 32
MAX_CSV_FIELD_CHARS = 4_096
MAX_SOURCE_FILENAME_CHARS = 200
FILE_HASH_CHUNK_BYTES = 64 * 1024
SAFE_KEY = re.compile(r"[A-Za-z0-9._:-]{8,128}")
SAFE_CODE = re.compile(r"[A-Z0-9][A-Z0-9._/-]{0,49}")
ALLOWED_CSV_MIME_TYPES = frozenset({"text/csv", "application/csv", "application/vnd.ms-excel"})
ALLOWED_UNIT_STATUSES = frozenset(status.value for status in UnitStatusEnum)
MAX_AREA_M2 = Decimal("100000")


class CsvFormatError(ValueError):
    """The stored bytes cannot be interpreted as the supported CSV envelope."""


@dataclass(frozen=True)
class ParsedCsvRow:
    row_number: int
    values: dict[str, str]
    structural_issue: ImportRowIssue | None = None


@dataclass(frozen=True)
class ParsedCsv:
    headers: tuple[str, ...]
    rows: tuple[ParsedCsvRow, ...]


@dataclass(frozen=True)
class Candidate:
    row_number: int
    unit_number: str
    floor: int
    area_m2: float
    status: str


@dataclass(frozen=True)
class RowResult:
    row_number: int
    status: str
    issues: tuple[ImportRowIssue, ...]
    candidate: Candidate | None = None


@dataclass(frozen=True)
class ImportRunExecution:
    run: ImportRun
    replayed: bool
    replay_body: dict | None = None
    cleanup_error_key: str | None = None
    new_error_key: str | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def _correlation_id(request: Request) -> UUID:
    try:
        return UUID(str(getattr(request.state, "correlation_id", None)))
    except (TypeError, ValueError):
        return uuid4()


def _payload_hash(payload: object) -> str:
    try:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AppError("ERR-VALIDATION", "Dữ liệu yêu cầu không hợp lệ.", 422) from exc
    return hashlib.sha256(encoded).hexdigest()


def _validate_idempotency_key(value: str | None) -> str:
    if value is None or SAFE_KEY.fullmatch(value) is None:
        raise AppError("ERR-IDEMPOTENCY-KEY", "Idempotency-Key phải dài 8-128 ký tự an toàn.", 400)
    return value


def _issue(code: str, column: str | None, message: str) -> ImportRowIssue:
    return ImportRowIssue(code=code, column=column, message=message)


def _normalise_building_code(value: str) -> str:
    code = value.strip().upper()
    if SAFE_CODE.fullmatch(code) is None:
        raise AppError("ERR-VALIDATION", "Dữ liệu yêu cầu không hợp lệ.", 422)
    return code


def resolve_import_building(
    session: Session,
    context: UserContext,
    building_code: str,
    *,
    lock: bool = False,
) -> Building:
    """Resolve an input business code inside the server-derived active scope."""
    context.assert_role(*IMPORT_RUN_ROLES)
    active_site_id = context.assert_active_site()
    statement = select(Building).join(Site, Building.site_id == Site.id).where(
        Building.code == _normalise_building_code(building_code),
        Site.id == active_site_id,
        Site.tenant_id == context.tenant_id,
    )
    if lock:
        statement = statement.with_for_update()
    building = session.scalar(statement)
    if building is None:
        raise scope_not_found()
    context.assert_building_role(building.id, *IMPORT_RUN_ROLES)
    return building


def _scoped_run(
    session: Session,
    context: UserContext,
    run_id: UUID,
    *,
    lock: bool = False,
) -> ImportRun:
    context.assert_role(*IMPORT_RUN_ROLES)
    statement = select(ImportRun).where(
        ImportRun.id == run_id,
        ImportRun.tenant_id == context.tenant_id,
        ImportRun.site_id == context.assert_active_site(),
    )
    if lock:
        statement = statement.with_for_update()
    run = session.scalar(statement)
    if run is None:
        raise scope_not_found()
    context.assert_building_role(run.building_id, *IMPORT_RUN_ROLES)
    return run


def _safe_filename(value: str | None) -> tuple[str, str | None]:
    original = value or "unit-import.csv"
    name = Path(original).name
    # Treat both slash forms as path separators regardless of the host OS.  The
    # value is later used to derive a download filename, so controls are also
    # rejected rather than relying on a response-header implementation detail.
    if (
        name != original
        or PureWindowsPath(original).name != original
        or name in {"", ".", ".."}
        or len(name) > MAX_SOURCE_FILENAME_CHARS
        or any(ord(character) < 32 or ord(character) == 127 for character in name)
    ):
        return "rejected-import.csv", "unsafe-file-name"
    if Path(name).suffix.lower() != ".csv":
        return "rejected-import.csv", "extension-not-allowed"
    return name, None


def _claimed_csv_mime(value: str | None) -> tuple[str, str | None]:
    mime = (value or "").split(";", 1)[0].strip().lower()
    if mime not in ALLOWED_CSV_MIME_TYPES:
        return "application/octet-stream", "mime-not-allowed"
    return mime, None


def _parse_csv(content: bytes) -> ParsedCsv:
    if not content or len(content) > MAX_IMPORT_CSV_BYTES:
        raise CsvFormatError("CSV rỗng hoặc vượt giới hạn kích thước.")
    if b"\x00" in content:
        raise CsvFormatError("CSV chứa dữ liệu nhị phân không hợp lệ.")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvFormatError("CSV phải dùng mã hóa UTF-8.") from exc
    try:
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        header_values = next(reader, None)
        if not header_values:
            raise CsvFormatError("CSV phải có hàng tiêu đề.")
        if len(header_values) > MAX_IMPORT_COLUMNS:
            raise CsvFormatError("CSV có quá nhiều cột.")
        headers = tuple(value.strip() for value in header_values)
        if any(not value or len(value) > 200 for value in headers) or len(set(headers)) != len(headers):
            raise CsvFormatError("Hàng tiêu đề CSV không hợp lệ.")
        rows: list[ParsedCsvRow] = []
        for row_number, values in enumerate(reader, start=1):
            if len(rows) >= MAX_IMPORT_ROWS:
                raise CsvFormatError("CSV vượt giới hạn 10.000 dòng.")
            if len(values) != len(headers):
                rows.append(ParsedCsvRow(
                    row_number=row_number,
                    values={},
                    structural_issue=_issue("ERR-IMPORT-ROW", None, "Số cột của dòng không khớp hàng tiêu đề."),
                ))
                continue
            if any(len(value) > MAX_CSV_FIELD_CHARS for value in values):
                rows.append(ParsedCsvRow(
                    row_number=row_number,
                    values={},
                    structural_issue=_issue("ERR-IMPORT-ROW", None, "Giá trị ô vượt giới hạn cho phép."),
                ))
                continue
            rows.append(ParsedCsvRow(row_number=row_number, values=dict(zip(headers, values))))
    except csv.Error as exc:
        raise CsvFormatError("Cú pháp CSV không hợp lệ.") from exc
    if not rows:
        raise CsvFormatError("CSV phải có ít nhất một dòng dữ liệu.")
    return ParsedCsv(headers=headers, rows=tuple(rows))


def _mapping_from_request(mapping: UnitCsvMapping, headers: tuple[str, ...]) -> tuple[dict[str, str], str]:
    normalized = {field: value.strip() for field, value in mapping.model_dump().items()}
    if not set(normalized.values()).issubset(set(headers)):
        raise AppError("ERR-VALIDATION", "Cột map không tồn tại trong tệp CSV.", 422)
    return normalized, _payload_hash(normalized)


def _code_value(value: str) -> tuple[str | None, ImportRowIssue | None]:
    canonical = value.strip().upper()
    if SAFE_CODE.fullmatch(canonical) is None:
        return None, _issue("ERR-IMPORT-ROW", "unit_number", "Mã căn hộ không hợp lệ.")
    if canonical != value:
        return canonical, _issue("WARN-NORMALIZED", "unit_number", "Mã căn hộ đã được chuẩn hóa.")
    return canonical, None


def _floor_value(value: str, floors_count: int) -> tuple[int | None, ImportRowIssue | None]:
    stripped = value.strip()
    if re.fullmatch(r"[0-9]+", stripped) is None:
        return None, _issue("ERR-IMPORT-ROW", "floor", "Tầng phải là số nguyên.")
    floor = int(stripped)
    if not 1 <= floor <= floors_count:
        return None, _issue("ERR-IMPORT-ROW", "floor", "Tầng nằm ngoài phạm vi của tòa nhà.")
    return floor, None


def _area_value(value: str) -> tuple[float | None, ImportRowIssue | None]:
    try:
        area = Decimal(value.strip())
    except (InvalidOperation, ValueError):
        return None, _issue("ERR-IMPORT-ROW", "area_m2", "Diện tích phải là số dương.")
    if not area.is_finite() or not Decimal("0") < area <= MAX_AREA_M2:
        return None, _issue("ERR-IMPORT-ROW", "area_m2", "Diện tích phải nằm trong phạm vi hợp lệ.")
    if area.as_tuple().exponent < -2:
        return None, _issue("ERR-IMPORT-ROW", "area_m2", "Diện tích có tối đa hai chữ số thập phân.")
    return float(area), None


def _status_value(value: str) -> tuple[str | None, ImportRowIssue | None]:
    canonical = value.strip().lower()
    if canonical not in ALLOWED_UNIT_STATUSES:
        return None, _issue("ERR-IMPORT-ROW", "status", "Trạng thái căn hộ không hợp lệ.")
    if canonical != value:
        return canonical, _issue("WARN-NORMALIZED", "status", "Trạng thái đã được chuẩn hóa.")
    return canonical, None


def _validate_row(row: ParsedCsvRow, mapping: dict[str, str], building: Building) -> RowResult:
    if row.structural_issue is not None:
        return RowResult(row.row_number, "ERROR", (row.structural_issue,))
    unit_number, number_issue = _code_value(row.values[mapping["unit_number"]])
    floor, floor_issue = _floor_value(row.values[mapping["floor"]], building.floors_count)
    area_m2, area_issue = _area_value(row.values[mapping["area_m2"]])
    status, status_issue = _status_value(row.values[mapping["status"]])
    issues = tuple(issue for issue in (number_issue, floor_issue, area_issue, status_issue) if issue is not None)
    if any(issue.code.startswith("ERR-") for issue in issues):
        return RowResult(row.row_number, "ERROR", issues)
    candidate = Candidate(row.row_number, unit_number, floor, area_m2, status)
    return RowResult(row.row_number, "WARNING" if issues else "VALIDATED", issues, candidate)


def _evaluate_rows(parsed: ParsedCsv, mapping: dict[str, str], building: Building, existing_numbers: set[str]) -> list[RowResult]:
    seen_numbers: set[str] = set()
    results: list[RowResult] = []
    for row in parsed.rows:
        result = _validate_row(row, mapping, building)
        candidate = result.candidate
        if candidate is None:
            results.append(result)
            continue
        if candidate.unit_number in seen_numbers:
            results.append(RowResult(
                candidate.row_number,
                "SKIPPED",
                (_issue("WARN-DUPLICATE-IN-BATCH", "unit_number", "Mã căn trùng trong cùng lô nhập."),),
            ))
            continue
        seen_numbers.add(candidate.unit_number)
        if candidate.unit_number in existing_numbers:
            results.append(RowResult(
                candidate.row_number,
                "SKIPPED",
                (_issue("WARN-ALREADY-EXISTS", "unit_number", "Căn hộ đã tồn tại nên không được cập nhật."),),
            ))
            continue
        results.append(result)
    return results


def _counts(results: list[RowResult]) -> dict[str, int]:
    return {
        "total_rows": len(results),
        "valid_rows": sum(result.status in {"VALIDATED", "WARNING", "IMPORTED"} for result in results),
        "warning_rows": sum(
            any(issue.code.startswith("WARN-") for issue in result.issues)
            for result in results
        ),
        "error_rows": sum(result.status == "ERROR" for result in results),
        "skipped_rows": sum(result.status == "SKIPPED" for result in results),
        "applied_rows": sum(result.status == "IMPORTED" for result in results),
    }


def _result_data(result: RowResult) -> list[dict]:
    return [issue.model_dump() for issue in result.issues]


def _apply_counts(run: ImportRun, results: list[RowResult]) -> None:
    for field, value in _counts(results).items():
        setattr(run, field, value)


def _update_persisted_rows(session: Session, run: ImportRun, results: list[RowResult]) -> None:
    existing = {
        row.row_number: row
        for row in session.scalars(select(ImportRunRow).where(ImportRunRow.import_run_id == run.id))
    }
    for result in results:
        row = existing.pop(result.row_number, None)
        if row is None:
            session.add(ImportRunRow(
                import_run_id=run.id,
                row_number=result.row_number,
                status=result.status,
                issues=_result_data(result),
            ))
        else:
            row.status = result.status
            row.issues = _result_data(result)
    if existing:
        session.execute(delete(ImportRunRow).where(ImportRunRow.id.in_([row.id for row in existing.values()])))


def _storage_target(storage_root: Path, storage_key: str) -> Path:
    root = storage_root.resolve()
    target = (root / storage_key).resolve()
    if root not in target.parents:
        raise AppError("ERR-FILE-REJECTED", "Không thể lưu tệp.", 422)
    return target


def _write_private(storage_root: Path, storage_key: str, content: bytes) -> None:
    target = _storage_target(storage_root, storage_key)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)


def remove_private_file(storage_root: Path, storage_key: str | None) -> None:
    if not storage_key:
        return
    try:
        _storage_target(storage_root, storage_key).unlink(missing_ok=True)
    except AppError:
        return


def _read_private_bounded(storage_root: Path, storage_key: str, maximum_bytes: int) -> bytes:
    target = _storage_target(storage_root, storage_key)
    if not target.is_file():
        raise scope_not_found()
    chunks: list[bytes] = []
    total = 0
    try:
        with target.open("rb") as source:
            while chunk := source.read(FILE_HASH_CHUNK_BYTES):
                total += len(chunk)
                if total > maximum_bytes:
                    raise AppError("ERR-FILE-INTEGRITY", "Không thể xác thực tệp nguồn.", 409)
                chunks.append(chunk)
    except OSError:
        raise scope_not_found() from None
    return b"".join(chunks)


def _file_digest_and_size(target: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    with target.open("rb") as source:
        while chunk := source.read(FILE_HASH_CHUNK_BYTES):
            digest.update(chunk)
            total += len(chunk)
    return digest.hexdigest(), total


def _csv_safe(value: object) -> str:
    text = str(value or "")
    return "'" + text if text.startswith(("=", "+", "-", "@")) else text


def _error_report(results: list[RowResult]) -> bytes | None:
    flagged = [result for result in results if result.status in {"ERROR", "SKIPPED"}]
    if not flagged:
        return None
    destination = io.StringIO(newline="")
    writer = csv.writer(destination)
    writer.writerow(["row_number", "status", "code", "column", "message"])
    for result in flagged:
        for issue in result.issues:
            writer.writerow([
                result.row_number,
                result.status,
                _csv_safe(issue.code),
                _csv_safe(issue.column),
                _csv_safe(issue.message),
            ])
    return destination.getvalue().encode("utf-8")


def _replace_error_file(
    storage_root: Path,
    run: ImportRun,
    results: list[RowResult],
) -> tuple[str | None, str | None]:
    """Write a fresh private error report and return (old_key, new_key)."""
    old_key = run.error_storage_key
    content = _error_report(results)
    if content is None:
        run.error_filename = None
        run.error_storage_key = None
        run.error_sha256 = None
        run.error_size_bytes = None
        return old_key, None
    storage_key = f"imports/{run.tenant_id}/{run.site_id}/{run.id}/errors-{uuid4().hex}.csv"
    _write_private(storage_root, storage_key, content)
    run.error_filename = f"{Path(run.source_filename).stem}-errors.csv"
    run.error_storage_key = storage_key
    run.error_sha256 = hashlib.sha256(content).hexdigest()
    run.error_size_bytes = len(content)
    return old_key, storage_key


def _audit(
    session: Session,
    context: UserContext,
    request: Request,
    *,
    event_type: str,
    action: str,
    run: ImportRun,
    after: dict | None = None,
) -> None:
    session.add(AuditEvent(
        tenant_id=context.tenant_id,
        site_id=context.assert_active_site(),
        building_id=run.building_id,
        actor_account_id=context.account_id,
        event_type=event_type,
        action=action,
        resource_type=RESOURCE_TYPE,
        resource_id=run.id,
        after_data=after,
        correlation_id=_correlation_id(request),
    ))


def _emit(
    session: Session,
    context: UserContext,
    request: Request,
    *,
    event_type: str,
    run: ImportRun,
    payload: dict,
) -> None:
    session.add(DomainEvent(
        tenant_id=context.tenant_id,
        site_id=context.assert_active_site(),
        actor_account_id=context.account_id,
        event_type=event_type,
        resource_type=RESOURCE_TYPE,
        resource_id=run.id,
        correlation_id=_correlation_id(request),
        payload=payload,
    ))


def _claim_or_replay(
    session: Session,
    context: UserContext,
    *,
    operation: str,
    key: str | None,
    payload: object,
    run_id: UUID,
) -> tuple[IdempotencyRecord | None, IdempotencyRecord | None]:
    """Claim an idempotency key atomically, or return its completed receipt."""
    safe_key = _validate_idempotency_key(key)
    request_hash = _payload_hash(payload)
    inserted_id = session.scalar(
        insert(IdempotencyRecord)
        .values(
            tenant_id=context.tenant_id,
            site_id=context.assert_active_site(),
            actor_account_id=context.account_id,
            operation=operation,
            idempotency_key=safe_key,
            request_hash=request_hash,
            resource_type=RESOURCE_TYPE,
            resource_id=run_id,
            response_status=200,
            response_body=None,
        )
        .on_conflict_do_nothing(constraint="uq_idempotency_scope_operation_key")
        .returning(IdempotencyRecord.id)
    )
    if inserted_id is not None:
        receipt = session.get(IdempotencyRecord, inserted_id)
        if receipt is None:
            raise RuntimeError("Không thể tải lại idempotency receipt vừa tạo.")
        return receipt, None
    existing = session.scalar(select(IdempotencyRecord).where(
        IdempotencyRecord.tenant_id == context.tenant_id,
        IdempotencyRecord.site_id == context.assert_active_site(),
        IdempotencyRecord.actor_account_id == context.account_id,
        IdempotencyRecord.operation == operation,
        IdempotencyRecord.idempotency_key == safe_key,
    ))
    if existing is None or existing.request_hash != request_hash:
        raise AppError("ERR-CONFLICT", "Idempotency-Key đã được dùng cho nội dung khác.", 409)
    if existing.response_body is None:
        raise AppError("ERR-CONFLICT", "Yêu cầu trước vẫn đang được xử lý.", 409)
    return None, existing


def _completed_replay(
    session: Session,
    context: UserContext,
    *,
    operation: str,
    key: str | None,
    payload: object,
) -> IdempotencyRecord | None:
    """Return an already-completed receipt before evaluating mutable run state."""
    safe_key = _validate_idempotency_key(key)
    request_hash = _payload_hash(payload)
    existing = session.scalar(select(IdempotencyRecord).where(
        IdempotencyRecord.tenant_id == context.tenant_id,
        IdempotencyRecord.site_id == context.assert_active_site(),
        IdempotencyRecord.actor_account_id == context.account_id,
        IdempotencyRecord.operation == operation,
        IdempotencyRecord.idempotency_key == safe_key,
    ))
    if existing is None:
        return None
    if existing.request_hash != request_hash:
        raise AppError("ERR-CONFLICT", "Idempotency-Key đã được dùng cho nội dung khác.", 409)
    if existing.response_body is None:
        raise AppError("ERR-CONFLICT", "Yêu cầu trước vẫn đang được xử lý.", 409)
    return existing


def _view_payload(run: ImportRun) -> dict:
    return ImportRunView.model_validate(run).model_dump(mode="json")


def _set_receipt(receipt: IdempotencyRecord, run: ImportRun, status: int) -> None:
    receipt.response_status = status
    receipt.response_body = _view_payload(run)


def _source_key(run_id: UUID, tenant_id: UUID, site_id: UUID, quarantined: bool) -> str:
    if quarantined:
        return f"quarantine/imports/{tenant_id}/{site_id}/{run_id}.bin"
    return f"imports/{tenant_id}/{site_id}/{run_id}/source.csv"


def _source_snapshot(run: ImportRun) -> tuple[str, int, str, bool]:
    return (
        run.source_storage_key,
        run.source_size_bytes,
        run.source_sha256,
        run.source_is_quarantined,
    )


def create_import_run(
    session: Session,
    context: UserContext,
    request: Request,
    *,
    building_code: str,
    mode: str,
    file_name: str | None,
    claimed_mime_type: str | None,
    content: bytes,
    idempotency_key: str | None,
    storage_root: Path,
) -> ImportRunExecution:
    if mode not in {"PARTIAL", "ALL_OR_NOTHING"}:
        raise AppError("ERR-VALIDATION", "Dữ liệu yêu cầu không hợp lệ.", 422)
    if not content:
        raise AppError("ERR-FILE-REJECTED", "Tệp CSV rỗng hoặc vượt giới hạn kích thước.", 422)
    if len(content) > MAX_IMPORT_CSV_BYTES:
        raise AppError("ERR-FILE-REJECTED", "Tệp CSV rỗng hoặc vượt giới hạn kích thước.", 422)
    building = resolve_import_building(session, context, building_code)
    filename, filename_error = _safe_filename(file_name)
    mime_type, mime_error = _claimed_csv_mime(claimed_mime_type)
    validation_error = filename_error or mime_error
    if validation_error is None:
        try:
            _parse_csv(content)
        except CsvFormatError:
            validation_error = "content-not-csv"
    digest = hashlib.sha256(content).hexdigest()
    payload = {
        "building_code": building.code,
        "mode": mode,
        "source_sha256": digest,
        "source_mime_type": mime_type,
        "source_filename": filename,
    }
    run_id = uuid4()
    receipt, replay = _claim_or_replay(
        session, context, operation=UPLOAD_OPERATION, key=idempotency_key,
        payload=payload, run_id=run_id,
    )
    if replay is not None:
        run = _scoped_run(session, context, replay.resource_id)
        return ImportRunExecution(run=run, replayed=True, replay_body=replay.response_body)
    if receipt is None:
        raise RuntimeError("Không thể claim import receipt.")
    source_quarantined = validation_error is not None
    source_key = _source_key(run_id, context.tenant_id, context.assert_active_site(), source_quarantined)
    run = ImportRun(
        id=run_id,
        tenant_id=context.tenant_id,
        site_id=context.assert_active_site(),
        building_id=building.id,
        created_by_id=context.account_id,
        mode=mode,
        status="FAILED" if source_quarantined else "UPLOADED",
        source_filename=filename,
        source_storage_key=source_key,
        source_mime_type="application/octet-stream" if source_quarantined else mime_type,
        source_size_bytes=len(content),
        source_sha256=digest,
        source_is_quarantined=source_quarantined,
        source_quarantine_reason=validation_error,
        failure_code="ERR-FILE-QUARANTINED" if source_quarantined else None,
        failed_at=_now() if source_quarantined else None,
    )
    try:
        _write_private(storage_root, source_key, content)
        session.add(run)
        session.flush()
        _audit(
            session, context, request,
            event_type="ImportFileQuarantined" if source_quarantined else "ImportRunUploaded",
            action="quarantine" if source_quarantined else "upload",
            run=run,
            after={"sha256": digest, "size_bytes": len(content), "reason": validation_error},
        )
        if source_quarantined:
            _emit(
                session, context, request, event_type="ImportFileQuarantined", run=run,
                payload={"reason": validation_error},
            )
        _set_receipt(receipt, run, 422 if source_quarantined else 201)
    except Exception:
        remove_private_file(storage_root, source_key)
        raise
    return ImportRunExecution(run=run, replayed=False)


def _run_source(run: ImportRun, storage_root: Path) -> ParsedCsv:
    try:
        content = _read_private_bounded(
            storage_root, run.source_storage_key, MAX_IMPORT_CSV_BYTES,
        )
    except AppError as exc:
        if exc.code == "ERR-SCOPE-NOTFOUND":
            raise AppError("ERR-FILE-INTEGRITY", "Không thể xác thực tệp nguồn.", 409) from None
        raise
    if (
        len(content) != run.source_size_bytes
        or hashlib.sha256(content).hexdigest() != run.source_sha256
    ):
        raise AppError("ERR-FILE-INTEGRITY", "Không thể xác thực tệp nguồn.", 409)
    try:
        return _parse_csv(content)
    except CsvFormatError as exc:
        raise AppError("ERR-FILE-INTEGRITY", "Không thể xác thực tệp nguồn.", 409) from exc


def _existing_unit_numbers(session: Session, building_id: UUID) -> set[str]:
    return {
        number.upper()
        for number in session.scalars(select(Unit.unit_number).where(Unit.building_id == building_id))
    }


def preview_import_run(
    session: Session,
    context: UserContext,
    request: Request,
    *,
    run_id: UUID,
    body: ImportRunPreviewRequest,
    idempotency_key: str | None,
    storage_root: Path,
) -> ImportRunExecution:
    requested_mapping = {
        field: value.strip()
        for field, value in body.mapping.model_dump().items()
    }
    payload = {
        "run_id": str(run_id),
        "expected_version": body.expected_version,
        "mapping": requested_mapping,
    }
    unlocked_run = _scoped_run(session, context, run_id)
    replay = _completed_replay(
        session, context, operation=PREVIEW_OPERATION, key=idempotency_key, payload=payload,
    )
    if replay is not None:
        return ImportRunExecution(run=unlocked_run, replayed=True, replay_body=replay.response_body)
    if unlocked_run.source_is_quarantined:
        raise AppError("ERR-FILE-QUARANTINED", "Tệp không an toàn và đã bị chặn.", 423)
    source_snapshot = _source_snapshot(unlocked_run)
    parsed = _run_source(unlocked_run, storage_root)
    # No mutation happened above. End the read-only transaction before the
    # file I/O is followed by a row lock, so other work is not blocked by CSV parsing.
    session.rollback()
    run = _scoped_run(session, context, run_id, lock=True)
    replay = _completed_replay(
        session, context, operation=PREVIEW_OPERATION, key=idempotency_key, payload=payload,
    )
    if replay is not None:
        return ImportRunExecution(run=run, replayed=True, replay_body=replay.response_body)
    if run.source_is_quarantined:
        raise AppError("ERR-FILE-QUARANTINED", "Tệp không an toàn và đã bị chặn.", 423)
    if _source_snapshot(run) != source_snapshot:
        raise AppError("ERR-CONFLICT", "Tệp nguồn đã thay đổi. Hãy tải lại rồi thử lại.", 409)
    if run.status not in {"UPLOADED", "PREVIEWED"}:
        raise AppError("ERR-STATE-TRANSITION", "Import run chưa ở trạng thái có thể preview.", 409)
    if run.version != body.expected_version:
        raise AppError("ERR-CONFLICT", "Dữ liệu đã được cập nhật. Hãy tải lại rồi thử lại.", 409)
    mapping, mapping_hash = _mapping_from_request(body.mapping, parsed.headers)
    receipt, replay = _claim_or_replay(
        session, context, operation=PREVIEW_OPERATION, key=idempotency_key,
        payload=payload, run_id=run.id,
    )
    if replay is not None:
        return ImportRunExecution(run=run, replayed=True, replay_body=replay.response_body)
    if receipt is None:
        raise RuntimeError("Không thể claim preview receipt.")
    old_error_key: str | None = None
    new_error_key: str | None = None
    building = _locked_run_building(session, context, run)
    try:
        run.status = "VALIDATING"
        run.processed_started_at = _now()
        results = _evaluate_rows(parsed, mapping, building, _existing_unit_numbers(session, building.id))
        _update_persisted_rows(session, run, results)
        _apply_counts(run, results)
        old_error_key, new_error_key = _replace_error_file(storage_root, run, results)
        run.mapping_json = mapping
        run.mapping_hash = mapping_hash
        run.status = "PREVIEWED"
        run.failure_code = None
        run.failed_at = None
        run.previewed_at = _now()
        run.version += 1
        _audit(
            session, context, request, event_type="ImportRunPreviewed", action="preview", run=run,
            after={**_counts(results), "mapping_hash": mapping_hash},
        )
        _set_receipt(receipt, run, 200)
    except Exception:
        remove_private_file(storage_root, new_error_key)
        raise
    return ImportRunExecution(
        run=run, replayed=False, cleanup_error_key=old_error_key, new_error_key=new_error_key,
    )


def _locked_run_building(session: Session, context: UserContext, run: ImportRun) -> Building:
    statement = select(Building).join(Site, Building.site_id == Site.id).where(
        Building.id == run.building_id,
        Site.id == context.assert_active_site(),
        Site.tenant_id == context.tenant_id,
    ).with_for_update()
    building = session.scalar(statement)
    if building is None:
        raise scope_not_found()
    context.assert_building_role(building.id, *IMPORT_RUN_ROLES)
    return building


def apply_import_run(
    session: Session,
    context: UserContext,
    request: Request,
    *,
    run_id: UUID,
    body: ImportRunApplyRequest,
    idempotency_key: str | None,
    storage_root: Path,
) -> ImportRunExecution:
    payload = {
        "run_id": str(run_id),
        "expected_version": body.expected_version,
    }
    # Every successful preview increments version, so this caller-supplied value
    # binds apply idempotency to the mapping generation without mutable server state.
    unlocked_run = _scoped_run(session, context, run_id)
    replay = _completed_replay(
        session, context, operation=APPLY_OPERATION, key=idempotency_key, payload=payload,
    )
    if replay is not None:
        return ImportRunExecution(run=unlocked_run, replayed=True, replay_body=replay.response_body)
    if unlocked_run.source_is_quarantined:
        raise AppError("ERR-FILE-QUARANTINED", "Tệp không an toàn và đã bị chặn.", 423)
    source_snapshot = _source_snapshot(unlocked_run)
    parsed = _run_source(unlocked_run, storage_root)
    # Release the read-only transaction before taking locks for the atomic apply.
    session.rollback()
    run = _scoped_run(session, context, run_id, lock=True)
    replay = _completed_replay(
        session, context, operation=APPLY_OPERATION, key=idempotency_key, payload=payload,
    )
    if replay is not None:
        return ImportRunExecution(run=run, replayed=True, replay_body=replay.response_body)
    if run.source_is_quarantined:
        raise AppError("ERR-FILE-QUARANTINED", "Tệp không an toàn và đã bị chặn.", 423)
    if _source_snapshot(run) != source_snapshot:
        raise AppError("ERR-CONFLICT", "Tệp nguồn đã thay đổi. Hãy tải lại rồi thử lại.", 409)
    if run.status != "PREVIEWED":
        raise AppError("ERR-STATE-TRANSITION", "Import run chưa sẵn sàng để áp dụng.", 409)
    if run.version != body.expected_version:
        raise AppError("ERR-CONFLICT", "Dữ liệu đã được cập nhật. Hãy tải lại rồi thử lại.", 409)
    if not isinstance(run.mapping_json, dict):
        raise AppError("ERR-STATE-TRANSITION", "Import run chưa có mapping hợp lệ.", 409)
    receipt, replay = _claim_or_replay(
        session, context, operation=APPLY_OPERATION, key=idempotency_key,
        payload=payload, run_id=run.id,
    )
    if replay is not None:
        return ImportRunExecution(run=run, replayed=True, replay_body=replay.response_body)
    if receipt is None:
        raise RuntimeError("Không thể claim apply receipt.")
    mapping = {key: str(value) for key, value in run.mapping_json.items()}
    if set(mapping) != {"unit_number", "floor", "area_m2", "status"}:
        raise AppError("ERR-STATE-TRANSITION", "Import run có mapping không hợp lệ.", 409)
    building = _locked_run_building(session, context, run)
    results = _evaluate_rows(parsed, mapping, building, _existing_unit_numbers(session, building.id))
    rejected = run.mode == "ALL_OR_NOTHING" and any(
        result.status in {"ERROR", "SKIPPED"} for result in results
    )
    old_error_key: str | None = None
    new_error_key: str | None = None
    try:
        run.status = "APPLYING"
        run.processed_started_at = _now()
        if not rejected:
            records = [
                Unit(
                    building_id=building.id,
                    unit_number=result.candidate.unit_number,
                    floor=result.candidate.floor,
                    area_m2=result.candidate.area_m2,
                    status=result.candidate.status,
                )
                for result in results
                if result.candidate is not None
            ]
            session.add_all(records)
            session.flush()
            results = [
                RowResult(result.row_number, "IMPORTED", result.issues, result.candidate)
                if result.candidate is not None else result
                for result in results
            ]
        _update_persisted_rows(session, run, results)
        _apply_counts(run, results)
        old_error_key, new_error_key = _replace_error_file(storage_root, run, results)
        run.status = "FAILED" if rejected else "APPLIED"
        run.failure_code = "ERR-IMPORT-ROW" if rejected else None
        run.failed_at = _now() if rejected else None
        run.applied_at = None if rejected else _now()
        run.version += 1
        summary = {
            **_counts(results),
            "source_sha256": run.source_sha256,
            "status": run.status,
        }
        _audit(
            session, context, request,
            event_type="ImportRunRejected" if rejected else "ImportRunApplied",
            action="apply",
            run=run,
            after=summary,
        )
        _emit(
            session, context, request, event_type="ImportRunCompleted", run=run,
            payload=summary,
        )
        _set_receipt(receipt, run, 200)
    except Exception:
        remove_private_file(storage_root, new_error_key)
        raise
    return ImportRunExecution(
        run=run, replayed=False, cleanup_error_key=old_error_key, new_error_key=new_error_key,
    )


def get_import_run(session: Session, context: UserContext, run_id: UUID) -> ImportRun:
    return _scoped_run(session, context, run_id)


def list_import_rows(
    session: Session,
    context: UserContext,
    *,
    run_id: UUID,
    page: int,
    page_size: int,
) -> tuple[ImportRun, list[ImportRunRow], int]:
    run = _scoped_run(session, context, run_id)
    total = session.scalar(select(func.count(ImportRunRow.id)).where(ImportRunRow.import_run_id == run.id)) or 0
    rows = session.scalars(
        select(ImportRunRow)
        .where(ImportRunRow.import_run_id == run.id)
        .order_by(ImportRunRow.row_number)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return run, rows, total


def create_error_file_signed_link(
    session: Session,
    context: UserContext,
    request: Request,
    *,
    run_id: UUID,
    link_ttl_seconds: int,
) -> tuple[ImportRun, str, datetime]:
    run = _scoped_run(session, context, run_id)
    if run.source_is_quarantined:
        raise AppError("ERR-FILE-QUARANTINED", "Tệp không an toàn và đã bị chặn.", 423)
    if not run.error_storage_key:
        raise scope_not_found()
    token = create_token({
        "sub": str(context.account_id),
        "active_site_id": str(context.assert_active_site()),
        "purpose": "import-error-download",
        "import_run_id": str(run.id),
        "tenant_id": str(context.tenant_id),
        "building_id": str(run.building_id),
    }, request.app.state.settings.auth_secret(), expires_in_seconds=link_ttl_seconds)
    expires_at = _now() + timedelta(seconds=link_ttl_seconds)
    _audit(
        session, context, request, event_type="ImportRunErrorLinkIssued", action="signed-link", run=run,
        after={"expires_at": expires_at.isoformat()},
    )
    return run, token, expires_at


def assert_error_file_token(
    request: Request,
    context: UserContext,
    run: ImportRun,
    token: str,
) -> None:
    claims = decode_token(
        token,
        request.app.state.settings.auth_secret(),
        expired_code="ERR-LINK-EXPIRED",
        expired_message="Liên kết đã hết hạn. Tải lại trang.",
        expired_status=410,
    )
    expected = {
        "purpose": "import-error-download",
        "sub": str(context.account_id),
        "tenant_id": str(context.tenant_id),
        "active_site_id": str(context.assert_active_site()),
        "building_id": str(run.building_id),
        "import_run_id": str(run.id),
    }
    if any(claims.get(key) != value for key, value in expected.items()):
        raise scope_not_found()


def error_file_path(storage_root: Path, run: ImportRun) -> Path:
    if run.source_is_quarantined:
        raise AppError("ERR-FILE-QUARANTINED", "Tệp không an toàn và đã bị chặn.", 423)
    if not run.error_storage_key:
        raise scope_not_found()
    target = _storage_target(storage_root, run.error_storage_key)
    if not target.is_file():
        raise scope_not_found()
    try:
        digest, size_bytes = _file_digest_and_size(target)
    except OSError:
        raise AppError("ERR-FILE-INTEGRITY", "Không thể xác thực tệp lỗi.", 409) from None
    if (
        run.error_sha256 is None
        or run.error_size_bytes is None
        or size_bytes != run.error_size_bytes
        or digest != run.error_sha256
    ):
        raise AppError("ERR-FILE-INTEGRITY", "Không thể xác thực tệp lỗi.", 409)
    return target


def record_error_file_download(
    session: Session,
    context: UserContext,
    request: Request,
    run: ImportRun,
) -> None:
    _audit(
        session, context, request, event_type="ImportRunErrorFileDownloaded", action="download", run=run,
        after={"error_sha256": run.error_sha256},
    )
