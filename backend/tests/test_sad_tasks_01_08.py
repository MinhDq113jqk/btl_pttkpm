"""SAD T01–T08 tests on a disposable database and synthetic records only."""
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4
import os
import pytest
from sqlalchemy import select
from app.models.account import Account, AccountRole
from app.models.billing import FeePolicyVersion
from app.models.operational_control import OperationsRecord, StockItem, MeterAssignment
from app.models.building import Building
from app.services.sad_work import apply_benefits
from auth_test_support import mint_session_token
from test_steps2_3 import controlled_case
from test_step1_fee_proration import concurrent_case
from test_steps4_5 import create, act, record, approve, treasury
from test_portal_workflows import post, action
from app.models.service import ServiceCategory, ServiceRequest, WorkOrder
from app.models.maintenance import Asset
from app.models.resident_portal import PortalFeeSource, PortalFinancialAdjustment
from app.models.billing import BillingInvoice
from test_steps2_3 import issue, next_action

pytestmark = pytest.mark.skipif(os.getenv('GREENCITY_ISOLATED_SECURITY_TESTS') != '1', reason='Disposable PostgreSQL only')


def fee_draft(c, basis='UNIT_AREA_M2'):
    r = c['client'].post('/api/v1/billing/fee-policies', json={'building_id': str(c['building'].id), 'code': 'FEE-' + uuid4().hex[:8].upper(), 'name': 'Synthetic tariff', 'effective_from': '2026-09-01', 'unit_rate_vnd': 100, 'basis': basis, **({'commodity': 'WATER', 'uom': 'm3'} if basis == 'SERVICE_UNIT' else {})}, headers={**c['auth']['accountant'], 'Idempotency-Key': uuid4().hex})
    assert r.status_code == 201, r.text
    return r.json()


def publication(c, tariff):
    return record(c, 'FEE_PUBLICATION', {'fee_version_id': tariff['id'], 'evidence_reference': 'SYN-POLICY'})


def test_t01_building_zone_and_effective_catalog(controlled_case):
    c = controlled_case
    zone = create(c, '/property/nodes', {'kind': 'ZONE', 'code': 'ZONE-SYN', 'name': 'Synthetic zone', 'data': {}})
    body = {'kind': 'FLOOR', 'building_id': str(c['building'].id), 'code': 'FL-SYN', 'name': 'Synthetic floor', 'data': {'floor_number': 1}}
    assert post(c, '/property/nodes', body, 'cskh').status_code == 409
    approve(c, record(c, 'BUILDING_ZONE', {'zone_id': zone['id'], 'evidence_reference': 'SYN-LINK'}))
    floor = create(c, '/property/nodes', {**body, 'parent_id': zone['id']})
    assert floor['parent_id'] == zone['id']
    space = create(c, '/property/nodes', {'kind': 'COMMON_AREA', 'building_id': str(c['building'].id), 'parent_id': floor['id'], 'code': 'SYN-COMMON', 'name': 'Synthetic common space', 'data': {}})
    assert space['parent_id'] == floor['id']
    assert action(c, f"/property/nodes/{zone['id']}/actions", zone, 'DEACTIVATE').status_code == 409
    catalog = approve(c, record(c, 'MASTER_DATA', {'code': 'TEAM-SYN', 'revision': 1, 'valid_from': '2025-01-01', 'body': 'Synthetic list', 'confirmed_rule_reference': 'SYN', 'catalog': 'TEAM', 'entries': [{'code': 'TECH', 'name': 'Synthetic technical'}]}))
    response = c['client'].get('/api/v1/portal/operations/master-data', params={'building_id': str(c['building'].id), 'catalog': 'TEAM', 'as_of': '2026-09-01'}, headers=c['auth']['cskh'])
    assert response.status_code == 200 and response.json()['items'][0]['id'] == catalog['id']


def test_t02_draft_preview_stale_and_independent_publication(controlled_case):
    c = controlled_case; policy = fee_draft(c, 'SERVICE_UNIT'); tariff = policy['versions'][0]
    assert tariff['published_at'] is None and tariff['basis'] == 'SERVICE_UNIT'
    row = publication(c, tariff); path = f"/operations/records/{row['id']}/actions"
    row = act(c, path, row, 'SUBMIT')
    assert action(c, path, row, 'APPROVE', 'checker').status_code == 409
    row = act(c, path, row, 'REJECT', 'checker'); row = act(c, path, row, 'PREVIEW')
    assert row['data']['preview']['snapshot']['items'][0]['after_vnd'] is None
    edited = c['client'].post(f"/api/v1/billing/fee-policies/{policy['id']}/versions/{tariff['id']}/edit", json={'expected_version': tariff['version'], 'effective_from': tariff['effective_from'], 'basis': 'SERVICE_UNIT', 'unit_rate_vnd': 200, 'commodity': 'WATER', 'uom': 'm3'}, headers={**c['auth']['accountant'], 'Idempotency-Key': uuid4().hex})
    assert edited.status_code == 200, edited.text
    row = act(c, path, row, 'SUBMIT')
    assert action(c, path, row, 'APPROVE', 'checker').status_code == 409
    row = act(c, path, row, 'REJECT', 'checker'); row = act(c, path, row, 'PREVIEW'); row = act(c, path, row, 'SUBMIT')
    assert action(c, path, row, 'APPROVE').status_code == 403
    act(c, path, row, 'APPROVE', 'checker')
    with c['database'].get_session() as session:
        version = session.get(FeePolicyVersion, UUID(tariff['id'])); assert version.published_at is not None


