from billing_review_support import finish_review
"""Automatic tests on a disposable database, without browser/provider/device traffic."""
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4
import os
import secrets
import pytest
from pydantic import SecretStr
from sqlalchemy import func, select
from app.core.exceptions import AppError
from app.models.account import AccountRole
from app.models.billing import AccountingPeriod, BillingAccount, BillingInvoice, Payment, ArLedgerEntry
from app.models.resident_portal import PortalFeeSource, PortalPaymentIntent
from app.schemas.resident_portal import RecoveryVerify
from app.services.resident_portal import available_booking_capacity, deposit_movement
from app.services import vnpay
from test_r6_resident_service_requests_integration import resident_request_case


def test_interval_peak_and_adjacent_bookings():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    assert available_booking_capacity(2, [(start, start + timedelta(hours=1), 1),
        (start + timedelta(hours=1), start + timedelta(hours=2), 1)], start, start + timedelta(hours=2)) == 1
    assert available_booking_capacity(2, [(start, start + timedelta(hours=2), 2)], start, start + timedelta(hours=1)) == 0


def test_deposit_cannot_deduct_released_or_refund_unreleased_funds():
    row = SimpleNamespace(balance_vnd=100, refundable_vnd=0, required_vnd=100, status='HELD', version=1)
    deposit_movement(row, 'RELEASE', 60)
    with pytest.raises(AppError):
        deposit_movement(row, 'DEDUCT', 41)
    with pytest.raises(AppError):
        deposit_movement(row, 'REFUND', 61)
    deposit_movement(row, 'REFUND', 60)
    assert row.balance_vnd == 40 and row.refundable_vnd == 0


def test_vnpay_signing_tamper_and_email_injection():
    params = {'vnp_TxnRef': 'synthetic', 'vnp_Amount': '12300', 'vnp_OrderInfo': 'Hoa don A B'}
    key = secrets.token_urlsafe(32)
    params['vnp_SecureHash'] = vnpay.sign(params, key)
    assert vnpay.verify(params, key)
    assert not vnpay.verify({**params, 'vnp_Amount': '12400'}, key)
    assert vnpay.canonical_parameters(params).endswith('vnp_TxnRef=synthetic')
    for email in ('a@example.invalid\r\nBcc:b@example.invalid', 'a,b@example.invalid', 'a;b@example.invalid'):
        with pytest.raises(ValueError):
            RecoveryVerify(reference='synthetic proof', current_password='synthetic', verified_email=email)
    assert RecoveryVerify(reference='synthetic proof', current_password='synthetic', verified_email='person@example.invalid').verified_email == 'person@example.invalid'


isolated = pytest.mark.skipif(os.getenv('GREENCITY_ISOLATED_SECURITY_TESTS') != '1', reason='Disposable PostgreSQL runner required')


@pytest.fixture
def portal_case(resident_request_case):
    case = resident_request_case
    with case['database'].get_session() as session:
        role = session.scalar(select(AccountRole.id).where(AccountRole.account_id == case['staff'].id, AccountRole.role == 'admin'))
        if not role:
            session.add(AccountRole(account_id=case['staff'].id, role='admin', site_id=case['site'].id, building_id=None))
            session.commit()
    return case


def post(case, path, body, actor='resident', key=None):
    return case['client'].post('/api/v1/portal' + path, json=body,
        headers={**case['auth'][actor], 'Idempotency-Key': key or 'portal-' + uuid4().hex})


def action(case, path, row, name, actor='cskh', data=None, key=None):
    return post(case, path, {'action': name, 'expected_version': row['version'], 'reason': 'Synthetic workflow decision', 'data': data or {}}, actor, key)


def resource(case, kind, capacity=1, deposit=0):
    policy = {'quota_per_unit': 1, 'offer_minutes': 10, 'credential_days': 30} if kind == 'PARKING' else {'slot_minutes': 30, 'max_duration_minutes': 120, 'cancel_before_minutes': 60, 'cancel_fee_vnd': 100, 'no_show_fee_vnd': 100} if kind == 'FACILITY' else {'recurring': True}
    response = post(case, '/resources', {'kind': kind, 'building_id': str(case['building'].id), 'name': 'Synthetic ' + kind,
        'capacity': capacity, 'fee_vnd': 1000, 'deposit_vnd': deposit, 'description': '', 'policy': policy}, 'cskh')
    assert response.status_code == 201, response.text
    return response.json()


