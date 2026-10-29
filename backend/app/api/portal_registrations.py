from datetime import timedelta, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import func, or_, select

from app.core.exceptions import AppError
from app.core.policy import UserContext, context_for_account, get_current_user_context, scope_not_found
from app.models.account import Account
from app.models.resident_portal import (PortalResource, VehicleRegistration, ResidentCredential,
    FacilityBooking, PortalDeposit, ServiceEnrollment, PortalResourceClosure)
from app.schemas.resident_portal import VehicleInput, BookingInput, EnrollmentInput, PortalAction, ResourceClosureInput
from app.services.r2 import audit, emit, require_version, utc_now
from app.services.portal_finance import create_fee_source, create_deposit, end_fee_source, queue_booking_credit, change_fee_source, fee_effective_date
from app.services.resident_portal import (MANAGERS, PORTAL_STAFF, available_booking_capacity,
    command, resident, scoped, scope_values, unit_for, view, visible_conditions, validate_booking_window)

router = APIRouter(prefix="/portal", tags=["Resident registrations"])
ACTIVE_BOOKINGS = ("AWAITING_DEPOSIT", "CONFIRMED", "CHECKED_IN")


@router.get('/resources/{identifier}/closures')
def closures(identifier: UUID, request: Request, unit_id: UUID | None = None, context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        if resident(context):
            unit = unit_for(session, context, unit_id, 'booking')
            resource = session.scalar(select(PortalResource).where(PortalResource.id == identifier,
                *context.scope_conditions(PortalResource), PortalResource.building_id == unit.building_id, PortalResource.kind == 'FACILITY'))
            if resource is None:
                raise scope_not_found()
        else:
            resource = scoped(session, context, PortalResource, identifier)
        return {'items': [view(r) for r in session.scalars(select(PortalResourceClosure).where(
            PortalResourceClosure.resource_id == resource.id).order_by(PortalResourceClosure.starts_at.desc()).limit(100))]}


@router.post('/resources/{identifier}/closures', status_code=201)
def create_closure(identifier: UUID, body: ResourceClosureInput, request: Request,
                   context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        context.assert_role(*MANAGERS)
        resource = scoped(session, context, PortalResource, identifier, lock=True)
        require_version(resource.version, body.expected_version)
        if resource.kind != 'FACILITY' or body.ends_at <= utc_now():
            raise AppError('ERR-RESOURCE-CLOSED', 'Cần tiện ích và khoảng đóng chưa kết thúc.', 422)
        row = PortalResourceClosure(**scope_values(context, building_id=resource.building_id), resource_id=resource.id,
            starts_at=body.starts_at, ends_at=body.ends_at, reason=body.reason)
        session.add(row); resource.version += 1
        affected = session.scalars(select(FacilityBooking).where(FacilityBooking.resource_id == resource.id,
            FacilityBooking.status.in_(('WAITING', 'AWAITING_DEPOSIT', 'CONFIRMED')),
            FacilityBooking.starts_at < body.ends_at, FacilityBooking.ends_at > body.starts_at).with_for_update()).all()
        from app.api.portal import _notify
        for booking in affected:
            booking.status = 'CANCELLED'; booking.version += 1
            end_fee_source(session, 'BOOKING', booking.id); queue_booking_credit(session, booking, context.account_id, body.reason)
            audit(session, context, request, event_type='BookingCancelledByFacility', action='cancel', resource_type='FacilityBooking',
                resource_id=booking.id, building_id=booking.building_id, after={'status': 'CANCELLED'}, reason=body.reason)
            _notify(session, context, request, booking, 'Hủy lượt đặt do lịch đóng tiện ích', body.reason)
        return row, 'booking'
    return command(request, context, key, 'resource.closure', {'id': str(identifier), **body.model_dump(mode='json')}, execute)


@router.post('/closures/{identifier}/actions')
def closure_action(identifier: UUID, body: PortalAction, request: Request,
                   context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        context.assert_role(*MANAGERS)
        row = scoped(session, context, PortalResourceClosure, identifier, lock=True)
        require_version(row.version, body.expected_version)
        if body.action != 'CANCEL' or row.status != 'SCHEDULED':
            raise AppError('ERR-STATE-TRANSITION', 'Lịch đóng không còn có thể hủy.', 409)
        row.status = 'CANCELLED'; row.version += 1
        return row, 'booking'
    return command(request, context, key, 'closure.cancel', {'id': str(identifier), **body.model_dump(mode='json')}, execute)


def _resource(session, context, identifier, unit, kind):
    row = session.scalar(select(PortalResource).where(PortalResource.id == identifier,
        *context.scope_conditions(PortalResource), PortalResource.building_id == unit.building_id,
        PortalResource.kind == kind).with_for_update())
    if row is None:
        raise scope_not_found()
    if row.status != "OPEN":
        raise AppError("ERR-RESOURCE-CLOSED", "Tài nguyên đang đóng hoặc bảo trì.", 409)
    return row


def _owner_context(session, row):
    account = session.scalar(select(Account).where(Account.id == row.account_id,
        Account.tenant_id == row.tenant_id, Account.is_active.is_(True)))
    if account is None:
        raise scope_not_found()
    return context_for_account(session, account, row.site_id)


def _booking_entitlement(session, context, unit_id, moment):
    from app.models.person import UnitPersonRelationship
    from app.models.resident_portal import ResidentDelegation
    use_date = moment.astimezone(timezone(timedelta(hours=7))).date()
    native = session.scalar(select(UnitPersonRelationship.id).where(
        UnitPersonRelationship.unit_id == unit_id, UnitPersonRelationship.person_id == context.resident_person_id,
        UnitPersonRelationship.tenant_id == context.tenant_id, UnitPersonRelationship.valid_from <= use_date,
        or_(UnitPersonRelationship.valid_to.is_(None), UnitPersonRelationship.valid_to > use_date)).limit(1))
    if native:
        return True
    grantors = [account for uid, account, permissions in context.resident_delegation_grantors if uid == unit_id and 'booking' in permissions]
    delegated = session.scalar(select(ResidentDelegation.id).join(Account, Account.id == ResidentDelegation.account_id)
        .join(UnitPersonRelationship, (UnitPersonRelationship.person_id == Account.person_id) & (UnitPersonRelationship.unit_id == unit_id))
        .where(ResidentDelegation.unit_id == unit_id, ResidentDelegation.account_id.in_(grantors),
            ResidentDelegation.delegate_person_id == context.resident_person_id, ResidentDelegation.revoked_at.is_(None),
            ResidentDelegation.valid_from <= use_date, ResidentDelegation.valid_to > use_date,
            UnitPersonRelationship.relationship_type == 'owner', UnitPersonRelationship.valid_from <= use_date,
            or_(UnitPersonRelationship.valid_to.is_(None), UnitPersonRelationship.valid_to > use_date)).limit(1))
    return delegated is not None


def _list(request, context, model, permission, unit_id, *, roles=MANAGERS):
    with request.app.state.database.get_session() as session:
        conditions = list(visible_conditions(context, model, permission, roles=roles))
        if unit_id:
            unit_for(session, context, unit_id, permission, roles=roles)
            conditions.append(model.unit_id == unit_id)
        return {"items": [view(r) for r in session.scalars(select(model).where(*conditions)
                              .order_by(model.created_at.desc()).limit(200))]}


@router.get("/vehicles")
def vehicles(request: Request, unit_id: UUID | None = None, context: UserContext = Depends(get_current_user_context)):
    return _list(request, context, VehicleRegistration, "parking", unit_id, roles=(*MANAGERS, 'security'))


def _expire_offers(session, resource):
    for row in session.scalars(select(VehicleRegistration).where(VehicleRegistration.resource_id == resource.id,
            VehicleRegistration.status == "OFFERED", VehicleRegistration.offer_expires_at <= utc_now()).with_for_update()):
        row.status = "CANCELLED"; row.offer_expires_at = None; row.version += 1


def _parking_available(session, resource, unit_id):
    _expire_offers(session, resource)
    occupied = session.scalar(select(func.count(VehicleRegistration.id)).where(
        VehicleRegistration.resource_id == resource.id, VehicleRegistration.status.in_(("ACTIVE", "OFFERED", "PAUSED")))) or 0
    quota = session.scalar(select(func.count(VehicleRegistration.id)).where(
        VehicleRegistration.resource_id == resource.id, VehicleRegistration.unit_id == unit_id,
        VehicleRegistration.status.in_(("ACTIVE", "OFFERED", "PAUSED")))) or 0
    from app.models.operational_control import VisitorParking
    visitors = session.scalar(select(func.count()).select_from(VisitorParking).where(VisitorParking.resource_id == resource.id, VisitorParking.status == 'ENTERED')) or 0
    return occupied + visitors < resource.capacity and quota < resource.policy["quota_per_unit"]


@router.post("/vehicles", status_code=201)
def register_vehicle(body: VehicleInput, request: Request, context: UserContext = Depends(get_current_user_context),
                     key: str = Header(..., alias="Idempotency-Key")):
    def execute(session):
        context.assert_role("resident")
        unit = unit_for(session, context, body.unit_id, "parking")
        from app.services.property import renovation_permission
        renovation_permission(session,unit,'PARKING')
        resource = _resource(session, context, body.resource_id, unit, "PARKING")
        if resource.policy.get('vehicle_types') and body.vehicle_type not in resource.policy['vehicle_types']:
            raise AppError('ERR-VEHICLE-TYPE', 'Bãi xe không hỗ trợ loại xe này.', 422)
        duplicate = session.scalar(select(VehicleRegistration.id).where(*context.scope_conditions(VehicleRegistration),
            VehicleRegistration.plate == body.plate, VehicleRegistration.status != "CANCELLED").limit(1))
        if duplicate:
            raise AppError("ERR-VEHICLE-DUPLICATE", "Biển số đã có đăng ký chưa kết thúc.", 409)
        row = VehicleRegistration(**scope_values(context, unit), resource_id=resource.id,
            plate=body.plate, vehicle_type=body.vehicle_type,
            policy_snapshot={**resource.policy, "fee_vnd": resource.fee_vnd, "resource_version": resource.version})
        session.add(row)
        return row, "parking"
    return command(request, context, key, "vehicle.create", body.model_dump(mode="json"), execute, roles=PORTAL_STAFF)


@router.post("/vehicles/{identifier}/actions")
def vehicle_action(identifier: UUID, body: PortalAction, request: Request,
                   context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias="Idempotency-Key")):
    def execute(session):
        row = scoped(session, context, VehicleRegistration, identifier, "parking", roles=PORTAL_STAFF)
        unit = unit_for(session, context, row.unit_id, "parking", roles=PORTAL_STAFF)
        resource = session.scalar(select(PortalResource).where(PortalResource.id == row.resource_id).with_for_update())
        row = scoped(session, context, VehicleRegistration, identifier, "parking", lock=True, roles=PORTAL_STAFF)
        require_version(row.version, body.expected_version)
        is_resident = resident(context)
        if not is_resident:
            context.assert_building_role(row.building_id, *MANAGERS)
        if is_resident and body.action not in {"CANCEL", "CONFIRM", "PAUSE", "RESUME"}:
            raise AppError("ERR-FORBIDDEN", "Cư dân không tự cấp suất xe.", 403)
        if body.action in {"APPROVE", "OFFER", "CONFIRM", "RESUME"}:
            from app.services.property import renovation_permission
            renovation_permission(session,unit,'PARKING')
            if resource.status != "OPEN":
                raise AppError("ERR-RESOURCE-CLOSED", "Bãi xe đang đóng.", 409)
            owner = _owner_context(session, row)
            if row.unit_id not in owner.resident_units_for("parking"):
                raise scope_not_found()
        if body.action == "APPROVE" and row.status == "PENDING":
            context.assert_building_role(row.building_id, *MANAGERS)
            row.status = "ACTIVE" if _parking_available(session, resource, row.unit_id) else "WAITING"
        elif body.action == "OFFER" and row.status == "WAITING":
            context.assert_building_role(row.building_id, *MANAGERS)
            _expire_offers(session, resource)
            session.flush()
            first = session.scalar(select(VehicleRegistration.id).where(VehicleRegistration.resource_id == resource.id,
                VehicleRegistration.status == "WAITING").order_by(VehicleRegistration.created_at, VehicleRegistration.id).limit(1))
            if first != row.id or not _parking_available(session, resource, row.unit_id):
                raise AppError("ERR-PARKING-QUEUE", "Cần cấp đúng thứ tự chờ và còn sức chứa/quota.", 409)
            row.status = "OFFERED"; row.offer_expires_at = utc_now() + timedelta(minutes=resource.policy["offer_minutes"])
        elif body.action == "CONFIRM" and row.status == "OFFERED":
            if row.offer_expires_at <= utc_now():
                raise AppError("ERR-OFFER-EXPIRED", "Suất được mời đã hết hạn.", 409)
            row.status = "ACTIVE"; row.offer_expires_at = None
        elif body.action == "PAUSE" and row.status == "ACTIVE":
            if not row.policy_snapshot.get("charge_when_paused", True):
                change_fee_source(session, "PARKING", row.id, "PAUSE", fee_effective_date(body.data.get("effective_on")))
            row.status = "PAUSED"
            for card in session.scalars(select(ResidentCredential).where(ResidentCredential.vehicle_id == row.id,
                ResidentCredential.status == 'ACTIVE').with_for_update()):
                card.status = 'LOCKED'; card.version += 1; card.sync_status = 'NOT_CONFIGURED'
        elif body.action == "RESUME" and row.status == "PAUSED":
            if not row.policy_snapshot.get("charge_when_paused", True):
                change_fee_source(session, "PARKING", row.id, "RESUME", fee_effective_date(body.data.get("effective_on")))
            row.status = "ACTIVE"
        elif body.action == "CANCEL" and row.status != "CANCELLED":
            change_fee_source(session, "PARKING", row.id, "END", fee_effective_date(body.data.get("effective_on")))
            row.status = "CANCELLED"
            for card in session.scalars(select(ResidentCredential).where(ResidentCredential.vehicle_id == row.id,
                    ResidentCredential.status.in_(("ACTIVE", "LOCKED", "LOST"))).with_for_update()):
                card.status = "REVOKED"; card.version += 1; card.sync_status = "NOT_CONFIGURED"
                emit(session, context, request, event_type="CredentialRevoked", resource_type="ResidentCredential",
                     resource_id=card.id, payload={"revision": card.version, "status": card.status})
        else:
            raise AppError("ERR-STATE-TRANSITION", "Thao tác xe không hợp lệ.", 409)
        if row.status == "ACTIVE":
            from app.models.resident_portal import PortalFeeSource
            if session.scalar(select(PortalFeeSource.id).where(PortalFeeSource.source_kind == "PARKING", PortalFeeSource.source_id == row.id)) is None:
                create_fee_source(session, row, "PARKING", row.policy_snapshot["fee_vnd"],
                    f"Phí xe {row.plate}", row.policy_snapshot, recurring=True, basis="PER_VEHICLE")
        row.version += 1
        from app.api.portal import _notify
        _notify(session, context, request, row, "Đăng ký xe cập nhật", body.reason)
        return row, "parking"
    return command(request, context, key, f"vehicle.{body.action.lower()}", {"id": str(identifier), **body.model_dump(mode="json")}, execute, roles=PORTAL_STAFF)


@router.get("/credentials")
def credentials(request: Request, unit_id: UUID | None = None, context: UserContext = Depends(get_current_user_context)):
    return _list(request, context, ResidentCredential, "parking", unit_id, roles=(*MANAGERS, 'security'))


@router.post("/vehicles/{identifier}/credential", status_code=201)
def issue_credential(identifier: UUID, body: PortalAction, request: Request,
                     context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias="Idempotency-Key")):
    def execute(session):
        context.assert_role("admin", "director", "security")
        vehicle = scoped(session, context, VehicleRegistration, identifier, "parking", lock=True, roles=("admin", "director", "security"))
        require_version(vehicle.version, body.expected_version)
        if vehicle.status != "ACTIVE" or vehicle.unit_id not in _owner_context(session, vehicle).resident_units_for("parking"):
            raise AppError("ERR-CREDENTIAL-INELIGIBLE", "Xe/người đăng ký chưa đủ điều kiện cấp thẻ.", 409)
        if session.scalar(select(ResidentCredential.id).where(ResidentCredential.vehicle_id == vehicle.id,
                ResidentCredential.status.in_(("ACTIVE", "LOCKED", "LOST"))).limit(1)):
            raise AppError("ERR-CREDENTIAL-DUPLICATE", "Xe đã có thẻ đang hoạt động.", 409)
        row = ResidentCredential(tenant_id=vehicle.tenant_id, site_id=vehicle.site_id,
            building_id=vehicle.building_id, unit_id=vehicle.unit_id, account_id=vehicle.account_id,
            vehicle_id=vehicle.id, code="GC-" + uuid4().hex.upper(),
            valid_to=utc_now().date() + timedelta(days=vehicle.policy_snapshot["credential_days"]))
        session.add(row)
        return row, "parking"
    return command(request, context, key, "credential.issue", {"id": str(identifier), **body.model_dump(mode="json")}, execute, roles=("admin", "director", "security"))


@router.post("/credentials/{identifier}/actions")
def credential_action(identifier: UUID, body: PortalAction, request: Request,
                      context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias="Idempotency-Key")):
    def execute(session):
        row = scoped(session, context, ResidentCredential, identifier, "parking", roles=("admin", "director", "security"))
        vehicle = session.scalar(select(VehicleRegistration).where(VehicleRegistration.id == row.vehicle_id).with_for_update())
        row = scoped(session, context, ResidentCredential, identifier, "parking", lock=True, roles=("admin", "director", "security"))
        require_version(row.version, body.expected_version)
        if resident(context) and body.action != "LOST":
            raise AppError("ERR-FORBIDDEN", "Cư dân chỉ được báo mất/khóa khẩn cấp.", 403)
        if row.vehicle_id is None:
            from app.services.access_cards import access_card_action
            return access_card_action(session, context, row, body), 'parking'
        if body.action in {"LOCK", "LOST", "REVOKE"} and row.status != "REVOKED":
            row.status = {"LOCK": "LOCKED", "LOST": "LOST", "REVOKE": "REVOKED"}[body.action]
            row.version += 1; row.sync_status = "NOT_CONFIGURED"
        elif body.action == 'UNLOCK' and row.status == 'LOCKED':
            if vehicle.status != 'ACTIVE' or row.valid_to < utc_now().date() or row.unit_id not in _owner_context(session, row).resident_units_for('parking'):
                raise AppError('ERR-CREDENTIAL-INELIGIBLE', 'Không còn điều kiện mở khóa thẻ.', 409)
            row.status = 'ACTIVE'; row.version += 1; row.sync_status = 'NOT_CONFIGURED'
        elif body.action in {"REPLACE", "RENEW"}:
            if vehicle.status != "ACTIVE" or row.unit_id not in _owner_context(session, row).resident_units_for("parking"):
                raise AppError("ERR-CREDENTIAL-INELIGIBLE", "Không còn quyền cấp/gia hạn thẻ.", 409)
            if body.action == "RENEW" and row.status == "ACTIVE":
                row.valid_to = utc_now().date() + timedelta(days=vehicle.policy_snapshot["credential_days"])
                row.version += 1; row.sync_status = "NOT_CONFIGURED"
            elif body.action == "REPLACE" and row.status in {"LOST", "LOCKED", "EXPIRED"}:
                old = row; old.status = "REVOKED"; old.version += 1
                row = ResidentCredential(tenant_id=old.tenant_id, site_id=old.site_id,
                    building_id=old.building_id, unit_id=old.unit_id, account_id=old.account_id,
                    vehicle_id=old.vehicle_id, code="GC-" + uuid4().hex.upper(), replaces_id=old.id,
                    valid_to=utc_now().date() + timedelta(days=vehicle.policy_snapshot["credential_days"]))
                session.add(row)
            else:
                raise AppError("ERR-STATE-TRANSITION", "Thẻ không ở trạng thái được đổi/gia hạn.", 409)
        elif body.action == "ACK":
            revision = body.data.get("revision")
            if revision != row.version or row.sync_status != "PENDING":
                raise AppError("ERR-CREDENTIAL-STALE-ACK", "Không có lệnh đang chờ đúng phiên bản.", 409)
            row.applied_revision = revision; row.sync_status = "APPLIED"
        else:
            raise AppError("ERR-STATE-TRANSITION", "Thao tác thẻ không hợp lệ.", 409)
        return row, "parking"
    return command(request, context, key, f"credential.{body.action.lower()}", {"id": str(identifier), **body.model_dump(mode="json")}, execute, roles=("admin", "director", "security"))