def test_t02_benefit_splits_period_and_prevents_overlap(controlled_case):
    c = controlled_case; policy = fee_draft(c)
    data = {'fee_policy_id': policy['id'], 'unit_ids': [str(c['unit'].id)], 'valid_from': '2026-09-10', 'valid_to': '2026-09-20', 'percent': '50', 'evidence_reference': 'SYN-BENEFIT'}
    benefit = approve(c, record(c, 'FEE_BENEFIT', data))
    duplicate = record(c, 'FEE_BENEFIT', data); duplicate = act(c, f"/operations/records/{duplicate['id']}/actions", duplicate, 'SUBMIT')
    assert action(c, f"/operations/records/{duplicate['id']}/actions", duplicate, 'APPROVE', 'checker').status_code == 409
    with c['database'].get_session() as session:
        segment = {'key': 'rate', 'starts_on': date(2026, 9, 1), 'ends_on': date(2026, 10, 1), 'quantity': Decimal(50), 'amount_vnd': 100, 'rounding_unit_vnd': 1}
        parts, snapshots = apply_benefits(session, c['unit'].id, UUID(policy['id']), [segment], {'rate': object()})
        assert len(parts) == 3 and parts[1]['quantity'] == 25 and snapshots[0]['id'] == benefit['id']


def meter(c, point, upstream=None, unit=False):
    return create(c, '/operations/meters', {'building_id': str(c['building'].id), 'unit_id': str(c['unit'].id) if unit else None, 'code': point, 'serial': uuid4().hex, 'commodity': 'WATER', 'baseline': '100', 'valid_from': '2026-09-01', 'upstream_id': upstream})


def verified(c, meter, when, value):
    row = create(c, '/operations/readings', {'meter_id': meter['id'], 'read_on': when, 'value': str(value), 'evidence_reference': 'SYN-READ'})
    return act(c, f"/operations/readings/{row['id']}/actions", row, 'VERIFY', 'checker')


def test_t03_equal_windows_missing_boundary_and_assignment(controlled_case):
    c = controlled_case; parent = meter(c, 'Synthetic inlet'); child = meter(c, 'Synthetic branch', parent['id'], True)
    assert parent['code'].startswith('MTR-WATER-')
    verified(c, parent, '2026-09-30', 120)
    uri = f"/api/v1/portal/operations/meters/{parent['id']}/reconciliation"
    params = {'starts_on': '2026-09-01', 'ends_on': '2026-09-30'}
    missing = c['client'].get(uri, params=params, headers=c['auth']['cskh']).json()
    assert missing['difference'] is None and missing['status'] == 'INCOMPLETE'
    verified(c, child, '2026-09-30', 115)
    complete = c['client'].get(uri, params=params, headers=c['auth']['cskh']).json()
    assert Decimal(complete['difference']) == 5
    assigned = create(c, '/operations/meter-assignments', {'meter_id': child['id'], 'unit_id': str(c['unit'].id), 'point': 'Synthetic new point', 'valid_from': '2026-09-30', 'evidence_reference': 'SYN-ASSIGN'})
    with c['database'].get_session() as session:
        history = session.scalars(select(MeterAssignment).where(MeterAssignment.meter_id == UUID(child['id'])).order_by(MeterAssignment.valid_from)).all()
        assert len(history) == 2 and history[0].valid_to == date(2026, 9, 30)
    assert post(c, '/operations/meter-assignments', {'meter_id': child['id'], 'point': 'Bad retroactive', 'valid_from': '2026-09-10', 'evidence_reference': 'SYN'}, 'cskh').status_code == 409


def test_t05_allocation_and_unsettled_advance_comparison(controlled_case):
    c = controlled_case; budget = treasury(c, 1000)
    body = {'budget_id': budget['id'], 'kind': 'ADVANCE', 'amount_vnd': 100, 'reference': 'SYN-ADVANCE', 'evidence_reference': 'SYN-EXPENSE'}
    assert post(c, '/operations/expenses', body, 'accountant').status_code == 422
    expense = create(c, '/operations/expenses', {**body, 'allocation': {f"UNIT:{c['unit'].id}": 100}}, 'accountant')
    path = f"/operations/expenses/{expense['id']}/actions"
    expense = act(c, path, expense, 'SUBMIT', 'accountant'); expense = act(c, path, expense, 'APPROVE', 'checker')
    expense = act(c, path, expense, 'PAY', 'accountant', {'amount_vnd': 100, 'reference': 'SYN-CASH'})
    uri = f"/api/v1/portal/operations/treasury/{budget['id']}/comparison"
    summary = c['client'].get(uri, headers=c['auth']['accountant']).json()
    assert summary['actual_vnd'] == 0 and summary['unsettled_advance_vnd'] == 100
    approve(c, record(c, 'ADVANCE_SETTLEMENT', {'expense_id': expense['id'], 'actual_vnd': 80, 'returned_vnd': 20, 'reference': 'SYN-RETURN', 'evidence_reference': 'SYN-SETTLE'}))
    summary = c['client'].get(uri, headers=c['auth']['accountant']).json()
    assert summary['actual_vnd'] == 80 and summary['unsettled_advance_vnd'] == 0


