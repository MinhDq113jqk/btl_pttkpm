"""Resident and management workflows; all unit IDs are re-authorized server-side."""
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy import func, or_, select, update

from app.core.exceptions import AppError
from app.core.policy import UserContext, get_current_user_context, scope_not_found
from app.models.account import Account, AccountRole
from app.models.person import Person, UnitPersonRelationship
from app.models.service import CaseRecord, ServiceRequest, WorkOrder
from app.models.resident_portal import (PortalDossier, PortalDossierEvent, ResidentDelegation,
    LiabilityEpisode, PortalResource, PortalFeeSource, PortalFeePosting, PortalDeposit,
    PortalDepositMovement, VehicleRegistration, ResidentCredential, FacilityBooking,
    ServiceEnrollment, PortalRequestMessage, ResidentDocument, PortalContent, PortalPaymentIntent)
from app.schemas.resident_portal import DossierCreate, PortalAction, ResourceInput, DepositAction
from app.services.r2 import audit, require_version, utc_now
from app.services.resident_portal import (FINANCE, MANAGERS, PORTAL_STAFF, command, deposit_movement,
    resident, scope_values, scoped, staff_conditions, unit_for, validate_resource_policy, view,
    visible_conditions, require_transition)
from app.services.outbox import enqueue_notification
from app.schemas.property import validate_property_data
from app.services.property import PROPERTY_KINDS, apply_property
from app.services.portal_finance import business_date

router = APIRouter(prefix="/portal", tags=["Resident portal"])


@router.post("/jobs/tick")
def portal_jobs(request: Request, context: UserContext = Depends(get_current_user_context)):
    from app.services.portal_jobs import tick
    with request.app.state.database.get_session() as session:
        result = tick(session, context, request)
        from app.api.portal_control import run_due_schedules
        result.update(run_due_schedules(session, context, request))
        session.commit()
        return result


@router.get("/options")
def portal_options(request: Request, context: UserContext = Depends(get_current_user_context)):
    context.assert_role(*PORTAL_STAFF)
    from app.models.building import Building
    from app.models.unit import Unit
    with request.app.state.database.get_session() as session:
        grants = [g for g in context.role_grants if g.role in PORTAL_STAFF
                  and (g.building_id is not None or g.role in {"admin", "director", "accountant"})]
        conditions = or_(*[(Building.id == g.building_id if g.building_id is not None else True) for g in grants]) if grants else False
        buildings = session.scalars(select(Building).where(Building.site_id == context.assert_active_site(), conditions).order_by(Building.code)).all()
        units = session.scalars(select(Unit).where(Unit.building_id.in_([b.id for b in buildings])).order_by(Unit.unit_number)).all()
        return {"buildings": [{"id": b.id, "name": b.name} for b in buildings],
                "units": [{"id": u.id, "unit_number": u.unit_number, "building_id": u.building_id} for u in units]}


def _notify(session, context, request, row, title, body):
    enqueue_notification(session, context, request, event_type="ResidentPortalUpdated",
        resource_type=row.__class__.__name__, resource_id=row.id, recipient_account_id=row.account_id,
        template_code="PORTAL_UPDATE", template_snapshot={"title": title, "body": body,
            "unit_id": str(row.unit_id) if row.unit_id else None, "resource_id": str(row.id)})


@router.get("/profile")
def profile(request: Request, unit_id: UUID | None = None,
            context: UserContext = Depends(get_current_user_context)):
    context.assert_role("resident")
    with request.app.state.database.get_session() as session:
        person = session.scalar(select(Person).where(Person.id == context.resident_person_id,
                                                      Person.tenant_id == context.tenant_id))
        if person is None:
            raise scope_not_found()
        unit_ids = tuple(dict.fromkeys((*context.resident_unit_ids,
                         *(identifier for identifier, _ in context.resident_delegations))))
        units = []
        from app.models.unit import Unit
        from app.models.building import Building
        for unit, building in session.execute(select(Unit, Building).join(Building, Building.id == Unit.building_id)
                .where(Unit.id.in_(unit_ids), Building.site_id == context.assert_active_site()).order_by(Unit.unit_number)):
            delegated = next((list(p) for identifier, p in context.resident_delegations if identifier == unit.id), [])
            units.append({"id": unit.id, "unit_number": unit.unit_number, "building_id": building.id,
                "building_name": building.name, "area_m2": unit.area_m2,
                "permissions": ["profile", "documents", "requests", "parking", "booking", "finance"]
                    if unit.id in context.resident_unit_ids else delegated})
        selected = unit_id or (units[0]["id"] if units else None)
        if selected is not None and selected not in unit_ids:
            raise scope_not_found()
        facts = []
        history = []
        presence = None
        liability = None
        if selected in context.resident_unit_ids:
            from app.services.property import person_family
            family = person_family(session, context.tenant_id, person.id)
            relationships = session.scalars(select(UnitPersonRelationship).where(
                UnitPersonRelationship.person_id.in_(family),
                UnitPersonRelationship.unit_id == selected,
                UnitPersonRelationship.tenant_id == context.tenant_id)
                .order_by(UnitPersonRelationship.valid_from.desc())).all()
            history = [dict(relationship_type=r.relationship_type, valid_from=r.valid_from,
                            valid_to=r.valid_to, ownership_ratio=r.ownership_ratio) for r in relationships]
            facts = [dict(relationship_type=r.relationship_type, valid_from=r.valid_from,
                          valid_to=r.valid_to, ownership_ratio=r.ownership_ratio)
                     for r in relationships if r.valid_from <= date.today() and (r.valid_to is None or r.valid_to > date.today())]
            for dossier in session.scalars(select(PortalDossier).where(
                    *context.scope_conditions(PortalDossier), PortalDossier.unit_id == selected,
                    PortalDossier.person_id.in_(family), PortalDossier.status.in_(("APPROVED", "COMPLETED")),
                    PortalDossier.kind.in_(("ABSENCE", "RETURN", "MOVE_OUT")),
                    PortalDossier.valid_from <= date.today(),
                    or_(PortalDossier.valid_to.is_(None), PortalDossier.valid_to > date.today()))
                    .order_by(PortalDossier.valid_from.desc(), PortalDossier.created_at.desc())):
                if str(dossier.data.get("target_person_id", dossier.person_id)) in {str(p) for p in family}:
                    presence = {"status": dossier.kind, "valid_from": dossier.valid_from, "valid_to": dossier.valid_to}
                    break
            episode = session.scalar(select(LiabilityEpisode).where(
                *context.scope_conditions(LiabilityEpisode), LiabilityEpisode.unit_id == selected,
                LiabilityEpisode.valid_from <= date.today(),
                or_(LiabilityEpisode.valid_to.is_(None), LiabilityEpisode.valid_to > date.today()))
                .order_by(LiabilityEpisode.valid_from.desc()).limit(1))
            if episode:
                liability = {"person_id": episode.person_id, "is_self": episode.person_id in family,
                             "valid_from": episode.valid_from, "valid_to": episode.valid_to}
        return {"person": {"id": person.id, "full_name": person.full_name,
            "phone_masked": person.phone_masked, "email_masked": person.email_masked},
            "units": units, "selected_unit_id": selected, "relationships": facts,
            "relationship_history": history, "presence": presence, "liability": liability}


