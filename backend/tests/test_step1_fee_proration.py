from billing_review_support import finish_review, checker_headers
"""Independent money oracles and persisted workflows on disposable PostgreSQL."""
from datetime import UTC, date, datetime
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from decimal import Decimal
import os
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select

from app.core.config import Settings
from app.core.database import Database
from app.main import create_app
from app.models.account import Account, AccountRole
from app.models.billing import AccountingPeriod, ArLedgerEntry, BillingAccount, BillingInvoice, BillingInvoiceItem, FeePolicyVersion
from app.models.building import Building
from app.models.person import Person, UnitPersonRelationship
from app.models.resident_portal import PortalFeeInterval, PortalFeeSource, ServiceEnrollment
from app.models.site import Site
from app.models.tenant import Tenant
from app.models.unit import Unit
from app.services.billing_proration import calculate_proration
from auth_test_support import mint_session_token
from test_portal_workflows import portal_case, resident_request_case, post, action, resource
from test_r4_billing_issue_integration import _policy, _period, _run, _key

isolated = pytest.mark.skipif(os.getenv('GREENCITY_ISOLATED_SECURITY_TESTS') != '1', reason='Disposable PostgreSQL runner required')


@pytest.fixture
def concurrent_case(monkeypatch):
    """Committed fixture so each API request uses its own PostgreSQL connection."""
    settings = Settings()
    assert os.getenv('GREENCITY_ISOLATED_SECURITY_TESTS') == '1'
    assert settings.app_env == 'test' and settings.sqlalchemy_url().host == '127.0.0.1'
    database = Database(settings)
    monkeypatch.setattr('app.services.portal_finance.business_date', lambda: date(2026, 10, 9))
    try:
        with database.get_session() as session:
            tenant = Tenant(name='Proration concurrent ' + uuid4().hex)
            session.add(tenant); session.flush()
            site = Site(tenant_id=tenant.id, code='PROR-' + uuid4().hex[:8], name='Synthetic', address='Synthetic')
            session.add(site); session.flush()
            building = Building(site_id=site.id, code='B1', name='Synthetic')
            session.add(building); session.flush()
            unit = Unit(building_id=building.id, unit_number='0101', floor=1, area_m2=50, status='occupied')
            person = Person(tenant_id=tenant.id, full_name='Synthetic owner', phone_masked='***', email_masked='owner@example.invalid')
            session.add_all([unit, person]); session.flush()
            staff = Account(tenant_id=tenant.id, username='pror_staff_' + uuid4().hex,
                full_name='Synthetic manager', hashed_password='token-only-test-account')
            resident = Account(tenant_id=tenant.id, username='pror_owner_' + uuid4().hex,
                full_name='Synthetic owner', person_id=person.id, hashed_password='token-only-test-account')
            session.add_all([staff, resident]); session.flush()
            account = BillingAccount(tenant_id=tenant.id, site_id=site.id, building_id=building.id, unit_id=unit.id,
                account_number='PROR-' + uuid4().hex[:8], opened_on=date(2025, 1, 1))
            session.add_all([AccountRole(account_id=staff.id, role='admin', site_id=site.id, building_id=None),
                AccountRole(account_id=staff.id, role='accountant', site_id=site.id, building_id=None),
                AccountRole(account_id=resident.id, role='resident', site_id=site.id, building_id=building.id),
                UnitPersonRelationship(tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                    unit_id=unit.id, person_id=person.id, relationship_type='owner', ownership_ratio=Decimal(1), valid_from=date(2025, 1, 1)),
                account])
            period = AccountingPeriod(tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                period_key='2026-09', period_start=date(2026, 9, 1), period_end=date(2026, 9, 30), status='OPEN')
            session.add(period); session.commit()
        auth = {label: {'Authorization': 'Bearer ' + mint_session_token(database, account.id, settings.auth_secret(),
            claims={'active_site_id': str(site.id)})} for label, account in [('resident', resident), ('cskh', staff), ('accountant', staff)]}
        with TestClient(create_app(settings, database)) as client:
            yield dict(client=client, database=database, settings=settings, tenant=tenant, site=site, sites=[site],
                building=building, buildings=[building], unit=unit, units=[unit], billing_account=account, period=period, auth=auth)
    finally:
        database.close()