@isolated
def test_dossier_scope_replay_approval_and_proof_download(portal_case):
    case = portal_case
    body = {'unit_id': str(case['unit'].id), 'kind': 'PROFILE_CHANGE', 'title': 'Update synthetic profile', 'data': {'full_name': 'Synthetic updated resident'}, 'valid_from': str(date.today())}
    denied = post(case, '/dossiers', {**body, 'unit_id': str(case['other_unit'].id)})
    assert denied.status_code == 404
    key = 'dossier-' + uuid4().hex
    created = post(case, '/dossiers', body, key=key)
    assert created.status_code == 201, created.text
    row = created.json()
    replay = post(case, '/dossiers', body, key=key)
    assert replay.json()['id'] == row['id']
    assert action(case, f"/dossiers/{row['id']}/actions", row, 'APPROVE', actor='resident').status_code == 403
    approved = action(case, f"/dossiers/{row['id']}/actions", row, 'APPROVE')
    assert approved.status_code == 200, approved.text
    assert case['client'].get('/api/v1/portal/profile', headers=case['auth']['resident']).json()['person']['full_name'] == body['data']['full_name']
    stale = action(case, f"/dossiers/{row['id']}/actions", row, 'REJECT')
    assert stale.status_code == 409
    uploaded = case['client'].post('/api/v1/portal/documents', params={'unit_id': str(case['unit'].id), 'title': 'Synthetic proof'}, content=b'%PDF-1.4\nsynthetic\n%%EOF',
        headers={**case['auth']['resident'], 'Idempotency-Key': 'proof-' + uuid4().hex, 'Content-Type': 'application/pdf', 'X-File-Name': 'proof.pdf'})
    assert uploaded.status_code == 201, uploaded.text
    identifier = uploaded.json()['id']
    link = case['client'].get(f'/api/v1/portal/documents/{identifier}/signed-link', params={'unit_id': str(case['unit'].id)}, headers=case['auth']['resident'])
    assert link.status_code == 200, link.text
    foreign = case['client'].get(f'/api/v1/portal/documents/{identifier}/download', params={'token': link.json()['token'], 'unit_id': str(case['other_unit'].id)}, headers=case['auth']['resident'])
    assert foreign.status_code == 404


@isolated
def test_vehicle_quota_and_booking_capacity_deposit(portal_case):
    case = portal_case; park = resource(case, 'PARKING')
    row = post(case, '/vehicles', {'unit_id': str(case['unit'].id), 'resource_id': park['id'], 'plate': 'SYN-' + uuid4().hex[:8], 'vehicle_type': 'CAR'}).json()
    approved = action(case, f"/vehicles/{row['id']}/actions", row, 'APPROVE')
    assert approved.status_code == 200, approved.text
    assert approved.json()['status'] == 'ACTIVE'
    second = post(case, '/vehicles', {'unit_id': str(case['unit'].id), 'resource_id': park['id'], 'plate': 'SYN-' + uuid4().hex[:8], 'vehicle_type': 'CAR'}).json()
    assert action(case, f"/vehicles/{second['id']}/actions", second, 'APPROVE').json()['status'] == 'WAITING'
    card = action(case, f"/vehicles/{row['id']}/credential", approved.json(), 'ISSUE')
    assert card.status_code == 201, card.text
    assert action(case, f"/credentials/{card.json()['id']}/actions", card.json(), 'LOST', 'resident').json()['status'] == 'LOST'
    facility = resource(case, 'FACILITY', deposit=500)
    start = datetime.now(UTC) + timedelta(days=1)
    body = {'unit_id': str(case['unit'].id), 'resource_id': facility['id'], 'starts_at': start.isoformat(), 'ends_at': (start + timedelta(hours=1)).isoformat(), 'quantity': 1}
    booking = post(case, '/bookings', body)
    assert booking.status_code == 201, booking.text
    assert booking.json()['status'] == 'AWAITING_DEPOSIT'
    assert post(case, '/bookings', body).json()['status'] == 'WAITING'
    assert action(case, f"/bookings/{booking.json()['id']}/actions", booking.json(), 'CONFIRM', 'resident').status_code == 409
    with case['database'].get_session() as session:
        assert session.scalar(select(PortalFeeSource.id).where(PortalFeeSource.source_kind == 'BOOKING', PortalFeeSource.source_id == booking.json()['id'])) is None


