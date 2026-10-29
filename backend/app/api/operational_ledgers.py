"""Meter, inventory and treasury controls with locked source balances."""
from datetime import date
from decimal import Decimal
from uuid import UUID
from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import func, select
from app.core.exceptions import AppError
from app.core.policy import UserContext, get_current_user_context, scope_not_found
from app.models.account import Account
from app.models.operational_control import Meter, MeterReading, StockItem, StockMovement, TreasuryAccount, TreasuryMovement, Expense, OperationsRecord
from app.schemas.operational_control import MeterInput, ReadingInput, MeterBillingInput, StockInput, StockCommand, TreasuryInput, ExpenseInput
from app.schemas.resident_portal import PortalAction
from app.services.operational_control import building_scope, load, event, state, independent, data_model, as_uuid, TECHNICAL, FINANCIAL, financial_lock
from app.services.resident_portal import command, scope_values, unit_for, view, staff_conditions
from app.services.r2 import require_version, utc_now
from app.api.portal_control import listing

router = APIRouter(prefix='/portal/operations', tags=['Operational ledgers'])


@router.get('/meters')
def meters(request: Request, context: UserContext = Depends(get_current_user_context)):
    return listing(request, context, Meter, (*TECHNICAL, 'accountant'))


def new_meter(session, context, body, replaces_id=None):
    building_scope(session, context, body.building_id, TECHNICAL)
    unit = unit_for(session, context, body.unit_id, roles=TECHNICAL) if body.unit_id else None
    if unit and unit.building_id != body.building_id:
        raise scope_not_found()
    if body.upstream_id:
        parent = load(session, context, Meter, body.upstream_id, TECHNICAL)
        if parent.commodity != body.commodity or parent.status != 'ACTIVE' or parent.building_id != body.building_id:
            raise AppError('ERR-METER-RELATION', 'Đồng hồ đầu nguồn không phù hợp.', 422)
    from app.services.sad_work import next_code
    from app.models.operational_control import MeterAssignment
    row = Meter(**scope_values(context, unit, building_id=body.building_id), **body.model_dump(exclude={'unit_id', 'building_id', 'code'}), code=next_code(session, context.assert_active_site(), 'MTR-' + body.commodity), replaces_id=replaces_id)
    session.add(row); session.flush()
    session.add(MeterAssignment(**scope_values(context, unit, building_id=body.building_id), meter_id=row.id, point=body.code,
        valid_from=body.valid_from, evidence_reference='INITIAL_ASSIGNMENT:' + row.code))
    return row