def test_t07_typed_waste_and_completion_evidence(controlled_case):
    c = controlled_case
    data = {'category': 'Synthetic waste', 'description': 'Synthetic disposal', 'evidence_reference': 'SYN', 'due_on': '2026-10-20', 'corrective_action': 'Synthetic handover', 'waste_type': 'Recycling', 'quantity': None, 'uom': None, 'collection_point': 'Synthetic collection', 'receiving_party': 'Synthetic receiver', 'handover_reference': 'SYN-HANDOVER'}
    waste = approve(c, record(c, 'WASTE', data)); path = f"/operations/records/{waste['id']}/actions"
    assert waste['data']['quantity'] is None
    assert action(c, path, waste, 'COMPLETE').status_code == 422
    done = act(c, path, waste, 'COMPLETE', data={'result': 'Synthetic result', 'completion_evidence_reference': 'SYN-PROOF'})
    assert done['status'] == 'COMPLETED'


def test_t08_training_ack_is_personal_and_versioned(controlled_case):
    c = controlled_case
    with c['database'].get_session() as session:
        worker = Account(tenant_id=c['tenant'].id, username='worker_' + uuid4().hex, full_name='Synthetic worker', hashed_password='token-only-test-account')
        session.add(worker); session.flush(); session.add(AccountRole(account_id=worker.id, site_id=c['site'].id, building_id=c['building'].id, role='technician')); session.commit()
    c['auth']['worker'] = {'Authorization': 'Bearer ' + mint_session_token(c['database'], worker.id, c['settings'].auth_secret(), claims={'active_site_id': str(c['site'].id)})}
    catalogs = []
    for kind, code in [('TEAM', 'Technical'), ('POSITION', 'Technician'), ('TERRITORY', 'Synthetic')]:
        cat = approve(c, record(c, 'MASTER_DATA', {'code': kind + '-SYN', 'revision': 1, 'valid_from': '2025-01-01', 'body': 'Synthetic', 'confirmed_rule_reference': 'SYN', 'catalog': kind, 'entries': [{'code': code, 'name': code}]}))
        catalogs.append(cat['id'])
    staff = approve(c, record(c, 'STAFF', {'account_id': str(worker.id), 'team': 'Technical', 'position': 'Technician', 'territory': 'Synthetic', 'catalog_ids': catalogs, 'skills': ['repair']}))
    sop = approve(c, record(c, 'SOP', {'code': 'SOP-SYN', 'revision': 1, 'valid_from': '2025-01-01', 'body': 'Synthetic procedure', 'confirmed_rule_reference': 'SYN-SOP'}))
    training = approve(c, record(c, 'TRAINING', {'sop_id': sop['id'], 'staff_ids': [staff['id']], 'scheduled_at': '2026-09-01T00:00:00Z', 'evidence_reference': 'SYN-TRAINING'}))
    path = f"/operations/my-work/{training['id']}/acknowledge"
    data = {'result': 'Synthetic acknowledged', 'evidence_reference': 'SYN-ACK'}
    assert action(c, path, training, 'ACK_TRAINING', 'checker', data).status_code == 404
    assert action(c, f"/operations/records/{training['id']}/actions", training, 'COMPLETE').status_code == 409
    ack = act(c, path, training, 'ACK_TRAINING', 'worker', data)
    assert ack['data']['acknowledgements'][staff['id']]['sop_id'] == sop['id']
    done = act(c, f"/operations/records/{training['id']}/actions", ack, 'COMPLETE')
    assert done['status'] == 'COMPLETED'


def work_order(c, status='DRAFT'):
    with c['database'].get_session() as s:
        scope = dict(tenant_id=c['tenant'].id, site_id=c['site'].id, building_id=c['building'].id)
        category = ServiceCategory(**scope, code=uuid4().hex, name='Synthetic repair', sla_minutes=60)
        s.add(category); s.flush()
        request = ServiceRequest(**scope, category_id=category.id, code=uuid4().hex, title='Synthetic request', description='Synthetic repair', priority='MEDIUM', sla_started_at=datetime.now(UTC), sla_duration_minutes=60, owner_account_id=c['maker'].id, created_by_id=c['maker'].id, updated_by_id=c['maker'].id)
        s.add(request); s.flush()
        wo = WorkOrder(**scope, service_request_id=request.id, code=uuid4().hex, title='Synthetic WO', description='Synthetic repair', status=status, created_by_id=c['maker'].id, updated_by_id=c['maker'].id)
        s.add(wo); s.commit(); return wo


