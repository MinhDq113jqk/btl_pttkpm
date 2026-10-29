"""Personal training read contract, offline with synthetic rows only."""
from contextlib import nullcontext
from types import SimpleNamespace
from uuid import uuid4

from app.api import sad_work


def test_my_training_reports_only_the_current_workers_acknowledgement(monkeypatch):
    own_account, other_account, own_staff, other_staff = [uuid4() for _ in range(4)]
    def row(kind, data):
        return SimpleNamespace(id=uuid4(), kind=kind, status='APPROVED', data=data)
    staff = [SimpleNamespace(id=own_staff, data={'account_id': str(own_account)}),
             SimpleNamespace(id=other_staff, data={'account_id': str(other_account)})]
    acknowledgement = {'actor_id': str(own_account), 'result': 'Đã tiếp nhận SOP', 'evidence_reference': 'ACK-01'}
    other_ack = {'actor_id': str(other_account), 'result': 'Worker B', 'evidence_reference': 'ACK-02'}
    completed = row('TRAINING', {'staff_ids': [str(own_staff), str(other_staff)], 'acknowledgements': {str(own_staff): acknowledgement, str(other_staff): other_ack}})
    pending = row('TRAINING', {'staff_ids': [str(own_staff), str(other_staff)], 'acknowledgements': {str(other_staff): other_ack}})
    foreign = row('TRAINING', {'staff_ids': [str(other_staff)]})
    batches = iter([staff, [], [completed, pending, foreign]])
    session = SimpleNamespace(scalars=lambda query: SimpleNamespace(all=lambda: next(batches)))
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(database=SimpleNamespace(get_session=lambda: nullcontext(session)))))
    context = SimpleNamespace(account_id=own_account, assert_role=lambda *roles: None, scope_conditions=lambda model: [])
    monkeypatch.setattr(sad_work, 'view', lambda value: {'id': str(value.id), 'kind': value.kind, 'data': value.data})
    result = sad_work.my_work(request, context)
    assert len(result['items']) == 2
    assert result['items'][0]['my_acknowledgement'] == acknowledgement
    assert result['items'][1]['my_acknowledgement'] is None


def test_my_work_retains_only_assigned_work_and_incoming_handoffs(monkeypatch):
    account_id, staff_id, roster_id, other_roster_id = [uuid4() for _ in range(4)]
    staff = [SimpleNamespace(id=staff_id, data={'account_id': str(account_id)})]
    own_roster = SimpleNamespace(id=roster_id, status='APPROVED', data={'staff_id': str(staff_id)})
    incoming = SimpleNamespace(id=uuid4(), status='IN_PROGRESS', data={'staff_id': 'other-staff', 'handover_to_roster_id': str(roster_id)})
    closed = SimpleNamespace(id=uuid4(), status='COMPLETED', data={'staff_id': 'other-staff', 'handover_to_roster_id': str(roster_id)})
    assigned = SimpleNamespace(id=uuid4(), kind='WORK_ASSIGNMENT', data={'roster_id': str(roster_id)})
    foreign = SimpleNamespace(id=uuid4(), kind='WORK_ASSIGNMENT', data={'roster_id': str(other_roster_id)})
    batches = iter([staff, [own_roster, incoming, closed], [assigned, foreign]])
    session = SimpleNamespace(scalars=lambda query: SimpleNamespace(all=lambda: next(batches)))
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(database=SimpleNamespace(get_session=lambda: nullcontext(session)))))
    context = SimpleNamespace(account_id=account_id, assert_role=lambda *roles: None, scope_conditions=lambda model: [])
    monkeypatch.setattr(sad_work, 'view', lambda row: {'id': str(row.id), 'data': row.data})
    result = sad_work.my_work(request, context)
    assert [row['id'] for row in result['items']] == [str(assigned.id)]
    assert [row['id'] for row in result['handoffs']] == [str(incoming.id)]
