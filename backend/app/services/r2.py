import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.policy import UserContext, scope_not_found
from app.models.maintenance import MaintenanceHistory, MaintenanceOccurrence, MaintenancePlan
from app.models.platform import AuditEvent, DomainEvent, IdempotencyRecord
from app.models.service import CaseRecord, ChargeReversal, CostLine, PendingCharge, ServiceRequest, WorkOrder


MAX_SLA_MINUTES = 365 * 24 * 60
MAX_MAINTENANCE_INTERVAL_DAYS = 3650
MAX_EVIDENCE_BYTES = 10 * 1024 * 1024


class ImageEvidenceError(ValueError):
    pass


def calculate_sla_deadline(started_at: datetime, duration_minutes: int) -> datetime:
    if started_at.tzinfo is None:
        raise ValueError("SLA start must be timezone-aware")
    if duration_minutes <= 0 or duration_minutes > MAX_SLA_MINUTES:
        raise ValueError("SLA duration is outside the supported range")
    return started_at + timedelta(minutes=duration_minutes)


def next_maintenance_due(due_at: datetime, interval_days: int) -> datetime:
    if due_at.tzinfo is None:
        raise ValueError("Maintenance due time must be timezone-aware")
    if interval_days <= 0 or interval_days > MAX_MAINTENANCE_INTERVAL_DAYS:
        raise ValueError("Maintenance interval is outside the supported range")
    return due_at + timedelta(days=interval_days)


def validate_image_evidence(content: bytes, claimed_mime: str) -> str:
    if not content or len(content) > MAX_EVIDENCE_BYTES:
        raise ImageEvidenceError("Image evidence is empty or too large")
    detected = None
    if (content.startswith(b"\x89PNG\r\n\x1a\n")
            and content.endswith(b"\x00\x00\x00\x00IEND\xaeB\x60\x82")):
        detected = "image/png"
    elif content.startswith(b"\xff\xd8\xff") and content.endswith(b"\xff\xd9"):
        detected = "image/jpeg"
    if detected is None or claimed_mime != detected:
        raise ImageEvidenceError("Image evidence content does not match its MIME type")
    return detected


def utc_now() -> datetime:
    return datetime.now(UTC)


def request_correlation_id(request: Request) -> UUID:
    value = getattr(request.state, "correlation_id", None)
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return uuid4()


def audit(
    session: Session,
    context: UserContext,
    request: Request,
    *,
    event_type: str,
    action: str,
    resource_type: str,
    resource_id: UUID,
    building_id: UUID | None,
    before: dict | None = None,
    after: dict | None = None,
    reason: str | None = None,
) -> None:
    session.add(AuditEvent(
        tenant_id=context.tenant_id,
        site_id=context.assert_active_site(),
        building_id=building_id,
        actor_account_id=context.account_id,
        event_type=event_type,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        before_data=before,
        after_data=after,
        reason=reason,
        correlation_id=request_correlation_id(request),
    ))


def emit(
    session: Session,
    context: UserContext,
    request: Request,
    *,
    event_type: str,
    resource_type: str,
    resource_id: UUID,
    payload: dict | None = None,
) -> None:
    session.add(DomainEvent(
        tenant_id=context.tenant_id,
        site_id=context.assert_active_site(),
        actor_account_id=context.account_id,
        event_type=event_type,
        resource_type=resource_type,
        resource_id=resource_id,
        correlation_id=request_correlation_id(request),
        payload=payload or {},
    ))


