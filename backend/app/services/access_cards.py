"""General and visitor cards retain independent authority from vehicle registration."""
from datetime import datetime, date
from uuid import uuid4
from sqlalchemy import select
from app.core.exceptions import AppError
from app.core.policy import context_for_account
from app.models.account import Account
from app.models.operational_control import OperationsRecord
from app.models.resident_portal import ResidentCredential
from app.services.r2 import utc_now


def assert_card_authority(session, card, *, entering=False):
    holder = session.get(Account, card.account_id)
    if (not holder or not holder.is_active or card.unit_id not in
            context_for_account(session, holder, card.site_id).resident_unit_ids
            or card.valid_to < utc_now().date()):
        raise AppError('ERR-CREDENTIAL-INELIGIBLE', 'Chủ thể/thời hạn cấp thẻ không còn hiệu lực.', 409)
    if card.authorization_record_id:
        authority = session.get(OperationsRecord, card.authorization_record_id)
        if (not authority or authority.tenant_id != card.tenant_id or authority.building_id != card.building_id
                or authority.unit_id != card.unit_id or authority.kind not in ('VISITOR', 'CONTRACTOR')
                or authority.status not in ('HOST_CONFIRMED', 'IN_PROGRESS')
                or authority.data['host_account_id'] != str(card.account_id)
                or not set(card.access_scope).issubset(authority.data['areas'])
                or card.valid_to > datetime.fromisoformat(authority.data['ends_at']).date()
                or utc_now() >= datetime.fromisoformat(authority.data['ends_at'])):
            raise AppError('ERR-CREDENTIAL-AUTHORITY', 'Thẻ khách cần hồ sơ tiếp đón còn hiệu lực và đúng khu vực.', 409)
        if entering and utc_now() < datetime.fromisoformat(authority.data['starts_at']):
            raise AppError('ERR-CREDENTIAL-AUTHORITY', 'Chưa đến thời gian vào.', 409)


def access_card_action(session, context, row, body):
    if body.action in ('LOCK', 'LOST', 'REVOKE') and row.status not in ('REVOKED', 'EXPIRED'):
        row.status = {'LOCK': 'LOCKED', 'LOST': 'LOST', 'REVOKE': 'REVOKED'}[body.action]
    elif body.action == 'UNLOCK' and row.status == 'LOCKED':
        assert_card_authority(session, row); row.status = 'ACTIVE'
    elif body.action == 'RENEW' and row.status == 'ACTIVE':
        try:
            until = date.fromisoformat(body.data['valid_to'])
        except (KeyError, TypeError, ValueError):
            raise AppError('ERR-CONTROL-INPUT', 'Cần ngày hết hạn mới.', 422) from None
        row.valid_to = until; assert_card_authority(session, row)
    elif body.action == 'REPLACE' and row.status in ('LOST', 'LOCKED'):
        assert_card_authority(session, row)
        old = row; old.status = 'REVOKED'; old.version += 1; old.sync_status = 'NOT_CONFIGURED'
        session.flush()
        row = ResidentCredential(tenant_id=old.tenant_id, site_id=old.site_id, building_id=old.building_id,
            unit_id=old.unit_id, account_id=old.account_id, vehicle_id=None,
            authorization_record_id=old.authorization_record_id, code='GC-'+uuid4().hex.upper(),
            valid_to=old.valid_to, access_scope=list(old.access_scope), replaces_id=old.id)
        session.add(row); session.flush()
    else:
        raise AppError('ERR-STATE-TRANSITION', 'Thao tác không phù hợp thẻ ra vào.', 409)
    row.version += 1; row.sync_status = 'NOT_CONFIGURED'
    from app.services.operational_control import event
    event(session, context, row, body.action, body.reason)
    return row
