"""Typed dossiers and explicit effects for SAD operational extensions."""
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import func, select
from app.core.exceptions import AppError
from app.core.policy import scope_not_found, context_for_account
from app.models.account import Account
from app.models.operational_control import OperationsRecord, Meter, MeterReading, TreasuryAccount, Expense, TreasuryMovement
from app.schemas.operational_control import (VendorData, PurchaseData, QuotationData, ContractData, DeliveryData, SafetyData, RuleData, ViolationData, VisitorData, CustodyData, StaffData, RosterData, MeterCycleData, AssetData, MeterReplacementData, MeterCorrectionData, BudgetRevisionData, AdvanceSettlementData)
from app.services.operational_control import load, data_model, as_uuid, state, event, independent, TECHNICAL, MANAGEMENT, FINANCIAL, SECURITY
from app.services.resident_portal import scope_values
from app.services.r2 import utc_now
from app.schemas.operational_control import ContractRevisionData, DepositPolicyData, LeaseDepositData, DataQualityData

RECORDS = {
    'VENDOR': (VendorData, MANAGEMENT), 'PURCHASE': (PurchaseData, (*MANAGEMENT, 'accountant')), 'QUOTATION': (QuotationData, (*MANAGEMENT, 'accountant')),
    'CONTRACT': (ContractData, (*MANAGEMENT, 'accountant')), 'CONTRACT_REVISION': (ContractRevisionData, (*MANAGEMENT, 'accountant')), 'DELIVERY': (DeliveryData, (*MANAGEMENT, 'accountant', 'technical_lead')),
    'VENDOR_EVALUATION': (SafetyData, MANAGEMENT), 'METER_CYCLE': (MeterCycleData, TECHNICAL), 'METER_REPLACEMENT': (MeterReplacementData, TECHNICAL), 'METER_CORRECTION': (MeterCorrectionData, TECHNICAL),
    'BUDGET_REVISION': (BudgetRevisionData, FINANCIAL), 'ADVANCE_SETTLEMENT': (AdvanceSettlementData, FINANCIAL),
    'RULE': (RuleData, MANAGEMENT), 'VIOLATION': (ViolationData, MANAGEMENT), 'RISK': (SafetyData, MANAGEMENT), 'INSPECTION': (SafetyData, (*MANAGEMENT, 'technical_lead')), 'INSURANCE': (SafetyData, MANAGEMENT),
    'WASTE': (SafetyData, (*MANAGEMENT, 'cleaning')), 'LANDSCAPE': (SafetyData, (*MANAGEMENT, 'cleaning')), 'PEST': (SafetyData, (*MANAGEMENT, 'cleaning')), 'ENV_INCIDENT': (SafetyData, (*MANAGEMENT, 'cleaning')),
    'VISITOR': (VisitorData, SECURITY), 'CONTRACTOR': (VisitorData, SECURITY), 'EMERGENCY_PLAN': (RuleData, SECURITY), 'DRILL': (SafetyData, SECURITY), 'KEY_CUSTODY': (CustodyData, SECURITY),
    'PARCEL_CUSTODY': (CustodyData, MANAGEMENT), 'LOST_FOUND': (CustodyData, MANAGEMENT), 'STAFF': (StaffData, MANAGEMENT), 'ROSTER': (RosterData, MANAGEMENT),
    'SOP': (RuleData, MANAGEMENT), 'TRAINING': (SafetyData, MANAGEMENT), 'MASTER_DATA': (RuleData, ('admin', 'director')), 'DATA_QUALITY': (DataQualityData, ('admin', 'director')),
    'DEPOSIT_POLICY': (DepositPolicyData, FINANCIAL), 'LEASE_DEPOSIT': (LeaseDepositData, FINANCIAL),
    'ASSET_CHANGE': (AssetData, TECHNICAL),
}
from app.services import sad_work
RECORDS.update(sad_work.EXTRA_RECORDS)
from app.services import sad_extensions
RECORDS.update(sad_extensions.RECORDS)


def definition(kind):
    if kind not in RECORDS:
        raise AppError('ERR-RECORD-KIND', 'Loại hồ sơ vận hành không được hỗ trợ.', 422)
    return RECORDS[kind]


def linked_record(session, context, identifier, kinds, roles):
    row = load(session, context, OperationsRecord, identifier, roles, lock=True)
    if row.kind not in kinds:
        raise AppError('ERR-RECORD-REFERENCE', 'Hồ sơ nguồn không đúng loại.', 422)
    return row


