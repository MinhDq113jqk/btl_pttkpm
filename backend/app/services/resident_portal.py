"""Shared scope, transaction and state rules for resident portal commands."""
import hashlib
from datetime import UTC, date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, func, or_, select

from app.core.exceptions import AppError
from app.core.policy import scope_not_found
from app.models.building import Building
from app.models.person import UnitPersonRelationship
from app.models.site import Site
from app.models.unit import Unit
from app.services.r2 import audit, emit, idempotency_replay, remember_idempotency, validate_idempotency_key

PORTAL_STAFF = ("admin", "director", "cskh", "accountant", "security", "technical_lead", "cleaning")
MANAGERS = ("admin", "director", "cskh")
FINANCE = ("admin", "director", "accountant")


def resident(context):
    return "resident" in context.roles and not any(role in PORTAL_STAFF for role in context.roles)


def staff_conditions(context, model, roles=MANAGERS):
    context.assert_role(*roles)
    grants = [grant for grant in context.role_grants if grant.role in roles
              and (grant.building_id is not None or grant.role in {"admin", "director", "accountant"})]
    if not grants:
        raise scope_not_found()
    return (or_(*[(model.building_id == grant.building_id if grant.building_id is not None
                  else True) for grant in grants]),)


def visible_conditions(context, model, permission="profile", *, own=True, roles=MANAGERS):
    base = context.scope_conditions(model)
    if not resident(context):
        return (*base, *staff_conditions(context, model, roles))
    context.assert_role("resident")
    unit_ids = context.resident_units_for(permission)
    owners = or_(model.account_id == context.account_id, *(
        and_(model.unit_id == unit_id, model.account_id == grantor)
        for unit_id, grantor, permissions in context.resident_delegation_grantors if permission in permissions))
    return (*base, model.unit_id.in_(unit_ids), *((owners,) if own else ()))


def scoped(session, context, model, identifier, permission="profile", *, lock=False, own=True, roles=MANAGERS):
    statement = select(model).where(model.id == identifier,
                                    *visible_conditions(context, model, permission, own=own, roles=roles))
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    row = session.scalar(statement)
    if row is None:
        raise scope_not_found()
    return row


def unit_for(session, context, identifier, permission="profile", *, roles=MANAGERS, owner=False):
    row = session.scalar(select(Unit).join(Building, Unit.building_id == Building.id).join(Site, Site.id == Building.site_id).where(
        Unit.id == identifier, Building.site_id == context.assert_active_site(),
        Site.tenant_id == context.tenant_id,
    ).with_for_update(of=Unit))
    if row is None:
        raise scope_not_found()
    if resident(context):
        if identifier not in context.resident_units_for(permission):
            raise scope_not_found()
        if owner:
            from app.services.property import person_family
            relationship = session.scalar(select(UnitPersonRelationship.id).where(
                UnitPersonRelationship.unit_id == identifier,
                UnitPersonRelationship.person_id.in_(person_family(session, context.tenant_id, context.resident_person_id)),
                UnitPersonRelationship.tenant_id == context.tenant_id,
                UnitPersonRelationship.relationship_type == "owner",
                UnitPersonRelationship.valid_from <= date.today(),
                or_(UnitPersonRelationship.valid_to.is_(None), UnitPersonRelationship.valid_to > date.today()),
            ).limit(1))
            if relationship is None:
                raise AppError("ERR-FORBIDDEN", "Hồ sơ này cần quyền chủ sở hữu.", 403)
    else:
        context.assert_building_role(row.building_id, *roles)
    return row


def scope_values(context, unit=None, *, account_id=None, building_id=None):
    return dict(tenant_id=context.tenant_id, site_id=context.assert_active_site(),
                building_id=unit.building_id if unit else building_id,
                unit_id=unit.id if unit else None, account_id=account_id or context.account_id)


def view(row):
    hidden = {"storage_key", "token_hash", "verification_reference", "pin_hash", "hashed_password"}
    return {column.name: getattr(row, column.name) for column in row.__table__.columns
            if column.name not in hidden}


