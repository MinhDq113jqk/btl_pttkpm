"""SAD T01–T08 relationships and workflow guards, shared by API and UI catalog."""
import hashlib
import json
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID
from sqlalchemy import select, func, or_
from app.core.exceptions import AppError
from app.core.policy import scope_not_found, context_for_account
from app.models.operational_control import OperationsRecord, Meter, MeterReading, MeterAssignment, Expense, StockItem, StockMovement
from app.models.billing import FeePolicy, FeePolicyVersion, BillingAccount
from app.models.unit import Unit
from app.services.operational_control import load, state, as_uuid, MANAGEMENT, FINANCIAL, TECHNICAL, SECURITY, event, building_scope, data_model
from app.services.resident_portal import scope_values, unit_for, view
from app.services.r2 import utc_now
from app.schemas import sad_work as schemas

EXTRA_RECORDS = {
    'MASTER_DATA': (schemas.CatalogData, ('admin', 'director')),
    'ORGANIZATION': (schemas.OrganizationData, ('admin', 'director')),
    'BUILDING_ZONE': (schemas.BuildingZoneData, ('admin', 'director')),
    'BUILDING_PROFILE': (schemas.BuildingProfileData, ('admin', 'director')),
    'SITE_PROFILE': (schemas.SiteProfileData, ('admin', 'director')),
    'TOOL_CUSTODY': (schemas.ToolCustodyData, TECHNICAL),
    'FEE_PUBLICATION': (schemas.FeePublicationData, FINANCIAL),
    'FEE_BENEFIT': (schemas.BenefitData, FINANCIAL),
    'METER_DISCREPANCY': (schemas.MeterDiscrepancyData, TECHNICAL),
    'ASSET_WORK_LINK': (schemas.AssetWorkLinkData, TECHNICAL),
    'BUDGET_VARIANCE': (schemas.BudgetVarianceData, FINANCIAL),
    'CONTRACT_MILESTONE': (schemas.ContractMilestoneData, (*MANAGEMENT, 'accountant')),
    'VENDOR_EVALUATION': (schemas.VendorEvaluationData, MANAGEMENT),
    'UOM_CONVERSION': (schemas.UomConversionData, TECHNICAL),
    'WASTE': (schemas.WasteData, (*MANAGEMENT, 'cleaning')),
    'LANDSCAPE': (schemas.EnvironmentWorkData, (*MANAGEMENT, 'cleaning')),
    'PEST': (schemas.EnvironmentWorkData, (*MANAGEMENT, 'cleaning')),
    'ENV_INCIDENT': (schemas.EnvironmentIncidentData, (*MANAGEMENT, 'cleaning')),
    'RISK': (schemas.RiskData, MANAGEMENT),
    'INSPECTION': (schemas.InspectionData, (*MANAGEMENT, 'technical_lead')),
    'DRILL': (schemas.InspectionData, SECURITY),
    'EMERGENCY_PLAN': (schemas.EmergencyPlanData, SECURITY),
    'TRAINING': (schemas.TrainingData, MANAGEMENT),
    'WORK_ASSIGNMENT': (schemas.AssignmentData, (*MANAGEMENT, 'technical_lead')),
}
RESULT_KINDS = {'WASTE', 'LANDSCAPE', 'PEST', 'ENV_INCIDENT', 'RISK', 'INSPECTION', 'DRILL', 'METER_DISCREPANCY'}


def record_ref(session, context, row, identifier, kind, states=('APPROVED', 'COMPLETED')):
    # Cross-domain reads still require explicit building authority, not an unscoped session.get.
    roles = ('admin', 'director', 'cskh', 'technical_lead', 'technician', 'cleaning', 'security') if kind in ('STAFF', 'ROSTER', 'SOP') else EXTRA_RECORDS.get(kind, (None, MANAGEMENT))[1]
    source = load(session, context, OperationsRecord, as_uuid(identifier), roles, lock=True)
    if source.kind != kind or source.building_id != row.building_id:
        raise scope_not_found()
    state(source, states)
    return source


def account_in_building(session, context, row, identifier):
    from app.models.account import Account
    account = session.scalar(select(Account).where(Account.id == as_uuid(identifier), Account.tenant_id == row.tenant_id, Account.is_active.is_(True)))
    if not account or not any(g.building_id == row.building_id or g.building_id is None and g.role in ('admin', 'director', 'accountant')
                              for g in context_for_account(session, account, row.site_id).role_grants):
        raise scope_not_found()
    return account


def active_on(row, when):
    return row.status == 'APPROVED' and date.fromisoformat(row.data['valid_from']) <= when and (not row.data.get('valid_to') or when < date.fromisoformat(row.data['valid_to']))


def scoped_target(session, context, row, model, identifier, roles):
    target = load(session, context, model, as_uuid(identifier), roles, lock=True)
    if target.building_id != row.building_id:
        raise scope_not_found()
    return target


