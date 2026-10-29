import hashlib
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import FileResponse
from sqlalchemy import and_, or_, select

from app.core.exceptions import AppError
from app.core.policy import UserContext, get_current_user_context, scope_not_found
from app.core.security import create_token, decode_token
from app.models.resident_portal import PortalDossier, ResidentDocument, PortalContent
from app.schemas.resident_portal import ContentInput, PortalAction
from app.services.r2 import MAX_EVIDENCE_BYTES, validate_image_evidence, ImageEvidenceError, require_version, utc_now
from app.services.private_storage import verified_private_path, write_private_bytes
from app.services.resident_portal import MANAGERS, command, resident, scope_values, scoped, staff_conditions, unit_for, view

router = APIRouter(prefix="/portal", tags=["Resident documents and content"])


def _document_conditions(context, unit_id=None):
    conditions = list(context.scope_conditions(ResidentDocument))
    if resident(context):
        if unit_id is None or unit_id not in context.resident_units_for("documents"):
            raise scope_not_found()
        from app.models.unit import Unit
        conditions.extend((
            or_(ResidentDocument.unit_id == unit_id, ResidentDocument.unit_id.is_(None)),
            or_(ResidentDocument.building_id.is_(None), ResidentDocument.building_id.in_(
                select(Unit.building_id).where(Unit.id == unit_id))),
            or_(ResidentDocument.account_id == context.account_id, ResidentDocument.published.is_(True), *(
                and_(ResidentDocument.unit_id == uid, ResidentDocument.account_id == grantor)
                for uid, grantor, permissions in context.resident_delegation_grantors if "documents" in permissions)),
        ))
    else:
        conditions.extend(staff_conditions(context, ResidentDocument, MANAGERS))
        if unit_id:
            conditions.append(ResidentDocument.unit_id == unit_id)
    return conditions


def _document(session, context, identifier, *, unit_id=None, lock=False):
    statement = select(ResidentDocument).where(ResidentDocument.id == identifier,
        *_document_conditions(context, unit_id), ResidentDocument.revoked_at.is_(None))
    if lock:
        statement = statement.with_for_update()
    row = session.scalar(statement)
    if row is None:
        raise scope_not_found()
    return row