@pytest.mark.parametrize('start,end,from_day,to_day,expected', [
    (date(2024, 2, 1), date(2024, 2, 29), date(2024, 2, 20), date(2024, 3, 1), 100000),
    (date(2025, 2, 1), date(2025, 2, 28), date(2025, 2, 1), date(2025, 2, 15), 145000),
    (date(2026, 9, 1), date(2026, 9, 30), date(2026, 8, 1), None, 290000),
    (date(2026, 9, 1), date(2026, 9, 30), date(2026, 10, 1), None, 0),
    (date(2026, 10, 1), date(2026, 10, 31), date(2026, 10, 22), None, 93548),
])
def test_calendar_day_oracles(start, end, from_day, to_day, expected):
    result = calculate_proration(start, end, [{'key': 'source', 'starts_on': from_day, 'ends_on': to_day, 'amount_vnd': 290000}])
    assert result['amount_vnd'] == expected


def test_round_once_across_intervals_and_exact_area_rates():
    result = calculate_proration(date(2026, 9, 1), date(2026, 9, 2), [
        {'key': 'a', 'starts_on': date(2026, 9, 1), 'ends_on': date(2026, 9, 2), 'amount_vnd': 1},
        {'key': 'b', 'starts_on': date(2026, 9, 2), 'ends_on': date(2026, 9, 3), 'amount_vnd': 1}])
    assert result['amount_vnd'] == 1  # Half a dong + half a dong, rather than 1 + 1.
    result = calculate_proration(date(2026, 9, 1), date(2026, 9, 30), [
        {'key': 'old', 'starts_on': date(2026, 9, 1), 'ends_on': date(2026, 9, 16), 'quantity': Decimal('80.25'), 'amount_vnd': 12000},
        {'key': 'new', 'starts_on': date(2026, 9, 16), 'ends_on': date(2026, 10, 1), 'quantity': Decimal('80.25'), 'amount_vnd': 13000}])
    assert result['amount_vnd'] == 1_003_125
    assert sum(row['amount_vnd'] for row in result['segments']) == 1_003_125


def test_overlap_fails_closed_and_vietnam_business_date(monkeypatch):
    with pytest.raises(ValueError, match='Overlapping'):
        calculate_proration(date(2026, 9, 1), date(2026, 9, 30), [
            {'key': 'a', 'starts_on': date(2026, 9, 1), 'ends_on': date(2026, 9, 15), 'amount_vnd': 1000},
            {'key': 'b', 'starts_on': date(2026, 9, 14), 'amount_vnd': 1000}])
    from app.services import portal_finance
    monkeypatch.setattr(portal_finance, 'utc_now', lambda: datetime(2026, 10, 8, 17, 30, tzinfo=UTC))
    assert portal_finance.business_date() == date(2026, 10, 9)


def new_portal_case(case, monkeypatch):
    case = dict(case)
    monkeypatch.setattr('app.services.portal_finance.business_date', lambda: date(2026, 10, 9))
    with case['database'].get_session() as session:
        unit = Unit(building_id=case['building'].id, unit_number='PROR-' + uuid4().hex[:8], floor=1, area_m2=50, status='occupied')
        session.add(unit); session.flush()
        session.add(UnitPersonRelationship(tenant_id=case['tenant'].id, site_id=case['site'].id,
            building_id=case['building'].id, unit_id=unit.id, person_id=case['residents']['resident'][1].id,
            relationship_type='owner', ownership_ratio=Decimal(1), valid_from=date(2025, 1, 1)))
        account = BillingAccount(tenant_id=case['tenant'].id, site_id=case['site'].id,
            building_id=case['building'].id, unit_id=unit.id, account_number='PROR-' + uuid4().hex[:10], opened_on=date(2025, 1, 1))
        period = AccountingPeriod(tenant_id=case['tenant'].id, site_id=case['site'].id,
            building_id=case['building'].id, period_key='PROR-' + uuid4().hex[:8],
            period_start=date(2026, 9, 1), period_end=date(2026, 9, 30), status='OPEN')
        session.add_all([account, period]); session.commit()
    return {**case, 'unit': unit, 'period': period}


def enroll(case, *, recurring=True, effective_on='2026-09-01'):
    catalog = resource(case, 'SERVICE')
    updated = action(case, f"/resources/{catalog['id']}/actions", catalog, 'UPDATE', data={
        'fee_vnd': 300000, 'policy': {'recurring': recurring, 'rounding_unit_vnd': 1}})
    assert updated.status_code == 200, updated.text
    row = post(case, '/enrollments', {'unit_id': str(case['unit'].id), 'resource_id': catalog['id']}).json()
    with case['database'].get_session() as session:
        session.get(ServiceEnrollment, UUID(row['id'])).created_at = datetime(2026, 9, 1, tzinfo=UTC)
        session.commit()
    approved = action(case, f"/enrollments/{row['id']}/actions", row, 'APPROVE', data={'effective_on': effective_on})
    assert approved.status_code == 200, approved.text
    return approved.json()


