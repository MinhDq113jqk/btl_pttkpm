"""Source imports and controlled parking discrepancy resolution, no guessed fees."""
from uuid import UUID
from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import select
from app.core.exceptions import AppError
from app.core.policy import UserContext, get_current_user_context, scope_not_found
from app.models.account import Account
from app.models.account_parking import ParkingUsageBatch, ParkingReconciliation, ParkingDiscrepancy
from app.models.operational_control import ParkingSlot
from app.models.resident_portal import PortalResource, VehicleRegistration
from app.schemas.account_parking import UsageBatchInput, ReconcileInput, ParkingDecision
from app.services.operational_control import load, event, MANAGEMENT
from app.services.resident_portal import command, scope_values, staff_conditions, unit_for, view
from app.services.r2 import require_version, utc_now
from app.services.parking_reconciliation import collect, digest

router = APIRouter(prefix='/portal/control', tags=['Parking reconciliation'])
READERS = (*MANAGEMENT, 'security')


def parking_resource(session, context, identifier, roles, lock=False):
    row = load(session, context, PortalResource, identifier, roles, lock=lock)
    if row.kind != 'PARKING':
        raise scope_not_found()
    return row


@router.get('/parking-usage')
def usage(request: Request, resource_id: UUID, context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        parking_resource(session, context, resource_id, READERS)
        return {'items': [view(b) for b in session.scalars(select(ParkingUsageBatch).where(
            ParkingUsageBatch.resource_id == resource_id, *context.scope_conditions(ParkingUsageBatch)).order_by(ParkingUsageBatch.created_at.desc()).limit(200))]}


@router.post('/parking-usage', status_code=201)
def import_usage(body: UsageBatchInput, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        resource = parking_resource(session, context, body.resource_id, READERS, True)
        if body.ends_at > utc_now():
            raise AppError('ERR-CONTROL-INPUT', 'Không xác nhận dữ liệu lượt sử dụng trong tương lai.', 422)
        for entry in body.entries:
            if entry.unit_id and unit_for(session, context, entry.unit_id, roles=READERS).building_id != resource.building_id:
                raise scope_not_found()
            if entry.holder_account_id and not session.scalar(select(Account.id).where(
                Account.id == entry.holder_account_id, Account.tenant_id == context.tenant_id)):
                raise scope_not_found()
        existing = session.scalar(select(ParkingUsageBatch).where(ParkingUsageBatch.resource_id == resource.id,
            ParkingUsageBatch.source_reference == body.source_reference))
        data = body.model_dump(mode='json')
        if existing:
            if digest(UsageBatchInput.model_validate({k: view(existing)[k] for k in data}).model_dump(mode='json')) != digest(data):
                raise AppError('ERR-CONFLICT', 'Mã nguồn đã dùng với nội dung khác; hãy cấp mã nguồn mới.', 409)
            return existing, 'parking'
        row = ParkingUsageBatch(**scope_values(context, building_id=resource.building_id), **body.model_dump(exclude={'entries'}), entries=data['entries'])
        session.add(row); event(session, context, row, 'IMPORT', body.source_reference)
        return row, 'parking'
    return command(request, context, key, 'parking.usage.import', body.model_dump(mode='json'), execute, roles=READERS)


@router.get('/parking-reconciliations')
def reports(request: Request, building_id: UUID | None = None, context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        conditions = [*context.scope_conditions(ParkingReconciliation), *staff_conditions(context, ParkingReconciliation, READERS)]
        if building_id:
            context.assert_building_role(building_id, *READERS); conditions.append(ParkingReconciliation.building_id == building_id)
        rows = session.scalars(select(ParkingReconciliation).where(*conditions).order_by(ParkingReconciliation.created_at.desc()).limit(100)).all()
        return {'items': [{k: v for k, v in view(r).items() if k != 'snapshot'} | {'usage_data_status': r.snapshot['usage_data_status'],
            'finding_count': len(r.snapshot['finding_ids'])} for r in rows]}


@router.get('/parking-reconciliations/{identifier}')
def report(identifier: UUID, request: Request, context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        row = load(session, context, ParkingReconciliation, identifier, READERS)
        findings = session.scalars(select(ParkingDiscrepancy).where(ParkingDiscrepancy.id.in_(
            [UUID(i) for i in row.snapshot['finding_ids']]), *context.scope_conditions(ParkingDiscrepancy))).all()
        owners = {a.id: a.full_name for a in session.scalars(select(Account).where(
            Account.id.in_({f.account_id for f in findings}), Account.tenant_id == context.tenant_id))}
        return {**view(row), 'findings': [{**view(f), 'owner_name': owners.get(f.account_id)} for f in findings]}


@router.post('/parking-reconciliations', status_code=201)
def reconcile(body: ReconcileInput, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        resource = parking_resource(session, context, body.resource_id, MANAGEMENT, True)
        as_of = utc_now()
        if body.ends_at > as_of:
            raise AppError('ERR-CONTROL-INPUT', 'Khoảng đối chiếu không được nằm trong tương lai.', 422)
        snapshot, findings = collect(session, resource, body.starts_at, body.ends_at, as_of, body.require_slots, body.policy_reference)
        source_digest = digest({'snapshot': snapshot, 'findings': findings})
        old = session.scalar(select(ParkingReconciliation).where(ParkingReconciliation.resource_id == resource.id, ParkingReconciliation.digest == source_digest))
        if old:
            return old, 'parking'
        row = ParkingReconciliation(**scope_values(context, building_id=resource.building_id), **body.model_dump(),
            as_of=as_of, digest=source_digest, snapshot=snapshot)
        session.add(row); session.flush(); identifiers = []
        for finding in findings:
            discrepancy = session.scalar(select(ParkingDiscrepancy).where(ParkingDiscrepancy.resource_id == resource.id,
                ParkingDiscrepancy.fingerprint == finding['fingerprint']))
            if discrepancy is None:
                discrepancy = ParkingDiscrepancy(**scope_values(context, building_id=resource.building_id), resource_id=resource.id,
                    report_id=row.id, **finding)
                session.add(discrepancy); event(session, context, discrepancy, 'OPEN', body.policy_reference)
            identifiers.append(str(discrepancy.id))
        row.snapshot = {**snapshot, 'finding_ids': identifiers}
        event(session, context, row, 'SCAN', body.policy_reference)
        return row, 'parking'
    return command(request, context, key, 'parking.reconcile', body.model_dump(mode='json'), execute, roles=MANAGEMENT)


@router.post('/parking-discrepancies/{identifier}/resolve')
def resolve(identifier: UUID, body: ParkingDecision, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        initial = load(session, context, ParkingDiscrepancy, identifier, MANAGEMENT)
        resource = parking_resource(session, context, initial.resource_id, MANAGEMENT, True)
        row = load(session, context, ParkingDiscrepancy, identifier, MANAGEMENT, lock=True)
        require_version(row.version, body.expected_version)
        if row.status != 'OPEN':
            raise AppError('ERR-STATE-TRANSITION', 'Sai lệch đã có quyết định xử lý.', 409)
        report = load(session, context, ParkingReconciliation, row.report_id, MANAGEMENT)
        _, current = collect(session, resource, report.starts_at, report.ends_at, utc_now(), report.require_slots, report.policy_reference)
        if row.fingerprint not in {f['fingerprint'] for f in current}:
            raise AppError('ERR-SOURCE-CHANGED', 'Nguồn đã thay đổi. Cần đối chiếu lại trước khi xử lý.', 409)
        effect = None
        if body.action == 'RELEASE_INVALID_SLOT':
            if row.code != 'INVALID_SLOT':
                raise AppError('ERR-CONTROL-INPUT', 'Chỉ giải phóng ô trong sai lệch ô không hợp lệ.', 422)
            slot = load(session, context, ParkingSlot, UUID(row.source['slot']['id']), MANAGEMENT, lock=True)
            effect = {'slot_id': str(slot.id), 'before_vehicle_id': str(slot.vehicle_id), 'after_vehicle_id': None}
            slot.vehicle_id = None; slot.version += 1; event(session, context, slot, 'RELEASE', body.reason)
        elif body.action == 'ASSIGN_MISSING_SLOT':
            if row.code != 'MISSING_SLOT' or body.slot_id is None or not row.source['owner_valid'] or resource.status != 'OPEN':
                raise AppError('ERR-CONTROL-INPUT', 'Cần sai lệch thiếu ô, chủ thể hợp lệ và bãi đang mở.', 422)
            vehicle = load(session, context, VehicleRegistration, UUID(row.source['vehicle']['id']), MANAGEMENT, lock=True)
            slot = load(session, context, ParkingSlot, body.slot_id, MANAGEMENT, lock=True)
            if slot.resource_id != resource.id or slot.status != 'OPEN' or slot.vehicle_id or vehicle.vehicle_type not in slot.vehicle_types:
                raise AppError('ERR-CONFLICT', 'Ô được chọn không còn phù hợp hoặc đang có xe.', 409)
            if session.scalar(select(ParkingSlot.id).where(ParkingSlot.vehicle_id == vehicle.id)):
                raise AppError('ERR-CONFLICT', 'Xe đã có ô đỗ.', 409)
            slot.vehicle_id = vehicle.id; slot.version += 1
            effect = {'slot_id': str(slot.id), 'before_vehicle_id': None, 'after_vehicle_id': str(vehicle.id)}
            event(session, context, slot, 'ASSIGN', body.reason)
        row.status = 'RESOLVED'; row.version += 1
        row.decision = {'action': body.action, 'reason': body.reason, 'evidence_reference': body.evidence_reference,
            'actor_id': str(context.account_id), 'at': utc_now().isoformat(), 'effect': effect}
        event(session, context, row, body.action, body.reason)
        return row, 'parking'
    return command(request, context, key, 'parking.resolve', {'id': str(identifier), **body.model_dump(mode='json')}, execute, roles=MANAGEMENT)