def validate(session, context, row):
    d = row.data
    if row.kind == 'SITE_PROFILE' or row.kind == 'BUILDING_PROFILE' and d['operation'] == 'CREATE':
        if not any(g.role in ('admin', 'director') and g.building_id is None for g in context.role_grants):
            raise scope_not_found()
    if row.kind == 'BUDGET_VARIANCE':
        from app.models.operational_control import TreasuryAccount
        budget = scoped_target(session, context, row, TreasuryAccount, d['budget_id'], FINANCIAL)
        if budget.kind != 'BUDGET':
            raise AppError('ERR-BUDGET-REFERENCE', 'Giải thích cần ngân sách đúng loại.', 422)
    for key in ('owner_account_id', 'representative_account_id', 'responsible_account_id'):
        if d.get(key):
            account_in_building(session, context, row, d[key])
    if row.kind == 'TOOL_CUSTODY':
        account_in_building(session, context, row, d['custodian_account_id'])
        movement = scoped_target(session, context, row, StockMovement, d['source_movement_id'], TECHNICAL)
        if movement.kind != 'ISSUE' or movement.status != 'POSTED':
            raise AppError('ERR-TOOL-ORIGIN', 'Công cụ cần phiếu xuất đã ghi sổ.', 409)
        if row.status in (None, 'DRAFT', 'SUBMITTED', 'REJECTED') and movement.custody.get('recipient_account_id') != d['custodian_account_id']:
            raise AppError('ERR-TOOL-CUSTODIAN', 'Người giữ ban đầu phải là người nhận trên phiếu xuất.', 409)
    if row.kind in ('BUILDING_ZONE', 'BUILDING_PROFILE'):
        from app.models.property import PropertyNode
        zone = load(session, context, PropertyNode, as_uuid(d['zone_id']), ('admin', 'director'))
        if zone.kind != 'ZONE' or zone.status != 'ACTIVE' or zone.site_id != row.site_id:
            raise scope_not_found()
    if row.kind == 'FEE_PUBLICATION':
        tariff = scoped_target(session, context, row, FeePolicyVersion, d['fee_version_id'], FINANCIAL)
        if tariff.published_at:
            raise AppError('ERR-FEE-ALREADY-PUBLISHED', 'Phiên bản đã được công bố.', 409)
    if row.kind == 'FEE_BENEFIT':
        scoped_target(session, context, row, FeePolicy, d['fee_policy_id'], FINANCIAL)
        for uid in d['unit_ids']:
            if unit_for(session, context, as_uuid(uid), roles=FINANCIAL).building_id != row.building_id:
                raise scope_not_found()
    if row.kind == 'CONTRACT':
        milestones = [data_model(schemas.Milestone, m).model_dump(mode='json') for m in d.get('milestone_items', [])]
        if milestones and (len({m['code'] for m in milestones}) != len(milestones) or sum(m['amount_vnd'] for m in milestones) != d['amount_vnd']
                           or any(not d['starts_on'] <= m['due_on'] <= d['ends_on'] for m in milestones)):
            raise AppError('ERR-CONTRACT-MILESTONES', 'Mốc phải duy nhất, trong thời hạn và tổng bằng giá trị hợp đồng.', 422)
        if d.get('allows_partial_payment') and not d.get('partial_payment_reference'):
            raise AppError('ERR-POLICY-INCOMPLETE', 'Thanh toán theo phần cần điều khoản đã xác nhận.', 422)
        if d.get('purchase_id'):
            order = record_ref(session, context, row, d['purchase_id'], 'PURCHASE')
            quote = record_ref(session, context, row, order.data['selected_quote_id'], 'QUOTATION')
            if quote.data['vendor_id'] != d['vendor_id'] or order.data['selected_amount_vnd'] != d['amount_vnd']:
                raise AppError('ERR-CONTRACT-ORDER', 'Hợp đồng khác NCC hoặc giá trị đơn hàng.', 409)
    if row.kind == 'CONTRACT_MILESTONE':
        contract = record_ref(session, context, row, d['contract_id'], 'CONTRACT', ('APPROVED',))
        if d['milestone_code'] not in {m['code'] for m in contract.data.get('milestone_items', [])}:
            raise AppError('ERR-CONTRACT-MILESTONE', 'Mốc không thuộc hợp đồng.', 422)
        peers = session.scalars(select(OperationsRecord).where(OperationsRecord.kind == row.kind, OperationsRecord.building_id == row.building_id, OperationsRecord.id != row.id, OperationsRecord.status.not_in(('REJECTED', 'CANCELLED')))).all()
        if any(p.data['contract_id'] == d['contract_id'] and p.data['milestone_code'] == d['milestone_code'] for p in peers):
            raise AppError('ERR-CONTRACT-MILESTONE-DUPLICATE', 'Mốc đã có hồ sơ nghiệm thu.', 409)
    if row.kind == 'VENDOR_EVALUATION':
        contract = record_ref(session, context, row, d['contract_id'], 'CONTRACT', ('APPROVED', 'SUPERSEDED', 'CLOSED', 'TERMINATED'))
        record_ref(session, context, row, d['vendor_id'], 'VENDOR')
        if contract.data['vendor_id'] != d['vendor_id']:
            raise scope_not_found()
        for identifier in d['delivery_ids']:
            delivery = record_ref(session, context, row, identifier, 'DELIVERY', ('COMPLETED',))
            if str(delivery.related_id) != contract.data.get('purchase_id'):
                raise scope_not_found()
    if row.kind == 'UOM_CONVERSION':
        item = scoped_target(session, context, row, StockItem, d['item_id'], TECHNICAL)
        if item.uom == d['from_uom'] or d.get('valid_to') and d['valid_to'] <= d['valid_from']:
            raise AppError('ERR-UOM-CONVERSION', 'Đơn vị nguồn/hiệu lực quy đổi không hợp lệ.', 422)
    if row.kind == 'ENV_INCIDENT' and d['hazardous']:
        from app.models.operations import SecurityIncident
        if not d.get('security_incident_id'):
            raise AppError('ERR-ENV-SAFETY-LINK', 'Sự cố nguy hiểm cần hồ sơ an toàn trong cùng tòa.', 422)
        scoped_target(session, context, row, SecurityIncident, d['security_incident_id'], (*MANAGEMENT, 'cleaning'))
    if row.kind in ('INSPECTION', 'DRILL'):
        for finding in d['findings']:
            account_in_building(session, context, row, finding['owner_account_id'])
        if row.kind == 'DRILL' and not d.get('plan_id'):
            raise AppError('ERR-EMERGENCY-PLAN', 'Diễn tập cần phiên bản phương án.', 422)
        if d.get('plan_id'):
            record_ref(session, context, row, d['plan_id'], 'EMERGENCY_PLAN', ('APPROVED',))
    if row.kind == 'TRAINING':
        sop = record_ref(session, context, row, d['sop_id'], 'SOP', ('APPROVED',))
        if not active_on(sop, datetime.fromisoformat(d['scheduled_at']).date()):
            raise AppError('ERR-SOP-EFFECTIVITY', 'SOP không có hiệu lực vào thời điểm đào tạo.', 409)
        for identifier in d['staff_ids']:
            record_ref(session, context, row, identifier, 'STAFF', ('APPROVED',))
    if row.kind == 'STAFF' and d.get('catalog_ids'):
        catalogs = [record_ref(session, context, row, identifier, 'MASTER_DATA', ('APPROVED',)) for identifier in d['catalog_ids']]
        for field, catalog in [('team', 'TEAM'), ('position', 'POSITION'), ('territory', 'TERRITORY')]:
            if d.get(field) and not any(c.data['catalog'] == catalog and active_on(c, utc_now().date()) and any(e['code'] == d[field] and e['active'] for e in c.data['entries']) for c in catalogs):
                raise AppError('ERR-STAFF-CATALOG', 'Nhân sự cần mã tổ/vị trí/địa bàn thuộc danh mục có hiệu lực.', 422)
    if row.kind == 'ASSET_WORK_LINK':
        from app.models.maintenance import Asset
        from app.models.service import WorkOrder
        asset = scoped_target(session, context, row, Asset, d['asset_id'], TECHNICAL)
        wo = scoped_target(session, context, row, WorkOrder, d['work_order_id'], TECHNICAL)
        if wo.status != 'DRAFT' or asset.status != 'ACTIVE' or wo.asset_id and wo.asset_id != asset.id:
            raise AppError('ERR-ASSET-WORK-LINK', 'WO đã đóng hoặc tài sản không phù hợp.', 409)
    if row.kind == 'WORK_ASSIGNMENT':
        assignment_candidate(session, context, row)
    if row.kind == 'METER_DISCREPANCY':
        scoped_target(session, context, row, Meter, d['meter_id'], TECHNICAL)
        if d['ends_on'] <= d['starts_on']:
            raise AppError('ERR-METER-INTERVAL', 'Khoảng đối chiếu không hợp lệ.', 422)
        if d['resolution'] == 'CORRECTION':
            correction = record_ref(session, context, row, d.get('correction_record_id'), 'METER_CORRECTION')
            reading = load(session, context, MeterReading, as_uuid(correction.data['reading_id']), TECHNICAL)
            if str(reading.meter_id) != d['meter_id']:
                raise scope_not_found()