def source_for(case, enrollment):
    rows = case['client'].get('/api/v1/portal/fee-sources', params={'unit_id': str(case['unit'].id)}, headers=case['auth']['resident']).json()['items']
    return next(row for row in rows if row['source_id'] == enrollment['id'])


def preview(case, source, actor='resident'):
    return case['client'].get(f"/api/v1/portal/fee-sources/{source['id']}/preview",
        params={'period_id': str(case['period'].id)}, headers=case['auth'][actor])


@isolated
def test_service_pause_resume_end_preview_post_and_replay(portal_case, monkeypatch):
    case = new_portal_case(portal_case, monkeypatch); row = enroll(case)
    for name, day in [('PAUSE', '2026-09-11'), ('RESUME', '2026-09-21'), ('END', '2026-10-01')]:
        response = action(case, f"/enrollments/{row['id']}/actions", row, name, 'resident', {'effective_on': day})
        assert response.status_code == 200, response.text
        row = response.json()
    source = source_for(case, row)
    assert source['status'] == 'ENDED' and len(source['intervals']) == 2
    before = preview(case, source)
    assert before.status_code == 200, before.text
    result = before.json()
    assert result['calculation']['active_days'] == 20
    assert result['calculation']['amount_vnd'] == 200000
    body = {'period_id': str(case['period'].id), 'expected_version': source['version'], 'calculation_hash': result['calculation_hash']}
    denied = post(case, f"/fee-sources/{source['id']}/post", body, 'resident')
    assert denied.status_code == 403
    stale = post(case, f"/fee-sources/{source['id']}/post", {**body, 'calculation_hash': '0' * 64}, 'cskh')
    assert stale.status_code == 409 and stale.json()['error']['code'] == 'ERR-FEE-PREVIEW-STALE'
    key = 'proration-' + uuid4().hex
    first = post(case, f"/fee-sources/{source['id']}/post", body, 'cskh', key)
    assert first.status_code == 200, first.text
    assert post(case, f"/fee-sources/{source['id']}/post", body, 'cskh', key).json() == first.json()
    finish_review(case, first.json(), maker='cskh')
    with case['database'].get_session() as session:
        invoices = session.scalars(select(BillingInvoice).join(BillingAccount, BillingAccount.id == BillingInvoice.billing_account_id)
            .where(BillingAccount.unit_id == case['unit'].id)).all()
        assert len(invoices) == 1 and invoices[0].total_vnd == 200000
        line = session.scalar(select(BillingInvoiceItem).where(BillingInvoiceItem.billing_invoice_id == invoices[0].id))
        assert line.calculation_snapshot == result['calculation']
        version = session.get(FeePolicyVersion, line.fee_policy_version_id)
        assert version.effective_to == date(2026, 10, 1) and version.rounding_unit_vnd == line.rounding_unit_vnd_snapshot
        entries = session.scalars(select(ArLedgerEntry).where(ArLedgerEntry.source_id == invoices[0].id)).all()
        assert len(entries) == 1 and entries[0].debit_vnd == 200000
    assert preview(case, source).json()['posted_invoice_id'] is not None


@isolated
def test_zero_accrual_does_not_create_invoice_or_ledger(portal_case, monkeypatch):
    case = new_portal_case(portal_case, monkeypatch); row = enroll(case)
    paused = action(case, f"/enrollments/{row['id']}/actions", row, 'PAUSE', 'resident', {'effective_on': '2026-09-01'})
    assert paused.status_code == 200, paused.text
    source = source_for(case, paused.json()); details = preview(case, source).json()
    assert details['calculation']['amount_vnd'] == 0 and details['calculation']['active_days'] == 0
    response = post(case, f"/fee-sources/{source['id']}/post", {'period_id': str(case['period'].id),
        'expected_version': source['version'], 'calculation_hash': details['calculation_hash']}, 'cskh')
    assert response.status_code == 409 and response.json()['error']['code'] == 'ERR-FEE-NO-ACCRUAL'
    with case['database'].get_session() as session:
        assert session.scalar(select(func.count(BillingInvoice.id)).where(BillingInvoice.accounting_period_id == case['period'].id)) == 0
        assert session.scalar(select(func.count(ArLedgerEntry.id)).where(ArLedgerEntry.accounting_period_id == case['period'].id)) == 0