@router.get("/bookings")
def bookings(request: Request, unit_id: UUID | None = None, context: UserContext = Depends(get_current_user_context)):
    return _list(request, context, FacilityBooking, "booking", unit_id)


@router.get("/resources/{identifier}/availability")
def availability(identifier: UUID, request: Request, unit_id: UUID,
                 starts_at: str, ends_at: str, context: UserContext = Depends(get_current_user_context)):
    from datetime import datetime
    from pydantic import ValidationError
    try:
        interval = BookingInput(unit_id=unit_id, resource_id=identifier,
            starts_at=datetime.fromisoformat(starts_at.replace("Z", "+00:00")),
            ends_at=datetime.fromisoformat(ends_at.replace("Z", "+00:00")))
    except (ValueError, ValidationError):
        raise AppError("ERR-BOOKING-TIME", "Khoảng thời gian không hợp lệ.", 422) from None
    with request.app.state.database.get_session() as session:
        unit = unit_for(session, context, unit_id, "booking")
        resource = _resource(session, context, identifier, unit, "FACILITY")
        validate_booking_window(resource.policy, interval.starts_at, interval.ends_at, future=True)
        reservations = session.execute(select(FacilityBooking.starts_at, FacilityBooking.ends_at, FacilityBooking.quantity)
            .where(FacilityBooking.resource_id == resource.id, FacilityBooking.status.in_(ACTIVE_BOOKINGS),
                FacilityBooking.starts_at < interval.ends_at, FacilityBooking.ends_at > interval.starts_at)).all()
        blocked = session.scalar(select(PortalResourceClosure.id).where(PortalResourceClosure.resource_id == resource.id,
            PortalResourceClosure.status == 'SCHEDULED', PortalResourceClosure.starts_at < interval.ends_at,
            PortalResourceClosure.ends_at > interval.starts_at).limit(1)) is not None
        return {"capacity": resource.capacity, "blocked": blocked, "available": 0 if blocked else max(0, available_booking_capacity(
            resource.capacity, reservations, interval.starts_at, interval.ends_at)), "resource_version": resource.version}