@pytest.mark.parametrize('corrected,delta', [('112', 200), ('108', -200)])
def test_t02_t03_api_tariff_to_invoice_and_immutable_correction(controlled_case, corrected, delta):
    c = controlled_case; policy = fee_draft(c, 'SERVICE_UNIT'); tariff = policy['versions'][0]
    row = publication(c, tariff); row = act(c, f"/operations/records/{row['id']}/actions", row, 'PREVIEW'); approve(c, row)
    m = meter(c, 'Synthetic billed point', unit=True); reading = verified(c, m, '2026-09-20', 110)
    source = create(c, f"/operations/readings/{reading['id']}/billing", {'expected_version': reading['version'], 'tariff_version_id': tariff['id']}, 'accountant')
    preview = c['client'].get(f"/api/v1/portal/fee-sources/{source['id']}/preview", params={'period_id': str(c['period'].id)}, headers=c['auth']['accountant']).json()
    response = post(c, f"/fee-sources/{source['id']}/post", {'period_id': str(c['period'].id), 'expected_version': source['version'], 'calculation_hash': preview['calculation_hash']}, 'accountant')
    assert response.status_code == 200, response.text
    result = issue(c, response.json()); invoice_id = result['issued_invoice_ids'][0]
    correction = approve(c, record(c, 'METER_CORRECTION', {'reading_id': reading['id'], 'corrected_value': corrected, 'evidence_reference': 'SYN-CORRECT'}))
    with c['database'].get_session() as s:
        from app.models.operational_control import MeterReading
        assert s.get(MeterReading, UUID(reading['id'])).value == Decimal(110)
        assert s.get(BillingInvoice, UUID(invoice_id)).total_vnd == 1000
        assert s.get(PortalFeeSource, UUID(source['id'])).amount_vnd == 1000
        if delta > 0:
            additional = s.get(PortalFeeSource, UUID(correction['data']['additional_fee_source_ids'][0])); assert additional.amount_vnd == delta and additional.status == 'ACTIVE'
        else:
            credit = s.get(PortalFinancialAdjustment, UUID(correction['data']['credit_adjustment_ids'][0])); assert credit.amount_vnd == -delta and credit.status == 'REQUESTED'
    # Subsequent readings use the approved logical boundary, without rewriting the issued source.
    later = verified(c, m, '2026-09-30', 120)
    assert Decimal(later['consumption']) == 120 - Decimal(corrected)


def test_t04_asset_code_snapshot_disposal_and_no_new_plan(controlled_case):
    c = controlled_case
    with c['database'].get_session() as s:
        s.add(AccountRole(account_id=c['maker'].id, site_id=c['site'].id, building_id=c['building'].id, role='technical_lead')); s.commit()
    response = c['client'].post('/api/v1/assets', json={'building_id': str(c['building'].id), 'code': 'PUMP', 'name': 'Synthetic pump'}, headers={**c['auth']['cskh'], 'Idempotency-Key': uuid4().hex})
    assert response.status_code == 201, response.text
    asset = response.json(); assert asset['code'].startswith('AST-PUMP-')
    with c['database'].get_session() as s:
        a = s.get(Asset, UUID(asset['id'])); a.location = 'Synthetic location A'; s.commit()
    wo = work_order(c)
    approve(c, record(c, 'ASSET_WORK_LINK', {'asset_id': asset['id'], 'work_order_id': str(wo.id), 'warranty_decision': 'MANAGEMENT', 'inspection_reference': 'SYN-INSPECTION', 'evidence_reference': 'SYN-LINK'}))
    detail = c['client'].get(f'/api/v1/work-orders/{wo.id}', headers=c['auth']['cskh'])
    assert detail.status_code == 200, detail.text
    assert detail.json()['asset_id'] == asset['id'] and detail.json()['asset_snapshot']['location'] == 'Synthetic location A'
    data = {'asset_id': asset['id'], 'operation': 'DISPOSE', 'location': 'Synthetic A', 'due_on': '2026-10-11', 'evidence_reference': 'SYN-DISPOSE', 'description': 'Synthetic disposal decision'}
    disposal = approve(c, record(c, 'ASSET_CHANGE', data)); path = f"/operations/records/{disposal['id']}/actions"
    assert action(c, path, disposal, 'COMPLETE').status_code == 409
    with c['database'].get_session() as s:
        target = s.get(WorkOrder, wo.id); target.status = 'CLOSED'; s.commit()
    act(c, path, disposal, 'COMPLETE')
    with c['database'].get_session() as s:
        assert s.get(Asset, UUID(asset['id'])).status == 'DISPOSED'
        assert s.get(WorkOrder, wo.id).asset_snapshot['location'] == 'Synthetic location A'
    payload = {'building_id': str(c['building'].id), 'kind': 'ASSET_WORK_LINK', 'title': 'Synthetic link', 'data': {'asset_id': asset['id'], 'work_order_id': str(work_order(c).id), 'warranty_decision': 'MANAGEMENT', 'inspection_reference': 'SYN-INSPECTION', 'evidence_reference': 'SYN-LINK'}}
    assert post(c, '/operations/records', payload, 'cskh').status_code == 409


