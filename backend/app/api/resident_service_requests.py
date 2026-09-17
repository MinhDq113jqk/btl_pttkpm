import hashlib
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.policy import UserContext, get_current_user_context, scope_not_found
from app.core.security import create_token, decode_token
from app.models.building import Building
from app.models.platform import Attachment, AuditEvent
from app.models.service import ServiceCategory, ServiceRequest
from app.models.site import Site
from app.models.unit import Unit
from app.schemas.resident_service_requests import (
    ResidentAttachmentListResponse,
    ResidentAttachmentView,
    ResidentRequestTimelineEvent,
    ResidentRequestTimelineResponse,
    ResidentServiceRequestCreate,
    ResidentServiceRequestListResponse,
    ResidentServiceRequestUpdate,
    ResidentServiceRequestView,
    ResidentSignedAttachmentLink,
)
from app.schemas.r2 import (
    ServiceRequestFormBuilding,
    ServiceRequestFormCategory,
    ServiceRequestFormOptions,
    ServiceRequestFormUnit,
)
from app.services.r2 import (
    ImageEvidenceError,
    MAX_EVIDENCE_BYTES,
    audit,
    calculate_sla_deadline,
    emit,
    idempotency_replay,
    remember_idempotency,
    require_version,
    utc_now,
    validate_idempotency_key,
    validate_image_evidence,
)


router = APIRouter(tags=["R6 resident service requests"])
EDITABLE_STATUSES = frozenset({"NEW", "WAITING_INFO"})


def _assert_resident_scope(context: UserContext) -> UUID:
    context.assert_role("resident")
    active_site_id = context.assert_active_site()
    if context.resident_person_id is None or not context.resident_unit_ids:
        raise scope_not_found()
    return active_site_id


def _resident_request(
    session: Session, context: UserContext, request_id: UUID, *, lock: bool = False,
) -> ServiceRequest:
    _assert_resident_scope(context)
    statement = select(ServiceRequest).where(
        ServiceRequest.id == request_id,
        *context.scope_conditions(ServiceRequest),
        ServiceRequest.unit_id.in_(context.resident_unit_ids),
        or_(
            ServiceRequest.owner_account_id == context.account_id,
            ServiceRequest.created_by_id == context.account_id,
        ),
    )
    if lock:
        statement = statement.with_for_update()
    record = session.scalar(statement)
    if record is None:
        raise scope_not_found()
    return record


def _resident_unit(session: Session, context: UserContext, unit_id: UUID) -> Unit:
    active_site_id = _assert_resident_scope(context)
    unit = session.scalar(select(Unit).join(Building, Building.id == Unit.building_id).where(
        Unit.id == unit_id,
        Unit.id.in_(context.resident_unit_ids),
        Building.site_id == active_site_id,
    ))
    if unit is None:
        raise scope_not_found()
    return unit


@router.get("/resident/service-request-options", response_model=ServiceRequestFormOptions)
def get_resident_service_request_options(
    request: Request,
    current_user: UserContext = Depends(get_current_user_context),
):
    """Return only buildings, units and active categories owned by the resident.

    The resident UI may choose from these values, but the create endpoint
    re-checks every identifier against the live session scope before writing.
    """
    active_site_id = _assert_resident_scope(current_user)
    with request.app.state.database.get_session() as session:
        units = session.scalars(select(Unit).join(
            Building, Building.id == Unit.building_id,
        ).join(
            Site, Site.id == Building.site_id,
        ).where(
            Unit.id.in_(current_user.resident_unit_ids),
            Site.id == active_site_id,
            Site.tenant_id == current_user.tenant_id,
        ).order_by(Unit.unit_number, Unit.id)).all()
        if not units:
            raise scope_not_found()
        building_ids = {unit.building_id for unit in units}
        buildings = session.scalars(select(Building).join(
            Site, Site.id == Building.site_id,
        ).where(
            Building.id.in_(building_ids),
            Site.id == active_site_id,
            Site.tenant_id == current_user.tenant_id,
        ).order_by(Building.code, Building.id)).all()
        categories = session.scalars(select(ServiceCategory).where(
            *current_user.scope_conditions(ServiceCategory),
            ServiceCategory.is_active.is_(True),
            ServiceCategory.building_id.is_(None) | ServiceCategory.building_id.in_(building_ids),
        ).order_by(ServiceCategory.name, ServiceCategory.id)).all()
        return ServiceRequestFormOptions(
            buildings=[ServiceRequestFormBuilding(id=building.id, code=building.code, name=building.name)
                       for building in buildings],
            categories=[ServiceRequestFormCategory(
                id=category.id, code=category.code, name=category.name,
                building_id=category.building_id,
            ) for category in categories],
            units=[ServiceRequestFormUnit(
                id=unit.id, unit_number=unit.unit_number, building_id=unit.building_id,
            ) for unit in units],
        )