@isolated
def test_one_time_fee_is_not_prorated_or_posted_in_two_periods(portal_case, monkeypatch):
    case = new_portal_case(portal_case, monkeypatch); row = enroll(case, recurring=False, effective_on='2026-09-16')
    source = source_for(case, row); details = preview(case, source).json()
    assert source['intervals'] == [] and details['calculation']['method'] == 'ONE_TIME'
    assert details['calculation']['amount_vnd'] == 300000
    response = post(case, f"/fee-sources/{source['id']}/post", {'period_id': str(case['period'].id),
        'expected_version': source['version'], 'calculation_hash': details['calculation_hash']}, 'cskh')
    assert response.status_code == 200, response.text
    finish_review(case, response.json(), maker='cskh')
    source = source_for(case, row)
    with case['database'].get_session() as session:
        period = AccountingPeriod(tenant_id=case['tenant'].id, site_id=case['site'].id, building_id=case['building'].id,
            period_key='ONCE-' + uuid4().hex[:8], period_start=date(2026, 10, 1), period_end=date(2026, 10, 31), status='OPEN')
        session.add(period); session.commit()
    response = post(case, f"/fee-sources/{source['id']}/post", {'period_id': str(period.id),
        'expected_version': source['version']}, 'cskh')
    assert response.status_code == 409 and response.json()['error']['code'] == 'ERR-FEE-ALREADY-POSTED'


@isolated
def test_posted_period_and_invalid_dates_do_not_mutate_service(portal_case, monkeypatch):
    case = new_portal_case(portal_case, monkeypatch); row = enroll(case); source = source_for(case, row)
    details = preview(case, source).json()
    posted = post(case, f"/fee-sources/{source['id']}/post", {'period_id': str(case['period'].id),
        'expected_version': source['version'], 'calculation_hash': details['calculation_hash']}, 'cskh')
    assert posted.status_code == 200, posted.text
    finish_review(case, posted.json(), maker='cskh')
    for day, code in [('2026-09-11', 409), ('2026-10-10', 422), ('2026-08-01', 409)]:
        response = action(case, f"/enrollments/{row['id']}/actions", row, 'PAUSE', 'resident', {'effective_on': day})
        assert response.status_code == code, response.text
    with case['database'].get_session() as session:
        assert session.get(ServiceEnrollment, UUID(row['id'])).status == 'ACTIVE'
        assert session.get(PortalFeeSource, UUID(source['id'])).status == 'ACTIVE'
        assert session.scalar(select(func.count(PortalFeeInterval.id)).where(PortalFeeInterval.fee_source_id == source['id'])) == 1


@isolated
def test_same_day_pause_resume_keeps_one_open_interval(portal_case, monkeypatch):
    case = new_portal_case(portal_case, monkeypatch); row = enroll(case)
    for name, day in [('PAUSE', '2026-09-05'), ('RESUME', '2026-09-05'), ('PAUSE', '2026-09-06'), ('RESUME', '2026-09-06'), ('END', '2026-09-11')]:
        response = action(case, f"/enrollments/{row['id']}/actions", row, name, 'resident', {'effective_on': day})
        assert response.status_code == 200, response.text
        row = response.json()
    result = preview(case, source_for(case, row)).json()['calculation']
    assert result['active_days'] == 10 and result['amount_vnd'] == 100000


