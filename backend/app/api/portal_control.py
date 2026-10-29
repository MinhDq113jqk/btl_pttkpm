"""Parking, cards, communication, scheduled jobs and scoped exports."""
import hashlib
import json
import math
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, Header, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response
from sqlalchemy import func, select
from app.core.exceptions import AppError
from app.core.policy import UserContext, get_current_user_context, scope_not_found
from app.models.operational_control import (ParkingSlot, VisitorParking, CardBlank, IntegrationEndpoint,
    IntegrationDelivery, CommunityResponse, NotificationTemplate, NotificationPreference, JobSchedule, JobRun, ReportExport, ControlEvent)
from app.models.resident_portal import PortalResource, VehicleRegistration, ResidentCredential, PortalContent, ResidentDocument
from app.schemas.portal_control import (SlotInput, VisitorParkingInput, BlankInput, EndpointInput, CommunityAnswer, TemplateInput, PreferenceInput, JobInput)
from app.schemas.resident_portal import PortalAction, VehicleInput
from app.schemas.portal_control import AccessCardInput
from app.services.r2 import require_version, utc_now
from app.services.resident_portal import command, scoped, scope_values, staff_conditions, unit_for, view, resident
from app.services.operational_control import building_scope, load, event, state, data_model, as_uuid, MANAGEMENT, SECURITY

router = APIRouter(prefix='/portal/control', tags=['Operational control'])


@router.get('/catalog')
def control_catalog(context: UserContext = Depends(get_current_user_context)):
    from app.schemas.operational_control import MeterInput, ReadingInput, StockInput, StockCommand, TreasuryInput, ExpenseInput
    from app.schemas.sad_work import MeterAssignmentInput
    from app.schemas.portal_control import InvitationInput
    specs = [('meter-assignments', MeterAssignmentInput, ('admin', 'director', 'technical_lead')), ('access-cards', AccessCardInput, SECURITY), ('parking-slots', SlotInput, MANAGEMENT), ('visitor-parking', VisitorParkingInput, SECURITY), ('card-blanks', BlankInput, SECURITY),
        ('integrations', EndpointInput, ('admin', 'director')), ('templates', TemplateInput, MANAGEMENT), ('jobs', JobInput, ('admin', 'director')), ('invitations', InvitationInput, ('admin',)),
        ('meters', MeterInput, ('admin', 'director', 'technical_lead', 'accountant')), ('readings', ReadingInput, ('admin', 'director', 'technical_lead', 'accountant')), ('stock', StockInput, ('admin', 'director', 'technical_lead')),
        ('stock-movements', StockCommand, ('admin', 'director', 'technical_lead')), ('treasury', TreasuryInput, ('admin', 'director', 'accountant')), ('expenses', ExpenseInput, ('admin', 'director', 'accountant'))]
    from app.schemas.resident_portal import PortalInput
    specs.append(('commercial-ledgers', PortalInput, ('admin', 'director', 'accountant')))
    return {'items': [{'kind': name, 'schema': schema.model_json_schema(),
        'can_create': name != 'commercial-ledgers' and (name not in ('meters', 'readings') or any(r in context.roles for r in ('admin', 'director', 'technical_lead'))),
        'can_bill': name == 'readings' and any(r in context.roles for r in ('admin', 'director', 'accountant'))}
        for name, schema, roles in specs if any(r in context.roles for r in roles)]}


def listing(request, context, model, roles, building_id=None):
    with request.app.state.database.get_session() as session:
        conditions = [*context.scope_conditions(model), *staff_conditions(context, model, roles)]
        if building_id:
            building_scope(session, context, building_id, roles)
            conditions.append(model.building_id == building_id)
        return {'items': [view(r) for r in session.scalars(select(model).where(*conditions).order_by(model.created_at.desc()).limit(200))]}


@router.get('/parking-slots')
def slots(request: Request, building_id: UUID | None = None, context: UserContext = Depends(get_current_user_context)):
    return listing(request, context, ParkingSlot, (*MANAGEMENT, 'security'), building_id)


@router.get('/access-cards')
def access_cards(request: Request, context: UserContext = Depends(get_current_user_context)):
    result = listing(request, context, ResidentCredential, SECURITY)
    return {'items': [r for r in result['items'] if r['vehicle_id'] is None]}


