"""Shared authorization and append-only histories, never arbitrary JSON commands."""
from uuid import UUID
from sqlalchemy import select
from app.core.exceptions import AppError
from app.core.policy import scope_not_found
from app.models.operational_control import ControlEvent
from app.services.resident_portal import scope_values, staff_conditions, view

MANAGEMENT = ('admin', 'director', 'cskh')
TECHNICAL = ('admin', 'director', 'technical_lead')
SECURITY = ('admin', 'director', 'security')
FINANCIAL = ('admin', 'director', 'accountant')


def financial_lock(session, context):
    import hashlib
    from sqlalchemy import func
    key = int.from_bytes(hashlib.sha256(f'operational-finance:{context.tenant_id}:{context.assert_active_site()}'.encode()).digest()[:8], 'big', signed=True)
    session.execute(select(func.pg_advisory_xact_lock(key)))


def building_scope(session, context, building_id, roles):
    from app.models.building import Building
    from app.models.site import Site
    building = session.scalar(select(Building).join(Site, Site.id == Building.site_id).where(Building.id == building_id, Building.site_id == context.assert_active_site(), Site.tenant_id == context.tenant_id))
    if building is None:
        raise scope_not_found()
    context.assert_building_role(building_id, *roles)
    return building


def load(session, context, model, identifier, roles, *, lock=False):
    q = select(model).where(model.id == identifier, *context.scope_conditions(model), *staff_conditions(context, model, roles))
    if lock:
        q = q.with_for_update().execution_options(populate_existing=True)
    row = session.scalar(q)
    if row is None:
        raise scope_not_found()
    return row


def independent(context, row, roles=('admin', 'director')):
    context.assert_building_role(row.building_id, *roles)
    if context.account_id == row.account_id:
        raise AppError('ERR-INDEPENDENT-CHECKER', 'Người lập không được tự duyệt/nghiệm thu.', 403)


def event(session, context, row, action, reason):
    from fastapi.encoders import jsonable_encoder
    session.flush()
    values = scope_values(context, building_id=row.building_id)
    values['unit_id'] = getattr(row, 'unit_id', None)
    session.add(ControlEvent(**values,
        parent_type=row.__tablename__, parent_id=row.id, action=action, reason=reason,
        snapshot=jsonable_encoder(view(row))))


def state(row, allowed):
    if row.status not in allowed:
        raise AppError('ERR-STATE-TRANSITION', 'Thao tác không phù hợp trạng thái hiện tại.', 409)


def data_model(model, data):
    from pydantic import ValidationError
    try:
        return model.model_validate(data)
    except ValidationError:
        raise AppError('ERR-CONTROL-INPUT', 'Dữ liệu nghiệp vụ thiếu hoặc không hợp lệ.', 422) from None


def as_uuid(value):
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        raise AppError('ERR-CONTROL-INPUT', 'Mã tham chiếu không hợp lệ.', 422) from None
