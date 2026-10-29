"""Versioned GreenCity JSON exchange. Registry ACKs are backed by receiver rows."""
import hashlib
import json
from uuid import uuid4
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from app.core.exceptions import AppError
from app.core.policy import scope_not_found
from app.models.operational_control import IntegrationEndpoint, IntegrationDelivery, Meter, Expense
from app.models.sad_extensions import ExchangeState
from app.models.resident_portal import ResidentCredential
from app.models.billing import BillingInvoice, Payment
from app.services.operational_control import load, as_uuid, event
from app.services.resident_portal import scope_values, view

ROLES = ('admin', 'director')
SOURCES = {'CREDENTIAL': (ResidentCredential, ('ACCESS', 'PARKING')), 'METER': (Meter, ('METER',)),
           'INVOICE': (BillingInvoice, ('ACCOUNTING',)), 'PAYMENT': (Payment, ('ACCOUNTING', 'BANK')),
           'EXPENSE': (Expense, ('ACCOUNTING',))}


def digest(payload):
    return hashlib.sha256(json.dumps(jsonable_encoder(payload), ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def source(session, context, endpoint, kind, identifier):
    if kind not in SOURCES or endpoint.kind not in SOURCES[kind][1]:
        raise AppError('ERR-EXCHANGE-SOURCE', 'Nguồn không thuộc hợp đồng trao đổi của hệ thống này.', 422)
    row = load(session, context, SOURCES[kind][0], identifier, ROLES, lock=True)
    if row.building_id != endpoint.building_id:
        raise scope_not_found()
    return row


def snapshot(session, row, kind):
    if kind == 'CREDENTIAL':
        from app.services.access_cards import assert_card_authority
        from app.models.operational_control import OperationsRecord
        authority = None
        if row.status == 'ACTIVE':
            assert_card_authority(session, row)
        if row.vehicle_id is None:
            authority = session.get(OperationsRecord, row.authorization_record_id) if row.authorization_record_id else None
        return {'status': row.status, 'areas': row.access_scope if row.status == 'ACTIVE' else [], 'valid_to': row.valid_to.isoformat(),
                **({'authorization_id': str(authority.id), 'authorization_version': authority.version,
                    'valid_from_at': authority.data['starts_at'], 'valid_until_at': authority.data['ends_at']} if authority else {})}
    return jsonable_encoder(view(row))


def queue(session, context, endpoint, kind, identifier):
    row = source(session, context, endpoint, kind, identifier)
    payload = snapshot(session, row, kind)
    existing = session.scalar(select(IntegrationDelivery).where(IntegrationDelivery.endpoint_id == endpoint.id,
        IntegrationDelivery.source_type == kind, IntegrationDelivery.source_id == row.id, IntegrationDelivery.source_version == row.version))
    if existing:
        if digest(existing.desired_state) != digest(payload):
            raise AppError('ERR-EXCHANGE-VERSION', 'Nguồn thay đổi nhưng chưa tăng phiên bản; cần đối chiếu trước.', 409)
        return existing
    delivery = IntegrationDelivery(**scope_values(context, building_id=endpoint.building_id), endpoint_id=endpoint.id,
        source_type=kind, source_id=row.id, source_version=row.version, desired_state=payload,
        status='PENDING' if endpoint.status == 'ACTIVE' else 'NOT_CONFIGURED')
    session.add(delivery); event(session, context, delivery, 'QUEUE', 'Lập gói trao đổi theo phiên bản nguồn.')
    return delivery


def envelope(row):
    return {'contract': 'GREENCITY-JSON-1', 'correlation_id': str(row.id), 'endpoint_id': str(row.endpoint_id),
            'source_type': row.source_type, 'source_id': str(row.source_id), 'source_version': row.source_version,
            'payload': row.desired_state, 'sha256': digest(row.desired_state)}


def dispatch(session, context, row, body):
    endpoint = load(session, context, IntegrationEndpoint, row.endpoint_id, ROLES, lock=True)
    current = source(session, context, endpoint, row.source_type, row.source_id)
    try:
        stale = current.version != row.source_version or digest(snapshot(session, current, row.source_type)) != digest(row.desired_state)
    except AppError:
        stale = True
    if stale:
        row.status = 'SUPERSEDED'
        return
    if body.action in ('RECONCILE','REPORT_FAILURE'):
        expected = envelope(row)
        if row.status not in ('AWAITING_ACK', 'FAILED') or endpoint.adapter != 'JSON_FILE' or endpoint.status != 'ACTIVE' or any(body.data.get(k) != expected[k] for k in ('correlation_id', 'source_version', 'sha256')) or not isinstance(body.data.get('external_reference'), str) or not 3 <= len(body.data['external_reference']) <= 150:
            raise AppError('ERR-EXCHANGE-ACK', 'Xác nhận cần đúng mã đối chiếu, phiên bản, checksum và chứng từ hệ thống nhận.', 422)
        if body.action == 'REPORT_FAILURE':
            if row.status == 'CONFIRMED' or not isinstance(body.data.get('error_code'),str) or not 3 <= len(body.data['error_code']) <= 80:
                raise AppError('ERR-EXCHANGE-ERROR', 'Lệnh chưa xác nhận mới được ghi lỗi; cần mã lỗi bên nhận.', 422)
            row.status = 'FAILED'
            event(session, context, row, 'EXTERNAL_FAILURE', body.data['error_code'] + ': ' + body.data['external_reference'])
        else: row.status = 'CONFIRMED'
        row.external_reference = body.data['external_reference']
    elif body.action in ('RETRY', 'DISPATCH'):
        if row.status == 'CONFIRMED': return
        row.attempts += 1
        if endpoint.status != 'ACTIVE': row.status = 'NOT_CONFIGURED'; return
        if endpoint.adapter == 'JSON_FILE': row.status = 'AWAITING_ACK'; return
        if endpoint.adapter != 'JSON_REGISTRY': row.status = 'NOT_CONFIGURED'; return
        state = session.scalar(select(ExchangeState).where(ExchangeState.endpoint_id == endpoint.id,
            ExchangeState.source_type == row.source_type, ExchangeState.source_id == row.source_id).with_for_update())
        if state and state.source_version > row.source_version:
            row.status = 'SUPERSEDED'; return
        if state and state.source_version == row.source_version and digest(state.payload) != digest(row.desired_state):
            row.status = 'CONFLICT'; return
        if state is None:
            state = ExchangeState(**scope_values(context, building_id=row.building_id), endpoint_id=endpoint.id,
                source_type=row.source_type, source_id=row.source_id, source_version=row.source_version,
                payload=row.desired_state, external_reference='REG-' + uuid4().hex)
            session.add(state)
        else:
            state.payload = row.desired_state; state.source_version = row.source_version; state.version += 1
        session.flush()
        row.external_reference = state.external_reference; row.status = 'CONFIRMED'
        event(session, context, state, 'RECEIVE', str(row.id))
    else:
        raise AppError('ERR-EXCHANGE-ACTION', 'Thao tác trao đổi không hợp lệ.', 422)
    if row.source_type == 'CREDENTIAL' and row.status == 'CONFIRMED':
        current.sync_status = 'CONFIRMED'