@router.post("/bookings", status_code=201)
def book_facility(body: BookingInput, request: Request, context: UserContext = Depends(get_current_user_context),
                  key: str = Header(..., alias="Idempotency-Key")):
    def execute(session):
        context.assert_role("resident")
        unit = unit_for(session, context, body.unit_id, "booking")
        from app.services.property import renovation_permission
        renovation_permission(session,unit,'BOOKING')
        resource = _resource(session, context, body.resource_id, unit, "FACILITY")
        if resource.policy.get('quota_per_unit'):
            # Serialize on resource and unit; waiting bookings also consume the quota.
            start = body.starts_at - timedelta(days=resource.policy['quota_window_days'])
            finish = body.starts_at + timedelta(days=resource.policy['quota_window_days'])
            total = session.scalar(select(func.coalesce(func.sum(FacilityBooking.quantity), 0)).where(FacilityBooking.resource_id == resource.id, FacilityBooking.unit_id == unit.id, FacilityBooking.status != 'CANCELLED', FacilityBooking.starts_at > start, FacilityBooking.starts_at < finish)) or 0
            if total + body.quantity > resource.policy['quota_per_unit']:
                raise AppError('ERR-BOOKING-QUOTA', 'Vượt hạn mức đặt tiện ích của căn trong cửa sổ công bố.', 409)
        if session.scalar(select(PortalResourceClosure.id).where(PortalResourceClosure.resource_id == resource.id,
            PortalResourceClosure.status == 'SCHEDULED', PortalResourceClosure.starts_at < body.ends_at,
            PortalResourceClosure.ends_at > body.starts_at).limit(1)):
            raise AppError('ERR-RESOURCE-CLOSED', 'Khoảng đặt trùng lịch đóng/bảo trì tiện ích.', 409)
        if not all(_booking_entitlement(session, context, unit.id, moment) for moment in (body.starts_at, body.ends_at - timedelta(microseconds=1))):
            raise AppError("ERR-BOOKING-ELIGIBILITY", "Quan hệ cư trú/ủy quyền không phủ thời gian sử dụng.", 409)
        validate_booking_window(resource.policy, body.starts_at, body.ends_at, future=True)
        if body.quantity > resource.capacity:
            raise AppError("ERR-CAPACITY", "Số suất yêu cầu vượt sức chứa tiện ích.", 422)
        reservations = session.execute(select(FacilityBooking.starts_at, FacilityBooking.ends_at, FacilityBooking.quantity)
            .where(FacilityBooking.resource_id == resource.id, FacilityBooking.status.in_(ACTIVE_BOOKINGS),
                FacilityBooking.starts_at < body.ends_at, FacilityBooking.ends_at > body.starts_at)).all()
        free = available_booking_capacity(resource.capacity, reservations, body.starts_at, body.ends_at)
        waiting = free < body.quantity
        deposit = resource.deposit_vnd * body.quantity
        row = FacilityBooking(**scope_values(context, unit), resource_id=resource.id,
            starts_at=body.starts_at, ends_at=body.ends_at, quantity=body.quantity,
            hold_expires_at=min(body.starts_at, utc_now() + timedelta(seconds=request.app.state.settings.booking_hold_seconds)) if deposit and not waiting else None,
            status="WAITING" if waiting else "AWAITING_DEPOSIT" if deposit else "CONFIRMED",
            policy_snapshot={**resource.policy, "fee_vnd": resource.fee_vnd * body.quantity,
                             "deposit_vnd": deposit, "resource_version": resource.version})
        session.add(row); session.flush()
        if not waiting:
            create_deposit(session, row, "BOOKING", deposit)
            if not deposit:
                create_fee_source(session, row, "BOOKING", row.policy_snapshot["fee_vnd"],
                                  f"Đặt tiện ích {resource.name}", row.policy_snapshot, basis="PER_BOOKING")
        return row, "booking"
    return command(request, context, key, "booking.create", body.model_dump(mode="json"), execute, roles=PORTAL_STAFF)