def test_t06_partial_acceptance_ap_and_damaged_stock_return(controlled_case):
    c = controlled_case; budget = treasury(c)
    vendor = approve(c, record(c, 'VENDOR', {'code': uuid4().hex, 'tax_code': 'SYN-TAX', 'capabilities': 'Synthetic supplier', 'contact': 'Synthetic contact'}))
    item = create(c, '/operations/stock', {'building_id': str(c['building'].id), 'code': uuid4().hex, 'name': 'Synthetic tool', 'uom': 'piece', 'warehouse': 'SYN', 'location': 'SYN', 'lot': 'SYN', 'unit_cost_vnd': 10})
    order = record(c, 'PURCHASE', {'budget_id': budget['id'], 'specification': 'Synthetic items', 'quantity': '10', 'uom': 'piece', 'estimated_vnd': 100, 'item_id': item['id']})
    quote = approve(c, record(c, 'QUOTATION', {'vendor_id': vendor['id'], 'quantity': '10', 'amount_vnd': 100, 'specification': 'Synthetic items', 'evidence_reference': 'SYN'}, order['id']))
    order = act(c, f"/operations/records/{order['id']}/actions", order, 'SELECT_QUOTE', data={'quotation_id': quote['id']}); order = approve(c, order)
    contract = approve(c, record(c, 'CONTRACT', {'vendor_id': vendor['id'], 'purchase_id': order['id'], 'reference': 'SYN-CONTRACT', 'starts_on': '2026-01-01', 'ends_on': '2026-12-31', 'amount_vnd': 100, 'milestones': 'Synthetic obligations', 'milestone_items': [{'code': 'M1', 'due_on': '2026-10-20', 'obligation': 'Synthetic acceptance', 'amount_vnd': 100}], 'allows_partial_payment': True, 'partial_payment_reference': 'SYN-PARTIAL'}))
    delivery = approve(c, record(c, 'DELIVERY', {'quantity': '6', 'accepted_quantity': '5', 'rejected_quantity': '1', 'missing_quantity': '4', 'responsible_account_id': str(c['maker'].id), 'reference': 'SYN-DELIVERY', 'evidence_reference': 'SYN', 'defects': 'Synthetic defect'}, order['id']))
    delivery = act(c, f"/operations/records/{delivery['id']}/actions", delivery, 'COMPLETE', 'checker', {'defect_resolution': 'Synthetic rejection and remediation decision'})
    ap = {'budget_id': budget['id'], 'procurement_id': order['id'], 'kind': 'AP', 'amount_vnd': 51, 'reference': 'SYN-AP', 'evidence_reference': 'SYN', 'allocation': {f"BUILDING:{c['building'].id}": 51}}
    assert post(c, '/operations/expenses', ap, 'accountant').status_code == 409
    ap['amount_vnd'] = 50; ap['allocation'] = {f"BUILDING:{c['building'].id}": 50}; create(c, '/operations/expenses', ap, 'accountant')
    progress = c['client'].get(f"/api/v1/portal/operations/records/{contract['id']}/contract-progress", headers=c['auth']['accountant'])
    assert progress.status_code == 200, progress.text
    assert progress.json()['milestones'][0]['status'] == 'PENDING' and progress.json()['financial']['payable_vnd'] == 50
    base = {'item_id': item['id'], 'quantity': '5', 'expected_version': 1, 'reference': 'SYN', 'evidence_reference': 'SYN', 'sender_account_id': str(c['maker'].id), 'recipient_account_id': str(c['checker'].id)}
    create(c, '/operations/stock-movements', {**base, 'kind': 'RECEIVE', 'delivery_id': delivery['id']})
    assert post(c, '/operations/stock-movements', {**base, 'kind': 'RECEIVE', 'delivery_id': delivery['id'], 'expected_version': 2}, 'cskh').status_code == 409
    wo = work_order(c, 'ASSIGNED'); issued = create(c, '/operations/stock-movements', {**base, 'kind': 'ISSUE', 'work_order_id': str(wo.id), 'expected_version': 2})
    returned = {**base, 'kind': 'RETURN', 'related_id': issued['id'], 'expected_version': 3, 'quantity': '2', 'condition': 'DAMAGED'}
    assert post(c, '/operations/stock-movements', returned, 'cskh').status_code == 409
    returned.update(sender_account_id=str(c['checker'].id), recipient_account_id=str(c['maker'].id)); create(c, '/operations/stock-movements', returned)
    with c['database'].get_session() as s:
        stored = s.get(StockItem, UUID(item['id'])); assert stored.quantity == 0 and stored.damaged_quantity == 2
    revision = approve(c, record(c, 'CONTRACT_REVISION', {'contract_id': contract['id'], 'operation': 'TERMINATE', 'reference': 'SYN-END', 'starts_on': '2026-01-01', 'ends_on': '2026-12-31', 'amount_vnd': 100, 'milestones': 'Synthetic open obligations', 'evidence_reference': 'SYN-END'}))
    with c['database'].get_session() as s:
        closed = s.get(OperationsRecord, UUID(contract['id'])); assert closed.data['closing_decision']['remaining_milestones'][0]['code'] == 'M1'