def validate_links(session, context, row):
    _, roles = definition(row.kind)
    d = row.data
    sad_work.validate(session, context, row)
    sad_extensions.validate(session, context, row)
    if row.related_id:
        source = load(session, context, OperationsRecord, row.related_id, roles)
        if source.building_id != row.building_id:
            raise scope_not_found()
    if row.kind in ('QUOTATION', 'CONTRACT'):
        vendor = linked_record(session, context, as_uuid(d['vendor_id']), ('VENDOR',), roles)
        state(vendor, ('APPROVED', 'COMPLETED'))
    if row.kind == 'QUOTATION':
        if not row.related_id:
            raise AppError('ERR-RECORD-REFERENCE', 'Báo giá cần đề nghị mua.', 422)
        order = linked_record(session, context, row.related_id, ('PURCHASE',), roles)
        state(order, ('DRAFT', 'SUBMITTED'))
        if Decimal(d['quantity']) != Decimal(order.data['quantity']):
            raise AppError('ERR-QUOTE-COMPARISON', 'Báo giá phải cùng số lượng yêu cầu để so sánh.', 422)
    if row.kind == 'PURCHASE':
        budget = load(session, context, TreasuryAccount, as_uuid(d['budget_id']), FINANCIAL)
        if budget.kind != 'BUDGET' or budget.building_id != row.building_id:
            raise scope_not_found()
        state(budget, ('ACTIVE',))
        if d.get('item_id'):
            from app.models.operational_control import StockItem
            item = load(session, context, StockItem, as_uuid(d['item_id']), (*MANAGEMENT, 'accountant', 'technical_lead'))
            if item.building_id != row.building_id or item.uom != d['uom']:
                raise AppError('ERR-STOCK-REFERENCE', 'Vật tư bổ sung khác tòa hoặc đơn vị tính.', 422)
    if row.kind == 'DELIVERY':
        if not row.related_id:
            raise AppError('ERR-RECORD-REFERENCE', 'Giao hàng cần đơn hàng được duyệt.', 422)
        order = linked_record(session, context, row.related_id, ('PURCHASE',), roles)
        state(order, ('APPROVED', 'COMPLETED'))
        delivered = session.scalars(select(OperationsRecord).where(OperationsRecord.related_id == order.id, OperationsRecord.kind == 'DELIVERY', OperationsRecord.status.not_in(('REJECTED', 'CANCELLED')), OperationsRecord.id != row.id)).all()
        accepted = Decimal(d['accepted_quantity']) if d.get('accepted_quantity') is not None else Decimal(d['quantity'])
        if sum((Decimal(r.data.get('accepted_quantity') if r.data.get('accepted_quantity') is not None else r.data['quantity']) for r in delivered), Decimal(0)) + accepted > Decimal(order.data['quantity']):
            raise AppError('ERR-DELIVERY-QUANTITY', 'Giao hàng vượt số lượng đặt.', 409)
        if (Decimal(d.get('rejected_quantity', '0')) or Decimal(d.get('missing_quantity', '0')) or d.get('defects')) and not d.get('responsible_account_id'):
            raise AppError('ERR-DELIVERY-OWNER', 'Phần lỗi/thiếu cần người chịu trách nhiệm khắc phục.', 422)
        if d.get('rectifies_delivery_id'):
            original = linked_record(session, context, as_uuid(d['rectifies_delivery_id']), ('DELIVERY',), roles)
            if original.related_id != order.id or original.id == row.id or original.status != 'COMPLETED':
                raise scope_not_found()
            capacity = Decimal(original.data.get('rejected_quantity', '0')) + Decimal(original.data.get('missing_quantity', '0'))
            rectified = sum((Decimal(p.data['quantity']) for p in delivered if p.data.get('rectifies_delivery_id') == str(original.id)), Decimal(0))
            if rectified + Decimal(d['quantity']) > capacity:
                raise AppError('ERR-DELIVERY-RECTIFICATION', 'Khắc phục vượt phần lỗi/thiếu của lần giao nguồn.', 409)
    if row.kind == 'VIOLATION':
        rule = linked_record(session, context, as_uuid(d['rule_id']), ('RULE',), roles)
        when = date.fromisoformat(d['occurred_on'])
        if rule.status != 'APPROVED' or when < date.fromisoformat(rule.data['valid_from']) or rule.data.get('valid_to') and when >= date.fromisoformat(rule.data['valid_to']):
            raise AppError('ERR-RULE-EFFECTIVITY', 'Vi phạm cần nội quy đã duyệt có hiệu lực lúc xảy ra.', 409)
        subject = session.scalar(select(Account).where(Account.id == as_uuid(d['subject_account_id']), Account.tenant_id == row.tenant_id))
        if not subject or not row.unit_id or row.unit_id not in context_for_account(session, subject, row.site_id).resident_unit_ids:
            raise AppError('ERR-VIOLATION-SUBJECT', 'Đối tượng vi phạm cần quan hệ cư trú trong căn liên quan.', 422)
    if row.kind in ('VISITOR', 'CONTRACTOR'):
        host = session.scalar(select(Account).where(Account.id == as_uuid(d['host_account_id']), Account.tenant_id == row.tenant_id, Account.is_active.is_(True)))
        if not host or row.unit_id not in context_for_account(session, host, row.site_id).resident_unit_ids:
            raise AppError('ERR-VISITOR-HOST', 'Người tiếp đón phải có quan hệ cư trú hiện hành tại căn.', 422)
        if row.kind == 'CONTRACTOR':
            from app.models.resident_portal import PortalDossier
            dossier = load(session, context, PortalDossier, as_uuid(d.get('authorization_dossier_id')), SECURITY)
            if dossier.kind != 'RENOVATION' or dossier.status != 'IN_PROGRESS' or dossier.unit_id != row.unit_id:
                raise AppError('ERR-CONTRACTOR-AUTHORIZATION', 'Nhà thầu cần hồ sơ cải tạo đang được phép thi công.', 409)
    if row.kind == 'STAFF':
        account = session.scalar(select(Account).where(Account.id == as_uuid(d['account_id']), Account.tenant_id == row.tenant_id, Account.is_active.is_(True)))
        if not account:
            raise scope_not_found()
        ctx = context_for_account(session, account, row.site_id)
        if not any(g.role in ('cskh', 'technical_lead', 'technician', 'cleaning', 'security') and g.building_id == row.building_id for g in ctx.role_grants):
            raise AppError('ERR-STAFF-SCOPE', 'Nhân sự cần quyền vận hành trong tòa phụ trách.', 422)
    if row.kind == 'ROSTER':
        staff = linked_record(session, context, as_uuid(d['staff_id']), ('STAFF',), MANAGEMENT)
        state(staff, ('APPROVED',))
        if d['required_skill'] not in staff.data['skills'] or staff.data.get('certificate_expires_on') and date.fromisoformat(staff.data['certificate_expires_on']) < datetime.fromisoformat(d['ends_at']).date():
            raise AppError('ERR-STAFF-SKILL', 'Nhân sự thiếu kỹ năng hoặc chứng nhận còn hiệu lực.', 409)
        # Lock staff serializes all assignments; check overlap again at approval/replacement.
        peers = session.scalars(select(OperationsRecord).where(*context.scope_conditions(OperationsRecord), OperationsRecord.kind == 'ROSTER', OperationsRecord.status.not_in(('REJECTED', 'CANCELLED', 'COMPLETED')), OperationsRecord.id != row.id)).all()
        start, end = datetime.fromisoformat(d['starts_at']), datetime.fromisoformat(d['ends_at'])
        if any(p.data['staff_id'] == d['staff_id'] and datetime.fromisoformat(p.data['starts_at']) < end and datetime.fromisoformat(p.data['ends_at']) > start for p in peers):
            raise AppError('ERR-ROSTER-OVERLAP', 'Nhân sự đang có ca trùng thời gian.', 409)
    if row.kind == 'METER_CYCLE':
        for identifier in d['meter_ids']:
            meter = load(session, context, Meter, as_uuid(identifier), TECHNICAL)
            if meter.building_id != row.building_id:
                raise scope_not_found()
    if row.kind in ('KEY_CUSTODY', 'PARCEL_CUSTODY', 'LOST_FOUND', 'TOOL_CUSTODY'):
        target = sad_work.account_in_building(session, context, row, d['custodian_account_id'])
        if not target:
            raise scope_not_found()
        if row.kind == 'PARCEL_CUSTODY':
            from app.models.parcel import Parcel
            parcel = load(session, context, Parcel, as_uuid(d['reference']), MANAGEMENT)
            if parcel.building_id != row.building_id:
                raise scope_not_found()
    if row.kind == 'ASSET_CHANGE':
        from app.models.maintenance import Asset
        asset = load(session, context, Asset, as_uuid(d['asset_id']), TECHNICAL)
        if asset.building_id != row.building_id:
            raise scope_not_found()
        if d['operation'] == 'OUTAGE':
            start, end = d.get('starts_at'), d.get('ends_at')
            if not start or not end or datetime.fromisoformat(start).tzinfo is None or datetime.fromisoformat(end).tzinfo is None or datetime.fromisoformat(end) <= datetime.fromisoformat(start):
                raise AppError('ERR-ASSET-OUTAGE', 'Lịch ngừng thiết bị cần khoảng thời gian hợp lệ.', 422)
            peers = session.scalars(select(OperationsRecord).where(OperationsRecord.kind == 'ASSET_CHANGE', OperationsRecord.status.in_(('APPROVED', 'COMPLETED')), OperationsRecord.id != row.id, *context.scope_conditions(OperationsRecord))).all()
            if any(p.data.get('asset_id') == str(asset.id) and p.data.get('operation') == 'OUTAGE' and datetime.fromisoformat(p.data['starts_at']) < datetime.fromisoformat(end) and datetime.fromisoformat(p.data['ends_at']) > datetime.fromisoformat(start) for p in peers):
                raise AppError('ERR-ASSET-OUTAGE', 'Tài sản đã có lịch ngừng chồng thời gian.', 409)
        if d['operation'] == 'LABOR':
            from app.models.service import WorkOrder
            wo = load(session, context, WorkOrder, as_uuid(d.get('work_order_id')), TECHNICAL)
            from app.services.asset_operations import asset_work_orders
            if not session.scalar(asset_work_orders(asset.id).where(WorkOrder.id == wo.id)) or Decimal(d['hours']) <= 0:
                raise AppError('ERR-ASSET-LABOR', 'Giờ công cần WO đúng tài sản và số giờ dương.', 422)


