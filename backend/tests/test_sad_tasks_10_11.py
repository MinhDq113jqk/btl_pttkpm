"""Real transactions on disposable PG; email stub, no external/provider/device calls."""
import os
import secrets
import smtplib
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4
import pytest
from sqlalchemy import select, func
from app.core.security import hash_password
from app.models.account import Account, AccountRole
from app.models.account_parking import AccountEmailChange, ParkingDiscrepancy, ParkingReconciliation
from app.models.auth_session import AuthSession
from app.models.resident_portal import AccountRecovery, VehicleRegistration
from app.models.operational_control import ParkingSlot, ControlEvent
from app.services.account_control import token_digest
from auth_test_support import mint_session_token
from test_step1_fee_proration import concurrent_case
from test_portal_workflows import post, action, resource

pytestmark = pytest.mark.skipif(os.getenv('GREENCITY_ISOLATED_SECURITY_TESTS') != '1', reason='Disposable PostgreSQL required')


@pytest.fixture
def case(concurrent_case, monkeypatch):
    c = concurrent_case; password = secrets.token_urlsafe(24)
    with c['database'].get_session() as s:
        maker = s.scalar(select(Account).join(AccountRole).where(Account.tenant_id == c['tenant'].id, AccountRole.role == 'accountant'))
        resident = s.scalar(select(Account).join(AccountRole).where(Account.tenant_id == c['tenant'].id, AccountRole.role == 'resident'))
        maker.hashed_password = resident.hashed_password = hash_password(password)
        director = Account(tenant_id=c['tenant'].id, username='director_'+uuid4().hex, full_name='Synthetic director', hashed_password=hash_password(password))
        admin = Account(tenant_id=c['tenant'].id, username='admin_'+uuid4().hex, full_name='Synthetic tenant admin', hashed_password=hash_password(password))
        worker = Account(tenant_id=c['tenant'].id, username='worker_'+uuid4().hex, full_name='Synthetic worker', hashed_password=hash_password(password))
        admin2 = Account(tenant_id=c['tenant'].id, username='admin2_'+uuid4().hex, full_name='Synthetic second admin', hashed_password=hash_password(password))
        s.add_all([director, admin, worker, admin2]); s.flush()
        s.add_all([AccountRole(account_id=director.id, site_id=c['site'].id, role='director'),
            AccountRole(account_id=admin.id, role='admin', site_id=None), AccountRole(account_id=admin2.id, role='admin', site_id=None),
            AccountRole(account_id=worker.id, site_id=c['site'].id, building_id=c['building'].id, role='technician')]); s.commit()
    for label, account in [('director', director), ('admin', admin), ('worker', worker), ('admin2', admin2)]:
        c['auth'][label] = {'Authorization': 'Bearer '+mint_session_token(c['database'], account.id, c['settings'].auth_secret(), claims={'active_site_id': str(c['site'].id)})}
    c['settings'].smtp_enabled = True; c['settings'].smtp_host = 'mail.invalid'; c['settings'].smtp_from_email = 'noreply@example.invalid'
    return {**c, 'maker': maker, 'resident': resident, 'director': director, 'admin': admin, 'worker': worker, 'admin2': admin2, 'password': password}


def get(c, path, actor='cskh', **params):
    r = c['client'].get('/api/v1/portal'+path, params=params, headers=c['auth'][actor]); assert r.status_code == 200, r.text
    return r.json()


def verify(c, target, actor, monkeypatch):
    tokens = []
    monkeypatch.setattr('app.api.portal_accounts.send_recovery', lambda settings, email, identifier, token, expiry: tokens.append((identifier, token)))
    r = c['client'].post('/api/v1/auth/recovery/request', json={'username': target.username}); assert r.status_code == 200
    rows = get(c, '/recovery-requests', actor)['items']; row = next(r for r in rows if r['username'] == target.username)
    r = post(c, f"/recovery-requests/{row['id']}/verify", {'reference': 'SYNTHETIC verification evidence', 'current_password': c['password'], 'verified_email': 'verified@example.invalid'}, actor)
    assert r.status_code == 200, r.text; assert 'token' not in r.json()
    return {'request_id': str(tokens[-1][0]), 'token': tokens[-1][1], 'new_password': secrets.token_urlsafe(24)}