def preview_fee(session, context, row):
    tariff = scoped_target(session, context, row, FeePolicyVersion, row.data['fee_version_id'], FINANCIAL)
    policy = session.scalar(select(FeePolicy).where(FeePolicy.id == tariff.fee_policy_id).with_for_update())
    versions = session.scalars(select(FeePolicyVersion).where(FeePolicyVersion.fee_policy_id == tariff.fee_policy_id, FeePolicyVersion.published_at.is_not(None)).order_by(FeePolicyVersion.effective_from)).all()
    before = [v for v in versions if v.effective_from <= tariff.effective_from]
    previous = before[-1] if before else None
    from app.models.property import UnitProfileEpisode
    profiles = session.scalars(select(UnitProfileEpisode).where(UnitProfileEpisode.building_id == row.building_id)).all()
    units = session.scalars(select(Unit).where(Unit.building_id == row.building_id).order_by(Unit.id)).all()
    items = []
    for unit in units:
        profile = next((p for p in profiles if p.unit_id == unit.id and p.valid_from <= tariff.effective_from and (not p.valid_to or p.valid_to > tariff.effective_from)), None)
        quantity = Decimal(1) if tariff.basis == 'FIXED_UNIT' else (getattr(profile or unit, tariff.area_field, None) if tariff.basis == 'UNIT_AREA_M2' else None)
        def amount(rate):
            return int((Decimal(quantity) * rate.unit_rate_vnd / rate.rounding_unit_vnd).quantize(Decimal(1), rounding=ROUND_HALF_UP)) * rate.rounding_unit_vnd if quantity is not None else None
        old = amount(previous) if previous and previous.basis == tariff.basis and previous.area_field == tariff.area_field else None
        new = amount(tariff)
        items.append({'unit_id': str(unit.id), 'unit_number': unit.unit_number, 'quantity': str(quantity) if quantity is not None else None,
                      'before_vnd': old, 'after_vnd': new, 'difference_vnd': new-old if old is not None and new is not None else None,
                      'status': 'MEASURED_VOLUME_REQUIRED' if tariff.basis == 'SERVICE_UNIT' else 'MISSING_AREA' if quantity is None else 'ESTIMATED',
                      'unit_version': unit.version, 'profile_id': str(profile.id) if profile else None, 'profile_version': profile.version if profile else None})
    benefits = session.scalars(select(OperationsRecord).where(OperationsRecord.kind == 'FEE_BENEFIT', OperationsRecord.building_id == row.building_id, OperationsRecord.status == 'APPROVED')).all()
    snapshot = {'tariff': view(tariff), 'policy_active': policy.is_active, 'previous': [view(v) for v in versions], 'items': items,
                'benefits': [view(b) for b in benefits], 'note': 'Ước tính kỳ đầy đủ trước miễn giảm. Biểu phí tiêu thụ hiển thị thay đổi đơn giá; chưa có sản lượng không suy tiền bằng 0.',
                'unit_rate_vnd': tariff.unit_rate_vnd, 'before_unit_rate_vnd': previous.unit_rate_vnd if previous else None}
    from fastapi.encoders import jsonable_encoder
    snapshot = jsonable_encoder(snapshot)
    return {'snapshot': snapshot, 'hash': hashlib.sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode()).hexdigest()}


