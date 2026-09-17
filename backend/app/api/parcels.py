"""V1 parcel intake, handover, case linkage and private evidence endpoints."""
import hashlib
from datetime import UTC, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import and_, func, or_, select

from app.core.exceptions import AppError
from app.core.policy import UserContext, get_current_user_context, scope_not_found
from app.core.security import create_token, decode_token, hash_password, verify_password
from app.models.parcel import Parcel
from app.models.operations import SecurityIncident
from app.models.platform import Attachment, AuditEvent
from app.models.service import CaseRecord
from app.schemas.parcel import (
    ParcelAttachmentListResponse,
    ParcelAttachmentView,
    ParcelCaseCreate,
    ParcelCaseView,
    ParcelCreate,
    ParcelExceptionCommand,
    ParcelHandoverCommand,
    ParcelIncidentLinkCreate,
    ParcelIncidentView,
    ParcelListResponse,
    ParcelReadyCommand,
    ParcelSignedAttachmentLink,
    ParcelStatus,
    ParcelTimelineEvent,
    ParcelTimelineResponse,
    ParcelView,
)
from app.services.parcels import (
    PIN_LOCK_DURATION,
    PIN_ATTEMPT_COUNTER_MAX,
    PIN_MAX_ATTEMPTS,
    assert_parcel_operator,
    assert_parcel_incident_operator,
    assert_case_source,
    assert_transition,
    ensure_recipient_in_tenant,
    ensure_unit_in_scope,
    parcel_view,
    scoped_parcel_attachment,
    scoped_parcel_case,
    scoped_parcel_incident,
    parcel_visibility,
    scoped_parcel,
    utc_now,
    verify_handover_pin,
)
from app.services.r2 import (
    ImageEvidenceError,
    MAX_EVIDENCE_BYTES,
    audit,
    emit,
    idempotency_replay,
    remember_idempotency,
    require_version,
    validate_idempotency_key,
    validate_image_evidence,
)


router = APIRouter(tags=["V1 parcels"])


def _case_view(record: CaseRecord) -> ParcelCaseView:
    return ParcelCaseView.model_validate(record)


def _incident_view(record: SecurityIncident) -> ParcelIncidentView:
    return ParcelIncidentView.model_validate(record)


def _attachment_view(record: Attachment) -> ParcelAttachmentView:
    return ParcelAttachmentView.model_validate(record)


def _lock_idempotency(session, context: UserContext, *, operation: str, key: str | None) -> str:
    """Serialize same-actor file retries before reading/writing private bytes."""
    safe_key = validate_idempotency_key(key)
    material = ":".join((str(context.tenant_id), str(context.assert_active_site()),
                           str(context.account_id), operation, safe_key))
    lock_key = int.from_bytes(hashlib.sha256(material.encode("utf-8")).digest()[:8], "big", signed=True)
    session.execute(select(func.pg_advisory_xact_lock(lock_key)))
    return safe_key


def _assert_signed_parcel_attachment_token(
    request: Request,
    token: str,
    context: UserContext,
    parcel: Parcel,
    attachment: Attachment,
) -> None:
    claims = decode_token(
        token,
        request.app.state.settings.auth_secret(),
        expired_code="ERR-LINK-EXPIRED",
        expired_message="Liên kết đã hết hạn. Tải lại trang.",
        expired_status=410,
    )
    expected = {
        "purpose": "parcel-attachment-download",
        "sub": str(context.account_id),
        "tenant_id": str(context.tenant_id),
        "active_site_id": str(context.assert_active_site()),
        "parcel_id": str(parcel.id),
        "attachment_id": str(attachment.id),
    }
    if any(claims.get(key) != value for key, value in expected.items()):
        raise scope_not_found()


def _timeline_condition(parcel_id: UUID):
    case_ids = select(CaseRecord.id).where(CaseRecord.source_parcel_id == parcel_id)
    incident_ids = select(SecurityIncident.id).where(SecurityIncident.parcel_id == parcel_id)
    attachment_ids = select(Attachment.id).where(Attachment.parcel_id == parcel_id)
    return or_(
        and_(AuditEvent.resource_type == "Parcel", AuditEvent.resource_id == parcel_id),
        and_(AuditEvent.resource_type == "Case", AuditEvent.resource_id.in_(case_ids)),
        and_(AuditEvent.resource_type == "SecurityIncident", AuditEvent.resource_id.in_(incident_ids)),
        and_(AuditEvent.resource_type == "Attachment", AuditEvent.resource_id.in_(attachment_ids)),
    )