@isolated
@pytest.mark.parametrize('refund_status', ['00', '09'])
def test_supplemental_fee_signed_ipn_credit_and_refund(portal_case, monkeypatch, refund_status):
    from decimal import Decimal
    from app.models.unit import Unit
    from app.models.person import UnitPersonRelationship
    case = dict(portal_case)
    with case['database'].get_session() as session:
        unit = Unit(building_id=case['building'].id, unit_number='ZZ-FIN-' + uuid4().hex[:8], floor=1, area_m2=50, status='occupied')
        session.add(unit); session.flush()
        session.add(UnitPersonRelationship(tenant_id=case['tenant'].id, site_id=case['site'].id,
            building_id=case['building'].id, unit_id=unit.id, person_id=case['residents']['resident'][1].id,
            relationship_type='owner', ownership_ratio=Decimal('1'), valid_from=date(2025, 1, 1)))
        session.commit()
    case['unit'] = unit
    service = resource(case, 'SERVICE')
    registration = post(case, '/enrollments', {'unit_id': str(case['unit'].id), 'resource_id': service['id']})
    assert registration.status_code == 201, registration.text
    approved = action(case, f"/enrollments/{registration.json()['id']}/actions", registration.json(), 'APPROVE')
    assert approved.status_code == 200, approved.text
    with case['database'].get_session() as session:
        account = BillingAccount(tenant_id=case['tenant'].id, site_id=case['site'].id, building_id=case['building'].id, unit_id=case['unit'].id, account_number='SYN-' + uuid4().hex, opened_on=date.today())
        today = date.today()
        period = session.scalar(select(AccountingPeriod).where(AccountingPeriod.tenant_id == case['tenant'].id,
            AccountingPeriod.building_id == case['building'].id, AccountingPeriod.period_start == today,
            AccountingPeriod.period_end == today, AccountingPeriod.status == 'OPEN'))
        if period is None:
            period = AccountingPeriod(tenant_id=case['tenant'].id, site_id=case['site'].id, building_id=case['building'].id,
                period_key='SYN-' + uuid4().hex[:8], period_start=today, period_end=today, status='OPEN')
        session.add_all((account, period)); session.commit()
        source = session.scalar(select(PortalFeeSource).where(PortalFeeSource.source_kind == 'SERVICE', PortalFeeSource.source_id == registration.json()['id']))
        source_id, source_version, period_id = str(source.id), source.version, str(period.id)
    posted = post(case, f'/fee-sources/{source_id}/post', {'period_id': period_id, 'expected_version': source_version}, 'cskh')
    assert posted.status_code == 200, posted.text
    finish_review(case, posted.json(), maker='cskh')
    invoice = case['client'].get('/api/v1/portal/invoices', params={'unit_id': str(case['unit'].id)}, headers=case['auth']['resident']).json()['items'][0]
    settings = case['settings']; settings.vnpay_enabled = True; settings.vnpay_tmn_code = 'SYNTHETC'
    settings.vnpay_hash_secret = SecretStr(secrets.token_urlsafe(32)); settings.vnpay_tenant_id = case['tenant'].id
    settings.vnpay_service_account_id = case['staff'].id; settings.vnpay_return_url = 'http://localhost/api/v1/portal/payments/vnpay/return'
    intent = post(case, '/payment-intents', {'unit_id': str(case['unit'].id), 'invoice_id': invoice['id']})
    assert intent.status_code == 201, intent.text
    params = {'vnp_TmnCode': settings.vnpay_tmn_code, 'vnp_TxnRef': intent.json()['reference'], 'vnp_Amount': '100000',
        'vnp_ResponseCode': '00', 'vnp_TransactionStatus': '00', 'vnp_TransactionNo': str(int(uuid4().hex[:10], 16)), 'vnp_PayDate': datetime.now(vnpay.VN_TIMEZONE).strftime('%Y%m%d%H%M%S')}
    url = '/api/v1/portal/payments/vnpay/ipn'
    assert case['client'].get(url, params=params).json()['RspCode'] == '97'
    params['vnp_SecureHash'] = vnpay.sign(params, settings.vnpay_hash_secret.get_secret_value())
    first = case['client'].get(url, params=params)
    assert first.json()['RspCode'] == '00', first.text
    assert case['client'].get(url, params=params).json()['RspCode'] == '02'
    with case['database'].get_session() as session:
        assert session.scalar(select(func.count(Payment.id)).where(Payment.source_reference == 'VNPAY:' + params['vnp_TransactionNo'])) == 1
        assert session.get(BillingInvoice, invoice['id']).outstanding_vnd == 0
    from app.models.account import Account
    from app.core.security import hash_password
    from auth_test_support import mint_session_token
    with case['database'].get_session() as session:
        checker = Account(tenant_id=case['tenant'].id, username='synthetic_checker_' + uuid4().hex,
            full_name='Synthetic checker', hashed_password=hash_password(secrets.token_urlsafe(24)))
        session.add(checker); session.flush()
        session.add(AccountRole(account_id=checker.id, role='accountant', site_id=case['site'].id, building_id=None)); session.commit()
    checker_header = {'Authorization': 'Bearer ' + mint_session_token(case['database'], checker.id, settings.auth_secret(), claims={'active_site_id': str(case['site'].id)})}
    case['auth']['checker'] = checker_header
    credit = post(case, '/adjustments', {'unit_id': str(case['unit'].id), 'kind': 'CREDIT', 'invoice_id': invoice['id'], 'amount_vnd': 1000, 'reason': 'Synthetic approved cancellation'}, 'cskh')
    assert credit.status_code == 201, credit.text
    assert action(case, f"/adjustments/{credit.json()['id']}/actions", credit.json(), 'APPROVE', data={'period_id': period_id}).status_code == 403
    credited = action(case, f"/adjustments/{credit.json()['id']}/actions", credit.json(), 'APPROVE', 'checker', {'period_id': period_id})
    assert credited.status_code == 200, credited.text
    refund = post(case, '/adjustments', {'unit_id': str(case['unit'].id), 'kind': 'REFUND', 'invoice_id': invoice['id'],
        'payment_intent_id': intent.json()['id'], 'amount_vnd': 1000, 'reason': 'Synthetic refund decision'}, 'cskh')
    assert refund.status_code == 201, refund.text
    refund = action(case, f"/adjustments/{refund.json()['id']}/actions", refund.json(), 'APPROVE', 'checker', {'period_id': period_id})
    assert refund.status_code == 200, refund.text
    calls = []
    def provider(config, payload):
        calls.append(payload)
        response = {'vnp_ResponseId': uuid4().hex, 'vnp_Command': payload['vnp_Command'], 'vnp_ResponseCode': '00',
            'vnp_Message': 'Synthetic fixture', 'vnp_TmnCode': settings.vnpay_tmn_code, 'vnp_TxnRef': intent.json()['reference'],
            'vnp_Amount': '100000', 'vnp_BankCode': 'SYN', 'vnp_PayDate': params['vnp_PayDate'], 'vnp_TransactionNo': '912345678',
            'vnp_TransactionType': '02', 'vnp_TransactionStatus': '05' if payload['vnp_Command'] == 'refund' else refund_status, 'vnp_OrderInfo': 'Synthetic fixture'}
        fields = ['vnp_ResponseId', 'vnp_Command', 'vnp_ResponseCode', 'vnp_Message', 'vnp_TmnCode', 'vnp_TxnRef', 'vnp_Amount',
            'vnp_BankCode', 'vnp_PayDate', 'vnp_TransactionNo', 'vnp_TransactionType', 'vnp_TransactionStatus', 'vnp_OrderInfo']
        if payload['vnp_Command'] == 'querydr':
            fields += ['vnp_PromotionCode', 'vnp_PromotionAmount']
        response['vnp_SecureHash'] = vnpay.pipe_sign(response, fields, settings.vnpay_hash_secret.get_secret_value())
        return response
    monkeypatch.setattr(vnpay, 'call_transaction', provider)
    pending = action(case, f"/adjustments/{refund.json()['id']}/provider", refund.json(), 'SEND')
    assert pending.status_code == 200, pending.text
    assert pending.json()['status'] == 'RECONCILIATION'
    duplicate = action(case, f"/adjustments/{refund.json()['id']}/provider", refund.json(), 'SEND')
    assert duplicate.status_code == 200 and len(calls) == 1
    assert action(case, f"/adjustments/{refund.json()['id']}/actions", pending.json(), 'RELEASE_REFUND', 'checker', {'period_id': period_id}).status_code == 409
    completed = action(case, f"/adjustments/{refund.json()['id']}/provider", pending.json(), 'CHECK')
    assert completed.status_code == 200, completed.text
    assert len(calls) == 2
    if refund_status == '00':
        assert completed.json()['status'] == 'COMPLETED'
    else:
        assert completed.json()['status'] == 'RECONCILIATION'
        assert action(case, f"/adjustments/{refund.json()['id']}/actions", completed.json(), 'RELEASE_REFUND', 'cskh', {'period_id': period_id}).status_code == 403
        released = action(case, f"/adjustments/{refund.json()['id']}/actions", completed.json(), 'RELEASE_REFUND', 'checker', {'period_id': period_id})
        assert released.status_code == 200, released.text
        assert released.json()['status'] == 'REJECTED'
        assert action(case, f"/adjustments/{refund.json()['id']}/actions", released.json(), 'RELEASE_REFUND', 'checker', {'period_id': period_id}).status_code == 409
        with case['database'].get_session() as session:
            assert session.scalar(select(func.sum(ArLedgerEntry.debit_vnd - ArLedgerEntry.credit_vnd)).where(ArLedgerEntry.billing_account_id == account.id)) == -1000