def test_t07_custody_discrepancy_needs_resolution(controlled_case):
    c = controlled_case
    row = approve(c, record(c, 'KEY_CUSTODY', {'reference': 'SYN-KEY', 'location': 'Synthetic A', 'custodian_account_id': str(c['maker'].id), 'due_on': '2026-10-20', 'condition': 'GOOD', 'evidence_reference': 'SYN'}))
    data = {'recipient_name': 'Synthetic receiver', 'recipient_verification_reference': 'SYN-VERIFY', 'condition': 'DAMAGED'}
    path = f"/operations/records/{row['id']}/actions"
    assert action(c, path, row, 'RETURN', data=data).status_code == 422
    data.update(discrepancy_reference='SYN-DAMAGE', resolution_reference='SYN-DECISION')
    done = act(c, path, row, 'RETURN', data=data); assert done['data']['handover']['resolution_reference'] == 'SYN-DECISION'


def staff_profile(c, role='technician'):
    with c['database'].get_session() as s:
        s.add(AccountRole(account_id=c['maker'].id, site_id=c['site'].id, building_id=c['building'].id, role='technical_lead'))
        worker = Account(tenant_id=c['tenant'].id, username='worker_' + uuid4().hex, full_name='Synthetic worker', hashed_password='token-only-test-account')
        s.add(worker); s.flush(); s.add(AccountRole(account_id=worker.id, site_id=c['site'].id, building_id=c['building'].id, role=role)); s.commit()
    c['auth']['worker'] = {'Authorization': 'Bearer ' + mint_session_token(c['database'], worker.id, c['settings'].auth_secret(), claims={'active_site_id': str(c['site'].id)})}
    catalogs = []
    for kind, code in [('TEAM', 'SyntheticTeam'), ('POSITION', 'SyntheticPosition'), ('TERRITORY', 'SyntheticTerritory')]:
        catalogs.append(approve(c, record(c, 'MASTER_DATA', {'code': kind + '-' + uuid4().hex, 'revision': 1, 'valid_from': '2025-01-01', 'body': 'Synthetic', 'confirmed_rule_reference': 'SYN', 'catalog': kind, 'entries': [{'code': code, 'name': code}]}))['id'])
    staff = approve(c, record(c, 'STAFF', {'account_id': str(worker.id), 'team': 'SyntheticTeam', 'position': 'SyntheticPosition', 'territory': 'SyntheticTerritory', 'catalog_ids': catalogs, 'skills': ['repair']}))
    now = datetime.now(UTC)
    roster = approve(c, record(c, 'ROSTER', {'staff_id': staff['id'], 'starts_at': (now-timedelta(hours=1)).isoformat(), 'ends_at': (now+timedelta(hours=1)).isoformat(), 'required_skill': 'repair', 'task': 'Synthetic task'}))
    return worker, staff, roster


def test_t08_direct_assignment_waits_for_personal_acceptance_and_absence_blocks_start(controlled_case):
    c = controlled_case; worker, staff, roster = staff_profile(c); wo = work_order(c)
    path = f"/api/v1/work-orders/{wo.id}"
    response = c['client'].post(path + '/assign', json={'assignee_id': str(worker.id), 'expected_version': wo.version}, headers=c['auth']['cskh'])
    assert response.status_code == 200, response.text
    assert response.json()['assigned_to_id'] is None
    own = c['client'].get('/api/v1/portal/operations/my-work', headers=c['auth']['worker']); assert own.status_code == 200
    assignment = next(row for row in own.json()['items'] if row['kind'] == 'WORK_ASSIGNMENT')
    assert action(c, f"/operations/my-work/{assignment['id']}/acknowledge", assignment, 'ACCEPT_WORK', 'checker', {'result': 'Synthetic accept', 'evidence_reference': 'SYN'}).status_code == 404
    act(c, f"/operations/my-work/{assignment['id']}/acknowledge", assignment, 'ACCEPT_WORK', 'worker', {'result': 'Synthetic accept', 'evidence_reference': 'SYN'})
    with c['database'].get_session() as s:
        target = s.get(WorkOrder, wo.id); assert target.status == 'ASSIGNED' and target.assigned_to_id == worker.id; version = target.version
    act(c, f"/operations/records/{roster['id']}/actions", roster, 'ABSENCE')
    blocked = c['client'].post(path + '/start', json={'expected_version': version}, headers=c['auth']['worker'])
    assert blocked.status_code == 409, blocked.text