@isolated
def test_posting_racing_pause_has_one_consistent_outcome(concurrent_case):
    case = concurrent_case; row = enroll(case); source = source_for(case, row)
    details = preview(case, source).json(); barrier = Barrier(2)
    review = post(case, f"/fee-sources/{source['id']}/post", {'period_id': str(case['period'].id), 'expected_version': source['version'], 'calculation_hash': details['calculation_hash']}, 'cskh').json()
    review = action(case, f"/finance/reviews/{review['id']}/actions", review, 'SUBMIT', 'cskh').json()
    case['auth']['checker'] = checker_headers(case)
    review = action(case, f"/finance/reviews/{review['id']}/actions", review, 'APPROVE', 'checker').json()
    def do_post():
        with TestClient(case['client'].app) as client:
            barrier.wait(timeout=10)
            return action({**case, 'client': client}, f"/finance/reviews/{review['id']}/actions", review, 'ISSUE', 'cskh')
    def do_pause():
        with TestClient(case['client'].app) as client:
            barrier.wait(timeout=10)
            return action({**case, 'client': client}, f"/enrollments/{row['id']}/actions", row, 'PAUSE', 'resident', {'effective_on': '2026-09-11'})
    with ThreadPoolExecutor(max_workers=2) as pool:
        posting = pool.submit(do_post); pausing = pool.submit(do_pause)
        results = [posting.result(timeout=30), pausing.result(timeout=30)]
    assert sorted(response.status_code for response in results) == [200, 409]
    with case['database'].get_session() as session:
        source_row = session.get(PortalFeeSource, UUID(source['id']))
        invoices = session.scalars(select(BillingInvoice).join(BillingAccount, BillingAccount.id == BillingInvoice.billing_account_id)
            .where(BillingAccount.unit_id == case['unit'].id)).all()
        if source_row.status == 'ACTIVE':
            assert len(invoices) == 1 and invoices[0].total_vnd == 300000
        else:
            assert source_row.status == 'PAUSED' and invoices == []
    if results[1].status_code == 200:
        assert preview(case, source).json()['calculation']['amount_vnd'] == 100000


@isolated
def test_common_run_and_portal_post_serialize_without_deadlock(concurrent_case, monkeypatch):
    from app.api import billing
    case = concurrent_case; row = enroll(case); source = source_for(case, row)
    details = preview(case, source).json()
    policy = _policy(case, effective_from='2026-09-01', rate=12000)
    common_locked = Event(); portal_ready = Event()
    original = billing._prepare_review
    def hold_common_run(*args, **kwargs):
        common_locked.set()
        assert portal_ready.wait(timeout=10)
        return original(*args, **kwargs)
    def observe_portal_period(connection, cursor, statement, parameters, context, executemany):
        if common_locked.is_set() and 'accounting_periods' in statement and 'FOR UPDATE' in statement:
            portal_ready.set()
    monkeypatch.setattr(billing, '_prepare_review', hold_common_run)
    event.listen(case['database'].engine, 'before_cursor_execute', observe_portal_period)
    def common_run():
        with TestClient(case['client'].app) as client:
            return _run({**case, 'client': client}, str(case['period'].id), policy['versions'][0]['id'])
    def portal_post():
        assert common_locked.wait(timeout=10)
        with TestClient(case['client'].app) as client:
            return post({**case, 'client': client}, f"/fee-sources/{source['id']}/post",
                {'period_id': str(case['period'].id), 'expected_version': source['version'],
                 'calculation_hash': details['calculation_hash']}, 'cskh')
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            run = pool.submit(common_run); posting = pool.submit(portal_post)
            common_result = run.result(timeout=30); portal_result = posting.result(timeout=30)
        assert common_result.status_code == 201 and common_result.json()['status'] == 'POSTED', common_result.text
        assert portal_result.status_code == 200, portal_result.text
        finish_review(case, portal_result.json(), maker='cskh')
        with case['database'].get_session() as session:
            invoices = session.scalars(select(BillingInvoice).where(BillingInvoice.accounting_period_id == case['period'].id)).all()
            assert sorted(invoice.total_vnd for invoice in invoices) == [300000, 600000]
            assert session.scalar(select(func.sum(ArLedgerEntry.debit_vnd)).where(
                ArLedgerEntry.accounting_period_id == case['period'].id)) == 900000
    finally:
        event.remove(case['database'].engine, 'before_cursor_execute', observe_portal_period)


@isolated
def test_parking_pause_policy_stops_only_approved_fee_source(portal_case, monkeypatch):
    case = new_portal_case(portal_case, monkeypatch)
    park = resource(case, 'PARKING')
    updated = action(case, f"/resources/{park['id']}/actions", park, 'UPDATE', data={
        'fee_vnd': 300000, 'policy': {**park['policy'], 'charge_when_paused': False}})
    assert updated.status_code == 200
    monkeypatch.setattr('app.services.portal_finance.business_date', lambda: date(2026, 9, 1))
    row = post(case, '/vehicles', {'unit_id': str(case['unit'].id), 'resource_id': park['id'],
        'plate': 'PROR-' + uuid4().hex[:8], 'vehicle_type': 'CAR'}).json()
    response = action(case, f"/vehicles/{row['id']}/actions", row, 'APPROVE')
    assert response.status_code == 200, response.text
    row = response.json()
    monkeypatch.setattr('app.services.portal_finance.business_date', lambda: date(2026, 10, 9))
    for name, day in [('PAUSE', '2026-09-11'), ('RESUME', '2026-09-21')]:
        response = action(case, f"/vehicles/{row['id']}/actions", row, name, 'resident', {'effective_on': day})
        assert response.status_code == 200, response.text
        row = response.json()
    assert preview(case, source_for(case, row)).json()['calculation']['amount_vnd'] == 200000