@router.get("/parcels", response_model=ParcelListResponse)
def list_parcels(
    request: Request,
    building_id: UUID | None = Query(default=None),
    status: ParcelStatus | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: UserContext = Depends(get_current_user_context),
):
    visibility = parcel_visibility(current_user)
    conditions = [*current_user.scope_conditions(Parcel), visibility]
    if building_id is not None:
        assert_parcel_operator(current_user, building_id)
        conditions.append(Parcel.building_id == building_id)
    if status is not None:
        conditions.append(Parcel.status == status)
    with request.app.state.database.get_session() as session:
        total = session.scalar(select(func.count(Parcel.id)).where(*conditions)) or 0
        records = session.scalars(select(Parcel).where(*conditions).order_by(
            Parcel.received_at.desc(), Parcel.id.desc(),
        ).offset((page - 1) * page_size).limit(page_size)).all()
        return ParcelListResponse(
            items=[parcel_view(record) for record in records],
            page=page,
            page_size=page_size,
            total=total,
        )


@router.post("/parcels", response_model=ParcelView, status_code=201)
def receive_parcel(
    request: Request,
    body: ParcelCreate,
    current_user: UserContext = Depends(get_current_user_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    assert_parcel_operator(current_user, body.building_id)
    payload = body.model_dump(mode="json")
    with request.app.state.database.get_session() as session:
        replay = idempotency_replay(
            session, current_user, operation="parcel.create",
            key=idempotency_key, payload=payload,
        )
        if replay:
            return parcel_view(scoped_parcel(session, current_user, replay.resource_id))
        ensure_unit_in_scope(
            session, current_user, building_id=body.building_id, unit_id=body.unit_id,
        )
        ensure_recipient_in_tenant(session, current_user, body.recipient_person_id)
        received_at = (body.received_at or utc_now()).astimezone(UTC)
        record = Parcel(
            tenant_id=current_user.tenant_id,
            site_id=current_user.assert_active_site(),
            building_id=body.building_id,
            unit_id=body.unit_id,
            recipient_person_id=body.recipient_person_id,
            parcel_code=body.parcel_code,
            carrier_reference=body.carrier_reference,
            recipient_name_snapshot=body.recipient_name_snapshot,
            recipient_contact_snapshot=body.recipient_contact_snapshot,
            storage_location=body.storage_location,
            pin_hash=hash_password(body.pin),
            status="RECEIVED",
            received_at=received_at,
            created_by_id=current_user.account_id,
            updated_by_id=current_user.account_id,
        )
        session.add(record)
        session.flush()
        audit(
            session, current_user, request, event_type="ParcelReceived", action="create",
            resource_type="Parcel", resource_id=record.id, building_id=record.building_id,
            after={"parcel_code": record.parcel_code, "status": record.status},
        )
        emit(
            session, current_user, request, event_type="ParcelReceived",
            resource_type="Parcel", resource_id=record.id,
            payload={"parcel_code": record.parcel_code, "status": record.status},
        )
        remember_idempotency(
            session, current_user, operation="parcel.create", key=idempotency_key,
            payload=payload, resource_type="Parcel", resource_id=record.id,
            response_status=201,
        )
        session.commit()
        return parcel_view(record)


@router.get("/parcels/{parcel_id}", response_model=ParcelView)
def get_parcel(
    request: Request,
    parcel_id: UUID,
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        return parcel_view(scoped_parcel(session, current_user, parcel_id))


@router.get("/parcels/{parcel_id}/case", response_model=ParcelCaseView)
def get_parcel_case(
    request: Request,
    parcel_id: UUID,
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        parcel = scoped_parcel(session, current_user, parcel_id)
        case_record = scoped_parcel_case(session, current_user, parcel.id)
        if case_record is None:
            raise scope_not_found()
        return _case_view(case_record)


@router.post("/parcels/{parcel_id}/case", response_model=ParcelCaseView, status_code=201)
def open_parcel_case(
    request: Request,
    parcel_id: UUID,
    body: ParcelCaseCreate,
    current_user: UserContext = Depends(get_current_user_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    payload = body.model_dump(mode="json") | {"parcel_id": str(parcel_id)}
    with request.app.state.database.get_session() as session:
        parcel = scoped_parcel(session, current_user, parcel_id, lock=True)
        assert_case_source(parcel)
        replay = idempotency_replay(
            session, current_user, operation="parcel.case.create",
            key=idempotency_key, payload=payload,
        )
        if replay is not None:
            case_record = scoped_parcel_case(session, current_user, parcel.id, replay.resource_id)
            if case_record is None:
                raise scope_not_found()
            return _case_view(case_record)
        existing = scoped_parcel_case(session, current_user, parcel.id)
        if existing is not None:
            raise AppError("ERR-DUPLICATE", "Bưu phẩm đã có Case liên kết.", 409)
        case_record = CaseRecord(
            tenant_id=parcel.tenant_id,
            site_id=parcel.site_id,
            building_id=parcel.building_id,
            source_work_order_id=None,
            source_parcel_id=parcel.id,
            reason=body.reason.strip(),
            status="NEW",
            created_by_id=current_user.account_id,
            updated_by_id=current_user.account_id,
        )
        session.add(case_record)
        session.flush()
        audit(
            session, current_user, request, event_type="ParcelCaseOpened", action="create",
            resource_type="Case", resource_id=case_record.id, building_id=parcel.building_id,
            after={"source_parcel_id": str(parcel.id), "reason": case_record.reason},
        )
        emit(
            session, current_user, request, event_type="ParcelCaseOpened",
            resource_type="Case", resource_id=case_record.id,
            payload={"parcel_id": str(parcel.id), "reason": case_record.reason},
        )
        remember_idempotency(
            session, current_user, operation="parcel.case.create", key=idempotency_key,
            payload=payload, resource_type="Case", resource_id=case_record.id,
            response_status=201,
        )
        session.commit()
        return _case_view(case_record)


@router.get("/parcels/{parcel_id}/incident", response_model=ParcelIncidentView)
def get_parcel_incident(
    request: Request,
    parcel_id: UUID,
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        parcel = scoped_parcel(session, current_user, parcel_id)
        incident = scoped_parcel_incident(session, current_user, parcel.id)
        if incident is None:
            raise scope_not_found()
        return _incident_view(incident)


@router.post("/parcels/{parcel_id}/incident-link", response_model=ParcelIncidentView)
def link_parcel_incident(
    request: Request,
    parcel_id: UUID,
    body: ParcelIncidentLinkCreate,
    current_user: UserContext = Depends(get_current_user_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    payload = body.model_dump(mode="json") | {"parcel_id": str(parcel_id)}
    with request.app.state.database.get_session() as session:
        parcel = scoped_parcel(session, current_user, parcel_id, lock=True)
        assert_parcel_incident_operator(current_user, parcel.building_id)
        replay = idempotency_replay(
            session, current_user, operation="parcel.incident.link",
            key=idempotency_key, payload=payload,
        )
        if replay is not None:
            incident = session.scalar(select(SecurityIncident).where(
                SecurityIncident.id == replay.resource_id,
                *current_user.scope_conditions(SecurityIncident),
            ))
            if incident is None:
                raise scope_not_found()
            return _incident_view(incident)
        incident = session.scalar(select(SecurityIncident).where(
            SecurityIncident.id == body.incident_id,
            *current_user.scope_conditions(SecurityIncident),
        ).with_for_update())
        if incident is None:
            raise scope_not_found()
        if incident.building_id != parcel.building_id:
            raise scope_not_found()
        if incident.parcel_id is not None and incident.parcel_id != parcel.id:
            raise AppError("ERR-DUPLICATE", "Incident đã liên kết với bưu phẩm khác.", 409)
        existing = scoped_parcel_incident(session, current_user, parcel.id)
        if existing is not None and existing.id != incident.id:
            raise AppError("ERR-DUPLICATE", "Bưu phẩm đã có incident liên kết.", 409)
        before = {"parcel_id": str(incident.parcel_id) if incident.parcel_id else None, "version": incident.version}
        incident.parcel_id = parcel.id
        incident.updated_by_id = current_user.account_id
        incident.version += 1
        audit(
            session, current_user, request, event_type="ParcelIncidentLinked", action="link",
            resource_type="SecurityIncident", resource_id=incident.id,
            building_id=parcel.building_id,
            before=before,
            after={"parcel_id": str(parcel.id), "version": incident.version, "reason": body.reason.strip()},
        )
        emit(
            session, current_user, request, event_type="ParcelIncidentLinked",
            resource_type="SecurityIncident", resource_id=incident.id,
            payload={"parcel_id": str(parcel.id)},
        )
        remember_idempotency(
            session, current_user, operation="parcel.incident.link", key=idempotency_key,
            payload=payload, resource_type="SecurityIncident", resource_id=incident.id,
            response_status=200,
        )
        session.commit()
        return _incident_view(incident)


@router.get("/parcels/{parcel_id}/timeline", response_model=ParcelTimelineResponse)
def get_parcel_timeline(
    request: Request,
    parcel_id: UUID,
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        parcel = scoped_parcel(session, current_user, parcel_id)
        events = session.scalars(select(AuditEvent).where(
            *current_user.scope_conditions(AuditEvent),
            _timeline_condition(parcel.id),
        ).order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc())).all()
        return ParcelTimelineResponse(items=[ParcelTimelineEvent.model_validate(event) for event in events])


@router.get("/parcels/{parcel_id}/evidence", response_model=ParcelAttachmentListResponse)
def list_parcel_evidence(
    request: Request,
    parcel_id: UUID,
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        parcel = scoped_parcel(session, current_user, parcel_id)
        attachments = session.scalars(select(Attachment).where(
            Attachment.parcel_id == parcel.id,
            *current_user.scope_conditions(Attachment),
            Attachment.is_quarantined.is_(False),
        ).order_by(Attachment.created_at.asc(), Attachment.id.asc())).all()
        return ParcelAttachmentListResponse(items=[_attachment_view(item) for item in attachments])


@router.post("/parcels/{parcel_id}/evidence", response_model=ParcelAttachmentView, status_code=201)
async def upload_parcel_evidence(
    request: Request,
    parcel_id: UUID,
    current_user: UserContext = Depends(get_current_user_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    file_name: str | None = Header(None, alias="X-File-Name"),
):
    # Authorize parcel scope before consuming an arbitrary request body.
    with request.app.state.database.get_session() as session:
        parcel = scoped_parcel(session, current_user, parcel_id)

    buffered = bytearray()
    async for chunk in request.stream():
        if len(buffered) + len(chunk) > MAX_EVIDENCE_BYTES:
            raise AppError("ERR-FILE-REJECTED", "Tệp không đúng loại, nội dung hoặc giới hạn kích thước.", 422)
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
        "parcel_id": str(parcel_id),
        "sha256": digest,
        "mime_type": detected_mime or claimed_mime,
    }
    with request.app.state.database.get_session() as session:
        safe_key = _lock_idempotency(
            session, current_user, operation="parcel.evidence", key=idempotency_key,
        )
        replay = idempotency_replay(
            session, current_user, operation="parcel.evidence", key=safe_key, payload=payload,
        )
        if replay is not None:
            if replay.response_status == 422:
                raise AppError("ERR-FILE-QUARANTINED", "Tệp không an toàn và đã bị chặn.", 422)
            record = scoped_parcel_attachment(session, current_user, parcel_id, replay.resource_id)
            if record is None:
                raise scope_not_found()
            return _attachment_view(record)
        parcel = scoped_parcel(session, current_user, parcel_id, lock=True)
        is_quarantined = rejection_reason is not None
        if is_quarantined:
            storage_key = f"quarantine/{parcel.tenant_id}/{parcel.site_id}/{uuid4().hex}.bin"
            stored_mime = "application/octet-stream"
        else:
            extension = ".png" if detected_mime == "image/png" else ".jpg"
            storage_key = f"parcel/{parcel.tenant_id}/{parcel.site_id}/{uuid4().hex}{extension}"
            stored_mime = detected_mime
        root = request.app.state.settings.private_storage_path.resolve()
        target = (root / storage_key).resolve()
        if root not in target.parents:
            raise AppError("ERR-FILE-REJECTED", "Không thể lưu tệp.", 422)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        try:
            attachment = Attachment(
                tenant_id=parcel.tenant_id,
                site_id=parcel.site_id,
                building_id=parcel.building_id,
                parcel_id=parcel.id,
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
            event_type = "AttachmentQuarantined" if is_quarantined else "ParcelEvidenceAdded"
            audit(
                session, current_user, request, event_type=event_type,
                action="quarantine" if is_quarantined else "upload",
                resource_type="Attachment", resource_id=attachment.id,
                building_id=parcel.building_id,
                after={
                    "parcel_id": str(parcel.id), "mime_type": attachment.mime_type,
                    "size_bytes": attachment.size_bytes, "sha256": attachment.sha256,
                    "quarantine_reason": rejection_reason,
                },
            )
            if is_quarantined:
                emit(
                    session, current_user, request, event_type="AttachmentQuarantined",
                    resource_type="Attachment", resource_id=attachment.id,
                    payload={"reason": rejection_reason, "parcel_id": str(parcel.id)},
                )
            else:
                emit(
                    session, current_user, request, event_type="ParcelEvidenceAdded",
                    resource_type="Attachment", resource_id=attachment.id,
                    payload={"parcel_id": str(parcel.id)},
                )
            remember_idempotency(
                session, current_user, operation="parcel.evidence", key=safe_key,
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
    "/parcels/{parcel_id}/evidence/{attachment_id}/signed-link",
    response_model=ParcelSignedAttachmentLink,
)
def create_parcel_evidence_signed_link(
    request: Request,
    parcel_id: UUID,
    attachment_id: UUID,
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        parcel = scoped_parcel(session, current_user, parcel_id)
        attachment = scoped_parcel_attachment(session, current_user, parcel.id, attachment_id)
        if attachment is None:
            raise scope_not_found()
        ttl = request.app.state.settings.attachment_link_ttl_seconds
        token = create_token({
            "sub": str(current_user.account_id),
            "active_site_id": str(current_user.assert_active_site()),
            "purpose": "parcel-attachment-download",
            "attachment_id": str(attachment.id),
            "parcel_id": str(parcel.id),
            "tenant_id": str(current_user.tenant_id),
        }, request.app.state.settings.auth_secret(), expires_in_seconds=ttl)
        expires_at = utc_now() + timedelta(seconds=ttl)
        audit(
            session, current_user, request, event_type="ParcelAttachmentSignedLinkIssued",
            action="signed-link", resource_type="Attachment", resource_id=attachment.id,
            building_id=parcel.building_id, after={"expires_at": expires_at.isoformat()},
        )
        session.commit()
        return ParcelSignedAttachmentLink(
            url=(f"/api/v1/parcels/{parcel.id}/evidence/{attachment.id}/content"
                 f"?signed_token={token}"),
            expires_at=expires_at,
        )


@router.get("/parcels/{parcel_id}/evidence/{attachment_id}/content")
def download_parcel_evidence(
    request: Request,
    parcel_id: UUID,
    attachment_id: UUID,
    signed_token: str = Query(..., min_length=1, max_length=16384),
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        parcel = scoped_parcel(session, current_user, parcel_id)
        attachment = scoped_parcel_attachment(session, current_user, parcel.id, attachment_id)
        if attachment is None:
            raise scope_not_found()
        _assert_signed_parcel_attachment_token(request, signed_token, current_user, parcel, attachment)
        root = request.app.state.settings.private_storage_path.resolve()
        target = (root / attachment.storage_key).resolve()
        if not target.is_file() or root not in target.parents:
            raise scope_not_found()
        audit(
            session, current_user, request, event_type="ParcelAttachmentDownloaded", action="download",
            resource_type="Attachment", resource_id=attachment.id, building_id=parcel.building_id,
        )
        session.commit()
        return FileResponse(
            target, media_type=attachment.mime_type, filename=attachment.original_name,
            headers={"Cache-Control": "private, no-store"},
        )


@router.post("/parcels/{parcel_id}/ready", response_model=ParcelView)
def mark_parcel_ready(
    request: Request,
    parcel_id: UUID,
    body: ParcelReadyCommand,
    current_user: UserContext = Depends(get_current_user_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    payload = body.model_dump(mode="json") | {"parcel_id": str(parcel_id)}
    with request.app.state.database.get_session() as session:
        replay = idempotency_replay(
            session, current_user, operation="parcel.ready", key=idempotency_key, payload=payload,
        )
        if replay:
            return parcel_view(scoped_parcel(session, current_user, replay.resource_id))
        record = scoped_parcel(session, current_user, parcel_id, lock=True)
        require_version(record.version, body.expected_version)
        assert_transition(record, "READY_FOR_PICKUP")
        before = {"status": record.status, "version": record.version}
        record.status = "READY_FOR_PICKUP"
        record.ready_for_pickup_at = utc_now()
        record.updated_by_id = current_user.account_id
        record.version += 1
        audit(
            session, current_user, request, event_type="ParcelReadyForPickup", action="transition",
            resource_type="Parcel", resource_id=record.id, building_id=record.building_id,
            before=before, after={"status": record.status, "version": record.version},
        )
        emit(
            session, current_user, request, event_type="ParcelReadyForPickup",
            resource_type="Parcel", resource_id=record.id,
            payload={"status": record.status},
        )
        remember_idempotency(
            session, current_user, operation="parcel.ready", key=idempotency_key,
            payload=payload, resource_type="Parcel", resource_id=record.id,
            response_status=200,
        )
        session.commit()
        return parcel_view(record)


@router.post("/parcels/{parcel_id}/handover", response_model=ParcelView)
def handover_parcel(
    request: Request,
    parcel_id: UUID,
    body: ParcelHandoverCommand,
    current_user: UserContext = Depends(get_current_user_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    payload = body.model_dump(mode="json") | {"parcel_id": str(parcel_id)}
    with request.app.state.database.get_session() as session:
        replay = idempotency_replay(
            session, current_user, operation="parcel.handover", key=idempotency_key, payload=payload,
        )
        if replay:
            return parcel_view(scoped_parcel(session, current_user, replay.resource_id))
        record = scoped_parcel(session, current_user, parcel_id, lock=True)
        require_version(record.version, body.expected_version)
        assert_transition(record, "HANDED_OVER")
        now = utc_now()
        verify_handover_pin(record, body.pin, now)
        if not verify_password(body.pin, record.pin_hash):
            before = {"status": record.status, "pin_attempt_count": record.pin_attempt_count}
            record.pin_attempt_count = min(record.pin_attempt_count + 1, PIN_ATTEMPT_COUNTER_MAX)
            locked = record.pin_attempt_count >= PIN_MAX_ATTEMPTS
            if locked:
                record.pin_locked_until = now + PIN_LOCK_DURATION
            record.updated_by_id = current_user.account_id
            record.version += 1
            audit(
                session, current_user, request, event_type="ParcelPinFailed", action="verify_pin",
                resource_type="Parcel", resource_id=record.id, building_id=record.building_id,
                before=before,
                after={"pin_attempt_count": record.pin_attempt_count,
                       "pin_locked": locked},
                reason="invalid parcel PIN",
            )
            session.commit()
            if locked:
                raise AppError("ERR-PIN-LOCKED", "PIN tạm thời bị khóa. Hãy thử lại sau.", 423)
            raise AppError("ERR-PIN-INVALID", "PIN không chính xác.", 403)

        before = {"status": record.status, "version": record.version}
        record.status = "HANDED_OVER"
        record.handed_over_at = now
        record.handed_over_by_id = current_user.account_id
        record.pin_locked_until = None
        record.updated_by_id = current_user.account_id
        record.version += 1
        audit(
            session, current_user, request, event_type="ParcelHandedOver", action="handover",
            resource_type="Parcel", resource_id=record.id, building_id=record.building_id,
            before=before,
            after={"status": record.status, "version": record.version},
        )
        emit(
            session, current_user, request, event_type="ParcelHandedOver",
            resource_type="Parcel", resource_id=record.id,
            payload={"status": record.status},
        )
        remember_idempotency(
            session, current_user, operation="parcel.handover", key=idempotency_key,
            payload=payload, resource_type="Parcel", resource_id=record.id,
            response_status=200,
        )
        session.commit()
        return parcel_view(record)


@router.post("/parcels/{parcel_id}/exception", response_model=ParcelView)
def record_parcel_exception(
    request: Request,
    parcel_id: UUID,
    body: ParcelExceptionCommand,
    current_user: UserContext = Depends(get_current_user_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    payload = body.model_dump(mode="json") | {"parcel_id": str(parcel_id)}
    with request.app.state.database.get_session() as session:
        replay = idempotency_replay(
            session, current_user, operation="parcel.exception", key=idempotency_key, payload=payload,
        )
        if replay:
            return parcel_view(scoped_parcel(session, current_user, replay.resource_id))
        record = scoped_parcel(session, current_user, parcel_id, lock=True)
        require_version(record.version, body.expected_version)
        assert_transition(record, body.status)
        before = {"status": record.status, "version": record.version}
        record.status = body.status
        record.exception_reason = body.reason
        record.updated_by_id = current_user.account_id
        record.version += 1
        audit(
            session, current_user, request, event_type="ParcelExceptionRecorded", action="transition",
            resource_type="Parcel", resource_id=record.id, building_id=record.building_id,
            before=before, after={"status": record.status, "version": record.version},
            reason=record.exception_reason,
        )
        emit(
            session, current_user, request, event_type="ParcelExceptionRecorded",
            resource_type="Parcel", resource_id=record.id,
            payload={"status": record.status},
        )
        remember_idempotency(
            session, current_user, operation="parcel.exception", key=idempotency_key,
            payload=payload, resource_type="Parcel", resource_id=record.id,
            response_status=200,
        )
        session.commit()
        return parcel_view(record)
