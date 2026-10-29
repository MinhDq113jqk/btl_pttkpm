"""Quantity/custody and scoped allocations for SAD T05/T06."""
from decimal import Decimal
from sqlalchemy import select, func
from app.core.exceptions import AppError
from app.core.policy import scope_not_found
from app.models.operational_control import OperationsRecord, StockMovement, StockItem
from app.services.operational_control import TECHNICAL, FINANCIAL, load, as_uuid
from app.services.r2 import utc_now
from app.services.sad_work import account_in_building, active_on


def validate_allocation(session, context, expense):
    from app.models.property import PropertyNode
    from app.models.maintenance import Asset
    from app.models.service import WorkOrder
    from app.models.unit import Unit
    if not expense.allocation or sum(expense.allocation.values()) != expense.amount_vnd:
        raise AppError('ERR-EXPENSE-ALLOCATION', 'Phân bổ phải có đối tượng và bằng tổng chứng từ.', 422)
    models = {'UNIT': Unit, 'SPACE': PropertyNode, 'ASSET': Asset, 'WORK_ORDER': WorkOrder}
    for target, amount in expense.allocation.items():
        if type(amount) is not int or amount <= 0 or ':' not in target:
            raise AppError('ERR-EXPENSE-ALLOCATION', 'Đối tượng/số tiền phân bổ không hợp lệ.', 422)
        kind, identifier = target.split(':', 1)
        if kind == 'BUILDING':
            if as_uuid(identifier) != expense.building_id: raise scope_not_found()
        elif kind in models:
            from app.services.resident_portal import unit_for
            obj = unit_for(session, context, as_uuid(identifier), roles=FINANCIAL) if kind == 'UNIT' else load(session, context, models[kind], as_uuid(identifier), FINANCIAL)
            if obj.building_id != expense.building_id: raise scope_not_found()
        else:
            raise AppError('ERR-EXPENSE-ALLOCATION', 'Loại đối tượng phân bổ chưa được hỗ trợ.', 422)


def movement_custody(session, context, body, item):
    required = body.kind in ('RECEIVE', 'ISSUE', 'RETURN', 'TRANSFER')
    if required and (not body.sender_account_id or not body.recipient_account_id):
        raise AppError('ERR-STOCK-CUSTODY', 'Phiếu giao/nhận cần người giao và người nhận.', 422)
    for identifier in (body.sender_account_id, body.recipient_account_id):
        if identifier: account_in_building(session, context, item, identifier)
    quantity = body.quantity
    custody = body.model_dump(mode='json', include={'sender_account_id', 'recipient_account_id', 'condition', 'input_uom', 'conversion_id', 'delivery_id'})
    custody['input_quantity'] = str(quantity); custody['base_uom'] = item.uom
    custody['unit_cost_vnd'] = item.unit_cost_vnd
    if body.input_uom and body.input_uom != item.uom:
        conversion = load(session, context, OperationsRecord, body.conversion_id, TECHNICAL, lock=True) if body.conversion_id else None
        if not conversion or conversion.kind != 'UOM_CONVERSION' or conversion.data['item_id'] != str(item.id) or conversion.data['from_uom'] != body.input_uom or not active_on(conversion, utc_now().date()):
            raise AppError('ERR-UOM-CONVERSION', 'Quy đổi cần hồ sơ đã duyệt có hiệu lực của vật tư.', 409)
        quantity *= Decimal(conversion.data['factor'])
        if quantity != quantity.quantize(Decimal('0.0001')):
            raise AppError('ERR-UOM-PRECISION', 'Lượng quy đổi vượt độ chính xác kho.', 422)
        custody['conversion_snapshot'] = conversion.data
    if body.delivery_id:
        delivery = load(session, context, OperationsRecord, body.delivery_id, TECHNICAL, lock=True)
        if body.kind != 'RECEIVE' or delivery.kind != 'DELIVERY' or delivery.status != 'COMPLETED' or delivery.building_id != item.building_id:
            raise AppError('ERR-STOCK-DELIVERY', 'Nhập từ nghiệm thu cần hồ sơ đã hoàn thành cùng tòa.', 409)
        order = load(session, context, OperationsRecord, delivery.related_id, TECHNICAL)
        if order.data.get('item_id') != str(item.id): raise scope_not_found()
        imported = session.scalars(select(StockMovement).where(StockMovement.item_id == item.id, StockMovement.kind == 'RECEIVE', StockMovement.status == 'POSTED')).all()
        used = sum((m.quantity for m in imported if m.custody.get('delivery_id') == str(delivery.id)), Decimal(0))
        if used + quantity > Decimal(delivery.data.get('accepted_quantity', delivery.data['quantity'])):
            raise AppError('ERR-STOCK-DELIVERY', 'Nhập kho vượt phần đã nghiệm thu đạt.', 409)
    return quantity, custody