def test_profile_whitelist_version_and_reauth(case):
    c = case; row = get(c, '/account-profile', 'worker')
    body = {'full_name': 'Synthetic changed name', 'current_password': c['password'], 'expected_version': row['profile_version']}
    assert post(c, '/account-profile', {**body, 'role': 'admin'}, 'worker').status_code == 422
    assert post(c, '/account-profile', {**body, 'current_password': 'wrong'}, 'worker').status_code == 403
    r = post(c, '/account-profile', body, 'worker'); assert r.status_code == 200, r.text
    assert post(c, '/account-profile', body, 'worker').status_code == 409
    with c['database'].get_session() as s:
        assert s.get(Account, c['worker'].id).full_name == 'Synthetic changed name'
        assert list(s.scalars(select(AccountRole.role).where(AccountRole.account_id == c['worker'].id))) == ['technician']


@pytest.mark.parametrize('invalid', ['wrong-purpose', 'expired', 'profile-changed', 'wrong-account'])
def test_email_token_binding_and_invalid_cases(case, monkeypatch, invalid):
    c = case; sent = []
    monkeypatch.setattr('app.api.account_profile.send_email_verification', lambda *args: sent.append(args))
    r = post(c, '/account-profile/email/request', {'email': 'new@example.invalid', 'current_password': c['password'], 'expected_version': 1}, 'worker')
    assert r.status_code == 200, r.text; body = {'request_id': r.json()['request_id'], 'token': sent[-1][3]}
    assert 'token' not in r.json(); actor = 'worker'
    with c['database'].get_session() as s:
        challenge = s.get(AccountEmailChange, UUID(body['request_id']))
        assert challenge.token_hash != body['token']
        if invalid == 'wrong-purpose': challenge.token_hash = token_digest('account-recovery', challenge.id, body['token'])
        elif invalid == 'expired': challenge.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        elif invalid == 'profile-changed': s.get(Account, c['worker'].id).profile_version += 1
        else: actor = 'resident'
        s.commit()
    assert post(c, '/account-profile/email/confirm', body, actor).status_code == 400
    with c['database'].get_session() as s:
        assert s.get(Account, c['worker'].id).email is None


def test_email_success_revokes_sessions_and_failed_send_does_not_change_email(case, monkeypatch):
    c = case; sent = []
    monkeypatch.setattr('app.api.account_profile.send_email_verification', lambda *args: sent.append(args))
    r = post(c, '/account-profile/email/request', {'email': 'new@example.invalid', 'current_password': c['password'], 'expected_version': 1}, 'worker')
    body = {'request_id': r.json()['request_id'], 'token': sent[-1][3]}
    assert post(c, '/account-profile/email/confirm', body, 'worker').status_code == 200
    assert c['client'].get('/api/v1/auth/me', headers=c['auth']['worker']).status_code == 401
    with c['database'].get_session() as s:
        assert s.get(Account, c['worker'].id).email == 'new@example.invalid'
        assert not s.scalar(select(AuthSession.id).where(AuthSession.account_id == c['worker'].id, AuthSession.revoked_at.is_(None)))
    c['auth']['worker'] = {'Authorization': 'Bearer '+mint_session_token(c['database'], c['worker'].id, c['settings'].auth_secret(), claims={'active_site_id': str(c['site'].id)})}
    assert post(c, '/account-profile/email/confirm', body, 'worker').status_code == 400
    monkeypatch.setattr('app.api.account_profile.send_email_verification', lambda *args: (_ for _ in ()).throw(smtplib.SMTPException('synthetic failure')))
    assert post(c, '/account-profile/email/request', {'email': 'other@example.invalid', 'current_password': c['password'], 'expected_version': 1}, 'resident').status_code == 502
    with c['database'].get_session() as s:
        assert s.get(Account, c['resident'].id).email is None
        assert s.scalar(select(AccountEmailChange.token_hash).where(AccountEmailChange.account_id == c['resident'].id)) is None


