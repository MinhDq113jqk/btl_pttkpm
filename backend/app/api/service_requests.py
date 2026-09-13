import hashlib
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy import false, func, or_, select, true

from app.core.exceptions import AppError
from app.core.policy import UserContext, get_current_user_context, scope_not_found
from app.core.security import create_token, decode_token
from app.models.account import Account, AccountRole
from app.models.building import Building
from app.models.platform import Attachment, AuditEvent
from app.models.service import (
    CaseRecord,
    CostLine,
    InvoiceItem,
    PendingCharge,
    ServiceCategory,
    ServiceRequest,
    WorkOrder,
    WorkOrderChecklistItem,
)
from app.models.unit import Unit
from app.schemas.r2 import (
    AttachmentView,
    ChargeDecision,
    ChargePost,
    ChecklistItemView,
    ChecklistUpdate,
    CostLineCreate,
    CostLineView,
    PendingChargeView,
    ReasonCommand,
    ServiceRequestCreate,
    ServiceRequestListItem,
    ServiceRequestListResponse,
    ServiceRequestStatus,
    ServiceRequestView,
    SignedAttachmentLink,
    SlaRun,
    SlaRunView,
    TriageRequest,
    VersionCommand,
    WorkOrderAccept,
    WorkOrderAssign,
    WorkOrderClose,
    WorkOrderCreate,
    WorkOrderSubmit,
    WorkOrderView,
)
from app.services.r2 import (
    ImageEvidenceError,
    MAX_EVIDENCE_BYTES,
    audit,
    calculate_sla_deadline,
    complete_maintenance,
    emit,
    idempotency_replay,
    recalculate_request_state,
    remember_idempotency,
    require_version,
    reverse_posted_charges,
    scoped_service_request,
    scoped_work_order,
    utc_now,
    validate_image_evidence,
)

router = APIRouter(tags=["R2 service and work orders"])

REQUEST_SITE_WIDE_ROLES = frozenset({"admin", "director", "accountant"})
REQUEST_BUILDING_ROLES = frozenset({"cskh", "technical_lead"})
REQUEST_LIST_ROLES = REQUEST_SITE_WIDE_ROLES | REQUEST_BUILDING_ROLES | {"technician"}


def _request_view(record: ServiceRequest) -> ServiceRequestView:
    return ServiceRequestView(
        id=record.id,
        code=record.code,
        tenant_id=record.tenant_id,
        site_id=record.site_id,
        building_id=record.building_id,
        unit_id=record.unit_id,
        category_id=record.category_id,
        linked_request_id=record.linked_request_id,
        link_type=record.link_type,
        link_reason=record.link_reason,
        title=record.title,
        description=record.description,
        priority=record.priority,
        status=record.status,
        sla_started_at=record.sla_started_at,
        sla_duration_minutes=record.sla_duration_minutes,
        sla_deadline=calculate_sla_deadline(record.sla_started_at, record.sla_duration_minutes),
        sla_breached_at=record.sla_breached_at,
        owner_account_id=record.owner_account_id,
        resolved_at=record.resolved_at,
        closed_at=record.closed_at,
        csat_score=record.csat_score,
        version=record.version,
    )


def _request_list_visibility(context: UserContext):
    context.assert_role(*REQUEST_LIST_ROLES)
    conditions = []
    for grant in context.role_grants:
        if grant.role not in REQUEST_SITE_WIDE_ROLES | REQUEST_BUILDING_ROLES:
            continue
        if grant.building_id is None:
            if grant.role in REQUEST_SITE_WIDE_ROLES:
                conditions.append(true())
        else:
            conditions.append(ServiceRequest.building_id == grant.building_id)
    if "technician" in context.roles:
        conditions.append(select(WorkOrder.id).where(
            WorkOrder.service_request_id == ServiceRequest.id,
            WorkOrder.tenant_id == ServiceRequest.tenant_id,
            WorkOrder.site_id == ServiceRequest.site_id,
            WorkOrder.building_id == ServiceRequest.building_id,
            WorkOrder.assigned_to_id == context.account_id,
        ).exists())
    return or_(*conditions) if conditions else false()


def _work_order_view(session, record: WorkOrder) -> WorkOrderView:
    checklist = session.scalars(select(WorkOrderChecklistItem).where(
        WorkOrderChecklistItem.work_order_id == record.id,
    ).order_by(WorkOrderChecklistItem.position)).all()
    evidence_count = session.scalar(select(func.count(Attachment.id)).where(
        Attachment.work_order_id == record.id,
        Attachment.is_quarantined.is_(False),
        Attachment.mime_type.in_(("image/png", "image/jpeg")),
    )) or 0
    return WorkOrderView(
        id=record.id,
        code=record.code,
        tenant_id=record.tenant_id,
        site_id=record.site_id,
        building_id=record.building_id,
        service_request_id=record.service_request_id,
        maintenance_occurrence_id=record.maintenance_occurrence_id,
        title=record.title,
        description=record.description,
        status=record.status,
        assigned_to_id=record.assigned_to_id,
        acceptance_mode=record.acceptance_mode,
        acceptance_reason=record.acceptance_reason,
        acceptance_evidence_id=record.acceptance_evidence_id,
        result_summary=record.result_summary,
        completed_at=record.completed_at,
        closed_at=record.closed_at,
        version=record.version,
        checklist=[ChecklistItemView.model_validate(item) for item in checklist],
        evidence_count=evidence_count,
    )


def _assert_request_view(session, context: UserContext, record: ServiceRequest) -> None:
    if "technician" in context.roles:
        assigned = session.scalar(select(WorkOrder.id).where(
            WorkOrder.service_request_id == record.id,
            WorkOrder.assigned_to_id == context.account_id,
        ).limit(1))
        if assigned is not None:
            return
        if not set(context.roles).intersection({
            "admin", "director", "cskh", "accountant", "technical_lead",
        }):
            raise scope_not_found()
    context.assert_building_role(
        record.building_id, "admin", "director", "cskh", "accountant", "technical_lead",
    )