def approval_effect(session, context, row):
    d = row.data
    sad_work.approve(session, context, row)
    sad_extensions.approve(session, context, row)
    targets = {'BUDGET_REVISION': (TreasuryAccount, 'budget_id', FINANCIAL), 'METER_REPLACEMENT': (Meter, 'meter_id', TECHNICAL), 'METER_CORRECTION': (MeterReading, 'reading_id', TECHNICAL), 'ADVANCE_SETTLEMENT': (Expense, 'expense_id', FINANCIAL)}
    if row.kind in targets:
        model, field, roles = targets[row.kind]
        target = load(session, context, model, as_uuid(d[field]), roles, lock=True)
        if target.building_id != row.building_id:
            raise scope_not_found()
    if row.kind == 'PURCHASE':
        quote_id = d.get('selected_quote_id')
        if not quote_id:
            raise AppError('ERR-QUOTE-SELECTION', 'Cần chọn báo giá và ghi căn cứ trước khi duyệt đơn hàng.', 409)
        quote = linked_record(session, context, as_uuid(quote_id), ('QUOTATION',), (*MANAGEMENT, 'accountant'))
        if quote.related_id != row.id or quote.status != 'APPROVED':
            raise AppError('ERR-QUOTE-SELECTION', 'Báo giá chưa được duyệt hoặc khác đề nghị mua.', 409)
        budget = load(session, context, TreasuryAccount, as_uuid(d['budget_id']), FINANCIAL, lock=True)
        amount = int(quote.data['amount_vnd'])
        if budget.spent_vnd + budget.reserved_vnd + amount > budget.limit_vnd:
            raise AppError('ERR-BUDGET-LIMIT', 'Đơn hàng vượt phần ngân sách khả dụng.', 409)
        budget.reserved_vnd += amount; budget.version += 1
        row.data = {**d, 'selected_amount_vnd': amount, 'remaining_commitment_vnd': amount}
    elif row.kind == 'BUDGET_REVISION':
        budget = load(session, context, TreasuryAccount, as_uuid(d['budget_id']), FINANCIAL, lock=True)
        if budget.kind != 'BUDGET' or budget.status != 'ACTIVE' or budget.spent_vnd + budget.reserved_vnd > d['new_limit_vnd']:
            raise AppError('ERR-BUDGET-LIMIT', 'Hạn mức mới thấp hơn chi và cam kết đã ghi nhận.', 409)
        event(session, context, budget, 'BEFORE_REVISION', d['evidence_reference'])
        budget.limit_vnd = d['new_limit_vnd']; budget.version += 1; event(session, context, budget, 'REVISION', d['evidence_reference'])
    elif row.kind == 'METER_REPLACEMENT':
        meter = load(session, context, Meter, as_uuid(d['meter_id']), TECHNICAL, lock=True); state(meter, ('ACTIVE',))
        previous = session.scalar(select(MeterReading).where(MeterReading.meter_id == meter.id).order_by(MeterReading.read_on.desc()).limit(1))
        when, value = date.fromisoformat(d['changed_on']), Decimal(d['final_value'])
        from app.services.meter_billing import effective_reading
        base = effective_reading(session, previous).value if previous else meter.baseline
        if value < base or when < meter.valid_from or when > utc_now().date() or previous and (when <= previous.read_on or previous.status != 'VERIFIED'):
            raise AppError('ERR-METER-SEQUENCE', 'Chỉ số tháo hoặc ngày thay không nối tiếp chỉ số đã xác minh.', 409)
        final = MeterReading(**scope_values(context, building_id=meter.building_id), meter_id=meter.id, read_on=when, value=value, consumption=(value-base)*meter.multiplier, evidence_reference=d['evidence_reference'], status='VERIFIED', verified_by_id=context.account_id)
        final.unit_id = meter.unit_id; final.account_id = row.account_id; session.add(final)
        from app.models.operational_control import MeterAssignment
        for assignment in session.scalars(select(MeterAssignment).where(MeterAssignment.meter_id == meter.id, MeterAssignment.valid_to.is_(None)).with_for_update()):
            if when <= assignment.valid_from:
                raise AppError('ERR-METER-ASSIGNMENT', 'Ngày tháo phải sau mốc gắn.', 409)
            assignment.valid_to = when; assignment.version += 1
        meter.valid_to = when; meter.status = 'REPLACED'; meter.version += 1
        session.flush()
        from app.api.operational_ledgers import new_meter
        from app.schemas.operational_control import MeterInput
        new = new_meter(session, context, MeterInput(building_id=meter.building_id, unit_id=meter.unit_id, code=d['new_code'], serial=d['new_serial'], commodity=meter.commodity, multiplier=meter.multiplier, baseline=d['new_baseline'], valid_from=when, upstream_id=meter.upstream_id), replaces_id=meter.id)
        row.data = {**d, 'new_meter_id': str(new.id), 'continuity_consumption': str(final.consumption)}
    elif row.kind == 'METER_CORRECTION':
        from app.models.unit import Unit
        from app.services.meter_billing import correction_sources, refresh_sources
        initial = load(session, context, MeterReading, as_uuid(d['reading_id']), TECHNICAL)
        if initial.unit_id:
            session.scalar(select(Unit).where(Unit.id == initial.unit_id).with_for_update())
        meter = load(session, context, Meter, initial.meter_id, TECHNICAL, lock=True)
        reading = load(session, context, MeterReading, initial.id, TECHNICAL, lock=True)
        before = session.scalar(select(MeterReading).where(MeterReading.meter_id == meter.id, MeterReading.read_on < reading.read_on).order_by(MeterReading.read_on.desc()).limit(1))
        after = session.scalar(select(MeterReading).where(MeterReading.meter_id == meter.id, MeterReading.read_on > reading.read_on).order_by(MeterReading.read_on).limit(1))
        from app.services.meter_billing import effective_reading
        corrected = Decimal(d['corrected_value']); base = effective_reading(session, before).value if before else meter.baseline
        if corrected < base or after and corrected > effective_reading(session, after).value:
            raise AppError('ERR-METER-CORRECTION', 'Chỉ số hiệu chỉnh phá vỡ thứ tự liên tục.', 409)
        affected = [reading, *([after] if after else [])]
        from app.services.meter_billing import financial_correction
        if financial_correction(session, context, row, meter, reading, after, corrected, base):
            return
        sources = correction_sources(session, affected)
        event(session, context, reading, 'BEFORE_CORRECTION', d['evidence_reference'])
        reading.value = corrected; reading.consumption = (corrected-base)*meter.multiplier; reading.version += 1; reading.status = 'VERIFIED'; reading.verified_by_id = context.account_id
        event(session, context, reading, 'CORRECTION', d['evidence_reference'])
        if after:
            event(session, context, after, 'BEFORE_CORRECTION', d['evidence_reference'])
            after.consumption = (after.value-corrected)*meter.multiplier; after.version += 1
            event(session, context, after, 'CONTINUITY_CORRECTION', d['evidence_reference'])
        refresh_sources(session, sources, affected, meter)
    elif row.kind == 'ADVANCE_SETTLEMENT':
        expense = load(session, context, Expense, as_uuid(d['expense_id']), FINANCIAL, lock=True)
        if expense.kind != 'ADVANCE' or expense.status != 'PAID' or d['actual_vnd'] + d['returned_vnd'] != expense.paid_vnd:
            raise AppError('ERR-ADVANCE-SETTLEMENT', 'Hoàn ứng cần chi thực tế + tiền trả lại bằng tạm ứng đã chi.', 409)
        budget = load(session, context, TreasuryAccount, expense.budget_id, FINANCIAL, lock=True)
        budget.spent_vnd -= d['returned_vnd']; budget.version += 1
        if d['returned_vnd']:
            session.add(TreasuryMovement(**scope_values(context, building_id=row.building_id), treasury_id=budget.id, expense_id=expense.id, amount_vnd=d['returned_vnd'], kind='ADVANCE_RETURN', reference=d['reference'], evidence_reference=d['evidence_reference']))
            if expense.fund_id:
                fund = load(session, context, TreasuryAccount, expense.fund_id, FINANCIAL, lock=True)
                fund.balance_vnd += d['returned_vnd']; fund.spent_vnd -= d['returned_vnd']; fund.version += 1
                session.add(TreasuryMovement(**scope_values(context, building_id=row.building_id), treasury_id=fund.id, expense_id=expense.id, amount_vnd=d['returned_vnd'], kind='ADVANCE_RETURN', reference=d['reference']+':FUND', evidence_reference=d['evidence_reference']))
        expense.status = 'SETTLED'; expense.version += 1
    elif row.kind in ('RULE', 'MASTER_DATA', 'SOP', 'EMERGENCY_PLAN', 'ORGANIZATION'):
        import hashlib
        session.execute(select(func.pg_advisory_xact_lock(int.from_bytes(hashlib.sha256(f'{row.site_id}:{row.kind}:{d["code"]}'.encode()).digest()[:8], 'big', signed=True))))
        peers = session.scalars(select(OperationsRecord).where(*context.scope_conditions(OperationsRecord), OperationsRecord.building_id == row.building_id, OperationsRecord.kind == row.kind, OperationsRecord.status == 'APPROVED', OperationsRecord.id != row.id)).all()
        start = date.fromisoformat(d['valid_from']); end = date.fromisoformat(d['valid_to']) if d.get('valid_to') else date.max
        for peer in peers:
            if peer.data['code'] != d['code']:
                continue
            if peer.data['revision'] >= d['revision'] or max(date.fromisoformat(peer.data['valid_from']), start) < min(date.fromisoformat(peer.data['valid_to']) if peer.data.get('valid_to') else date.max, end):
                raise AppError('ERR-RULE-REVISION', 'Phiên bản phải tăng và không chồng thời gian hiệu lực.', 409)
    elif row.kind == 'CONTRACT_REVISION':
        contract = linked_record(session, context, as_uuid(d['contract_id']), ('CONTRACT',), (*MANAGEMENT, 'accountant'))
        state(contract, ('APPROVED',))
        if d['operation'] in ('TERMINATE', 'LIQUIDATE'):
            completed = session.scalars(select(OperationsRecord).where(OperationsRecord.kind == 'CONTRACT_MILESTONE', OperationsRecord.status == 'COMPLETED', OperationsRecord.building_id == row.building_id)).all()
            done = {r.data['milestone_code'] for r in completed if r.data['contract_id'] == str(contract.id)}
            remaining = [m for m in contract.data.get('milestone_items', []) if m['code'] not in done]
            contract.data = {**contract.data, 'closing_decision': {'operation': d['operation'], 'reference': d['reference'], 'evidence_reference': d['evidence_reference'], 'remaining_milestones': remaining, 'at': utc_now().isoformat(), 'actor_id': str(context.account_id)}}
            if d['operation'] == 'LIQUIDATE':
                completed = session.scalars(select(OperationsRecord).where(OperationsRecord.kind == 'CONTRACT_MILESTONE', OperationsRecord.status == 'COMPLETED', OperationsRecord.building_id == row.building_id)).all()
                done = {r.data['milestone_code'] for r in completed if r.data['contract_id'] == str(contract.id)}
                if any(m['code'] not in done for m in contract.data.get('milestone_items', [])):
                    raise AppError('ERR-CONTRACT-OBLIGATIONS', 'Hợp đồng còn mốc/nghĩa vụ chưa hoàn thành.', 409)
                if contract.data.get('purchase_id'):
                    order = linked_record(session, context, as_uuid(contract.data['purchase_id']), ('PURCHASE',), FINANCIAL)
                    unpaid = session.scalar(select(Expense.id).where(Expense.procurement_id == order.id, Expense.status.not_in(('PAID', 'SETTLED', 'REJECTED'))).limit(1))
                    if unpaid or order.data.get('remaining_commitment_vnd', 0):
                        raise AppError('ERR-CONTRACT-OBLIGATIONS', 'Còn cam kết hoặc chứng từ chưa chi xong.', 409)
            contract.status = 'TERMINATED' if d['operation'] == 'TERMINATE' else 'CLOSED'
        else:
            if date.fromisoformat(d['ends_on']) <= date.fromisoformat(d['starts_on']):
                raise AppError('ERR-CONTRACT-INTERVAL', 'Khoảng hợp đồng mới không hợp lệ.', 422)
            if d['operation'] == 'RENEW' and date.fromisoformat(d['starts_on']) < date.fromisoformat(contract.data['ends_on']):
                raise AppError('ERR-CONTRACT-INTERVAL', 'Gia hạn phải nối tiếp hợp đồng cũ.', 409)
            replacement = OperationsRecord(**scope_values(context, building_id=contract.building_id), kind='CONTRACT', title=row.title, related_id=contract.id,
                data={**contract.data, **{k: d[k] for k in ('reference', 'starts_on', 'ends_on', 'amount_vnd', 'milestones')}, **({'milestone_items': d['milestone_items']} if d.get('milestone_items') is not None else {})}, status='APPROVED', approved_by_id=context.account_id)
            replacement.account_id = row.account_id; validate_links(session, context, replacement); session.add(replacement); session.flush()
            contract.status = 'SUPERSEDED'; row.data = {**d, 'new_contract_id': str(replacement.id)}
        contract.version += 1; event(session, context, contract, d['operation'], d['evidence_reference'])
    elif row.kind == 'LEASE_DEPOSIT':
        from app.models.property import LeaseContract
        lease = load(session, context, LeaseContract, as_uuid(d['lease_id']), FINANCIAL, lock=True)
        policy = linked_record(session, context, as_uuid(d['policy_id']), ('DEPOSIT_POLICY',), FINANCIAL)
        when = utc_now().date()
        if lease.status != 'ACTIVE' or lease.building_id != row.building_id or policy.status != 'APPROVED' or policy.data['source_kind'] != 'LEASE' or when < date.fromisoformat(policy.data['valid_from']) or policy.data.get('valid_to') and when >= date.fromisoformat(policy.data['valid_to']):
            raise AppError('ERR-DEPOSIT-POLICY', 'Hợp đồng/chính sách cọc thuê không còn hiệu lực.', 409)
        from app.services.portal_finance import create_deposit
        from app.models.resident_portal import PortalDeposit
        if session.scalar(select(PortalDeposit.id).where(PortalDeposit.source_kind == 'LEASE', PortalDeposit.source_id == lease.id)):
            raise AppError('ERR-DEPOSIT-DUPLICATE', 'Hợp đồng đã có hồ sơ cọc.', 409)
        deposit = create_deposit(session, lease, 'LEASE', int(policy.data['amount_vnd']))
        session.flush()
        row.data = {**d, 'deposit_id': str(deposit.id) if deposit else None, 'policy_snapshot': policy.data}