def approve(session, context, row):
    d = row.data
    if row.kind == 'MASTER_DATA':
        peers = session.scalars(select(OperationsRecord).where(OperationsRecord.kind == 'MASTER_DATA', OperationsRecord.status == 'APPROVED', OperationsRecord.building_id == row.building_id, OperationsRecord.id != row.id)).all()
        peers = [p for p in peers if p.data['catalog'] == d['catalog']]
        for previous in peers:
            if max(previous.data['valid_from'], d['valid_from']) < min(previous.data.get('valid_to') or '9999-12-31', d.get('valid_to') or '9999-12-31'):
                raise AppError('ERR-CATALOG-OVERLAP', 'Danh mục cùng loại không được chồng hiệu lực trong tòa.', 409)
        if peers:
            latest = max(peers, key=lambda p: p.data['revision'])
            incoming = {e['code']: e for e in d['entries']}
            if latest.data['revision'] >= d['revision'] or any(e['code'] not in incoming or not e['active'] and incoming[e['code']]['active'] for e in latest.data['entries']):
                raise AppError('ERR-CATALOG-IDENTITY', 'Phiên bản phải tăng; giữ mã cũ và không tái dùng mã đã ngừng.', 409)
    if row.kind == 'STAFF':
        account_in_building(session, context, row, d['account_id'])
        peers = session.scalars(select(OperationsRecord).where(OperationsRecord.kind == 'STAFF', OperationsRecord.status == 'APPROVED', OperationsRecord.building_id == row.building_id, OperationsRecord.id != row.id).with_for_update()).all()
        old = [p for p in peers if p.data['account_id'] == d['account_id']]
        if old:
            if len(old) != 1 or row.related_id != old[0].id:
                raise AppError('ERR-STAFF-DUPLICATE', 'Tài khoản đã có hồ sơ; chọn hồ sơ đó làm bản được thay thế.', 409)
            rosters = session.scalars(select(OperationsRecord).where(OperationsRecord.kind == 'ROSTER', OperationsRecord.status.in_(('APPROVED', 'IN_PROGRESS')), OperationsRecord.building_id == row.building_id)).all()
            if any(r.data['staff_id'] == str(old[0].id) and datetime.fromisoformat(r.data['ends_at']) >= utc_now() for r in rosters):
                raise AppError('ERR-STAFF-ACTIVE-ROSTER', 'Cần xử lý ca hiện hành trước khi thay hồ sơ nhân sự.', 409)
            old[0].status = 'SUPERSEDED'; old[0].version += 1; event(session, context, old[0], 'SUPERSEDED', 'Hồ sơ năng lực được thay bằng bản đã duyệt.')
    if row.kind == 'SITE_PROFILE':
        from app.models.site import Site
        site = session.scalar(select(Site).where(Site.id == row.site_id, Site.tenant_id == row.tenant_id).with_for_update())
        row.data = {**d, 'before': {'name': site.name, 'address': site.address}}
        site.name = d['name']; site.address = d['address']
    if row.kind == 'BUILDING_PROFILE':
        from app.models.building import Building
        from app.models.property import PropertyNode
        from app.models.site import Site
        session.scalar(select(Site).where(Site.id == row.site_id).with_for_update())
        if d['operation'] == 'CREATE':
            if session.scalar(select(Building.id).where(Building.site_id == row.site_id, Building.code == d['code'])):
                raise AppError('ERR-PROPERTY-CODE', 'Mã tòa đã tồn tại, không được tái sử dụng.', 409)
            building = Building(site_id=row.site_id, code=d['code'], name=d['name'], floors_count=d['floors_count'], zone_id=as_uuid(d['zone_id']))
            session.add(building); session.flush(); row.data = {**d, 'created_building_id': str(building.id)}
        else:
            building = session.scalar(select(Building).where(Building.id == row.building_id, Building.site_id == row.site_id).with_for_update())
            if building.code != d['code'] or building.zone_id != as_uuid(d['zone_id']):
                raise AppError('ERR-PROPERTY-IDENTITY', 'Mã tòa được giữ ổn định; đổi phân khu dùng hồ sơ liên kết riêng.', 409)
            if d['operation'] == 'DEACTIVATE' and (session.scalar(select(PropertyNode.id).where(PropertyNode.building_id == building.id, PropertyNode.status == 'ACTIVE').limit(1)) or session.scalar(select(Unit.id).where(Unit.building_id == building.id, Unit.status != 'INACTIVE').limit(1))):
                raise AppError('ERR-PROPERTY-CHILD', 'Cần ngừng các tầng/không gian/căn trước khi ngừng tòa.', 409)
            row.data = {**d, 'before': {'name': building.name, 'floors_count': building.floors_count, 'status': building.status, 'version': building.version}}
            building.name = d['name']; building.floors_count = d['floors_count']
            if d['operation'] in ('ACTIVATE', 'DEACTIVATE'): building.status = 'ACTIVE' if d['operation'] == 'ACTIVATE' else 'INACTIVE'
            building.version += 1
    if row.kind == 'BUDGET_VARIANCE':
        from app.models.operational_control import TreasuryAccount
        budget = scoped_target(session, context, row, TreasuryAccount, d['budget_id'], FINANCIAL)
        row.data = {**d, 'budget_snapshot': {'version': budget.version, 'limit_vnd': budget.limit_vnd, 'reserved_vnd': budget.reserved_vnd, 'spent_vnd': budget.spent_vnd, 'as_of': utc_now().isoformat()}}
    if row.kind == 'METER_DISCREPANCY':
        from app.services.meter_assignments import reconciliation
        meter = scoped_target(session, context, row, Meter, d['meter_id'], TECHNICAL)
        from fastapi.encoders import jsonable_encoder
        row.data = {**d, 'comparison_snapshot': jsonable_encoder(reconciliation(session, meter, date.fromisoformat(d['starts_on']), date.fromisoformat(d['ends_on'])))}
    if row.kind == 'WORK_ASSIGNMENT':
        target, staff = assignment_candidate(session, context, row)
        pending = session.scalars(select(OperationsRecord).where(OperationsRecord.kind == row.kind, OperationsRecord.status == 'APPROVED', OperationsRecord.building_id == row.building_id).with_for_update()).all()
        for previous in pending:
            if previous.data['target_type'] == d['target_type'] and previous.data['target_id'] == d['target_id']:
                previous.status = 'CANCELLED'; previous.version += 1; event(session, context, previous, 'SUPERSEDED', 'Đã có phân công thay thế được duyệt.')
        row.data = {**d, 'target_version': target.version}
    if row.kind == 'FEE_PUBLICATION':
        preview = d.get('preview')
        if not preview or preview['hash'] != preview_fee(session, context, row)['hash']:
            raise AppError('ERR-FEE-PREVIEW-STALE', 'Cần xem lại tác động do dữ liệu/biểu phí đã đổi.', 409)
        tariff = scoped_target(session, context, row, FeePolicyVersion, d['fee_version_id'], FINANCIAL)
        if tariff.created_by_id == context.account_id:
            raise AppError('ERR-INDEPENDENT-CHECKER', 'Người tạo biểu phí không được tự công bố.', 403)
        from app.api.billing import _assert_publish_does_not_change_closing_period
        policy = session.get(FeePolicy, tariff.fee_policy_id)
        _assert_publish_does_not_change_closing_period(session, policy, tariff.effective_from)
        if tariff.basis == 'SERVICE_UNIT' and (not tariff.tariff.get('commodity') or not tariff.tariff.get('uom')):
            raise AppError('ERR-METER-TARIFF', 'Biểu phí tiêu thụ cần loại đo và đơn vị.', 422)
        if any(v.effective_from > tariff.effective_from for v in session.scalars(select(FeePolicyVersion).where(FeePolicyVersion.fee_policy_id == tariff.fee_policy_id, FeePolicyVersion.published_at.is_not(None)))):
            raise AppError('ERR-FEE-EFFECTIVITY', 'Không công bố hồi tố trước phiên bản đã có.', 409)
        tariff.published_at = utc_now(); tariff.version += 1
    if row.kind == 'BUILDING_ZONE':
        from app.models.building import Building
        from app.models.property import PropertyNode
        building = session.scalar(select(Building).where(Building.id == row.building_id).with_for_update())
        floors = session.scalars(select(PropertyNode).where(PropertyNode.building_id == building.id, PropertyNode.kind == 'FLOOR').with_for_update()).all()
        for floor in floors:
            if floor.parent_id and floor.parent_id != as_uuid(d['zone_id']):
                raise AppError('ERR-BUILDING-ZONE', 'Tầng đã liên kết phân khu khác; cần xử lý trước.', 409)
        row.data = {**d, 'before_zone_id': str(building.zone_id) if building.zone_id else None, 'before_building_version': building.version}
        building.zone_id = as_uuid(d['zone_id']); building.version += 1
        for floor in floors:
            floor.parent_id = building.zone_id; floor.version += 1
    if row.kind == 'FEE_BENEFIT':
        peers = session.scalars(select(OperationsRecord).where(OperationsRecord.kind == row.kind, OperationsRecord.building_id == row.building_id, OperationsRecord.status == 'APPROVED')).all()
        if any(p.data['fee_policy_id'] == d['fee_policy_id'] and set(p.data['unit_ids']) & set(d['unit_ids']) and max(p.data['valid_from'], d['valid_from']) < min(p.data['valid_to'], d['valid_to']) for p in peers):
            raise AppError('ERR-BENEFIT-OVERLAP', 'Ưu đãi cùng chính sách/căn chồng thời gian.', 409)
    if row.kind == 'ASSET_WORK_LINK':
        from app.models.service import WorkOrder
        from app.models.maintenance import Asset
        wo = scoped_target(session, context, row, WorkOrder, d['work_order_id'], TECHNICAL)
        asset = scoped_target(session, context, row, Asset, d['asset_id'], TECHNICAL)
        wo.asset_id = asset.id; wo.asset_snapshot = {'code': asset.code, 'location': asset.location, 'building_id': str(asset.building_id), 'warranty_until': str(asset.warranty_until) if asset.warranty_until else None, 'decision': d, 'linked_at': utc_now().isoformat()}; wo.version += 1