@router.post("/bookings/{identifier}/actions")
def booking_action(identifier: UUID, body: PortalAction, request: Request,
                   context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias="Idempotency-Key")):
    def execute(session):
        row = scoped(session, context, FacilityBooking, identifier, "booking", roles=PORTAL_STAFF)
        unit=unit_for(session,context,row.unit_id,'booking',roles=PORTAL_STAFF)
        resource = session.scalar(select(PortalResource).where(PortalResource.id == row.resource_id).with_for_update())
        row = scoped(session, context, FacilityBooking, identifier, "booking", lock=True, roles=PORTAL_STAFF)
        require_version(row.version, body.expected_version)
        if resident(context) and body.action not in {"CANCEL", "CONFIRM"}:
            raise AppError("ERR-FORBIDDEN", "Thao tác cần người quản lý tiện ích.", 403)
        if not resident(context):
            context.assert_building_role(row.building_id, *MANAGERS)
        if body.action in {"CHECK_IN", "CONFIRM", "PROMOTE"}:
            from app.services.property import renovation_permission
            renovation_permission(session,unit,'BOOKING')
            if session.scalar(select(PortalResourceClosure.id).where(PortalResourceClosure.resource_id == resource.id,
                PortalResourceClosure.status == 'SCHEDULED', PortalResourceClosure.starts_at < row.ends_at,
                PortalResourceClosure.ends_at > row.starts_at).limit(1)):
                raise AppError('ERR-RESOURCE-CLOSED', 'Lượt đặt trùng lịch đóng/bảo trì.', 409)
            owner = _owner_context(session, row)
            if (resource.status != "OPEN" or row.unit_id not in owner.resident_units_for("booking")
                    or not all(_booking_entitlement(session, owner, row.unit_id, moment)
                               for moment in (row.starts_at, row.ends_at - timedelta(microseconds=1)))):
                raise AppError("ERR-BOOKING-INELIGIBLE", "Tiện ích hoặc tư cách sử dụng không còn hợp lệ.", 409)
        if body.action == "PROMOTE" and row.status == "WAITING":
            context.assert_building_role(row.building_id, *MANAGERS)
            validate_booking_window(resource.policy, row.starts_at, row.ends_at, future=True)
            if row.starts_at <= utc_now():
                raise AppError("ERR-BOOKING-TIME", "Lượt chờ đã qua giờ bắt đầu.", 409)
            first = session.scalar(select(FacilityBooking.id).where(FacilityBooking.resource_id == row.resource_id,
                FacilityBooking.status == "WAITING", FacilityBooking.starts_at < row.ends_at,
                FacilityBooking.ends_at > row.starts_at).order_by(FacilityBooking.created_at, FacilityBooking.id).limit(1))
            if first != row.id:
                raise AppError("ERR-BOOKING-QUEUE", "Cần xử lý lượt chờ trùng khung theo thứ tự.", 409)
            reservations = session.execute(select(FacilityBooking.starts_at, FacilityBooking.ends_at, FacilityBooking.quantity)
                .where(FacilityBooking.resource_id == resource.id, FacilityBooking.status.in_(ACTIVE_BOOKINGS),
                       FacilityBooking.starts_at < row.ends_at, FacilityBooking.ends_at > row.starts_at)).all()
            if available_booking_capacity(resource.capacity, reservations, row.starts_at, row.ends_at) < row.quantity:
                raise AppError("ERR-CAPACITY", "Chưa có đủ sức chứa cho lượt chờ.", 409)
            row.status = "AWAITING_DEPOSIT" if row.policy_snapshot["deposit_vnd"] else "CONFIRMED"
            row.hold_expires_at = min(row.starts_at, utc_now() + timedelta(seconds=request.app.state.settings.booking_hold_seconds)) if row.status == "AWAITING_DEPOSIT" else None
            create_deposit(session, row, "BOOKING", row.policy_snapshot["deposit_vnd"])
            if row.status == "CONFIRMED":
                create_fee_source(session, row, "BOOKING", row.policy_snapshot["fee_vnd"],
                                  f"Đặt tiện ích {resource.name}", row.policy_snapshot, basis="PER_BOOKING")
        elif body.action == "CONFIRM" and row.status == "AWAITING_DEPOSIT":
            if not row.hold_expires_at or row.hold_expires_at <= utc_now():
                raise AppError("ERR-BOOKING-HOLD", "Thời hạn giữ suất đã hết.", 409)
            deposit = session.scalar(select(PortalDeposit).where(PortalDeposit.source_kind == "BOOKING",
                PortalDeposit.source_id == row.id).with_for_update())
            if deposit is None or deposit.balance_vnd - deposit.refundable_vnd < deposit.required_vnd:
                raise AppError("ERR-DEPOSIT-REQUIRED", "Chưa có đủ tiền cọc thực nhận.", 409)
            row.status = "CONFIRMED"
            row.hold_expires_at = None
            create_fee_source(session, row, "BOOKING", row.policy_snapshot["fee_vnd"],
                f"Đặt tiện ích {resource.name}", row.policy_snapshot, basis="PER_BOOKING")
        elif body.action == "CHECK_IN" and row.status == "CONFIRMED":
            if not row.starts_at <= utc_now() < row.ends_at:
                raise AppError("ERR-BOOKING-TIME", "Chưa tới hoặc đã hết giờ sử dụng.", 409)
            row.status = "CHECKED_IN"
        elif body.action == "COMPLETE" and row.status == "CHECKED_IN":
            row.status = "COMPLETED"
        elif body.action in {"CANCEL", "CANCEL_BY_FACILITY"} and row.status in {"WAITING", "AWAITING_DEPOSIT", "CONFIRMED"}:
            late = (row.starts_at - utc_now()).total_seconds() < row.policy_snapshot["cancel_before_minutes"] * 60
            if body.action == "CANCEL_BY_FACILITY":
                context.assert_building_role(row.building_id, *MANAGERS)
            if late and body.action == "CANCEL" and row.status != "WAITING":
                create_fee_source(session, row, "BOOKING_CANCEL", row.policy_snapshot["cancel_fee_vnd"],
                                  "Phí hủy tiện ích", row.policy_snapshot, basis="PER_BOOKING")
            row.status = "CANCELLED"; end_fee_source(session, "BOOKING", row.id)
            queue_booking_credit(session, row, context.account_id, body.reason)
        elif body.action == "NO_SHOW" and row.status == "CONFIRMED" and utc_now() >= row.ends_at:
            row.status = "NO_SHOW"
            create_fee_source(session, row, "BOOKING_NO_SHOW", row.policy_snapshot["no_show_fee_vnd"],
                              "Phí không sử dụng tiện ích", row.policy_snapshot, basis="PER_BOOKING")
        else:
            raise AppError("ERR-STATE-TRANSITION", "Thao tác booking không hợp lệ.", 409)
        row.version += 1
        from app.api.portal import _notify
        _notify(session, context, request, row, "Đặt tiện ích cập nhật", body.reason)
        return row, "booking"
    return command(request, context, key, f"booking.{body.action.lower()}", {"id": str(identifier), **body.model_dump(mode="json")}, execute, roles=PORTAL_STAFF)


