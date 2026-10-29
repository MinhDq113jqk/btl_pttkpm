from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import select
from pydantic import Field
from app.core.exceptions import AppError
from app.core.policy import UserContext, get_current_user_context
from app.models.operational_control import IntegrationEndpoint, IntegrationDelivery, Meter, MeterReading
from app.models.sad_extensions import ExchangeState, ExchangeReceipt
from app.schemas.resident_portal import PortalInput, PortalAction
from app.services.operational_control import load, event, state, as_uuid, financial_lock
from app.services.resident_portal import command, scope_values, view
from app.services.r2 import require_version, utc_now
from app.services import integration_exchange as exchange

router = APIRouter(prefix='/portal/control', tags=['System exchange'])


class EndpointConfig(PortalInput):
    expected_version: int = Field(ge=1)
    adapter: Literal['JSON_REGISTRY', 'JSON_FILE']
    status: Literal['ACTIVE', 'DISABLED']
    reason: str = Field(min_length=3, max_length=300)


class IncomingReading(PortalInput):
    external_id: str = Field(min_length=3, max_length=150)
    meter_id: UUID
    read_on: date
    value: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    evidence_reference: str = Field(min_length=3, max_length=300)


class BankTransaction(PortalInput):
    external_id: str = Field(min_length=3, max_length=120)
    accounting_period_id: UUID
    billing_account_id: UUID | None = None
    amount_vnd: int = Field(gt=0, le=999999999999)
    received_at: datetime
    evidence_reference: str = Field(min_length=3, max_length=300)


class ParkingEvent(PortalInput):
    external_id: str = Field(min_length=3, max_length=150)
    operation: Literal['ENTER', 'EXIT']
    resource_id: UUID
    plate: str = Field(min_length=3, max_length=30)
    vehicle_type: str = Field(min_length=2, max_length=30)
    occurred_at: datetime
    visitor_id: UUID | None = None
    rate_vnd: int = Field(ge=0, le=999999999)
    evidence_reference: str = Field(min_length=3, max_length=300)


@router.get('/integrations/contract')
def contract(context: UserContext = Depends(get_current_user_context)):
    context.assert_role(*exchange.ROLES)
    return {'version': 'GREENCITY-JSON-1', 'inputs': {
        'readings': {'kind':'METER','label':'Chỉ số đồng hồ','schema':IncomingReading.model_json_schema()},
        'bank-transactions': {'kind':'BANK','label':'Giao dịch ngân hàng','schema':BankTransaction.model_json_schema()},
        'parking-events': {'kind':'PARKING','label':'Sự kiện vào/ra bãi xe','schema':ParkingEvent.model_json_schema()}}}


def check_receipt(session, endpoint, body):
    old = session.scalar(select(ExchangeReceipt).where(ExchangeReceipt.endpoint_id == endpoint.id, ExchangeReceipt.external_id == body.external_id))
    if old and old.digest != exchange.digest(body.model_dump(mode='json')):
        raise AppError('ERR-EXCHANGE-DUPLICATE', 'Mã bản tin đã có nội dung khác.', 409)
    return old


def receipt(session, context, endpoint, body, kind, result):
    payload = body.model_dump(mode='json')
    row = ExchangeReceipt(**scope_values(context, building_id=endpoint.building_id), endpoint_id=endpoint.id,
        external_id=body.external_id, kind=kind, payload=payload, digest=exchange.digest(payload), result=result, status='APPLIED')
    session.add(row); event(session, context, row, 'IMPORT', body.evidence_reference)
    return row


