"""SAD T01–T08 scoped histories, comparison and personal acknowledgements."""
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID
from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import select, func, or_
from app.core.exceptions import AppError
from app.core.policy import UserContext, get_current_user_context, scope_not_found
from app.models.operational_control import OperationsRecord, Meter, MeterAssignment, MeterReading, TreasuryAccount, Expense, StockItem
from app.schemas.sad_work import MeterAssignmentInput
from app.schemas.resident_portal import PortalAction
from app.services.resident_portal import command, scope_values, unit_for, view, staff_conditions
from app.services.operational_control import TECHNICAL, FINANCIAL, MANAGEMENT, load, state, event, as_uuid, financial_lock
from app.services.r2 import require_version, utc_now
from app.services.sad_work import active_on, assignment_candidate

router = APIRouter(prefix='/portal/operations', tags=['SAD T01–T08'])
WORKFORCE = ('admin', 'director', 'cskh', 'technical_lead', 'technician', 'cleaning', 'security')


@router.get('/eligible-workers')
def eligible_workers(request: Request, building_id: UUID, target_id: UUID, target_type: str, required_skill: str, sop_id: UUID | None = None, context: UserContext = Depends(get_current_user_context)):
    from types import SimpleNamespace
    from app.services.operational_control import building_scope
    if target_type not in ('WORK_ORDER', 'CLEANING', 'SECURITY'):
        raise AppError('ERR-WORK-TYPE', 'Loại công việc không hợp lệ.', 422)
    with request.app.state.database.get_session() as session:
        building_scope(session, context, building_id, (*MANAGEMENT, 'technical_lead'))
        rosters = session.scalars(select(OperationsRecord).where(*context.scope_conditions(OperationsRecord), OperationsRecord.building_id == building_id, OperationsRecord.kind == 'ROSTER', OperationsRecord.status.in_(('APPROVED', 'IN_PROGRESS')))).all()
        items = []
        for roster in rosters:
            row = SimpleNamespace(building_id=building_id, site_id=context.assert_active_site(), tenant_id=context.tenant_id, status='DRAFT', data={'roster_id': str(roster.id), 'target_id': str(target_id), 'target_type': target_type, 'required_skill': required_skill, 'sop_id': str(sop_id) if sop_id else None})
            try:
                _, staff = assignment_candidate(session, context, row)
                items.append({'roster_id': roster.id, 'staff_id': staff.id, 'name': staff.title, 'eligible': True, 'reason': None})
            except AppError as failure:
                items.append({'roster_id': roster.id, 'name': roster.title, 'eligible': False, 'reason': failure.message})
        return {'items': items}


@router.get('/meter-assignments')
def assignments(request: Request, context: UserContext = Depends(get_current_user_context)):
    context.assert_role(*TECHNICAL)
    with request.app.state.database.get_session() as session:
        return {'items': [view(r) for r in session.scalars(select(MeterAssignment).where(*context.scope_conditions(MeterAssignment), *staff_conditions(context, MeterAssignment, TECHNICAL)).order_by(MeterAssignment.valid_from.desc()))]}


