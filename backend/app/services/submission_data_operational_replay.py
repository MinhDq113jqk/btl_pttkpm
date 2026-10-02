"""Domain-command replay for FCS-13, FCS-14 and FCS-15.

The submission workbooks are treated as source facts.  This module resolves
their already-created reference rows and drives the persisted state machines;
it does not insert terminal invoice, ledger or case rows from an oracle file.
Every operation is deterministic and guarded by the same database uniqueness
constraints used by the HTTP commands, so a retry is a readback rather than a
second set of side effects.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal
import hashlib
import hmac
import os
from typing import Mapping, Sequence
from uuid import UUID, uuid5

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.models.account import Account, AccountRole
from app.models.billing import (
    AccountingPeriod,
    ArLedgerEntry,
    BillingAccount,
    BillingInvoice,
    BillingInvoiceItem,
    BillingRun,
    FeePolicy,
    FeePolicyVersion,
    OverpaymentCredit,
    Payment,
    PaymentAllocation,
    UnmatchedPayment,
)
from app.models.building import Building
from app.models.maintenance import Asset, MaintenanceOccurrence, MaintenancePlan
from app.models.operations import (
    CleaningChecklistResult,
    CleaningShift,
    CleaningTask,
    IncidentEscalation,
    IncidentEscalationAcknowledgement,
    PatrolLog,
    PatrolPoint,
    PatrolWindow,
    SecurityIncident,
    SecurityIncidentEvidence,
    SecurityShift,
    SecurityShiftHandoff,
)
from app.models.parcel import PARCEL_STATUS_TRANSITIONS, Parcel
from app.models.platform import AuditEvent, DomainEvent, IdempotencyRecord
from app.models.service import CaseRecord, WorkOrder, WorkOrderChecklistItem
from app.models.site import Site
from app.models.submission_import import SubmissionExternalReference, SubmissionImportRun
from app.models.tenant import Tenant
from app.models.unit import Unit
from app.services.billing import allocate_payment, execute_run, receive_payment_command
from app.services.submission_data_import import (
    SubmissionImportError,
    canonical_payload_sha256,
    upsert_external_reference,
)
from app.services.submission_data_mapping import derive_fee_policy_code, derive_period_key
from app.services.submission_data_normalization import normalize_date, normalize_enum, normalize_temporal
from app.services.submission_data_replay import (
    SubmissionReplayError,
    _audit,
    _emit,
    _structure,
)


class OperationalReplayError(SubmissionReplayError):
    """A source fact cannot be applied without breaking a domain invariant."""


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _required(value: object, code: str) -> str:
    result = _text(value)
    if not result:
        raise OperationalReplayError(code)
    return result


def _utc(value: object, *, field: str) -> datetime:
    try:
        return normalize_temporal(
            value,
            field=field,
            as_of_utc=datetime.max.replace(tzinfo=UTC),
        ).utc
    except (TypeError, ValueError) as exc:
        raise OperationalReplayError(f"REPLAY_{field.upper()}_INVALID") from exc


def _as_of(as_of_utc: datetime) -> datetime:
    if as_of_utc.tzinfo is None or as_of_utc.utcoffset() is None:
        raise OperationalReplayError("REPLAY_AS_OF_NOT_TIMEZONE_AWARE")
    return as_of_utc.astimezone(UTC)


def _correlation(run: SubmissionImportRun, key: str) -> UUID:
    return uuid5(run.correlation_id, key)


def _reference(
    session: Session,
    *,
    tenant_id: UUID,
    source: str,
    entity_type: str,
    source_key: str,
    error_code: str,
):
    reference = session.scalar(select(SubmissionExternalReference).where(
        SubmissionExternalReference.tenant_id == tenant_id,
        SubmissionExternalReference.source == source,
        SubmissionExternalReference.entity_type == entity_type,
        SubmissionExternalReference.source_key == source_key,
    ))
    if reference is None:
        raise OperationalReplayError(error_code)
    return reference


def _record_idempotency(
    session: Session,
    *,
    tenant_id: UUID,
    site_id: UUID,
    actor_id: UUID,
    operation: str,
    key: str,
    payload: Mapping[str, object],
    resource_type: str,
    resource_id: UUID,
) -> None:
    digest = canonical_payload_sha256(payload)
    existing = session.scalar(select(IdempotencyRecord).where(
        IdempotencyRecord.tenant_id == tenant_id,
        IdempotencyRecord.site_id == site_id,
        IdempotencyRecord.actor_account_id == actor_id,
        IdempotencyRecord.operation == operation,
        IdempotencyRecord.idempotency_key == key,
    ).with_for_update())
    if existing is not None:
        if existing.request_hash != digest or existing.resource_id != resource_id:
            raise OperationalReplayError("REPLAY_IDEMPOTENCY_CONFLICT")
        return
    session.add(IdempotencyRecord(
        tenant_id=tenant_id,
        site_id=site_id,
        actor_account_id=actor_id,
        operation=operation,
        idempotency_key=key,
        request_hash=digest,
        resource_type=resource_type,
        resource_id=resource_id,
        response_status=200,
    ))


def _account_by_id(session: Session, account_id: UUID | None, code: str) -> Account:
    account = session.get(Account, account_id) if account_id else None
    if account is None or not account.is_active:
        raise OperationalReplayError(code)
    return account


def _role_accounts(
    session: Session,
    *,
    tenant_id: UUID,
    site_id: UUID,
    building_id: UUID,
    role: str,
) -> list[Account]:
    return session.scalars(select(Account).join(AccountRole).where(
        Account.tenant_id == tenant_id,
        Account.is_active.is_(True),
        AccountRole.role == role,
        AccountRole.site_id == site_id,
        (AccountRole.building_id.is_(None) | (AccountRole.building_id == building_id)),
    ).order_by(Account.id)).all()


def _single_role_account(
    session: Session,
    *,
    tenant_id: UUID,
    site_id: UUID,
    building_id: UUID,
    role: str,
    code: str,
) -> Account:
    accounts = _role_accounts(
        session,
        tenant_id=tenant_id,
        site_id=site_id,
        building_id=building_id,
        role=role,
    )
    if len(accounts) != 1:
        raise OperationalReplayError(code)
    return accounts[0]


def _account_by_username(
    session: Session,
    *,
    tenant_id: UUID,
    site_id: UUID,
    building_id: UUID,
    username: str,
    role: str,
    error_code: str,
) -> Account:
    """Resolve a source actor by username and explicit role/scope only."""
    accounts = session.scalars(select(Account).join(AccountRole).where(
        Account.tenant_id == tenant_id,
        Account.username == username,
        Account.is_active.is_(True),
        AccountRole.role == role,
        AccountRole.site_id == site_id,
        (AccountRole.building_id.is_(None) | (AccountRole.building_id == building_id)),
    ).order_by(Account.id)).all()
    if len(accounts) != 1:
        raise OperationalReplayError(error_code)
    return accounts[0]


def _set_cleaning_checklist(
    session: Session,
    task: CleaningTask,
    row: Mapping[str, object],
    *,
    actor_id: UUID,
    performed_at: datetime,
    correlation_id: UUID,
) -> list[CleaningChecklistResult]:
    values = [
        normalize_enum(row.get("checklist_floor"), ("PENDING", "PASS", "FAIL", "NOT_APPLICABLE", "REWORK"), field="checklist_floor", output_case="preserve"),
        normalize_enum(row.get("checklist_bins"), ("PENDING", "PASS", "FAIL", "NOT_APPLICABLE", "REWORK"), field="checklist_bins", output_case="preserve"),
        normalize_enum(row.get("quality_result"), ("PENDING", "PASS", "FAIL", "NOT_APPLICABLE", "REWORK"), field="quality_result", output_case="preserve"),
    ]
    if not isinstance(row.get("rework_required"), bool):
        raise OperationalReplayError("CLEANING_REWORK_FLAG_INVALID")
    if row.get("rework_required") and "FAIL" not in values and "REWORK" not in values:
        values[2] = "FAIL"
    checklist = session.scalars(select(CleaningChecklistResult).where(
        CleaningChecklistResult.cleaning_task_id == task.id,
    ).order_by(CleaningChecklistResult.position).with_for_update()).all()
    if len(checklist) != 3:
        raise OperationalReplayError("CLEANING_CHECKLIST_SHAPE_INVALID")
    failed: list[CleaningChecklistResult] = []
    for item, value in zip(checklist, values, strict=True):
        result = "FAIL" if value == "REWORK" else value
        if item.result == result and (result == "PENDING" or item.performed_by_id == actor_id):
            if result == "FAIL":
                failed.append(item)
            continue
        if item.result not in {"PENDING", result} and item.result != "FAIL":
            raise OperationalReplayError("CLEANING_CHECKLIST_CONFLICT")
        item.result = result
        if result != "PENDING":
            item.performed_by_id = actor_id
            item.performed_at = performed_at
        item.version += 1
        _audit(
            session,
            tenant_id=task.tenant_id,
            site_id=task.site_id,
            building_id=task.building_id,
            actor_id=actor_id,
            correlation_id=correlation_id,
            event_type="CleaningChecklistReplayed",
            action="checklist-update",
            resource_type="CleaningChecklistResult",
            resource_id=item.id,
            after={"result": result},
        )
        if result == "FAIL":
            failed.append(item)
    return failed


def _create_cleaning_rework_case(
    session: Session,
    task: CleaningTask,
    failed: Sequence[CleaningChecklistResult],
    *,
    actor_id: UUID,
    correlation_id: UUID,
) -> tuple[WorkOrder, CaseRecord]:
    existing = session.scalar(select(WorkOrder).where(WorkOrder.cleaning_task_id == task.id).with_for_update())
    if existing is not None:
        case_record = session.scalar(select(CaseRecord).where(CaseRecord.source_work_order_id == existing.id))
        if case_record is None:
            case_record = CaseRecord(
                tenant_id=task.tenant_id,
                site_id=task.site_id,
                building_id=task.building_id,
                source_work_order_id=existing.id,
                reason="Checklist vệ sinh không đạt từ approved source.",
                created_by_id=actor_id,
                updated_by_id=actor_id,
            )
            session.add(case_record)
            session.flush()
        return existing, case_record
    labels = ", ".join(item.label for item in failed)
    work_order = WorkOrder(
        tenant_id=task.tenant_id,
        site_id=task.site_id,
        building_id=task.building_id,
        cleaning_task_id=task.id,
        code=f"CWO-{task.id.hex[:12].upper()}",
        title="Làm lại vệ sinh từ approved source",
        description=f"Checklist không đạt: {labels}"[:500],
        status="DRAFT",
        created_by_id=actor_id,
        updated_by_id=actor_id,
    )
    session.add(work_order)
    session.flush()
    session.add_all(WorkOrderChecklistItem(
        work_order_id=work_order.id,
        position=position,
        label=item.label,
        is_required=True,
    ) for position, item in enumerate(failed, 1))
    case_record = CaseRecord(
        tenant_id=task.tenant_id,
        site_id=task.site_id,
        building_id=task.building_id,
        source_work_order_id=work_order.id,
        reason=f"Checklist không đạt: {labels}"[:500],
        created_by_id=actor_id,
        updated_by_id=actor_id,
    )
    session.add(case_record)
    session.flush()
    _audit(
        session,
        tenant_id=task.tenant_id,
        site_id=task.site_id,
        building_id=task.building_id,
        actor_id=actor_id,
        correlation_id=correlation_id,
        event_type="CleaningReworkWorkOrderCreated",
        action="create",
        resource_type="WorkOrder",
        resource_id=work_order.id,
        after={"cleaning_task_id": str(task.id)},
    )
    _audit(
        session,
        tenant_id=task.tenant_id,
        site_id=task.site_id,
        building_id=task.building_id,
        actor_id=actor_id,
        correlation_id=correlation_id,
        event_type="CleaningReworkCaseOpened",
        action="create",
        resource_type="Case",
        resource_id=case_record.id,
        after={"source_work_order_id": str(work_order.id)},
    )
    _emit(
        session,
        tenant_id=task.tenant_id,
        site_id=task.site_id,
        actor_id=actor_id,
        correlation_id=correlation_id,
        event_type="CleaningReworkRequired",
        resource_type="CleaningTask",
        resource_id=task.id,
        payload={"work_order_id": str(work_order.id), "case_id": str(case_record.id)},
    )
    return work_order, case_record


def replay_maintenance_cleaning(
    session: Session,
    maintenance_rows: Sequence[Mapping[str, object]],
    cleaning_rows: Sequence[Mapping[str, object]],
    run: SubmissionImportRun,
    *,
    as_of_utc: datetime,
) -> dict[str, int]:
    """Replay FCS-13 Asset/Plan scheduler and cleaning checklist commands."""

    as_of = _as_of(as_of_utc)
    counts: defaultdict[str, int] = defaultdict(int)
    for row in maintenance_rows:
        tenant, site, building, _ = _structure(session, row)
        asset_code = _required(row.get("asset_code"), "ASSET_CODE_REQUIRED")
        asset = session.scalar(select(Asset).where(
            Asset.site_id == site.id,
            Asset.code == asset_code,
        ).with_for_update())
        if asset is None:
            raise OperationalReplayError("MAINTENANCE_ASSET_NOT_FOUND")
        plan_code = _required(row.get("maintenance_plan_code"), "MAINTENANCE_PLAN_CODE_REQUIRED")
        plan = session.scalar(select(MaintenancePlan).where(
            MaintenancePlan.asset_id == asset.id,
            MaintenancePlan.code == plan_code,
        ).with_for_update())
        if plan is None:
            raise OperationalReplayError("MAINTENANCE_PLAN_NOT_FOUND")
        if plan.next_due_at > as_of:
            raise OperationalReplayError("REPLAY_FUTURE_SCHEDULE")
        actor = _account_by_id(session, asset.updated_by_id, "MAINTENANCE_ACTOR_NOT_FOUND")
        correlation_id = _correlation(run, f"fcs13:maintenance:{asset_code}:{plan_code}:{plan.next_due_at.isoformat()}")
        occurrence = session.scalar(select(MaintenanceOccurrence).where(
            MaintenanceOccurrence.plan_id == plan.id,
            MaintenanceOccurrence.due_at == plan.next_due_at,
        ).with_for_update())
        if occurrence is None:
            occurrence = MaintenanceOccurrence(
                tenant_id=tenant.id,
                site_id=site.id,
                building_id=building.id,
                plan_id=plan.id,
                due_at=plan.next_due_at,
                status="DUE",
                created_by_id=actor.id,
                updated_by_id=actor.id,
            )
            session.add(occurrence)
            session.flush()
            _audit(
                session,
                tenant_id=tenant.id,
                site_id=site.id,
                building_id=building.id,
                actor_id=actor.id,
                correlation_id=correlation_id,
                event_type="MaintenanceOccurrenceDue",
                action="schedule",
                resource_type="MaintenanceOccurrence",
                resource_id=occurrence.id,
                after={"due_at": occurrence.due_at.isoformat()},
            )
            counts["maintenance_occurrences_created"] += 1
        work_order = session.scalar(select(WorkOrder).where(
            WorkOrder.maintenance_occurrence_id == occurrence.id,
        ).with_for_update())
        if work_order is None:
            work_order = WorkOrder(
                tenant_id=tenant.id,
                site_id=site.id,
                building_id=building.id,
                maintenance_occurrence_id=occurrence.id,
                code=f"MWO-{occurrence.id.hex[:12].upper()}",
                title=plan.title,
                description=f"Bảo trì định kỳ cho kế hoạch {plan.code}",
                status="DRAFT",
                created_by_id=actor.id,
                updated_by_id=actor.id,
            )
            session.add(work_order)
            session.flush()
            session.add_all(WorkOrderChecklistItem(
                work_order_id=work_order.id,
                position=position,
                label=item["label"],
                is_required=item.get("required", True),
            ) for position, item in enumerate(plan.checklist_template, 1))
            counts["maintenance_work_orders_created"] += 1
        if occurrence.status in {"DUE", "DEFERRED"}:
            occurrence.status = "WO_CREATED"
            occurrence.defer_until = None
            occurrence.defer_reason = None
            occurrence.updated_by_id = actor.id
            occurrence.version += 1
        upsert_external_reference(
            session,
            run,
            tenant_id=tenant.id,
            source="maintenance",
            entity_type="MaintenanceOccurrence",
            source_key=f"{asset_code}:{plan_code}:{plan.next_due_at.isoformat()}",
            target_id=occurrence.id,
            payload={"asset_code": asset_code, "plan_code": plan_code},
        )
        _record_idempotency(
            session,
            tenant_id=tenant.id,
            site_id=site.id,
            actor_id=actor.id,
            operation="submission.maintenance.replay",
            key=f"maintenance:{asset_code}:{plan_code}:{plan.next_due_at.isoformat()}",
            payload={"asset_code": asset_code, "plan_code": plan_code, "due_at": plan.next_due_at.isoformat()},
            resource_type="MaintenanceOccurrence",
            resource_id=occurrence.id,
        )
        counts["maintenance_rows"] += 1

    for row in cleaning_rows:
        tenant, site, building, _ = _structure(session, row)
        shift_code = _required(row.get("shift_code"), "CLEANING_SHIFT_REQUIRED")
        ref = _reference(
            session,
            tenant_id=tenant.id,
            source="cleaning",
            entity_type="CleaningShift",
            source_key=f"{site.code}:{shift_code}",
            error_code="CLEANING_SHIFT_REFERENCE_NOT_FOUND",
        )
        shift = session.scalar(select(CleaningShift).where(CleaningShift.id == ref.target_id).with_for_update())
        if shift is None:
            raise OperationalReplayError("CLEANING_SHIFT_REFERENCE_TARGET_MISSING")
        task = session.scalar(select(CleaningTask).where(
            CleaningTask.shift_id == shift.id,
        ).order_by(CleaningTask.id).with_for_update())
        if task is None or task.assigned_to_id is None:
            raise OperationalReplayError("CLEANING_TASK_REFERENCE_NOT_FOUND")
        actor = _account_by_id(session, task.assigned_to_id, "CLEANING_ACTOR_NOT_FOUND")
        source_status = normalize_enum(
            row.get("status"),
            ("PLANNED", "IN_PROGRESS", "COMPLETED", "CANCELLED"),
            field="cleaning_status",
            output_case="preserve",
        )
        correlation_id = _correlation(run, f"fcs13:cleaning:{shift_code}")
        performed_at = min(shift.scheduled_end_at, as_of)
        failed: list[CleaningChecklistResult] = []
        if source_status in {"IN_PROGRESS", "COMPLETED"}:
            failed = _set_cleaning_checklist(
                session,
                task,
                row,
                actor_id=actor.id,
                performed_at=performed_at,
                correlation_id=correlation_id,
            )
        if source_status == "PLANNED":
            desired_task_status = "PLANNED"
            desired_shift_status = "PLANNED"
        elif source_status == "IN_PROGRESS":
            desired_task_status = "IN_PROGRESS"
            desired_shift_status = "IN_PROGRESS"
        elif source_status == "CANCELLED":
            desired_task_status = "CANCELLED"
            desired_shift_status = "CANCELLED"
        else:
            desired_task_status = "REWORK_REQUIRED" if failed else "ACCEPTED"
            desired_shift_status = "COMPLETED"
        if desired_task_status == "IN_PROGRESS" and task.status in {"PLANNED", "ASSIGNED"}:
            task.status = "IN_PROGRESS"
            task.started_at = shift.scheduled_start_at
            task.updated_by_id = actor.id
            task.version += 1
        elif desired_task_status == "CANCELLED" and task.status != "CANCELLED":
            if task.status not in {"PLANNED", "ASSIGNED", "IN_PROGRESS"}:
                raise OperationalReplayError("CLEANING_STATE_CONFLICT")
            task.status = "CANCELLED"
            task.updated_by_id = actor.id
            task.version += 1
        elif desired_task_status == "ACCEPTED" and task.status != "ACCEPTED":
            if task.status not in {"PLANNED", "ASSIGNED", "IN_PROGRESS", "SUBMITTED"}:
                raise OperationalReplayError("CLEANING_STATE_CONFLICT")
            if task.status in {"PLANNED", "ASSIGNED"}:
                task.started_at = shift.scheduled_start_at
            task.status = "SUBMITTED"
            task.submitted_at = performed_at
            task.updated_by_id = actor.id
            task.version += 1
            acceptor = _single_role_account(
                session,
                tenant_id=tenant.id,
                site_id=site.id,
                building_id=building.id,
                role="technical_lead",
                code="CLEANING_ACCEPTOR_AMBIGUOUS",
            )
            task.status = "ACCEPTED"
            task.accepted_at = performed_at
            task.accepted_by_id = acceptor.id
            task.updated_by_id = acceptor.id
            task.version += 1
            _audit(
                session,
                tenant_id=tenant.id,
                site_id=site.id,
                building_id=building.id,
                actor_id=acceptor.id,
                correlation_id=correlation_id,
                event_type="CleaningTaskAccepted",
                action="accept",
                resource_type="CleaningTask",
                resource_id=task.id,
                after={"status": "ACCEPTED"},
            )
        elif desired_task_status == "REWORK_REQUIRED" and task.status != "REWORK_REQUIRED":
            if task.status not in {"PLANNED", "ASSIGNED", "IN_PROGRESS", "SUBMITTED", "REWORK_REQUIRED"}:
                raise OperationalReplayError("CLEANING_STATE_CONFLICT")
            task.status = "REWORK_REQUIRED"
            task.submitted_at = performed_at
            task.updated_by_id = actor.id
            task.version += 1
            _create_cleaning_rework_case(
                session,
                task,
                failed,
                actor_id=actor.id,
                correlation_id=correlation_id,
            )
        if shift.status != desired_shift_status:
            if shift.status == "COMPLETED" and desired_shift_status != "COMPLETED":
                raise OperationalReplayError("CLEANING_SHIFT_STATE_CONFLICT")
            shift.status = desired_shift_status
            shift.updated_by_id = actor.id
            shift.version += 1
        _record_idempotency(
            session,
            tenant_id=tenant.id,
            site_id=site.id,
            actor_id=actor.id,
            operation="submission.cleaning.replay",
            key=f"cleaning:{shift_code}",
            payload={"shift_code": shift_code, "status": source_status, "rework": bool(row.get("rework_required"))},
            resource_type="CleaningTask",
            resource_id=task.id,
        )
        counts["cleaning_rows"] += 1
        counts[f"cleaning_{desired_task_status.lower()}"] += 1
        if desired_task_status == "REWORK_REQUIRED":
            counts["cleaning_rework_cases"] += 1
    return dict(counts)


def _deterministic_pin(parcel_code: str) -> str:
    secret = os.getenv("GREENCITY_SUBMISSION_PIN_SECRET", "").strip()
    if len(secret.encode("utf-8")) < 16:
        raise OperationalReplayError("SUBMISSION_PIN_SECRET_REQUIRED")
    return hmac.new(
        secret.encode("utf-8"),
        parcel_code.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:12]


def _security_window_reason(row: Mapping[str, object]) -> str:
    # ``notes`` is intentionally ignored by the contract.  A missed patrol
    # therefore needs an explicit approved ``missed_reason`` field in the
    # replay input; silently treating free text as a reason would bypass FCS-05.
    reason = _text(row.get("missed_reason"))
    if not reason:
        raise OperationalReplayError("PATROL_MISSED_REASON_REQUIRED")
    return reason[:500]


def _replay_patrol_row(
    session: Session,
    row: Mapping[str, object],
    run: SubmissionImportRun,
    *,
    as_of: datetime,
    counts: defaultdict[str, int],
) -> None:
    tenant, site, building, _ = _structure(session, row)
    shift_code = _required(row.get("shift_code"), "SECURITY_SHIFT_REQUIRED")
    shift_ref = _reference(
        session,
        tenant_id=tenant.id,
        source="security",
        entity_type="SecurityShift",
        source_key=f"{site.code}:{building.code}:{shift_code}",
        error_code="SECURITY_SHIFT_REFERENCE_NOT_FOUND",
    )
    shift = session.scalar(select(SecurityShift).where(SecurityShift.id == shift_ref.target_id).with_for_update())
    if shift is None:
        raise OperationalReplayError("SECURITY_SHIFT_REFERENCE_TARGET_MISSING")
    point_code = _required(row.get("patrol_point_code"), "PATROL_POINT_REQUIRED")
    # Patrol points are keyed by site/code.  The resolved window keeps the
    # building-specific scope through its security shift and own building ID.
    point = session.scalar(select(PatrolPoint).where(
        PatrolPoint.site_id == site.id,
        PatrolPoint.code == point_code,
    ))
    if point is None:
        raise OperationalReplayError("PATROL_POINT_REFERENCE_NOT_FOUND")
    window_start = _utc(row.get("window_start"), field="window_start")
    window = session.scalar(select(PatrolWindow).where(
        PatrolWindow.security_shift_id == shift.id,
        PatrolWindow.patrol_point_id == point.id,
        PatrolWindow.window_start_at == window_start,
    ).with_for_update())
    if window is None:
        raise OperationalReplayError("PATROL_WINDOW_REFERENCE_NOT_FOUND")
    actor = _account_by_id(session, shift.assigned_to_id, "SECURITY_ACTOR_NOT_FOUND")
    status = normalize_enum(
        row.get("patrol_status"),
        ("SCHEDULED", "COMPLETED", "MISSED", "CANCELLED"),
        field="patrol_status",
        output_case="preserve",
    )
    correlation_id = _correlation(run, f"fcs14:patrol:{shift_code}:{point_code}:{window_start.isoformat()}")
    if status == "COMPLETED":
        if window.window_end_at > as_of:
            raise OperationalReplayError("REPLAY_FUTURE_TERMINAL_EVENT")
        if window.status == "SCHEDULED":
            window.status = "COMPLETED"
            window.completed_at = window.window_end_at
            window.updated_by_id = actor.id
            window.version += 1
        event_type = _text(row.get("event_type")) or "CHECK_IN"
        event_type = normalize_enum(event_type, ("CHECK_IN", "CHECK_OUT", "NOTE"), field="patrol_event_type", output_case="preserve")
        existing_log = session.scalar(select(PatrolLog).where(
            PatrolLog.patrol_window_id == window.id,
            PatrolLog.event_type == event_type,
        ))
        if existing_log is None:
            session.add(PatrolLog(
                patrol_window_id=window.id,
                recorded_by_id=actor.id,
                event_type=event_type,
                occurred_at=window.window_start_at,
            ))
            counts["patrol_logs_created"] += 1
    elif status == "MISSED":
        reason = _security_window_reason(row)
        if window.status == "SCHEDULED":
            window.status = "MISSED"
            window.missed_reason = reason
            window.updated_by_id = actor.id
            window.version += 1
        elif window.status == "MISSED" and window.missed_reason != reason:
            raise OperationalReplayError("PATROL_MISSED_REASON_CONFLICT")
    elif status == "CANCELLED":
        if window.status == "SCHEDULED":
            window.status = "CANCELLED"
            window.updated_by_id = actor.id
            window.version += 1
    if _text(row.get("handoff_summary")):
        receivers = _role_accounts(
            session,
            tenant_id=tenant.id,
            site_id=site.id,
            building_id=building.id,
            role="security",
        )
        receivers = [account for account in receivers if account.id != actor.id]
        if len(receivers) != 1:
            raise OperationalReplayError("SECURITY_HANDOFF_RECEIVER_AMBIGUOUS")
        existing_handoff = session.scalar(select(SecurityShiftHandoff).where(
            SecurityShiftHandoff.security_shift_id == shift.id,
            SecurityShiftHandoff.handed_over_by_id == actor.id,
            SecurityShiftHandoff.received_by_id == receivers[0].id,
            SecurityShiftHandoff.summary == _text(row.get("handoff_summary")),
        ))
        if existing_handoff is None:
            handoff = SecurityShiftHandoff(
                tenant_id=tenant.id,
                site_id=site.id,
                building_id=building.id,
                security_shift_id=shift.id,
                handed_over_by_id=actor.id,
                received_by_id=receivers[0].id,
                summary=_text(row.get("handoff_summary")),
            )
            session.add(handoff)
            session.flush()
            _audit(
                session,
                tenant_id=tenant.id,
                site_id=site.id,
                building_id=building.id,
                actor_id=actor.id,
                correlation_id=correlation_id,
                event_type="SecurityShiftHandoffRecorded",
                action="append",
                resource_type="SecurityShiftHandoff",
                resource_id=handoff.id,
                after={"security_shift_id": str(shift.id)},
            )
            counts["security_handoffs_created"] += 1
    windows = session.scalars(select(PatrolWindow).where(PatrolWindow.security_shift_id == shift.id)).all()
    if windows and all(item.status in {"COMPLETED", "MISSED", "CANCELLED"} for item in windows):
        shift.status = "COMPLETED"
    elif any(item.status != "SCHEDULED" for item in windows):
        shift.status = "IN_PROGRESS"
    shift.updated_by_id = actor.id
    shift.version += 1
    _record_idempotency(
        session,
        tenant_id=tenant.id,
        site_id=site.id,
        actor_id=actor.id,
        operation="submission.security.patrol.replay",
        key=f"patrol:{shift_code}:{point_code}:{window_start.isoformat()}",
        payload={"shift_code": shift_code, "patrol_point_code": point_code, "status": status},
        resource_type="PatrolWindow",
        resource_id=window.id,
    )
    counts["patrol_rows"] += 1


def _replay_incident_row(
    session: Session,
    row: Mapping[str, object],
    run: SubmissionImportRun,
    *,
    as_of: datetime,
    counts: defaultdict[str, int],
) -> None:
    tenant, site, building, _ = _structure(session, row)
    code = _required(row.get("incident_code"), "INCIDENT_CODE_REQUIRED")
    incident = session.scalar(select(SecurityIncident).where(
        SecurityIncident.site_id == site.id,
        SecurityIncident.code == code,
    ).with_for_update())
    if incident is None:
        raise OperationalReplayError("SECURITY_INCIDENT_REFERENCE_NOT_FOUND")
    actor = _account_by_id(session, incident.reported_by_id, "INCIDENT_ACTOR_NOT_FOUND")
    target = normalize_enum(
        row.get("status"),
        ("NEW", "TRIAGED", "IN_PROGRESS", "RESOLVED", "CLOSED"),
        field="incident_status",
        output_case="preserve",
    )
    correlation_id = _correlation(run, f"fcs14:incident:{code}")
    if incident.severity in {"HIGH", "CRITICAL"}:
        for role in ("security", "director"):
            escalation = session.scalar(select(IncidentEscalation).where(
                IncidentEscalation.security_incident_id == incident.id,
                IncidentEscalation.target_role == role,
            ).with_for_update())
            if escalation is None:
                escalation = IncidentEscalation(
                    security_incident_id=incident.id,
                    target_role=role,
                    escalated_by_id=actor.id,
                    reason=f"Escalation tự động cho sự cố {incident.severity}.",
                )
                session.add(escalation)
                session.flush()
                counts["incident_escalations_created"] += 1
            if target in {"IN_PROGRESS", "RESOLVED", "CLOSED"}:
                acknowledgement = session.scalar(select(IncidentEscalationAcknowledgement).where(
                    IncidentEscalationAcknowledgement.incident_escalation_id == escalation.id,
                ))
                if acknowledgement is None:
                    recipients = _role_accounts(
                        session,
                        tenant_id=tenant.id,
                        site_id=site.id,
                        building_id=building.id,
                        role=role,
                    )
                    recipient = recipients[0] if recipients else None
                    if recipient is None:
                        raise OperationalReplayError("INCIDENT_ESCALATION_ACK_ACTOR_NOT_FOUND")
                    acknowledgement = IncidentEscalationAcknowledgement(
                        incident_escalation_id=escalation.id,
                        acknowledged_by_id=recipient.id,
                        note="Acknowledged during approved source replay",
                    )
                    session.add(acknowledgement)
                    counts["incident_acknowledgements_created"] += 1
    if target in {"RESOLVED", "CLOSED"}:
        resolved_at = _utc(row.get("resolved_at"), field="resolved_at") if row.get("resolved_at") is not None else None
        if resolved_at is None or resolved_at > as_of:
            raise OperationalReplayError("INCIDENT_RESOLUTION_TIMESTAMP_REQUIRED")
    transitions = {"NEW": ("TRIAGED",), "TRIAGED": ("IN_PROGRESS",), "IN_PROGRESS": ("RESOLVED",), "RESOLVED": ("CLOSED",)}
    while incident.status != target:
        next_statuses = transitions.get(incident.status, ())
        if not next_statuses:
            raise OperationalReplayError("INCIDENT_STATE_CONFLICT")
        next_status = next_statuses[0]
        if next_status == "CLOSED":
            evidence_exists = session.scalar(select(SecurityIncidentEvidence.id).where(
                SecurityIncidentEvidence.security_incident_id == incident.id,
            ).limit(1)) is not None
            if not evidence_exists or not incident.conclusion:
                raise OperationalReplayError("INCIDENT_CLOSE_REQUIREMENTS")
            if incident.severity in {"HIGH", "CRITICAL"}:
                missing_ack = session.scalar(select(IncidentEscalation.id).where(
                    IncidentEscalation.security_incident_id == incident.id,
                    ~IncidentEscalation.id.in_(select(IncidentEscalationAcknowledgement.incident_escalation_id)),
                ).limit(1))
                if missing_ack is not None:
                    raise OperationalReplayError("INCIDENT_ESCALATION_UNACKNOWLEDGED")
            incident.closed_at = as_of
        if next_status == "RESOLVED":
            incident.resolved_at = _utc(row.get("resolved_at"), field="resolved_at")
        before = incident.status
        incident.status = next_status
        incident.updated_by_id = actor.id
        incident.version += 1
        _audit(
            session,
            tenant_id=tenant.id,
            site_id=site.id,
            building_id=building.id,
            actor_id=actor.id,
            correlation_id=correlation_id,
            event_type="SecurityIncidentTransitioned",
            action="transition",
            resource_type="SecurityIncident",
            resource_id=incident.id,
            before={"status": before},
            after={"status": next_status},
        )
        counts["incident_transitions"] += 1
    _record_idempotency(
        session,
        tenant_id=tenant.id,
        site_id=site.id,
        actor_id=actor.id,
        operation="submission.security.incident.replay",
        key=f"incident:{code}",
        payload={"incident_code": code, "status": target},
        resource_type="SecurityIncident",
        resource_id=incident.id,
    )
    counts["incident_rows"] += 1


def _parcel_case(
    session: Session,
    parcel: Parcel,
    *,
    actor_id: UUID,
    correlation_id: UUID,
    reason: str,
) -> CaseRecord:
    case_record = session.scalar(select(CaseRecord).where(CaseRecord.source_parcel_id == parcel.id).with_for_update())
    if case_record is not None:
        return case_record
    case_record = CaseRecord(
        tenant_id=parcel.tenant_id,
        site_id=parcel.site_id,
        building_id=parcel.building_id,
        source_parcel_id=parcel.id,
        reason=reason,
        created_by_id=actor_id,
        updated_by_id=actor_id,
    )
    session.add(case_record)
    session.flush()
    _audit(
        session,
        tenant_id=parcel.tenant_id,
        site_id=parcel.site_id,
        building_id=parcel.building_id,
        actor_id=actor_id,
        correlation_id=correlation_id,
        event_type="ParcelCaseOpened",
        action="create",
        resource_type="Case",
        resource_id=case_record.id,
        after={"source_parcel_id": str(parcel.id)},
    )
    return case_record


def _replay_parcel_row(
    session: Session,
    row: Mapping[str, object],
    run: SubmissionImportRun,
    *,
    as_of: datetime,
    counts: defaultdict[str, int],
) -> None:
    tenant, site, building, _ = _structure(session, row)
    parcel_code = _required(row.get("parcel_code"), "PARCEL_CODE_REQUIRED")
    ref = _reference(
        session,
        tenant_id=tenant.id,
        source="parcel",
        entity_type="Parcel",
        source_key=f"{site.code}:{parcel_code}",
        error_code="PARCEL_REFERENCE_NOT_FOUND",
    )
    parcel = session.scalar(select(Parcel).where(Parcel.id == ref.target_id).with_for_update())
    if parcel is None:
        raise OperationalReplayError("PARCEL_REFERENCE_TARGET_MISSING")
    actor = _account_by_id(session, parcel.updated_by_id, "PARCEL_ACTOR_NOT_FOUND")
    target = normalize_enum(
        row.get("status"),
        ("RECEIVED", "READY_FOR_PICKUP", "HANDED_OVER", "RETURNED", "LOST", "DAMAGED"),
        field="parcel_status",
        output_case="preserve",
    )
    correlation_id = _correlation(run, f"fcs14:parcel:{parcel_code}")
    if target in {"READY_FOR_PICKUP", "HANDED_OVER", "RETURNED", "LOST", "DAMAGED"}:
        ready_at = _utc(row.get("ready_at"), field="ready_at") if row.get("ready_at") is not None else parcel.received_at
        if ready_at > as_of:
            raise OperationalReplayError("REPLAY_FUTURE_TERMINAL_EVENT")
    if target == "READY_FOR_PICKUP" and parcel.status == "RECEIVED":
        parcel.status = "READY_FOR_PICKUP"
        parcel.ready_for_pickup_at = ready_at
        parcel.updated_by_id = actor.id
        parcel.version += 1
    elif target == "HANDED_OVER":
        if parcel.status == "RECEIVED":
            parcel.status = "READY_FOR_PICKUP"
            parcel.ready_for_pickup_at = ready_at
            parcel.version += 1
        if parcel.status == "READY_FOR_PICKUP":
            pin = _deterministic_pin(parcel_code)
            if not verify_password(pin, parcel.pin_hash):
                raise OperationalReplayError("PARCEL_PIN_HASH_CONFLICT")
            handed_over_at = _utc(row.get("handed_over_at"), field="handed_over_at") if row.get("handed_over_at") is not None else as_of
            if handed_over_at > as_of:
                raise OperationalReplayError("REPLAY_FUTURE_TERMINAL_EVENT")
            parcel.status = "HANDED_OVER"
            parcel.handed_over_at = handed_over_at
            parcel.handed_over_by_id = actor.id
            parcel.pin_locked_until = None
            parcel.updated_by_id = actor.id
            parcel.version += 1
    elif target in {"RETURNED", "LOST", "DAMAGED"} and parcel.status != target:
        if target not in PARCEL_STATUS_TRANSITIONS.get(parcel.status, frozenset()):
            raise OperationalReplayError("PARCEL_STATE_CONFLICT")
        parcel.status = target
        parcel.exception_reason = f"Approved source exception: {target.lower()}"
        parcel.updated_by_id = actor.id
        parcel.version += 1
    elif target != parcel.status:
        raise OperationalReplayError("PARCEL_STATE_CONFLICT")
    if bool(row.get("case_required")):
        if parcel.status not in {"HANDED_OVER", "RETURNED", "LOST", "DAMAGED"}:
            raise OperationalReplayError("PARCEL_CASE_SOURCE_INVALID")
        _parcel_case(
            session,
            parcel,
            actor_id=actor.id,
            correlation_id=correlation_id,
            reason=f"Approved source parcel exception: {parcel.status.lower()}",
        )
        counts["parcel_cases_created"] += 1
    _record_idempotency(
        session,
        tenant_id=tenant.id,
        site_id=site.id,
        actor_id=actor.id,
        operation="submission.parcel.replay",
        key=f"parcel:{parcel_code}",
        payload={"parcel_code": parcel_code, "status": target, "case_required": bool(row.get("case_required"))},
        resource_type="Parcel",
        resource_id=parcel.id,
    )
    counts["parcel_rows"] += 1


def replay_security_parcels(
    session: Session,
    patrol_rows: Sequence[Mapping[str, object]],
    incident_rows: Sequence[Mapping[str, object]],
    parcel_rows: Sequence[Mapping[str, object]],
    run: SubmissionImportRun,
    *,
    as_of_utc: datetime,
) -> dict[str, int]:
    """Replay FCS-14 patrol, incident/escalation and parcel commands."""

    as_of = _as_of(as_of_utc)
    counts: defaultdict[str, int] = defaultdict(int)
    for row in patrol_rows:
        _replay_patrol_row(session, row, run, as_of=as_of, counts=counts)
    for row in incident_rows:
        _replay_incident_row(session, row, run, as_of=as_of, counts=counts)
    for row in parcel_rows:
        _replay_parcel_row(session, row, run, as_of=as_of, counts=counts)
    return dict(counts)


def replay_billing_run(
    session: Session,
    policy_rows: Sequence[Mapping[str, object]],
    invoice_rows: Sequence[Mapping[str, object]],
    run: SubmissionImportRun,
    *,
    as_of_utc: datetime,
) -> dict[str, object]:
    """Generate Billing Runs through the billing service and reconcile file 10."""

    _as_of(as_of_utc)
    if not invoice_rows:
        raise OperationalReplayError("BILLING_ORACLE_EMPTY")
    groups: dict[tuple[str, str, str, str, int], list[Mapping[str, object]]] = defaultdict(list)
    for row in invoice_rows:
        try:
            policy_version = int(row.get("policy_version"))
        except (TypeError, ValueError) as exc:
            raise OperationalReplayError("BILLING_ORACLE_POLICY_VERSION_INVALID") from exc
        key = (
            _required(row.get("site_code"), "SITE_CODE_REQUIRED"),
            _required(row.get("building_code"), "BUILDING_CODE_REQUIRED"),
            _required(row.get("period_key"), "PERIOD_KEY_REQUIRED"),
            _required(row.get("billing_run_key"), "BILLING_RUN_KEY_REQUIRED"),
            policy_version,
        )
        groups[key].append(row)
    result: dict[str, object] = {
        "runs_created": 0,
        "runs_replayed": 0,
        "invoice_count": 0,
        "invoice_item_count": 0,
        "total_vnd": 0,
        "status_pending_fcs16": 0,
        "reconciled": True,
    }
    for (site_code, building_code, period_key, run_key, policy_version_number), rows in groups.items():
        representative = rows[0]
        tenant, site, building, _ = _structure(session, representative)
        policy_code = derive_fee_policy_code(representative, policy_rows)
        policy = session.scalar(select(FeePolicy).where(
            FeePolicy.building_id == building.id,
            FeePolicy.code == policy_code,
        ).with_for_update())
        if policy is None:
            raise OperationalReplayError("BILLING_POLICY_REFERENCE_NOT_FOUND")
        version = session.scalar(select(FeePolicyVersion).where(
            FeePolicyVersion.fee_policy_id == policy.id,
            FeePolicyVersion.version_number == policy_version_number,
        ).with_for_update())
        period = session.scalar(select(AccountingPeriod).where(
            AccountingPeriod.building_id == building.id,
            AccountingPeriod.period_key == period_key,
        ).with_for_update())
        if version is None or period is None:
            raise OperationalReplayError("BILLING_PERIOD_POLICY_REFERENCE_NOT_FOUND")
        accountants = _role_accounts(
            session,
            tenant_id=tenant.id,
            site_id=site.id,
            building_id=building.id,
            role="accountant",
        )
        if not accountants:
            raise OperationalReplayError("BILLING_ACTOR_NOT_FOUND")
        actor = accountants[0]
        expected_by_account: dict[str, Mapping[str, object]] = {}
        for row in rows:
            account_number = _required(row.get("billing_account_number"), "BILLING_ACCOUNT_NUMBER_REQUIRED")
            if account_number in expected_by_account:
                raise OperationalReplayError("BILLING_ORACLE_DUPLICATE_ACCOUNT")
            expected_by_account[account_number] = row
        accounts = session.scalars(select(BillingAccount).where(
            BillingAccount.building_id == building.id,
            BillingAccount.status == "ACTIVE",
            BillingAccount.opened_on <= period.period_end,
        ).order_by(BillingAccount.account_number, BillingAccount.id).with_for_update()).all()
        if {account.account_number for account in accounts} != set(expected_by_account):
            raise OperationalReplayError("BILLING_ORACLE_ACCOUNT_COUNT_MISMATCH")
        for account in accounts:
            row = expected_by_account[account.account_number]
            if _text(row.get("unit_number")) != _text(session.get(Unit, account.unit_id).unit_number):
                raise OperationalReplayError("BILLING_ORACLE_UNIT_MISMATCH")
        existing_run = session.scalar(select(BillingRun).where(
            BillingRun.site_id == site.id,
            BillingRun.run_key == run_key,
        ).with_for_update())
        if existing_run is None:
            existing_run = BillingRun(
                tenant_id=tenant.id,
                site_id=site.id,
                building_id=building.id,
                accounting_period_id=period.id,
                fee_policy_version_id=version.id,
                run_key=run_key,
                cutoff_at=period.cutoff_at,
                initiated_by_id=actor.id,
            )
            session.add(existing_run)
            session.flush()
            result["runs_created"] = int(result["runs_created"]) + 1
        elif existing_run.status == "POSTED":
            result["runs_replayed"] = int(result["runs_replayed"]) + 1
        elif existing_run.status == "FAILED":
            existing_run.retry_count += 1
        else:
            raise OperationalReplayError("BILLING_RUN_STATE_CONFLICT")
        by_account = expected_by_account

        def invoice_number(account: BillingAccount) -> str:
            return _required(by_account.get(account.account_number, {}).get("invoice_number"), "BILLING_ORACLE_INVOICE_NUMBER_REQUIRED")

        def issued_on(account: BillingAccount) -> date | None:
            value = by_account[account.account_number].get("issued_on")
            return normalize_date(value, field="issued_on") if value is not None else None

        def due_on(account: BillingAccount) -> date | None:
            value = by_account[account.account_number].get("due_on")
            return normalize_date(value, field="due_on") if value is not None else None

        if existing_run.status != "POSTED":
            execute_run(
                session,
                existing_run,
                period,
                version,
                actor.id,
                invoice_number_resolver=invoice_number,
                issued_on_resolver=issued_on,
                due_on_resolver=due_on,
            )
            if existing_run.status != "POSTED":
                raise OperationalReplayError(existing_run.failure_code or "BILLING_RUN_FAILED")
        invoices = session.scalars(select(BillingInvoice).where(
            BillingInvoice.billing_run_id == existing_run.id,
        ).order_by(BillingInvoice.invoice_number)).all()
        if len(invoices) != len(rows):
            raise OperationalReplayError("BILLING_ORACLE_INVOICE_COUNT_MISMATCH")
        for invoice in invoices:
            oracle = next((item for item in rows if item.get("invoice_number") == invoice.invoice_number), None)
            if oracle is None:
                raise OperationalReplayError("BILLING_ORACLE_INVOICE_KEY_MISMATCH")
            expected_total = int(Decimal(str(oracle.get("total_vnd"))))
            expected_outstanding = int(Decimal(str(oracle.get("outstanding_vnd"))))
            if invoice.total_vnd != expected_total:
                raise OperationalReplayError("BILLING_ORACLE_TOTAL_MISMATCH")
            item_rows = session.scalars(select(BillingInvoiceItem).where(
                BillingInvoiceItem.billing_invoice_id == invoice.id,
            ).order_by(BillingInvoiceItem.line_number)).all()
            if invoice.total_vnd != sum(item.amount_vnd for item in item_rows):
                raise OperationalReplayError("BILLING_INVOICE_ITEM_SUM_MISMATCH")
            for item in item_rows:
                if item.fee_policy_version_id != version.id or item.rounding_unit_vnd_snapshot != version.rounding_unit_vnd:
                    raise OperationalReplayError("BILLING_POLICY_SNAPSHOT_MISMATCH")
            expected_status = _text(oracle.get("invoice_status"))
            if expected_status != invoice.status:
                if expected_status in {"PAID", "PARTIALLY_PAID"} and invoice.status == "ISSUED":
                    result["status_pending_fcs16"] = int(result["status_pending_fcs16"]) + 1
                else:
                    raise OperationalReplayError("BILLING_ORACLE_STATUS_MISMATCH")
            if expected_status == "ISSUED" and invoice.outstanding_vnd != expected_outstanding:
                raise OperationalReplayError("BILLING_ORACLE_OUTSTANDING_MISMATCH")
            result["invoice_count"] = int(result["invoice_count"]) + 1
            result["invoice_item_count"] = int(result["invoice_item_count"]) + len(item_rows)
            result["total_vnd"] = int(result["total_vnd"]) + invoice.total_vnd
    return result


def replay_payment_allocations(
    session: Session,
    payment_rows: Sequence[Mapping[str, object]],
    invoice_rows: Sequence[Mapping[str, object]],
    policy_rows: Sequence[Mapping[str, object]],
    run: SubmissionImportRun,
    *,
    as_of_utc: datetime,
) -> dict[str, object]:
    """Replay FCS-16 receipts through payment commands and reconcile AR.

    File 11 is treated as an oracle for the command result.  Payment, ledger,
    allocation and credit rows are created only by the domain command/service;
    the loader never inserts an oracle status or balance directly.
    """
    as_of = _as_of(as_of_utc)
    if not payment_rows:
        raise OperationalReplayError("PAYMENT_ORACLE_EMPTY")
    result: dict[str, object] = {
        "payment_rows": 0,
        "payments_created": 0,
        "payments_replayed": 0,
        "unmatched_count": 0,
        "allocated_count": 0,
        "overpaid_count": 0,
        "allocation_vnd": 0,
        "credit_vnd": 0,
        "invoice_reconciled": 0,
        "ar_accounts_reconciled": 0,
        "ar_delta_vnd": 0,
        "reconciled": True,
    }
    for row in payment_rows:
        tenant, site, building, _ = _structure(session, row)
        source_reference = _required(row.get("source_reference"), "PAYMENT_SOURCE_REFERENCE_REQUIRED")
        receipt_number = _required(row.get("receipt_number"), "PAYMENT_RECEIPT_REQUIRED")
        payment_source = normalize_enum(
            row.get("payment_source"), ("CASH", "BANK_TRANSFER", "GATEWAY"),
            field="payment_source", output_case="preserve",
        )
        try:
            amount_vnd = int(Decimal(str(row.get("amount_vnd"))))
        except (TypeError, ValueError, ArithmeticError) as exc:
            raise OperationalReplayError("PAYMENT_AMOUNT_INVALID") from exc
        if amount_vnd <= 0:
            raise OperationalReplayError("PAYMENT_AMOUNT_INVALID")
        received_at = _utc(row.get("received_at"), field="received_at")
        if received_at > as_of:
            raise OperationalReplayError("REPLAY_FUTURE_TERMINAL_EVENT")
        actor = _account_by_username(
            session,
            tenant_id=tenant.id,
            site_id=site.id,
            building_id=building.id,
            username=_required(row.get("received_by_username"), "PAYMENT_ACTOR_REQUIRED"),
            role="accountant",
            error_code="PAYMENT_ACTOR_NOT_FOUND",
        )
        period_key = derive_period_key(row, invoice_rows, policy_rows)
        period = session.scalar(select(AccountingPeriod).where(
            AccountingPeriod.tenant_id == tenant.id,
            AccountingPeriod.site_id == site.id,
            AccountingPeriod.building_id == building.id,
            AccountingPeriod.period_key == period_key,
        ).with_for_update())
        if period is None:
            raise OperationalReplayError("PAYMENT_PERIOD_REFERENCE_NOT_FOUND")
        account_number = _text(row.get("billing_account_number"))
        account = None
        if account_number:
            account = session.scalar(select(BillingAccount).where(
                BillingAccount.tenant_id == tenant.id,
                BillingAccount.site_id == site.id,
                BillingAccount.building_id == building.id,
                BillingAccount.account_number == account_number,
            ).with_for_update())
            if account is None:
                raise OperationalReplayError("PAYMENT_ACCOUNT_REFERENCE_NOT_FOUND")
        target_status = normalize_enum(
            row.get("status"),
            ("ALLOCATED", "PARTIALLY_ALLOCATED", "OVERPAID", "UNMATCHED"),
            field="payment_status", output_case="preserve",
        )
        safe_payload = {
            "source_reference": source_reference,
            "receipt_number": receipt_number,
            "payment_source": payment_source,
            "amount_vnd": amount_vnd,
            "period_key": period_key,
            "target_status": target_status,
            "billing_account_number": account_number or None,
            "received_at": received_at.isoformat(),
            "received_by_username": actor.username,
            "matched_invoice_number": _text(row.get("matched_invoice_number")) or None,
            "allocated_vnd": int(Decimal(str(row.get("allocated_vnd") or 0))),
            "overpayment_vnd": int(Decimal(str(row.get("overpayment_vnd") or 0))),
            "unmatched_reason": _text(row.get("unmatched_reason")) or None,
        }
        payment = session.scalar(select(Payment).where(
            Payment.tenant_id == tenant.id,
            Payment.site_id == site.id,
            Payment.payment_source == payment_source,
            Payment.source_reference == source_reference,
        ).with_for_update())
        created = payment is None
        if created:
            payment = receive_payment_command(
                session,
                tenant_id=tenant.id,
                site_id=site.id,
                building_id=building.id,
                period=period,
                account=account,
                payment_source=payment_source,
                source_reference=source_reference,
                receipt_number=receipt_number,
                amount_vnd=amount_vnd,
                received_at=received_at,
                actor_id=actor.id,
                unmatched_reason=_text(row.get("unmatched_reason")) or "Approved source payment is unmatched.",
            )
            result["payments_created"] = int(result["payments_created"]) + 1
            _audit(
                session,
                tenant_id=tenant.id,
                site_id=site.id,
                building_id=building.id,
                actor_id=actor.id,
                correlation_id=_correlation(run, f"fcs16:payment:{source_reference}"),
                event_type="PaymentReceived" if account is not None else "PaymentUnmatched",
                action="create",
                resource_type="Payment",
                resource_id=payment.id,
                after={"amount_vnd": amount_vnd, "status": payment.status},
            )
            _emit(
                session,
                tenant_id=tenant.id,
                site_id=site.id,
                actor_id=actor.id,
                correlation_id=_correlation(run, f"fcs16:payment:{source_reference}"),
                event_type="PaymentReceived" if account is not None else "PaymentUnmatched",
                resource_type="Payment",
                resource_id=payment.id,
                payload={"amount_vnd": amount_vnd, "billing_account_present": account is not None},
            )
        else:
            result["payments_replayed"] = int(result["payments_replayed"]) + 1
            if (
                payment.receipt_number != receipt_number
                or payment.amount_vnd != amount_vnd
                or payment.accounting_period_id != period.id
                or payment.building_id != building.id
                or payment.received_at != received_at
                or payment.received_by_id != actor.id
                or (payment.billing_account_id != (account.id if account is not None else None))
            ):
                raise OperationalReplayError("PAYMENT_ORACLE_RETRY_CONFLICT")

        if target_status == "UNMATCHED":
            if account is not None or payment.status != "UNMATCHED":
                raise OperationalReplayError("PAYMENT_UNMATCHED_STATE_MISMATCH")
            result["unmatched_count"] = int(result["unmatched_count"]) + 1
        else:
            if account is None or payment.billing_account_id != account.id:
                raise OperationalReplayError("PAYMENT_ACCOUNT_REQUIRED_FOR_ALLOCATION")
            if payment.status not in {"ALLOCATED", "OVERPAID"}:
                allocations, credit = allocate_payment(session, payment, actor.id)
                _audit(
                    session,
                    tenant_id=tenant.id,
                    site_id=site.id,
                    building_id=building.id,
                    actor_id=actor.id,
                    correlation_id=_correlation(run, f"fcs16:payment:{source_reference}"),
                    event_type="PaymentAllocated",
                    action="allocate",
                    resource_type="Payment",
                    resource_id=payment.id,
                    after={"status": payment.status, "allocated_vnd": sum(item.amount_vnd for item in allocations)},
                )
                _emit(
                    session,
                    tenant_id=tenant.id,
                    site_id=site.id,
                    actor_id=actor.id,
                    correlation_id=_correlation(run, f"fcs16:payment:{source_reference}"),
                    event_type="PaymentAllocated",
                    resource_type="Payment",
                    resource_id=payment.id,
                    payload={"status": payment.status, "allocation_count": len(allocations)},
                )
            else:
                allocations = session.scalars(select(PaymentAllocation).where(
                    PaymentAllocation.payment_id == payment.id,
                ).order_by(PaymentAllocation.created_at, PaymentAllocation.id)).all()
                credit = session.scalar(select(OverpaymentCredit).where(
                    OverpaymentCredit.payment_id == payment.id,
                ))
            allocated_vnd = sum(item.amount_vnd for item in allocations)
            expected_allocated = int(Decimal(str(row.get("allocated_vnd") or 0)))
            expected_credit = int(Decimal(str(row.get("overpayment_vnd") or 0)))
            if allocated_vnd != expected_allocated:
                raise OperationalReplayError("PAYMENT_ALLOCATION_ORACLE_MISMATCH")
            actual_credit = credit.remaining_vnd if credit is not None else 0
            if actual_credit != expected_credit:
                raise OperationalReplayError("PAYMENT_CREDIT_ORACLE_MISMATCH")
            matched_invoice_number = _text(row.get("matched_invoice_number"))
            if matched_invoice_number:
                invoice = session.scalar(select(BillingInvoice).where(
                    BillingInvoice.site_id == site.id,
                    BillingInvoice.invoice_number == matched_invoice_number,
                ).with_for_update())
                if invoice is None:
                    raise OperationalReplayError("PAYMENT_INVOICE_REFERENCE_NOT_FOUND")
                if not any(item.billing_invoice_id == invoice.id for item in allocations):
                    raise OperationalReplayError("PAYMENT_INVOICE_ALLOCATION_MISMATCH")
                if target_status == "PARTIALLY_ALLOCATED" and invoice.status != "PARTIALLY_PAID":
                    raise OperationalReplayError("PAYMENT_PARTIAL_STATE_MISMATCH")
            if target_status == "OVERPAID":
                if payment.status != "OVERPAID" or actual_credit <= 0:
                    raise OperationalReplayError("PAYMENT_OVERPAID_STATE_MISMATCH")
                result["overpaid_count"] = int(result["overpaid_count"]) + 1
            elif payment.status != "ALLOCATED":
                raise OperationalReplayError("PAYMENT_ALLOCATION_STATE_MISMATCH")
            else:
                result["allocated_count"] = int(result["allocated_count"]) + 1
            result["allocation_vnd"] = int(result["allocation_vnd"]) + allocated_vnd
            result["credit_vnd"] = int(result["credit_vnd"]) + actual_credit
        _record_idempotency(
            session,
            tenant_id=tenant.id,
            site_id=site.id,
            actor_id=actor.id,
            operation="submission.billing.payment.replay",
            key=f"payment:{source_reference}",
            payload=safe_payload,
            resource_type="Payment",
            resource_id=payment.id,
        )
        result["payment_rows"] = int(result["payment_rows"]) + 1

    expected_invoices: dict[tuple[UUID, str], Mapping[str, object]] = {}
    for row in invoice_rows:
        _, site, _, _ = _structure(session, row)
        invoice_number = _required(row.get("invoice_number"), "PAYMENT_ORACLE_INVOICE_REQUIRED")
        key = (site.id, invoice_number)
        if key in expected_invoices:
            raise OperationalReplayError("PAYMENT_ORACLE_INVOICE_DUPLICATE")
        expected_invoices[key] = row
    expected_by_account: dict[UUID, int] = defaultdict(int)
    for (site_id, invoice_number), row in expected_invoices.items():
        invoice = session.scalar(select(BillingInvoice).where(
            BillingInvoice.site_id == site_id,
            BillingInvoice.invoice_number == invoice_number,
        ))
        if invoice is None:
            raise OperationalReplayError("PAYMENT_ORACLE_INVOICE_NOT_FOUND")
        expected_status = _text(row.get("invoice_status"))
        expected_outstanding = int(Decimal(str(row.get("outstanding_vnd"))))
        if invoice.status != expected_status or invoice.outstanding_vnd != expected_outstanding:
            raise OperationalReplayError("PAYMENT_INVOICE_RECONCILIATION_MISMATCH")
        expected_by_account[invoice.billing_account_id] += expected_outstanding
        result["invoice_reconciled"] = int(result["invoice_reconciled"]) + 1
    for account_id, expected_balance in expected_by_account.items():
        actual_balance = session.scalar(select(func.coalesce(
            func.sum(ArLedgerEntry.debit_vnd - ArLedgerEntry.credit_vnd), 0,
        )).where(ArLedgerEntry.billing_account_id == account_id)) or 0
        delta = int(actual_balance) - expected_balance
        if delta != 0:
            raise OperationalReplayError("PAYMENT_AR_RECONCILIATION_MISMATCH")
        result["ar_accounts_reconciled"] = int(result["ar_accounts_reconciled"]) + 1
    result["reconciled"] = True
    return result


__all__ = [
    "OperationalReplayError",
    "replay_maintenance_cleaning",
    "replay_security_parcels",
    "replay_billing_run",
    "replay_payment_allocations",
]