@router.get("/enrollments")
def enrollments(request: Request, unit_id: UUID | None = None, context: UserContext = Depends(get_current_user_context)):
    return _list(request, context, ServiceEnrollment, "finance", unit_id)


@router.post("/enrollments", status_code=201)
def enroll_service(body: EnrollmentInput, request: Request, context: UserContext = Depends(get_current_user_context),
                   key: str = Header(..., alias="Idempotency-Key")):
    def execute(session):
        context.assert_role("resident")
        unit = unit_for(session, context, body.unit_id, "finance")
        from app.services.property import renovation_permission
        renovation_permission(session,unit,'SERVICE')
        resource = _resource(session, context, body.resource_id, unit, "SERVICE")
        existing = session.scalar(select(ServiceEnrollment.id).where(ServiceEnrollment.unit_id == unit.id,
            ServiceEnrollment.resource_id == resource.id, ServiceEnrollment.status.in_(("PENDING", "ACTIVE", "PAUSED"))).limit(1))
        if existing:
            raise AppError("ERR-ENROLLMENT-DUPLICATE", "Căn hộ đã đăng ký dịch vụ này.", 409)
        row = ServiceEnrollment(**scope_values(context, unit), resource_id=resource.id,
            policy_snapshot={**resource.policy, "fee_vnd": resource.fee_vnd, "resource_version": resource.version})
        session.add(row)
        return row, "finance"
    return command(request, context, key, "enrollment.create", body.model_dump(mode="json"), execute)