@isolated
def test_recovery_smtp_without_provider_connection(portal_case, monkeypatch):
    case = portal_case; captured = {}
    def deliver(settings, email, request_id, token, expires_at):
        captured.update(request_id=str(request_id), token=token)
    monkeypatch.setattr('app.api.portal_accounts.send_recovery', deliver)
    settings = case['settings']; settings.smtp_enabled = True; settings.smtp_host = 'smtp.example.invalid'; settings.smtp_from_email = 'greencity@example.invalid'
    response = case['client'].post('/api/v1/auth/recovery/request', json={'username': case['residents']['housemate'][0].username})
    assert response.status_code == 200, response.text
    requests = case['client'].get('/api/v1/portal/recovery-requests', headers=case['auth']['cskh']).json()['items']
    selected = next(r for r in requests if r['username'] == case['residents']['housemate'][0].username)
    verified = case['client'].post(f"/api/v1/portal/recovery-requests/{selected['id']}/verify", headers=case['auth']['cskh'],
        json={'reference': 'Synthetic identity evidence', 'current_password': 'invalid', 'verified_email': 'resident@example.invalid'})
    assert verified.status_code == 403
    # Reauthentication logic is exercised above; replace only password verification for synthetic setup.
    monkeypatch.setattr('app.api.portal_accounts.verify_password', lambda *args: True)
    verified = case['client'].post(f"/api/v1/portal/recovery-requests/{selected['id']}/verify", headers=case['auth']['cskh'],
        json={'reference': 'Synthetic identity evidence', 'current_password': 'synthetic', 'verified_email': 'resident@example.invalid'})
    assert verified.status_code == 200, verified.text
    assert 'token' not in verified.json() and captured['request_id'] == selected['id']
    monkeypatch.setattr('app.api.portal_accounts.verify_password', lambda *args: False)
    body = {**captured, 'new_password': secrets.token_urlsafe(24)}
    completed = case['client'].post('/api/v1/auth/recovery/complete', json=body)
    assert completed.status_code == 200, completed.text
    assert case['client'].post('/api/v1/auth/recovery/complete', json=body).status_code == 400