def complete(session, context, row, action_data):
    d = row.data
    validate(session, context, row)
    if row.kind in RESULT_KINDS:
        for key in ('result', 'completion_evidence_reference'):
            if not isinstance(action_data.get(key), str) or not 3 <= len(action_data[key]) <= 4000:
                raise AppError('ERR-COMPLETION-EVIDENCE', 'Hoàn thành cần kết quả và bằng chứng khắc phục.', 422)
        if row.kind in ('INSPECTION', 'DRILL'):
            resolutions = action_data.get('finding_results', [])
            if len(resolutions) != len(d['findings']) or any(not isinstance(r, str) or len(r.strip()) < 3 for r in resolutions):
                raise AppError('ERR-FINDING-INCOMPLETE', 'Cần kết quả cho từng phát hiện.', 422)
        row.data = {**d, 'completion': {**action_data, 'actor_id': str(context.account_id), 'completed_at': utc_now().isoformat()}}
        if row.kind == 'METER_DISCREPANCY':
            from app.services.meter_assignments import reconciliation
            from fastapi.encoders import jsonable_encoder
            meter = scoped_target(session, context, row, Meter, d['meter_id'], TECHNICAL)
            comparison = reconciliation(session, meter, date.fromisoformat(d['starts_on']), date.fromisoformat(d['ends_on']))
            if comparison['status'] != 'COMPLETE':
                raise AppError('ERR-METER-INCOMPLETE', 'Còn thiếu dữ liệu khoảng đo; chưa được đóng chênh lệch.', 409)
            row.data = {**row.data, 'resolved_comparison': jsonable_encoder(comparison)}
    if row.kind == 'TRAINING':
        if set(d.get('acknowledgements', {})) != set(d['staff_ids']):
            raise AppError('ERR-TRAINING-INCOMPLETE', 'Còn nhân sự chưa xác nhận đúng phiên bản SOP.', 409)
    if row.kind == 'WORK_ASSIGNMENT':
        raise AppError('ERR-ASSIGNMENT-ACK', 'Nhân sự cần tiếp nhận phân công.', 409)


