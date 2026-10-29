"""SAD projects, commercial leases, insurance and energy with controlled effects."""
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import select
from app.core.exceptions import AppError
from app.core.policy import scope_not_found
from app.models.operational_control import OperationsRecord, TreasuryAccount, Expense, Meter, MeterReading
from app.models.sad_extensions import CommercialLedger
from app.models.property import PropertyNode
from app.models.maintenance import Asset
from app.models.resident_portal import ResidentDocument
from app.models.operations import SecurityIncident
from app.schemas import sad_extensions as s
from app.services.operational_control import load, as_uuid, state, data_model, independent, event, MANAGEMENT, FINANCIAL, TECHNICAL
from app.services.resident_portal import scope_values
from app.services.r2 import require_version, utc_now

ROLES = (*MANAGEMENT, 'accountant', 'technical_lead')
RECORDS = {
    'INSURANCE_POLICY': (s.InsurancePolicy, MANAGEMENT), 'INSURANCE_CLAIM': (s.InsuranceClaim, MANAGEMENT),
    'PROJECT': (s.Project, ROLES), 'PROJECT_CHANGE': (s.ProjectChange, ROLES),
    'PROJECT_ACCEPTANCE': (s.ProjectAcceptance, ROLES), 'PROJECT_HANDOVER': (s.ProjectHandover, ROLES),
    'PROJECT_PROGRESS': (s.ProjectProgress, ROLES), 'PROJECT_DEFECT_RESOLUTION': (s.ProjectDefectResolution, ROLES),
    'PROJECT_SETTLEMENT': (s.ProjectSettlement, ROLES),
    'COMMERCIAL_SPACE': (s.CommercialSpace, MANAGEMENT), 'COMMERCIAL_PROPOSAL': (s.CommercialProposal, ROLES),
    'COMMERCIAL_LEASE': (s.CommercialLease, ROLES), 'LEASE_AMENDMENT': (s.LeaseAmendment, ROLES),
    'COMMERCIAL_CHARGE': (s.CommercialCharge, FINANCIAL), 'COMMERCIAL_MOVEMENT': (s.CommercialMovement, FINANCIAL),
    'ENERGY_TARGET': (s.EnergyTarget, TECHNICAL), 'ENERGY_REPORT': (s.EnergyReport, TECHNICAL),
    'ENERGY_MEASURE': (s.EnergyMeasure, TECHNICAL), 'ENERGY_RESULT': (s.EnergyResult, TECHNICAL),
}


def fail(code, message):
    raise AppError(code, message, 409)


def target(session, context, row, model, identifier):
    obj = load(session, context, model, as_uuid(identifier), ROLES, lock=True)
    if obj.building_id != row.building_id:
        raise scope_not_found()
    return obj


def ref(session, context, row, identifier, kind, states=('APPROVED', 'IN_PROGRESS', 'COMPLETED')):
    obj = target(session, context, row, OperationsRecord, identifier)
    if obj.kind != kind:
        raise scope_not_found()
    state(obj, states)
    return obj


def peers(session, row, kind, field, identifier, states=('APPROVED', 'IN_PROGRESS', 'COMPLETED')):
    return [p for p in session.scalars(select(OperationsRecord).where(
        OperationsRecord.tenant_id == row.tenant_id, OperationsRecord.site_id == row.site_id,
        OperationsRecord.building_id == row.building_id, OperationsRecord.kind == kind,
        OperationsRecord.status.in_(states), OperationsRecord.id != row.id)) if p.data.get(field) == str(identifier)]


def documents(session, context, row, ids):
    for identifier in ids:
        doc = target(session, context, row, ResidentDocument, identifier)
        if not any(r in context.roles for r in MANAGEMENT) and (doc.unit_id is not None or doc.dossier_id is not None):
            raise scope_not_found()
        if doc.quarantined or doc.revoked_at or doc.verification_status != 'VERIFIED':
            fail('ERR-DOCUMENT-EVIDENCE', 'Chứng từ phải được xác minh và chưa thu hồi.')


def project_items(session, row, project):
    accepted = peers(session, row, 'PROJECT_ACCEPTANCE', 'project_id', project.id)
    updates = peers(session, row, 'PROJECT_PROGRESS', 'project_id', project.id)
    return [{'code': i['code'], 'quantity': i['quantity'],
             'accepted': str(sum((Decimal(a.data['accepted_quantity']) for a in accepted if a.data['item_code'] == i['code']), Decimal(0))),
             'progress': next((p.data for p in sorted(updates, key=lambda p:p.created_at, reverse=True) if p.data['item_code'] == i['code']), None),
             'due_on': i['due_on'], 'planned_vnd': i['planned_vnd']} for i in project.data['items']]