def proof(case, dossier_id):
    response = case['client'].post('/api/v1/portal/documents', params={'unit_id': str(case['unit'].id), 'dossier_id': dossier_id, 'title': 'Synthetic evidence'},
        content=b'%PDF-1.4\nsynthetic\n%%EOF', headers={**case['auth']['resident'], 'Idempotency-Key': 'proof-' + uuid4().hex, 'Content-Type': 'application/pdf', 'X-File-Name': 'synthetic.pdf'})
    assert response.status_code == 201, response.text


@isolated
def test_delegation_reauthorizes_each_permission_and_revocation(portal_case):
    from app.models.account import Account
    from app.models.person import Person
    from app.core.security import hash_password
    from auth_test_support import mint_session_token
    case = portal_case
    with case['database'].get_session() as session:
        person = Person(tenant_id=case['tenant'].id, full_name='Synthetic delegate', phone_masked='***', email_masked='***')
        session.add(person); session.flush()
        account = Account(tenant_id=case['tenant'].id, person_id=person.id, username='synthetic_delegate_' + uuid4().hex,
            full_name='Synthetic delegate', hashed_password=hash_password(secrets.token_urlsafe(24)))
        session.add(account); session.commit()
    created = post(case, '/dossiers', {'unit_id': str(case['unit'].id), 'kind': 'DELEGATION', 'title': 'Synthetic limited delegation',
        'valid_from': str(date.today()), 'valid_to': str(date.today() + timedelta(days=14)),
        'data': {'delegate_username': account.username, 'permissions': ['parking', 'requests']}})
    assert created.status_code == 201, created.text
    proof(case, created.json()['id'])
    approved = action(case, f"/dossiers/{created.json()['id']}/actions", created.json(), 'APPROVE')
    assert approved.status_code == 200, approved.text
    auth = {'Authorization': 'Bearer ' + mint_session_token(case['database'], account.id, case['settings'].auth_secret(), claims={'active_site_id': str(case['site'].id)})}
    profile = case['client'].get('/api/v1/portal/profile', headers=auth)
    assert profile.status_code == 200, profile.text
    assert set(profile.json()['units'][0]['permissions']) == {'parking', 'requests'}
    assert case['client'].get('/api/v1/portal/vehicles', params={'unit_id': str(case['unit'].id)}, headers=auth).status_code == 200
    assert case['client'].get('/api/v1/portal/invoices', params={'unit_id': str(case['unit'].id)}, headers=auth).status_code == 404
    completed = action(case, f"/dossiers/{created.json()['id']}/actions", approved.json(), 'COMPLETE')
    assert completed.status_code == 200, completed.text
    assert case['client'].get('/api/v1/portal/vehicles', params={'unit_id': str(case['unit'].id)}, headers=auth).status_code == 200
    revoked = action(case, f"/dossiers/{created.json()['id']}/actions", completed.json(), 'REVOKE')
    assert revoked.status_code == 200, revoked.text
    assert case['client'].get('/api/v1/portal/vehicles', params={'unit_id': str(case['unit'].id)}, headers=auth).status_code == 404