def _assert_work_order_view(context: UserContext, record: WorkOrder) -> None:
    if "technician" in context.roles and record.assigned_to_id == context.account_id:
        return
    if "technician" in context.roles and not set(context.roles).intersection({
        "admin", "director", "cskh", "accountant", "technical_lead",
    }):
        raise scope_not_found()
    context.assert_building_role(
        record.building_id, "admin", "director", "cskh", "accountant", "technical_lead",
    )


def _assert_technician(record: WorkOrder, context: UserContext) -> None:
    context.assert_role("technician")
    if record.assigned_to_id != context.account_id:
        raise scope_not_found()


def _load_attachment(session, context: UserContext, attachment_id: UUID, work_order_id: UUID | None = None) -> Attachment:
    statement = select(Attachment).where(
        Attachment.id == attachment_id,
        *context.scope_conditions(Attachment),
        Attachment.is_quarantined.is_(False),
    )
    if work_order_id is not None:
        statement = statement.where(Attachment.work_order_id == work_order_id)
    attachment = session.scalar(statement)
    if attachment is None:
        raise scope_not_found()
    return attachment


def _authorized_attachment(session, context: UserContext, attachment_id: UUID) -> tuple[Attachment, WorkOrder]:
    attachment = session.scalar(select(Attachment).where(
        Attachment.id == attachment_id,
        *context.scope_conditions(Attachment),
    ))
    if attachment is None:
        raise scope_not_found()
    work_order = scoped_work_order(session, context, attachment.work_order_id)
    _assert_work_order_view(context, work_order)
    if attachment.is_quarantined:
        raise AppError("ERR-FILE-QUARANTINED", "Tệp không an toàn và đã bị chặn.", 423)
    return attachment, work_order


def _assert_signed_attachment_token(
    request: Request,
    token: str,
    attachment: Attachment,
    work_order: WorkOrder,
    context: UserContext,
) -> None:
    claims = decode_token(
        token,
        request.app.state.settings.auth_secret(),
        expired_code="ERR-LINK-EXPIRED",
        expired_message="Liên kết đã hết hạn. Tải lại trang.",
        expired_status=410,
    )
    expected = {
        "purpose": "attachment-download",
        "sub": str(context.account_id),
        "tenant_id": str(context.tenant_id),
        "active_site_id": str(context.assert_active_site()),
        "building_id": str(work_order.building_id),
        "attachment_id": str(attachment.id),
    }
    if any(claims.get(key) != value for key, value in expected.items()):
        raise scope_not_found()