def agreements(lease):
    return [*lease.data.get('agreement_history', []),
            {'version': lease.data['agreement_version'], 'agreement': lease.data['agreement']}]


def lease_agreement(lease, start, end):
    matches = [v for v in agreements(lease) if v['agreement']['starts_on'] <= start < end <= v['agreement']['ends_on']]
    if len(matches) != 1:
        fail('ERR-LEASE-PERIOD', 'Kỳ phí phải nằm trong một phiên bản hợp đồng; tách kỳ khi thay phụ lục.')
    return matches[0]


def check_space_overlap(session, context, row, agreement, exclude=None):
    for lease in session.scalars(select(OperationsRecord).where(*context.scope_conditions(OperationsRecord),
            OperationsRecord.kind == 'COMMERCIAL_LEASE', OperationsRecord.status.in_(('APPROVED','IN_PROGRESS','COMPLETED')))):
        if lease.id in (row.id, exclude): continue
        for version in agreements(lease):
            a = version['agreement']; end = min(a['ends_on'], lease.data.get('closed_on', a['ends_on']))
            if a['space_id'] == agreement['space_id'] and a['starts_on'] < agreement['ends_on'] and end > agreement['starts_on']:
                fail('ERR-LEASE-OVERLAP', 'Mặt bằng đã có hợp đồng trùng thời gian.')


def close_obligations(session, lease, closes_on):
    entries = session.scalars(select(CommercialLedger).where(CommercialLedger.contract_id == lease.id)).all()
    if any(l.received_vnd < l.amount_vnd if l.kind != 'DEPOSIT' else l.received_vnd != l.released_vnd + l.deducted_vnd for l in entries):
        fail('ERR-LEASE-OBLIGATION', 'Phải xử lý hết công nợ và tiền cọc trước thu hồi/kết thúc.')
    for version in agreements(lease):
        a = version['agreement']; start, end = a['starts_on'], min(a['ends_on'], closes_on)
        for source, kind in (('rent_vnd','RENT'),('service_vnd','SERVICE')):
            if not a[source] or start >= end: continue
            cursor = start
            for l in sorted((l for l in entries if l.kind == kind and l.ends_on.isoformat() > start and l.starts_on.isoformat() < end), key=lambda l:l.starts_on):
                if l.starts_on.isoformat() > cursor: break
                cursor = max(cursor, l.ends_on.isoformat())
            if cursor < end:
                fail('ERR-LEASE-UNISSUED', 'Còn kỳ thuê/dịch vụ chưa ghi nhận nghĩa vụ đến ngày trả mặt bằng.')