def assignment_candidate(session, context, row):
    from app.models.service import WorkOrder
    from app.models.operations import CleaningTask, CleaningShift, SecurityShift
    d = row.data
    roster = record_ref(session, context, row, d['roster_id'], 'ROSTER', ('APPROVED', 'IN_PROGRESS'))
    staff = record_ref(session, context, row, roster.data['staff_id'], 'STAFF', ('APPROVED',))
    account = account_in_building(session, context, row, staff.data['account_id'])
    start, end = datetime.fromisoformat(roster.data['starts_at']), datetime.fromisoformat(roster.data['ends_at'])
    if d['target_type'] == 'WORK_ORDER' and not start <= utc_now() < end:
        raise AppError('ERR-ROSTER-TIME', 'WO cần ca đang có hiệu lực.', 409)
    if d['required_skill'] not in staff.data['skills'] or staff.data.get('certificate_expires_on') and date.fromisoformat(staff.data['certificate_expires_on']) < end.date():
        raise AppError('ERR-STAFF-SKILL', 'Nhân sự thiếu năng lực hoặc chứng nhận còn hạn.', 409)
    model = {'WORK_ORDER': WorkOrder, 'CLEANING': CleaningTask, 'SECURITY': SecurityShift}[d['target_type']]
    target = scoped_target(session, context, row, model, d['target_id'], (*MANAGEMENT, 'technical_lead', 'technician', 'cleaning', 'security'))
    if row.status == 'APPROVED' and d.get('target_version') and target.version != d['target_version']:
        raise AppError('ERR-ASSIGNMENT-STALE', 'Công việc đã thay đổi sau khi duyệt phân công.', 409)
    if target.status in ('CLOSED', 'CANCELLED', 'COMPLETED', 'ACCEPTED'):
        raise AppError('ERR-WORK-CLOSED', 'Công việc đã kết thúc.', 409)
    planned = session.get(CleaningShift, target.shift_id) if d['target_type'] == 'CLEANING' else target
    if hasattr(planned, 'scheduled_start_at') and not (start <= planned.scheduled_start_at and planned.scheduled_end_at <= end):
        raise AppError('ERR-ROSTER-TIME', 'Ca không phủ thời gian công việc.', 409)
    if d.get('sop_id'):
        sop = record_ref(session, context, row, d['sop_id'], 'SOP', ('APPROVED',))
        if not active_on(sop, start.date()):
            raise AppError('ERR-SOP-EFFECTIVITY', 'SOP không có hiệu lực trong ca.', 409)
        trainings = session.scalars(select(OperationsRecord).where(OperationsRecord.kind == 'TRAINING', OperationsRecord.building_id == row.building_id, OperationsRecord.status.in_(('APPROVED', 'COMPLETED')))).all()
        if not any(t.data['sop_id'] == str(sop.id) and str(staff.id) in t.data.get('acknowledgements', {}) for t in trainings):
            raise AppError('ERR-SOP-UNACKNOWLEDGED', 'Nhân sự chưa xác nhận phiên bản SOP này.', 409)
    role = {'WORK_ORDER': 'technician', 'CLEANING': 'cleaning', 'SECURITY': 'security'}[d['target_type']]
    if not any(g.role == role and g.building_id == row.building_id for g in context_for_account(session, account, row.site_id).role_grants):
        raise AppError('ERR-STAFF-ROLE', 'Nhân sự không có quyền thực hiện công việc này.', 409)
    return target, staff


