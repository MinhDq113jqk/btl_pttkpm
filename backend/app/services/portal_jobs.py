"""Scheduled lifecycle work; callers supply a scoped administrative context."""
import hashlib
from datetime import date, datetime, timedelta, timezone
from uuid import UUID
from sqlalchemy import func, or_, select, tuple_

from app.core.exceptions import AppError
from app.core.policy import context_for_account
from app.models.account import Account
from app.models.building import Building
from app.models.person import UnitPersonRelationship
from app.models.resident_portal import (PortalContent, PortalPaymentIntent, ResidentCredential,
    VehicleRegistration, FacilityBooking, ServiceEnrollment, PortalDossier, PortalDossierEvent)
from app.services.r2 import audit, utc_now
from app.services.outbox import enqueue_notification
from app.services.portal_finance import end_fee_source, queue_booking_credit
from app.services.resident_portal import staff_conditions


def tick(session, context, request, *, limit=100, cutoff=None, target=None):
    context.assert_role('admin', 'director')
    now = cutoff or utc_now()
    from app.models.property import LeaseContract, UnitProfileEpisode
    from app.models.unit import Unit
    from app.services.portal_finance import business_date
    if cutoff:
        business_date = lambda: now.astimezone(timezone(timedelta(hours=7))).date()
    lifecycle_date = business_date if cutoff else date.today
    counts = {'asset_outages': 0, 'profiles': 0, 'content': 0, 'credentials': 0, 'vehicles': 0, 'bookings': 0, 'enrollments': 0, 'payments': 0}
    lock_key = int.from_bytes(hashlib.sha256(f'portal-jobs:{context.tenant_id}:{context.assert_active_site()}'.encode()).digest()[:8], 'big', signed=True)
    session.execute(select(func.pg_advisory_xact_lock(lock_key)))
    def rows(model, *conditions, order=()):
        if target and model.__tablename__ != target.__tablename__: return
        if target: conditions = (*conditions, model.id == target.id)
        columns = (*order, model.id)
        last = None
        while True:
            batch = session.scalars(select(model).where(*context.scope_conditions(model), *staff_conditions(context, model, ('admin', 'director')), *conditions,
                *((tuple_(*columns) > last,) if last else ()))
                .order_by(*columns).limit(limit).with_for_update(skip_locked=True)).all()
            if not batch:
                break
            last = tuple(getattr(batch[-1], column.key) for column in columns)
            yield from batch
    def notify(row, title, body):
        account = session.get(Account, row.account_id)
        if account and account.is_active:
            enqueue_notification(session, context, request, event_type='PortalLifecycleUpdated',
                resource_type=row.__class__.__name__, resource_id=row.id, recipient_account_id=row.account_id,
                template_code='PORTAL_UPDATE', template_snapshot={'title': title, 'body': body, 'unit_id': str(row.unit_id)})
        audit(session, context, request, event_type='PortalLifecycleUpdated', action='scheduled',
            resource_type=row.__class__.__name__, resource_id=row.id, building_id=row.building_id,
            after={'status': row.status, 'version': row.version})
    def eligible(row, permission):
        account = session.get(Account, row.account_id)
        if not account or not account.is_active:
            return False
        try:
            owner = context_for_account(session, account, row.site_id)
            if row.unit_id not in owner.resident_units_for(permission):
                return False
            if permission == 'booking':
                from app.api.portal_registrations import _booking_entitlement
                return all(_booking_entitlement(session, owner, row.unit_id, moment)
                           for moment in (row.starts_at, row.ends_at - timedelta(microseconds=1)))
            return True
        except AppError:
            return False
    for row in rows(LeaseContract, LeaseContract.status == 'ACTIVE', LeaseContract.valid_to <= business_date()):
        row.status = 'EXPIRED'; row.version += 1; notify(row, 'Hết hạn hợp đồng thuê', 'Hợp đồng hết hạn; cư trú và trách nhiệm phí được xử lý bằng hồ sơ riêng.')
    for row in rows(UnitProfileEpisode, UnitProfileEpisode.valid_from <= business_date(),
            or_(UnitProfileEpisode.valid_to.is_(None), UnitProfileEpisode.valid_to > business_date())):
        unit = session.scalar(select(Unit).where(Unit.id == row.unit_id).with_for_update())
        if unit and (unit.area_m2 != float(row.area_m2) or (unit.status != row.operating_status and unit.status != 'UNDER_RENOVATION')):
            unit.area_m2 = float(row.area_m2)
            if unit.status != 'UNDER_RENOVATION': unit.status = row.operating_status
            unit.version += 1; counts['profiles'] += 1
    for row in rows(PortalDossier, PortalDossier.kind == 'PROFILE_CHANGE', PortalDossier.status.in_(('APPROVED', 'COMPLETED')),
                    PortalDossier.valid_from <= lifecycle_date(), ~select(PortalDossierEvent.id).where(PortalDossierEvent.dossier_id == PortalDossier.id, PortalDossierEvent.action == 'APPLY').exists(),
                    order=(PortalDossier.valid_from, PortalDossier.created_at)):
        from app.api.portal import _apply_dossier
        _apply_dossier(session, context, row)
        session.add(PortalDossierEvent(dossier_id=row.id, actor_id=context.account_id, action='APPLY',
            message='Đã áp dụng thông tin đến ngày hiệu lực.', snapshot={'valid_from': str(row.valid_from)}))
        counts['profiles'] += 1
    from app.models.operational_control import OperationsRecord
    from app.models.maintenance import Asset
    from app.services.operational_control import event
    for row in rows(OperationsRecord, OperationsRecord.kind == 'ASSET_CHANGE', OperationsRecord.status == 'COMPLETED'):
        if row.data['operation'] != 'OUTAGE':
            continue
        start, end = datetime.fromisoformat(row.data['starts_at']), datetime.fromisoformat(row.data['ends_at'])
        asset = session.scalar(select(Asset).where(Asset.id == UUID(row.data['asset_id'])).with_for_update())
        if asset is None or asset.status == 'RETIRED':
            continue
        if start <= now < end and not row.data.get('outage_started'):
            row.data = {**row.data, 'outage_started': True, 'previous_asset_status': asset.status}
            asset.status = 'INACTIVE'; asset.version += 1; row.version += 1; counts['asset_outages'] += 1
            event(session, context, asset, 'OUTAGE_START', row.title)
        elif now >= end and row.data.get('outage_started') and not row.data.get('outage_ended'):
            row.data = {**row.data, 'outage_ended': True}
            # Another approved outage or an explicit retirement may still keep it unavailable.
            peers = session.scalars(select(OperationsRecord).where(OperationsRecord.kind == 'ASSET_CHANGE', OperationsRecord.status == 'COMPLETED', OperationsRecord.id != row.id, *context.scope_conditions(OperationsRecord))).all()
            active = any(p.data.get('asset_id') == str(asset.id) and p.data.get('operation') == 'OUTAGE' and datetime.fromisoformat(p.data['starts_at']) <= now < datetime.fromisoformat(p.data['ends_at']) for p in peers)
            # Remains unavailable until an explicit inspected RESTORE record completes.
            row.data = {**row.data, 'restoration_required': not active}
            row.version += 1; counts['asset_outages'] += 1; event(session, context, asset, 'OUTAGE_END', row.title)
    for row in rows(PortalContent, PortalContent.status == 'PUBLISHED', PortalContent.publish_at <= now, PortalContent.notified_at.is_(None)):
        if row.previous_id:
            previous = session.scalar(select(PortalContent).where(PortalContent.id == row.previous_id).with_for_update())
            if previous.status != 'WITHDRAWN':
                previous.status = 'WITHDRAWN'; previous.version += 1
                from app.services.operational_control import event
                event(session,context,previous,'REPLACED',row.change_reason)
        relations = [UnitPersonRelationship.tenant_id == row.tenant_id, UnitPersonRelationship.site_id == row.site_id,
            UnitPersonRelationship.valid_from <= lifecycle_date(), or_(UnitPersonRelationship.valid_to.is_(None), UnitPersonRelationship.valid_to > lifecycle_date())]
        if row.unit_id:
            relations.append(UnitPersonRelationship.unit_id == row.unit_id)
        elif row.building_id:
            relations.append(UnitPersonRelationship.building_id == row.building_id)
        recipients = session.scalars(select(Account.id).join(UnitPersonRelationship, Account.person_id == UnitPersonRelationship.person_id)
            .where(Account.tenant_id == row.tenant_id, Account.is_active.is_(True), *relations).distinct()).all()
        for recipient in recipients:
            enqueue_notification(session, context, request, event_type='PortalContentPublished', resource_type='PortalContent',
                resource_id=row.id, recipient_account_id=recipient, template_code='PORTAL_CONTENT',
                template_snapshot={'title': row.title, 'body': row.body[:4000], 'unit_id': str(row.unit_id) if row.unit_id else None})
        row.notified_at = now; counts['content'] += 1
    for row in rows(PortalPaymentIntent, PortalPaymentIntent.status == 'PENDING', PortalPaymentIntent.expires_at <= now):
        row.status = 'EXPIRED'; row.version += 1; counts['payments'] += 1
    for row in rows(VehicleRegistration, VehicleRegistration.status != 'CANCELLED'):
        if (row.status == 'OFFERED' and row.offer_expires_at <= now) or not eligible(row, 'parking'):
            row.status = 'CANCELLED'; row.version += 1; counts['vehicles'] += 1
            end_fee_source(session, 'PARKING', row.id); notify(row, 'Kết thúc đăng ký xe', 'Thời hạn nhận suất hoặc quyền đăng ký đã kết thúc.')
    for row in rows(ResidentCredential, ResidentCredential.status.in_(('ACTIVE', 'LOCKED', 'LOST'))):
        authority_ended = False
        if row.vehicle_id is None:
            from app.services.access_cards import assert_card_authority
            try:
                assert_card_authority(session, row)
            except AppError:
                authority_ended = True
        if row.valid_to < lifecycle_date() or not eligible(row, 'parking') or authority_ended:
            row.status = 'EXPIRED' if row.valid_to < lifecycle_date() else 'REVOKED'
            row.sync_status = 'NOT_CONFIGURED'; row.version += 1; counts['credentials'] += 1
            notify(row, 'Cập nhật thẻ cư dân', 'Thẻ hết hạn hoặc tư cách sử dụng đã kết thúc.')
    for row in rows(FacilityBooking, FacilityBooking.status.in_(('WAITING', 'AWAITING_DEPOSIT', 'CONFIRMED'))):
        if not eligible(row, 'booking') or (row.status == 'AWAITING_DEPOSIT' and row.hold_expires_at and row.hold_expires_at <= now) or (row.status == 'WAITING' and row.starts_at <= now):
            row.status = 'CANCELLED'; row.version += 1; counts['bookings'] += 1
            end_fee_source(session, 'BOOKING', row.id)
            queue_booking_credit(session, row, context.account_id, 'Lượt đặt kết thúc theo hiệu lực giữ suất/tư cách sử dụng.')
            notify(row, 'Cập nhật lượt đặt', 'Lượt đặt hết hạn giữ suất hoặc tư cách sử dụng đã kết thúc. Hồ sơ cọc được kế toán xử lý riêng.')
    for row in rows(ServiceEnrollment, ServiceEnrollment.status.in_(('PENDING', 'ACTIVE', 'PAUSED'))):
        if not eligible(row, 'finance'):
            row.status = 'ENDED'; row.version += 1; counts['enrollments'] += 1
            end_fee_source(session, 'SERVICE', row.id); notify(row, 'Kết thúc dịch vụ', 'Tư cách đăng ký đã kết thúc.')
    session.flush()
    return counts