def validate(session, context, row):
    if row.kind not in RECORDS:
        return
    d, kind = row.data, row.kind
    from app.services.sad_work import account_in_building
    for key in ('owner_account_id', 'handler_account_id', 'responsible_account_id', 'recipient_account_id'):
        if d.get(key):
            account_in_building(session, context, row, d[key])
    if kind == 'INSURANCE_POLICY':
        if d['deductible_vnd'] > d['limit_vnd']:
            fail('ERR-INSURANCE-LIMIT', 'Mức miễn thường vượt giới hạn bảo hiểm.')
    elif kind == 'INSURANCE_CLAIM':
        policy = ref(session, context, row, d['policy_id'], 'INSURANCE_POLICY')
        target(session, context, row, SecurityIncident, d['incident_id'])
        if not policy.data['starts_on'] <= d['occurred_on'] < policy.data['ends_on']:
            fail('ERR-INSURANCE-PERIOD', 'Ngày tổn thất nằm ngoài hiệu lực bảo hiểm.')
        documents(session, context, row, d['evidence_documents'])
    elif kind in ('PROJECT', 'PROJECT_CHANGE'):
        budget = target(session, context, row, TreasuryAccount, d['budget_id'])
        if budget.kind != 'BUDGET' or budget.status != 'ACTIVE' or not budget.starts_on.isoformat() <= d['starts_on'] < d['ends_on'] <= budget.ends_on.isoformat():
            fail('ERR-PROJECT-BUDGET', 'Dự án cần ngân sách hoạt động phủ thời gian dự kiến.')
        for item in d['items']:
            if item.get('asset_id'): target(session, context, row, Asset, item['asset_id'])
        if d.get('contract_id'): ref(session, context, row, d['contract_id'], 'CONTRACT')
        if kind == 'PROJECT_CHANGE':
            project = ref(session, context, row, d['project_id'], 'PROJECT', ('APPROVED', 'IN_PROGRESS'))
            require_version(project.version, d['expected_project_version'])
            if project.data['budget_id'] != d['budget_id']:
                fail('ERR-PROJECT-BUDGET', 'Điều chỉnh phải giữ nguồn ngân sách dự án.')
            progress = project_items(session, row, project)
            new = {i['code']: i for i in d['items']}
            if any(Decimal(i['accepted']) > 0 and (i['code'] not in new or Decimal(new[i['code']]['quantity']) < Decimal(i['accepted'])) for i in progress):
                fail('ERR-PROJECT-ACCEPTANCE', 'Điều chỉnh không được xóa hoặc giảm phần đã nghiệm thu.')
            old = {i['code']:i for i in project.data['items']}
            if any(Decimal(i['accepted']) > 0 and new[i['code']]['uom'] != old[i['code']]['uom'] for i in progress):
                fail('ERR-PROJECT-UOM', 'Hạng mục đã nghiệm thu phải giữ nguyên đơn vị đo.')
            accepted = peers(session, row, 'PROJECT_ACCEPTANCE', 'project_id', project.id)
            if sum(a.data['actual_vnd'] for a in accepted) > d['planned_vnd'] or any(sum(a.data['actual_vnd'] for a in accepted if a.data['item_code']==i['code']) > i['planned_vnd'] for i in new.values()):
                fail('ERR-PROJECT-BUDGET', 'Dự toán điều chỉnh không được thấp hơn giá trị hạng mục đã nghiệm thu.')
    elif kind.startswith('PROJECT_'):
        project = ref(session, context, row, d['project_id'], 'PROJECT', ('APPROVED', 'IN_PROGRESS'))
        if kind == 'PROJECT_ACCEPTANCE':
            item = next((i for i in project.data['items'] if i['code'] == d['item_code']), None)
            done = next((i for i in project_items(session, row, project) if i['code'] == d['item_code']), None)
            if not item or Decimal(done['accepted']) + Decimal(d['accepted_quantity']) > Decimal(item['quantity']):
                fail('ERR-PROJECT-QUANTITY', 'Nghiệm thu vượt khối lượng hoặc sai hạng mục.')
            if not project.data['starts_on'] <= d['performed_on'] <= utc_now().date().isoformat():
                fail('ERR-PROJECT-DATE', 'Ngày nghiệm thu phải sau khởi công và không ở tương lai.')
            if Decimal(d['defective_quantity']) and len(d['defect_resolution'].strip()) < 3:
                fail('ERR-PROJECT-DEFECT', 'Khối lượng lỗi cần kết luận và phương án khắc phục.')
            if Decimal(d['accepted_quantity']) + Decimal(d['defective_quantity']) > Decimal(item['quantity']):
                fail('ERR-PROJECT-QUANTITY', 'Tổng khối lượng đạt/lỗi vượt hạng mục.')
            accepted = peers(session, row, kind, 'project_id', project.id)
            if sum(a.data['actual_vnd'] for a in accepted) + d['actual_vnd'] > project.data['planned_vnd'] or sum(a.data['actual_vnd'] for a in accepted if a.data['item_code']==d['item_code']) + d['actual_vnd'] > item['planned_vnd']:
                fail('ERR-PROJECT-BUDGET', 'Giá trị nghiệm thu vượt dự toán; cần điều chỉnh được duyệt trước.')
        elif kind == 'PROJECT_PROGRESS':
            item = next((i for i in project.data['items'] if i['code']==d['item_code']), None)
            if not item or Decimal(d['actual_quantity']) > Decimal(item['quantity']) or not project.data['starts_on'] <= d['performed_on'] <= utc_now().date().isoformat():
                fail('ERR-PROJECT-PROGRESS', 'Tiến độ có hạng mục, khối lượng hoặc ngày không hợp lệ.')
        elif kind == 'PROJECT_DEFECT_RESOLUTION':
            source = ref(session, context, row, d['acceptance_id'], 'PROJECT_ACCEPTANCE')
            previous = peers(session, row, kind, 'acceptance_id', source.id)
            if source.data['project_id'] != str(project.id) or sum((Decimal(p.data['addressed_quantity']) for p in previous), Decimal(0)) + Decimal(d['addressed_quantity']) > Decimal(source.data['defective_quantity']):
                fail('ERR-PROJECT-DEFECT', 'Khắc phục vượt phần lỗi của nghiệm thu nguồn.')
        elif kind == 'PROJECT_HANDOVER':
            if any(Decimal(i['accepted']) < Decimal(i['quantity']) for i in project_items(session, row, project)):
                fail('ERR-PROJECT-INCOMPLETE', 'Còn hạng mục chưa nghiệm thu đủ.')
            for acceptance in peers(session, row, 'PROJECT_ACCEPTANCE', 'project_id', project.id):
                fixed = sum((Decimal(p.data['addressed_quantity']) for p in peers(session, row, 'PROJECT_DEFECT_RESOLUTION','acceptance_id', acceptance.id)),Decimal(0))
                if fixed < Decimal(acceptance.data['defective_quantity']):
                    fail('ERR-PROJECT-DEFECT', 'Còn lỗi chưa có hồ sơ khắc phục được nghiệm thu.')
            documents(session, context, row, d['as_built_document_ids'])
            for identifier in d['asset_ids']: target(session, context, row, Asset, identifier)
            if date.fromisoformat(d['warranty_until']) <= utc_now().date():
                fail('ERR-PROJECT-WARRANTY', 'Hạn bảo hành phải sau ngày bàn giao.')
            if peers(session, row, kind, 'project_id', project.id): fail('ERR-PROJECT-DUPLICATE', 'Dự án đã bàn giao.')
        elif kind == 'PROJECT_SETTLEMENT':
            if not peers(session, row, 'PROJECT_HANDOVER', 'project_id', project.id):
                fail('ERR-PROJECT-HANDOVER', 'Cần hồ sơ bàn giao trước quyết toán.')
            expenses = [target(session, context, row, Expense, i) for i in d['expense_ids']]
            if len(set(d['expense_ids'])) != len(expenses) or any(e.budget_id != as_uuid(project.data['budget_id']) or e.status != 'PAID' or e.procurement_id != project.id for e in expenses):
                fail('ERR-PROJECT-EXPENSE', 'Chi phí quyết toán phải được chi trả, cùng dự án và không trùng.')
            accepted = peers(session, row, 'PROJECT_ACCEPTANCE', 'project_id', project.id)
            if d['actual_vnd'] != sum(e.paid_vnd for e in expenses) or d['actual_vnd'] != sum(a.data['actual_vnd'] for a in accepted):
                fail('ERR-PROJECT-SETTLEMENT', 'Quyết toán phải bằng tổng nghiệm thu và chi phí được trả.')
    elif kind == 'COMMERCIAL_SPACE':
        node = target(session, context, row, PropertyNode, d['property_node_id'])
        if node.status != 'ACTIVE' or node.kind not in ('COMMERCIAL_SPACE','COMMON_AREA'): fail('ERR-COMMERCIAL-SPACE', 'Vị trí khai thác phải là mặt bằng/khu chung đang hoạt động.')
    elif kind in ('COMMERCIAL_PROPOSAL', 'LEASE_AMENDMENT'):
        ref(session, context, row, d['space_id'], 'COMMERCIAL_SPACE')
        if kind == 'LEASE_AMENDMENT':
            lease = ref(session, context, row, d['lease_id'], 'COMMERCIAL_LEASE', ('APPROVED', 'IN_PROGRESS'))
            require_version(lease.version, d['expected_lease_version'])
            if d['space_id'] != lease.data['agreement']['space_id']:
                fail('ERR-LEASE-SPACE', 'Phụ lục phải giữ vị trí khai thác nguồn.')
            if d['operation'] in ('AMEND','RENEW'):
                check_space_overlap(session, context, row, d, lease.id)
                a = lease.data['agreement']
                if d['operation']=='RENEW' and d['starts_on'] != a['ends_on']:
                    fail('ERR-LEASE-RENEWAL', 'Kỳ gia hạn phải nối tiếp sau kỳ hợp đồng nguồn.')
                if d['operation']=='AMEND' and not a['starts_on'] <= d['starts_on'] < a['ends_on']:
                    fail('ERR-LEASE-AMENDMENT', 'Ngày áp dụng phụ lục phải nằm trong kỳ hợp đồng hiện tại.')
            if d['operation'] in ('TERMINATE', 'REPOSSESS'):
                if not d.get('return_condition') or not lease.data['agreement']['starts_on'] < d['ends_on'] <= min(lease.data['agreement']['ends_on'],utc_now().date().isoformat()):
                    fail('ERR-LEASE-HANDOVER', 'Kết thúc cần tình trạng trả mặt bằng và ngày kết thúc thực tế hợp lệ.')
                close_obligations(session, lease, d['ends_on'])
    elif kind == 'COMMERCIAL_LEASE':
        proposal = ref(session, context, row, d['proposal_id'], 'COMMERCIAL_PROPOSAL')
        for lease in session.scalars(select(OperationsRecord).where(*context.scope_conditions(OperationsRecord), OperationsRecord.kind == kind, OperationsRecord.id != row.id, OperationsRecord.status.in_(('APPROVED', 'IN_PROGRESS')))):
            if lease.data['contract_number'] == d['contract_number']:
                fail('ERR-LEASE-NUMBER', 'Số hợp đồng đã được sử dụng.')
        check_space_overlap(session, context, row, proposal.data)
    elif kind == 'COMMERCIAL_CHARGE':
        lease = ref(session, context, row, d['lease_id'], 'COMMERCIAL_LEASE', ('APPROVED', 'IN_PROGRESS'))
        lease_agreement(lease, d['starts_on'], d['ends_on'])
        if prorated_months(date.fromisoformat(d['starts_on']),date.fromisoformat(d['ends_on'])) > {'MONTH':1,'QUARTER':3,'YEAR':12}[lease.data['rent_cycle']]:
            fail('ERR-LEASE-CYCLE', 'Kỳ phát hành vượt chu kỳ thanh toán hợp đồng.')
        for ledger in session.scalars(select(CommercialLedger).where(CommercialLedger.contract_id == lease.id, CommercialLedger.kind != 'DEPOSIT')):
            if ledger.starts_on.isoformat() < d['ends_on'] and ledger.ends_on.isoformat() > d['starts_on']:
                fail('ERR-LEASE-PERIOD', 'Kỳ tính phí chồng kỳ đã ghi nhận.')
    elif kind == 'COMMERCIAL_MOVEMENT':
        ledger = target(session, context, row, CommercialLedger, d['charge_id'])
        if d['occurred_on'] > utc_now().date().isoformat(): fail('ERR-LEASE-DATE','Chứng từ thu/hoàn không được ở tương lai.')
        if d['operation'] == 'RECEIPT' and ledger.received_vnd + d['amount_vnd'] > ledger.amount_vnd:
            fail('ERR-LEASE-AMOUNT', 'Thu vượt khoản phải thu.')
        if d['operation'] != 'RECEIPT' and (ledger.kind != 'DEPOSIT' or ledger.released_vnd + ledger.deducted_vnd + d['amount_vnd'] > ledger.received_vnd):
            fail('ERR-LEASE-DEPOSIT', 'Hoàn/khấu trừ vượt tiền cọc thực nhận.')
        if any(p.data['reference'] == d['reference'] for p in session.scalars(select(OperationsRecord).where(*context.scope_conditions(OperationsRecord), OperationsRecord.kind == kind, OperationsRecord.id != row.id, OperationsRecord.status.in_(('APPROVED', 'COMPLETED'))))):
            fail('ERR-LEASE-REFERENCE', 'Chứng từ thu/hoàn đã được ghi nhận.')
    elif kind == 'ENERGY_TARGET':
        area = target(session, context, row, PropertyNode, d['area_id'])
        if area.kind != 'COMMON_AREA' or area.status != 'ACTIVE': fail('ERR-ENERGY-AREA','Định mức cần khu chung đang hoạt động.')
        for identifier in d['meter_ids']:
            meter = target(session, context, row, Meter, identifier)
            if meter.commodity != d['commodity'] or meter.unit_id is not None:
                fail('ERR-ENERGY-METER', 'Định mức khu chung cần đồng hồ đúng đại lượng, không gắn căn cư dân.')
        meters = [target(session, context, row, Meter, i) for i in d['meter_ids']]
        if any(m.upstream_id in {n.id for n in meters} for m in meters):
            fail('ERR-ENERGY-DOUBLE-COUNT', 'Không cộng đồng hồ nguồn với nhánh của nó.')
    elif kind in ('ENERGY_REPORT', 'ENERGY_MEASURE'):
        policy = ref(session, context, row, d['target_id'], 'ENERGY_TARGET')
        if kind == 'ENERGY_REPORT' and not policy.data['starts_on'] <= d['starts_on'] < d['ends_on'] <= policy.data['ends_on']:
            fail('ERR-ENERGY-PERIOD', 'Kỳ báo cáo nằm ngoài hiệu lực định mức.')
    elif kind == 'ENERGY_RESULT':
        measure = ref(session, context, row, d['measure_id'], 'ENERGY_MEASURE')
        before = ref(session, context, row, d['baseline_report_id'], 'ENERGY_REPORT')
        after = ref(session, context, row, d['result_report_id'], 'ENERGY_REPORT')
        if before.id == after.id or before.data['ends_on'] > after.data['starts_on'] or after.data['starts_on'] != d['starts_on'] or after.data['ends_on'] != d['ends_on']:
            fail('ERR-ENERGY-COMPARISON', 'Kỳ kết quả phải khớp báo cáo và sau kỳ cơ sở.')
        if before.data['target_id'] != measure.data['target_id'] or after.data['target_id'] != measure.data['target_id'] or any(r.data['analysis']['status'] != 'COMPLETE' for r in (before, after)):
            fail('ERR-ENERGY-COMPARISON', 'So sánh cần cùng định nghĩa và đủ dữ liệu xác minh.')