@router.get("/dossiers")
def dossiers(request: Request, unit_id: UUID | None = None, status: str | None = None,
             context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        roles = (*MANAGERS, "accountant")
        conditions = list(visible_conditions(context, PortalDossier, roles=roles))
        if not resident(context) and not any(r in MANAGERS for r in context.roles):
            conditions.append(PortalDossier.kind.in_(("RENOVATION", "LIABILITY_CHANGE")))
        if unit_id:
            unit_for(session, context, unit_id, roles=roles)
            conditions.append(PortalDossier.unit_id == unit_id)
        if status:
            conditions.append(PortalDossier.status == status)
        rows = session.scalars(select(PortalDossier).where(*conditions)
                              .order_by(PortalDossier.created_at.desc()).limit(200)).all()
        return {"items": [view(row) for row in rows]}


@router.get("/dossiers/{identifier}")
def dossier_detail(identifier: UUID, request: Request, context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        row = scoped(session, context, PortalDossier, identifier, roles=(*MANAGERS,*FINANCE))
        events = session.scalars(select(PortalDossierEvent).where(PortalDossierEvent.dossier_id == row.id)
                                .order_by(PortalDossierEvent.created_at, PortalDossierEvent.id)).all()
        return {**view(row), "history": [view(event) for event in events]}


def _validate_dossier_data(kind, data):
    import json
    if kind in PROPERTY_KINDS:
        return validate_property_data(kind, data)
    fields = {
        "PROFILE_CHANGE": {"full_name", "phone", "email", "phone_masked", "email_masked"},
        "MOVE_IN": {"target_person_id", "target_username", "relationship_type", "full_name", "phone_masked", "email_masked"},
        "MOVE_OUT": {"target_person_id"}, "ABSENCE": {"target_person_id"}, "RETURN": {"target_person_id"},
        "LEASE": {"target_person_id", "target_username", "liable_person_id", "contract_reference"},
        "DELEGATION": {"delegate_person_id", "delegate_username", "permissions"},
        "TRANSFER": {"target_person_id", "target_username", "ownership_ratio"},
        "RENOVATION": {"description", "contractor", "deposit_vnd", "work_start", "work_end"},
    }
    if set(data) - fields[kind] or len(json.dumps(data)) > 16000:
        raise AppError("ERR-DOSSIER-DATA", "Thông tin hồ sơ không hợp lệ.", 422)
    if kind == "PROFILE_CHANGE":
        if not data or any(not isinstance(v, str) or not v.strip() for v in data.values()):
            raise AppError("ERR-DOSSIER-DATA", "Cần nhập trường đề nghị cập nhật.", 422)
        limits = {"full_name": 200, "phone": 30, "email": 254, "phone_masked": 50, "email_masked": 100}
        if any(len(v) > limits[k] for k, v in data.items()):
            raise AppError("ERR-DOSSIER-DATA", "Thông tin vượt độ dài cho phép.", 422)
        import re
        if "phone" in data and not re.fullmatch(r"\+?[0-9 ()-]{8,30}", data["phone"]):
            raise AppError("ERR-DOSSIER-DATA", "Số điện thoại không hợp lệ.", 422)
        if "email" in data and not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", data["email"]):
            raise AppError("ERR-DOSSIER-DATA", "Email không hợp lệ.", 422)
    if kind == "DELEGATION":
        permissions = data.get("permissions")
        if (not isinstance(permissions, list) or not permissions
                or any(not isinstance(p, str) for p in permissions)
                or not set(permissions) <= {"profile", "documents", "requests", "parking", "booking"}):
            raise AppError("ERR-DOSSIER-DATA", "Phạm vi ủy quyền không hợp lệ.", 422)
    for field in ("full_name", "phone_masked", "email_masked", "contract_reference", "description", "contractor", "target_username", "delegate_username"):
        if field in data and (not isinstance(data[field], str) or not data[field].strip()
                or len(data[field]) > {"full_name": 200, "phone_masked": 50, "email_masked": 100,
                    "contract_reference": 150, "target_username": 100, "delegate_username": 100}.get(field, 4000)):
            raise AppError("ERR-DOSSIER-DATA", f"Trường {field} không hợp lệ.", 422)
    if kind == "TRANSFER":
        try:
            ratio = Decimal(str(data.get("ownership_ratio", 0)))
            valid = ratio.is_finite() and 0 < ratio <= 1 and ratio == ratio.quantize(Decimal("0.0001"))
        except (InvalidOperation, ValueError):
            valid = False
        if not valid:
            raise AppError("ERR-OWNERSHIP", "Tỷ lệ chuyển nhượng cần nằm trong (0, 1], tối đa 4 số lẻ.", 422)
    return data


@router.post("/dossiers", status_code=201)
def create_dossier(body: DossierCreate, request: Request,
                   context: UserContext = Depends(get_current_user_context),
                   key: str = Header(..., alias="Idempotency-Key")):
    def execute(session):
        owner_only = body.kind in {"MOVE_IN", "LEASE", "LEASE_RENEW", "LEASE_AMEND", "LEASE_TERMINATE", "DELEGATION", "TRANSFER", "RENOVATION", "UNIT_PROFILE", "UNIT_STATUS", "LIABILITY_CHANGE"}
        unit = unit_for(session, context, body.unit_id, roles=(*MANAGERS,*FINANCE), owner=owner_only)
        if body.kind in {'LEASE','LEASE_RENEW','LEASE_AMEND','MOVE_IN'}:
            from app.services.property import renovation_permission
            renovation_permission(session,unit,'LEASE' if body.kind.startswith('LEASE') else 'MOVE_IN')
        if resident(context):
            if context.resident_person_id is None or body.person_id not in (None,context.resident_person_id):
                raise scope_not_found()
            if body.kind in {'HANDOVER','PERSON_MERGE'}:
                raise AppError('ERR-FORBIDDEN','Loại hồ sơ này do BQL lập.',403)
            person_id = context.resident_person_id
        else:
            if body.kind == 'LIABILITY_CHANGE': context.assert_role(*FINANCE)
            else: context.assert_role(*MANAGERS)
            person_id = _subject_person(session, context, body.person_id).id
        data = _validate_dossier_data(body.kind, body.data)
        if body.kind in {"DELEGATION", "LEASE", "LEASE_RENEW", "LEASE_AMEND", "RENOVATION"} and body.valid_to is None:
            raise AppError("ERR-DOSSIER-INTERVAL", "Loại hồ sơ này cần ngày kết thúc.", 422)
        if body.kind == "TRANSFER" and body.valid_to is not None:
            raise AppError("ERR-DOSSIER-INTERVAL", "Chuyển nhượng là thay đổi sở hữu không có ngày hết hạn.", 422)
        row = PortalDossier(**scope_values(context, unit), person_id=person_id,
            kind=body.kind, title=body.title, data=data, valid_from=body.valid_from, valid_to=body.valid_to)
        session.add(row); session.flush()
        session.add(PortalDossierEvent(dossier_id=row.id, actor_id=context.account_id,
                    action="SUBMIT", message=body.title, snapshot={"status": "SUBMITTED", "data": body.data}))
        return row, "profile"
    return command(request, context, key, "dossier.create", body.model_dump(mode="json"), execute, roles=(*MANAGERS,*FINANCE))


def _subject_person(session, context, value):
    try:
        identifier = UUID(str(value))
    except (ValueError, TypeError):
        accounts = session.scalars(select(Account).where(Account.username == str(value),
            Account.tenant_id == context.tenant_id, Account.person_id.is_not(None))).all()
        if len(accounts) != 1:
            raise AppError("ERR-DOSSIER-DATA", "Không xác định được người trong hồ sơ.", 422) from None
        identifier = accounts[0].person_id
    person = session.scalar(select(Person).where(Person.id == identifier, Person.tenant_id == context.tenant_id))
    if person is None:
        raise scope_not_found()
    return person


def _end_relationships(session, row, person_id, *, owners=False):
    rels = session.scalars(select(UnitPersonRelationship).where(
        UnitPersonRelationship.unit_id == row.unit_id, UnitPersonRelationship.tenant_id == row.tenant_id,
        *((UnitPersonRelationship.relationship_type == "owner",) if owners else (UnitPersonRelationship.person_id == person_id, UnitPersonRelationship.relationship_type != "owner")),
        UnitPersonRelationship.valid_from < row.valid_from,
        or_(UnitPersonRelationship.valid_to.is_(None), UnitPersonRelationship.valid_to > row.valid_from),
    ).with_for_update()).all()
    if not rels:
        raise AppError("ERR-RELATIONSHIP-INTERVAL", "Không có quan hệ có thể kết thúc tại ngày đề nghị.", 409)
    for rel in rels:
        rel.valid_to = row.valid_from


def _apply_dossier(session, context, row):
    data = row.data
    _validate_dossier_data(row.kind, data)
    # Unit lock serializes interval/ownership changes, including concurrent approvals.
    unit = unit_for(session, context, row.unit_id, roles=(*MANAGERS,*FINANCE))
    if row.kind in {'LEASE','LEASE_RENEW','LEASE_AMEND','MOVE_IN'}:
        from app.services.property import renovation_permission
        renovation_permission(session,unit,'LEASE' if row.kind.startswith('LEASE') else 'MOVE_IN')
    if row.kind in {"MOVE_IN", "LEASE", "LEASE_RENEW", "LEASE_AMEND", "LEASE_TERMINATE", "DELEGATION", "TRANSFER", "RENOVATION", "UNIT_PROFILE", "UNIT_STATUS", "LIABILITY_CHANGE"}:
        from app.services.property import person_family
        owner = session.scalar(select(UnitPersonRelationship.id).where(
            UnitPersonRelationship.unit_id == row.unit_id, UnitPersonRelationship.person_id.in_(person_family(session, row.tenant_id, row.person_id)),
            UnitPersonRelationship.relationship_type == "owner", UnitPersonRelationship.valid_from <= row.valid_from,
            or_(UnitPersonRelationship.valid_to.is_(None), UnitPersonRelationship.valid_to > row.valid_from)).limit(1))
        if owner is None:
            raise AppError("ERR-DOSSIER-ELIGIBILITY", "Người đề nghị không còn quyền chủ sở hữu tại ngày hiệu lực.", 409)
    if row.kind == "PROFILE_CHANGE":
        person = _subject_person(session, context, row.person_id)
        before = {field: getattr(person, field) for field in ('full_name','phone_masked','email_masked')}
        for field, value in data.items():
            if field == "phone":
                person.phone_masked = "***" + value[-4:]
            elif field == "email":
                local, domain = value.split("@", 1)
                person.email_masked = local[:1] + "***@" + domain[-90:]
            else:
                setattr(person, field, value)
        if "full_name" in data:
            session.execute(update(Account).where(Account.person_id == person.id,
                Account.tenant_id == row.tenant_id).values(full_name=data["full_name"]))
        session.add(PortalDossierEvent(dossier_id=row.id, actor_id=context.account_id, action='PROFILE_APPLIED',
            message='Lưu lịch sử thông tin người.', snapshot={'before':before,'after':{field:getattr(person,field) for field in before}}))
    elif row.kind in PROPERTY_KINDS:
        apply_property(session, context, row, unit)
    elif row.kind in {"MOVE_IN", "TRANSFER"}:
        target_value = data.get("target_person_id") or data.get("target_username")
        if row.kind == "MOVE_IN" and not target_value and data.get("full_name"):
            if not isinstance(data["full_name"], str) or not 3 <= len(data["full_name"].strip()) <= 200:
                raise AppError("ERR-DOSSIER-DATA", "Họ tên cư dân không hợp lệ.", 422)
            target = Person(tenant_id=row.tenant_id, full_name=data["full_name"].strip(),
                phone_masked=data.get("phone_masked", "Chưa xác minh"), email_masked=data.get("email_masked", "Chưa xác minh"))
            session.add(target); session.flush()
        else:
            target = _subject_person(session, context, target_value or row.person_id)
        relation = "owner" if row.kind == "TRANSFER" else "tenant" if row.kind == "LEASE" else data.get("relationship_type", "family_member")
        if relation not in {"owner", "tenant", "family_member"} or (relation == "owner" and row.kind != "TRANSFER"):
            raise AppError("ERR-DOSSIER-DATA", "Quan hệ đề nghị không được phép.", 422)
        ratio = None
        if relation == "owner":
            ratio = Decimal(str(data.get("ownership_ratio", "0")))
            if target.id == row.person_id:
                raise AppError("ERR-OWNERSHIP", "Người nhận phải khác người chuyển nhượng.", 422)
            owners = session.scalars(select(UnitPersonRelationship).where(
                UnitPersonRelationship.unit_id == row.unit_id, UnitPersonRelationship.relationship_type == "owner",
                or_(UnitPersonRelationship.valid_to.is_(None), UnitPersonRelationship.valid_to > row.valid_from))
                .with_for_update()).all()
            source = next((o for o in owners if o.person_id == row.person_id and o.valid_from < row.valid_from), None)
            if (source is None or source.ownership_ratio < ratio or source.valid_to is not None
                    or any(o.valid_from >= row.valid_from or o.valid_to is not None for o in owners)):
                raise AppError("ERR-OWNERSHIP", "Tỷ lệ/ngày chuyển nhượng xung đột với lịch sử sở hữu.", 409)
            existing_target = next((o for o in owners if o.person_id == target.id), None)
            source.valid_to = row.valid_from
            scope = dict(tenant_id=row.tenant_id, site_id=row.site_id, building_id=row.building_id, unit_id=row.unit_id, relationship_type="owner", valid_from=row.valid_from)
            if source.ownership_ratio > ratio:
                session.add(UnitPersonRelationship(**scope, person_id=row.person_id, ownership_ratio=source.ownership_ratio - ratio))
            if existing_target:
                existing_target.valid_to = row.valid_from
                ratio += existing_target.ownership_ratio
            session.flush()
        overlapping = session.scalar(select(UnitPersonRelationship.id).where(
            UnitPersonRelationship.unit_id == row.unit_id, UnitPersonRelationship.person_id == target.id,
            UnitPersonRelationship.relationship_type == relation,
            or_(UnitPersonRelationship.valid_to.is_(None), UnitPersonRelationship.valid_to > row.valid_from),
            *((UnitPersonRelationship.valid_from < row.valid_to,) if row.valid_to else ()),
        ).limit(1))
        if overlapping:
            raise AppError("ERR-RELATIONSHIP-OVERLAP", "Khoảng cư trú trùng quan hệ hiện có.", 409)
        session.add(UnitPersonRelationship(tenant_id=row.tenant_id, site_id=row.site_id,
            building_id=row.building_id, unit_id=row.unit_id, person_id=target.id,
            relationship_type=relation, ownership_ratio=ratio, valid_from=row.valid_from, valid_to=row.valid_to))
    elif row.kind in {"ABSENCE", "RETURN"}:
        # Presence changes preserve ownership/lease episodes and their billing history.
        relationship = session.scalar(select(UnitPersonRelationship.id).where(
            UnitPersonRelationship.unit_id == row.unit_id, UnitPersonRelationship.person_id == row.person_id,
            UnitPersonRelationship.valid_from <= row.valid_from,
            or_(UnitPersonRelationship.valid_to.is_(None), UnitPersonRelationship.valid_to > row.valid_from)).limit(1))
        if relationship is None:
            raise AppError("ERR-RELATIONSHIP-INTERVAL", "Cần quan hệ cư trú có hiệu lực tại ngày đề nghị.", 409)
    elif row.kind == "MOVE_OUT":
        target = _subject_person(session, context, data.get("target_person_id", row.person_id))
        # A resident may not propose removing another person without owner rights.
        owner = session.scalar(select(UnitPersonRelationship.id).where(
            UnitPersonRelationship.person_id == row.person_id, UnitPersonRelationship.unit_id == row.unit_id,
            UnitPersonRelationship.relationship_type == "owner",
            UnitPersonRelationship.valid_from <= row.valid_from,
            or_(UnitPersonRelationship.valid_to.is_(None), UnitPersonRelationship.valid_to > row.valid_from)))
        if target.id != row.person_id and owner is None:
            raise AppError("ERR-FORBIDDEN", "Không có quyền đề nghị kết thúc quan hệ người khác.", 403)
        if owner is None or target.id != row.person_id:
            _end_relationships(session, row, target.id)
    elif row.kind == "DELEGATION":
        target = _subject_person(session, context, data.get("delegate_person_id") or data.get("delegate_username"))
        if target.id == row.person_id:
            raise AppError("ERR-DOSSIER-DATA", "Người được ủy quyền phải khác người ủy quyền.", 422)
        session.add(ResidentDelegation(**scope_values(context, unit, account_id=row.account_id),
            dossier_id=row.id, delegate_person_id=target.id, permissions=data["permissions"],
            valid_from=row.valid_from, valid_to=row.valid_to))
        account = session.scalar(select(Account).where(Account.person_id == target.id, Account.tenant_id == row.tenant_id))
        if account is None:
            raise AppError("ERR-DELEGATE-ACCOUNT", "BQL cần tạo tài khoản cư dân cho người được ủy quyền trước.", 409)
        grant = session.scalar(select(AccountRole.id).where(AccountRole.account_id == account.id,
            AccountRole.site_id == row.site_id, AccountRole.role == "resident"))
        if not grant:
            session.add(AccountRole(account_id=account.id, site_id=row.site_id, building_id=None, role="resident"))
    elif row.kind == "RENOVATION":
        deposit = session.scalar(select(PortalDeposit).where(PortalDeposit.source_kind == "RENOVATION",
            PortalDeposit.source_id == row.id).with_for_update())
        if deposit is None:
            raise AppError("ERR-DEPOSIT-REQUIRED", "BQL cần thiết lập điều kiện cọc trước khi duyệt cải tạo.", 409)
        if deposit.balance_vnd - deposit.refundable_vnd < deposit.required_vnd:
            raise AppError("ERR-DEPOSIT-REQUIRED", "Hồ sơ chưa có đủ cọc thực nhận.", 409)


@router.post("/dossiers/{identifier}/actions")
def dossier_action(identifier: UUID, body: PortalAction, request: Request,
                   context: UserContext = Depends(get_current_user_context),
                   key: str = Header(..., alias="Idempotency-Key")):
    def execute(session):
        initial = scoped(session, context, PortalDossier, identifier, roles=(*MANAGERS,*FINANCE))
        unit = unit_for(session, context, initial.unit_id, roles=(*MANAGERS,*FINANCE))
        row = scoped(session, context, PortalDossier, identifier, lock=True, roles=(*MANAGERS,*FINANCE))
        require_version(row.version, body.expected_version)
        if not resident(context):
            context.assert_building_role(row.building_id, *(FINANCE if row.kind == 'LIABILITY_CHANGE' else MANAGERS))
        if resident(context) and body.action not in {"SUPPLEMENT", "CANCEL"}:
            raise AppError("ERR-FORBIDDEN", "Cư dân không được tự phê duyệt hồ sơ.", 403)
        transitions = {
            "SUBMITTED": {"REQUEST_INFO": "WAITING_INFO", "APPROVE": "APPROVED", "REJECT": "REJECTED", "CANCEL": "CANCELLED"},
            "WAITING_INFO": {"SUPPLEMENT": "SUBMITTED", "REJECT": "REJECTED", "CANCEL": "CANCELLED"},
            "APPROVED": {"COMPLETE": "COMPLETED", "REVOKE": "REVOKED"},
            "COMPLETED": {"REVOKE": "REVOKED"},
        }
        if row.kind == 'RENOVATION':
            transitions['APPROVED'] = {'START':'IN_PROGRESS'}
            transitions['IN_PROGRESS'] = {'COMPLETE':'COMPLETED'}
        target = require_transition(row.status, body.action, transitions)
        event_extra = {}
        if body.action in {'START','COMPLETE'} and row.kind == 'RENOVATION':
            context.assert_building_role(row.building_id,*MANAGERS)
            if body.action == 'START':
                if not row.valid_from <= business_date() < row.valid_to or unit.status == 'UNDER_RENOVATION':
                    raise AppError('ERR-RENOVATION-STATE','Chưa trong thời hạn thi công hoặc căn đang có cải tạo khác.',409)
                _apply_dossier(session,context,row)
                allowed=body.data.get('allowed_operations',[])
                if not isinstance(allowed,list) or any(not isinstance(v,str) or v not in {'LEASE','MOVE_IN','BOOKING','SERVICE','PARKING'} for v in allowed):
                    raise AppError('ERR-RENOVATION-POLICY','Phạm vi nghiệp vụ trong thi công không hợp lệ.',422)
                row.data={**row.data,'allowed_operations':sorted(set(allowed))}
                event_extra = {'unit_status_before':unit.status,'allowed_operations':row.data['allowed_operations']}
                unit.status = 'UNDER_RENOVATION'
            else:
                start = session.scalar(select(PortalDossierEvent).where(PortalDossierEvent.dossier_id==row.id,
                    PortalDossierEvent.action=='START').order_by(PortalDossierEvent.created_at.desc()).limit(1))
                if start is None or unit.status != 'UNDER_RENOVATION':
                    raise AppError('ERR-RENOVATION-STATE','Không có đợt thi công đang mở để nghiệm thu.',409)
                unit.status = start.snapshot['unit_status_before']
            unit.version += 1
        if body.action == "SUPPLEMENT":
            row.data = _validate_dossier_data(row.kind, {**row.data, **body.data})
        if body.action == "APPROVE":
            if not body.reason.strip():
                raise AppError('ERR-DECISION-REASON', 'Cần lý do quyết định.', 422)
            if row.kind == 'LIABILITY_CHANGE':
                context.assert_building_role(row.building_id,*FINANCE)
            if row.kind in PROPERTY_KINDS | {'TRANSFER','RENOVATION','DELEGATION'} and row.account_id == context.account_id:
                raise AppError('ERR-MAKER-CHECKER','Người lập không tự duyệt hồ sơ thay đổi.',409)
            row.decision_reason = body.reason
            if row.kind in PROPERTY_KINDS | {"TRANSFER", "RENOVATION", "DELEGATION"}:
                proof = session.scalar(select(ResidentDocument.id).where(ResidentDocument.dossier_id == row.id,
                    ResidentDocument.quarantined.is_(False), ResidentDocument.revoked_at.is_(None)).limit(1))
                if proof is None:
                    raise AppError("ERR-DOSSIER-EVIDENCE", "Hồ sơ cần tài liệu minh chứng trước khi duyệt.", 409)
            if row.kind != "PROFILE_CHANGE" or row.valid_from <= date.today():
                _apply_dossier(session, context, row)
                session.add(PortalDossierEvent(dossier_id=row.id, actor_id=context.account_id, action="APPLY",
                    message="Đã áp dụng dữ liệu được phê duyệt.", snapshot={"valid_from": str(row.valid_from)}))
        if body.action == "REVOKE":
            if row.kind != "DELEGATION":
                raise AppError("ERR-STATE-TRANSITION", "Thay đổi dữ liệu đã có hiệu lực cần hồ sơ điều chỉnh mới.", 409)
            session.execute(update(ResidentDelegation).where(ResidentDelegation.dossier_id == row.id).values(revoked_at=utc_now()))
        row.status = target; row.version += 1; row.decision_reason = body.reason
        if not resident(context):
            row.decided_by_id = context.account_id; row.decided_at = utc_now()
        session.add(PortalDossierEvent(dossier_id=row.id, actor_id=context.account_id,
            action=body.action, message=body.reason, snapshot={"status": row.status, "data": row.data, **event_extra}))
        _notify(session, context, request, row, "Hồ sơ đã cập nhật", f"{row.title}: {body.reason}")
        return row, "profile"
    return command(request, context, key, f"dossier.{body.action.lower()}",
                   {"id": str(identifier), **body.model_dump(mode="json")}, execute, roles=(*MANAGERS,*FINANCE))


@router.get("/resources")
def resources(request: Request, kind: str | None = None, unit_id: UUID | None = None,
              context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        conditions = list(context.scope_conditions(PortalResource))
        if resident(context):
            if unit_id is None:
                raise AppError("ERR-UNIT-REQUIRED", "Cần chọn căn hộ.", 422)
            permission = {"PARKING": "parking", "FACILITY": "booking", "SERVICE": "finance"}.get(kind, "profile")
            unit = unit_for(session, context, unit_id, permission)
            conditions.append(PortalResource.building_id == unit.building_id)
        else:
            conditions.extend(staff_conditions(context, PortalResource, PORTAL_STAFF))
        if kind:
            conditions.append(PortalResource.kind == kind)
        return {"items": [view(r) for r in session.scalars(select(PortalResource).where(*conditions)
                                                            .order_by(PortalResource.name).limit(200))]}


@router.post("/resources", status_code=201)
def create_resource(body: ResourceInput, request: Request,
                    context: UserContext = Depends(get_current_user_context),
                    key: str = Header(..., alias="Idempotency-Key")):
    def execute(session):
        context.assert_building_role(body.building_id, *MANAGERS)
        from app.models.building import Building
        building = session.scalar(select(Building).where(Building.id == body.building_id,
                                  Building.site_id == context.assert_active_site()))
        if building is None:
            raise scope_not_found()
        validate_resource_policy(body.kind, body.policy)
        row = PortalResource(**scope_values(context, building_id=body.building_id),
                             **body.model_dump(exclude={"building_id"}))
        session.add(row)
        return row, "profile"
    return command(request, context, key, "resource.create", body.model_dump(mode="json"), execute)


@router.post("/resources/{identifier}/actions")
def resource_action(identifier: UUID, body: PortalAction, request: Request,
                    context: UserContext = Depends(get_current_user_context),
                    key: str = Header(..., alias="Idempotency-Key")):
    def execute(session):
        context.assert_role(*MANAGERS)
        row = scoped(session, context, PortalResource, identifier, lock=True)
        require_version(row.version, body.expected_version)
        if body.action not in {"OPEN", "CLOSE", "UPDATE"}:
            raise AppError("ERR-STATE-TRANSITION", "Thao tác cấu hình không hợp lệ.", 422)
        if body.action == "UPDATE":
            allowed = {"name", "description", "capacity", "fee_vnd", "deposit_vnd", "policy"}
            if set(body.data) - allowed:
                raise AppError("ERR-POLICY-INCOMPLETE", "Không được đổi loại hoặc địa bàn tài nguyên.", 422)
            values = {field: body.data.get(field, getattr(row, field)) for field in allowed}
            checked = ResourceInput(kind=row.kind, building_id=row.building_id, **values)
            validate_resource_policy(row.kind, checked.policy)
            if row.kind == "PARKING":
                occupied = session.scalar(select(func.count(VehicleRegistration.id)).where(
                    VehicleRegistration.resource_id == row.id, VehicleRegistration.status.in_(("ACTIVE", "OFFERED", "PAUSED")))) or 0
                if checked.capacity < occupied:
                    raise AppError("ERR-CAPACITY", "Sức chứa mới thấp hơn số suất đã cấp.", 409)
            if row.kind == "FACILITY" and checked.capacity < row.capacity:
                if session.scalar(select(FacilityBooking.id).where(FacilityBooking.resource_id == row.id,
                    FacilityBooking.ends_at > utc_now(), FacilityBooking.status.in_(("CONFIRMED", "AWAITING_DEPOSIT", "CHECKED_IN"))).limit(1)):
                    raise AppError("ERR-CAPACITY", "Cần xử lý booking tương lai trước khi giảm sức chứa.", 409)
            for field, value in checked.model_dump(exclude={"kind", "building_id"}).items():
                setattr(row, field, value)
        else:
            row.status = "OPEN" if body.action == "OPEN" else "CLOSED"
        row.version += 1
        return row, "profile"
    return command(request, context, key, f"resource.{body.action.lower()}",
                   {"id": str(identifier), **body.model_dump(mode="json")}, execute)


@router.get("/deposits")
def deposits(request: Request, unit_id: UUID | None = None,
             context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        conditions = list(visible_conditions(context, PortalDeposit, "finance", roles=FINANCE))
        if unit_id:
            unit_for(session, context, unit_id, "finance", roles=FINANCE)
            conditions.append(PortalDeposit.unit_id == unit_id)
        rows = session.scalars(select(PortalDeposit).where(*conditions).order_by(PortalDeposit.created_at.desc()).limit(200)).all()
        result = []
        for row in rows:
            moves = session.scalars(select(PortalDepositMovement).where(PortalDepositMovement.deposit_id == row.id)
                                    .order_by(PortalDepositMovement.created_at)).all()
            result.append({**view(row), "movements": [view(move) for move in moves]})
        return {"items": result}


@router.post("/dossiers/{identifier}/deposit")
def configure_renovation_deposit(identifier: UUID, body: PortalAction, request: Request,
                    context: UserContext = Depends(get_current_user_context),
                    key: str = Header(..., alias="Idempotency-Key")):
    def execute(session):
        context.assert_role(*FINANCE)
        row = scoped(session, context, PortalDossier, identifier, lock=True, roles=FINANCE)
        require_version(row.version, body.expected_version)
        amount = body.data.get("required_vnd")
        if row.kind != "RENOVATION" or row.status not in {"SUBMITTED", "WAITING_INFO"} or type(amount) is not int or amount < 0:
            raise AppError("ERR-DEPOSIT-AMOUNT", "Chỉ thiết lập cọc hợp lệ cho hồ sơ cải tạo đang chờ.", 422)
        existing = session.scalar(select(PortalDeposit).where(PortalDeposit.source_kind == "RENOVATION", PortalDeposit.source_id == row.id))
        if existing:
            raise AppError("ERR-CONFLICT", "Điều kiện cọc đã được thiết lập.", 409)
        deposit = PortalDeposit(tenant_id=row.tenant_id, site_id=row.site_id, building_id=row.building_id,
            unit_id=row.unit_id, account_id=row.account_id, source_kind="RENOVATION", source_id=row.id,
            required_vnd=amount, status="HELD" if amount == 0 else "AWAITING_FUNDS")
        session.add(deposit)
        return deposit, "finance"
    return command(request, context, key, "renovation.deposit", {"id": str(identifier), **body.model_dump(mode="json")}, execute, roles=FINANCE)


@router.post("/deposits/{identifier}/actions")
def deposit_action(identifier: UUID, body: DepositAction, request: Request,
                   context: UserContext = Depends(get_current_user_context),
                   key: str = Header(..., alias="Idempotency-Key")):
    def execute(session):
        context.assert_role(*FINANCE)
        row = scoped(session, context, PortalDeposit, identifier, "finance", lock=True, roles=FINANCE)
        if body.action != 'RECEIVE':
            raise AppError('ERR-FINANCE-APPROVAL-REQUIRED','Khấu trừ, giải tỏa và hoàn cọc cần hồ sơ lập–duyệt–thực hiện.',409)
        require_version(row.version, body.expected_version)
        duplicate = session.scalar(select(PortalDepositMovement.id).where(
            *context.scope_conditions(PortalDepositMovement), PortalDepositMovement.kind == body.action,
            PortalDepositMovement.reference == body.reference))
        if duplicate:
            raise AppError("ERR-CONFLICT", "Mã chứng từ cọc đã được sử dụng.", 409)
        deposit_movement(row, body.action, body.amount_vnd)
        session.add(PortalDepositMovement(tenant_id=row.tenant_id, site_id=row.site_id,
            building_id=row.building_id, unit_id=row.unit_id, account_id=row.account_id,
            deposit_id=row.id, kind=body.action, amount_vnd=body.amount_vnd,
            reference=body.reference, reason=body.reason, actor_id=context.account_id))
        _notify(session, context, request, row, "Cập nhật hồ sơ cọc", body.reason)
        return row, "finance"
    return command(request, context, key, f"deposit.{body.action.lower()}", {"id": str(identifier), **body.model_dump(mode="json")}, execute, roles=FINANCE)


def _service_request(session, context, identifier):
    from app.api.resident_service_requests import _resident_request
    from app.services.r2 import scoped_service_request
    if resident(context):
        return _resident_request(session, context, identifier, lock=True)
    row = scoped_service_request(session, context, identifier, lock=True)
    context.assert_building_role(row.building_id, *MANAGERS)
    return row


@router.get("/requests/{identifier}/messages")
def request_messages(identifier: UUID, request: Request, context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        row = _service_request(session, context, identifier)
        messages = session.scalars(select(PortalRequestMessage).where(
            PortalRequestMessage.service_request_id == row.id).order_by(PortalRequestMessage.created_at)).all()
        return {"items": [view(message) for message in messages], "version": row.version, "status": row.status,
                "csat_score": row.csat_score}


@router.post("/requests/{identifier}/messages")
def request_message(identifier: UUID, body: PortalAction, request: Request,
                    context: UserContext = Depends(get_current_user_context),
                    key: str = Header(..., alias="Idempotency-Key")):
    def execute(session):
        row = _service_request(session, context, identifier)
        require_version(row.version, body.expected_version)
        before = {"status": row.status, "version": row.version}
        is_resident = resident(context)
        resident_actions = {"REPLY", "CONFIRM", "REOPEN", "COMPLAINT", "RATE"}
        staff_actions = {"REPLY", "REQUEST_INFO", "RESUME", "RESOLVE_COMPLAINT"}
        if body.action not in (resident_actions if is_resident else staff_actions):
            raise AppError("ERR-FORBIDDEN", "Thao tác không thuộc quyền của bạn.", 403)
        if body.action == "REPLY" and row.status in {"CLOSED", "CANCELLED"}:
            raise AppError("ERR-STATE-TRANSITION", "Cần mở lại yêu cầu trước khi tiếp tục trao đổi.", 409)
        if body.action == "REQUEST_INFO":
            if row.status not in {"NEW", "TRIAGED", "IN_PROGRESS"}:
                raise AppError("ERR-STATE-TRANSITION", "Yêu cầu không ở trạng thái có thể bổ sung.", 409)
            row.status = "WAITING_INFO"
        elif body.action in {"RESUME", "REPLY"} and row.status == "WAITING_INFO":
            row.status = "TRIAGED"
        elif body.action == "CONFIRM":
            if row.status not in {"RESOLVED", "CLOSED"}:
                raise AppError("ERR-STATE-TRANSITION", "Chưa có kết quả để xác nhận.", 409)
            unfinished = session.scalar(select(WorkOrder.id).where(WorkOrder.service_request_id == row.id,
                WorkOrder.status.not_in(("COMPLETED", "CLOSED", "CANCELLED"))).limit(1))
            if unfinished:
                raise AppError("ERR-WORK-INCOMPLETE", "Còn công việc chưa hoàn tất.", 409)
            row.status = "CLOSED"; row.closed_at = utc_now()
        elif body.action in {"REOPEN", "COMPLAINT"}:
            if row.status not in {"RESOLVED", "CLOSED"}:
                raise AppError("ERR-STATE-TRANSITION", "Chỉ phản hồi kết quả đã xử lý.", 409)
            row.status = "IN_PROGRESS"; row.closed_at = None; row.resolved_at = None
            if body.action == "COMPLAINT":
                session.add(CaseRecord(tenant_id=row.tenant_id, site_id=row.site_id,
                    building_id=row.building_id, source_service_request_id=row.id,
                    reason=body.reason[:500], created_by_id=context.account_id, updated_by_id=context.account_id))
        elif body.action == "RATE":
            score = body.data.get("score")
            if row.status != "CLOSED" or row.csat_score is not None or type(score) is not int or not 1 <= score <= 5:
                raise AppError("ERR-CSAT", "Chỉ đánh giá một lần sau khi kết thúc, từ 1–5 điểm.", 409)
            row.csat_score = score
        elif body.action == "RESOLVE_COMPLAINT":
            cases = session.scalars(select(CaseRecord).where(
                CaseRecord.source_service_request_id == row.id, CaseRecord.status != "CLOSED")).all()
            for case in cases:
                case.status = "CLOSED"; case.updated_by_id = context.account_id; case.version += 1
        row.version += 1; row.updated_by_id = context.account_id
        message = PortalRequestMessage(tenant_id=row.tenant_id, site_id=row.site_id,
            building_id=row.building_id, unit_id=row.unit_id, account_id=row.owner_account_id,
            service_request_id=row.id, actor_id=context.account_id, action=body.action, message=body.reason)
        session.add(message); session.flush()
        audit(session, context, request, event_type="ResidentConversationUpdated", action=body.action.lower(),
            resource_type="ServiceRequest", resource_id=row.id, building_id=row.building_id,
            before=before, after={"status": row.status, "version": row.version}, reason=body.reason)
        _notify(session, context, request, message, "Phản hồi yêu cầu dịch vụ", body.reason)
        if is_resident:
            recipients = session.scalars(select(Account.id).join(AccountRole, AccountRole.account_id == Account.id).where(
                Account.tenant_id == row.tenant_id, Account.is_active.is_(True), Account.id != row.owner_account_id,
                AccountRole.effective_at(), AccountRole.site_id == row.site_id, AccountRole.role.in_(MANAGERS),
                or_(AccountRole.building_id == row.building_id,
                    (AccountRole.building_id.is_(None) & AccountRole.role.in_(("admin", "director"))))).distinct()).all()
            for recipient in recipients:
                enqueue_notification(session, context, request, event_type="ResidentConversationUpdated",
                    resource_type="ServiceRequest", resource_id=row.id, recipient_account_id=recipient,
                    template_code="PORTAL_UPDATE", template_snapshot={"title": "Phản hồi mới từ cư dân",
                    "body": body.reason, "unit_id": str(row.unit_id), "resource_id": str(row.id)})
        return message, "requests"
    return command(request, context, key, f"request.{body.action.lower()}", {"id": str(identifier), **body.model_dump(mode="json")}, execute)