def _view(record: ServiceRequest) -> ResidentServiceRequestView:
    # Resident requests always have a Unit; the cast is guarded at creation and
    # lookup time so no unscoped request can enter this view.
    if record.unit_id is None:
        raise scope_not_found()
    return ResidentServiceRequestView(
        id=record.id,
        code=record.code,
        unit_id=record.unit_id,
        category_id=record.category_id,
        title=record.title,
        description=record.description,
        priority=record.priority,
        status=record.status,
        sla_deadline=calculate_sla_deadline(record.sla_started_at, record.sla_duration_minutes),
        sla_breached_at=record.sla_breached_at,
        resolved_at=record.resolved_at,
        closed_at=record.closed_at,
        version=record.version,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _attachment_view(attachment: Attachment) -> ResidentAttachmentView:
    return ResidentAttachmentView(
        id=attachment.id,
        original_name=attachment.original_name,
        mime_type=attachment.mime_type,
        size_bytes=attachment.size_bytes,
        sha256=attachment.sha256,
        created_at=attachment.created_at,
    )


def _lock_idempotency(
    session: Session, context: UserContext, *, operation: str, key: str | None,
) -> str:
    """Serialize only same-actor retries; the database unique key remains the backstop."""
    safe_key = validate_idempotency_key(key)
    material = ":".join((str(context.tenant_id), str(context.assert_active_site()),
                           str(context.account_id), operation, safe_key))
    lock_key = int.from_bytes(hashlib.sha256(material.encode("utf-8")).digest()[:8], "big", signed=True)
    session.execute(select(func.pg_advisory_xact_lock(lock_key)))
    return safe_key


def _resident_attachment(
    session: Session, context: UserContext, service_request: ServiceRequest, attachment_id: UUID,
) -> Attachment:
    attachment = session.scalar(select(Attachment).where(
        Attachment.id == attachment_id,
        Attachment.service_request_id == service_request.id,
        *context.scope_conditions(Attachment),
    ))
    if attachment is None:
        raise scope_not_found()
    if attachment.is_quarantined:
        raise AppError("ERR-FILE-QUARANTINED", "Tệp không an toàn và đã bị chặn.", 423)
    return attachment


def _assert_attachment_token(
    request: Request, token: str, context: UserContext,
    service_request: ServiceRequest, attachment: Attachment,
) -> None:
    claims = decode_token(
        token,
        request.app.state.settings.auth_secret(),
        expired_code="ERR-LINK-EXPIRED",
        expired_message="Liên kết đã hết hạn. Tải lại trang.",
        expired_status=410,
    )
    expected = {
        "purpose": "resident-service-request-attachment-download",
        "sub": str(context.account_id),
        "tenant_id": str(context.tenant_id),
        "active_site_id": str(context.assert_active_site()),
        "service_request_id": str(service_request.id),
        "attachment_id": str(attachment.id),
    }
    if any(claims.get(key) != value for key, value in expected.items()):
        raise scope_not_found()


@router.get("/resident/service-requests", response_model=ResidentServiceRequestListResponse)
def list_resident_service_requests(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: UserContext = Depends(get_current_user_context),
):
    _assert_resident_scope(current_user)
    conditions = (
        *current_user.scope_conditions(ServiceRequest),
        ServiceRequest.unit_id.in_(current_user.resident_unit_ids),
        or_(
            ServiceRequest.owner_account_id == current_user.account_id,
            ServiceRequest.created_by_id == current_user.account_id,
        ),
    )
    with request.app.state.database.get_session() as session:
        total = session.scalar(select(func.count(ServiceRequest.id)).where(*conditions)) or 0
        records = session.scalars(select(ServiceRequest).where(*conditions).order_by(
            ServiceRequest.created_at.desc(), ServiceRequest.id.desc(),
        ).offset((page - 1) * page_size).limit(page_size)).all()
        return ResidentServiceRequestListResponse(
            items=[_view(record) for record in records], page=page, page_size=page_size, total=total,
        )


@router.post("/resident/service-requests", response_model=ResidentServiceRequestView, status_code=201)
def create_resident_service_request(
    request: Request,
    body: ResidentServiceRequestCreate,
    current_user: UserContext = Depends(get_current_user_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    payload = body.model_dump(mode="json")
    with request.app.state.database.get_session() as session:
        safe_key = _lock_idempotency(
            session, current_user, operation="resident-service-request.create", key=idempotency_key,
        )
        replay = idempotency_replay(
            session, current_user, operation="resident-service-request.create", key=safe_key, payload=payload,
        )
        if replay is not None:
            return _view(_resident_request(session, current_user, replay.resource_id))
        unit = _resident_unit(session, current_user, body.unit_id)
        category = session.scalar(select(ServiceCategory).where(
            ServiceCategory.id == body.category_id,
            *current_user.scope_conditions(ServiceCategory),
            ServiceCategory.is_active.is_(True),
            or_(ServiceCategory.building_id.is_(None), ServiceCategory.building_id == unit.building_id),
        ))
        if category is None:
            raise scope_not_found()
        now = utc_now()
        record = ServiceRequest(
            tenant_id=current_user.tenant_id,
            site_id=current_user.assert_active_site(),
            building_id=unit.building_id,
            unit_id=unit.id,
            category_id=category.id,
            code=f"SR-{uuid4().hex[:12].upper()}",
            title=body.title,
            description=body.description,
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
        audit(session, current_user, request, event_type="ResidentServiceRequestCreated", action="create",
              resource_type="ServiceRequest", resource_id=record.id, building_id=record.building_id,
              after={"status": record.status, "priority": record.priority})
        emit(session, current_user, request, event_type="ResidentServiceRequestCreated",
             resource_type="ServiceRequest", resource_id=record.id, payload={"code": record.code})
        remember_idempotency(
            session, current_user, operation="resident-service-request.create", key=safe_key,
            payload=payload, resource_type="ServiceRequest", resource_id=record.id, response_status=201,
        )
        session.commit()
        return _view(record)


@router.get("/resident/service-requests/{request_id}", response_model=ResidentServiceRequestView)
def get_resident_service_request(
    request: Request,
    request_id: UUID,
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        return _view(_resident_request(session, current_user, request_id))


@router.patch("/resident/service-requests/{request_id}", response_model=ResidentServiceRequestView)
def update_resident_service_request(
    request: Request,
    request_id: UUID,
    body: ResidentServiceRequestUpdate,
    current_user: UserContext = Depends(get_current_user_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    payload = body.model_dump(mode="json") | {"service_request_id": str(request_id)}
    with request.app.state.database.get_session() as session:
        safe_key = _lock_idempotency(
            session, current_user, operation="resident-service-request.update", key=idempotency_key,
        )
        replay = idempotency_replay(
            session, current_user, operation="resident-service-request.update", key=safe_key, payload=payload,
        )
        if replay is not None:
            return _view(_resident_request(session, current_user, replay.resource_id))
        record = _resident_request(session, current_user, request_id, lock=True)
        require_version(record.version, body.expected_version)
        if record.status not in EDITABLE_STATUSES:
            raise AppError("ERR-STATE-TRANSITION", "Yêu cầu không còn ở trạng thái có thể chỉnh sửa.", 409)
        before = {"title": record.title, "description": record.description, "priority": record.priority}
        if body.title is not None:
            record.title = body.title
        if body.description is not None:
            record.description = body.description
        if body.priority is not None:
            record.priority = body.priority
        record.updated_by_id = current_user.account_id
        record.version += 1
        audit(session, current_user, request, event_type="ResidentServiceRequestUpdated", action="update",
              resource_type="ServiceRequest", resource_id=record.id, building_id=record.building_id,
              before=before, after={"status": record.status, "priority": record.priority})
        emit(session, current_user, request, event_type="ResidentServiceRequestUpdated",
             resource_type="ServiceRequest", resource_id=record.id)
        remember_idempotency(
            session, current_user, operation="resident-service-request.update", key=safe_key,
            payload=payload, resource_type="ServiceRequest", resource_id=record.id, response_status=200,
        )
        session.commit()
        return _view(record)


@router.get("/resident/service-requests/{request_id}/timeline", response_model=ResidentRequestTimelineResponse)
def list_resident_service_request_timeline(
    request: Request,
    request_id: UUID,
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        record = _resident_request(session, current_user, request_id)
        events = session.scalars(select(AuditEvent).where(
            *current_user.scope_conditions(AuditEvent),
            AuditEvent.resource_type == "ServiceRequest",
            AuditEvent.resource_id == record.id,
        ).order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc())).all()
        return ResidentRequestTimelineResponse(items=[ResidentRequestTimelineEvent(
            id=event.id,
            event_type=event.event_type,
            action=event.action,
            before_status=(event.before_data or {}).get("status"),
            after_status=(event.after_data or {}).get("status"),
            before_priority=(event.before_data or {}).get("priority"),
            after_priority=(event.after_data or {}).get("priority"),
            created_at=event.created_at,
        ) for event in events])


@router.get("/resident/service-requests/{request_id}/evidence", response_model=ResidentAttachmentListResponse)
def list_resident_service_request_evidence(
    request: Request,
    request_id: UUID,
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        record = _resident_request(session, current_user, request_id)
        attachments = session.scalars(select(Attachment).where(
            Attachment.service_request_id == record.id,
            *current_user.scope_conditions(Attachment),
            Attachment.is_quarantined.is_(False),
        ).order_by(Attachment.created_at.asc(), Attachment.id.asc())).all()
        return ResidentAttachmentListResponse(items=[_attachment_view(attachment) for attachment in attachments])


@router.post("/resident/service-requests/{request_id}/evidence", response_model=ResidentAttachmentView, status_code=201)
async def upload_resident_service_request_evidence(
    request: Request,
    request_id: UUID,
    current_user: UserContext = Depends(get_current_user_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    file_name: str | None = Header(None, alias="X-File-Name"),
):
    # Reject an out-of-scope target before reading an arbitrary-size request body.
    with request.app.state.database.get_session() as session:
        record = _resident_request(session, current_user, request_id)
        if record.status not in EDITABLE_STATUSES:
            raise AppError("ERR-STATE-TRANSITION", "Yêu cầu không còn nhận bổ sung bằng chứng.", 409)

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
        "service_request_id": str(request_id),
        "sha256": digest,
        "mime_type": detected_mime or claimed_mime,
    }
    with request.app.state.database.get_session() as session:
        safe_key = _lock_idempotency(
            session, current_user, operation="resident-service-request.evidence", key=idempotency_key,
        )
        replay = idempotency_replay(
            session, current_user, operation="resident-service-request.evidence", key=safe_key, payload=payload,
        )
        if replay is not None:
            if replay.response_status == 422:
                raise AppError("ERR-FILE-QUARANTINED", "Tệp không an toàn và đã bị chặn.", 422)
            record = _resident_request(session, current_user, request_id)
            return _attachment_view(_resident_attachment(session, current_user, record, replay.resource_id))
        record = _resident_request(session, current_user, request_id, lock=True)
        if record.status not in EDITABLE_STATUSES:
            raise AppError("ERR-STATE-TRANSITION", "Yêu cầu không còn nhận bổ sung bằng chứng.", 409)
        is_quarantined = rejection_reason is not None
        if is_quarantined:
            storage_key = f"quarantine/{record.tenant_id}/{record.site_id}/{uuid4().hex}.bin"
            stored_mime = "application/octet-stream"
        else:
            extension = ".png" if detected_mime == "image/png" else ".jpg"
            storage_key = f"resident/{record.tenant_id}/{record.site_id}/{uuid4().hex}{extension}"
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
                service_request_id=record.id,
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
            event_type = "AttachmentQuarantined" if is_quarantined else "ResidentServiceRequestEvidenceAdded"
            audit(session, current_user, request, event_type=event_type,
                  action="quarantine" if is_quarantined else "upload",
                  resource_type="Attachment", resource_id=attachment.id, building_id=record.building_id,
                  after={
                      "mime_type": attachment.mime_type,
                      "size_bytes": attachment.size_bytes,
                      "sha256": attachment.sha256,
                      "quarantine_reason": rejection_reason,
                  })
            if is_quarantined:
                emit(session, current_user, request, event_type="AttachmentQuarantined",
                     resource_type="Attachment", resource_id=attachment.id,
                     payload={"reason": rejection_reason, "service_request_id": str(record.id)})
            else:
                emit(session, current_user, request, event_type="ResidentServiceRequestEvidenceAdded",
                     resource_type="Attachment", resource_id=attachment.id,
                     payload={"service_request_id": str(record.id)})
            remember_idempotency(
                session, current_user, operation="resident-service-request.evidence", key=safe_key,
                payload=payload, resource_type="Attachment", resource_id=attachment.id,
                response_status=422 if is_quarantined else 201,
            )
            session.commit()
        except Exception:
            target.unlink(missing_ok=True)
            raise
        if is_quarantined:
            raise AppError("ERR-FILE-QUARANTINED", "Tệp không an toàn và đã bị chặn.", 422)
        return _attachment_view(attachment)


@router.get(
    "/resident/service-requests/{request_id}/evidence/{attachment_id}/signed-link",
    response_model=ResidentSignedAttachmentLink,
)
def create_resident_evidence_signed_link(
    request: Request,
    request_id: UUID,
    attachment_id: UUID,
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        record = _resident_request(session, current_user, request_id)
        attachment = _resident_attachment(session, current_user, record, attachment_id)
        ttl = request.app.state.settings.attachment_link_ttl_seconds
        token = create_token({
            "sub": str(current_user.account_id),
            "active_site_id": str(current_user.assert_active_site()),
            "purpose": "resident-service-request-attachment-download",
            "attachment_id": str(attachment.id),
            "service_request_id": str(record.id),
            "tenant_id": str(current_user.tenant_id),
        }, request.app.state.settings.auth_secret(), expires_in_seconds=ttl)
        expires_at = utc_now() + timedelta(seconds=ttl)
        audit(session, current_user, request, event_type="ResidentAttachmentSignedLinkIssued",
              action="signed-link", resource_type="Attachment", resource_id=attachment.id,
              building_id=record.building_id, after={"expires_at": expires_at.isoformat()})
        session.commit()
        return ResidentSignedAttachmentLink(
            url=(f"/api/v1/resident/service-requests/{record.id}/evidence/{attachment.id}"
                 f"/content?signed_token={token}"),
            expires_at=expires_at,
        )


@router.get("/resident/service-requests/{request_id}/evidence/{attachment_id}/content")
def download_resident_evidence(
    request: Request,
    request_id: UUID,
    attachment_id: UUID,
    signed_token: str = Query(..., min_length=1, max_length=16384),
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        record = _resident_request(session, current_user, request_id)
        attachment = _resident_attachment(session, current_user, record, attachment_id)
        _assert_attachment_token(request, signed_token, current_user, record, attachment)
        root = request.app.state.settings.private_storage_path.resolve()
        target = (root / attachment.storage_key).resolve()
        if not target.is_file() or root not in target.parents:
            raise scope_not_found()
        audit(session, current_user, request, event_type="ResidentAttachmentDownloaded", action="download",
              resource_type="Attachment", resource_id=attachment.id, building_id=record.building_id)
        session.commit()
        return FileResponse(target, media_type=attachment.mime_type, filename=attachment.original_name,
                            headers={"Cache-Control": "private, no-store"})