def energy_analysis(session, context, row, policy):
    from app.services.meter_billing import effective_reading
    d, p = row.data, policy.data
    result, total = [], Decimal(0)
    for identifier in p['meter_ids']:
        meter = target(session, context, row, Meter, identifier)
        bounds = [session.scalar(select(MeterReading).where(MeterReading.meter_id == meter.id, MeterReading.read_on == date.fromisoformat(d[k]), MeterReading.status == 'VERIFIED')) for k in ('starts_on', 'ends_on')]
        complete = all(bounds) and meter.valid_from.isoformat() <= d['starts_on'] and (not meter.valid_to or meter.valid_to.isoformat() >= d['ends_on'])
        quantity = (effective_reading(session, bounds[1]).value - effective_reading(session, bounds[0]).value) * meter.multiplier if complete else None
        if quantity is not None and quantity < 0: complete = False; quantity = None
        result.append({'meter_id': str(meter.id), 'meter_version':meter.version, 'multiplier':str(meter.multiplier), 'source_ids': [str(b.id) if b else None for b in bounds], 'source_versions':[b.version if b else None for b in bounds], 'effective_values':[str(effective_reading(session,b).value) if b else None for b in bounds], 'quantity': str(quantity) if quantity is not None else None, 'status': 'VERIFIED' if complete else 'MISSING'})
        if quantity is not None: total += quantity
    days = (date.fromisoformat(d['ends_on']) - date.fromisoformat(d['starts_on'])).days
    target_days = (date.fromisoformat(p['ends_on']) - date.fromisoformat(p['starts_on'])).days
    quota = Decimal(p['target_quantity']) * days / target_days
    complete = all(i['status'] == 'VERIFIED' for i in result)
    return {'status': 'COMPLETE' if complete else 'INCOMPLETE', 'sources': result, 'uom': p['uom'], 'definition': p['definition'], 'policy_version': policy.version,
            'days': days, 'actual': str(total) if complete else None, 'target': str(quota),
            'difference': str(total-quota) if complete else None, 'anomaly': complete and total > quota * (1 + Decimal(p['tolerance_percent']) / 100),
            'cause_status': 'VERIFIED' if d.get('verified_cause_reference') else 'UNDETERMINED'}