@isolated
def test_area_policy_changes_mid_period_preserve_rate_snapshots(concurrent_case):
    case = concurrent_case
    policy = _policy(case, effective_from='2027-03-01', rate=12000)
    published = case['client'].post(f"/api/v1/billing/fee-policies/{policy['id']}/versions", headers=_key(case, 'version'),
        json={'effective_from': '2027-03-16', 'unit_rate_vnd': 13000, 'rounding_unit_vnd': 1})
    assert published.status_code == 201, published.text
    from test_r4_billing_issue_integration import publish_policy_version
    publish_policy_version(case, published.json()['id'])
    period = _period(case, key='2027-03', start='2027-03-01', end='2027-03-30', cutoff='2027-03-30T00:00:00Z')
    with case['database'].get_session() as session:
        session.get(Unit, case['units'][0].id).area_m2 = Decimal('80.25')
        session.commit()
    response = _run(case, period['id'], policy['versions'][0]['id'])
    assert response.status_code == 201 and response.json()['status'] == 'POSTED', response.text
    with case['database'].get_session() as session:
        invoice = session.scalar(select(BillingInvoice).where(BillingInvoice.accounting_period_id == period['id'],
            BillingInvoice.billing_account_id == case['billing_account'].id))
        assert invoice.total_vnd == 1_003_125
        lines = session.scalars(select(BillingInvoiceItem).where(BillingInvoiceItem.billing_invoice_id == invoice.id)
            .order_by(BillingInvoiceItem.line_number)).all()
        assert [(line.unit_rate_vnd_snapshot, line.amount_vnd) for line in lines] == [(12000, 481500), (13000, 521625)]
        assert all(line.calculation_snapshot['active_days'] == 30 for line in lines)
    blocked = case['client'].post(f"/api/v1/billing/fee-policies/{policy['id']}/versions", headers=_key(case, 'retroactive'),
        json={'effective_from': '2027-03-20', 'unit_rate_vnd': 1, 'rounding_unit_vnd': 1})
    assert blocked.status_code == 409


@isolated
def test_account_opened_and_closed_mid_period_charges_only_active_days(concurrent_case):
    case = concurrent_case
    with case['database'].get_session() as session:
        unit = Unit(building_id=case['buildings'][0].id, unit_number='PROR-' + uuid4().hex[:8], floor=1, area_m2=1, status='occupied')
        session.add(unit); session.flush()
        owner = Person(tenant_id=case['tenant'].id, full_name='Synthetic prorated owner',
                       phone_masked='[SYNTHETIC]', email_masked='[SYNTHETIC]')
        session.add(owner); session.flush()
        session.add(UnitPersonRelationship(tenant_id=case['tenant'].id, site_id=case['sites'][0].id,
            building_id=unit.building_id, unit_id=unit.id, person_id=owner.id,
            relationship_type='owner', ownership_ratio=Decimal(1), valid_from=date(2020, 1, 1)))
        account = BillingAccount(tenant_id=case['tenant'].id, site_id=case['sites'][0].id,
            building_id=case['buildings'][0].id, unit_id=unit.id, account_number='PROR-' + uuid4().hex[:8],
            opened_on=date(2027, 4, 11), closed_on=date(2027, 4, 21), status='CLOSED')
        session.add(account); session.commit()
    policy = _policy(case, effective_from='2027-04-01', rate=300000)
    period = _period(case, key='2027-04', start='2027-04-01', end='2027-04-30', cutoff='2027-04-30T00:00:00Z')
    result = _run(case, period['id'], policy['versions'][0]['id'])
    assert result.status_code == 201 and result.json()['status'] == 'POSTED', result.text
    with case['database'].get_session() as session:
        invoice = session.scalar(select(BillingInvoice).where(BillingInvoice.billing_account_id == account.id,
            BillingInvoice.accounting_period_id == period['id']))
        assert invoice.total_vnd == 100000