@router.get("/documents")
def documents(request: Request, unit_id: UUID | None = None, context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        if unit_id:
            unit_for(session, context, unit_id, "documents")
        return {"items": [view(row) for row in session.scalars(select(ResidentDocument).where(
            *_document_conditions(context, unit_id), ResidentDocument.revoked_at.is_(None))
            .order_by(ResidentDocument.created_at.desc()).limit(200))]}


def validate_portal_file(content, mime):
    if mime in {"image/png", "image/jpeg"}:
        try:
            return validate_image_evidence(content, mime)
        except ImageEvidenceError:
            raise AppError("ERR-FILE-TYPE", "Ảnh không hợp lệ.", 422) from None
    if (mime == "application/pdf" and content.startswith(b"%PDF-")
            and b"%%EOF" in content[-1024:] and not any(marker in content for marker in
                (b"/JavaScript", b"/JS", b"/Launch", b"/EmbeddedFile", b"/OpenAction"))):
        return mime
    raise AppError("ERR-FILE-TYPE", "Chỉ nhận PDF, PNG hoặc JPEG hợp lệ.", 422)


@router.post("/documents", status_code=201)
async def upload_document(request: Request, unit_id: UUID | None = None,
        building_id: UUID | None = None, dossier_id: UUID | None = None,
        replaces_id: UUID | None = None, title: str = "Tài liệu",
        context: UserContext = Depends(get_current_user_context),
        filename: str = Header(..., alias="X-File-Name"), key: str = Header(..., alias="Idempotency-Key")):
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > MAX_EVIDENCE_BYTES:
            raise AppError("ERR-FILE-SIZE", "Tài liệu vượt giới hạn 10 MB.", 413)
    if not content or not 1 <= len(title.strip()) <= 200:
        raise AppError("ERR-FILE-SIZE", "Tài liệu hoặc tiêu đề không hợp lệ.", 422)
    mime = validate_portal_file(bytes(content), request.headers.get("content-type", "").split(";")[0])
    from urllib.parse import unquote
    filename = Path(unquote(filename).replace("\\", "/")).name
    if not filename or len(filename) > 255:
        raise AppError("ERR-FILE-NAME", "Tên tài liệu không hợp lệ.", 422)
    digest = hashlib.sha256(content).hexdigest()
    written = []
    def execute(session):
        unit = unit_for(session, context, unit_id, "documents") if unit_id else None
        if resident(context) and unit is None:
            raise scope_not_found()
        if not resident(context) and unit is None:
            if building_id:
                context.assert_building_role(building_id, *MANAGERS)
            else:
                context.assert_role("admin", "director")
        values = scope_values(context, unit, building_id=building_id)
        if dossier_id:
            parent = scoped(session, context, PortalDossier, dossier_id, lock=True)
            if parent.unit_id != unit_id or parent.status not in {"SUBMITTED", "WAITING_INFO"}:
                raise AppError("ERR-DOSSIER-EVIDENCE", "Chỉ bổ sung minh chứng cho hồ sơ đang tiếp nhận.", 409)
            values["account_id"] = parent.account_id
        version = 1
        if replaces_id:
            old = _document(session, context, replaces_id, unit_id=unit_id, lock=True)
            if old.unit_id != unit_id or old.dossier_id != dossier_id or old.account_id != values["account_id"]:
                raise scope_not_found()
            if session.scalar(select(ResidentDocument.id).where(ResidentDocument.replaces_id == old.id).limit(1)):
                raise AppError("ERR-CONFLICT", "Tài liệu đã có phiên bản mới.", 409)
            version = old.content_version + 1
        identifier = uuid4()
        storage_key = f"portal/{context.tenant_id}/{context.assert_active_site()}/{identifier.hex}"
        path = write_private_bytes(request.app.state.settings.private_storage_path, storage_key, bytes(content))
        written.append((identifier, path))
        row = ResidentDocument(id=identifier, **values, dossier_id=dossier_id, replaces_id=replaces_id,
            content_version=version, title=title.strip(), original_name=filename, storage_key=storage_key,
            mime_type=mime, size_bytes=len(content), sha256=digest)
        session.add(row)
        return row, "documents"
    try:
        return command(request, context, key, "document.upload", {"unit_id": str(unit_id) if unit_id else None,
            "building_id": str(building_id) if building_id else None, "dossier_id": str(dossier_id) if dossier_id else None,
            "replaces_id": str(replaces_id) if replaces_id else None, "title": title, "filename": filename,
            "sha256": digest, "mime": mime}, execute)
    except Exception:
        # A lost commit response can still mean success. Remove only files whose
        # manifest is confirmed absent after the command session has rolled back.
        for identifier, path in written:
            try:
                with request.app.state.database.get_session() as session:
                    if session.get(ResidentDocument, identifier) is None:
                        path.unlink(missing_ok=True)
            except Exception:
                pass  # Preserve the file if DB availability leaves commit uncertain.
        raise


@router.get("/documents/{identifier}/signed-link")
def document_link(identifier: UUID, request: Request, unit_id: UUID | None = None,
                  context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        row = _document(session, context, identifier, unit_id=unit_id)
        if row.quarantined or row.archived_at:
            raise AppError("ERR-FILE-QUARANTINED", "Tài liệu đang bị chặn.", 423)
        token = create_token({"purpose": "portal-document-download", "sub": str(context.account_id),
            "tenant_id": str(context.tenant_id), "active_site_id": str(context.assert_active_site()),
            "document_id": str(row.id)}, request.app.state.settings.auth_secret(),
            expires_in_seconds=request.app.state.settings.attachment_link_ttl_seconds)
        return {"url": f"/api/v1/portal/documents/{row.id}/download", "token": token,
                "unit_id": unit_id, "expires_in_seconds": request.app.state.settings.attachment_link_ttl_seconds}


@router.get("/documents/{identifier}/download")
def download_document(identifier: UUID, request: Request, token: str, unit_id: UUID | None = None,
                      context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        row = _document(session, context, identifier, unit_id=unit_id)
        claims = decode_token(token, request.app.state.settings.auth_secret(), expired_code="ERR-LINK-EXPIRED",
                              expired_message="Liên kết tài liệu đã hết hạn.", expired_status=410)
        expected = {"purpose": "portal-document-download", "sub": str(context.account_id),
            "tenant_id": str(context.tenant_id), "active_site_id": str(context.assert_active_site()), "document_id": str(row.id)}
        if row.quarantined or row.archived_at or any(claims.get(k) != v for k, v in expected.items()):
            raise scope_not_found()
        path = verified_private_path(request.app.state.settings.private_storage_path, row.storage_key, row.sha256, row.size_bytes)
        if path is None:
            raise AppError("ERR-FILE-INTEGRITY", "Tài liệu không còn khả dụng.", 409)
        return FileResponse(path, media_type=row.mime_type, filename=row.original_name,
            headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/documents/{identifier}/actions")
def document_action(identifier: UUID, body: PortalAction, request: Request,
                    context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias="Idempotency-Key")):
    def execute(session):
        context.assert_role(*MANAGERS)
        row = _document(session, context, identifier, lock=True)
        require_version(row.version, body.expected_version)
        if body.action == "PUBLISH" and not row.quarantined:
            row.published = True
        elif body.action == "WITHDRAW":
            row.published = False
        elif body.action == "REVOKE":
            row.revoked_at = utc_now(); row.published = False
        elif body.action == 'VERIFY':
            if row.quarantined or row.account_id == context.account_id:
                raise AppError('ERR-INDEPENDENT-CHECKER', 'Cần người xác minh độc lập và tài liệu không bị chặn.', 403)
            from datetime import date
            try:
                row.expires_on = date.fromisoformat(body.data['expires_on']) if body.data.get('expires_on') else None
                row.retain_until = date.fromisoformat(body.data['retain_until']) if body.data.get('retain_until') else None
                if row.retain_until and row.expires_on and row.retain_until < row.expires_on:
                    raise ValueError()
            except (ValueError, TypeError):
                raise AppError('ERR-DOCUMENT-DATE', 'Thời hạn tài liệu không hợp lệ.', 422) from None
            row.verification_status = 'VERIFIED'; row.verified_by_id = context.account_id
        elif body.action == 'INCOMPLETE':
            row.verification_status = 'INCOMPLETE'; row.verified_by_id = context.account_id
        elif body.action == 'ARCHIVE':
            if not row.retain_until or row.retain_until > utc_now().date():
                raise AppError('ERR-RETENTION-POLICY', 'Chưa đến thời hạn kết thúc lưu giữ đã xác nhận.', 409)
            row.archived_at = utc_now(); row.published = False
        else:
            raise AppError("ERR-STATE-TRANSITION", "Thao tác tài liệu không hợp lệ.", 409)
        row.version += 1
        from app.services.operational_control import event
        event(session, context, row, body.action, body.reason)
        return row, "documents"
    return command(request, context, key, f"document.{body.action.lower()}", {"id": str(identifier), **body.model_dump(mode="json")}, execute)


@router.get("/content")
def content_list(request: Request, unit_id: UUID | None = None, context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        conditions = list(context.scope_conditions(PortalContent))
        if resident(context):
            unit = unit_for(session, context, unit_id, "documents") if unit_id else None
            if unit is None:
                raise scope_not_found()
            conditions.extend((PortalContent.status.in_(("PUBLISHED", "CLOSED", "WITHDRAWN")), PortalContent.publish_at <= utc_now(),
                or_(PortalContent.building_id.is_(None), PortalContent.building_id == unit.building_id),
                or_(PortalContent.unit_id.is_(None), PortalContent.unit_id == unit.id)))
        else:
            conditions.extend(staff_conditions(context, PortalContent))
        return {"items": [view(row) for row in session.scalars(select(PortalContent).where(*conditions)
            .order_by(PortalContent.publish_at.desc()).limit(200))]}


@router.post("/content", status_code=201)
def create_content(body: ContentInput, request: Request, context: UserContext = Depends(get_current_user_context),
                   key: str = Header(..., alias="Idempotency-Key")):
    def execute(session):
        unit = unit_for(session, context, body.unit_id) if body.unit_id else None
        context.assert_role(*MANAGERS)
        if unit is None:
            if body.building_id:
                context.assert_building_role(body.building_id, *MANAGERS)
            else:
                context.assert_role("admin", "director")
        if unit and body.building_id and unit.building_id != body.building_id:
            raise scope_not_found()
        if body.document_id:
            doc = _document(session, context, body.document_id)
            if (not doc.published or doc.revoked_at or doc.quarantined
                    or (doc.building_id and doc.building_id != (unit.building_id if unit else body.building_id))
                    or (doc.unit_id and doc.unit_id != (unit.id if unit else None))):
                raise AppError("ERR-DOCUMENT-AUDIENCE", "Tài liệu cần công bố cho đúng đối tượng trước.", 409)
        row = PortalContent(**scope_values(context, unit, building_id=body.building_id),
                            **body.model_dump(exclude={"unit_id", "building_id"}))
        session.add(row)
        return row, "documents"
    return command(request, context, key, "content.create", body.model_dump(mode="json"), execute)


@router.post("/content/{identifier}/actions")
def content_action(identifier: UUID, body: PortalAction, request: Request,
                   context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias="Idempotency-Key")):
    def execute(session):
        context.assert_role(*MANAGERS)
        row = scoped(session, context, PortalContent, identifier, lock=True)
        require_version(row.version, body.expected_version)
        if body.action == 'SUBMIT' and row.status in {'DRAFT', 'REJECTED'}:
            row.status = 'SUBMITTED'
        elif body.action in {'APPROVE', 'REJECT'} and row.status == 'SUBMITTED':
            from app.services.operational_control import independent
            independent(context, row)
            if row.kind == 'VOTE' and not row.policy.get('confirmed_rule_reference'):
                raise AppError('ERR-POLICY-INCOMPLETE', 'Cần xác nhận quy trình biểu quyết trước khi duyệt.', 409)
            row.status = 'APPROVED' if body.action == 'APPROVE' else 'REJECTED'
            row.approved_by_id = context.account_id if body.action == 'APPROVE' else None
        elif body.action == "PUBLISH" and row.status == "APPROVED":
            from app.models.account import Account
            from app.core.policy import context_for_account
            from app.services.operational_control import independent
            checker = session.get(Account, row.approved_by_id)
            if not checker or not checker.is_active:
                raise AppError('ERR-APPROVAL-STALE', 'Người duyệt không còn hoạt động.', 409)
            independent(context_for_account(session, checker, row.site_id), row)
            row.status = "PUBLISHED"
            if row.previous_id and row.publish_at <= utc_now():
                previous = session.scalar(select(PortalContent).where(PortalContent.id == row.previous_id).with_for_update())
                previous.status = 'WITHDRAWN'; previous.version += 1
                from app.services.operational_control import event
                event(session, context, previous, 'REPLACED', row.change_reason)
        elif body.action == 'CLOSE' and row.status == 'PUBLISHED':
            if row.kind == 'MEETING':
                from app.models.sad_completion import CommunityTask
                if not row.minutes or session.scalar(select(CommunityTask.id).where(CommunityTask.content_id == row.id, CommunityTask.status.in_(('OPEN','IN_PROGRESS'))).limit(1)):
                    raise AppError('ERR-MEETING-OPEN-DECISIONS', 'Cần biên bản và xử lý đủ các quyết định trước khi kết thúc.', 409)
            row.status = 'CLOSED'
        elif body.action == "WITHDRAW" and row.status == "PUBLISHED":
            row.status = "WITHDRAWN"
            row.change_reason = body.reason
            from app.services.sad_completion import notify_content_change
            notify_content_change(session,context,request,row,'Nội dung đã rút: '+body.reason)
        else:
            raise AppError("ERR-STATE-TRANSITION", "Nội dung cần tạo bản mới nếu đã công bố.", 409)
        row.version += 1
        from app.services.operational_control import event
        event(session, context, row, body.action, body.reason)
        return row, "documents"
    return command(request, context, key, f"content.{body.action.lower()}", {"id": str(identifier), **body.model_dump(mode="json")}, execute)