@router.get("/service-requests", response_model=ServiceRequestListResponse)
def list_service_requests(
    request: Request,
    status: ServiceRequestStatus | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: UserContext = Depends(get_current_user_context),
):
    visibility = _request_list_visibility(current_user)
    conditions = [*current_user.scope_conditions(ServiceRequest), visibility]
    if status is not None:
        conditions.append(ServiceRequest.status == status)

    with request.app.state.database.get_session() as session:
        total = session.scalar(select(func.count(ServiceRequest.id)).where(*conditions)) or 0
        rows = session.execute(
            select(ServiceRequest, Building, Unit)
            .join(Building, (Building.id == ServiceRequest.building_id)
                  & (Building.site_id == ServiceRequest.site_id))
            .outerjoin(Unit, (Unit.id == ServiceRequest.unit_id)
                       & (Unit.building_id == ServiceRequest.building_id))
            .where(*conditions)
            .order_by(ServiceRequest.created_at.desc(), ServiceRequest.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()

        return ServiceRequestListResponse(
            items=[ServiceRequestListItem(
                id=record.id,
                code=record.code,
                title=record.title,
                unit_id=record.unit_id,
                unit_number=unit.unit_number if unit is not None else None,
                building_id=record.building_id,
                building_code=building.code,
                building_name=building.name,
                status=record.status,
                priority=record.priority,
                sla_deadline=calculate_sla_deadline(
                    record.sla_started_at, record.sla_duration_minutes,
                ),
                created_at=record.created_at,
            ) for record, building, unit in rows],
            page=page,
            page_size=page_size,
            total=total,
        )


@router.post("/service-requests", response_model=ServiceRequestView, status_code=201)
def create_service_request(
    request: Request,
    body: ServiceRequestCreate,
    current_user: UserContext = Depends(get_current_user_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    current_user.assert_building_role(body.building_id, "cskh")
    payload = body.model_dump(mode="json")
    with request.app.state.database.get_session() as session:
        replay = idempotency_replay(session, current_user, operation="service-request.create",
                                    key=idempotency_key, payload=payload)
        if replay:
            return _request_view(scoped_service_request(session, current_user, replay.resource_id))
        category = session.scalar(select(ServiceCategory).where(
            ServiceCategory.id == body.category_id,
            *current_user.scope_conditions(ServiceCategory),
            ServiceCategory.is_active.is_(True),
            (ServiceCategory.building_id.is_(None) | (ServiceCategory.building_id == body.building_id)),
        ))
        if category is None:
            raise scope_not_found()
        if body.unit_id is not None and session.scalar(select(Unit.id).where(
            Unit.id == body.unit_id, Unit.building_id == body.building_id,
        )) is None:
            raise scope_not_found()
        if body.linked_request_id is not None:
            linked = scoped_service_request(session, current_user, body.linked_request_id)
            if linked.building_id != body.building_id:
                raise scope_not_found()
        now = utc_now()
        record = ServiceRequest(
            tenant_id=current_user.tenant_id,
            site_id=current_user.assert_active_site(),
            building_id=body.building_id,
            unit_id=body.unit_id,
            category_id=category.id,
            linked_request_id=body.linked_request_id,
            link_type=body.link_type,
            link_reason=body.link_reason,
            code=f"SR-{uuid4().hex[:12].upper()}",
            title=body.title.strip(),
            description=body.description.strip(),
            priority=body.priority,
            status="NEW",
            sla_started_at=now,
            sla_duration_minutes=category.sla_minutes,
            owner_account_id=current_user.account_id,
            created_by_id=current_user.account_id,
            updated_by_id=current_user.account_id,
        )
        session.add(record)
        session.flush()
        audit(session, current_user, request, event_type="ServiceRequestCreated", action="create",
              resource_type="ServiceRequest", resource_id=record.id, building_id=record.building_id,
              after={"status": record.status, "priority": record.priority})
        emit(session, current_user, request, event_type="ServiceRequestCreated",
             resource_type="ServiceRequest", resource_id=record.id,
             payload={"code": record.code})
        remember_idempotency(session, current_user, operation="service-request.create",
                             key=idempotency_key, payload=payload,
                             resource_type="ServiceRequest", resource_id=record.id, response_status=201)
        session.commit()
        return _request_view(record)


@router.get("/service-requests/{request_id}", response_model=ServiceRequestView)
def get_service_request(request: Request, request_id: UUID,
                        current_user: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        record = scoped_service_request(session, current_user, request_id)
        _assert_request_view(session, current_user, record)
        return _request_view(record)


@router.post("/service-requests/{request_id}/triage", response_model=ServiceRequestView)
def triage_service_request(request: Request, request_id: UUID, body: TriageRequest,
                           current_user: UserContext = Depends(get_current_user_context)):
    current_user.assert_role("cskh")
    with request.app.state.database.get_session() as session:
        record = scoped_service_request(session, current_user, request_id, lock=True)
        current_user.assert_building_role(record.building_id, "cskh")
        require_version(record.version, body.expected_version)
        if record.status not in {"NEW", "TRIAGED"}:
            raise AppError("ERR-STATE-TRANSITION", "Yêu cầu không còn ở trạng thái có thể phân loại.", 409)
        owner = session.scalar(select(Account).join(AccountRole).where(
            Account.id == body.owner_account_id,
            Account.tenant_id == current_user.tenant_id,
            Account.is_active.is_(True),
            AccountRole.site_id == current_user.assert_active_site(),
            AccountRole.role.in_(("cskh", "technical_lead")),
            AccountRole.building_id == record.building_id,
        ))
        if owner is None:
            raise scope_not_found()
        before = {"status": record.status, "priority": record.priority, "owner_account_id": str(record.owner_account_id)}
        record.status = "TRIAGED"
        record.priority = body.priority
        record.owner_account_id = owner.id
        record.updated_by_id = current_user.account_id
        record.version += 1
        audit(session, current_user, request, event_type="ServiceRequestTriaged", action="triage",
              resource_type="ServiceRequest", resource_id=record.id, building_id=record.building_id,
              before=before, after={"status": record.status, "priority": record.priority,
                                    "owner_account_id": str(record.owner_account_id)})
        session.commit()
        return _request_view(record)


@router.post("/service-requests/{request_id}/work-orders", response_model=WorkOrderView, status_code=201)
def create_work_order(
    request: Request,
    request_id: UUID,
    body: WorkOrderCreate,
    current_user: UserContext = Depends(get_current_user_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    current_user.assert_role("cskh", "technical_lead")
    payload = body.model_dump(mode="json") | {"service_request_id": str(request_id)}
    with request.app.state.database.get_session() as session:
        replay = idempotency_replay(session, current_user, operation="work-order.create",
                                    key=idempotency_key, payload=payload)
        if replay:
            record = scoped_work_order(session, current_user, replay.resource_id)
            _assert_work_order_view(current_user, record)
            return _work_order_view(session, record)
        service_request = scoped_service_request(session, current_user, request_id, lock=True)
        current_user.assert_building_role(service_request.building_id, "cskh", "technical_lead")
        if service_request.status in {"RESOLVED", "CLOSED", "CANCELLED"}:
            raise AppError("ERR-STATE-TRANSITION", "Yêu cầu phải được mở lại trước khi tạo công việc.", 409)
        record = WorkOrder(
            tenant_id=service_request.tenant_id,
            site_id=service_request.site_id,
            building_id=service_request.building_id,
            service_request_id=service_request.id,
            code=f"WO-{uuid4().hex[:12].upper()}",
            title=body.title.strip(),
            description=body.description.strip(),
            status="DRAFT",
            created_by_id=current_user.account_id,
            updated_by_id=current_user.account_id,
        )
        session.add(record)
        session.flush()
        session.add_all(WorkOrderChecklistItem(
            work_order_id=record.id,
            position=position,
            label=item.label.strip(),
            is_required=item.required,
        ) for position, item in enumerate(body.checklist, 1))
        service_request.status = "IN_PROGRESS"
        service_request.updated_by_id = current_user.account_id
        service_request.version += 1
        audit(session, current_user, request, event_type="WorkOrderCreated", action="create",
              resource_type="WorkOrder", resource_id=record.id, building_id=record.building_id,
              after={"status": record.status, "service_request_id": str(service_request.id)})
        remember_idempotency(session, current_user, operation="work-order.create",
                             key=idempotency_key, payload=payload,
                             resource_type="WorkOrder", resource_id=record.id, response_status=201)
        session.commit()
        return _work_order_view(session, record)


@router.get("/work-orders/{work_order_id}", response_model=WorkOrderView)
def get_work_order(request: Request, work_order_id: UUID,
                   current_user: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        record = scoped_work_order(session, current_user, work_order_id)
        _assert_work_order_view(current_user, record)
        return _work_order_view(session, record)


@router.post("/work-orders/{work_order_id}/assign", response_model=WorkOrderView)
def assign_work_order(request: Request, work_order_id: UUID, body: WorkOrderAssign,
                      current_user: UserContext = Depends(get_current_user_context)):
    current_user.assert_role("technical_lead")
    with request.app.state.database.get_session() as session:
        record = scoped_work_order(session, current_user, work_order_id, lock=True)
        current_user.assert_building_role(record.building_id, "technical_lead")
        require_version(record.version, body.expected_version)
        if record.status not in {"DRAFT", "ASSIGNED"}:
            raise AppError("ERR-STATE-TRANSITION", "Công việc không thể phân công ở trạng thái hiện tại.", 409)
        assignee = session.scalar(select(Account).join(AccountRole).where(
            Account.id == body.assignee_id,
            Account.tenant_id == current_user.tenant_id,
            Account.is_active.is_(True),
            AccountRole.site_id == current_user.assert_active_site(),
            AccountRole.role == "technician",
        ))
        if assignee is None:
            raise scope_not_found()
        before = {"status": record.status, "assigned_to_id": str(record.assigned_to_id) if record.assigned_to_id else None}
        record.status = "ASSIGNED"
        record.assigned_to_id = assignee.id
        record.updated_by_id = current_user.account_id
        record.version += 1
        audit(session, current_user, request, event_type="WorkOrderAssigned", action="assign",
              resource_type="WorkOrder", resource_id=record.id, building_id=record.building_id,
              before=before, after={"status": record.status, "assigned_to_id": str(assignee.id)})
        emit(session, current_user, request, event_type="WorkOrderAssigned",
             resource_type="WorkOrder", resource_id=record.id,
             payload={"assigned_to_id": str(assignee.id)})
        session.commit()
        return _work_order_view(session, record)


@router.post("/work-orders/{work_order_id}/start", response_model=WorkOrderView)
def start_work_order(request: Request, work_order_id: UUID, body: VersionCommand,
                     current_user: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        record = scoped_work_order(session, current_user, work_order_id, lock=True)
        _assert_technician(record, current_user)
        require_version(record.version, body.expected_version)
        if record.status not in {"ASSIGNED", "ON_HOLD"}:
            raise AppError("ERR-STATE-TRANSITION", "Công việc chưa sẵn sàng để bắt đầu.", 409)
        record.status = "IN_PROGRESS"
        record.updated_by_id = current_user.account_id
        record.version += 1
        if record.maintenance_occurrence_id:
            from app.models.maintenance import MaintenanceOccurrence
            occurrence = session.get(MaintenanceOccurrence, record.maintenance_occurrence_id)
            occurrence.status = "IN_PROGRESS"
            occurrence.updated_by_id = current_user.account_id
            occurrence.version += 1
        audit(session, current_user, request, event_type="WorkOrderStarted", action="start",
              resource_type="WorkOrder", resource_id=record.id, building_id=record.building_id,
              after={"status": record.status})
        session.commit()
        return _work_order_view(session, record)


@router.patch("/work-orders/{work_order_id}/checklist/{item_id}", response_model=ChecklistItemView)
def update_checklist_item(request: Request, work_order_id: UUID, item_id: UUID,
                          body: ChecklistUpdate,
                          current_user: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        record = scoped_work_order(session, current_user, work_order_id, lock=True)
        _assert_technician(record, current_user)
        if record.status != "IN_PROGRESS":
            raise AppError("ERR-STATE-TRANSITION", "Checklist chỉ cập nhật khi công việc đang thực hiện.", 409)
        item = session.scalar(select(WorkOrderChecklistItem).where(
            WorkOrderChecklistItem.id == item_id,
            WorkOrderChecklistItem.work_order_id == record.id,
        ).with_for_update())
        if item is None:
            raise scope_not_found()
        require_version(item.version, body.expected_version)
        before_item = {"is_completed": item.is_completed, "result": item.result}
        item.is_completed = body.is_completed
        item.result = body.result.strip() if body.result else None
        item.completed_by_id = current_user.account_id if body.is_completed else None
        item.completed_at = utc_now() if body.is_completed else None
        item.version += 1
        record.updated_by_id = current_user.account_id
        record.version += 1
        audit(session, current_user, request, event_type="WorkOrderChecklistUpdated",
              action="checklist-update", resource_type="WorkOrderChecklistItem",
              resource_id=item.id, building_id=record.building_id,
              before=before_item,
              after={"is_completed": item.is_completed, "result": item.result})
        session.commit()
        return ChecklistItemView.model_validate(item)


@router.post("/work-orders/{work_order_id}/evidence", response_model=AttachmentView, status_code=201)
async def upload_work_order_evidence(
    request: Request,
    work_order_id: UUID,
    current_user: UserContext = Depends(get_current_user_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    file_name: str | None = Header(None, alias="X-File-Name"),
):
    # Authorize the target before spending work on untrusted file content.
    with request.app.state.database.get_session() as session:
        record = scoped_work_order(session, current_user, work_order_id)
        _assert_technician(record, current_user)
        if record.status != "IN_PROGRESS":
            raise AppError("ERR-STATE-TRANSITION", "Chỉ tải bằng chứng khi công việc đang thực hiện.", 409)

    buffered = bytearray()
    async for chunk in request.stream():
        if len(buffered) + len(chunk) > MAX_EVIDENCE_BYTES:
            raise AppError("ERR-FILE-REJECTED", "Ảnh không đúng loại, nội dung hoặc giới hạn kích thước.", 422)
        buffered.extend(chunk)
    content = bytes(buffered)
    claimed_mime = (request.headers.get("content-type") or "").split(";", 1)[0].lower()
    safe_name = Path(file_name or "evidence").name
    rejection_reason = None
    if safe_name != (file_name or "evidence") or safe_name in {"", ".", ".."}:
        safe_name = "rejected-evidence.bin"
        rejection_reason = "unsafe-file-name"
    try:
        detected_mime = validate_image_evidence(content, claimed_mime)
    except ImageEvidenceError:
        detected_mime = None
        rejection_reason = rejection_reason or "content-or-mime-not-allowed"
    digest = hashlib.sha256(content).hexdigest()
    payload = {
        "work_order_id": str(work_order_id),
        "sha256": digest,
        "mime_type": detected_mime or claimed_mime,
    }
    with request.app.state.database.get_session() as session:
        replay = idempotency_replay(session, current_user, operation="work-order.evidence",
                                    key=idempotency_key, payload=payload)
        if replay:
            if replay.response_status == 422:
                raise AppError("ERR-FILE-QUARANTINED", "Tệp không an toàn và đã bị chặn.", 422)
            return AttachmentView.model_validate(_load_attachment(session, current_user, replay.resource_id))
        record = scoped_work_order(session, current_user, work_order_id, lock=True)
        _assert_technician(record, current_user)
        if record.status != "IN_PROGRESS":
            raise AppError("ERR-STATE-TRANSITION", "Chỉ tải bằng chứng khi công việc đang thực hiện.", 409)
        is_quarantined = rejection_reason is not None
        if is_quarantined:
            storage_key = f"quarantine/{record.tenant_id}/{record.site_id}/{uuid4().hex}.bin"
            stored_mime = "application/octet-stream"
        else:
            extension = ".png" if detected_mime == "image/png" else ".jpg"
            storage_key = f"{record.tenant_id}/{record.site_id}/{uuid4().hex}{extension}"
            stored_mime = detected_mime
        root = request.app.state.settings.private_storage_path.resolve()
        target = (root / storage_key).resolve()
        if root not in target.parents:
            raise AppError("ERR-FILE-REJECTED", "Không thể lưu tệp.", 422)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        try:
            attachment = Attachment(
                tenant_id=record.tenant_id,
                site_id=record.site_id,
                building_id=record.building_id,
                work_order_id=record.id,
                uploaded_by_id=current_user.account_id,
                original_name=safe_name,
                storage_key=storage_key,
                mime_type=stored_mime,
                size_bytes=len(content),
                sha256=digest,
                is_quarantined=is_quarantined,
            )
            session.add(attachment)
            session.flush()
            event_type = "AttachmentQuarantined" if is_quarantined else "WorkOrderEvidenceAdded"
            audit(session, current_user, request, event_type=event_type,
                  action="quarantine" if is_quarantined else "upload",
                  resource_type="Attachment", resource_id=attachment.id,
                  building_id=record.building_id,
                  after={
                      "mime_type": attachment.mime_type,
                      "size_bytes": attachment.size_bytes,
                      "sha256": attachment.sha256,
                      "quarantine_reason": rejection_reason,
                  })
            if is_quarantined:
                emit(session, current_user, request, event_type="AttachmentQuarantined",
                     resource_type="Attachment", resource_id=attachment.id,
                     payload={"reason": rejection_reason, "work_order_id": str(record.id)})
            remember_idempotency(session, current_user, operation="work-order.evidence",
                                 key=idempotency_key, payload=payload,
                                 resource_type="Attachment", resource_id=attachment.id,
                                 response_status=422 if is_quarantined else 201)
            session.commit()
        except Exception:
            target.unlink(missing_ok=True)
            raise
        if is_quarantined:
            raise AppError("ERR-FILE-QUARANTINED", "Tệp không an toàn và đã bị chặn.", 422)
        return AttachmentView.model_validate(attachment)


@router.get("/attachments/{attachment_id}/signed-link", response_model=SignedAttachmentLink)
def create_attachment_signed_link(
    request: Request,
    attachment_id: UUID,
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        attachment, work_order = _authorized_attachment(session, current_user, attachment_id)
        ttl = request.app.state.settings.attachment_link_ttl_seconds
        token = create_token({
            "sub": str(current_user.account_id),
            "active_site_id": str(current_user.assert_active_site()),
            "purpose": "attachment-download",
            "attachment_id": str(attachment.id),
            "tenant_id": str(current_user.tenant_id),
            "building_id": str(work_order.building_id),
        }, request.app.state.settings.auth_secret(), expires_in_seconds=ttl)
        expires_at = utc_now() + timedelta(seconds=ttl)
        audit(session, current_user, request, event_type="AttachmentSignedLinkIssued",
              action="signed-link", resource_type="Attachment", resource_id=attachment.id,
              building_id=work_order.building_id,
              after={"expires_at": expires_at.isoformat()})
        session.commit()
        return SignedAttachmentLink(
            url=f"/api/v1/attachments/{attachment.id}/content?signed_token={token}",
            expires_at=expires_at,
        )


@router.get("/attachments/{attachment_id}/content")
def download_attachment(
    request: Request,
    attachment_id: UUID,
    signed_token: str = Query(..., min_length=1, max_length=16384),
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        attachment, work_order = _authorized_attachment(session, current_user, attachment_id)
        _assert_signed_attachment_token(
            request, signed_token, attachment, work_order, current_user,
        )
        target = (request.app.state.settings.private_storage_path.resolve() / attachment.storage_key).resolve()
        if not target.is_file() or request.app.state.settings.private_storage_path.resolve() not in target.parents:
            raise scope_not_found()
        audit(session, current_user, request, event_type="AttachmentDownloaded", action="download",
              resource_type="Attachment", resource_id=attachment.id,
              building_id=work_order.building_id)
        session.commit()
        return FileResponse(target, media_type=attachment.mime_type,
                            filename=attachment.original_name,
                            headers={"Cache-Control": "private, no-store"})


@router.post("/work-orders/{work_order_id}/cost-lines", response_model=CostLineView, status_code=201)
def create_cost_line(
    request: Request,
    work_order_id: UUID,
    body: CostLineCreate,
    current_user: UserContext = Depends(get_current_user_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    payload = body.model_dump(mode="json") | {"work_order_id": str(work_order_id)}
    with request.app.state.database.get_session() as session:
        replay = idempotency_replay(session, current_user, operation="cost-line.create",
                                    key=idempotency_key, payload=payload)
        if replay:
            line = session.get(CostLine, replay.resource_id)
            charge_id = session.scalar(select(PendingCharge.id).where(PendingCharge.cost_line_id == line.id))
            return CostLineView.model_validate(line).model_copy(update={"pending_charge_id": charge_id})
        record = scoped_work_order(session, current_user, work_order_id)
        if "technician" in current_user.roles and record.assigned_to_id == current_user.account_id:
            pass
        else:
            current_user.assert_building_role(record.building_id, "technical_lead")
        if record.status not in {"IN_PROGRESS", "WAITING_ACCEPTANCE"}:
            raise AppError("ERR-STATE-TRANSITION", "Chi phí chỉ ghi nhận khi công việc đang thực hiện.", 409)
        if body.cost_bearer == "RESIDENT":
            if body.evidence_attachment_id is None:
                raise AppError("ERR-CHECKLIST-INCOMPLETE", "Chi phí cư dân cần bằng chứng.", 422)
            _load_attachment(session, current_user, body.evidence_attachment_id, record.id)
        line = CostLine(
            work_order_id=record.id,
            description=body.description.strip(),
            amount_vnd=body.amount_vnd,
            cost_bearer=body.cost_bearer,
            status="SUBMITTED",
            evidence_attachment_id=body.evidence_attachment_id,
            created_by_id=current_user.account_id,
            updated_by_id=current_user.account_id,
        )
        session.add(line)
        session.flush()
        charge = None
        if line.cost_bearer == "RESIDENT":
            charge = PendingCharge(cost_line_id=line.id, status="SUBMITTED",
                                    submitted_by_id=current_user.account_id)
            session.add(charge)
            session.flush()
        audit(session, current_user, request, event_type="CostLineSubmitted", action="submit",
              resource_type="CostLine", resource_id=line.id, building_id=record.building_id,
              after={"cost_bearer": line.cost_bearer, "amount_vnd": line.amount_vnd})
        emit(session, current_user, request, event_type="CostLineSubmitted",
             resource_type="CostLine", resource_id=line.id,
             payload={"pending_charge_id": str(charge.id) if charge else None})
        remember_idempotency(session, current_user, operation="cost-line.create",
                             key=idempotency_key, payload=payload,
                             resource_type="CostLine", resource_id=line.id, response_status=201)
        session.commit()
        return CostLineView.model_validate(line).model_copy(
            update={"pending_charge_id": charge.id if charge else None},
        )


def _scoped_charge(session, context: UserContext, charge_id: UUID, *, lock: bool = False):
    statement = select(PendingCharge, CostLine, WorkOrder).join(
        CostLine, PendingCharge.cost_line_id == CostLine.id,
    ).join(WorkOrder, CostLine.work_order_id == WorkOrder.id).where(
        PendingCharge.id == charge_id,
        *context.scope_conditions(WorkOrder),
    )
    if lock:
        statement = statement.with_for_update()
    result = session.execute(statement).one_or_none()
    if result is None:
        raise scope_not_found()
    return result


@router.post("/pending-charges/{charge_id}/decision", response_model=PendingChargeView)
def decide_pending_charge(request: Request, charge_id: UUID, body: ChargeDecision,
                          current_user: UserContext = Depends(get_current_user_context)):
    current_user.assert_role("accountant")
    with request.app.state.database.get_session() as session:
        charge, _, work_order = _scoped_charge(session, current_user, charge_id, lock=True)
        current_user.assert_building_role(work_order.building_id, "accountant")
        require_version(charge.version, body.expected_version)
        if charge.submitted_by_id == current_user.account_id:
            audit(session, current_user, request, event_type="PermissionDenied", action="approve",
                  resource_type="PendingCharge", resource_id=charge.id,
                  building_id=work_order.building_id, before={"status": charge.status},
                  reason="self-approval blocked")
            session.commit()
            raise AppError("ERR-SOD-SELF-APPROVE", "Người tạo không thể tự duyệt.", 403)
        if charge.status != "SUBMITTED":
            raise AppError("ERR-STATE-TRANSITION", "Khoản phí không ở trạng thái chờ duyệt.", 409)
        before = {"status": charge.status}
        charge.status = "APPROVED" if body.decision == "APPROVE" else "REJECTED"
        charge.reviewed_by_id = current_user.account_id
        charge.reviewed_at = utc_now()
        charge.review_reason = body.reason.strip() if body.reason else None
        charge.version += 1
        audit(session, current_user, request,
              event_type="PendingChargeApproved" if charge.status == "APPROVED" else "PendingChargeRejected",
              action=body.decision.lower(), resource_type="PendingCharge", resource_id=charge.id,
              building_id=work_order.building_id, before=before, after={"status": charge.status},
              reason=charge.review_reason)
        emit(session, current_user, request,
             event_type="PendingChargeApproved" if charge.status == "APPROVED" else "PendingChargeRejected",
             resource_type="PendingCharge", resource_id=charge.id, payload={"status": charge.status})
        session.commit()
        return PendingChargeView.model_validate(charge)


@router.post("/pending-charges/{charge_id}/post", response_model=PendingChargeView)
def post_pending_charge(request: Request, charge_id: UUID, body: ChargePost,
                        current_user: UserContext = Depends(get_current_user_context),
                        idempotency_key: str = Header(..., alias="Idempotency-Key")):
    current_user.assert_role("accountant")
    payload = body.model_dump(mode="json") | {"charge_id": str(charge_id)}
    with request.app.state.database.get_session() as session:
        replay = idempotency_replay(session, current_user, operation="pending-charge.post",
                                    key=idempotency_key, payload=payload)
        if replay:
            charge, _, _ = _scoped_charge(session, current_user, replay.resource_id)
            return PendingChargeView.model_validate(charge)
        charge, line, work_order = _scoped_charge(session, current_user, charge_id, lock=True)
        current_user.assert_building_role(work_order.building_id, "accountant")
        require_version(charge.version, body.expected_version)
        if charge.status != "APPROVED":
            raise AppError("ERR-STATE-TRANSITION", "Chỉ khoản đã duyệt mới được ghi nhận posting.", 409)
        session.add(InvoiceItem(
            tenant_id=work_order.tenant_id,
            site_id=work_order.site_id,
            pending_charge_id=charge.id,
            posting_reference=body.posting_reference.strip(),
            amount_vnd=line.amount_vnd,
            created_by_id=current_user.account_id,
        ))
        charge.status = "POSTED"
        charge.posted_at = utc_now()
        charge.version += 1
        audit(session, current_user, request, event_type="PendingChargePosted", action="post-anchor",
              resource_type="PendingCharge", resource_id=charge.id, building_id=work_order.building_id,
              before={"status": "APPROVED"}, after={"status": charge.status,
                                                    "posting_reference": body.posting_reference})
        emit(session, current_user, request, event_type="PendingChargePosted",
             resource_type="PendingCharge", resource_id=charge.id,
             payload={"posting_reference": body.posting_reference})
        remember_idempotency(session, current_user, operation="pending-charge.post",
                             key=idempotency_key, payload=payload,
                             resource_type="PendingCharge", resource_id=charge.id,
                             response_status=200)
        session.commit()
        return PendingChargeView.model_validate(charge)


@router.post("/work-orders/{work_order_id}/submit", response_model=WorkOrderView)
def submit_work_order(request: Request, work_order_id: UUID, body: WorkOrderSubmit,
                      current_user: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        record = scoped_work_order(session, current_user, work_order_id, lock=True)
        _assert_technician(record, current_user)
        require_version(record.version, body.expected_version)
        if record.status != "IN_PROGRESS":
            raise AppError("ERR-STATE-TRANSITION", "Công việc chưa ở trạng thái có thể gửi nghiệm thu.", 409)
        incomplete = session.scalar(select(func.count(WorkOrderChecklistItem.id)).where(
            WorkOrderChecklistItem.work_order_id == record.id,
            WorkOrderChecklistItem.is_required.is_(True),
            WorkOrderChecklistItem.is_completed.is_(False),
        )) or 0
        evidence = session.scalar(select(func.count(Attachment.id)).where(
            Attachment.work_order_id == record.id,
            Attachment.is_quarantined.is_(False),
            Attachment.mime_type.in_(("image/png", "image/jpeg")),
        )) or 0
        evidence_required = True
        if record.maintenance_occurrence_id:
            from app.models.maintenance import MaintenanceOccurrence, MaintenancePlan
            evidence_required = session.scalar(select(MaintenancePlan.evidence_required).join(
                MaintenanceOccurrence, MaintenanceOccurrence.plan_id == MaintenancePlan.id,
            ).where(MaintenanceOccurrence.id == record.maintenance_occurrence_id))
            if evidence_required is None:
                raise AppError("ERR-MNT-INTEGRITY", "Công việc bảo trì thiếu liên kết hợp lệ.", 409)
        if incomplete or (evidence_required and not evidence):
            raise AppError("ERR-CHECKLIST-INCOMPLETE",
                           "Hãy hoàn thành checklist và thêm ảnh trước khi gửi nghiệm thu.", 422)
        record.status = "WAITING_ACCEPTANCE"
        record.result_summary = body.result_summary.strip()
        record.updated_by_id = current_user.account_id
        record.version += 1
        audit(session, current_user, request, event_type="WorkOrderSubmitted", action="submit",
              resource_type="WorkOrder", resource_id=record.id, building_id=record.building_id,
              before={"status": "IN_PROGRESS"}, after={"status": record.status})
        session.commit()
        return _work_order_view(session, record)


@router.post("/work-orders/{work_order_id}/accept", response_model=WorkOrderView)
def accept_work_order(request: Request, work_order_id: UUID, body: WorkOrderAccept,
                      current_user: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        record = scoped_work_order(session, current_user, work_order_id, lock=True)
        require_version(record.version, body.expected_version)
        if record.status != "WAITING_ACCEPTANCE":
            raise AppError("ERR-STATE-TRANSITION", "Công việc chưa chờ nghiệm thu.", 409)
        if record.assigned_to_id == current_user.account_id:
            raise AppError("ERR-SOD-SELF-APPROVE", "Người thực hiện không thể tự nghiệm thu.", 403)
        if body.mode == "PROXY":
            current_user.assert_building_role(record.building_id, "cskh")
            _load_attachment(session, current_user, body.evidence_id, record.id)
        else:
            current_user.assert_building_role(record.building_id, "technical_lead")
            if body.evidence_id is not None:
                _load_attachment(session, current_user, body.evidence_id, record.id)
        record.status = "COMPLETED"
        record.accepted_by_id = current_user.account_id
        record.acceptance_mode = body.mode
        record.acceptance_reason = body.reason.strip() if body.reason else None
        record.acceptance_evidence_id = body.evidence_id
        record.completed_at = utc_now()
        record.updated_by_id = current_user.account_id
        record.version += 1
        if record.service_request_id:
            service_request = scoped_service_request(session, current_user, record.service_request_id, lock=True)
            recalculate_request_state(session, service_request, current_user.account_id)
        else:
            from app.models.maintenance import MaintenanceOccurrence
            occurrence = session.scalar(select(MaintenanceOccurrence).where(
                MaintenanceOccurrence.id == record.maintenance_occurrence_id,
            ).with_for_update())
            complete_maintenance(session, occurrence, record,
                                 performed_by_id=record.assigned_to_id,
                                 accepted_by_id=current_user.account_id)
            emit(session, current_user, request, event_type="MaintenanceCompleted",
                 resource_type="MaintenanceOccurrence", resource_id=occurrence.id,
                 payload={"work_order_id": str(record.id)})
        audit(session, current_user, request, event_type="WorkOrderCompleted", action="accept",
              resource_type="WorkOrder", resource_id=record.id, building_id=record.building_id,
              before={"status": "WAITING_ACCEPTANCE"},
              after={"status": record.status, "acceptance_mode": body.mode},
              reason=record.acceptance_reason)
        emit(session, current_user, request, event_type="WorkOrderCompleted",
             resource_type="WorkOrder", resource_id=record.id,
             payload={"acceptance_mode": body.mode})
        session.commit()
        return _work_order_view(session, record)


@router.post("/work-orders/{work_order_id}/cancel", response_model=WorkOrderView)
def cancel_work_order(request: Request, work_order_id: UUID, body: ReasonCommand,
                      current_user: UserContext = Depends(get_current_user_context)):
    current_user.assert_role("technical_lead")
    with request.app.state.database.get_session() as session:
        record = scoped_work_order(session, current_user, work_order_id, lock=True)
        current_user.assert_building_role(record.building_id, "technical_lead")
        require_version(record.version, body.expected_version)
        if record.status in {"CLOSED", "CANCELLED"}:
            raise AppError("ERR-STATE-TRANSITION", "Công việc đã ở trạng thái kết thúc.", 409)
        before = record.status
        reverse_posted_charges(session, current_user, request, record, body.reason.strip())
        for charge in session.scalars(select(PendingCharge).join(CostLine).where(
            CostLine.work_order_id == record.id,
            PendingCharge.status.in_(("SUBMITTED", "APPROVED", "REJECTED")),
        ).with_for_update()):
            charge.status = "CANCELLED"
            charge.version += 1
        for line in session.scalars(select(CostLine).where(
            CostLine.work_order_id == record.id,
            CostLine.status.in_(("DRAFT", "SUBMITTED")),
        ).with_for_update()):
            line.status = "CANCELLED"
            line.updated_by_id = current_user.account_id
            line.version += 1
        record.status = "CANCELLED"
        record.cancelled_reason = body.reason.strip()
        record.updated_by_id = current_user.account_id
        record.version += 1
        if record.service_request_id:
            recalculate_request_state(session,
                                      scoped_service_request(session, current_user, record.service_request_id, lock=True),
                                      current_user.account_id)
        audit(session, current_user, request, event_type="WorkOrderCancelled", action="cancel",
              resource_type="WorkOrder", resource_id=record.id, building_id=record.building_id,
              before={"status": before}, after={"status": record.status},
              reason=record.cancelled_reason)
        session.commit()
        return _work_order_view(session, record)


@router.post("/work-orders/{work_order_id}/reopen", response_model=WorkOrderView)
def reopen_work_order(request: Request, work_order_id: UUID, body: ReasonCommand,
                      current_user: UserContext = Depends(get_current_user_context)):
    current_user.assert_role("technical_lead")
    with request.app.state.database.get_session() as session:
        record = scoped_work_order(session, current_user, work_order_id, lock=True)
        current_user.assert_building_role(record.building_id, "technical_lead")
        require_version(record.version, body.expected_version)
        if record.status not in {"COMPLETED", "CLOSED", "CANCELLED"}:
            raise AppError("ERR-STATE-TRANSITION", "Chỉ công việc đã kết thúc mới được mở lại.", 409)
        if record.maintenance_occurrence_id:
            raise AppError("ERR-MNT-REOPEN", "Bảo trì đã nghiệm thu cần tạo occurrence điều chỉnh mới.", 409)
        before = record.status
        reverse_posted_charges(session, current_user, request, record, body.reason.strip())
        record.status = "IN_PROGRESS"
        record.accepted_by_id = None
        record.acceptance_mode = None
        record.acceptance_reason = None
        record.acceptance_evidence_id = None
        record.completed_at = None
        record.closed_at = None
        record.cancelled_reason = None
        record.updated_by_id = current_user.account_id
        record.version += 1
        if record.service_request_id:
            recalculate_request_state(session,
                                      scoped_service_request(session, current_user, record.service_request_id, lock=True),
                                      current_user.account_id)
        audit(session, current_user, request, event_type="WorkOrderReopened", action="reopen",
              resource_type="WorkOrder", resource_id=record.id, building_id=record.building_id,
              before={"status": before}, after={"status": record.status}, reason=body.reason.strip())
        session.commit()
        return _work_order_view(session, record)


@router.post("/work-orders/{work_order_id}/close", response_model=WorkOrderView)
def close_work_order(request: Request, work_order_id: UUID, body: WorkOrderClose,
                     current_user: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        record = scoped_work_order(session, current_user, work_order_id, lock=True)
        current_user.assert_building_role(record.building_id, "technical_lead", "cskh")
        require_version(record.version, body.expected_version)
        if record.status != "COMPLETED":
            raise AppError("ERR-STATE-TRANSITION", "Chỉ công việc đã nghiệm thu mới được đóng.", 409)
        record.status = "CLOSED"
        record.closed_at = utc_now()
        record.updated_by_id = current_user.account_id
        record.version += 1
        if record.service_request_id:
            service_request = scoped_service_request(session, current_user, record.service_request_id, lock=True)
            recalculate_request_state(session, service_request, current_user.account_id)
            if body.csat_score is not None:
                service_request.csat_score = body.csat_score
        audit(session, current_user, request, event_type="WorkOrderClosed", action="close",
              resource_type="WorkOrder", resource_id=record.id, building_id=record.building_id,
              before={"status": "COMPLETED"}, after={"status": record.status})
        session.commit()
        return _work_order_view(session, record)


@router.post("/service-requests/{request_id}/close", response_model=ServiceRequestView)
def close_service_request(request: Request, request_id: UUID, body: WorkOrderClose,
                          current_user: UserContext = Depends(get_current_user_context)):
    current_user.assert_role("cskh")
    with request.app.state.database.get_session() as session:
        record = scoped_service_request(session, current_user, request_id, lock=True)
        current_user.assert_building_role(record.building_id, "cskh")
        require_version(record.version, body.expected_version)
        if record.status != "RESOLVED":
            raise AppError("ERR-STATE-TRANSITION", "Chỉ yêu cầu đã giải quyết mới được đóng.", 409)
        record.status = "CLOSED"
        record.closed_at = utc_now()
        record.csat_score = body.csat_score
        record.updated_by_id = current_user.account_id
        record.version += 1
        audit(session, current_user, request, event_type="ServiceRequestClosed", action="close",
              resource_type="ServiceRequest", resource_id=record.id, building_id=record.building_id,
              before={"status": "RESOLVED"}, after={"status": record.status,
                                                      "csat_score": record.csat_score})
        session.commit()
        return _request_view(record)


@router.post("/service-requests/sla/run", response_model=SlaRunView)
def run_sla_scan(request: Request, body: SlaRun,
                 current_user: UserContext = Depends(get_current_user_context)):
    current_user.assert_role("admin", "director")
    breached = []
    with request.app.state.database.get_session() as session:
        records = session.scalars(select(ServiceRequest).where(
            *current_user.scope_conditions(ServiceRequest),
            ServiceRequest.status.in_(("NEW", "TRIAGED", "IN_PROGRESS", "WAITING_INFO")),
            ServiceRequest.sla_breached_at.is_(None),
        ).order_by(ServiceRequest.id).with_for_update()).all()
        for record in records:
            if calculate_sla_deadline(record.sla_started_at, record.sla_duration_minutes) <= body.as_of:
                record.sla_breached_at = body.as_of
                record.updated_by_id = current_user.account_id
                record.version += 1
                breached.append(record.id)
                audit(session, current_user, request, event_type="SlaBreached", action="escalate",
                      resource_type="ServiceRequest", resource_id=record.id,
                      building_id=record.building_id, after={"sla_breached_at": body.as_of.isoformat()})
                emit(session, current_user, request, event_type="SlaBreached",
                     resource_type="ServiceRequest", resource_id=record.id)
        session.commit()
    return SlaRunView(breached_request_ids=breached)