def apply_benefits(session, unit_id, policy_id, segments, version_by_id):
    benefits = session.scalars(select(OperationsRecord).where(OperationsRecord.kind == 'FEE_BENEFIT', OperationsRecord.status == 'APPROVED', OperationsRecord.building_id == select(Unit.building_id).where(Unit.id == unit_id).scalar_subquery())).all()
    benefits = [b for b in benefits if str(unit_id) in b.data['unit_ids'] and b.data['fee_policy_id'] == str(policy_id)]
    expanded = []
    snapshots = []
    for segment in segments:
        boundaries = {segment['starts_on'], segment['ends_on']}
        for benefit in benefits:
            for field in ('valid_from', 'valid_to'):
                when = date.fromisoformat(benefit.data[field])
                if segment['starts_on'] < when < segment['ends_on']: boundaries.add(when)
        points = sorted(boundaries)
        for start, end in zip(points, points[1:]):
            active = [b for b in benefits if b.data['valid_from'] <= start.isoformat() < b.data['valid_to']]
            if len(active) > 1:
                raise AppError('ERR-BENEFIT-OVERLAP', 'Ưu đãi chồng thời gian, cần xử lý trước tính phí.', 409)
            key = f"{segment['key']}:{start}"
            version_by_id[key] = version_by_id[segment['key']]
            quantity = Decimal(segment['quantity'])
            if active:
                benefit = active[0]
                if Decimal(benefit.data['percent']) != 100:
                    quantity *= (Decimal(100)-Decimal(benefit.data['percent']))/100
                snapshots.append({'id': str(benefit.id), 'version': benefit.version, 'data': benefit.data})
            expanded.append({**segment, 'key': key, 'starts_on': start, 'ends_on': end, 'quantity': quantity, 'amount_vnd': 0 if active and Decimal(active[0].data['percent']) == 100 else segment['amount_vnd']})
    return expanded, snapshots


