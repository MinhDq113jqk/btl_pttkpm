"""Synthetic API/DB tests only. No browser, provider or project database."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4
import hashlib
import os
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from app.models.account import AccountRole
from app.models.operational_control import StockItem, MeterReading, TreasuryAccount, AccountInvitation
from app.models.service import WorkOrder, ServiceRequest, ServiceCategory
from test_steps2_3 import controlled_case
from test_step1_fee_proration import concurrent_case
from test_portal_workflows import post, action, resource

pytestmark = pytest.mark.skipif(os.getenv('GREENCITY_ISOLATED_SECURITY_TESTS') != '1', reason='Disposable PostgreSQL required')


def create(c, path, data, actor='cskh'):
    if path == '/operations/expenses' and 'allocation' not in data:
        data = {**data, 'allocation': {f"BUILDING:{c['building'].id}": data['amount_vnd']}}
    r = post(c, path, data, actor); assert r.status_code == 201, r.text; return r.json()


def act(c, path, row, verb, actor='cskh', data=None):
    r = action(c, path, row, verb, actor, data); assert r.status_code == 200, r.text; return r.json()


def record(c, kind, data, related=None, unit=False):
    return create(c, '/operations/records', {'building_id': str(c['building'].id), 'unit_id': str(c['unit'].id) if unit else None, 'kind': kind, 'title': 'Synthetic ' + kind, 'data': data, 'related_id': related})


def approve(c, row):
    path = '/operations/records/' + row['id'] + '/actions'
    row = act(c, path, row, 'SUBMIT'); return act(c, path, row, 'APPROVE', 'checker')


def treasury(c, limit=1000, kind='BUDGET'):
    row = create(c, '/operations/treasury', {'building_id': str(c['building'].id), 'kind': kind, 'code': uuid4().hex, 'purpose': 'Synthetic budget', 'starts_on': '2025-01-01', 'ends_on': '2027-12-31', 'limit_vnd': limit}, 'accountant')
    path = '/operations/treasury/' + row['id'] + '/actions'
    row = act(c, path, row, 'SUBMIT', 'accountant'); return act(c, path, row, 'APPROVE', 'checker')


def test_meter_verification_replacement_and_correction_preserve_continuity(controlled_case):
    c = controlled_case
    meter = create(c, '/operations/meters', {'building_id': str(c['building'].id), 'unit_id': str(c['unit'].id), 'code': uuid4().hex, 'serial': 'SYN-OLD', 'commodity': 'WATER', 'baseline': '100', 'valid_from': '2026-09-01'})
    reading = create(c, '/operations/readings', {'meter_id': meter['id'], 'read_on': '2026-09-10', 'value': '110', 'evidence_reference': 'SYN-READ'})
    assert action(c, f"/operations/readings/{reading['id']}/actions", reading, 'VERIFY').status_code == 403
    reading = act(c, f"/operations/readings/{reading['id']}/actions", reading, 'VERIFY', 'checker')
    replacement = approve(c, record(c, 'METER_REPLACEMENT', {'meter_id': meter['id'], 'changed_on': '2026-09-15', 'final_value': '115', 'new_code': uuid4().hex, 'new_serial': 'SYN-NEW', 'new_baseline': '7', 'evidence_reference': 'SYN-SWAP'}))
    newer = create(c, '/operations/readings', {'meter_id': replacement['data']['new_meter_id'], 'read_on': '2026-09-20', 'value': '12', 'evidence_reference': 'SYN-NEW-READ'})
    act(c, f"/operations/readings/{newer['id']}/actions", newer, 'VERIFY', 'checker')
    with c['database'].get_session() as s:
        values = s.scalars(select(MeterReading).where(MeterReading.building_id == c['building'].id)).all()
        assert sum(r.consumption for r in values) == Decimal(20)
    approve(c, record(c, 'METER_CORRECTION', {'reading_id': reading['id'], 'corrected_value': '112', 'evidence_reference': 'SYN-CORRECT'}))
    with c['database'].get_session() as s:
        values = s.scalars(select(MeterReading).where(MeterReading.building_id == c['building'].id)).all()
        assert sum(r.consumption for r in values) == Decimal(20)


def test_stock_reservation_return_and_no_duplicate_issue(controlled_case):
    c = controlled_case
    with c['database'].get_session() as s:
        category = ServiceCategory(tenant_id=c['tenant'].id, site_id=c['site'].id, building_id=c['building'].id, code=uuid4().hex, name='Synthetic technical', sla_minutes=60)
        s.add(category); s.flush()
        request = ServiceRequest(tenant_id=c['tenant'].id, site_id=c['site'].id, building_id=c['building'].id, category_id=category.id, code=uuid4().hex, title='Synthetic request', description='Synthetic work', priority='MEDIUM', sla_started_at=datetime.now(UTC), sla_duration_minutes=60, owner_account_id=c['maker'].id, created_by_id=c['maker'].id, updated_by_id=c['maker'].id)
        s.add(request); s.flush()
        wo = WorkOrder(tenant_id=c['tenant'].id, site_id=c['site'].id, building_id=c['building'].id, service_request_id=request.id, code=uuid4().hex, title='Synthetic WO', description='Synthetic work', status='ASSIGNED', created_by_id=c['maker'].id, updated_by_id=c['maker'].id)
        s.add(wo); s.commit()
    item = create(c, '/operations/stock', {'building_id': str(c['building'].id), 'code': uuid4().hex, 'name': 'Synthetic item', 'uom': 'piece', 'warehouse': 'SYN', 'location': 'A', 'lot': 'LOT', 'unit_cost_vnd': 10})
    def move(kind, quantity, version, **kwargs):
        sender, recipient = (c['checker'], c['maker']) if kind == 'RETURN' else (c['maker'], c['checker'])
        return post(c, '/operations/stock-movements', {'item_id': item['id'], 'kind': kind, 'quantity': str(quantity), 'expected_version': version, 'reference': uuid4().hex, 'evidence_reference': 'SYN-STOCK', 'sender_account_id': str(sender.id), 'recipient_account_id': str(recipient.id), **kwargs}, 'cskh')
    assert move('RECEIVE', 10, 1).status_code == 201
    reserved = move('RESERVE', 7, 2, work_order_id=str(wo.id)); assert reserved.status_code == 201, reserved.text
    assert move('ISSUE', 4, 3, work_order_id=str(wo.id)).status_code == 409
    issued = move('ISSUE', 7, 3, work_order_id=str(wo.id), related_id=reserved.json()['id']); assert issued.status_code == 201, issued.text
    assert move('RETURN', 8, 4, related_id=issued.json()['id']).status_code == 409
    assert move('RETURN', 2, 4, related_id=issued.json()['id']).status_code == 201
    with c['database'].get_session() as s:
        row = s.get(StockItem, UUID(item['id'])); assert row.quantity == 5 and row.reserved == 0
        with pytest.raises(DBAPIError), s.begin_nested():
            s.execute(text('UPDATE greencity.operational_stock_movements SET quantity=99 WHERE id=:id'), {'id': issued.json()['id']})


def test_budget_competing_approvals_and_fund_payment(controlled_case):
    c = controlled_case; budget = treasury(c, 100); fund = treasury(c, kind='FUND')
    fund = act(c, f"/operations/treasury/{fund['id']}/actions", fund, 'RECEIPT', 'accountant', {'amount_vnd': 100, 'reference': uuid4().hex, 'evidence_reference': 'SYN-RECEIPT'})
    rows = []
    for _ in range(2):
        row = create(c, '/operations/expenses', {'budget_id': budget['id'], 'fund_id': fund['id'], 'kind': 'EXPENSE', 'amount_vnd': 70, 'reference': uuid4().hex, 'evidence_reference': 'SYN-EXPENSE'}, 'accountant')
        rows.append(act(c, f"/operations/expenses/{row['id']}/actions", row, 'SUBMIT', 'accountant'))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda row: action(c, f"/operations/expenses/{row['id']}/actions", row, 'APPROVE', 'checker'), rows))
    assert sorted(r.status_code for r in results) == [200, 409]
    approved = next(r.json() for r in results if r.status_code == 200)
    paid = act(c, f"/operations/expenses/{approved['id']}/actions", approved, 'PAY', 'accountant', {'amount_vnd': 70, 'reference': uuid4().hex})
    assert paid['paid_vnd'] == 70
    with c['database'].get_session() as s:
        assert s.get(TreasuryAccount, UUID(fund['id'])).balance_vnd == 30


def test_procurement_three_way_match_and_independent_acceptance(controlled_case):
    c = controlled_case; budget = treasury(c)
    vendor = approve(c, record(c, 'VENDOR', {'code': uuid4().hex, 'tax_code': 'SYN-TAX', 'capabilities': 'Synthetic capability', 'contact': 'Synthetic contact'}))
    order = record(c, 'PURCHASE', {'budget_id': budget['id'], 'specification': 'Synthetic supplies', 'quantity': '2', 'uom': 'piece', 'estimated_vnd': 100})
    quote = approve(c, record(c, 'QUOTATION', {'vendor_id': vendor['id'], 'amount_vnd': 90, 'quantity': '2', 'specification': 'Synthetic supplies', 'evidence_reference': 'SYN-QUOTE'}, order['id']))
    order = act(c, f"/operations/records/{order['id']}/actions", order, 'SELECT_QUOTE', data={'quotation_id': quote['id']})
    order = approve(c, order)
    payload = {'budget_id': budget['id'], 'procurement_id': order['id'], 'kind': 'AP', 'amount_vnd': 90, 'reference': uuid4().hex, 'evidence_reference': 'SYN-INVOICE'}
    assert post(c, '/operations/expenses', payload, 'accountant').status_code == 409
    delivery = approve(c, record(c, 'DELIVERY', {'quantity': '2', 'reference': uuid4().hex, 'evidence_reference': 'SYN-DELIVERY', 'defects': ''}, order['id']))
    assert action(c, f"/operations/records/{delivery['id']}/actions", delivery, 'COMPLETE').status_code == 403
    act(c, f"/operations/records/{delivery['id']}/actions", delivery, 'COMPLETE', 'checker')
    obligation = create(c, '/operations/expenses', payload, 'accountant')
    assert obligation['amount_vnd'] == 90


def test_content_approval_survey_and_vote_duplicate(controlled_case):
    c = controlled_case; now = datetime.now(UTC)
    row = create(c, '/content', {'building_id': str(c['building'].id), 'kind': 'VOTE', 'title': 'Synthetic vote', 'body': 'Synthetic body', 'publish_at': (now-timedelta(minutes=1)).isoformat(), 'policy': {'options': ['YES', 'NO'], 'confirmed_rule_reference': 'SYN-RULE'}})
    assert action(c, f"/content/{row['id']}/actions", row, 'PUBLISH').status_code == 409
    row = act(c, f"/content/{row['id']}/actions", row, 'SUBMIT')
    assert action(c, f"/content/{row['id']}/actions", row, 'APPROVE').status_code == 403
    row = act(c, f"/content/{row['id']}/actions", row, 'APPROVE', 'checker'); row = act(c, f"/content/{row['id']}/actions", row, 'PUBLISH')
    answer = {'unit_id': str(c['unit'].id), 'answer': 'YES'}
    create(c, f"/control/content/{row['id']}/responses", answer, 'resident')
    assert post(c, f"/control/content/{row['id']}/responses", answer, 'resident').status_code == 409


def test_report_frozen_scope_and_tamper_guard(controlled_case):
    c = controlled_case; treasury(c)
    row = create(c, '/control/reports', {'building_id': str(c['building'].id), 'kind': 'FINANCIAL'}, 'accountant')
    response = c['client'].get(f"/api/v1/portal/control/reports/{row['id']}", headers=c['auth']['accountant'])
    assert response.status_code == 200, response.text
    assert sum(response.json()['counts'].values()) == len(row['rows'])
    assert c['client'].get(f"/api/v1/portal/control/reports/{row['id']}", headers=c['auth']['resident']).status_code in (403, 404)
    with c['database'].get_session() as s:
        with pytest.raises(DBAPIError), s.begin_nested():
            s.execute(text("UPDATE greencity.report_exports SET rows='[]' WHERE id=:id"), {'id': row['id']})


def test_invitation_pending_one_use_and_purpose(controlled_case):
    c = controlled_case
    with c['database'].get_session() as s:
        s.add(AccountRole(account_id=c['maker'].id, role='admin', site_id=None, building_id=None)); s.commit()
    row = create(c, '/control/invitations', {'building_id': str(c['building'].id), 'username': 'invite_'+uuid4().hex, 'full_name': 'Synthetic invite', 'role': 'security', 'email': 'synthetic@example.invalid', 'verification_reference': 'SYN-VERIFIED'})
    assert 'token_hash' not in row
    from app.models.account import Account
    import secrets
    token = secrets.token_urlsafe(48)
    with c['database'].get_session() as s:
        invitation = s.get(AccountInvitation, UUID(row['id'])); target = s.get(Account, invitation.target_account_id); assert not target.is_active
        invitation.token_hash = hashlib.sha256(('account-invitation:'+token).encode()).hexdigest(); s.commit()
    url = f"/api/v1/portal/invitations/{row['id']}/accept"
    payload = {'token': token, 'password': secrets.token_urlsafe(24)}
    assert c['client'].post(url, json={**payload, 'token': 'wrong'*10}).status_code == 422
    assert c['client'].post(url, json=payload).status_code == 200
    assert c['client'].post(url, json=payload).status_code == 422


def test_slots_card_blanks_and_stale_device_commands(controlled_case):
    c = controlled_case; parking = resource(c, 'PARKING', capacity=2)
    vehicle = create(c, '/vehicles', {'unit_id': str(c['unit'].id), 'resource_id': parking['id'], 'plate': 'SYN-'+uuid4().hex[:9], 'vehicle_type': 'CAR'}, 'resident')
    vehicle = act(c, f"/vehicles/{vehicle['id']}/actions", vehicle, 'APPROVE')
    slot = create(c, '/control/parking-slots', {'resource_id': parking['id'], 'code': 'A-1', 'vehicle_types': ['BIKE']})
    assert action(c, f"/control/parking-slots/{slot['id']}/actions", slot, 'ASSIGN', data={'vehicle_id': vehicle['id']}).status_code == 409
    response = action(c, f"/vehicles/{vehicle['id']}/credential", vehicle, 'ISSUE'); assert response.status_code == 201, response.text
    card = response.json()
    blank = create(c, '/control/card-blanks', {'building_id': str(c['building'].id), 'code': 'SYN-CARD-'+uuid4().hex[:8]})
    act(c, f"/control/card-blanks/{blank['id']}/actions", blank, 'ISSUE', data={'credential_id': card['id']})
    card = c['client'].get('/api/v1/portal/credentials', headers=c['auth']['cskh']).json()['items'][0]
    endpoint = create(c, '/control/integrations', {'building_id': str(c['building'].id), 'code': uuid4().hex, 'kind': 'ACCESS'})
    delivery = act(c, f"/control/integrations/{endpoint['id']}/queue", endpoint, 'QUEUE', data={'credential_id': card['id']})
    assert delivery['status'] == 'NOT_CONFIGURED'
    act(c, f"/credentials/{card['id']}/actions", card, 'LOCK')
    delivery = act(c, f"/control/deliveries/{delivery['id']}/actions", delivery, 'RETRY')
    assert delivery['status'] == 'SUPERSEDED'


def test_visitor_capacity_and_booking_quota(controlled_case):
    c = controlled_case; parking = resource(c, 'PARKING', capacity=1)
    guest = create(c, '/control/visitor-parking', {'resource_id': parking['id'], 'plate': 'SYN-VISITOR', 'vehicle_type': 'CAR', 'rate_vnd': 100, 'entered_at': (datetime.now(UTC)-timedelta(hours=2)).isoformat()})
    vehicle = create(c, '/vehicles', {'unit_id': str(c['unit'].id), 'resource_id': parking['id'], 'plate': 'SYN-CAR', 'vehicle_type': 'CAR'}, 'resident')
    assert act(c, f"/vehicles/{vehicle['id']}/actions", vehicle, 'APPROVE')['status'] == 'WAITING'
    guest = act(c, f"/control/visitor-parking/{guest['id']}/actions", guest, 'EXIT', data={'exited_at': datetime.now(UTC).isoformat()})
    assert guest['fee_vnd'] >= 200
    facility = resource(c, 'FACILITY', capacity=10)
    facility = act(c, f"/resources/{facility['id']}/actions", facility, 'UPDATE', data={'name': facility['name'], 'description': '', 'capacity': 10, 'fee_vnd': 1000, 'deposit_vnd': 0, 'policy': {**facility['policy'], 'quota_per_unit': 1, 'quota_window_days': 7}})
    start = datetime.now(UTC)+timedelta(days=1)
    payload = {'unit_id': str(c['unit'].id), 'resource_id': facility['id'], 'starts_at': start.isoformat(), 'ends_at': (start+timedelta(hours=1)).isoformat()}
    create(c, '/bookings', payload, 'resident')
    assert post(c, '/bookings', payload, 'resident').status_code == 409


def test_document_verify_expiry_bundle_and_retention(controlled_case):
    c = controlled_case
    response = c['client'].post('/api/v1/portal/documents', params={'unit_id': str(c['unit'].id), 'title': 'Synthetic document'}, content=b'%PDF-1.4\nsynthetic\n%%EOF', headers={**c['auth']['resident'], 'Idempotency-Key': uuid4().hex, 'Content-Type': 'application/pdf', 'X-File-Name': 'synthetic.pdf'})
    assert response.status_code == 201, response.text
    doc = act(c, f"/documents/{response.json()['id']}/actions", response.json(), 'VERIFY', data={'expires_on': '2026-01-01', 'retain_until': '2026-01-02'})
    assert doc['verification_status'] == 'VERIFIED'
    bundle = c['client'].post('/api/v1/portal/control/documents/bundle', json={'unit_id': str(c['unit'].id), 'document_ids': [doc['id']]}, headers=c['auth']['resident'])
    assert bundle.status_code == 200 and bundle.content.startswith(b'PK'), bundle.text[:100]
    doc = act(c, f"/documents/{doc['id']}/actions", doc, 'ARCHIVE')
    denied = c['client'].get(f"/api/v1/portal/documents/{doc['id']}/signed-link", params={'unit_id': str(c['unit'].id)}, headers=c['auth']['resident'])
    assert denied.status_code == 423


def test_job_failure_rollback_and_controlled_retry(controlled_case, monkeypatch):
    c = controlled_case
    row = create(c, '/control/jobs', {'building_id': str(c['building'].id), 'name': 'Synthetic lifecycle', 'kind': 'LIFECYCLE', 'interval_minutes': 5, 'next_run_at': (datetime.now(UTC)-timedelta(minutes=1)).isoformat()})
    from app.models.resident_portal import PortalContent
    from app.services import business_jobs
    with c['database'].get_session() as session:
        session.add(PortalContent(tenant_id=c['tenant'].id,site_id=c['site'].id,building_id=c['building'].id,account_id=c['maker'].id,
            kind='NOTICE',title='Synthetic published notice',body='Synthetic notice body',status='PUBLISHED',publish_at=datetime.now(UTC)-timedelta(days=1)))
        session.commit()
    original = business_jobs.perform
    def failure(*args):
        from app.core.exceptions import AppError
        raise AppError('ERR-SYNTHETIC-JOB', 'Synthetic failure', 409)
    monkeypatch.setattr(business_jobs, 'perform', failure)
    failed = act(c, f"/control/jobs/{row['id']}/actions", row, 'RUN')
    assert failed['status'] == 'FAILED' and failed['result']['items'][0]['error_code'] == 'ERR-SYNTHETIC-JOB'
    monkeypatch.setattr(business_jobs, 'perform', original)
    retried = act(c, f"/control/jobs/{row['id']}/actions", row, 'RETRY')
    assert retried['id'] == failed['id'] and retried['status'] == 'SUCCEEDED'


def test_resident_host_confirmation_and_violation_appeal(controlled_case):
    c = controlled_case
    from app.models.account import Account
    with c['database'].get_session() as s:
        owner_account = s.scalar(select(Account).where(Account.person_id == c['owner'].id))
    now = datetime.now(UTC)
    visitor = approve(c, record(c, 'VISITOR', {'host_account_id': str(owner_account.id), 'name': 'Synthetic guest', 'starts_at': (now-timedelta(minutes=1)).isoformat(), 'ends_at': (now+timedelta(hours=1)).isoformat(), 'purpose': 'Synthetic visit', 'areas': ['LOBBY']}, unit=True))
    assert action(c, f"/operations/records/{visitor['id']}/actions", visitor, 'START').status_code == 409
    visitor = act(c, f"/operations/resident-records/{visitor['id']}/actions", visitor, 'HOST_CONFIRM', 'resident')
    visitor = act(c, f"/operations/records/{visitor['id']}/actions", visitor, 'ENTER')
    assert visitor['status'] == 'IN_PROGRESS'
    rule = approve(c, record(c, 'RULE', {'code': uuid4().hex, 'revision': 1, 'valid_from': '2025-01-01', 'body': 'Synthetic rule', 'confirmed_rule_reference': 'SYN-PROCESS'}))
    violation = approve(c, record(c, 'VIOLATION', {'rule_id': rule['id'], 'occurred_on': '2026-09-01', 'evidence_reference': 'SYN-EVIDENCE', 'description': 'Synthetic violation', 'subject_account_id': str(owner_account.id)}, unit=True))
    violation = act(c, f"/operations/resident-records/{violation['id']}/actions", violation, 'APPEAL', 'resident')
    assert violation['status'] == 'APPEALED'
    assert action(c, f"/operations/resident-records/{violation['id']}/actions", violation, 'DECIDE', 'resident').status_code == 409


def test_template_delivery_ack_and_placeholder_guard(controlled_case):
    c = controlled_case
    from app.models.account import Account
    from app.models.platform import NotificationReadModel
    with c['database'].get_session() as s:
        owner_account = s.scalar(select(Account).where(Account.person_id == c['owner'].id))
    payload = {'building_id': str(c['building'].id), 'code': 'SYN_'+uuid4().hex.upper(), 'title': 'Synthetic {name}', 'body': 'Synthetic message {name}', 'required_fields': ['name'], 'mandatory': True}
    assert post(c, '/control/templates', {**payload, 'body': '{name:1000000000}'}, 'cskh').status_code == 422
    template = create(c, '/control/templates', payload)
    delivery = create(c, f"/control/templates/{template['id']}/send", {'recipient_account_id': str(owner_account.id), 'variables': {'name': 'Synthetic'}, 'category': 'SECURITY'})
    assert delivery['channel'] == 'IN_APP'
    ack = post(c, f"/control/notifications/{delivery['notification_id']}/ack", {}, 'resident')
    assert ack.status_code == 200, ack.text
    repeated = post(c, f"/control/notifications/{delivery['notification_id']}/ack", {}, 'resident')
    assert repeated.json()['acknowledged_at'] == ack.json()['acknowledged_at']


def test_measured_fee_correction_invalidates_review_and_preserves_issued_invoice(controlled_case):
    c = controlled_case
    from app.models.billing import FeePolicy, FeePolicyVersion, BillingInvoice
    from app.models.resident_portal import PortalFeeSource
    from test_steps2_3 import issue, next_action
    with c['database'].get_session() as s:
        scope = {'tenant_id': c['tenant'].id, 'site_id': c['site'].id, 'building_id': c['building'].id}
        policy = FeePolicy(**scope, code=uuid4().hex, name='Synthetic water tariff'); s.add(policy); s.flush()
        tariff = FeePolicyVersion(**scope, fee_policy_id=policy.id, version_number=1, effective_from=date(2025,1,1), unit_rate_vnd=123, rounding_unit_vnd=10, basis='SERVICE_UNIT', published_at=datetime.now(UTC))
        s.add(tariff); s.commit(); tariff_id = str(tariff.id)
    meter = create(c, '/operations/meters', {'building_id': str(c['building'].id), 'unit_id': str(c['unit'].id), 'code': uuid4().hex, 'serial': uuid4().hex, 'commodity': 'WATER', 'baseline': '100', 'valid_from': '2026-09-01'})
    reading = create(c, '/operations/readings', {'meter_id': meter['id'], 'read_on': '2026-09-20', 'value': '110.5', 'evidence_reference': 'SYN-READ'})
    assert post(c, f"/operations/readings/{reading['id']}/billing", {'expected_version': reading['version'], 'tariff_version_id': tariff_id}, 'accountant').status_code == 409
    reading = act(c, f"/operations/readings/{reading['id']}/actions", reading, 'VERIFY', 'checker')
    source = create(c, f"/operations/readings/{reading['id']}/billing", {'expected_version': reading['version'], 'tariff_version_id': tariff_id}, 'accountant')
    assert source['amount_vnd'] == 1290
    preview_url = f"/api/v1/portal/fee-sources/{source['id']}/preview"
    old = c['client'].get(preview_url, params={'period_id': str(c['period'].id)}, headers=c['auth']['accountant']).json()
    r = post(c, f"/fee-sources/{source['id']}/post", {'period_id': str(c['period'].id), 'expected_version': source['version'], 'calculation_hash': old['calculation_hash']}, 'accountant')
    assert r.status_code == 200, r.text
    review = next_action(c, 'reviews', r.json(), 'SUBMIT'); review = next_action(c, 'reviews', review, 'APPROVE', 'checker')
    approve(c, record(c, 'METER_CORRECTION', {'reading_id': reading['id'], 'corrected_value': '111', 'evidence_reference': 'SYN-CORRECT'}))
    assert action(c, f"/finance/reviews/{review['id']}/actions", review, 'ISSUE', 'accountant').status_code == 409
    review = next_action(c, 'reviews', review, 'REFRESH')
    result = issue(c, review)
    invoice_id = result['issued_invoice_ids'][0]
    correction = record(c, 'METER_CORRECTION', {'reading_id': reading['id'], 'corrected_value': '112', 'evidence_reference': 'SYN-AFTER-INVOICE'})
    correction = act(c, f"/operations/records/{correction['id']}/actions", correction, 'SUBMIT')
    adjusted = action(c, f"/operations/records/{correction['id']}/actions", correction, 'APPROVE', 'checker')
    assert adjusted.status_code == 200 and adjusted.json()['data']['additional_fee_source_ids']
    with c['database'].get_session() as s:
        assert s.get(BillingInvoice, UUID(invoice_id)).total_vnd == 1350
        assert s.get(PortalFeeSource, UUID(source['id'])).amount_vnd == 1350


def test_meter_cycle_missing_readings_and_independent_close(controlled_case):
    c = controlled_case
    meter = create(c, '/operations/meters', {'building_id': str(c['building'].id), 'code': uuid4().hex, 'serial': uuid4().hex, 'commodity': 'WATER', 'baseline': '0', 'valid_from': '2026-09-01'})
    cycle = approve(c, record(c, 'METER_CYCLE', {'starts_on': '2026-09-01', 'ends_on': '2026-09-30', 'meter_ids': [meter['id']], 'route': 'Synthetic route'}))
    url = f"/operations/records/{cycle['id']}/actions"
    assert action(c, url, cycle, 'COMPLETE', 'checker').status_code == 409
    progress = c['client'].get(f"/api/v1/portal/operations/records/{cycle['id']}/progress", headers=c['auth']['cskh'])
    assert progress.status_code == 200 and progress.json()['missing'] == 1
    cycle = act(c, url, cycle, 'UNREADABLE', data={'meter_id': meter['id']})
    assert action(c, url, cycle, 'COMPLETE').status_code == 403
    assert act(c, url, cycle, 'COMPLETE', 'checker')['status'] == 'COMPLETED'


def test_general_and_visitor_cards_cannot_escape_host_authority(controlled_case):
    c = controlled_case
    from app.models.account import Account
    with c['database'].get_session() as s:
        holder = s.scalar(select(Account).where(Account.person_id == c['owner'].id))
    payload = {'building_id': str(c['building'].id), 'unit_id': str(c['unit'].id), 'holder_account_id': str(holder.id), 'valid_to': (date.today()+timedelta(days=1)).isoformat(), 'areas': ['LOBBY']}
    general = create(c, '/control/access-cards', payload)
    assert general['vehicle_id'] is None
    now = datetime.now(UTC)
    guest = approve(c, record(c, 'VISITOR', {'host_account_id': str(holder.id), 'name': 'Synthetic guest', 'starts_at': (now-timedelta(minutes=1)).isoformat(), 'ends_at': (now+timedelta(hours=1)).isoformat(), 'purpose': 'Synthetic visit', 'areas': ['LOBBY']}, unit=True))
    guest = act(c, f"/operations/resident-records/{guest['id']}/actions", guest, 'HOST_CONFIRM', 'resident')
    guest_payload = {**payload, 'authorization_record_id': guest['id'], 'valid_to': now.date().isoformat()}
    assert post(c, '/control/access-cards', {**guest_payload, 'areas': ['PLANT_ROOM']}, 'cskh').status_code == 409
    card = create(c, '/control/access-cards', guest_payload)
    guest = act(c, f"/operations/records/{guest['id']}/actions", guest, 'ENTER'); act(c, f"/operations/records/{guest['id']}/actions", guest, 'EXIT')
    card = act(c, f"/control/access-cards/{card['id']}/actions", card, 'LOCK')
    assert action(c, f"/control/access-cards/{card['id']}/actions", card, 'UNLOCK').status_code == 409
    lost = act(c, f"/credentials/{general['id']}/actions", general, 'LOST', 'resident')
    replacement = act(c, f"/control/access-cards/{general['id']}/actions", lost, 'REPLACE')
    assert replacement['replaces_id'] == general['id']


def test_smtp_uncertain_delivery_requires_reconciliation_before_retry(controlled_case, monkeypatch):
    c = controlled_case
    from app.models.account import Account
    with c['database'].get_session() as s:
        holder = s.scalar(select(Account).where(Account.person_id == c['owner'].id))
        s.add(AccountInvitation(tenant_id=c['tenant'].id, site_id=c['site'].id, building_id=c['building'].id, account_id=c['maker'].id, target_account_id=holder.id, email='synthetic@example.invalid', verification_reference='SYN-VERIFIED', expires_at=datetime.now(UTC)+timedelta(hours=1), status='USED', delivery_status='SENT'))
        s.commit()
    assert post(c, '/control/preferences', {'category': 'SECURITY', 'channel': 'EMAIL', 'enabled': True}, 'resident').status_code == 200
    template = create(c, '/control/templates', {'building_id': str(c['building'].id), 'code': 'SYN_'+uuid4().hex.upper(), 'title': 'Synthetic', 'body': 'Synthetic notification', 'required_fields': [], 'mandatory': True})
    delivery = create(c, f"/control/templates/{template['id']}/send", {'recipient_account_id': str(holder.id), 'variables': {}, 'category': 'SECURITY'})
    monkeypatch.setattr('app.services.portal_mail.require_smtp', lambda settings: None)
    calls = []
    def timeout(*args):
        calls.append(True); raise TimeoutError('Synthetic timeout')
    monkeypatch.setattr('app.services.portal_mail.send_message', timeout)
    unknown = act(c, f"/control/notification-deliveries/{delivery['id']}/send", delivery, 'SEND')
    assert unknown['status'] == 'UNKNOWN' and len(calls) == 1
    assert action(c, f"/control/notification-deliveries/{delivery['id']}/send", unknown, 'SEND').status_code == 409
    reconciled = act(c, f"/control/notification-deliveries/{delivery['id']}/actions", unknown, 'CONFIRM_FAILED', data={'delivery_evidence_reference': 'SYN-RECONCILED'})
    monkeypatch.setattr('app.services.portal_mail.send_message', lambda *args: calls.append(True))
    assert act(c, f"/control/notification-deliveries/{delivery['id']}/send", reconciled, 'SEND')['status'] == 'SENT'
    assert len(calls) == 2


def test_asset_profile_outage_and_restore_with_history(controlled_case, monkeypatch):
    c = controlled_case
    with c['database'].get_session() as s:
        s.add(AccountRole(account_id=c['maker'].id, role='technical_lead', site_id=c['site'].id, building_id=c['building'].id)); s.commit()
    from app.models.maintenance import Asset
    response = c['client'].post('/api/v1/assets', json={'building_id': str(c['building'].id), 'code': 'SYN-'+uuid4().hex[:12].upper(), 'name': 'Synthetic asset'}, headers={**c['auth']['cskh'], 'Idempotency-Key': uuid4().hex})
    assert response.status_code == 201, response.text
    asset = response.json(); now = datetime.now(UTC)
    base = {'asset_id': asset['id'], 'location': 'Synthetic plant room', 'due_on': '2026-10-10', 'description': 'Synthetic operation', 'evidence_reference': 'SYN-EVIDENCE'}
    profile = approve(c, record(c, 'ASSET_CHANGE', {**base, 'operation': 'PROFILE', 'serial': 'SYN-SERIAL', 'warranty_until': '2027-01-01'}))
    act(c, f"/operations/records/{profile['id']}/actions", profile, 'COMPLETE')
    outage = approve(c, record(c, 'ASSET_CHANGE', {**base, 'operation': 'OUTAGE', 'starts_at': (now-timedelta(minutes=1)).isoformat(), 'ends_at': (now+timedelta(minutes=1)).isoformat()}))
    act(c, f"/operations/records/{outage['id']}/actions", outage, 'COMPLETE')
    assert post(c, '/jobs/tick', {}, 'cskh').status_code == 200
    with c['database'].get_session() as s:
        row = s.get(Asset, UUID(asset['id'])); assert row.status == 'INACTIVE' and row.serial == 'SYN-SERIAL'
    monkeypatch.setattr('app.services.portal_jobs.utc_now', lambda: now+timedelta(minutes=2))
    assert post(c, '/jobs/tick', {}, 'cskh').status_code == 200
    with c['database'].get_session() as s:
        assert s.get(Asset, UUID(asset['id'])).status == 'INACTIVE'
    restore = approve(c, record(c, 'ASSET_CHANGE', {**base, 'operation': 'RESTORE', 'inspection_due_on': '2027-01-01'}))
    act(c, f"/operations/records/{restore['id']}/actions", restore, 'COMPLETE')
    with c['database'].get_session() as s:
        assert s.get(Asset, UUID(asset['id'])).status == 'ACTIVE'
    summary = c['client'].get(f"/api/v1/portal/operations/assets/{asset['id']}/summary", headers=c['auth']['cskh'])
    assert summary.status_code == 200 and summary.json()['material_cost_vnd'] == 0
    from app.models.maintenance import MaintenancePlan, MaintenanceOccurrence
    from app.models.service import CostLine
    with c['database'].get_session() as s:
        scope = dict(tenant_id=c['tenant'].id, site_id=c['site'].id, building_id=c['building'].id, created_by_id=c['maker'].id, updated_by_id=c['maker'].id)
        plan = MaintenancePlan(**scope, asset_id=UUID(asset['id']), code=uuid4().hex, title='Synthetic plan', interval_days=30, next_due_at=now, checklist_template=[])
        s.add(plan); s.flush()
        occurrence = MaintenanceOccurrence(**scope, plan_id=plan.id, due_at=now); s.add(occurrence); s.flush()
        wo = WorkOrder(**scope, maintenance_occurrence_id=occurrence.id, code=uuid4().hex, title='Synthetic maintenance', description='Synthetic work', status='IN_PROGRESS')
        s.add(wo); s.flush(); wo_id = wo.id
        s.add(CostLine(work_order_id=wo.id, description='Synthetic estimate', amount_vnd=500, cost_bearer='MANAGEMENT', created_by_id=c['maker'].id, updated_by_id=c['maker'].id)); s.commit()
    labor = approve(c, record(c, 'ASSET_CHANGE', {**base, 'operation': 'LABOR', 'work_order_id': str(wo_id), 'hours': '1.5', 'cost_vnd': 200}))
    act(c, f"/operations/records/{labor['id']}/actions", labor, 'COMPLETE')
    retired = approve(c, record(c, 'ASSET_CHANGE', {**base, 'operation': 'RETIRE'}))
    blocked = action(c, f"/operations/records/{retired['id']}/actions", retired, 'COMPLETE'); assert blocked.status_code == 409 and blocked.json()['error']['code'] == 'ERR-ASSET-OPEN-WORK'
    summary = c['client'].get(f"/api/v1/portal/operations/assets/{asset['id']}/summary", headers=c['auth']['cskh'])
    assert summary.status_code == 200, summary.text
    assert summary.json()['submitted_cost_vnd'] == 500 and summary.json()['labor_cost_vnd'] == 200
    assert float(summary.json()['labor_hours']) == 1.5 and summary.json()['work_orders'][0]['id'] == str(wo_id)


def test_account_lock_end_and_session_management_require_tenant_admin(controlled_case):
    c = controlled_case
    from app.models.account import Account
    with c['database'].get_session() as s:
        holder = s.scalar(select(Account).where(Account.person_id == c['owner'].id))
    target = {'version': holder.session_version}
    path = f'/control/accounts/{holder.id}/actions'
    assert action(c, path, target, 'LOCK').status_code == 403
    with c['database'].get_session() as s:
        s.add(AccountRole(account_id=c['maker'].id, role='admin', site_id=None, building_id=None)); s.commit()
    act(c, path, target, 'LOCK')
    assert c['client'].get('/api/v1/auth/me', headers=c['auth']['resident']).status_code == 401
    sessions = c['client'].get(f'/api/v1/portal/control/accounts/{holder.id}/sessions', headers=c['auth']['cskh'])
    assert sessions.status_code == 200 and all(row['revoked_at'] for row in sessions.json()['items'])
    target['version'] += 1; act(c, path, target, 'UNLOCK')
    target['version'] += 1; act(c, path, target, 'END')
    target['version'] += 1
    assert action(c, path, target, 'UNLOCK').status_code == 409
    assert action(c, f"/control/accounts/{c['maker'].id}/actions", {'version': 1}, 'SET_ROLE', data={'role': 'admin'}).status_code == 403


def test_history_report_and_reference_options_recheck_domain_and_building_scope(controlled_case):
    c = controlled_case; budget = treasury(c)
    from app.models.account import Account
    from app.models.building import Building
    from sqlalchemy import delete
    revision = approve(c, record(c, 'BUDGET_REVISION', {'budget_id': budget['id'], 'new_limit_vnd': 2000, 'evidence_reference': 'SYN-REVISION'}))
    export = create(c, '/control/reports', {'building_id': str(c['building'].id), 'kind': 'DOSSIERS'})
    with c['database'].get_session() as s:
        other = Building(site_id=c['site'].id, code=uuid4().hex, name='Synthetic other'); s.add(other); s.flush()
        foreign = Account(tenant_id=c['tenant'].id, username=uuid4().hex, full_name='Synthetic foreign staff', hashed_password='token-only-test-account'); s.add(foreign); s.flush()
        s.add(AccountRole(account_id=foreign.id, site_id=c['site'].id, building_id=other.id, role='cleaning'))
        s.execute(delete(AccountRole).where(AccountRole.account_id == c['maker'].id))
        s.add(AccountRole(account_id=c['maker'].id, site_id=c['site'].id, building_id=c['building'].id, role='cskh')); s.commit()
    assert c['client'].get(f"/api/v1/portal/control/history/treasury_accounts/{budget['id']}", headers=c['auth']['cskh']).status_code in (403,404)
    assert c['client'].get(f"/api/v1/portal/control/reports/{export['id']}", headers=c['auth']['cskh']).status_code == 403
    assert c['client'].get('/api/v1/portal/operations/options', headers=c['auth']['resident']).status_code == 403
    options = c['client'].get('/api/v1/portal/operations/options', headers=c['auth']['cskh'])
    assert options.status_code == 200 and str(foreign.id) not in [r['id'] for r in options.json()['accounts']]
    filtered = create(c, '/control/reports', {'building_id': str(c['building'].id), 'kind': 'DOSSIERS'})
    assert revision['id'] not in [r['data']['id'] for r in filtered['rows']]


def test_supplier_contract_revision_and_lease_deposit_keep_sources(controlled_case):
    c = controlled_case
    from app.models.property import LeaseContract
    from app.models.resident_portal import PortalDeposit
    from test_steps2_3 import dossier, approve_dossier
    vendor = approve(c, record(c, 'VENDOR', {'code': uuid4().hex, 'tax_code': 'SYN-TAX', 'capabilities': 'Synthetic capability', 'contact': 'Synthetic contact'}))
    contract = approve(c, record(c, 'CONTRACT', {'vendor_id': vendor['id'], 'reference': uuid4().hex, 'starts_on': '2026-09-01', 'ends_on': '2026-10-01', 'amount_vnd': 1000, 'milestones': 'Synthetic milestones', 'milestone_items': [{'code': 'SYN-M1', 'due_on': '2026-10-01', 'amount_vnd': 1000, 'obligation': 'Synthetic obligation'}]}))
    revision = approve(c, record(c, 'CONTRACT_REVISION', {'contract_id': contract['id'], 'operation': 'RENEW', 'reference': uuid4().hex, 'starts_on': '2026-10-01', 'ends_on': '2027-10-01', 'amount_vnd': 1200, 'milestones': 'Synthetic renewed milestones', 'milestone_items': [{'code': 'SYN-M2', 'due_on': '2027-10-01', 'amount_vnd': 1200, 'obligation': 'Synthetic renewed obligation'}], 'evidence_reference': 'SYN-RENEW'}))
    assert revision['data']['new_contract_id'] != contract['id']
    approve_dossier(c, dossier(c, 'LEASE', {'target_person_id': str(c['payer'].id), 'contract_reference': uuid4().hex}, start='2026-09-01', end='2027-09-01'))
    with c['database'].get_session() as s:
        lease = s.scalar(select(LeaseContract).where(LeaseContract.unit_id == c['unit'].id, LeaseContract.status == 'ACTIVE'))
    policy = approve(c, record(c, 'DEPOSIT_POLICY', {'code': uuid4().hex, 'purpose': 'Synthetic lease deposit', 'source_kind': 'LEASE', 'amount_vnd': 1000, 'conditions': 'Synthetic return conditions', 'valid_from': '2026-01-01'}))
    deposited = approve(c, record(c, 'LEASE_DEPOSIT', {'lease_id': str(lease.id), 'policy_id': policy['id'], 'evidence_reference': 'SYN-LEASE-DEPOSIT'}))
    with c['database'].get_session() as s:
        deposit = s.get(PortalDeposit, UUID(deposited['data']['deposit_id']))
        assert deposit.required_vnd == 1000 and deposit.balance_vnd == 0 and deposit.source_id == lease.id


def test_opposite_parking_changes_and_slot_assignment_keep_consistent_resources(controlled_case):
    c = controlled_case; left = resource(c, 'PARKING', capacity=2); right = resource(c, 'PARKING', capacity=2)
    for parking in (left, right):
        act(c, f"/resources/{parking['id']}/actions", parking, 'UPDATE', data={'policy': {**parking['policy'], 'quota_per_unit': 2}})
    cars = []
    for parking in (left, right):
        row = create(c, '/vehicles', {'unit_id': str(c['unit'].id), 'resource_id': parking['id'], 'plate': 'SYN-'+uuid4().hex[:10], 'vehicle_type': 'CAR'}, 'resident')
        cars.append(act(c, f"/vehicles/{row['id']}/actions", row, 'APPROVE'))
    def change(pair):
        car, target = pair
        return action(c, f"/control/vehicles/{car['id']}/change", car, 'CHANGE', 'cskh', {'resource_id': target['id'], 'plate': car['plate'], 'vehicle_type': 'CAR'})
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(change, [(cars[0], right), (cars[1], left)]))
    assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
    slot = create(c, '/control/parking-slots', {'resource_id': right['id'], 'code': 'SYN-SLOT', 'vehicle_types': ['CAR']})
    assert act(c, f"/control/parking-slots/{slot['id']}/actions", slot, 'ASSIGN', data={'vehicle_id': cars[0]['id']})['vehicle_id'] == cars[0]['id']


def test_resident_report_contains_scoped_units_and_relations(controlled_case):
    c = controlled_case
    report = create(c, '/control/reports', {'building_id': str(c['building'].id), 'kind': 'RESIDENT'})
    units = [r['data'] for r in report['rows'] if r['source'] == 'units']
    assert [r['id'] for r in units] == [str(c['unit'].id)]
    assert all(r['data']['building_id'] == str(c['building'].id) for r in report['rows'])
    assert any(r['source'] == 'unit_person_relationships' for r in report['rows'])


def test_facility_opening_schedule_and_availability_use_same_rules(controlled_case):
    from app.services.resident_portal import validate_resource_policy
    from app.core.exceptions import AppError
    c = controlled_case; facility = resource(c, 'FACILITY', capacity=2)
    local = datetime.now(UTC) + timedelta(days=2)
    day = local.date()
    start = datetime(day.year, day.month, day.day, 1, tzinfo=UTC)  # 08:00 GMT+7
    policy = {**facility['policy'], 'opening_weekdays': [start.isoweekday()], 'opens_at': '08:00', 'closes_at': '10:00'}
    act(c, f"/resources/{facility['id']}/actions", facility, 'UPDATE', data={'policy': policy})
    def body(moment):
        return {'resource_id': facility['id'], 'unit_id': str(c['unit'].id), 'starts_at': moment.isoformat(), 'ends_at': (moment+timedelta(minutes=30)).isoformat()}
    for moment in (start-timedelta(minutes=30), start+timedelta(minutes=15), start+timedelta(hours=2), start+timedelta(days=1)):
        response = post(c, '/bookings', body(moment), 'resident'); assert response.status_code == 422, response.text
        result = c['client'].get(f"/api/v1/portal/resources/{facility['id']}/availability", params={k: v for k, v in body(moment).items() if k != 'resource_id'}, headers=c['auth']['resident'])
        assert result.status_code == 422, result.text
    booked = create(c, '/bookings', body(start), 'resident'); assert booked['policy_snapshot']['opens_at'] == '08:00'
    for malformed in ({'opens_at': '08:00'}, {'opening_weekdays': [True], 'opens_at': '08:00', 'closes_at': '10:00'}, {'opening_weekdays': [1, 1], 'opens_at': '08:00', 'closes_at': '10:00'}):
        with pytest.raises(AppError):
            validate_resource_policy('FACILITY', {**facility['policy'], **malformed})


def test_role_effectivity_rechecks_issued_session_and_keeps_history(controlled_case):
    from app.models.account import Account
    from app.core.policy import context_for_account
    from app.models.operational_control import OperationsRecord
    c = controlled_case; now = datetime.now(UTC)
    with c['database'].get_session() as s:
        s.add(AccountRole(account_id=c['maker'].id, role='admin', site_id=None, building_id=None)); s.commit()
        target = s.get(Account, c['checker'].id); version = target.session_version
    body = {'action': 'SET_ROLE', 'expected_version': version, 'reason': 'Synthetic timed assignment', 'data': {'role': 'security', 'building_id': str(c['building'].id), 'valid_from': (now-timedelta(minutes=1)).isoformat(), 'valid_to': (now+timedelta(minutes=1)).isoformat()}}
    response = post(c, f"/control/accounts/{c['checker'].id}/actions", body, 'cskh'); assert response.status_code == 200, response.text
    with c['database'].get_session() as s:
        target = s.get(Account, c['checker'].id)
        assert context_for_account(s, target, c['site'].id).roles == ['security']
        grant = s.scalar(select(AccountRole).where(AccountRole.account_id == target.id)); grant.valid_to = now-timedelta(seconds=1); s.commit()
        assert 'security' not in context_for_account(s, target).roles
        from app.api.security import _account_has_security_grant
        assert not _account_has_security_grant(s, context_for_account(s, c['maker'], c['site'].id), target.id, c['building'].id)
        change = s.scalar(select(OperationsRecord).where(OperationsRecord.related_id == target.id, OperationsRecord.kind == 'ACCOUNT_CHANGE'))
        assert change.data['before']['roles'][0]['role'] == 'admin'
        assert change.data['after']['roles'][0]['valid_to'] is not None
        # Existing resident token must stop authorizing the instant its role expires.
        resident_grant = s.scalar(select(AccountRole).join(Account, Account.id == AccountRole.account_id).where(Account.tenant_id == c['tenant'].id, AccountRole.role == 'resident'))
        resident_grant.valid_to = now-timedelta(seconds=1); s.commit()
    assert c['client'].get('/api/v1/portal/profile', headers=c['auth']['resident']).status_code in (403, 404)
    sessions = c['client'].get(f"/api/v1/portal/control/accounts/{c['checker'].id}/sessions", headers=c['auth']['cskh'])
    assert sessions.status_code == 200 and sessions.json()['changes'][0]['data']['action'] == 'SET_ROLE'
