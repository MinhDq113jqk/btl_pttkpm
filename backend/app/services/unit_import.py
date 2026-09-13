"""Synchronous, scoped Unit import receipt for the R1 AC-02 evidence slice.

This module deliberately does not implement the roadmap's durable ImportRun,
file storage, or Unit--Person import.  It accepts already-mapped Unit JSON and
uses the existing idempotency/audit/outbox tables to persist a bounded receipt.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from uuid import UUID, uuid4

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.policy import UserContext, scope_not_found
from app.models.building import Building
from app.models.enums import UnitStatusEnum
from app.models.platform import AuditEvent, DomainEvent, IdempotencyRecord
from app.models.site import Site
from app.models.unit import Unit
from app.schemas.unit import (
    UnitImportItem,
    UnitImportItemResult,
    UnitImportRequest,
    UnitImportResponse,
)


IMPORT_OPERATION = "unit.import.v1"
IMPORT_RESOURCE_TYPE = "UnitImportReceipt"
IMPORT_ROLES = ("admin", "cskh")
_SAFE_KEY = re.compile(r"[A-Za-z0-9._:-]{8,128}")
_SAFE_CODE = re.compile(r"[A-Z0-9][A-Z0-9._/-]{0,49}")
_MAX_AREA_M2 = Decimal("100000")
_ALLOWED_STATUSES = frozenset(status.value for status in UnitStatusEnum)


@dataclass(frozen=True)
class _Issue:
    code: str
    column: str | None
    message: str


@dataclass(frozen=True)
class _Candidate:
    result_index: int
    unit_number: str
    floor: int
    area_m2: float
    status: str


@dataclass(frozen=True)
class UnitImportExecution:
    response: UnitImportResponse
    replayed: bool


def _correlation_id(request: Request) -> UUID:
    try:
        return UUID(str(getattr(request.state, "correlation_id", None)))
    except (TypeError, ValueError):
        return uuid4()


def _payload_hash(payload: object) -> str:
    try:
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AppError("ERR-VALIDATION", "Dữ liệu yêu cầu không hợp lệ.", 422) from exc
    return hashlib.sha256(encoded).hexdigest()


def validate_idempotency_key(value: str | None) -> str:
    if value is None or _SAFE_KEY.fullmatch(value) is None:
        raise AppError("ERR-IDEMPOTENCY-KEY", "Idempotency-Key phải dài 8-128 ký tự an toàn.", 400)
    return value


def _normalise_building_code(value: str) -> str:
    code = value.strip().upper()
    if _SAFE_CODE.fullmatch(code) is None:
        raise AppError("ERR-VALIDATION", "Dữ liệu yêu cầu không hợp lệ.", 422)
    return code


def resolve_import_building(session: Session, context: UserContext, building_code: str) -> Building:
    """Lock the one in-scope building before validating or inserting its Units."""
    context.assert_role(*IMPORT_ROLES)
    active_site_id = context.assert_active_site()
    building = session.scalar(
        select(Building)
        .join(Site, Building.site_id == Site.id)
        .where(
            Building.code == _normalise_building_code(building_code),
            Site.id == active_site_id,
            Site.tenant_id == context.tenant_id,
        )
        .with_for_update()
    )
    if building is None:
        raise scope_not_found()
    # The input code identifies a source row only.  This policy call derives the
    # authorized building scope from the database-backed session grants.
    context.assert_building_role(building.id, *IMPORT_ROLES)
    return building


def _text_value(value: object, column: str) -> tuple[str | None, _Issue | None]:
    if not isinstance(value, str):
        return None, _Issue("ERR-IMPORT-ROW", column, "Giá trị phải là chuỗi ký tự.")
    canonical = value.strip().upper()
    if _SAFE_CODE.fullmatch(canonical) is None:
        return None, _Issue(
            "ERR-IMPORT-ROW", column,
            "Mã phải dài 1-50 ký tự chữ, số hoặc . _ / -.",
        )
    warning = None
    if canonical != value:
        warning = _Issue("WARN-NORMALIZED", column, "Mã đã được chuẩn hóa trước khi nhập.")
    return canonical, warning


def _floor_value(value: object, floors_count: int) -> tuple[int | None, _Issue | None]:
    if isinstance(value, bool):
        return None, _Issue("ERR-IMPORT-ROW", "floor", "Tầng phải là số nguyên.")
    if isinstance(value, int):
        floor = value
    elif isinstance(value, str) and re.fullmatch(r"[0-9]+", value.strip()):
        floor = int(value.strip())
    else:
        return None, _Issue("ERR-IMPORT-ROW", "floor", "Tầng phải là số nguyên.")
    if not 1 <= floor <= floors_count:
        return None, _Issue("ERR-IMPORT-ROW", "floor", "Tầng nằm ngoài phạm vi của tòa nhà.")
    return floor, None


def _area_value(value: object) -> tuple[float | None, _Issue | None]:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        return None, _Issue("ERR-IMPORT-ROW", "area_m2", "Diện tích phải là số dương.")
    try:
        area = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None, _Issue("ERR-IMPORT-ROW", "area_m2", "Diện tích phải là số dương.")
    if not area.is_finite() or not Decimal("0") < area <= _MAX_AREA_M2:
        return None, _Issue("ERR-IMPORT-ROW", "area_m2", "Diện tích phải nằm trong phạm vi hợp lệ.")
    if area.as_tuple().exponent < -2:
        return None, _Issue("ERR-IMPORT-ROW", "area_m2", "Diện tích có tối đa hai chữ số thập phân.")
    return float(area), None


def _status_value(value: object) -> tuple[str | None, _Issue | None]:
    if not isinstance(value, str):
        return None, _Issue("ERR-IMPORT-ROW", "status", "Trạng thái căn hộ không hợp lệ.")
    canonical = value.strip().lower()
    if canonical not in _ALLOWED_STATUSES:
        return None, _Issue("ERR-IMPORT-ROW", "status", "Trạng thái căn hộ không hợp lệ.")
    warning = None
    if canonical != value:
        warning = _Issue("WARN-NORMALIZED", "status", "Trạng thái đã được chuẩn hóa trước khi nhập.")
    return canonical, warning


def _validate_item(
    row_number: int, item: UnitImportItem, building: Building,
) -> tuple[_Candidate | None, UnitImportItemResult]:
    unit_number, warning = _text_value(item.unit_number, "unit_number")
    if unit_number is None:
        return None, UnitImportItemResult(
            row_number=row_number, status="ERROR", code=warning.code,
            column=warning.column, message=warning.message,
        )
    floor, issue = _floor_value(item.floor, building.floors_count)
    if floor is None:
        return None, UnitImportItemResult(
            row_number=row_number, status="ERROR", code=issue.code,
            column=issue.column, message=issue.message,
        )
    area_m2, issue = _area_value(item.area_m2)
    if area_m2 is None:
        return None, UnitImportItemResult(
            row_number=row_number, status="ERROR", code=issue.code,
            column=issue.column, message=issue.message,
        )
    status, status_warning = _status_value(item.status)
    if status is None:
        return None, UnitImportItemResult(
            row_number=row_number, status="ERROR", code=status_warning.code,
            column=status_warning.column, message=status_warning.message,
        )
    warning = warning or status_warning
    return _Candidate(-1, unit_number, floor, area_m2, status), UnitImportItemResult(
        row_number=row_number,
        status="VALIDATED",
        code=warning.code if warning else "OK",
        column=warning.column if warning else None,
        message=warning.message if warning else None,
    )


def _claim_or_replay(
    session: Session,
    context: UserContext,
    *,
    key: str,
    request_hash: str,
    receipt_id: UUID,
) -> tuple[IdempotencyRecord | None, UnitImportResponse | None]:
    """Atomically claim a receipt, or return its stored response for a retry."""
    inserted_id = session.scalar(
        insert(IdempotencyRecord)
        .values(
            tenant_id=context.tenant_id,
            site_id=context.assert_active_site(),
            actor_account_id=context.account_id,
            operation=IMPORT_OPERATION,
            idempotency_key=key,
            request_hash=request_hash,
            resource_type=IMPORT_RESOURCE_TYPE,
            resource_id=receipt_id,
            response_status=200,
            response_body=None,
        )
        .on_conflict_do_nothing(constraint="uq_idempotency_scope_operation_key")
        .returning(IdempotencyRecord.id)
    )
    if inserted_id is not None:
        receipt = session.get(IdempotencyRecord, inserted_id)
        if receipt is None:  # Defensive only; the row was returned by this transaction.
            raise RuntimeError("Could not reload idempotency receipt")
        return receipt, None

    existing = session.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.tenant_id == context.tenant_id,
            IdempotencyRecord.site_id == context.assert_active_site(),
            IdempotencyRecord.actor_account_id == context.account_id,
            IdempotencyRecord.operation == IMPORT_OPERATION,
            IdempotencyRecord.idempotency_key == key,
        )
    )
    if existing is None or existing.request_hash != request_hash:
        raise AppError("ERR-CONFLICT", "Idempotency-Key đã được dùng cho nội dung khác.", 409)
    if existing.response_body is None:
        raise AppError("ERR-CONFLICT", "Lần nhập trước vẫn đang được xử lý.", 409)
    return None, UnitImportResponse.model_validate(existing.response_body)


def _response(
    receipt_id: UUID,
    body: UnitImportRequest,
    results: list[UnitImportItemResult],
    *,
    applied: bool,
) -> UnitImportResponse:
    return UnitImportResponse(
        receipt_id=receipt_id,
        status="APPLIED" if applied else "REJECTED",
        mode=body.mode,
        total_rows=len(results),
        applied_rows=sum(result.status == "IMPORTED" for result in results),
        skipped_rows=sum(result.status == "SKIPPED" for result in results),
        warning_rows=sum(result.code.startswith("WARN-") for result in results),
        error_rows=sum(result.status == "ERROR" for result in results),
        items=results,
    )


def import_units(
    session: Session,
    context: UserContext,
    request: Request,
    body: UnitImportRequest,
    idempotency_key: str | None,
) -> UnitImportExecution:
    """Validate and apply one building's Unit batch in a single transaction."""
    key = validate_idempotency_key(idempotency_key)
    request_hash = _payload_hash(body.model_dump(mode="json"))
    building = resolve_import_building(session, context, body.building_code)
    receipt_id = uuid4()
    receipt, replay = _claim_or_replay(
        session, context, key=key, request_hash=request_hash, receipt_id=receipt_id,
    )
    if replay is not None:
        return UnitImportExecution(response=replay, replayed=True)

    existing_numbers = {
        number.upper()
        for number in session.scalars(select(Unit.unit_number).where(Unit.building_id == building.id))
    }
    results: list[UnitImportItemResult] = []
    candidates: list[_Candidate] = []
    seen_numbers: set[str] = set()
    for row_number, item in enumerate(body.items, start=1):
        candidate, result = _validate_item(row_number, item, building)
        results.append(result)
        if candidate is None:
            continue
        if candidate.unit_number in seen_numbers:
            results[-1] = UnitImportItemResult(
                row_number=row_number, status="SKIPPED", code="WARN-DUPLICATE-IN-BATCH",
                column="unit_number", message="Mã căn trùng trong cùng lô nhập.",
            )
            continue
        seen_numbers.add(candidate.unit_number)
        if candidate.unit_number in existing_numbers:
            results[-1] = UnitImportItemResult(
                row_number=row_number, status="SKIPPED", code="WARN-ALREADY-EXISTS",
                column="unit_number", message="Căn hộ đã tồn tại nên không được cập nhật.",
            )
            continue
        candidates.append(_Candidate(
            result_index=len(results) - 1,
            unit_number=candidate.unit_number,
            floor=candidate.floor,
            area_m2=candidate.area_m2,
            status=candidate.status,
        ))

    rejected = body.mode == "all_or_nothing" and any(
        result.status in {"ERROR", "SKIPPED"} for result in results
    )
    if not rejected:
        records = [
            Unit(
                building_id=building.id,
                unit_number=candidate.unit_number,
                floor=candidate.floor,
                area_m2=candidate.area_m2,
                status=candidate.status,
            )
            for candidate in candidates
        ]
        session.add_all(records)
        session.flush()
        for candidate in candidates:
            results[candidate.result_index] = results[candidate.result_index].model_copy(
                update={"status": "IMPORTED"},
            )

    response = _response(receipt_id, body, results, applied=not rejected)
    if receipt is None:  # Covered above; keeps type checkers and future edits honest.
        raise RuntimeError("Idempotency receipt was not claimed")
    receipt.response_body = response.model_dump(mode="json")
    summary = {
        "receipt_id": str(receipt_id),
        "status": response.status,
        "total_rows": response.total_rows,
        "applied_rows": response.applied_rows,
        "skipped_rows": response.skipped_rows,
        "warning_rows": response.warning_rows,
        "error_rows": response.error_rows,
        "request_hash": request_hash,
    }
    correlation_id = _correlation_id(request)
    session.add(AuditEvent(
        tenant_id=context.tenant_id,
        site_id=context.assert_active_site(),
        building_id=building.id,
        actor_account_id=context.account_id,
        event_type="UnitImportApplied" if not rejected else "UnitImportRejected",
        action="import",
        resource_type=IMPORT_RESOURCE_TYPE,
        resource_id=receipt_id,
        after_data=summary,
        correlation_id=correlation_id,
    ))
    session.add(DomainEvent(
        tenant_id=context.tenant_id,
        site_id=context.assert_active_site(),
        actor_account_id=context.account_id,
        event_type="ImportRunCompleted",
        resource_type=IMPORT_RESOURCE_TYPE,
        resource_id=receipt_id,
        correlation_id=correlation_id,
        payload=summary,
    ))
    return UnitImportExecution(response=response, replayed=False)