def test_t08_security_acceptance_preserves_planned_state_and_start_uses_ack(controlled_case):
    from app.models.operations import SecurityShift
    c = controlled_case; worker, staff, roster = staff_profile(c, 'security'); now = datetime.now(UTC)
    with c['database'].get_session() as s:
        shift = SecurityShift(tenant_id=c['tenant'].id, site_id=c['site'].id, building_id=c['building'].id, scheduled_start_at=now, scheduled_end_at=now+timedelta(minutes=10), status='PLANNED', created_by_id=c['maker'].id, updated_by_id=c['maker'].id)
        s.add(shift); s.commit()
    assignment = approve(c, record(c, 'WORK_ASSIGNMENT', {'target_type': 'SECURITY', 'target_id': str(shift.id), 'roster_id': roster['id'], 'required_skill': 'repair', 'evidence_reference': 'SYN'}))
    candidates = c['client'].get('/api/v1/portal/operations/eligible-workers', params={'building_id': str(c['building'].id), 'target_type': 'SECURITY', 'target_id': str(shift.id), 'required_skill': 'repair'}, headers=c['auth']['cskh'])
    assert candidates.status_code == 200 and candidates.json()['items'][0]['eligible'] is True
    act(c, f"/operations/my-work/{assignment['id']}/acknowledge", assignment, 'ACCEPT_WORK', 'worker', {'result': 'Synthetic accept', 'evidence_reference': 'SYN'})
    with c['database'].get_session() as s:
        target = s.get(SecurityShift, shift.id); assert target.status == 'PLANNED'; version = target.version
    start = c['client'].post(f"/api/v1/security/shifts/{shift.id}/start", json={'expected_version': version}, headers=c['auth']['worker'])
    assert start.status_code == 200, start.text


def test_t01_building_workflow_keeps_code_and_rejects_child_of_inactive_building(controlled_case):
    c = controlled_case; zone = create(c, '/property/nodes', {'kind': 'ZONE', 'code': 'SYN-ZONE', 'name': 'Synthetic zone', 'data': {}})
    profile = {'operation': 'CREATE', 'code': 'SYN-B2', 'name': 'Synthetic B2', 'floors_count': 3, 'zone_id': zone['id'], 'evidence_reference': 'SYN'}
    created = approve(c, record(c, 'BUILDING_PROFILE', profile)); bid = created['data']['created_building_id']
    row = create(c, '/operations/records', {'building_id': bid, 'kind': 'BUILDING_PROFILE', 'title': 'Synthetic deactivate', 'data': {**profile, 'operation': 'DEACTIVATE'}}); approve(c, row)
    payload = {'kind': 'FLOOR', 'building_id': bid, 'parent_id': zone['id'], 'code': 'SYN-FL2', 'name': 'Synthetic floor', 'data': {'floor_number': 1}}
    assert post(c, '/property/nodes', payload, 'cskh').status_code == 409
    duplicate = record(c, 'BUILDING_PROFILE', profile); duplicate = act(c, f"/operations/records/{duplicate['id']}/actions", duplicate, 'SUBMIT')
    assert action(c, f"/operations/records/{duplicate['id']}/actions", duplicate, 'APPROVE', 'checker').status_code == 409


def test_t03_segment_reconciliation_and_database_history_guard(controlled_case):
    from sqlalchemy.exc import DBAPIError
    c = controlled_case; inlet = meter(c, 'Synthetic inlet'); branch = meter(c, 'Synthetic branch', inlet['id'], True)
    verified(c, inlet, '2026-09-30', 130); verified(c, branch, '2026-09-15', 110)
    create(c, '/operations/meter-assignments', {'meter_id': branch['id'], 'unit_id': str(c['unit'].id), 'point': 'Synthetic changed point', 'valid_from': '2026-09-15', 'evidence_reference': 'SYN'})
    verified(c, branch, '2026-09-30', 125)
    result = c['client'].get(f"/api/v1/portal/operations/meters/{inlet['id']}/reconciliation", params={'starts_on': '2026-09-01', 'ends_on': '2026-09-30'}, headers=c['auth']['cskh'])
    assert result.status_code == 200 and Decimal(result.json()['difference']) == 5
    assert len(result.json()['downstream'][0]['segments']) == 2
    with c['database'].get_session() as s:
        scope = dict(tenant_id=c['tenant'].id, site_id=c['site'].id, building_id=c['building'].id, account_id=c['maker'].id)
        with pytest.raises(DBAPIError), s.begin_nested():
            s.add(MeterAssignment(**scope, meter_id=UUID(branch['id']), point='Overlap', valid_from=date(2026, 9, 10), evidence_reference='SYN')); s.flush()