@isolated
def test_closure_cancels_conflicts_and_worker_notifies_once(portal_case):
    from app.models.resident_portal import FacilityBooking
    from app.models.platform import DomainEvent
    case = portal_case; facility = resource(case, 'FACILITY')
    start = datetime.now(UTC) + timedelta(days=2)
    booking = post(case, '/bookings', {'unit_id': str(case['unit'].id), 'resource_id': facility['id'], 'starts_at': start.isoformat(), 'ends_at': (start + timedelta(hours=1)).isoformat()})
    assert booking.status_code == 201, booking.text
    closure = post(case, f"/resources/{facility['id']}/closures", {'expected_version': facility['version'], 'starts_at': start.isoformat(),
        'ends_at': (start + timedelta(hours=2)).isoformat(), 'reason': 'Synthetic maintenance interval'}, 'cskh')
    assert closure.status_code == 201, closure.text
    with case['database'].get_session() as session:
        assert session.get(FacilityBooking, booking.json()['id']).status == 'CANCELLED'
    conflict = post(case, '/bookings', {'unit_id': str(case['unit'].id), 'resource_id': facility['id'], 'starts_at': start.isoformat(), 'ends_at': (start + timedelta(hours=1)).isoformat()})
    assert conflict.status_code == 409
    content = post(case, '/content', {'unit_id': str(case['unit'].id), 'kind': 'GUIDE', 'title': 'Synthetic notice', 'body': 'Synthetic content', 'publish_at': (datetime.now(UTC) - timedelta(minutes=1)).isoformat()}, 'cskh')
    assert content.status_code == 201, content.text
    draft = content.json()
    assert action(case, f"/content/{draft['id']}/actions", draft, 'PUBLISH').status_code == 409
    submitted = action(case, f"/content/{draft['id']}/actions", draft, 'SUBMIT').json()
    from app.models.account import Account
    from auth_test_support import mint_session_token
    with case['database'].get_session() as session:
        checker = Account(tenant_id=case['tenant'].id, username='content_'+uuid4().hex, full_name='Synthetic checker', hashed_password='token-only-test-account')
        session.add(checker); session.flush()
        session.add(AccountRole(account_id=checker.id, role='admin', site_id=case['site'].id, building_id=None)); session.commit()
    case['auth']['content_checker'] = {'Authorization': 'Bearer ' + mint_session_token(case['database'], checker.id, case['settings'].auth_secret(), claims={'active_site_id': str(case['site'].id)})}
    approved = action(case, f"/content/{draft['id']}/actions", submitted, 'APPROVE', 'content_checker')
    assert approved.status_code == 200, approved.text
    published = action(case, f"/content/{draft['id']}/actions", approved.json(), 'PUBLISH')
    assert published.status_code == 200, published.text
    tick = post(case, '/jobs/tick', {}, 'cskh')
    assert tick.status_code == 200, tick.text
    with case['database'].get_session() as session:
        count = session.scalar(select(func.count(DomainEvent.id)).where(DomainEvent.event_type == 'PortalContentPublished', DomainEvent.resource_id == content.json()['id']))
        assert count > 0
    assert post(case, '/jobs/tick', {}, 'cskh').status_code == 200
    with case['database'].get_session() as session:
        assert session.scalar(select(func.count(DomainEvent.id)).where(DomainEvent.event_type == 'PortalContentPublished', DomainEvent.resource_id == content.json()['id'])) == count