def next_code(session, site_id, prefix):
    # Serialise allocation across all work-order entry points; old codes remain untouched.
    key = int.from_bytes(hashlib.sha256(f'code:{site_id}:{prefix}'.encode()).digest()[:8], 'big', signed=True)
    session.execute(select(func.pg_advisory_xact_lock(key)))
    from app.models.service import WorkOrder
    from app.models.maintenance import Asset
    model = WorkOrder if prefix.startswith('WO-') else Meter if prefix.startswith('MTR-') else Asset
    codes = session.scalars(select(model.code).where(model.site_id == site_id, model.code.like(prefix + '-%'))).all()
    sequence = max([int(c.rsplit('-', 1)[-1]) for c in codes if c.rsplit('-', 1)[-1].isdigit()] or [0]) + 1
    return f'{prefix}-{sequence:06d}'


def queue_direct_assignment(session, context, target, account_id, target_type, starts_at=None, ends_at=None):
    """All legacy assignment entry points enforce the managed roster, then await ACK."""
    start, end = starts_at or utc_now(), ends_at or utc_now()
    profiles = session.scalars(select(OperationsRecord).where(OperationsRecord.kind == 'STAFF', OperationsRecord.status == 'APPROVED',
        OperationsRecord.tenant_id == context.tenant_id, OperationsRecord.site_id == context.assert_active_site(), OperationsRecord.building_id == target.building_id).with_for_update()).all()
    profiles = [p for p in profiles if p.data['account_id'] == str(account_id)]
    if len(profiles) != 1:
        raise AppError('ERR-STAFF-PROFILE', 'Cần hồ sơ nhân sự đã duyệt trước khi phân công.', 409)
    rosters = session.scalars(select(OperationsRecord).where(OperationsRecord.kind == 'ROSTER', OperationsRecord.status.in_(('APPROVED', 'IN_PROGRESS')), OperationsRecord.building_id == target.building_id)).all()
    rosters = [r for r in rosters if r.data['staff_id'] == str(profiles[0].id) and datetime.fromisoformat(r.data['starts_at']) <= start and end <= datetime.fromisoformat(r.data['ends_at'])]
    if len(rosters) != 1:
        raise AppError('ERR-STAFF-ROSTER', 'Cần một ca đã duyệt phủ thời gian công việc; ca vắng không được phân công.', 409)
    session.flush()
    row = OperationsRecord(**scope_values(context, building_id=target.building_id), kind='WORK_ASSIGNMENT', title='Tiếp nhận ' + target_type,
        data={'target_type': target_type, 'target_id': str(target.id), 'roster_id': str(rosters[0].id), 'required_skill': rosters[0].data['required_skill'], 'sop_id': None, 'evidence_reference': 'DIRECT_ASSIGNMENT:' + str(target.id)}, status='APPROVED')
    assignment_candidate(session, context, row)
    pending = session.scalars(select(OperationsRecord).where(OperationsRecord.kind == 'WORK_ASSIGNMENT', OperationsRecord.status == 'APPROVED', OperationsRecord.building_id == target.building_id).with_for_update()).all()
    for previous in pending:
        if previous.data['target_type'] == target_type and previous.data['target_id'] == str(target.id):
            previous.status = 'CANCELLED'; previous.version += 1; event(session, context, previous, 'SUPERSEDED', 'Đã thay phân công; đầu mối điều phối vẫn chịu trách nhiệm.')
    session.add(row); event(session, context, row, 'ASSIGN_PENDING', 'Chờ nhân sự tiếp nhận.')
    row.data = {**row.data, 'target_version': target.version}
    return row


def require_work_ack(session, target, context, target_type):
    rows = session.scalars(select(OperationsRecord).where(OperationsRecord.kind == 'WORK_ASSIGNMENT', OperationsRecord.status.in_(('APPROVED', 'COMPLETED')), OperationsRecord.tenant_id == target.tenant_id, OperationsRecord.site_id == target.site_id, OperationsRecord.building_id == target.building_id).order_by(OperationsRecord.created_at)).all()
    matches = [r for r in rows if r.data['target_type'] == target_type and r.data['target_id'] == str(target.id)]
    if not matches or matches[-1].status != 'COMPLETED':
        raise AppError('ERR-WORK-ACK-REQUIRED', 'Cần tiếp nhận phân công tại Đào tạo & Nhận việc trước khi bắt đầu.', 409)
    # Recheck account role, absence, competence, certificate and SOP at execution.
    target_row, staff = assignment_candidate(session, context, matches[-1])
    if staff.data['account_id'] != str(context.account_id):
        raise scope_not_found()
    roster = session.get(OperationsRecord, as_uuid(matches[-1].data['roster_id']))
    if not datetime.fromisoformat(roster.data['starts_at']) <= utc_now() < datetime.fromisoformat(roster.data['ends_at']):
        raise AppError('ERR-ROSTER-TIME', 'Ngoài thời gian ca được phân công.', 409)