@router.post('/meters', status_code=201)
def meter_create(body: MeterInput, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        row = new_meter(session, context, body); event(session, context, row, 'ASSIGN', 'Gắn đồng hồ theo thời gian.')
        return row, 'profile'
    return command(request, context, key, 'meter.create', body.model_dump(mode='json'), execute, roles=TECHNICAL)


@router.get('/readings')
def readings(request: Request, context: UserContext = Depends(get_current_user_context)):
    return listing(request, context, MeterReading, (*TECHNICAL, 'accountant'))


@router.post('/readings', status_code=201)
def reading_create(body: ReadingInput, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        meter = load(session, context, Meter, body.meter_id, TECHNICAL, lock=True)
        state(meter, ('ACTIVE',))
        previous = session.scalar(select(MeterReading).where(MeterReading.meter_id == meter.id).order_by(MeterReading.read_on.desc()).limit(1))
        if body.read_on < meter.valid_from or body.read_on > utc_now().date() or previous and (body.read_on <= previous.read_on or previous.status != 'VERIFIED'):
            raise AppError('ERR-METER-SEQUENCE', 'Kỳ ghi không hợp lệ hoặc chỉ số trước chưa xác minh.', 409)
        from app.services.meter_billing import effective_reading
        base = effective_reading(session, previous).value if previous else meter.baseline
        if body.value < base:
            raise AppError('ERR-METER-DECREASE', 'Chỉ số giảm cần hồ sơ thay đồng hồ hoặc hiệu chỉnh.', 422)
        consumption = (body.value - base) * meter.multiplier
        if consumption > Decimal('99999999999999.9999'):
            raise AppError('ERR-METER-RANGE', 'Sản lượng vượt giới hạn.', 422)
        row = MeterReading(**scope_values(context, building_id=meter.building_id), meter_id=meter.id, read_on=body.read_on, value=body.value, consumption=consumption, evidence_reference=body.evidence_reference, anomaly=bool(body.anomaly_threshold and consumption > body.anomaly_threshold))
        row.unit_id = meter.unit_id; session.add(row); event(session, context, row, 'READ', body.evidence_reference)
        return row, 'profile'
    return command(request, context, key, 'meter.read', body.model_dump(mode='json'), execute, roles=TECHNICAL)


@router.post('/readings/{identifier}/actions')
def reading_action(identifier: UUID, body: PortalAction, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        row = load(session, context, MeterReading, identifier, TECHNICAL, lock=True)
        require_version(row.version, body.expected_version); state(row, ('SUBMITTED', 'REJECTED'))
        if body.action in ('VERIFY', 'REJECT'):
            independent(context, row, TECHNICAL)
            if row.anomaly and body.action == 'VERIFY' and not body.data.get('anomaly_resolution'):
                raise AppError('ERR-METER-ANOMALY', 'Cần kết luận xác minh bất thường.', 422)
            row.status = 'VERIFIED' if body.action == 'VERIFY' else 'REJECTED'; row.verified_by_id = context.account_id if body.action == 'VERIFY' else None
        else:
            raise AppError('ERR-STATE-TRANSITION', 'Chỉ số cần xác minh hoặc từ chối.', 409)
        row.version += 1; event(session, context, row, body.action, body.reason)
        return row, 'profile'
    return command(request, context, key, 'reading.' + body.action, {'id': str(identifier), **body.model_dump(mode='json')}, execute, roles=TECHNICAL)


@router.get('/meters/{identifier}/reconciliation')
def meter_reconciliation(identifier: UUID, request: Request, starts_on: date, ends_on: date, context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        parent = load(session, context, Meter, identifier, TECHNICAL)
        from app.services.meter_assignments import reconciliation
        return reconciliation(session, parent, starts_on, ends_on)


@router.post('/readings/{identifier}/billing', status_code=201)
def measured_source(identifier: UUID, body: MeterBillingInput, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        from app.models.billing import FeePolicyVersion
        from app.models.unit import Unit
        from app.models.resident_portal import PortalFeeSource
        from app.services.portal_finance import create_fee_source
        from app.services.meter_billing import price_snapshot
        initial = load(session, context, MeterReading, identifier, FINANCIAL)
        if not initial.unit_id:
            raise AppError('ERR-METER-COMMON', 'Đồng hồ khu chung dùng đối chiếu; phân bổ cần chính sách riêng.', 409)
        session.scalar(select(Unit).where(Unit.id == initial.unit_id).with_for_update())
        meter = load(session, context, Meter, initial.meter_id, FINANCIAL, lock=True)
        row = load(session, context, MeterReading, identifier, FINANCIAL, lock=True)
        require_version(row.version, body.expected_version); state(row, ('VERIFIED',))
        existing = session.scalar(select(PortalFeeSource).where(PortalFeeSource.source_kind == 'METER', PortalFeeSource.source_id == row.id))
        if existing:
            if existing.policy_snapshot['tariff_version_id'] != str(body.tariff_version_id):
                raise AppError('ERR-METER-TARIFF', 'Chỉ số đã có nguồn phí từ biểu phí khác.', 409)
            return existing, 'finance'
        tariff = load(session, context, FeePolicyVersion, body.tariff_version_id, FINANCIAL)
        snapshot = price_snapshot(session, row, meter, tariff)
        source = create_fee_source(session, row, 'METER', snapshot['amount_vnd'], 'Tiêu thụ ' + meter.code, snapshot, effective_on=row.read_on)
        if source is None:
            raise AppError('ERR-FEE-NO-ACCRUAL', 'Không phát sinh tiền tiêu thụ.', 409)
        event(session, context, source, 'MEASURED_SOURCE', 'Lập nguồn từ chỉ số đã xác minh; chờ duyệt phí.')
        return source, 'finance'
    return command(request, context, key, 'meter.billing', {'id': str(identifier), **body.model_dump(mode='json')}, execute, roles=FINANCIAL)


@router.get('/stock')
def stock(request: Request, context: UserContext = Depends(get_current_user_context)):
    return listing(request, context, StockItem, TECHNICAL)


@router.get('/assets/{identifier}/summary')
def asset_summary(identifier: UUID, request: Request, context: UserContext = Depends(get_current_user_context)):
    from app.models.maintenance import Asset
    from app.models.service import WorkOrder, CostLine
    with request.app.state.database.get_session() as session:
        asset = load(session, context, Asset, identifier, TECHNICAL)
        from app.services.asset_operations import asset_work_orders
        orders = session.scalars(asset_work_orders(asset.id).where(*context.scope_conditions(WorkOrder), *staff_conditions(context, WorkOrder, TECHNICAL))).all()
        ids = [r.id for r in orders]
        movements = session.scalars(select(StockMovement).where(StockMovement.work_order_id.in_(ids), StockMovement.kind.in_(('ISSUE', 'RETURN')), StockMovement.status == 'POSTED')).all()
        costs = session.scalars(select(CostLine).where(CostLine.work_order_id.in_(ids), CostLine.status != 'CANCELLED')).all()
        records = session.scalars(select(OperationsRecord).where(*context.scope_conditions(OperationsRecord), OperationsRecord.building_id == asset.building_id, OperationsRecord.kind == 'ASSET_CHANGE', OperationsRecord.status.in_(('APPROVED', 'COMPLETED')))).all()
        labor = [r for r in records if r.data['asset_id'] == str(asset.id) and r.data['operation'] == 'LABOR' and r.status == 'COMPLETED']
        materials = []
        for movement in movements:
            item = session.get(StockItem, movement.item_id)
            materials.append({**view(movement), 'item_name': item.name, 'cost_vnd': movement.quantity * item.unit_cost_vnd * (0 if movement.kind == 'RETURN' and movement.custody.get('condition') == 'DAMAGED' else -1 if movement.kind == 'RETURN' else 1)})
        return {'asset': view(asset), 'work_orders': [view(r) for r in orders], 'materials': materials,
            'labor': [view(r) for r in labor], 'cost_lines': [view(r) for r in costs],
            'material_cost_vnd': sum((r['cost_vnd'] for r in materials), Decimal(0)),
            'labor_hours': sum((Decimal(r.data['hours']) for r in labor), Decimal(0)),
            'labor_cost_vnd': sum(r.data['cost_vnd'] for r in labor),
            'submitted_cost_vnd': sum(r.amount_vnd for r in costs),
            'warnings': {'warranty_active': bool(asset.warranty_until and asset.warranty_until >= utc_now().date()), 'inspection_overdue': bool(asset.inspection_due_on and asset.inspection_due_on < utc_now().date()), 'inspection_not_recorded': asset.inspection_due_on is None},
            'note': 'Các nhóm chi phí được tách riêng; không cộng dòng dự kiến vào chi thực tế để tránh tính trùng.'}


@router.post('/stock', status_code=201)
def stock_create(body: StockInput, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        building_scope(session, context, body.building_id, TECHNICAL)
        row = StockItem(**scope_values(context, building_id=body.building_id), **body.model_dump(exclude={'building_id'})); session.add(row)
        return row, 'profile'
    return command(request, context, key, 'stock.create', body.model_dump(mode='json'), execute, roles=TECHNICAL)


@router.get('/stock-movements')
def stock_movements(request: Request, context: UserContext = Depends(get_current_user_context)):
    return listing(request, context, StockMovement, TECHNICAL)


def confirmed_wo(session, context, identifier, building_id):
    from app.models.service import WorkOrder
    wo = load(session, context, WorkOrder, identifier, TECHNICAL, lock=True)
    if wo.building_id != building_id or wo.status not in ('ASSIGNED', 'IN_PROGRESS', 'ON_HOLD', 'WAITING_ACCEPTANCE'):
        raise AppError('ERR-STOCK-WORK-ORDER', 'Vật tư cần lệnh công việc đã xác nhận còn mở.', 409)
    return wo


def stock_effect(session, context, row, item):
    q = row.quantity
    if row.kind == 'RECEIVE':
        item.quantity += q
    elif row.kind in ('RESERVE', 'ISSUE', 'DAMAGE', 'TRANSFER'):
        if item.status != 'AVAILABLE' or item.expires_on and item.expires_on < utc_now().date():
            raise AppError('ERR-STOCK-UNAVAILABLE', 'Vật tư hết hạn hoặc bị chặn.', 409)
        if row.kind in ('RESERVE', 'ISSUE'):
            if not row.work_order_id:
                raise AppError('ERR-STOCK-WORK-ORDER', 'Cần lệnh công việc.', 422)
            confirmed_wo(session, context, row.work_order_id, item.building_id)
        if row.kind == 'ISSUE' and row.related_id:
            reservation = load(session, context, StockMovement, row.related_id, TECHNICAL, lock=True)
            if reservation.kind != 'RESERVE' or reservation.item_id != item.id or reservation.work_order_id != row.work_order_id:
                raise AppError('ERR-STOCK-RESERVATION', 'Phiếu giữ vật tư không phù hợp.', 409)
            used = session.scalar(select(func.coalesce(func.sum(StockMovement.quantity), 0)).where(StockMovement.related_id == reservation.id, StockMovement.kind.in_(('ISSUE', 'RELEASE')))) or 0
            if q > reservation.quantity - used:
                raise AppError('ERR-STOCK-RESERVATION', 'Vượt phần vật tư đã giữ còn lại.', 409)
            item.reserved -= q
        elif item.quantity - item.reserved < q:
            raise AppError('ERR-STOCK-INSUFFICIENT', 'Không đủ tồn khả dụng.', 409)
        if row.kind == 'RESERVE':
            item.reserved += q
        else:
            item.quantity -= q
        if row.kind == 'TRANSFER':
            if not row.destination_id or row.destination_id == item.id:
                raise AppError('ERR-STOCK-DESTINATION', 'Cần vị trí nhận khác vị trí xuất.', 422)
            target = load(session, context, StockItem, row.destination_id, TECHNICAL, lock=True)
            if (target.code, target.uom, target.lot, target.unit_cost_vnd, target.expires_on) != (item.code, item.uom, item.lot, item.unit_cost_vnd, item.expires_on):
                raise AppError('ERR-STOCK-DESTINATION', 'Vật tư nhận không cùng mã, đơn vị, lô, giá và hạn.', 422)
            target.quantity += q; target.version += 1
            event(session, context, target, 'TRANSFER_IN', row.evidence_reference)
    elif row.kind in ('RETURN', 'RELEASE'):
        if not row.related_id:
            raise AppError('ERR-STOCK-ORIGIN', 'Cần phiếu xuất/giữ nguồn.', 422)
        source = load(session, context, StockMovement, row.related_id, TECHNICAL, lock=True)
        expected = 'ISSUE' if row.kind == 'RETURN' else 'RESERVE'
        if source.item_id != item.id or source.kind != expected or source.status != 'POSTED':
            raise AppError('ERR-STOCK-ORIGIN', 'Phiếu nguồn không phù hợp.', 422)
        if row.kind == 'RETURN' and source.custody.get('recipient_account_id') and row.custody.get('sender_account_id') != source.custody['recipient_account_id']:
            raise AppError('ERR-STOCK-CUSTODIAN', 'Người trả phải là người đã nhận ở phiếu xuất nguồn.', 409)
        row.work_order_id = source.work_order_id
        kinds = ('RETURN',) if row.kind == 'RETURN' else ('ISSUE', 'RELEASE')
        used = session.scalar(select(func.coalesce(func.sum(StockMovement.quantity), 0)).where(StockMovement.related_id == source.id, StockMovement.kind.in_(kinds), StockMovement.status == 'POSTED')) or 0
        if used + q > source.quantity:
            raise AppError('ERR-STOCK-ORIGIN', 'Vượt số lượng phiếu nguồn còn lại.', 409)
        if row.kind == 'RETURN':
            if row.custody.get('condition') == 'DAMAGED':
                item.damaged_quantity += q
            else:
                item.quantity += q
        else:
            item.reserved -= q
    elif row.kind == 'COUNT':
        if row.quantity < item.reserved:
            raise AppError('ERR-STOCK-RESERVATION', 'Tồn kiểm kê không được thấp hơn vật tư đang giữ.', 409)
        item.quantity = row.quantity
    item.version += 1
    event(session, context, item, row.kind, row.evidence_reference)


@router.post('/stock-movements', status_code=201)
def stock_command(body: StockCommand, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        # A common lock order avoids A→B and B→A transfer deadlocks.
        items = {}
        for identifier in sorted({body.item_id, *([body.destination_id] if body.destination_id else [])}, key=str):
            items[identifier] = load(session, context, StockItem, identifier, TECHNICAL, lock=True)
        item = items[body.item_id]; require_version(item.version, body.expected_version)
        from app.services.stock_finance_controls import movement_custody
        quantity, custody = movement_custody(session, context, body, item)
        row = StockMovement(**scope_values(context, building_id=item.building_id), **body.model_dump(exclude={'expected_version', 'quantity', 'sender_account_id', 'recipient_account_id', 'condition', 'input_uom', 'conversion_id', 'delivery_id'}), quantity=quantity, custody=custody, status='SUBMITTED' if body.kind in ('COUNT', 'DAMAGE') else 'POSTED')
        if body.kind not in ('COUNT', 'DAMAGE'):
            stock_effect(session, context, row, item)
        session.add(row); event(session, context, row, body.kind, body.evidence_reference)
        return row, 'profile'
    return command(request, context, key, 'stock.movement', body.model_dump(mode='json'), execute, roles=TECHNICAL)


@router.post('/stock-movements/{identifier}/actions')
def stock_approve(identifier: UUID, body: PortalAction, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        initial = load(session, context, StockMovement, identifier, TECHNICAL)
        item = load(session, context, StockItem, initial.item_id, TECHNICAL, lock=True)
        row = load(session, context, StockMovement, identifier, TECHNICAL, lock=True)
        require_version(row.version, body.expected_version); state(row, ('SUBMITTED',)); independent(context, row, TECHNICAL)
        if body.action == 'APPROVE':
            item = load(session, context, StockItem, row.item_id, TECHNICAL, lock=True)
            stock_effect(session, context, row, item); row.status = 'POSTED'; row.approved_by_id = context.account_id
        elif body.action == 'REJECT':
            row.status = 'REJECTED'
        else:
            raise AppError('ERR-STATE-TRANSITION', 'Phiếu kiểm kê/hư hỏng cần duyệt hoặc từ chối.', 409)
        row.version += 1; event(session, context, row, body.action, body.reason)
        return row, 'profile'
    return command(request, context, key, 'stock.' + body.action, {'id': str(identifier), **body.model_dump(mode='json')}, execute, roles=TECHNICAL)


@router.get('/treasury')
def treasury(request: Request, context: UserContext = Depends(get_current_user_context)):
    return listing(request, context, TreasuryAccount, FINANCIAL)


@router.post('/treasury', status_code=201)
def treasury_create(body: TreasuryInput, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        building_scope(session, context, body.building_id, FINANCIAL)
        row = TreasuryAccount(**scope_values(context, building_id=body.building_id), **body.model_dump(exclude={'building_id'})); session.add(row)
        return row, 'profile'
    return command(request, context, key, 'treasury.create', body.model_dump(mode='json'), execute, roles=FINANCIAL)


@router.post('/treasury/{identifier}/actions')
def treasury_action(identifier: UUID, body: PortalAction, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        financial_lock(session, context)
        row = load(session, context, TreasuryAccount, identifier, FINANCIAL, lock=True); require_version(row.version, body.expected_version)
        if body.action == 'SUBMIT':
            state(row, ('DRAFT', 'REJECTED')); row.status = 'SUBMITTED'
        elif body.action in ('APPROVE', 'REJECT'):
            state(row, ('SUBMITTED',)); independent(context, row)
            row.status = 'ACTIVE' if body.action == 'APPROVE' else 'REJECTED'; row.approved_by_id = context.account_id if body.action == 'APPROVE' else None
        elif body.action == 'RECEIPT':
            state(row, ('ACTIVE',))
            amount = body.data.get('amount_vnd'); reference = body.data.get('reference'); evidence = body.data.get('evidence_reference')
            if row.kind != 'FUND' or type(amount) is not int or not 0 < amount <= 999999999999 or not isinstance(reference, str) or not 3 <= len(reference) <= 150 or not isinstance(evidence, str) or not 3 <= len(evidence) <= 300:
                raise AppError('ERR-TREASURY-INPUT', 'Cần quỹ, số tiền, mã chứng từ và căn cứ thu hợp lệ.', 422)
            movement = TreasuryMovement(**scope_values(context, building_id=row.building_id), treasury_id=row.id, amount_vnd=amount, kind='RECEIPT', reference=reference, evidence_reference=evidence)
            session.add(movement); row.balance_vnd += amount
        elif body.action == 'CLOSE':
            state(row, ('ACTIVE',))
            if row.reserved_vnd or row.kind == 'FUND' and row.balance_vnd:
                raise AppError('ERR-TREASURY-BALANCE', 'Cần giải quyết số dư/cam kết trước khi đóng.', 409)
            row.status = 'CLOSED'
        elif body.action == 'RECONCILE':
            state(row, ('ACTIVE',))
            value = body.data.get('statement_balance_vnd'); reference = body.data.get('statement_reference', '')
            total = session.scalar(select(func.coalesce(func.sum(TreasuryMovement.amount_vnd), 0)).where(TreasuryMovement.treasury_id == row.id)) or 0
            if row.kind != 'FUND' or type(value) is not int or value != row.balance_vnd or total != row.balance_vnd or not isinstance(reference, str) or not 3 <= len(reference) <= 300:
                raise AppError('ERR-FUND-RECONCILIATION', 'Số dư quỹ, sổ thu/chi và số đối chiếu cần khớp; cần mã chứng từ đối chiếu.', 409)
        else:
            raise AppError('ERR-STATE-TRANSITION', 'Thao tác quỹ/ngân sách không hợp lệ.', 409)
        row.version += 1; event(session, context, row, body.action, body.reason)
        return row, 'profile'
    return command(request, context, key, 'treasury.' + body.action, {'id': str(identifier), **body.model_dump(mode='json')}, execute, roles=FINANCIAL)


@router.get('/treasury/{identifier}/reconciliation')
def treasury_reconciliation(identifier: UUID, request: Request, context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        row = load(session, context, TreasuryAccount, identifier, FINANCIAL)
        movements = session.scalars(select(TreasuryMovement).where(TreasuryMovement.treasury_id == row.id).order_by(TreasuryMovement.created_at, TreasuryMovement.id)).all()
        calculated = sum(m.amount_vnd for m in movements)
        return {'account': view(row), 'ledger_balance_vnd': calculated, 'matches': row.kind == 'FUND' and calculated == row.balance_vnd, 'available_budget_vnd': row.limit_vnd - row.spent_vnd - row.reserved_vnd, 'items': [view(m) for m in movements]}


@router.get('/treasury-movements')
def treasury_movements(request: Request, context: UserContext = Depends(get_current_user_context)):
    return listing(request, context, TreasuryMovement, FINANCIAL)


@router.get('/expenses')
def expenses(request: Request, context: UserContext = Depends(get_current_user_context)):
    return listing(request, context, Expense, FINANCIAL)


def payable_match(session, context, row):
    if row.kind != 'AP':
        return
    if not row.procurement_id:
        raise AppError('ERR-AP-MATCH', 'Công nợ NCC cần đơn hàng được duyệt.', 422)
    order = load(session, context, OperationsRecord, row.procurement_id, FINANCIAL, lock=True)
    if order.kind == 'PROJECT':
        if order.status not in ('APPROVED', 'IN_PROGRESS') or order.building_id != row.building_id or str(row.budget_id) != order.data['budget_id']:
            raise AppError('ERR-AP-MATCH', 'Dự án không còn mở hoặc khác ngân sách.', 409)
        accepted = sum(p.data['actual_vnd'] for p in session.scalars(select(OperationsRecord).where(OperationsRecord.kind == 'PROJECT_ACCEPTANCE', OperationsRecord.status.in_(('APPROVED', 'COMPLETED')), OperationsRecord.building_id == row.building_id)) if p.data['project_id'] == str(order.id))
        obligations = session.scalar(select(func.coalesce(func.sum(Expense.amount_vnd), 0)).where(Expense.procurement_id == order.id, Expense.status != 'REJECTED', *((Expense.id != row.id,) if row.id else ()))) or 0
        if obligations + row.amount_vnd > min(accepted, order.data['planned_vnd']):
            raise AppError('ERR-AP-MATCH', 'Chi phí vượt giá trị nghiệm thu/dự toán dự án.', 409)
        return
    if order.kind != 'PURCHASE' or order.status not in ('APPROVED', 'COMPLETED') or order.building_id != row.building_id:
        raise AppError('ERR-AP-MATCH', 'Đơn hàng không phù hợp.', 409)
    approved = session.scalars(select(OperationsRecord).where(OperationsRecord.related_id == order.id, OperationsRecord.kind == 'DELIVERY', OperationsRecord.status == 'COMPLETED')).all()
    accepted = sum((Decimal(d.data.get('accepted_quantity', d.data['quantity'])) for d in approved), Decimal(0))
    quantity = Decimal(order.data['quantity'])
    contracts = session.scalars(select(OperationsRecord).where(OperationsRecord.kind == 'CONTRACT', OperationsRecord.status == 'APPROVED', OperationsRecord.building_id == row.building_id)).all()
    partial = any(c.data.get('purchase_id') == str(order.id) and c.data.get('allows_partial_payment') and c.data.get('partial_payment_reference') for c in contracts)
    if accepted < quantity and not partial:
        raise AppError('ERR-AP-MATCH', 'Chưa nghiệm thu đủ; thanh toán từng phần cần điều khoản được duyệt.', 409)
    amount = int(order.data.get('selected_amount_vnd', order.data['estimated_vnd']))
    obligations = session.scalar(select(func.coalesce(func.sum(Expense.amount_vnd), 0)).where(Expense.procurement_id == order.id, Expense.status != 'REJECTED', *((Expense.id != row.id,) if row.id else ()))) or 0
    eligible = int(Decimal(amount) * min(accepted, quantity) / quantity)
    if obligations + row.amount_vnd > eligible:
        raise AppError('ERR-AP-MATCH', 'Tổng chứng từ vượt giá trị đặt hàng đã duyệt.', 409)


@router.post('/expenses', status_code=201)
def expense_create(body: ExpenseInput, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        financial_lock(session, context)
        budget = load(session, context, TreasuryAccount, body.budget_id, FINANCIAL, lock=True)
        if budget.kind != 'BUDGET' or budget.status != 'ACTIVE':
            raise AppError('ERR-BUDGET-INACTIVE', 'Cần ngân sách đã duyệt.', 409)
        if body.fund_id:
            fund = load(session, context, TreasuryAccount, body.fund_id, FINANCIAL)
            if fund.kind != 'FUND' or fund.status != 'ACTIVE' or fund.building_id != budget.building_id:
                raise AppError('ERR-FUND-INACTIVE', 'Quỹ chi không phù hợp phạm vi ngân sách.', 409)
        row = Expense(**scope_values(context, building_id=budget.building_id), **body.model_dump()); payable_match(session, context, row)
        from app.services.stock_finance_controls import validate_allocation
        validate_allocation(session, context, row)
        session.add(row); return row, 'profile'
    return command(request, context, key, 'expense.create', body.model_dump(mode='json'), execute, roles=FINANCIAL)


@router.post('/expenses/{identifier}/actions')
def expense_action(identifier: UUID, body: PortalAction, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        financial_lock(session, context)
        row = load(session, context, Expense, identifier, FINANCIAL, lock=True); require_version(row.version, body.expected_version)
        budget = load(session, context, TreasuryAccount, row.budget_id, FINANCIAL, lock=True)
        if body.action == 'SUBMIT':
            state(row, ('DRAFT',)); row.status = 'SUBMITTED'
        elif body.action in ('APPROVE', 'REJECT'):
            state(row, ('SUBMITTED',)); independent(context, row)
            if body.action == 'APPROVE':
                state(budget, ('ACTIVE',)); payable_match(session, context, row)
                from app.services.stock_finance_controls import validate_allocation
                validate_allocation(session, context, row)
                if row.kind != 'AP' and budget.spent_vnd + budget.reserved_vnd + row.amount_vnd > budget.limit_vnd:
                    raise AppError('ERR-BUDGET-LIMIT', 'Vượt ngân sách; cần đề nghị điều chỉnh ngân sách được duyệt.', 409)
                if not budget.starts_on <= utc_now().date() <= budget.ends_on:
                    raise AppError('ERR-BUDGET-PERIOD', 'Ngân sách ngoài kỳ hiệu lực.', 409)
                if row.kind == 'AP':
                    order = load(session, context, OperationsRecord, row.procurement_id, FINANCIAL, lock=True)
                    remaining = int(order.data.get('remaining_commitment_vnd', 0))
                    if remaining < row.amount_vnd:
                        raise AppError('ERR-AP-MATCH', 'Không đủ cam kết đặt hàng chưa phân bổ.', 409)
                    order.data = {**order.data, 'remaining_commitment_vnd': remaining - row.amount_vnd}; order.version += 1
                else:
                    budget.reserved_vnd += row.amount_vnd
                budget.version += 1
                row.status = 'APPROVED'; row.approved_by_id = context.account_id
            else:
                row.status = 'REJECTED'
        elif body.action == 'PAY':
            state(row, ('APPROVED', 'PART_PAID')); payable_match(session, context, row)
            checker = session.get(Account, row.approved_by_id)
            if not checker or not checker.is_active:
                raise AppError('ERR-APPROVAL-STALE', 'Người duyệt không còn hoạt động.', 409)
            from app.core.policy import context_for_account
            independent(context_for_account(session, checker, row.site_id), row)
            amount = body.data.get('amount_vnd'); reference = body.data.get('reference', '')
            if type(amount) is not int or not 0 < amount <= row.amount_vnd - row.paid_vnd or not isinstance(reference, str) or not 3 <= len(reference) <= 150:
                raise AppError('ERR-PAYMENT-AMOUNT', 'Số tiền hoặc mã chứng từ chi không hợp lệ.', 422)
            if row.fund_id:
                fund = load(session, context, TreasuryAccount, row.fund_id, FINANCIAL, lock=True); state(fund, ('ACTIVE',))
                if fund.balance_vnd < amount:
                    raise AppError('ERR-FUND-BALANCE', 'Quỹ không đủ số dư.', 409)
                fund.balance_vnd -= amount; fund.spent_vnd += amount; fund.version += 1
                session.add(TreasuryMovement(**scope_values(context, building_id=row.building_id), treasury_id=fund.id, expense_id=row.id, amount_vnd=-amount, kind='DISBURSEMENT', reference=reference + ':FUND', evidence_reference=body.reason))
            budget.reserved_vnd -= amount; budget.spent_vnd += amount; budget.version += 1; row.paid_vnd += amount
            session.add(TreasuryMovement(**scope_values(context, building_id=row.building_id), treasury_id=budget.id, expense_id=row.id, amount_vnd=-amount, kind='PAYMENT', reference=reference, evidence_reference=body.reason))
            row.status = 'PAID' if row.paid_vnd == row.amount_vnd else 'PART_PAID'
        elif body.action == 'CANCEL':
            state(row, ('DRAFT', 'SUBMITTED', 'APPROVED'))
            if row.paid_vnd:
                raise AppError('ERR-PAID-EXPENSE', 'Khoản đã chi cần hồ sơ hoàn ứng.', 409)
            if row.status == 'APPROVED':
                if row.kind == 'AP':
                    order = load(session, context, OperationsRecord, row.procurement_id, FINANCIAL, lock=True)
                    order.data = {**order.data, 'remaining_commitment_vnd': order.data['remaining_commitment_vnd'] + row.amount_vnd}; order.version += 1
                else:
                    budget.reserved_vnd -= row.amount_vnd
                budget.version += 1
            row.status = 'REJECTED'
        else:
            raise AppError('ERR-STATE-TRANSITION', 'Thao tác đề nghị chi không hợp lệ.', 409)
        row.version += 1; event(session, context, row, body.action, body.reason)
        return row, 'profile'
    return command(request, context, key, 'expense.' + body.action, {'id': str(identifier), **body.model_dump(mode='json')}, execute, roles=FINANCIAL)