def prorated_months(start, end):
    quantity = Decimal(0)
    cursor = start
    while cursor < end:
        boundary = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
        stop = min(end, boundary)
        quantity += Decimal((stop-cursor).days) / monthrange(cursor.year, cursor.month)[1]
        cursor = stop
    return quantity


def ledger(session, context, row, lease, kind, amount, start, end, due, snapshot):
    if amount:
        entry = CommercialLedger(**scope_values(context, building_id=row.building_id), contract_id=lease.id, source_record_id=row.id,
                                 kind=kind, amount_vnd=amount, starts_on=start, ends_on=end, due_on=due, snapshot=snapshot)
        session.add(entry); event(session, context, entry, 'ISSUE', row.data['evidence_reference'])


def approve(session, context, row):
    if row.kind not in RECORDS: return
    validate(session, context, row)
    d, kind = row.data, row.kind
    if kind in ('PROJECT', 'PROJECT_CHANGE'):
        budget = target(session, context, row, TreasuryAccount, d['budget_id'])
        old = 0
        project = row if kind == 'PROJECT' else ref(session, context, row, d['project_id'], 'PROJECT', ('APPROVED', 'IN_PROGRESS'))
        if kind == 'PROJECT_CHANGE': old = project.data['remaining_commitment_vnd']
        allocated = project.data['planned_vnd'] - old if kind == 'PROJECT_CHANGE' else 0
        new = d['planned_vnd'] - allocated
        if new < 0 or budget.spent_vnd + budget.reserved_vnd - old + new > budget.limit_vnd:
            fail('ERR-BUDGET-LIMIT', 'Dự toán vượt ngân sách khả dụng.')
        budget.reserved_vnd += new-old; budget.version += 1
        if kind == 'PROJECT': row.data = {**d, 'remaining_commitment_vnd': new, 'settled_vnd': 0}
        else:
            project.data = {**project.data, **{k: d[k] for k in s.Project.model_fields}, 'remaining_commitment_vnd': new}
            project.version += 1; event(session, context, project, 'PROJECT_CHANGE', d['change_reason'])
    elif kind == 'PROJECT_HANDOVER':
        for identifier in d['asset_ids']:
            asset = target(session, context, row, Asset, identifier)
            asset.warranty_until = date.fromisoformat(d['warranty_until']); asset.updated_by_id = context.account_id; asset.version += 1
            event(session, context, asset, 'PROJECT_HANDOVER', d['evidence_reference'])
    elif kind == 'PROJECT_SETTLEMENT':
        project = ref(session, context, row, d['project_id'], 'PROJECT', ('APPROVED', 'IN_PROGRESS'))
        budget = target(session, context, row, TreasuryAccount, project.data['budget_id'])
        budget.reserved_vnd -= project.data['remaining_commitment_vnd']; budget.version += 1
        project.data = {**project.data, 'remaining_commitment_vnd': 0, 'settled_vnd': d['actual_vnd'], 'settlement_id': str(row.id)}
        project.status = 'COMPLETED'; project.version += 1; event(session, context, project, 'SETTLE', d['evidence_reference'])
    elif kind == 'COMMERCIAL_LEASE':
        proposal = ref(session, context, row, d['proposal_id'], 'COMMERCIAL_PROPOSAL')
        row.data = {**d, 'agreement': proposal.data, 'agreement_version': 1}
        ledger(session, context, row, row, 'DEPOSIT', proposal.data['deposit_vnd'], date.fromisoformat(proposal.data['starts_on']), date.fromisoformat(proposal.data['ends_on']), date.fromisoformat(proposal.data['starts_on']), {'proposal_id': str(proposal.id), 'agreement': proposal.data})
    elif kind == 'LEASE_AMENDMENT':
        lease = ref(session, context, row, d['lease_id'], 'COMMERCIAL_LEASE', ('APPROVED', 'IN_PROGRESS'))
        if d['operation'] in ('TERMINATE', 'REPOSSESS'):
            lease.status = 'COMPLETED'
            lease.data = {**lease.data,'closed_on':d['ends_on'],'return_condition':d['return_condition'],'closure_record_id':str(row.id)}
        else:
            agreement = {k: d[k] for k in s.CommercialProposal.model_fields}
            # Keep obligations already issued immutable; amended prices affect future periods only.
            if any(l.ends_on.isoformat() > d['starts_on'] for l in session.scalars(select(CommercialLedger).where(CommercialLedger.contract_id == lease.id, CommercialLedger.kind != 'DEPOSIT'))):
                fail('ERR-LEASE-AMENDMENT', 'Phụ lục không được thay kỳ phí đã phát hành.')
            if d['deposit_vnd'] != lease.data['agreement']['deposit_vnd']:
                fail('ERR-LEASE-DEPOSIT', 'Giữ nguyên nghĩa vụ cọc đã phát hành; xử lý thu/hoàn bằng chứng từ riêng.')
            previous = dict(lease.data['agreement'])
            if d['operation']=='AMEND': previous['ends_on'] = d['starts_on']
            history = lease.data.get('agreement_history', [])
            if previous['starts_on'] < previous['ends_on']:
                history = [*history, {'version':lease.data['agreement_version'],'agreement':previous}]
            lease.data = {**lease.data, 'agreement': agreement, 'agreement_history':history, 'agreement_version': lease.data['agreement_version']+1}
        lease.version += 1; event(session, context, lease, d['operation'], d['evidence_reference'])
    elif kind == 'COMMERCIAL_CHARGE':
        lease = ref(session, context, row, d['lease_id'], 'COMMERCIAL_LEASE', ('APPROVED', 'IN_PROGRESS'))
        start, end, due = (date.fromisoformat(d[k]) for k in ('starts_on', 'ends_on', 'due_on'))
        months = prorated_months(start, end)
        version = lease_agreement(lease, d['starts_on'], d['ends_on'])
        for source, category in (('rent_vnd', 'RENT'), ('service_vnd', 'SERVICE')):
            amount = int((Decimal(version['agreement'][source]) * months).quantize(Decimal(1), rounding=ROUND_HALF_UP))
            ledger(session, context, row, lease, category, amount, start, end, due, {'agreement': version['agreement'], 'agreement_version': version['version'], 'contract_number': lease.data['contract_number'], 'months': str(months), 'rounding': 'HALF_UP_VND'})
    elif kind == 'COMMERCIAL_MOVEMENT':
        entry = target(session, context, row, CommercialLedger, d['charge_id'])
        field = {'RECEIPT':'received_vnd', 'REFUND':'released_vnd', 'DEDUCTION':'deducted_vnd'}[d['operation']]
        setattr(entry, field, getattr(entry, field)+d['amount_vnd'])
        entry.status = 'SETTLED' if entry.received_vnd == entry.amount_vnd and (entry.kind != 'DEPOSIT' or entry.released_vnd+entry.deducted_vnd == entry.received_vnd) else 'PARTIAL'
        entry.version += 1; event(session, context, entry, d['operation'], d['evidence_reference'])
    elif kind == 'ENERGY_REPORT':
        policy = ref(session, context, row, d['target_id'], 'ENERGY_TARGET')
        row.data = {**d, 'analysis': energy_analysis(session, context, row, policy)}
    elif kind == 'ENERGY_RESULT':
        before = ref(session, context, row, d['baseline_report_id'], 'ENERGY_REPORT').data['analysis']
        after = ref(session, context, row, d['result_report_id'], 'ENERGY_REPORT').data['analysis']
        if before['policy_version'] != after['policy_version']:
            fail('ERR-ENERGY-COMPARISON', 'Định mức đã thay phiên bản; cần kỳ so sánh cùng định nghĩa.')
        row.data = {**d, 'saving_per_day': str(Decimal(before['actual'])/before['days'] - Decimal(after['actual'])/after['days']), 'uom': after['uom'], 'baseline': before, 'result': after}