def completion_effect(session, context, row):
    if row.kind == 'DATA_QUALITY':
        from app.models.resident_portal import PortalDossier
        dossier = load(session, context, PortalDossier, as_uuid(row.data['correction_dossier_id']), ('admin', 'director'))
        if dossier.status not in ('APPROVED', 'COMPLETED') or dossier.building_id != row.building_id:
            raise AppError('ERR-DATA-CORRECTION', 'Cần hồ sơ hiệu chỉnh đã duyệt trong cùng phạm vi.', 409)
    if row.kind == 'DELIVERY':
        if row.data.get('defects') and not row.data.get('defect_resolution'):
            raise AppError('ERR-DELIVERY-DEFECT', 'Cần kết luận khắc phục thiếu/lỗi trước nghiệm thu.', 409)
        if row.data.get('accepted_quantity') is None:
            if row.data.get('defects') or Decimal(row.data.get('rejected_quantity', '0')):
                raise AppError('ERR-DELIVERY-ACCEPTANCE', 'Cần phân loại lượng đạt/lỗi trước nghiệm thu.', 409)
            row.data = {**row.data, 'accepted_quantity': row.data['quantity']}
        if Decimal(row.data['accepted_quantity']) + Decimal(row.data.get('rejected_quantity', '0')) != Decimal(row.data['quantity']):
            raise AppError('ERR-DELIVERY-ACCEPTANCE', 'Tổng lượng đạt/lỗi khác lượng thực giao.', 422)
    if row.kind == 'ASSET_CHANGE':
        from app.models.maintenance import Asset
        d = row.data; asset = load(session, context, Asset, as_uuid(d['asset_id']), TECHNICAL, lock=True)
        event(session, context, asset, 'BEFORE_' + d['operation'], d['evidence_reference'])
        if d['operation'] in ('PROFILE', 'MOVE'):
            asset.location = d['location']
            if d.get('serial'):
                asset.serial = d['serial']
        if d['operation'] in ('PROFILE', 'WARRANTY'):
            if d.get('warranty_until'):
                asset.warranty_until = date.fromisoformat(d['warranty_until'])
        if d['operation'] in ('PROFILE', 'INSPECTION', 'RESTORE'):
            if d.get('inspection_due_on'):
                asset.inspection_due_on = date.fromisoformat(d['inspection_due_on'])
        if d['operation'] in ('MOVE', 'RETIRE', 'REPLACE', 'DISPOSE'):
            from app.models.service import WorkOrder
            from app.models.maintenance import MaintenancePlan
            from app.services.asset_operations import asset_work_orders
            if session.scalar(asset_work_orders(asset.id).where(WorkOrder.status.not_in(('CLOSED', 'CANCELLED'))).limit(1)):
                raise AppError('ERR-ASSET-OPEN-WORK', 'Tài sản còn WO mở; cần xử lý trước khi chuyển/ngừng.', 409)
            for plan in session.scalars(select(MaintenancePlan).where(MaintenancePlan.asset_id == asset.id).with_for_update()):
                plan.is_active = False; plan.version += 1
        if d['operation'] == 'MOVE':
            from app.services.operational_control import building_scope
            if not d.get('target_building_id'):
                raise AppError('ERR-ASSET-LOCATION', 'Điều chuyển cần tòa đích.', 422)
            target = building_scope(session, context, as_uuid(d['target_building_id']), TECHNICAL)
            asset.building_id = target.id; asset.unit_id = None
        elif d['operation'] in ('RETIRE', 'REPLACE', 'DISPOSE'):
            if d['operation'] == 'REPLACE':
                replacement = load(session, context, Asset, as_uuid(d.get('replacement_asset_id')), TECHNICAL)
                if replacement.id == asset.id or replacement.status != 'ACTIVE':
                    raise AppError('ERR-ASSET-REPLACEMENT', 'Tài sản thay thế không phù hợp.', 422)
            asset.status = 'DISPOSED' if d['operation'] == 'DISPOSE' else 'RETIRED'
        elif d['operation'] == 'RESTORE':
            if asset.status != 'INACTIVE' or not d.get('inspection_due_on') or date.fromisoformat(d['inspection_due_on']) < utc_now().date():
                raise AppError('ERR-ASSET-RESTORE', 'Khôi phục cần tài sản đang ngừng và kiểm định còn hiệu lực.', 409)
            asset.status = 'ACTIVE'
        asset.version += 1; asset.updated_by_id = context.account_id
        event(session, context, asset, d['operation'], d['evidence_reference'])