@isolated
def test_partial_transfer_preserves_total_and_owner_history(portal_case):
    from decimal import Decimal
    from app.models.person import UnitPersonRelationship
    from app.models.unit import Unit
    case = dict(portal_case)
    owner = case['residents']['resident'][1]
    target = case['residents']['housemate'][1]
    with case['database'].get_session() as session:
        unit = Unit(building_id=case['building'].id, unit_number='ZZ-' + uuid4().hex[:8],
                    floor=1, area_m2=50, status='occupied')
        session.add(unit); session.flush()
        session.add(UnitPersonRelationship(tenant_id=case['tenant'].id, site_id=case['site'].id,
            building_id=case['building'].id, unit_id=unit.id, person_id=owner.id,
            relationship_type='owner', ownership_ratio=Decimal('1'), valid_from=date(2025, 1, 1)))
        session.commit()
    case['unit'] = unit
    effective = date.today() + timedelta(days=1)
    dossier = post(case, '/dossiers', {'unit_id': str(unit.id), 'kind': 'TRANSFER', 'title': 'Synthetic partial transfer',
        'valid_from': str(effective), 'data': {'target_person_id': str(target.id), 'ownership_ratio': '0.3000'}})
    assert dossier.status_code == 201, dossier.text
    proof(case, dossier.json()['id'])
    approved = action(case, f"/dossiers/{dossier.json()['id']}/actions", dossier.json(), 'APPROVE')
    assert approved.status_code == 200, approved.text
    with case['database'].get_session() as session:
        episodes = session.scalars(select(UnitPersonRelationship).where(
            UnitPersonRelationship.unit_id == unit.id, UnitPersonRelationship.relationship_type == 'owner')).all()
        active = [r for r in episodes if r.valid_from <= effective and (r.valid_to is None or r.valid_to > effective)]
        assert sum(r.ownership_ratio for r in active) == Decimal('1')
        assert {r.person_id: r.ownership_ratio for r in active} == {owner.id: Decimal('0.7'), target.id: Decimal('0.3')}
        assert any(r.person_id == owner.id and r.ownership_ratio == Decimal('1') and r.valid_to == effective for r in episodes)