def command(request, context, key, operation, payload, execute, *, roles=MANAGERS):
    safe_key = validate_idempotency_key(key)
    with request.app.state.database.get_session() as session:
        material = f"{context.tenant_id}:{context.assert_active_site()}:{context.account_id}:{operation}:{safe_key}"
        lock = int.from_bytes(hashlib.sha256(material.encode()).digest()[:8], "big", signed=True)
        session.execute(select(func.pg_advisory_xact_lock(lock)))
        replay = idempotency_replay(session, context, operation=operation, key=safe_key, payload=payload)
        if replay is not None:
            result = replay.response_body or {}
            if result.get("unit_id"):
                unit_for(session, context, UUID(result["unit_id"]), result.get("_permission", "profile"), roles=roles)
            elif not resident(context):
                context.assert_role(*roles)
                if result.get("building_id"):
                    context.assert_building_role(UUID(result["building_id"]), *roles)
            elif operation == 'assistant.support' and replay.resource_type == 'AssistantConversation':
                from app.models.sad_extensions import AssistantConversation
                conversation = session.scalar(select(AssistantConversation).where(AssistantConversation.id == replay.resource_id, *context.scope_conditions(AssistantConversation), AssistantConversation.account_id == context.account_id))
                if conversation is None: raise scope_not_found()
            else:
                raise scope_not_found()
            return {k: v for k, v in result.items() if k != "_permission"}
        row, permission = execute(session)
        session.flush()
        result = view(row)
        audit(session, context, request, event_type="PortalCommand", action=operation,
              resource_type=row.__class__.__name__, resource_id=row.id,
              building_id=row.building_id, after={"version": row.version, "status": getattr(row, "status", None)})
        emit(session, context, request, event_type="PortalCommand", resource_type=row.__class__.__name__,
             resource_id=row.id, payload={"account_id": str(row.account_id), "unit_id": str(row.unit_id) if row.unit_id else None})
        from fastapi.encoders import jsonable_encoder
        remember_idempotency(session, context, operation=operation, key=safe_key, payload=payload,
                             resource_type=row.__class__.__name__, resource_id=row.id, response_status=200,
                             response_body=jsonable_encoder({**result, "_permission": permission}))
        session.commit()
        return result


def require_transition(status, action, transitions):
    target = transitions.get(status, {}).get(action)
    if target is None:
        raise AppError("ERR-STATE-TRANSITION", "Thao tác không phù hợp trạng thái hiện tại.", 409)
    return target


def available_booking_capacity(capacity, reservations, starts_at, ends_at):
    """Sweep intervals; sum of all overlapping bookings overcounts non-overlapping slots."""
    events = []
    for start, end, quantity in reservations:
        if start < ends_at and end > starts_at:
            events.extend(((max(start, starts_at), quantity), (min(end, ends_at), -quantity)))
    peak = count = 0
    for _, delta in sorted(events, key=lambda pair: (pair[0], pair[1])):
        count += delta
        peak = max(peak, count)
    return capacity - peak