@router.post('/meter-assignments', status_code=201)
def assign_meter(body: MeterAssignmentInput, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        meter = load(session, context, Meter, body.meter_id, TECHNICAL, lock=True); state(meter, ('ACTIVE',))
        unit = unit_for(session, context, body.unit_id, roles=TECHNICAL) if body.unit_id else None
        if unit and unit.building_id != meter.building_id:
            raise scope_not_found()
        if body.valid_from < meter.valid_from:
            raise AppError('ERR-METER-ASSIGNMENT', 'Lịch gắn không được trước ngày lắp.', 422)
        latest = session.scalar(select(MeterReading).where(MeterReading.meter_id == meter.id).order_by(MeterReading.read_on.desc()).limit(1))
        if not latest or latest.status != 'VERIFIED' or latest.read_on != body.valid_from:
            raise AppError('ERR-METER-ASSIGNMENT-BOUNDARY', 'Đổi điểm đo cần chỉ số đã xác minh tại mốc đổi, không sửa lịch sử đã đo.', 409)
        peers = session.scalars(select(MeterAssignment).where(MeterAssignment.meter_id == meter.id).with_for_update()).all()
        for peer in peers:
            if peer.valid_from >= body.valid_from:
                raise AppError('ERR-METER-ASSIGNMENT-OVERLAP', 'Mốc gắn phải nối tiếp lịch sử.', 409)
            if peer.valid_to is None:
                event(session, context, peer, 'BEFORE_END', body.evidence_reference)
                peer.valid_to = body.valid_from; peer.version += 1
                event(session, context, peer, 'END', body.evidence_reference)
        row = MeterAssignment(**scope_values(context, unit, building_id=meter.building_id), **body.model_dump(exclude={'unit_id'}))
        meter.unit_id = unit.id if unit else None; meter.version += 1
        session.add(row); event(session, context, row, 'ASSIGN', body.evidence_reference)
        return row, 'profile'
    return command(request, context, key, 'meter.assignment', body.model_dump(mode='json'), execute, roles=TECHNICAL)


@router.get('/master-data')
def master_data(request: Request, building_id: UUID, catalog: str | None = None, as_of: date | None = None, context: UserContext = Depends(get_current_user_context)):
    from app.services.operational_control import building_scope
    with request.app.state.database.get_session() as session:
        building_scope(session, context, building_id, WORKFORCE)
        rows = session.scalars(select(OperationsRecord).where(*context.scope_conditions(OperationsRecord), OperationsRecord.building_id == building_id, OperationsRecord.kind == 'MASTER_DATA', OperationsRecord.status == 'APPROVED')).all()
        return {'as_of': as_of or utc_now().date(), 'items': [view(r) for r in rows if active_on(r, as_of or utc_now().date()) and (catalog is None or r.data['catalog'] == catalog)]}


@router.post('/meter-assignments/{identifier}/actions')
def detach_meter(identifier: UUID, body: PortalAction, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        initial = load(session, context, MeterAssignment, identifier, TECHNICAL)
        meter = load(session, context, Meter, initial.meter_id, TECHNICAL, lock=True)
        row = load(session, context, MeterAssignment, identifier, TECHNICAL, lock=True)
        require_version(row.version, body.expected_version)
        if body.action != 'DETACH' or row.valid_to is not None:
            raise AppError('ERR-METER-ASSIGNMENT', 'Chỉ tháo lịch gắn đang mở.', 409)
        try: ends_on = date.fromisoformat(body.data.get('valid_to', ''))
        except (TypeError, ValueError): raise AppError('ERR-METER-ASSIGNMENT', 'Cần ngày tháo hợp lệ.', 422) from None
        latest = session.scalar(select(MeterReading).where(MeterReading.meter_id == meter.id).order_by(MeterReading.read_on.desc()).limit(1))
        if not latest or latest.status != 'VERIFIED' or latest.read_on != ends_on or ends_on <= row.valid_from:
            raise AppError('ERR-METER-ASSIGNMENT-BOUNDARY', 'Tháo cần chỉ số xác minh tại mốc kết thúc.', 409)
        row.valid_to = ends_on; row.version += 1; meter.unit_id = None; meter.version += 1
        event(session, context, row, 'DETACH', body.reason); return row, 'profile'
    return command(request, context, key, 'meter.detach', {'id': str(identifier), **body.model_dump(mode='json')}, execute, roles=TECHNICAL)


@router.get('/treasury/{identifier}/comparison')
def budget_comparison(identifier: UUID, request: Request, context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        budget = load(session, context, TreasuryAccount, identifier, FINANCIAL)
        expenses = session.scalars(select(Expense).where(Expense.budget_id == budget.id, Expense.status != 'REJECTED')).all()
        records = session.scalars(select(OperationsRecord).where(OperationsRecord.building_id == budget.building_id, *context.scope_conditions(OperationsRecord))).all()
        orders = [r for r in records if r.kind == 'PURCHASE' and r.data.get('budget_id') == str(budget.id) and r.status in ('APPROVED', 'COMPLETED')]
        deliveries = [r for r in records if r.kind == 'DELIVERY' and r.status == 'COMPLETED' and r.related_id in {o.id for o in orders}]
        settlements = {r.data['expense_id']: r for r in records if r.kind == 'ADVANCE_SETTLEMENT' and r.status in ('APPROVED', 'COMPLETED')}
        actual = sum(e.paid_vnd for e in expenses if e.kind != 'ADVANCE') + sum(settlements[str(e.id)].data['actual_vnd'] for e in expenses if e.kind == 'ADVANCE' and str(e.id) in settlements)
        advances = sum(e.paid_vnd for e in expenses if e.kind == 'ADVANCE' and str(e.id) not in settlements)
        accepted = sum(int(Decimal(o.data['selected_amount_vnd']) * min(Decimal(o.data['quantity']), sum((Decimal(d.data.get('accepted_quantity', d.data['quantity'])) for d in deliveries if d.related_id == o.id), Decimal(0))) / Decimal(o.data['quantity'])) for o in orders)
        return {'budget': view(budget), 'planned_vnd': budget.limit_vnd, 'committed_vnd': budget.reserved_vnd, 'accepted_vnd': accepted,
                'actual_vnd': actual, 'unsettled_advance_vnd': advances, 'cash_disbursed_vnd': sum(e.paid_vnd for e in expenses), 'variance_vnd': budget.limit_vnd-actual,
                'expenses': [view(e) for e in expenses], 'orders': [view(o) for o in orders], 'deliveries': [view(d) for d in deliveries],
                'explanations': [view(r) for r in records if r.kind == 'BUDGET_VARIANCE' and r.data['budget_id'] == str(budget.id)]}


@router.get('/my-work')
def my_work(request: Request, context: UserContext = Depends(get_current_user_context)):
    context.assert_role(*WORKFORCE)
    with request.app.state.database.get_session() as session:
        staff = session.scalars(select(OperationsRecord).where(*context.scope_conditions(OperationsRecord), OperationsRecord.kind == 'STAFF', OperationsRecord.status == 'APPROVED')).all()
        ids = {str(s.id) for s in staff if s.data['account_id'] == str(context.account_id)}
        rosters = session.scalars(select(OperationsRecord).where(*context.scope_conditions(OperationsRecord), OperationsRecord.kind == 'ROSTER')).all()
        roster_ids = {str(r.id) for r in rosters if r.data['staff_id'] in ids}
        rows = session.scalars(select(OperationsRecord).where(*context.scope_conditions(OperationsRecord), OperationsRecord.kind.in_(('TRAINING', 'WORK_ASSIGNMENT')), OperationsRecord.status == 'APPROVED')).all()
        items = []
        for row in rows:
            if row.kind == 'TRAINING' and ids & set(row.data['staff_ids']):
                own_ack = next((row.data.get('acknowledgements', {}).get(identifier) for identifier in ids & set(row.data['staff_ids'])
                                if row.data.get('acknowledgements', {}).get(identifier)), None)
                items.append({**view(row), 'my_acknowledgement': own_ack})
            elif row.kind == 'WORK_ASSIGNMENT' and row.data['roster_id'] in roster_ids:
                items.append(view(row))
        return {'items': items,
                'handoffs': [view(r) for r in rosters if r.data.get('handover_to_roster_id') in roster_ids and r.status != 'COMPLETED']}


@router.get('/records/{identifier}/contract-progress')
def contract_progress(identifier: UUID, request: Request, context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        contract = load(session, context, OperationsRecord, identifier, (*MANAGEMENT, 'accountant'))
        if contract.kind != 'CONTRACT': raise scope_not_found()
        rows = session.scalars(select(OperationsRecord).where(*context.scope_conditions(OperationsRecord), OperationsRecord.building_id == contract.building_id, OperationsRecord.kind == 'CONTRACT_MILESTONE', OperationsRecord.status.not_in(('REJECTED', 'CANCELLED')))).all()
        rows = [r for r in rows if r.data['contract_id'] == str(contract.id)]
        milestones = []
        for milestone in contract.data.get('milestone_items', []):
            evidence = next((r for r in rows if r.data['milestone_code'] == milestone['code']), None)
            milestones.append({**milestone, 'status': evidence.status if evidence else 'PENDING', 'acceptance': view(evidence) if evidence else None})
        totals = None
        if contract.data.get('purchase_id') and context.matching_grants(frozenset(FINANCIAL), contract.building_id):
            order = load(session, context, OperationsRecord, as_uuid(contract.data['purchase_id']), FINANCIAL)
            expenses = session.scalars(select(Expense).where(Expense.procurement_id == order.id, Expense.status != 'REJECTED')).all()
            totals = {'committed_vnd': order.data.get('remaining_commitment_vnd', 0), 'payable_vnd': sum(e.amount_vnd for e in expenses), 'paid_vnd': sum(e.paid_vnd for e in expenses), 'expenses': [view(e) for e in expenses]}
        return {'milestones': milestones, 'financial': totals, 'closing_decision': contract.data.get('closing_decision')}


@router.post('/my-work/{identifier}/acknowledge')
def acknowledge(identifier: UUID, body: PortalAction, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        financial_lock(session, context)
        row = load(session, context, OperationsRecord, identifier, WORKFORCE, lock=True)
        require_version(row.version, body.expected_version); state(row, ('APPROVED', 'IN_PROGRESS'))
        evidence = body.data.get('evidence_reference'); result = body.data.get('result')
        if not all(isinstance(v, str) and 3 <= len(v) <= 1000 for v in (evidence, result)):
            raise AppError('ERR-ACK-EVIDENCE', 'Tiếp nhận cần kết quả và bằng chứng.', 422)
        if row.kind == 'TRAINING' and body.action == 'ACK_TRAINING':
            if datetime.fromisoformat(row.data['scheduled_at']) > utc_now():
                raise AppError('ERR-TRAINING-TIME', 'Chưa tới thời điểm đào tạo.', 409)
            staff = session.scalars(select(OperationsRecord).where(*context.scope_conditions(OperationsRecord), OperationsRecord.building_id == row.building_id, OperationsRecord.kind == 'STAFF', OperationsRecord.status == 'APPROVED')).all()
            own = [s for s in staff if str(s.id) in row.data['staff_ids'] and s.data['account_id'] == str(context.account_id)]
            if len(own) != 1: raise scope_not_found()
            if str(own[0].id) in row.data.get('acknowledgements', {}):
                raise AppError('ERR-ACK-DUPLICATE', 'Đã xác nhận đào tạo.', 409)
            row.data = {**row.data, 'acknowledgements': {**row.data.get('acknowledgements', {}), str(own[0].id): {'sop_id': row.data['sop_id'], 'at': utc_now().isoformat(), 'actor_id': str(context.account_id), 'evidence_reference': evidence, 'result': result}}}
        elif row.kind == 'WORK_ASSIGNMENT' and body.action == 'ACCEPT_WORK':
            target, staff = assignment_candidate(session, context, row)
            if staff.data['account_id'] != str(context.account_id): raise scope_not_found()
            target.assigned_to_id = context.account_id
            if target.status in ('DRAFT', 'PLANNED') and row.data['target_type'] != 'SECURITY': target.status = 'ASSIGNED'
            target.version += 1
            row.data = {**row.data, 'accepted_at': utc_now().isoformat(), 'result': result, 'acceptance_evidence_reference': evidence}; row.status = 'COMPLETED'
        elif row.kind == 'ROSTER' and body.action == 'ACK_HANDOVER':
            from app.services.sad_work import record_ref
            receiver = record_ref(session, context, row, row.data.get('handover_to_roster_id'), 'ROSTER', ('APPROVED', 'IN_PROGRESS'))
            staff = record_ref(session, context, row, receiver.data['staff_id'], 'STAFF', ('APPROVED',))
            if staff.data['account_id'] != str(context.account_id): raise scope_not_found()
            row.data = {**row.data, 'handover_ack': {'at': utc_now().isoformat(), 'actor_id': str(context.account_id), 'evidence_reference': evidence, 'result': result}}; row.status = 'COMPLETED'
        else:
            raise AppError('ERR-ACK-KIND', 'Thao tác xác nhận không hợp lệ.', 422)
        row.version += 1; event(session, context, row, body.action, body.reason)
        return row, 'profile'
    return command(request, context, key, 'workforce.acknowledge', {'id': str(identifier), **body.model_dump(mode='json')}, execute, roles=WORKFORCE)