@isolated
def test_future_profile_applies_once_on_due_date(portal_case, monkeypatch):
    from app.models.resident_portal import PortalDossierEvent
    import app.services.portal_jobs as jobs
    case = portal_case
    current = case['client'].get('/api/v1/portal/profile', headers=case['auth']['resident']).json()['person']['full_name']
    due = date.today() + timedelta(days=1)
    row = post(case, '/dossiers', {'unit_id': str(case['unit'].id), 'kind': 'PROFILE_CHANGE',
        'title': 'Synthetic scheduled profile', 'valid_from': str(due), 'data': {'full_name': 'Synthetic future name'}})
    assert row.status_code == 201, row.text
    approved = action(case, f"/dossiers/{row.json()['id']}/actions", row.json(), 'APPROVE')
    assert approved.status_code == 200, approved.text
    assert case['client'].get('/api/v1/portal/profile', headers=case['auth']['resident']).json()['person']['full_name'] == current
    class DueDate(date):
        @classmethod
        def today(cls):
            return due
    monkeypatch.setattr(jobs, 'date', DueDate)
    assert post(case, '/jobs/tick', {}, 'cskh').status_code == 200
    assert case['client'].get('/api/v1/portal/profile', headers=case['auth']['resident']).json()['person']['full_name'] == 'Synthetic future name'
    assert post(case, '/jobs/tick', {}, 'cskh').status_code == 200
    with case['database'].get_session() as session:
        assert session.scalar(select(func.count(PortalDossierEvent.id)).where(
            PortalDossierEvent.dossier_id == row.json()['id'], PortalDossierEvent.action == 'APPLY')) == 1


@isolated
def test_upload_rollback_removes_uncommitted_file(portal_case, monkeypatch, tmp_path):
    case = portal_case
    monkeypatch.setattr(case['settings'], 'private_storage_path', tmp_path)
    def fail(*args, **kwargs):
        raise RuntimeError('Synthetic transaction failure')
    monkeypatch.setattr('app.services.resident_portal.remember_idempotency', fail)
    response = case['client'].post('/api/v1/portal/documents', params={'unit_id': str(case['unit'].id), 'title': 'Synthetic rollback'},
        content=b'%PDF-1.4\nsynthetic\n%%EOF', headers={**case['auth']['resident'], 'Idempotency-Key': 'rollback-' + uuid4().hex,
        'Content-Type': 'application/pdf', 'X-File-Name': 'synthetic.pdf'})
    assert response.status_code == 500
    assert not [p for p in tmp_path.rglob('*') if p.is_file()]


@isolated
def test_request_conversation_confirmation_complaint_and_single_rating(portal_case):
    from app.models.service import ServiceRequest, CaseRecord
    case = portal_case
    created = case['client'].post('/api/v1/resident/service-requests', json={
        'unit_id': str(case['unit'].id), 'category_id': str(case['category'].id),
        'title': 'Synthetic conversation', 'description': 'Synthetic request details', 'priority': 'MEDIUM'},
        headers={**case['auth']['resident'], 'Idempotency-Key': 'conversation-' + uuid4().hex})
    assert created.status_code == 201, created.text
    identifier = created.json()['id']
    path = f'/requests/{identifier}/messages'
    def snapshot():
        return case['client'].get('/api/v1/portal' + path, headers=case['auth']['resident']).json()
    waiting = action(case, path, snapshot(), 'REQUEST_INFO')
    assert waiting.status_code == 200, waiting.text
    assert snapshot()['status'] == 'WAITING_INFO'
    assert action(case, path, snapshot(), 'REPLY', 'resident').status_code == 200
    assert snapshot()['status'] == 'TRIAGED'
    with case['database'].get_session() as session:
        row = session.get(ServiceRequest, identifier); row.status = 'RESOLVED'; session.commit()
    assert action(case, path, snapshot(), 'COMPLAINT', 'resident').status_code == 200
    with case['database'].get_session() as session:
        assert session.scalar(select(CaseRecord.id).where(CaseRecord.source_service_request_id == identifier)) is not None
    assert action(case, path, snapshot(), 'RESOLVE_COMPLAINT').status_code == 200
    with case['database'].get_session() as session:
        row = session.get(ServiceRequest, identifier); row.status = 'RESOLVED'; session.commit()
    assert action(case, path, snapshot(), 'CONFIRM', 'resident').status_code == 200
    assert action(case, path, snapshot(), 'REPLY', 'resident').status_code == 409
    assert action(case, path, snapshot(), 'RATE', 'resident', {'score': 4}).status_code == 200
    assert action(case, path, snapshot(), 'RATE', 'resident', {'score': 5}).status_code == 409