@router.post('/access-cards', status_code=201)
def create_access_card(body: AccessCardInput, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        building_scope(session, context, body.building_id, SECURITY)
        unit = unit_for(session, context, body.unit_id, roles=SECURITY)
        if unit.building_id != body.building_id or any(not 1 <= len(a) <= 80 for a in body.areas):
            raise AppError('ERR-CONTROL-INPUT', 'Căn hoặc khu vực cấp thẻ không phù hợp.', 422)
        row = ResidentCredential(**scope_values(context, unit), vehicle_id=None, code='GC-'+uuid4().hex.upper(),
            valid_to=body.valid_to, access_scope=list(dict.fromkeys(body.areas)), authorization_record_id=body.authorization_record_id)
        row.account_id = body.holder_account_id
        from app.services.access_cards import assert_card_authority
        assert_card_authority(session, row); session.add(row); event(session, context, row, 'ISSUE', 'Cấp thẻ ra vào theo căn/hồ sơ tiếp đón.')
        return row, 'parking'
    return command(request, context, key, 'access-card.create', body.model_dump(mode='json'), execute, roles=SECURITY)


@router.post('/access-cards/{identifier}/actions')
def general_card_action(identifier: UUID, body: PortalAction, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        row = load(session, context, ResidentCredential, identifier, SECURITY, lock=True)
        require_version(row.version, body.expected_version)
        if row.vehicle_id:
            raise scope_not_found()
        from app.services.access_cards import access_card_action
        return access_card_action(session, context, row, body), 'parking'
    return command(request, context, key, 'access-card.' + body.action, {'id': str(identifier), **body.model_dump(mode='json')}, execute, roles=SECURITY)


@router.post('/parking-slots', status_code=201)
def create_slot(body: SlotInput, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        resource = load(session, context, PortalResource, body.resource_id, MANAGEMENT, lock=True)
        if resource.kind != 'PARKING':
            raise scope_not_found()
        if (session.scalar(select(func.count()).select_from(ParkingSlot).where(ParkingSlot.resource_id == resource.id)) or 0) >= resource.capacity:
            raise AppError('ERR-CAPACITY', 'Số ô đã đạt sức chứa bãi xe.', 409)
        row = ParkingSlot(**scope_values(context, building_id=resource.building_id), **body.model_dump())
        session.add(row); event(session, context, row, 'CREATE', 'Khai báo ô đỗ.')
        return row, 'parking'
    return command(request, context, key, 'slot.create', body.model_dump(mode='json'), execute, roles=MANAGEMENT)


@router.post('/parking-slots/{identifier}/actions')
def slot_action(identifier: UUID, body: PortalAction, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        initial = load(session, context, ParkingSlot, identifier, MANAGEMENT)
        load(session, context, PortalResource, initial.resource_id, MANAGEMENT, lock=True)
        vehicle = load(session, context, VehicleRegistration, as_uuid(body.data.get('vehicle_id')), MANAGEMENT, lock=True) if body.action == 'ASSIGN' else None
        row = load(session, context, ParkingSlot, identifier, MANAGEMENT, lock=True)
        require_version(row.version, body.expected_version)
        if body.action == 'ASSIGN':
            state(row, ('OPEN',))
            if row.vehicle_id:
                raise AppError('ERR-CAPACITY', 'Ô đỗ đang có xe.', 409)
            if vehicle.resource_id != row.resource_id or vehicle.status not in ('ACTIVE', 'PAUSED') or vehicle.vehicle_type not in row.vehicle_types:
                raise AppError('ERR-SLOT-INELIGIBLE', 'Loại xe hoặc đăng ký không phù hợp ô đỗ.', 409)
            if session.scalar(select(ParkingSlot.id).where(ParkingSlot.vehicle_id == vehicle.id)):
                raise AppError('ERR-CONFLICT', 'Xe đã được gán ô đỗ.', 409)
            row.vehicle_id = vehicle.id
        elif body.action == 'RELEASE':
            row.vehicle_id = None
        elif body.action in ('CLOSE', 'OPEN'):
            if row.vehicle_id:
                raise AppError('ERR-CONFLICT', 'Cần giải phóng ô đỗ trước khi đóng.', 409)
            row.status = 'CLOSED' if body.action == 'CLOSE' else 'OPEN'
        else:
            raise AppError('ERR-STATE-TRANSITION', 'Thao tác ô đỗ không hợp lệ.', 409)
        row.version += 1; event(session, context, row, body.action, body.reason)
        return row, 'parking'
    return command(request, context, key, 'slot.' + body.action, {'id': str(identifier), **body.model_dump(mode='json')}, execute)


@router.post('/vehicles/{identifier}/change')
def vehicle_change(identifier: UUID, body: PortalAction, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        row = scoped(session, context, VehicleRegistration, identifier, 'parking', roles=(*MANAGEMENT, 'security'))
        change = data_model(VehicleInput, {'unit_id': row.unit_id, **{k: v for k, v in body.data.items() if k != 'effective_on'}})
        if change.unit_id != row.unit_id:
            raise scope_not_found()
        resources = {i: load(session, context, PortalResource, i, MANAGEMENT, lock=True) for i in sorted({row.resource_id, change.resource_id}, key=str)}
        old_resource = resources[row.resource_id]; resource = resources[change.resource_id]
        row = load(session, context, VehicleRegistration, identifier, MANAGEMENT, lock=True)
        require_version(row.version, body.expected_version); state(row, ('ACTIVE', 'PAUSED'))
        if resource.kind != 'PARKING' or resource.status != 'OPEN' or resource.building_id != row.building_id:
            raise AppError('ERR-RESOURCE-CLOSED', 'Bãi xe đích không phù hợp.', 409)
        if resource.id != old_resource.id:
            from app.api.portal_registrations import _parking_available
            if not _parking_available(session, resource, row.unit_id):
                raise AppError('ERR-CAPACITY', 'Bãi xe đích không còn suất.', 409)
        if session.scalar(select(VehicleRegistration.id).where(*context.scope_conditions(VehicleRegistration), VehicleRegistration.plate == change.plate, VehicleRegistration.id != row.id, VehicleRegistration.status != 'CANCELLED')):
            raise AppError('ERR-VEHICLE-DUPLICATE', 'Biển số đang có đăng ký.', 409)
        if resource.policy.get('vehicle_types') and change.vehicle_type not in resource.policy['vehicle_types']:
            raise AppError('ERR-SLOT-INELIGIBLE', 'Bãi xe không hỗ trợ loại xe.', 409)
        # Changing a parking resource never silently reprices an approved fee source.
        if resource.fee_vnd != row.policy_snapshot['fee_vnd']:
            from app.models.resident_portal import PortalFeeSource
            from app.services.portal_finance import change_fee_source, create_fee_source, fee_effective_date
            effective = fee_effective_date(body.data.get('effective_on'))
            source = session.scalar(select(PortalFeeSource).where(PortalFeeSource.source_kind == 'PARKING', PortalFeeSource.source_id == row.id).with_for_update())
            if source:
                if source.status == 'ACTIVE':
                    change_fee_source(session, 'PARKING', row.id, 'PAUSE', effective)
                    source.amount_vnd = resource.fee_vnd
                    source.policy_snapshot = {**source.policy_snapshot, 'fee_vnd': resource.fee_vnd}
                    change_fee_source(session, 'PARKING', row.id, 'RESUME', effective)
                else:
                    source.amount_vnd = resource.fee_vnd; source.version += 1
            else:
                source = create_fee_source(session, row, 'PARKING', resource.fee_vnd, f'Phí xe {change.plate}', resource.policy, recurring=True, basis='PER_VEHICLE')
            row.policy_snapshot = {**row.policy_snapshot, 'fee_vnd': resource.fee_vnd, 'resource_version': resource.version}
        event(session, context, row, 'BEFORE_CHANGE', body.reason)
        for slot in session.scalars(select(ParkingSlot).where(ParkingSlot.vehicle_id == row.id).with_for_update()):
            slot.vehicle_id = None; slot.version += 1
        row.plate = change.plate; row.vehicle_type = change.vehicle_type; row.resource_id = resource.id; row.version += 1
        for card in session.scalars(select(ResidentCredential).where(ResidentCredential.vehicle_id == row.id).with_for_update()):
            card.version += 1; card.sync_status = 'NOT_CONFIGURED'
        event(session, context, row, 'CHANGE', body.reason)
        return row, 'parking'
    return command(request, context, key, 'vehicle.change', {'id': str(identifier), **body.model_dump(mode='json')}, execute)


@router.get('/visitor-parking')
def visitor_list(request: Request, context: UserContext = Depends(get_current_user_context)):
    return listing(request, context, VisitorParking, SECURITY)


@router.post('/visitor-parking', status_code=201)
def visitor_entry(body: VisitorParkingInput, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        resource = load(session, context, PortalResource, body.resource_id, SECURITY, lock=True)
        from app.api.portal_registrations import _expire_offers
        _expire_offers(session, resource)
        occupied = session.scalar(select(func.count()).select_from(VehicleRegistration).where(VehicleRegistration.resource_id == resource.id, VehicleRegistration.status.in_(('ACTIVE', 'PAUSED', 'OFFERED')))) or 0
        visitors = session.scalar(select(func.count()).select_from(VisitorParking).where(VisitorParking.resource_id == resource.id, VisitorParking.status == 'ENTERED')) or 0
        if resource.kind != 'PARKING' or resource.status != 'OPEN' or occupied + visitors >= resource.capacity:
            raise AppError('ERR-CAPACITY', 'Bãi xe không còn suất.', 409)
        if body.entered_at > utc_now():
            raise AppError('ERR-CONTROL-INPUT', 'Giờ vào không được ở tương lai.', 422)
        row = VisitorParking(**scope_values(context, building_id=resource.building_id), **body.model_dump())
        row.plate = row.plate.upper().replace(' ', '')
        session.add(row); event(session, context, row, 'ENTER', 'Lượt gửi xe vãng lai.')
        return row, 'parking'
    return command(request, context, key, 'visitor.enter', body.model_dump(mode='json'), execute, roles=SECURITY)


@router.post('/visitor-parking/{identifier}/actions')
def visitor_action(identifier: UUID, body: PortalAction, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        row = load(session, context, VisitorParking, identifier, SECURITY, lock=True)
        require_version(row.version, body.expected_version)
        if body.action == 'EXIT':
            state(row, ('ENTERED',))
            try:
                ended = datetime.fromisoformat(body.data['exited_at'].replace('Z', '+00:00'))
                if ended.tzinfo is None or ended < row.entered_at or ended > utc_now():
                    raise ValueError()
            except (KeyError, ValueError, TypeError):
                raise AppError('ERR-CONTROL-INPUT', 'Giờ ra không hợp lệ.', 422) from None
            row.exited_at = ended; row.fee_vnd = max(1, math.ceil((ended - row.entered_at).total_seconds() / 3600)) * row.rate_vnd; row.status = 'EXITED'
        elif body.action == 'RECEIPT':
            state(row, ('EXITED',))
            reference = body.data.get('reference', '')
            if not isinstance(reference, str) or not 3 <= len(reference) <= 150 or row.fee_vnd <= 0:
                raise AppError('ERR-CONTROL-INPUT', 'Cần mã chứng từ thu hợp lệ.', 422)
            if session.scalar(select(VisitorParking.id).where(*context.scope_conditions(VisitorParking), VisitorParking.receipt_reference == reference)):
                raise AppError('ERR-CONFLICT', 'Chứng từ thu đã được dùng.', 409)
            row.receipt_reference = reference; row.paid_vnd = row.fee_vnd; row.status = 'PAID'
        elif body.action == 'RECONCILE':
            state(row, ('PAID', 'EXITED'))
            if row.paid_vnd != row.fee_vnd:
                raise AppError('ERR-RECONCILIATION', 'Lượt gửi xe chưa đủ chứng từ thu.', 409)
            row.status = 'RECONCILED'
        else:
            raise AppError('ERR-STATE-TRANSITION', 'Thao tác lượt gửi xe không hợp lệ.', 409)
        row.version += 1; event(session, context, row, body.action, body.reason)
        return row, 'parking'
    return command(request, context, key, 'visitor.' + body.action, {'id': str(identifier), **body.model_dump(mode='json')}, execute, roles=SECURITY)


@router.get('/card-blanks')
def blanks(request: Request, context: UserContext = Depends(get_current_user_context)):
    return listing(request, context, CardBlank, SECURITY)


@router.post('/card-blanks', status_code=201)
def blank_create(body: BlankInput, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        building_scope(session, context, body.building_id, SECURITY)
        row = CardBlank(**scope_values(context, building_id=body.building_id), code=body.code)
        session.add(row); return row, 'parking'
    return command(request, context, key, 'blank.create', body.model_dump(mode='json'), execute, roles=SECURITY)


@router.post('/card-blanks/{identifier}/actions')
def blank_action(identifier: UUID, body: PortalAction, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        row = load(session, context, CardBlank, identifier, SECURITY, lock=True)
        require_version(row.version, body.expected_version); state(row, ('AVAILABLE',))
        if body.action == 'ISSUE':
            card = load(session, context, ResidentCredential, as_uuid(body.data.get('credential_id')), SECURITY, lock=True)
            if card.status != 'ACTIVE' or card.building_id != row.building_id or session.scalar(select(CardBlank.id).where(CardBlank.credential_id == card.id)):
                raise AppError('ERR-CREDENTIAL-INELIGIBLE', 'Thẻ không đủ điều kiện gán phôi.', 409)
            if session.scalar(select(ResidentCredential.id).where(ResidentCredential.site_id == row.site_id, ResidentCredential.code == row.code, ResidentCredential.id != card.id)):
                raise AppError('ERR-CONFLICT', 'Mã thẻ đã được dùng.', 409)
            card.code = row.code; card.version += 1; card.sync_status = 'NOT_CONFIGURED'
            row.credential_id = card.id; row.status = 'ISSUED'
        elif body.action == 'DISCARD':
            row.status = 'DISCARDED'
        else:
            raise AppError('ERR-STATE-TRANSITION', 'Thao tác phôi thẻ không hợp lệ.', 409)
        row.version += 1; event(session, context, row, body.action, body.reason)
        return row, 'parking'
    return command(request, context, key, 'blank.' + body.action, {'id': str(identifier), **body.model_dump(mode='json')}, execute, roles=SECURITY)


@router.post('/credentials/{identifier}/scope')
def card_scope(identifier: UUID, body: PortalAction, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        card = load(session, context, ResidentCredential, identifier, SECURITY, lock=True)
        require_version(card.version, body.expected_version); state(card, ('ACTIVE',))
        areas = body.data.get('areas')
        if not isinstance(areas, list) or not 1 <= len(areas) <= 30 or any(not isinstance(a, str) or not 1 <= len(a) <= 80 for a in areas):
            raise AppError('ERR-CONTROL-INPUT', 'Cần danh sách khu vực được phép.', 422)
        card.access_scope = list(dict.fromkeys(areas))
        if card.vehicle_id is None:
            from app.services.access_cards import assert_card_authority
            assert_card_authority(session, card)
        card.version += 1; card.sync_status = 'NOT_CONFIGURED'
        event(session, context, card, 'ACCESS_SCOPE', body.reason)
        return card, 'parking'
    return command(request, context, key, 'card.scope', {'id': str(identifier), **body.model_dump(mode='json')}, execute, roles=SECURITY)


@router.get('/integrations')
def endpoints(request: Request, context: UserContext = Depends(get_current_user_context)):
    return listing(request, context, IntegrationEndpoint, ('admin', 'director'))


@router.post('/integrations', status_code=201)
def endpoint_create(body: EndpointInput, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        building_scope(session, context, body.building_id, ('admin', 'director'))
        row = IntegrationEndpoint(**scope_values(context, building_id=body.building_id), code=body.code, kind=body.kind)
        session.add(row); return row, 'profile'
    return command(request, context, key, 'integration.create', body.model_dump(mode='json'), execute, roles=('admin', 'director'))


@router.get('/deliveries')
def deliveries(request: Request, context: UserContext = Depends(get_current_user_context)):
    return listing(request, context, IntegrationDelivery, ('admin', 'director'))


@router.post('/integrations/{identifier}/queue')
def queue_card(identifier: UUID, body: PortalAction, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        endpoint = load(session, context, IntegrationEndpoint, identifier, ('admin', 'director'), lock=True)
        require_version(endpoint.version, body.expected_version)
        if endpoint.adapter != 'NOT_CONFIGURED':
            from app.services.integration_exchange import queue
            return queue(session, context, endpoint, 'CREDENTIAL', as_uuid(body.data.get('credential_id'))), 'profile'
        card = load(session, context, ResidentCredential, as_uuid(body.data.get('credential_id')), ('admin', 'director'), lock=True)
        if endpoint.kind not in ('ACCESS', 'PARKING') or card.building_id != endpoint.building_id:
            raise scope_not_found()
        authority = None
        if card.vehicle_id is None:
            from app.services.access_cards import assert_card_authority
            from app.models.operational_control import OperationsRecord
            assert_card_authority(session, card)
            authority = session.get(OperationsRecord, card.authorization_record_id) if card.authorization_record_id else None
        row = session.scalar(select(IntegrationDelivery).where(IntegrationDelivery.endpoint_id == endpoint.id, IntegrationDelivery.source_id == card.id, IntegrationDelivery.source_version == card.version))
        if row and authority and row.desired_state.get('authorization_version') != authority.version:
            row.status = 'SUPERSEDED'; row.version += 1
            card.version += 1; card.sync_status = 'NOT_CONFIGURED'
            event(session, context, card, 'AUTHORITY_REVISION', 'Hồ sơ tiếp đón thay phiên bản; lập lệnh mới.')
            row = None
        if row is None:
            row = IntegrationDelivery(**scope_values(context, building_id=endpoint.building_id), endpoint_id=endpoint.id, source_type='CREDENTIAL', source_id=card.id, source_version=card.version,
                desired_state={'status': card.status, 'areas': card.access_scope, 'valid_to': card.valid_to.isoformat(),
                    **({'authorization_id': str(authority.id), 'authorization_version': authority.version, 'valid_from_at': authority.data['starts_at'], 'valid_until_at': authority.data['ends_at']} if authority else {})})
            session.add(row)
        return row, 'profile'
    return command(request, context, key, 'integration.queue', {'id': str(identifier), **body.model_dump(mode='json')}, execute, roles=('admin', 'director'))


@router.post('/deliveries/{identifier}/actions')
def delivery_action(identifier: UUID, body: PortalAction, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        row = load(session, context, IntegrationDelivery, identifier, ('admin', 'director'), lock=True)
        require_version(row.version, body.expected_version)
        endpoint = load(session, context, IntegrationEndpoint, row.endpoint_id, ('admin', 'director'), lock=True)
        if endpoint.adapter != 'NOT_CONFIGURED' or row.source_type != 'CREDENTIAL':
            from app.services.integration_exchange import dispatch
            dispatch(session, context, row, body)
            row.version += 1; event(session, context, row, body.action, body.reason)
            return row, 'profile'
        card = load(session, context, ResidentCredential, row.source_id, ('admin', 'director'), lock=True)
        authority_stale = False
        if card.vehicle_id is None:
            from app.services.access_cards import assert_card_authority
            from app.models.operational_control import OperationsRecord
            try:
                assert_card_authority(session, card)
                authority = session.get(OperationsRecord, card.authorization_record_id) if card.authorization_record_id else None
                authority_stale = bool(authority and row.desired_state.get('authorization_version') != authority.version)
            except AppError:
                authority_stale = True
        if row.source_version != card.version or row.desired_state['status'] != card.status or authority_stale:
            row.status = 'SUPERSEDED'
        elif body.action == 'RETRY':
            # No device vendor/protocol selected. Never fabricate a successful ACK.
            row.status = 'NOT_CONFIGURED'; row.attempts += 1
        else:
            raise AppError('ERR-ADAPTER-NOT-CONFIGURED', 'Chưa cấu hình adapter thiết bị để nhận kết quả.', 409)
        row.version += 1; event(session, context, row, body.action, body.reason)
        return row, 'profile'
    return command(request, context, key, 'delivery.' + body.action, {'id': str(identifier), **body.model_dump(mode='json')}, execute, roles=('admin', 'director'))


@router.post('/content/{identifier}/responses', status_code=201)
def community_response(identifier: UUID, body: CommunityAnswer, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        context.assert_role('resident'); unit = unit_for(session, context, body.unit_id, 'documents', owner=False)
        row = session.scalar(select(PortalContent).where(PortalContent.id == identifier, *context.scope_conditions(PortalContent)).with_for_update())
        now = utc_now()
        if row is None or row.status != 'PUBLISHED' or row.publish_at > now or row.kind not in ('EVENT', 'SURVEY', 'VOTE') or row.building_id not in (None, unit.building_id) or row.unit_id not in (None, unit.id):
            raise scope_not_found()
        if row.starts_at and now < row.starts_at or row.ends_at and now >= row.ends_at:
            raise AppError('ERR-COMMUNITY-CLOSED', 'Ngoài thời gian tiếp nhận.', 409)
        if row.kind == 'VOTE':
            if not row.policy.get('confirmed_rule_reference'):
                raise AppError('ERR-POLICY-INCOMPLETE', 'Chưa xác nhận quy trình biểu quyết.', 409)
            unit_for(session, context, body.unit_id, 'documents', owner=True)
        if row.kind in ('SURVEY', 'VOTE') and body.answer not in row.policy.get('options', []):
            raise AppError('ERR-CONTROL-INPUT', 'Lựa chọn ngoài danh sách công bố.', 422)
        if session.scalar(select(CommunityResponse.id).where(CommunityResponse.content_id == row.id, CommunityResponse.unit_id == unit.id)):
            raise AppError('ERR-CONFLICT', 'Căn hộ đã có phản hồi.', 409)
        count = session.scalar(select(func.coalesce(func.sum(CommunityResponse.quantity), 0)).where(CommunityResponse.content_id == row.id)) or 0
        if row.kind == 'EVENT' and row.policy.get('capacity') and count + body.quantity > row.policy['capacity']:
            raise AppError('ERR-CAPACITY', 'Sự kiện đã đủ số người đăng ký.', 409)
        response = CommunityResponse(**scope_values(context, unit), content_id=row.id, answer=body.answer, quantity=body.quantity if row.kind == 'EVENT' else 1)
        session.add(response); return response, 'documents'
    return command(request, context, key, 'community.respond', {'id': str(identifier), **body.model_dump(mode='json')}, execute, roles=MANAGEMENT)


@router.get('/content/{identifier}/responses')
def community_results(identifier: UUID, request: Request, unit_id: UUID | None = None, context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        if resident(context):
            unit = unit_for(session, context, unit_id, 'documents')
            row = session.scalar(select(PortalContent).where(PortalContent.id == identifier, *context.scope_conditions(PortalContent), PortalContent.status.in_(('PUBLISHED', 'CLOSED'))))
            if row is None or row.building_id not in (None, unit.building_id) or row.unit_id not in (None, unit.id):
                raise scope_not_found()
            conditions = (CommunityResponse.unit_id == unit.id,)
        else:
            row = load(session, context, PortalContent, identifier, MANAGEMENT)
            conditions = ()
        rows = session.scalars(select(CommunityResponse).where(CommunityResponse.content_id == row.id, *conditions)).all()
        return {'items': [view(r) for r in rows], 'totals': {a: sum(r.quantity for r in rows if r.answer == a) for a in sorted({r.answer for r in rows})}}


@router.get('/templates')
def templates(request: Request, context: UserContext = Depends(get_current_user_context)):
    return listing(request, context, NotificationTemplate, MANAGEMENT)


@router.post('/templates', status_code=201)
def create_template(body: TemplateInput, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        import string
        building_scope(session, context, body.building_id, MANAGEMENT)
        session.execute(select(func.pg_advisory_xact_lock(int.from_bytes(hashlib.sha256(f'{context.assert_active_site()}:{body.code}'.encode()).digest()[:8], 'big', signed=True))))
        try:
            parts = list(string.Formatter().parse(body.title + body.body))
            fields = {field for _, field, spec, conversion in parts if field is not None}
            if fields != set(body.required_fields) or any(not f.isidentifier() for f in fields) or any(spec or conversion for _, field, spec, conversion in parts):
                raise ValueError()
        except ValueError:
            raise AppError('ERR-TEMPLATE-FIELDS', 'Tên biến mẫu phải khớp danh sách trường yêu cầu.', 422) from None
        revision = (session.scalar(select(func.max(NotificationTemplate.revision)).where(NotificationTemplate.site_id == context.assert_active_site(), NotificationTemplate.code == body.code)) or 0) + 1
        row = NotificationTemplate(**scope_values(context, building_id=body.building_id), revision=revision, **body.model_dump(exclude={'building_id'}))
        session.add(row); return row, 'profile'
    return command(request, context, key, 'template.create', body.model_dump(mode='json'), execute)


@router.get('/preferences')
def preferences(request: Request, context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        return {'items': [view(r) for r in session.scalars(select(NotificationPreference).where(*context.scope_conditions(NotificationPreference), NotificationPreference.account_id == context.account_id))]}


@router.post('/preferences')
def preference_save(body: PreferenceInput, request: Request, context: UserContext = Depends(get_current_user_context)):
    if body.category in ('BILLING', 'SECURITY') and not body.enabled:
        raise AppError('ERR-MANDATORY-NOTIFICATION', 'Thông báo tài chính/an toàn bắt buộc không được tắt.', 422)
    with request.app.state.database.get_session() as session:
        session.execute(select(func.pg_advisory_xact_lock(int.from_bytes(hashlib.sha256(f'pref:{context.account_id}'.encode()).digest()[:8], 'big', signed=True))))
        row = session.scalar(select(NotificationPreference).where(*context.scope_conditions(NotificationPreference), NotificationPreference.account_id == context.account_id, NotificationPreference.category == body.category).with_for_update())
        if row is None:
            row = NotificationPreference(**scope_values(context), **body.model_dump()); session.add(row)
        else:
            row.channel = body.channel; row.enabled = body.enabled; row.version += 1
        session.flush(); result = view(row); session.commit(); return result


@router.get('/jobs')
def schedules(request: Request, context: UserContext = Depends(get_current_user_context)):
    return listing(request, context, JobSchedule, ('admin', 'director'))


@router.get('/job-runs')
def runs(request: Request, context: UserContext = Depends(get_current_user_context)):
    return listing(request, context, JobRun, ('admin', 'director'))


@router.post('/job-runs/{identifier}/actions')
def run_action(identifier:UUID,body:PortalAction,request:Request,context:UserContext=Depends(get_current_user_context),key:str=Header(...,alias='Idempotency-Key')):
    def execute(session):
        run=load(session,context,JobRun,identifier,('admin','director'))
        schedule=load(session,context,JobSchedule,run.schedule_id,('admin','director'),lock=True)
        run=load(session,context,JobRun,identifier,('admin','director'),lock=True);require_version(run.version,body.expected_version)
        state(run,('FAILED','PARTIAL'))
        if schedule.next_run_at!=run.scheduled_at:raise AppError('ERR-JOB-SOURCE-STALE','Lịch đã chuyển sang mốc khác.',409)
        if body.action=='RETRY':
            return run_schedule(session,context,request,schedule,retry=True),'profile'
        if body.action!='REBASE_FAILURES':raise AppError('ERR-STATE-TRANSITION','Thao tác lượt chạy không hợp lệ.',409)
        from app.services.business_jobs import candidates
        current={(i['source_type'],i['source_id'],i['subtype']):i for i in candidates(session,context,schedule,run.scheduled_at)}
        items=[]
        for item in run.result['items']:
            if item['status']=='SUCCEEDED':items.append(item);continue
            fresh=current.get((item['source_type'],item['source_id'],item['subtype']))
            items.append({**fresh,'status':'PENDING','previous_attempt':item} if fresh else {**item,'status':'SUCCEEDED','result':{'skipped':'Không còn đủ điều kiện tại cutoff; BQL đã đối chiếu.'}})
        run.result={**run.result,'items':items};run.version+=1;event(session,context,run,body.action,body.reason)
        return run,'profile'
    return command(request,context,key,'job-run.'+body.action,{'id':str(identifier),**body.model_dump(mode='json')},execute,roles=('admin','director'))


@router.post('/jobs', status_code=201)
def schedule_create(body: JobInput, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        building_scope(session, context, body.building_id, ('admin', 'director'))
        row = JobSchedule(**scope_values(context, building_id=body.building_id), **body.model_dump(exclude={'building_id'})); session.add(row)
        return row, 'profile'
    return command(request, context, key, 'schedule.create', body.model_dump(mode='json'), execute, roles=('admin', 'director'))


def run_schedule(session, context, request, row, *, retry=False):
    state(row, ('ACTIVE',))
    from app.services.business_jobs import run_business_schedule
    return run_business_schedule(session,context,request,row,retry=retry)


def run_due_schedules(session, context, request):
    context.assert_role('admin', 'director')
    rows = session.scalars(select(JobSchedule).where(*context.scope_conditions(JobSchedule), *staff_conditions(context, JobSchedule, ('admin', 'director')), JobSchedule.status == 'ACTIVE', JobSchedule.next_run_at <= utc_now()).order_by(JobSchedule.next_run_at, JobSchedule.id).limit(100).with_for_update(skip_locked=True)).all()
    return {'scheduled_runs': len(rows), 'failed': sum(run_schedule(session, context, request, row).status in ('FAILED','PARTIAL') for row in rows)}


@router.post('/jobs/{identifier}/actions')
def job_action(identifier: UUID, body: PortalAction, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        row = load(session, context, JobSchedule, identifier, ('admin', 'director'), lock=True)
        require_version(row.version, body.expected_version)
        if body.action in ('RUN', 'RETRY'):
            row = run_schedule(session, context, request, row, retry=body.action == 'RETRY')
        elif body.action in ('PAUSE', 'RESUME'):
            row.status = 'PAUSED' if body.action == 'PAUSE' else 'ACTIVE'; row.version += 1
        else:
            raise AppError('ERR-STATE-TRANSITION', 'Thao tác tác vụ không hợp lệ.', 409)
        return row, 'profile'
    return command(request, context, key, 'job.' + body.action, {'id': str(identifier), **body.model_dump(mode='json')}, execute, roles=('admin', 'director'))


@router.get('/history/{parent_type}/{identifier}')
def history(parent_type: str, identifier: UUID, request: Request, context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        from app.models.operational_control import OperationsRecord, Meter, MeterAssignment, MeterReading, TreasuryAccount, Expense, StockItem, StockMovement, TreasuryMovement, NotificationDelivery
        from app.models.resident_portal import PortalFeeSource
        from app.services.operational_control import FINANCIAL, TECHNICAL
        specs = [(ParkingSlot, MANAGEMENT), (VisitorParking, SECURITY), (CardBlank, SECURITY), (ResidentCredential, SECURITY),
            (VehicleRegistration, MANAGEMENT), (IntegrationEndpoint, ('admin', 'director')), (IntegrationDelivery, ('admin', 'director')),
            (JobSchedule, ('admin', 'director')), (JobRun, ('admin', 'director')), (NotificationTemplate, MANAGEMENT), (NotificationDelivery, MANAGEMENT),
            (MeterAssignment, TECHNICAL), (Meter, TECHNICAL), (MeterReading, TECHNICAL), (StockItem, TECHNICAL), (StockMovement, TECHNICAL),
            (TreasuryAccount, FINANCIAL), (TreasuryMovement, FINANCIAL), (Expense, FINANCIAL), (PortalFeeSource, FINANCIAL)]
        if parent_type == OperationsRecord.__tablename__:
            from app.services.operations_records import definition
            candidate = session.get(OperationsRecord, identifier)
            if candidate is None:
                raise scope_not_found()
            _, roles = definition(candidate.kind)
            load(session, context, OperationsRecord, identifier, roles)
        else:
            model, roles = next(((m, r) for m, r in specs if m.__tablename__ == parent_type), (None, None))
            if model is None:
                raise scope_not_found()
            load(session, context, model, identifier, roles)
        return {'items': [view(r) for r in session.scalars(select(ControlEvent).where(*context.scope_conditions(ControlEvent), ControlEvent.parent_type == parent_type, ControlEvent.parent_id == identifier).order_by(ControlEvent.created_at, ControlEvent.id))]}
