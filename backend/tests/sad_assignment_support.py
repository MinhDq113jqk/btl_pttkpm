"""Approved synthetic workforce fixtures for earlier execution regressions.

Approval/refusal workflows are separately exercised in test_sad_tasks_01_08.
"""
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4
from sqlalchemy import select
from app.models.account import Account, AccountRole
from app.models.operational_control import OperationsRecord


def prepare_worker(case, worker, building_id, skill):
    with case['database'].get_session() as session:
        scope = dict(tenant_id=case['tenant'].id, site_id=case['sites'][0].id, building_id=UUID(str(building_id)))
        maker = case['accounts']['director']
        checker = case.get('sad_fixture_checker')
        if checker is None:
            checker = Account(tenant_id=case['tenant'].id, username='fixture_checker_' + uuid4().hex, full_name='Synthetic checker', hashed_password='token-only-test-account')
            session.add(checker); session.flush(); session.add(AccountRole(account_id=checker.id, site_id=scope['site_id'], role='admin')); case['sad_fixture_checker'] = checker
        staff = next((r for r in session.scalars(select(OperationsRecord).where(OperationsRecord.kind == 'STAFF', OperationsRecord.building_id == scope['building_id'], OperationsRecord.status == 'APPROVED')) if r.data['account_id'] == str(worker.id)), None)
        if staff is None:
            catalogs = []
            for kind, code in [('TEAM', 'SyntheticTeam'), ('POSITION', 'SyntheticPosition'), ('TERRITORY', 'SyntheticTerritory')]:
                source = next((r for r in session.scalars(select(OperationsRecord).where(OperationsRecord.kind == 'MASTER_DATA', OperationsRecord.building_id == scope['building_id'], OperationsRecord.status == 'APPROVED')) if r.data['catalog'] == kind), None)
                if source is None:
                    source = OperationsRecord(**scope, account_id=maker.id, approved_by_id=checker.id, kind='MASTER_DATA', title='Synthetic ' + kind, status='APPROVED', data={'code': kind+'-SYN', 'revision': 1, 'valid_from': '2025-01-01', 'valid_to': None, 'body': 'Synthetic catalog', 'confirmed_rule_reference': 'SYN', 'catalog': kind, 'entries': [{'code': code, 'name': code, 'active': True}]})
                    session.add(source); session.flush()
                catalogs.append(str(source.id))
            staff = OperationsRecord(**scope, account_id=maker.id, approved_by_id=checker.id, kind='STAFF', title='Synthetic worker', status='APPROVED', data={'account_id': str(worker.id), 'team': 'SyntheticTeam', 'position': 'SyntheticPosition', 'territory': 'SyntheticTerritory', 'catalog_ids': catalogs, 'skills': [skill], 'certificates': '', 'certificate_expires_on': None})
            session.add(staff); session.flush()
        roster = next((r for r in session.scalars(select(OperationsRecord).where(OperationsRecord.kind == 'ROSTER', OperationsRecord.building_id == scope['building_id'], OperationsRecord.status == 'APPROVED')) if r.data['staff_id'] == str(staff.id)), None)
        if roster is None:
            now = datetime.now(UTC)
            session.add(OperationsRecord(**scope, account_id=maker.id, approved_by_id=checker.id, kind='ROSTER', title='Synthetic execution roster', status='APPROVED', data={'staff_id': str(staff.id), 'starts_at': (now-timedelta(days=2)).isoformat(), 'ends_at': (now+timedelta(days=10)).isoformat(), 'required_skill': skill, 'task': 'Synthetic execution regression'}))
        session.commit()


def accept_work(case, target_id, worker_label):
    response = case['client'].get('/api/v1/portal/operations/my-work', headers=case['auth'][worker_label]); assert response.status_code == 200, response.text
    row = next(r for r in response.json()['items'] if r['kind'] == 'WORK_ASSIGNMENT' and r['data']['target_id'] == str(target_id))
    response = case['client'].post(f"/api/v1/portal/operations/my-work/{row['id']}/acknowledge", headers={**case['auth'][worker_label], 'Idempotency-Key': uuid4().hex}, json={'action': 'ACCEPT_WORK', 'expected_version': row['version'], 'reason': 'Synthetic acceptance', 'data': {'result': 'Synthetic accepted work', 'evidence_reference': 'SYN-ACK'}})
    assert response.status_code == 200, response.text