@router.post("/enrollments/{identifier}/actions")
def enrollment_action(identifier: UUID, body: PortalAction, request: Request,
                      context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias="Idempotency-Key")):
    def execute(session):
        initial = scoped(session, context, ServiceEnrollment, identifier, "finance")
        unit = unit_for(session, context, initial.unit_id, "finance")
        row = scoped(session, context, ServiceEnrollment, identifier, "finance", lock=True)
        require_version(row.version, body.expected_version)
        effective_on = fee_effective_date(body.data.get("effective_on"))
        if effective_on < row.created_at.astimezone(timezone(timedelta(hours=7))).date():
            raise AppError("ERR-FEE-EFFECTIVE-DATE", "Ngày hiệu lực trước ngày gửi đăng ký.", 409)
        before = row.status
        if body.action in {'APPROVE','RESUME'}:
            from app.services.property import renovation_permission
            renovation_permission(session,unit,'SERVICE')
        if body.action == "APPROVE" and row.status == "PENDING":
            context.assert_building_role(row.building_id, *MANAGERS)
            if row.unit_id not in _owner_context(session, row).resident_units_for("finance"):
                raise scope_not_found()
            row.status = "ACTIVE"
            create_fee_source(session, row, "SERVICE", row.policy_snapshot["fee_vnd"],
                "Dịch vụ đăng ký bổ sung", row.policy_snapshot, recurring=row.policy_snapshot["recurring"], effective_on=effective_on)
        elif body.action == "REJECT" and row.status == "PENDING":
            context.assert_building_role(row.building_id, *MANAGERS); row.status = "REJECTED"
        elif body.action == "END" and row.status in {"PENDING", "ACTIVE", "PAUSED"}:
            change_fee_source(session, "SERVICE", row.id, "END", effective_on)
            row.status = "ENDED"
        elif body.action == "PAUSE" and row.status == "ACTIVE" and row.policy_snapshot["recurring"]:
            change_fee_source(session, "SERVICE", row.id, "PAUSE", effective_on)
            row.status = "PAUSED"
        elif body.action == "RESUME" and row.status == "PAUSED" and row.policy_snapshot["recurring"]:
            catalog = session.get(PortalResource, row.resource_id)
            if catalog.status != "OPEN" or row.unit_id not in _owner_context(session, row).resident_units_for("finance"):
                raise AppError("ERR-RESOURCE-CLOSED", "Dịch vụ hoặc tư cách đăng ký không còn hiệu lực.", 409)
            change_fee_source(session, "SERVICE", row.id, "RESUME", effective_on)
            row.status = "ACTIVE"
        else:
            raise AppError("ERR-STATE-TRANSITION", "Thao tác đăng ký dịch vụ không hợp lệ.", 409)
        row.version += 1
        audit(session, context, request, event_type="ServiceEnrollmentStateChanged", action=body.action,
            resource_type="ServiceEnrollment", resource_id=row.id, building_id=row.building_id,
            before={"status": before}, after={"status": row.status, "effective_on": str(effective_on)}, reason=body.reason)
        from app.api.portal import _notify
        _notify(session, context, request, row, "Đăng ký dịch vụ cập nhật", body.reason)
        return row, "finance"
    return command(request, context, key, f"enrollment.{body.action.lower()}", {"id": str(identifier), **body.model_dump(mode="json")}, execute)