def test_worker_recovery_authority_public_response_and_no_role_restore(case, monkeypatch):
    c = case
    expected = c['client'].post('/api/v1/auth/recovery/request', json={'username': 'missing_'+uuid4().hex}).json()
    assert c['client'].post('/api/v1/auth/recovery/request', json={'username': c['worker'].username}).json() == expected
    token = verify(c, c['worker'], 'director', monkeypatch)
    assert c['client'].post('/api/v1/auth/recovery/complete', json=token).status_code == 200
    assert c['client'].post('/api/v1/auth/recovery/complete', json=token).status_code == 400
    assert c['client'].get('/api/v1/auth/me', headers=c['auth']['worker']).status_code == 401
    with c['database'].get_session() as s:
        assert list(s.scalars(select(AccountRole.role).where(AccountRole.account_id == c['worker'].id))) == ['technician']
    c['client'].post('/api/v1/auth/recovery/request', json={'username': c['maker'].username})
    assert not any(r['username'] == c['maker'].username for r in get(c, '/recovery-requests', 'director')['items'])
    with c['database'].get_session() as s:
        identifier = s.scalar(select(AccountRecovery.id).where(AccountRecovery.account_id == c['maker'].id))
    assert post(c, f'/recovery-requests/{identifier}/verify', {'reference': 'SYNTHETIC verification evidence', 'current_password': c['password'], 'verified_email': 'verified@example.invalid'}, 'director').status_code == 404
    verify(c, c['maker'], 'admin', monkeypatch)


@pytest.mark.parametrize('invalidate', ['sessions', 'roles', 'locked', 'purpose', 'expired'])
def test_recovery_rejects_stale_or_repurposed_tokens(case, monkeypatch, invalidate):
    c = case; body = verify(c, c['worker'], 'director', monkeypatch)
    with c['database'].get_session() as s:
        a = s.get(Account, c['worker'].id); row = s.get(AccountRecovery, UUID(body['request_id']))
        if invalidate == 'sessions': a.session_version += 1
        elif invalidate == 'roles':
            for role in s.scalars(select(AccountRole).where(AccountRole.account_id == a.id)): role.valid_to = datetime.now(UTC)-timedelta(seconds=1)
        elif invalidate == 'locked': a.is_active = False
        elif invalidate == 'purpose': row.token_hash = token_digest('email-change', row.id, body['token'])
        else: row.expires_at = datetime.now(UTC)-timedelta(seconds=1)
        s.commit()
    assert c['client'].post('/api/v1/auth/recovery/complete', json=body).status_code == 400


def test_permission_directory_and_independent_review(case):
    c = case; catalogue = get(c, '/control/permission-catalog', 'worker')
    assert len(catalogue['roles']) == 9 and not catalogue['can_manage_accounts']
    assert post(c, '/control/access-reviews', {'target_account_id': str(c['worker'].id), 'description': 'Synthetic sign requiring review', 'evidence_reference': 'SYN-PROOF'}, 'cskh').status_code == 403
    r = post(c, '/control/access-reviews', {'target_account_id': str(c['worker'].id), 'description': 'Synthetic sign requiring review', 'evidence_reference': 'SYN-PROOF'}, 'admin'); assert r.status_code == 201, r.text
    row = r.json(); body = {'action': 'LOCK', 'expected_version': row['version'], 'reason': 'Synthetic independent decision', 'current_password': c['password']}
    assert post(c, f"/control/access-reviews/{row['id']}/resolve", body, 'admin').status_code == 403
    r = post(c, f"/control/access-reviews/{row['id']}/resolve", body, 'admin2'); assert r.status_code == 200, r.text
    assert 'current_password' not in str(r.json())
    with c['database'].get_session() as s:
        assert not s.get(Account, c['worker'].id).is_active
        assert not s.scalar(select(AuthSession.id).where(AuthSession.account_id == c['worker'].id, AuthSession.revoked_at.is_(None)))
        events = s.scalars(select(ControlEvent).where(ControlEvent.tenant_id == c['tenant'].id)).all()
        assert all(c['password'] not in str(e.snapshot) for e in events)