@router.post('/integrations/{identifier}/bank-transactions')
def bank_transaction(identifier: UUID, body: BankTransaction, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        financial_lock(session, context)
        endpoint = load(session, context, IntegrationEndpoint, identifier, exchange.ROLES, lock=True)
        if endpoint.kind != 'BANK' or endpoint.status != 'ACTIVE': raise AppError('ERR-EXCHANGE-ENDPOINT', 'Cần hệ thống ngân hàng đang hoạt động.', 409)
        old = check_receipt(session, endpoint, body)
        if old: return old, 'finance'
        if body.received_at.tzinfo is None or body.received_at > utc_now(): raise AppError('ERR-EXCHANGE-TIME', 'Thời điểm nhận tiền cần múi giờ và không ở tương lai.', 422)
        from app.models.billing import AccountingPeriod, BillingAccount
        from app.services.billing import receive_payment_command
        period = load(session, context, AccountingPeriod, body.accounting_period_id, exchange.ROLES, lock=True)
        account = load(session, context, BillingAccount, body.billing_account_id, exchange.ROLES) if body.billing_account_id else None
        payment = receive_payment_command(session, tenant_id=context.tenant_id, site_id=context.assert_active_site(),
            building_id=endpoint.building_id, period=period, account=account, payment_source='BANK_TRANSFER',
            source_reference='BANK:' + exchange.digest({'endpoint':str(endpoint.id),'external_id':body.external_id}),
            receipt_number='BANK-' + exchange.digest({'endpoint':str(endpoint.id),'external_id':body.external_id}), amount_vnd=body.amount_vnd, received_at=body.received_at, actor_id=context.account_id)
        row = receipt(session, context, endpoint, body, 'BANK_TRANSACTION', {'payment_id': str(payment.id), 'payment_status': payment.status})
        return row, 'finance'
    return command(request, context, key, 'exchange.bank', {'endpoint_id':str(identifier), **body.model_dump(mode='json')}, execute, roles=exchange.ROLES)


@router.post('/integrations/{identifier}/parking-events')
def parking_event(identifier: UUID, body: ParkingEvent, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        import math
        from sqlalchemy import func
        from app.models.operational_control import VisitorParking
        from app.models.resident_portal import PortalResource, VehicleRegistration
        financial_lock(session, context)
        endpoint = load(session, context, IntegrationEndpoint, identifier, exchange.ROLES, lock=True)
        if endpoint.kind != 'PARKING' or endpoint.status != 'ACTIVE': raise AppError('ERR-EXCHANGE-ENDPOINT', 'Cần hệ thống bãi xe đang hoạt động.', 409)
        old = check_receipt(session, endpoint, body)
        if old: return old, 'parking'
        resource = load(session, context, PortalResource, body.resource_id, exchange.ROLES, lock=True)
        if resource.building_id != endpoint.building_id or resource.kind != 'PARKING': raise AppError('ERR-EXCHANGE-SOURCE', 'Bãi xe khác phạm vi hệ thống.', 422)
        if body.occurred_at.tzinfo is None or body.occurred_at > utc_now(): raise AppError('ERR-EXCHANGE-TIME', 'Thời điểm xe cần múi giờ và không ở tương lai.', 422)
        plate = body.plate.upper().replace(' ', '')
        if body.operation == 'ENTER':
            from app.api.portal_registrations import _expire_offers
            _expire_offers(session, resource)
            occupied = session.scalar(select(func.count()).select_from(VehicleRegistration).where(VehicleRegistration.resource_id == resource.id, VehicleRegistration.status.in_(('ACTIVE', 'PAUSED', 'OFFERED')))) or 0
            visitors = session.scalar(select(func.count()).select_from(VisitorParking).where(VisitorParking.resource_id == resource.id, VisitorParking.status == 'ENTERED')) or 0
            if resource.status != 'OPEN' or occupied + visitors >= resource.capacity: raise AppError('ERR-CAPACITY', 'Bãi xe không còn suất.', 409)
            if session.scalar(select(VisitorParking.id).where(VisitorParking.resource_id == resource.id, VisitorParking.plate == plate, VisitorParking.status == 'ENTERED')):
                raise AppError('ERR-EXCHANGE-ORDER', 'Xe đã có lượt vào chưa ghi ra.', 409)
            visit = VisitorParking(**scope_values(context, building_id=endpoint.building_id), resource_id=resource.id,
                plate=plate, vehicle_type=body.vehicle_type, entered_at=body.occurred_at, rate_vnd=body.rate_vnd)
            session.add(visit); session.flush()
        else:
            if not body.visitor_id: raise AppError('ERR-EXCHANGE-SOURCE', 'Bản tin ra cần lượt vào nguồn.', 422)
            visit = load(session, context, VisitorParking, body.visitor_id, exchange.ROLES, lock=True)
            state(visit, ('ENTERED',))
            if visit.resource_id != resource.id or visit.plate != plate or body.occurred_at < visit.entered_at:
                raise AppError('ERR-EXCHANGE-ORDER', 'Bản tin ra không khớp xe/bãi/thời điểm vào.', 409)
            visit.exited_at = body.occurred_at; visit.fee_vnd = max(1, math.ceil((body.occurred_at-visit.entered_at).total_seconds()/3600))*visit.rate_vnd
            visit.status = 'EXITED'; visit.version += 1
        event(session, context, visit, body.operation, body.evidence_reference)
        row = receipt(session, context, endpoint, body, 'PARKING_EVENT', {'visitor_id':str(visit.id), 'status':visit.status})
        return row, 'parking'
    return command(request, context, key, 'exchange.parking', {'endpoint_id':str(identifier), **body.model_dump(mode='json')}, execute, roles=exchange.ROLES)


@router.post('/integrations/{identifier}/configure')
def configure(identifier: UUID, body: EndpointConfig, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        row = load(session, context, IntegrationEndpoint, identifier, exchange.ROLES, lock=True)
        require_version(row.version, body.expected_version)
        row.adapter = body.adapter; row.status = body.status; row.version += 1
        event(session, context, row, 'CONFIGURE', body.reason)
        return row, 'profile'
    return command(request, context, key, 'exchange.configure', {'id': str(identifier), **body.model_dump(mode='json')}, execute, roles=exchange.ROLES)


@router.post('/integrations/{identifier}/sources')
def queue_source(identifier: UUID, body: PortalAction, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        endpoint = load(session, context, IntegrationEndpoint, identifier, exchange.ROLES, lock=True)
        require_version(endpoint.version, body.expected_version)
        row = exchange.queue(session, context, endpoint, body.data.get('source_type'), as_uuid(body.data.get('source_id')))
        return row, 'profile'
    return command(request, context, key, 'exchange.queue', {'id': str(identifier), **body.model_dump(mode='json')}, execute, roles=exchange.ROLES)


@router.get('/deliveries/{identifier}/package')
def package(identifier: UUID, request: Request, context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        row = load(session, context, IntegrationDelivery, identifier, exchange.ROLES)
        return exchange.envelope(row)


@router.get('/integrations/{identifier}/received')
def received(identifier: UUID, request: Request, context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        endpoint = load(session, context, IntegrationEndpoint, identifier, exchange.ROLES)
        return {'items': [view(r) for r in session.scalars(select(ExchangeState).where(ExchangeState.endpoint_id == endpoint.id))],
                'receipts': [view(r) for r in session.scalars(select(ExchangeReceipt).where(ExchangeReceipt.endpoint_id == endpoint.id))]}


@router.post('/integrations/{identifier}/readings')
def receive_reading(identifier: UUID, body: IncomingReading, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        financial_lock(session, context)
        endpoint = load(session, context, IntegrationEndpoint, identifier, exchange.ROLES, lock=True)
        if endpoint.kind != 'METER' or endpoint.status != 'ACTIVE':
            raise AppError('ERR-EXCHANGE-ENDPOINT', 'Cần hệ thống đồng hồ đang hoạt động.', 409)
        payload = body.model_dump(mode='json'); checksum = exchange.digest(payload)
        old = session.scalar(select(ExchangeReceipt).where(ExchangeReceipt.endpoint_id == endpoint.id, ExchangeReceipt.external_id == body.external_id))
        if old:
            if old.digest != checksum: raise AppError('ERR-EXCHANGE-DUPLICATE', 'Mã bản tin đã có nội dung khác.', 409)
            return old, 'profile'
        meter = exchange.source(session, context, endpoint, 'METER', body.meter_id); state(meter, ('ACTIVE',))
        previous = session.scalar(select(MeterReading).where(MeterReading.meter_id == meter.id).order_by(MeterReading.read_on.desc()).limit(1))
        if body.read_on < meter.valid_from or body.read_on > utc_now().date() or previous and (body.read_on <= previous.read_on or previous.status != 'VERIFIED'):
            raise AppError('ERR-METER-SEQUENCE', 'Bản tin không nối tiếp chỉ số đã xác minh.', 409)
        from app.services.meter_billing import effective_reading
        base = effective_reading(session, previous).value if previous else meter.baseline
        if body.value < base: raise AppError('ERR-METER-DECREASE', 'Chỉ số giảm cần hiệu chỉnh/thay đồng hồ.', 422)
        reading = MeterReading(**scope_values(context, building_id=meter.building_id), meter_id=meter.id,
            read_on=body.read_on, value=body.value, consumption=(body.value-base)*meter.multiplier,
            evidence_reference=body.evidence_reference, status='SUBMITTED', anomaly=bool(previous and (body.value-base)*meter.multiplier > previous.consumption*2))
        reading.unit_id = meter.unit_id; session.add(reading); session.flush()
        receipt = ExchangeReceipt(**scope_values(context, building_id=meter.building_id), endpoint_id=endpoint.id,
            external_id=body.external_id, kind='METER_READING', payload=payload, digest=checksum,
            result={'reading_id': str(reading.id), 'verification_status': 'SUBMITTED'}, status='APPLIED')
        session.add(receipt); event(session, context, reading, 'EXCHANGE_IMPORT', body.evidence_reference)
        return receipt, 'profile'
    return command(request, context, key, 'exchange.reading', {'endpoint_id': str(identifier), **body.model_dump(mode='json')}, execute, roles=exchange.ROLES)