def payload_hash(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_idempotency_key(value: str | None) -> str:
    if value is None or not re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", value):
        raise AppError("ERR-IDEMPOTENCY-KEY", "Idempotency-Key phải dài 8-128 ký tự an toàn.", 400)
    return value


def idempotency_replay(
    session: Session,
    context: UserContext,
    *,
    operation: str,
    key: str | None,
    payload: object,
) -> IdempotencyRecord | None:
    safe_key = validate_idempotency_key(key)
    existing = session.scalar(select(IdempotencyRecord).where(
        IdempotencyRecord.tenant_id == context.tenant_id,
        IdempotencyRecord.site_id == context.assert_active_site(),
        IdempotencyRecord.actor_account_id == context.account_id,
        IdempotencyRecord.operation == operation,
        IdempotencyRecord.idempotency_key == safe_key,
    ))
    if existing is not None and existing.request_hash != payload_hash(payload):
        raise AppError("ERR-CONFLICT", "Idempotency-Key đã được dùng cho nội dung khác.", 409)
    return existing


def remember_idempotency(
    session: Session,
    context: UserContext,
    *,
    operation: str,
    key: str,
    payload: object,
    resource_type: str,
    resource_id: UUID,
    response_status: int,
    response_body: dict | None = None,
) -> None:
    session.add(IdempotencyRecord(
        tenant_id=context.tenant_id,
        site_id=context.assert_active_site(),
        actor_account_id=context.account_id,
        operation=operation,
        idempotency_key=validate_idempotency_key(key),
        request_hash=payload_hash(payload),
        resource_type=resource_type,
        resource_id=resource_id,
        response_status=response_status,
        response_body=response_body,
    ))


def require_version(actual: int, expected: int) -> None:
    if actual != expected:
        raise AppError("ERR-CONFLICT", "Dữ liệu đã được cập nhật. Hãy tải lại rồi thử lại.", 409)


def scoped_service_request(
    session: Session, context: UserContext, request_id: UUID, *, lock: bool = False,
) -> ServiceRequest:
    statement = select(ServiceRequest).where(
        ServiceRequest.id == request_id, *context.scope_conditions(ServiceRequest),
    )
    if lock:
        statement = statement.with_for_update()
    record = session.scalar(statement)
    if record is None:
        raise scope_not_found()
    return record


def scoped_work_order(
    session: Session, context: UserContext, work_order_id: UUID, *, lock: bool = False,
) -> WorkOrder:
    statement = select(WorkOrder).where(
        WorkOrder.id == work_order_id, *context.scope_conditions(WorkOrder),
    )
    if lock:
        statement = statement.with_for_update()
    record = session.scalar(statement)
    if record is None:
        raise scope_not_found()
    return record


def recalculate_request_state(session: Session, service_request: ServiceRequest, actor_id: UUID) -> None:
    work_orders = session.scalars(select(WorkOrder).where(
        WorkOrder.service_request_id == service_request.id,
    ).order_by(WorkOrder.id).with_for_update()).all()
    terminal = {"COMPLETED", "CLOSED", "CANCELLED"}
    if work_orders and all(work_order.status in terminal for work_order in work_orders):
        # Closing a child after the request was explicitly closed must not reopen
        # the parent. A reopened child, however, always reopens the parent below.
        if service_request.status != "CLOSED":
            service_request.status = "RESOLVED"
            service_request.resolved_at = service_request.resolved_at or utc_now()
    elif work_orders:
        service_request.status = "IN_PROGRESS"
        service_request.resolved_at = None
        service_request.closed_at = None
    service_request.updated_by_id = actor_id
    service_request.version += 1


def complete_maintenance(
    session: Session, occurrence: MaintenanceOccurrence, work_order: WorkOrder,
    *, performed_by_id: UUID, accepted_by_id: UUID,
) -> MaintenanceHistory:
    if occurrence is None or performed_by_id is None:
        raise AppError("ERR-MNT-INTEGRITY", "Công việc bảo trì thiếu liên kết hợp lệ.", 409)
    plan = session.scalar(select(MaintenancePlan).where(
        MaintenancePlan.id == occurrence.plan_id,
    ).with_for_update())
    if plan is None:
        raise scope_not_found()
    occurrence.status = "COMPLETED"
    occurrence.completed_at = work_order.completed_at
    occurrence.updated_by_id = accepted_by_id
    occurrence.version += 1
    plan.next_due_at = next_maintenance_due(occurrence.due_at, plan.interval_days)
    plan.updated_by_id = accepted_by_id
    plan.version += 1
    history = MaintenanceHistory(
        tenant_id=occurrence.tenant_id,
        site_id=occurrence.site_id,
        asset_id=plan.asset_id,
        occurrence_id=occurrence.id,
        work_order_id=work_order.id,
        performed_by_id=performed_by_id,
        accepted_by_id=accepted_by_id,
        result_summary=work_order.result_summary or "Hoàn thành bảo trì",
        completed_at=work_order.completed_at or utc_now(),
    )
    session.add(history)
    return history


def reverse_posted_charges(
    session: Session, context: UserContext, request: Request, work_order: WorkOrder, reason: str,
) -> CaseRecord | None:
    charges = session.scalars(select(PendingCharge).join(
        CostLine, PendingCharge.cost_line_id == CostLine.id,
    ).where(CostLine.work_order_id == work_order.id, PendingCharge.status == "POSTED").with_for_update()).all()
    if not charges:
        return None
    case_record = CaseRecord(
        tenant_id=work_order.tenant_id,
        site_id=work_order.site_id,
        building_id=work_order.building_id,
        source_work_order_id=work_order.id,
        reason=reason,
        status="NEW",
        created_by_id=context.account_id,
        updated_by_id=context.account_id,
    )
    session.add(case_record)
    session.flush()
    for charge in charges:
        previous = charge.status
        charge.status = "REVERSED"
        charge.version += 1
        session.add(ChargeReversal(
            pending_charge_id=charge.id,
            case_id=case_record.id,
            reason=reason,
            created_by_id=context.account_id,
            created_at=utc_now(),
        ))
        audit(session, context, request, event_type="PendingChargeReversed", action="reverse",
              resource_type="PendingCharge", resource_id=charge.id, building_id=work_order.building_id,
              before={"status": previous}, after={"status": charge.status}, reason=reason)
    emit(session, context, request, event_type="CaseOpened", resource_type="Case",
         resource_id=case_record.id, payload={"source_work_order_id": str(work_order.id)})
    return case_record