def parking(c):
    park = resource(c, 'PARKING', capacity=3)
    r = post(c, '/vehicles', {'unit_id': str(c['unit'].id), 'resource_id': park['id'], 'plate': 'SYN-'+uuid4().hex[:8], 'vehicle_type': 'CAR'})
    assert r.status_code == 201, r.text
    r = action(c, f"/vehicles/{r.json()['id']}/actions", r.json(), 'APPROVE'); assert r.status_code == 200, r.text
    vehicle = r.json()
    r = post(c, '/control/parking-slots', {'resource_id': park['id'], 'code': 'SYN-01', 'vehicle_types': ['CAR']}, 'cskh'); assert r.status_code == 201, r.text
    return park, vehicle, r.json()


def scan(c, park, **kwargs):
    body = {'resource_id': park['id'], 'starts_at': '2026-01-01T00:00:00Z', 'ends_at': '2026-01-02T00:00:00Z', 'require_slots': True, 'policy_reference': 'SYN confirmed slot policy', **kwargs}
    r = post(c, '/control/parking-reconciliations', body, 'cskh'); assert r.status_code == 201, r.text
    return r.json(), body


def decide(c, finding, verb, slot=None, key=None):
    return post(c, f"/control/parking-discrepancies/{finding['id']}/resolve", {'expected_version': finding['version'], 'action': verb,
        'reason': 'Synthetic checked source and decision', 'evidence_reference': 'SYN-PROOF', 'slot_id': slot}, 'cskh', key)


def test_parking_snapshot_dedup_and_single_assignment(case):
    c = case; park, vehicle, slot = parking(c); row, body = scan(c, park)
    again, _ = scan(c, park); assert again['id'] == row['id']
    detail = get(c, f"/control/parking-reconciliations/{row['id']}")
    assert detail['snapshot']['usage_data_status'] == 'MISSING'
    missing = next(f for f in detail['findings'] if f['code'] == 'MISSING_SLOT')
    assert not any('NOT_USED' in f['code'] for f in detail['findings'])
    key = uuid4().hex
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: decide(c, missing, 'ASSIGN_MISSING_SLOT', slot['id'], key), range(2)))
    assert all(r.status_code == 200 for r in results), [r.status_code for r in results]
    assert decide(c, missing, 'ASSIGN_MISSING_SLOT', slot['id']).status_code == 409
    with c['database'].get_session() as s:
        assert s.get(ParkingSlot, UUID(slot['id'])).vehicle_id == UUID(vehicle['id'])
        assert s.get(ParkingSlot, UUID(slot['id'])).version == 2
        assert s.scalar(select(func.count()).select_from(ParkingDiscrepancy).where(ParkingDiscrepancy.resource_id == UUID(park['id']))) == 1
    after, _ = scan(c, park); assert not get(c, f"/control/parking-reconciliations/{after['id']}")['findings']
    assert get(c, f"/control/parking-reconciliations/{row['id']}")['snapshot']['slots'][0]['vehicle_id'] is None


def test_parking_stale_source_scope_and_policy_control(case):
    c = case; park, vehicle, slot = parking(c); row, _ = scan(c, park)
    missing = get(c, f"/control/parking-reconciliations/{row['id']}")['findings'][0]
    assert c['client'].get(f"/api/v1/portal/control/parking-reconciliations/{row['id']}", headers=c['auth']['resident']).status_code == 403
    with c['database'].get_session() as s:
        v = s.get(VehicleRegistration, UUID(vehicle['id'])); v.version += 1; s.commit()
    assert decide(c, missing, 'ASSIGN_MISSING_SLOT', slot['id']).status_code == 409
    with c['database'].get_session() as s: assert s.get(ParkingSlot, UUID(slot['id'])).vehicle_id is None
    row, _ = scan(c, park, require_slots=False)
    assert not any(f['code'] == 'MISSING_SLOT' for f in get(c, f"/control/parking-reconciliations/{row['id']}")['findings'])