def test_t07_inspection_requires_each_remediation_result_and_hazard_requires_safety_link(controlled_case):
    c = controlled_case
    base = {'category': 'Synthetic safety', 'description': 'Synthetic inspection', 'evidence_reference': 'SYN', 'due_on': '2026-10-20', 'corrective_action': 'Synthetic remediation'}
    row = approve(c, record(c, 'INSPECTION', {**base, 'performed_at': datetime.now(UTC).isoformat(), 'findings': [{'description': 'Synthetic finding', 'owner_account_id': str(c['maker'].id), 'due_on': '2026-10-20'}]}))
    proof = {'result': 'Synthetic completed', 'completion_evidence_reference': 'SYN'}
    assert action(c, f"/operations/records/{row['id']}/actions", row, 'COMPLETE', data=proof).status_code == 422
    act(c, f"/operations/records/{row['id']}/actions", row, 'COMPLETE', data={**proof, 'finding_results': ['Synthetic repaired and evidenced']})
    payload = {'building_id': str(c['building'].id), 'kind': 'ENV_INCIDENT', 'title': 'Synthetic hazard', 'data': {**base, 'areas': ['Synthetic area'], 'hazardous': True, 'owner_account_id': str(c['maker'].id), 'notification_reference': 'SYN'}}
    assert post(c, '/operations/records', payload, 'cskh').status_code == 422


def test_t01_catalog_versions_reject_overlap_and_reused_inactive_code(controlled_case):
    c = controlled_case
    base = {'code': 'SYN-CATALOG', 'revision': 1, 'valid_from': '2025-01-01', 'valid_to': '2026-11-01', 'body': 'Synthetic version', 'confirmed_rule_reference': 'SYN', 'catalog': 'TEAM', 'entries': [{'code': 'SYN-OLD', 'name': 'Synthetic inactive team', 'active': False}]}
    approve(c, record(c, 'MASTER_DATA', base))
    overlap = record(c, 'MASTER_DATA', {**base, 'revision': 2})
    overlap = act(c, f"/operations/records/{overlap['id']}/actions", overlap, 'SUBMIT')
    assert action(c, f"/operations/records/{overlap['id']}/actions", overlap, 'APPROVE', 'checker').json()['error']['code'] == 'ERR-CATALOG-OVERLAP'
    reused = record(c, 'MASTER_DATA', {**base, 'revision': 2, 'valid_from': '2026-11-01', 'valid_to': None, 'entries': [{'code': 'SYN-OLD', 'name': 'Synthetic new team', 'active': True}]})
    reused = act(c, f"/operations/records/{reused['id']}/actions", reused, 'SUBMIT')
    assert action(c, f"/operations/records/{reused['id']}/actions", reused, 'APPROVE', 'checker').json()['error']['code'] == 'ERR-CATALOG-IDENTITY'


def test_t06_approved_conversion_and_tool_custody_trace_issue_recipient(controlled_case):
    c = controlled_case
    item = create(c, '/operations/stock', {'building_id': str(c['building'].id), 'code': uuid4().hex, 'name': 'Synthetic tool', 'uom': 'piece', 'warehouse': 'SYN', 'location': 'SYN', 'lot': 'SYN', 'unit_cost_vnd': 10})
    conversion = approve(c, record(c, 'UOM_CONVERSION', {'item_id': item['id'], 'from_uom': 'box', 'factor': '10', 'valid_from': '2025-01-01', 'evidence_reference': 'SYN'}))
    base = {'item_id': item['id'], 'reference': 'SYN', 'evidence_reference': 'SYN', 'sender_account_id': str(c['maker'].id), 'recipient_account_id': str(c['checker'].id)}
    received = create(c, '/operations/stock-movements', {**base, 'kind': 'RECEIVE', 'quantity': '2', 'expected_version': 1, 'input_uom': 'box', 'conversion_id': conversion['id']})
    assert Decimal(received['quantity']) == 20 and received['custody']['conversion_snapshot']['factor'] == '10'
    wo = work_order(c, 'ASSIGNED')
    issued = create(c, '/operations/stock-movements', {**base, 'kind': 'ISSUE', 'quantity': '3', 'work_order_id': str(wo.id), 'expected_version': 2})
    custody = {'source_movement_id': issued['id'], 'reference': 'SYN-TOOL', 'location': 'Synthetic tool location', 'custodian_account_id': str(c['maker'].id), 'due_on': '2026-11-01', 'condition': 'GOOD', 'evidence_reference': 'SYN'}
    assert post(c, '/operations/records', {'building_id': str(c['building'].id), 'kind': 'TOOL_CUSTODY', 'title': 'Synthetic custody', 'data': custody}, 'cskh').status_code == 409
    custody['custodian_account_id'] = str(c['checker'].id)
    approved = approve(c, record(c, 'TOOL_CUSTODY', custody))
    moved = act(c, f"/operations/records/{approved['id']}/actions", approved, 'MOVE_CUSTODY', data={'custodian_account_id': str(c['maker'].id), 'location': 'Synthetic storage', 'condition': 'GOOD', 'recipient_verification_reference': 'SYN-VERIFY', 'evidence_reference': 'SYN-HANDOVER'})
    assert moved['data']['chain'][-1]['from']['custodian_account_id'] == str(c['checker'].id)
    assert moved['data']['chain'][-1]['to']['custodian_account_id'] == str(c['maker'].id)