def complete(session, context, row):
    if row.kind in ('PROJECT', 'COMMERCIAL_LEASE', 'INSURANCE_CLAIM'):
        fail('ERR-DOMAIN-WORKFLOW', 'Cần quyết toán dự án, xử lý nghĩa vụ hợp đồng hoặc kết quả bảo hiểm theo luồng riêng.')


def action(session, context, row, body):
    if body.action not in ('CLAIM_SUBMIT', 'CLAIM_OUTCOME'): return False
    if row.kind != 'INSURANCE_CLAIM': fail('ERR-INSURANCE-CLAIM', 'Cần hồ sơ yêu cầu bồi thường.')
    if body.action == 'CLAIM_SUBMIT':
        state(row, ('APPROVED',)); validate(session, context, row)
        row.status = 'SENT'; row.data = {**row.data, 'submission_reference': body.reason}
    else:
        independent(context, row)
        state(row, ('SENT', 'ACCEPTED'))
        outcome = data_model(s.InsuranceOutcome, body.data).model_dump(mode='json')
        policy = ref(session, context, row, row.data['policy_id'], 'INSURANCE_POLICY')
        if outcome['decided_on'] > utc_now().date().isoformat() or outcome['amount_vnd'] > min(policy.data['limit_vnd'], row.data['loss_vnd']) or outcome['decision'] == 'REJECTED' and outcome['amount_vnd']:
            fail('ERR-INSURANCE-OUTCOME', 'Kết quả bảo hiểm có thời điểm hoặc số tiền không hợp lệ.')
        if outcome['decision'] == 'PAID' and (row.status != 'ACCEPTED' or outcome['amount_vnd'] != row.data['outcome']['amount_vnd']):
            fail('ERR-INSURANCE-PAYMENT', 'Chỉ ghi đã trả khi có quyết định chấp nhận tương ứng.')
        row.data = {**row.data, 'outcome': outcome}; row.status = outcome['decision']
    return True


def progress(session, context, row):
    if row.kind == 'PROJECT':
        return {'items': project_items(session, row, row), 'remaining_commitment_vnd': row.data.get('remaining_commitment_vnd'),
                'records': [{'id': str(p.id), 'kind': p.kind, 'status': p.status, 'data': p.data} for k in ('PROJECT_ACCEPTANCE', 'PROJECT_HANDOVER', 'PROJECT_SETTLEMENT', 'PROJECT_CHANGE', 'PROJECT_PROGRESS','PROJECT_DEFECT_RESOLUTION') for p in peers(session, row, k, 'project_id', row.id)]}
    if row.kind == 'COMMERCIAL_LEASE':
        from app.services.resident_portal import view
        entries = session.scalars(select(CommercialLedger).where(CommercialLedger.contract_id == row.id)).all()
        return {'items': [view(e) for e in entries], 'debt_vnd': sum(e.amount_vnd-e.received_vnd for e in entries if e.kind != 'DEPOSIT'), 'deposit_held_vnd': sum(e.received_vnd-e.released_vnd-e.deducted_vnd for e in entries if e.kind == 'DEPOSIT')}
    return {'items': [], 'analysis': row.data.get('analysis'), 'outcome': row.data.get('outcome')}