def validate_resource_policy(kind, policy):
    if kind == "PARKING":
        required = ("quota_per_unit", "offer_minutes", "credential_days")
    elif kind == "FACILITY":
        required = ("slot_minutes", "max_duration_minutes", "cancel_before_minutes", "cancel_fee_vnd", "no_show_fee_vnd")
    else:
        required = ("recurring",)
    if any(key not in policy for key in required):
        raise AppError("ERR-POLICY-INCOMPLETE", "Chính sách thiếu trường bắt buộc: " + ", ".join(required), 422)
    for key in required:
        if key == "recurring":
            if type(policy[key]) is not bool:
                raise AppError("ERR-POLICY-INCOMPLETE", "recurring phải là true/false.", 422)
        elif type(policy[key]) is not int or policy[key] < (0 if key in {"cancel_before_minutes", "cancel_fee_vnd", "no_show_fee_vnd"} else 1):
            raise AppError("ERR-POLICY-INCOMPLETE", f"Giá trị {key} không hợp lệ.", 422)
    optional = {"rounding_unit_vnd"} if kind in {"PARKING", "SERVICE"} else set()
    if kind == "PARKING":
        optional.add("charge_when_paused")
        optional.add('vehicle_types')
        if 'vehicle_types' in policy and (not isinstance(policy['vehicle_types'], list) or not 1 <= len(policy['vehicle_types']) <= 10 or any(not isinstance(v, str) or not 2 <= len(v) <= 30 for v in policy['vehicle_types'])):
            raise AppError('ERR-POLICY-INCOMPLETE', 'Danh sách loại xe không hợp lệ.', 422)
        if "charge_when_paused" in policy and type(policy["charge_when_paused"]) is not bool:
            raise AppError("ERR-POLICY-INCOMPLETE", "charge_when_paused phải là true/false.", 422)
    if "rounding_unit_vnd" in policy and (type(policy["rounding_unit_vnd"]) is not int or not 1 <= policy["rounding_unit_vnd"] <= 9999999999):
        raise AppError("ERR-POLICY-INCOMPLETE", "Đơn vị làm tròn phải là số VND nguyên dương.", 422)
    if kind == 'FACILITY':
        optional.update(('quota_per_unit', 'quota_window_days', 'opening_weekdays', 'opens_at', 'closes_at'))
        for key in ('quota_per_unit', 'quota_window_days'):
            if key in policy and (type(policy[key]) is not int or not 1 <= policy[key] <= 100000):
                raise AppError('ERR-POLICY-INCOMPLETE', 'Hạn mức tiện ích phải là số nguyên dương.', 422)
        if ('quota_per_unit' in policy) != ('quota_window_days' in policy):
            raise AppError('ERR-POLICY-INCOMPLETE', 'Cần cả hạn mức và số ngày cửa sổ đặt.', 422)
        schedule = {'opening_weekdays', 'opens_at', 'closes_at'}
        if schedule & set(policy):
            import re
            days = policy.get('opening_weekdays')
            times = [policy.get('opens_at'), policy.get('closes_at')]
            if (not schedule <= set(policy) or not isinstance(days, list) or not 1 <= len(days) <= 7
                    or any(type(d) is not int or not 1 <= d <= 7 for d in days) or len(set(days)) != len(days)
                    or any(not isinstance(t, str) or not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', t) for t in times)
                    or times[0] >= times[1]):
                raise AppError('ERR-POLICY-INCOMPLETE', 'Cần ngày mở cửa (1–7), giờ mở/đóng HH:MM trong cùng ngày; giờ đóng sau giờ mở.', 422)
    if set(policy) - set(required) - optional:
        raise AppError("ERR-POLICY-INCOMPLETE", "Chính sách có trường không được hỗ trợ.", 422)
    if any(type(policy[k]) is int and policy[k] > 9999999999 for k in required):
        raise AppError("ERR-POLICY-INCOMPLETE", "Giá trị chính sách vượt giới hạn.", 422)
    if kind == "FACILITY" and (policy["max_duration_minutes"] < policy["slot_minutes"]
            or policy["max_duration_minutes"] % policy["slot_minutes"]):
        raise AppError("ERR-POLICY-INCOMPLETE", "Thời lượng tối đa cần là bội số của khung giờ.", 422)


def validate_booking_window(policy, starts_at, ends_at, *, future=False):
    duration = (ends_at - starts_at).total_seconds() / 60
    if (future and starts_at <= datetime.now(UTC) or duration <= 0
            or duration > policy['max_duration_minutes'] or duration % policy['slot_minutes']):
        raise AppError('ERR-BOOKING-TIME', 'Thời gian đặt ngoài điều kiện khung giờ.', 422)
    if 'opening_weekdays' not in policy:
        return  # Older policies retain their published conditions until explicitly updated.
    local = timezone(timedelta(hours=7))
    start, end = starts_at.astimezone(local), ends_at.astimezone(local)
    midnight = start.replace(hour=0, minute=0, second=0, microsecond=0)
    opened = midnight + timedelta(minutes=int(policy['opens_at'][:2]) * 60 + int(policy['opens_at'][3:]))
    closed = midnight + timedelta(minutes=int(policy['closes_at'][:2]) * 60 + int(policy['closes_at'][3:]))
    if start.isoweekday() not in policy['opening_weekdays'] or start < opened or end > closed:
        raise AppError('ERR-BOOKING-OPENING-HOURS', 'Lượt đặt nằm ngoài ngày/giờ mở cửa công bố (GMT+7).', 422)
    if (start - opened).total_seconds() % (policy['slot_minutes'] * 60):
        raise AppError('ERR-BOOKING-TIME', 'Giờ bắt đầu cần khớp khung tính từ giờ mở cửa.', 422)


def deposit_movement(deposit, action, amount):
    if type(amount) is not int or amount <= 0:
        raise AppError("ERR-DEPOSIT-AMOUNT", "Số tiền cọc phải lớn hơn 0.", 422)
    balance, released = deposit.balance_vnd, deposit.refundable_vnd
    if action == "RECEIVE":
        if deposit.status in {"RELEASED", "CLOSED"}:
            raise AppError("ERR-STATE-TRANSITION", "Hồ sơ cọc đã giải tỏa.", 409)
        balance += amount
    elif action in {"DEDUCT", "RELEASE"}:
        if amount > balance - released:
            raise AppError("ERR-DEPOSIT-BALANCE", "Số tiền vượt phần cọc đang giữ.", 409)
        if action == "DEDUCT":
            balance -= amount
        else:
            released += amount
    elif action == "REFUND":
        if amount > released:
            raise AppError("ERR-DEPOSIT-BALANCE", "Chưa có đủ quyết định giải tỏa/hoàn.", 409)
        balance -= amount
        released -= amount
    else:
        raise AppError("ERR-STATE-TRANSITION", "Thao tác cọc không hợp lệ.", 422)
    deposit.balance_vnd, deposit.refundable_vnd = balance, released
    deposit.status = "CLOSED" if balance == 0 and action == "REFUND" else "RELEASED" if released == balance and balance > 0 else "HELD" if balance >= deposit.required_vnd else "AWAITING_FUNDS"
    deposit.version += 1