def test_parking_usage_coverage_mismatch_and_duplicate_sources(case):
    c = case; park, vehicle, slot = parking(c)
    body = {'resource_id': park['id'], 'source_reference': 'SYN-LOG-A', 'starts_at': '2026-01-01T00:00:00Z', 'ends_at': '2026-01-02T00:00:00Z', 'completeness': 'PARTIAL',
        'entries': [{'event_reference': 'event-A', 'plate': vehicle['plate'], 'occurred_at': '2026-01-01T01:00:00Z', 'slot_code': 'UNKNOWN', 'holder_account_id': str(c['worker'].id)}]}
    r = post(c, '/control/parking-usage', body); assert r.status_code == 403
    r = post(c, '/control/parking-usage', body, 'cskh'); assert r.status_code == 201, r.text
    assert post(c, '/control/parking-usage', body, 'cskh').json()['id'] == r.json()['id']
    assert post(c, '/control/parking-usage', {**body, 'entries': []}, 'cskh').status_code == 409
    row, _ = scan(c, park); detail = get(c, f"/control/parking-reconciliations/{row['id']}")
    assert detail['snapshot']['usage_data_status'] == 'PARTIAL'
    assert {'USAGE_OWNER_MISMATCH', 'USAGE_SLOT_MISMATCH'} <= {f['code'] for f in detail['findings']}
    assert post(c, '/control/parking-usage', {**body, 'source_reference': 'SYN-LOG-B', 'completeness': 'COMPLETE'}, 'cskh').status_code == 201
    row, _ = scan(c, park); detail = get(c, f"/control/parking-reconciliations/{row['id']}")
    assert detail['snapshot']['usage_data_status'] == 'COMPLETE'
    duplicate = next(f for f in detail['findings'] if f['code'] == 'DUPLICATE_USAGE')
    assert decide(c, duplicate, 'RELEASE_INVALID_SLOT').status_code == 422
    assert decide(c, duplicate, 'RECORD_DECISION').status_code == 200


def test_different_concurrent_decisions_release_invalid_slot_once(case):
    c = case; park, vehicle, slot = parking(c)
    r = action(c, f"/control/parking-slots/{slot['id']}/actions", slot, 'ASSIGN', data={'vehicle_id': vehicle['id']}); assert r.status_code == 200, r.text
    # Simulate a declared legacy inconsistency, confined to disposable PG.
    with c['database'].get_session() as s:
        row = s.get(VehicleRegistration, UUID(vehicle['id'])); row.status = 'CANCELLED'; row.version += 1; s.commit()
    row, _ = scan(c, park)
    invalid = next(f for f in get(c, f"/control/parking-reconciliations/{row['id']}")['findings'] if f['code'] == 'INVALID_SLOT')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: decide(c, invalid, 'RELEASE_INVALID_SLOT'), range(2)))
    assert sorted(r.status_code for r in results) == [200, 409]
    with c['database'].get_session() as s:
        assert s.get(ParkingSlot, UUID(slot['id'])).vehicle_id is None
        assert s.get(ParkingSlot, UUID(slot['id'])).version == 3
        assert s.scalar(select(func.count()).select_from(ControlEvent).where(ControlEvent.parent_id == UUID(slot['id']), ControlEvent.action == 'RELEASE')) == 1


def test_changed_policy_requires_new_scan_before_correction(case):
    c = case; park, vehicle, slot = parking(c); row, _ = scan(c, park)
    missing = next(f for f in get(c, f"/control/parking-reconciliations/{row['id']}")['findings'] if f['code'] == 'MISSING_SLOT')
    r = action(c, f"/resources/{park['id']}/actions", park, 'UPDATE', data={'fee_vnd': 2000, 'policy': park['policy']}); assert r.status_code == 200, r.text
    r = decide(c, missing, 'ASSIGN_MISSING_SLOT', slot['id']); assert r.status_code == 409 and r.json()['error']['code'] == 'ERR-SOURCE-CHANGED'
