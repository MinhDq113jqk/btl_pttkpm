"""State-machine replay helpers for the approved submission pack.

The XLSX files describe facts and desired end states.  This module turns those
facts into the same persisted transitions used by the Service Request and Work
Order domain, while keeping the import-run transaction and correlation id
around every mutation.  It intentionally refuses to invent evidence for a
closed work order; supplied evidence is validated and written to the configured
private storage before the attachment row is committed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Callable, Mapping
from uuid import UUID, uuid5

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.account import Account, AccountRole
from app.models.building import Building
from app.models.platform import Attachment, AuditEvent, DomainEvent, IdempotencyRecord
from app.models.service import CostLine, ServiceCategory, ServiceRequest, WorkOrder, WorkOrderChecklistItem
from app.models.site import Site
from app.models.submission_import import SubmissionExternalReference
from app.models.tenant import Tenant
from app.models.unit import Unit
from app.services.private_storage import verified_private_path, write_private_bytes
from app.services.r2 import ImageEvidenceError, validate_image_evidence
from app.services.submission_data_import import SubmissionImportError, canonical_payload_sha256, upsert_external_reference
from app.services.submission_data_mapping import require_resolved
from app.services.submission_data_normalization import normalize_enum, normalize_temporal


class SubmissionReplayError(SubmissionImportError):
    """A source row cannot be replayed without violating a domain invariant."""


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _required(value: object, code: str) -> str:
    result = _text(value)
    if not result:
        raise SubmissionReplayError(code)
    return result


def _utc(value: object, *, field: str) -> datetime:
    return normalize_temporal(value, field=field, as_of_utc=datetime.max.replace(tzinfo=UTC)).utc


def _scope_account(
    session: Session,
    tenant_id: UUID,
    username: str,
    *,
    site_id: UUID,
    building_id: UUID,
    roles: tuple[str, ...],
    error_code: str,
) -> Account:
    account = session.scalar(select(Account).where(
        Account.tenant_id == tenant_id, Account.username == username,
    ))
    if account is None or not account.is_active:
        raise SubmissionReplayError(error_code)
    grants = session.scalars(select(AccountRole).where(
        AccountRole.account_id == account.id, AccountRole.role.in_(roles),
    )).all()
    if not any(
        grant.site_id == site_id
        and (grant.building_id is None or grant.building_id == building_id)
        for grant in grants
    ):
        raise SubmissionReplayError(error_code)
    return account


def _unique_role_account(
    session: Session,
    tenant_id: UUID,
    *,
    site_id: UUID,
    building_id: UUID,
    role: str,
    error_code: str,
) -> Account:
    rows = session.scalars(select(Account).join(AccountRole).where(
        Account.tenant_id == tenant_id,
        Account.is_active.is_(True),
        AccountRole.site_id == site_id,
        or_(AccountRole.building_id == building_id, AccountRole.building_id.is_(None)),
        AccountRole.role == role,
    ).distinct().order_by(Account.id)).all()
    if len(rows) != 1:
        raise SubmissionReplayError(error_code)
    return rows[0]


def _audit(
    session: Session,
    *,
    tenant_id: UUID,
    site_id: UUID,
    building_id: UUID,
    actor_id: UUID,
    correlation_id: UUID,
    event_type: str,
    action: str,
    resource_type: str,
    resource_id: UUID,
    before: dict | None = None,
    after: dict | None = None,
    reason: str | None = None,
) -> None:
    session.add(AuditEvent(
        tenant_id=tenant_id, site_id=site_id, building_id=building_id,
        actor_account_id=actor_id, event_type=event_type, action=action,
        resource_type=resource_type, resource_id=resource_id,
        before_data=before, after_data=after, reason=reason,
        correlation_id=correlation_id,
    ))


def _emit(
    session: Session,
    *,
    tenant_id: UUID,
    site_id: UUID,
    actor_id: UUID,
    correlation_id: UUID,
    event_type: str,
    resource_type: str,
    resource_id: UUID,
    payload: dict | None = None,
) -> None:
    session.add(DomainEvent(
        tenant_id=tenant_id, site_id=site_id, actor_account_id=actor_id,
        event_type=event_type, resource_type=resource_type,
        resource_id=resource_id, correlation_id=correlation_id,
        payload=payload or {},
    ))


def _idempotency_hash(payload: Mapping[str, object]) -> str:
    return canonical_payload_sha256(payload)


def _validate_submission_evidence(content: bytes) -> tuple[str, str]:
    """Validate approved-pack evidence and return its MIME type and suffix."""

    for claimed_mime, suffix in (("image/png", "png"), ("image/jpeg", "jpg")):
        try:
            return validate_image_evidence(content, claimed_mime), suffix
        except ImageEvidenceError:
            continue
    raise SubmissionReplayError("REPLAY_EVIDENCE_INVALID")


def _mark_idempotent(
    session: Session,
    *,
    tenant_id: UUID,
    site_id: UUID,
    actor_id: UUID,
    key: str,
    payload: Mapping[str, object],
    resource_type: str,
    resource_id: UUID,
) -> None:
    operation = "submission.service-request.replay"
    digest = _idempotency_hash(payload)
    existing = session.scalar(select(IdempotencyRecord).where(
        IdempotencyRecord.tenant_id == tenant_id,
        IdempotencyRecord.site_id == site_id,
        IdempotencyRecord.actor_account_id == actor_id,
        IdempotencyRecord.operation == operation,
        IdempotencyRecord.idempotency_key == key,
    ).with_for_update())
    if existing is not None:
        if existing.request_hash != digest or existing.resource_id != resource_id:
            raise SubmissionReplayError("REPLAY_IDEMPOTENCY_CONFLICT")
        return
    session.add(IdempotencyRecord(
        tenant_id=tenant_id, site_id=site_id, actor_account_id=actor_id,
        operation=operation, idempotency_key=key, request_hash=digest,
        resource_type=resource_type, resource_id=resource_id,
        response_status=200,
    ))


def _structure(
    session: Session,
    row: Mapping[str, object],
) -> tuple[Tenant, Site, Building, Unit | None]:
    tenant = session.scalar(select(Tenant).where(Tenant.code == _required(row.get("tenant_code"), "TENANT_CODE_REQUIRED")))
    if tenant is None:
        raise SubmissionReplayError("REPLAY_TENANT_NOT_FOUND")
    site = session.scalar(select(Site).where(
        Site.tenant_id == tenant.id, Site.code == _required(row.get("site_code"), "SITE_CODE_REQUIRED"),
    ))
    building = session.scalar(select(Building).where(
        Building.site_id == site.id, Building.code == _required(row.get("building_code"), "BUILDING_CODE_REQUIRED"),
    )) if site else None
    if site is None or building is None:
        raise SubmissionReplayError("REPLAY_SCOPE_NOT_FOUND")
    unit_number = _text(row.get("unit_number"))
    unit = session.scalar(select(Unit).where(
        Unit.building_id == building.id, Unit.unit_number == unit_number,
    )) if unit_number else None
    if unit_number and unit is None:
        raise SubmissionReplayError("REPLAY_UNIT_NOT_FOUND")
    return tenant, site, building, unit


def _category(session: Session, site_id: UUID, code: str) -> ServiceCategory:
    rows = session.scalars(select(ServiceCategory).where(
        ServiceCategory.site_id == site_id, ServiceCategory.code == code,
        ServiceCategory.is_active.is_(True),
    )).all()
    if len(rows) != 1:
        raise SubmissionReplayError("REPLAY_CATEGORY_NOT_UNIQUE")
    return rows[0]


def _set_checklist_complete(
    session: Session,
    work_order: WorkOrder,
    actor_id: UUID,
    correlation_id: UUID,
    completed_at: datetime,
) -> None:
    items = session.scalars(select(WorkOrderChecklistItem).where(
        WorkOrderChecklistItem.work_order_id == work_order.id,
    ).order_by(WorkOrderChecklistItem.position).with_for_update()).all()
    if not items:
        raise SubmissionReplayError("REPLAY_CHECKLIST_MISSING")
    for item in items:
        if item.is_completed:
            continue
        before = {"is_completed": item.is_completed, "result": item.result}
        item.is_completed = True
        item.result = item.result or "Imported source completion"
        item.completed_by_id = actor_id
        item.completed_at = completed_at
        item.version += 1
        _audit(
            session, tenant_id=work_order.tenant_id, site_id=work_order.site_id,
            building_id=work_order.building_id, actor_id=actor_id,
            correlation_id=correlation_id, event_type="WorkOrderChecklistUpdated",
            action="checklist-update", resource_type="WorkOrderChecklistItem",
            resource_id=item.id, before=before,
            after={"is_completed": True, "result": item.result},
        )


def replay_service_requests(
    session: Session,
    rows: list[Mapping[str, object]],
    run,
    *,
    as_of_utc: datetime,
    evidence_provider: Callable[[str], bytes | None] | None = None,
    evidence_storage_root: Path | None = None,
    written_evidence_paths: list[Path] | None = None,
) -> dict[str, int]:
    """Replay file 01 rows through legal Service Request/Work Order states.

    Rows that end in ``CLOSED`` require a real image supplied by the approved
    evidence pack.  The loader never fabricates an attachment to make a source
    terminal state pass.
    """

    if as_of_utc.tzinfo is None:
        raise SubmissionReplayError("REPLAY_AS_OF_NOT_TIMEZONE_AWARE")
    require_resolved("FCS05-WORK-ORDER-SOURCE")
    require_resolved("FCS05-COST-BEARER")
    counts: dict[str, int] = {"service_requests": 0, "work_orders": 0, "cost_lines": 0, "completed": 0}
    for row in rows:
        tenant, site, building, unit = _structure(session, row)
        work_code = _required(row.get("work_code"), "WORK_CODE_REQUIRED")
        source_status = normalize_enum(
            row.get("status"), ("NEW", "IN_PROGRESS", "CLOSED"),
            field="service_request_status", output_case="preserve",
        )
        created_at = _utc(row.get("created_at"), field="created_at")
        if created_at > as_of_utc:
            raise SubmissionReplayError("FUTURE_SERVICE_REQUEST")
        completed_at = _utc(row.get("completed_at"), field="completed_at") if row.get("completed_at") is not None else None
        if source_status == "CLOSED" and (completed_at is None or completed_at > as_of_utc):
            raise SubmissionReplayError("FUTURE_TERMINAL_EVENT")
        reported_by = _scope_account(
            session, tenant.id, _required(row.get("reported_by_username"), "REPORTED_BY_REQUIRED"),
            site_id=site.id, building_id=building.id,
            roles=("cskh", "technical_lead"), error_code="REPORTED_BY_SCOPE_NOT_FOUND",
        )
        assignee = _scope_account(
            session, tenant.id, _required(row.get("assignee_username"), "ASSIGNEE_REQUIRED"),
            site_id=site.id, building_id=building.id,
            roles=("technician", "technical_lead"), error_code="ASSIGNEE_SCOPE_NOT_FOUND",
        )
        category = _category(session, site.id, _required(row.get("request_type"), "CATEGORY_CODE_REQUIRED"))
        priority = normalize_enum(row.get("priority"), ("LOW", "MEDIUM", "HIGH", "URGENT"), field="priority", output_case="preserve")
        safe_payload = {
            "work_code": work_code, "request_type": category.code,
            "site_code": site.code, "building_code": building.code,
            "unit_number": unit.unit_number if unit else None,
            "status": source_status, "priority": priority,
        }
        correlation_id = uuid5(run.correlation_id, work_code)
        request_ref_key = f"{site.code}:{work_code}"
        request_ref = session.scalar(select(SubmissionExternalReference).where(
            SubmissionExternalReference.tenant_id == tenant.id,
            SubmissionExternalReference.source == "service-request",
            SubmissionExternalReference.entity_type == "ServiceRequest",
            SubmissionExternalReference.source_key == request_ref_key,
        ).with_for_update())
        request_record = session.get(ServiceRequest, request_ref.target_id) if request_ref else session.scalar(select(ServiceRequest).where(
            ServiceRequest.site_id == site.id, ServiceRequest.code == work_code,
        ).with_for_update())
        if request_record is None:
            request_record = ServiceRequest(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                unit_id=unit.id if unit else None, category_id=category.id,
                code=work_code, title=_required(row.get("title"), "REQUEST_TITLE_REQUIRED"),
                description=_required(row.get("description"), "REQUEST_DESCRIPTION_REQUIRED"),
                priority=priority, status="NEW", sla_started_at=created_at,
                sla_duration_minutes=category.sla_minutes,
                owner_account_id=reported_by.id, created_by_id=reported_by.id,
                updated_by_id=reported_by.id,
            )
            session.add(request_record)
            session.flush()
            _audit(session, tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                   actor_id=reported_by.id, correlation_id=correlation_id,
                   event_type="ServiceRequestCreated", action="create",
                   resource_type="ServiceRequest", resource_id=request_record.id,
                   after={"status": "NEW", "source_key": work_code})
            _emit(session, tenant_id=tenant.id, site_id=site.id, actor_id=reported_by.id,
                  correlation_id=correlation_id, event_type="ServiceRequestCreated",
                  resource_type="ServiceRequest", resource_id=request_record.id,
                  payload={"source_key": work_code})
            upsert_external_reference(
                session, run, tenant_id=tenant.id, source="service-request",
                entity_type="ServiceRequest", source_key=request_ref_key,
                target_id=request_record.id, payload=safe_payload,
            )
            counts["service_requests"] += 1
        else:
            if (request_record.site_id, request_record.building_id, request_record.category_id) != (site.id, building.id, category.id):
                raise SubmissionReplayError("REPLAY_REQUEST_METADATA_CONFLICT")
            _mark_idempotent(
                session, tenant_id=tenant.id, site_id=site.id, actor_id=reported_by.id,
                key=f"sr:{work_code}", payload=safe_payload,
                resource_type="ServiceRequest", resource_id=request_record.id,
            )
        if source_status == "NEW":
            _mark_idempotent(
                session, tenant_id=tenant.id, site_id=site.id, actor_id=reported_by.id,
                key=f"sr:{work_code}", payload=safe_payload,
                resource_type="ServiceRequest", resource_id=request_record.id,
            )
            continue

        triage_actor = reported_by if any(
            grant.role == "cskh" and grant.site_id == site.id
            and (grant.building_id is None or grant.building_id == building.id)
            for grant in session.scalars(select(AccountRole).where(AccountRole.account_id == reported_by.id)).all()
        ) else _unique_role_account(
            session, tenant.id, site_id=site.id, building_id=building.id,
            role="cskh", error_code="TRIAGE_ACTOR_AMBIGUOUS",
        )
        if request_record.status == "NEW":
            request_record.status = "TRIAGED"
            request_record.priority = priority
            request_record.owner_account_id = triage_actor.id
            request_record.updated_by_id = triage_actor.id
            request_record.version += 1
            _audit(session, tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                   actor_id=triage_actor.id, correlation_id=correlation_id,
                   event_type="ServiceRequestTriaged", action="triage",
                   resource_type="ServiceRequest", resource_id=request_record.id,
                   after={"status": "TRIAGED", "source_key": work_code})
        elif request_record.status not in {"TRIAGED", "IN_PROGRESS", "RESOLVED", "CLOSED"}:
            raise SubmissionReplayError("REPLAY_REQUEST_STATE_CONFLICT")

        wo_ref_key = f"{site.code}:{work_code}"
        wo_ref = session.scalar(select(SubmissionExternalReference).where(
            SubmissionExternalReference.tenant_id == tenant.id,
            SubmissionExternalReference.source == "service-request",
            SubmissionExternalReference.entity_type == "WorkOrder",
            SubmissionExternalReference.source_key == wo_ref_key,
        ).with_for_update())
        work_order = session.get(WorkOrder, wo_ref.target_id) if wo_ref else session.scalar(select(WorkOrder).where(
            WorkOrder.site_id == site.id, WorkOrder.code == f"WO-{work_code}",
        ).with_for_update())
        if work_order is None:
            work_order = WorkOrder(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                service_request_id=request_record.id, code=f"WO-{work_code}",
                title=_required(row.get("title"), "WORK_ORDER_TITLE_REQUIRED"),
                description=_required(row.get("description"), "WORK_ORDER_DESCRIPTION_REQUIRED"),
                status="DRAFT", created_by_id=triage_actor.id, updated_by_id=triage_actor.id,
            )
            session.add(work_order)
            session.flush()
            session.add(WorkOrderChecklistItem(
                work_order_id=work_order.id, position=1,
                label="Verify source work completion", is_required=True,
            ))
            request_record.status = "IN_PROGRESS"
            request_record.updated_by_id = triage_actor.id
            request_record.version += 1
            _audit(session, tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                   actor_id=triage_actor.id, correlation_id=correlation_id,
                   event_type="WorkOrderCreated", action="create",
                   resource_type="WorkOrder", resource_id=work_order.id,
                   after={"status": "DRAFT", "source_key": work_code})
            _emit(session, tenant_id=tenant.id, site_id=site.id, actor_id=triage_actor.id,
                  correlation_id=correlation_id, event_type="WorkOrderCreated",
                  resource_type="WorkOrder", resource_id=work_order.id,
                  payload={"source_key": work_code})
            upsert_external_reference(
                session, run, tenant_id=tenant.id, source="service-request",
                entity_type="WorkOrder", source_key=wo_ref_key,
                target_id=work_order.id, payload={"work_code": work_code, "status": source_status},
            )
            counts["work_orders"] += 1
        if work_order.status == "DRAFT":
            work_order.status = "ASSIGNED"
            work_order.assigned_to_id = assignee.id
            work_order.updated_by_id = assignee.id
            work_order.version += 1
            _audit(session, tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                   actor_id=triage_actor.id, correlation_id=correlation_id,
                   event_type="WorkOrderAssigned", action="assign",
                   resource_type="WorkOrder", resource_id=work_order.id,
                   after={"status": "ASSIGNED", "assignee_present": True})
            _emit(session, tenant_id=tenant.id, site_id=site.id, actor_id=triage_actor.id,
                  correlation_id=correlation_id, event_type="WorkOrderAssigned",
                  resource_type="WorkOrder", resource_id=work_order.id,
                  payload={"assigned_to_id": str(assignee.id)})
        elif work_order.assigned_to_id != assignee.id:
            raise SubmissionReplayError("REPLAY_ASSIGNEE_CONFLICT")
        if work_order.status == "ASSIGNED":
            work_order.status = "IN_PROGRESS"
            work_order.updated_by_id = assignee.id
            work_order.version += 1
            _audit(session, tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                   actor_id=assignee.id, correlation_id=correlation_id,
                   event_type="WorkOrderStarted", action="start",
                   resource_type="WorkOrder", resource_id=work_order.id,
                   after={"status": "IN_PROGRESS"})
            _emit(session, tenant_id=tenant.id, site_id=site.id, actor_id=assignee.id,
                  correlation_id=correlation_id, event_type="WorkOrderStarted",
                  resource_type="WorkOrder", resource_id=work_order.id,
                  payload={"source_key": work_code})
        cost = row.get("cost_vnd")
        try:
            cost_vnd = int(cost)
        except (TypeError, ValueError) as exc:
            raise SubmissionReplayError("REPLAY_COST_INVALID") from exc
        if cost_vnd <= 0:
            raise SubmissionReplayError("REPLAY_COST_INVALID")
        existing_cost = session.scalar(select(CostLine).where(CostLine.work_order_id == work_order.id).with_for_update())
        if existing_cost is None:
            existing_cost = CostLine(
                work_order_id=work_order.id, description="Approved source cost",
                amount_vnd=cost_vnd, cost_bearer="MANAGEMENT", status="SUBMITTED",
                created_by_id=assignee.id, updated_by_id=assignee.id,
            )
            session.add(existing_cost)
            session.flush()
            _audit(
                session, tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                actor_id=assignee.id, correlation_id=correlation_id,
                event_type="CostLineSubmitted", action="submit",
                resource_type="CostLine", resource_id=existing_cost.id,
                after={"cost_bearer": "MANAGEMENT", "amount_vnd": cost_vnd},
            )
            _emit(
                session, tenant_id=tenant.id, site_id=site.id, actor_id=assignee.id,
                correlation_id=correlation_id, event_type="CostLineSubmitted",
                resource_type="CostLine", resource_id=existing_cost.id,
                payload={"pending_charge_id": None},
            )
            counts["cost_lines"] += 1
        elif (existing_cost.amount_vnd, existing_cost.cost_bearer) != (cost_vnd, "MANAGEMENT"):
            raise SubmissionReplayError("REPLAY_COST_CONFLICT")
        if source_status != "CLOSED":
            _mark_idempotent(
                session, tenant_id=tenant.id, site_id=site.id, actor_id=reported_by.id,
                key=f"sr:{work_code}", payload=safe_payload,
                resource_type="ServiceRequest", resource_id=request_record.id,
            )
            continue
        evidence = evidence_provider(work_code) if evidence_provider else None
        if not evidence:
            raise SubmissionReplayError("REPLAY_EVIDENCE_REQUIRED")
        if evidence_storage_root is None:
            raise SubmissionReplayError("REPLAY_EVIDENCE_STORAGE_REQUIRED")
        mime_type, suffix = _validate_submission_evidence(evidence)
        _set_checklist_complete(session, work_order, assignee.id, correlation_id, completed_at)
        digest = sha256(evidence).hexdigest()
        attachment = session.scalar(select(Attachment).where(
            Attachment.work_order_id == work_order.id, Attachment.sha256 == digest,
        ).with_for_update())
        if attachment is None:
            storage_key = (
                f"submission-replay/{tenant.id}/{site.id}/{work_order.id}/"
                f"{digest}.{suffix}"
            )
            target = write_private_bytes(evidence_storage_root, storage_key, evidence)
            if written_evidence_paths is not None:
                written_evidence_paths.append(target)
            attachment = Attachment(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                work_order_id=work_order.id, uploaded_by_id=assignee.id,
                original_name=f"submission-evidence.{suffix}", storage_key=storage_key,
                mime_type=mime_type, size_bytes=len(evidence), sha256=digest,
                is_quarantined=False,
            )
            try:
                session.add(attachment)
                session.flush()
            except Exception:
                target.unlink(missing_ok=True)
                if written_evidence_paths is not None:
                    written_evidence_paths.remove(target)
                raise
            _audit(session, tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                   actor_id=assignee.id, correlation_id=correlation_id,
                   event_type="WorkOrderEvidenceAdded", action="upload",
                   resource_type="Attachment", resource_id=attachment.id,
                   after={"sha256": digest, "size_bytes": len(evidence)})
        else:
            if (
                attachment.mime_type != mime_type
                or attachment.size_bytes != len(evidence)
                or attachment.storage_key.rsplit("/", 1)[-1] != f"{digest}.{suffix}"
            ):
                raise SubmissionReplayError("REPLAY_EVIDENCE_CONFLICT")
            if verified_private_path(
                evidence_storage_root, attachment.storage_key, digest, len(evidence),
            ) is None:
                raise SubmissionReplayError("REPLAY_EVIDENCE_STORAGE_MISSING")
        if work_order.status == "IN_PROGRESS":
            work_order.status = "WAITING_ACCEPTANCE"
            work_order.result_summary = "Completed from approved source row"
            work_order.updated_by_id = assignee.id
            work_order.version += 1
            _audit(session, tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                   actor_id=assignee.id, correlation_id=correlation_id,
                   event_type="WorkOrderSubmitted", action="submit",
                   resource_type="WorkOrder", resource_id=work_order.id,
                   after={"status": "WAITING_ACCEPTANCE"})
        acceptor = None
        if work_order.status in {"WAITING_ACCEPTANCE", "COMPLETED"}:
            acceptor = _unique_role_account(
                session, tenant.id, site_id=site.id, building_id=building.id,
                role="technical_lead", error_code="ACCEPTOR_AMBIGUOUS",
            )
        if work_order.status == "WAITING_ACCEPTANCE":
            if acceptor is None:
                raise SubmissionReplayError("ACCEPTOR_AMBIGUOUS")
            work_order.status = "COMPLETED"
            work_order.accepted_by_id = acceptor.id
            work_order.acceptance_mode = "TECHNICAL"
            work_order.acceptance_reason = "Approved source replay"
            work_order.acceptance_evidence_id = attachment.id
            work_order.completed_at = completed_at
            work_order.updated_by_id = acceptor.id
            work_order.version += 1
            request_record.status = "RESOLVED"
            request_record.resolved_at = completed_at
            request_record.updated_by_id = acceptor.id
            request_record.version += 1
            _audit(session, tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                   actor_id=acceptor.id, correlation_id=correlation_id,
                   event_type="WorkOrderCompleted", action="accept",
                   resource_type="WorkOrder", resource_id=work_order.id,
                   after={"status": "COMPLETED", "acceptance_mode": "TECHNICAL"})
            _emit(session, tenant_id=tenant.id, site_id=site.id, actor_id=acceptor.id,
                  correlation_id=correlation_id, event_type="WorkOrderCompleted",
                  resource_type="WorkOrder", resource_id=work_order.id,
                  payload={"source_key": work_code})
        if work_order.status == "COMPLETED":
            if acceptor is None:
                raise SubmissionReplayError("ACCEPTOR_AMBIGUOUS")
            work_order.status = "CLOSED"
            work_order.closed_at = completed_at or as_of_utc
            work_order.updated_by_id = acceptor.id
            work_order.version += 1
            request_record.status = "CLOSED"
            request_record.closed_at = completed_at or as_of_utc
            request_record.updated_by_id = acceptor.id
            request_record.version += 1
            _audit(session, tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                   actor_id=acceptor.id, correlation_id=correlation_id,
                   event_type="WorkOrderClosed", action="close",
                   resource_type="WorkOrder", resource_id=work_order.id,
                   after={"status": "CLOSED"})
            _audit(session, tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                   actor_id=acceptor.id, correlation_id=correlation_id,
                   event_type="ServiceRequestClosed", action="close",
                   resource_type="ServiceRequest", resource_id=request_record.id,
                   after={"status": "CLOSED"})
            counts["completed"] += 1
        _mark_idempotent(
            session, tenant_id=tenant.id, site_id=site.id, actor_id=reported_by.id,
            key=f"sr:{work_code}", payload=safe_payload,
            resource_type="ServiceRequest", resource_id=request_record.id,
        )
    return counts


__all__ = ["SubmissionReplayError", "replay_service_requests"]
