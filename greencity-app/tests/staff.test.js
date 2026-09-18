import test from 'node:test';
import assert from 'node:assert/strict';
import { staffAccounts, findStaffAccount, getAllowedNav, canViewTab, canSubmitRefund, canApproveRefund, getScopedTasks, getScopedNotifications, loadStaffSession } from '../src/data/staffRoles.js';
import { loadAssistantHistory, persistAssistantHistory, createAssistantState, createConversation } from '../src/data/assistantStore.js';

test('eight staff roles share one account model', () => {
  assert.equal(staffAccounts.length, 8);
  assert.equal(new Set(staffAccounts.map(item => item.accountId)).size, 8);
  for (const account of staffAccounts) assert.ok(getAllowedNav(account).some(item => item.id === 'overview'));
});
test('financial maker/checker and read-only roles are separated', () => {
  assert.ok(canSubmitRefund(findStaffAccount('demo-accountant')));
  assert.ok(!canApproveRefund(findStaffAccount('demo-accountant')));
  assert.ok(canApproveRefund(findStaffAccount('demo-director')));
  assert.ok(!canSubmitRefund(findStaffAccount('demo-director')));
  for (const role of ['admin', 'auditor']) {
    const account = findStaffAccount(`demo-${role}`);
    assert.ok(canViewTab(account, 'refund-form'));
    assert.ok(!canSubmitRefund(account));
    assert.ok(!canApproveRefund(account));
  }
  assert.ok(!canApproveRefund(findStaffAccount('demo-director'), 'demo-director'));
});
test('execution roles see assigned tasks only and no financial module', () => {
  for (const [role, count] of [['technical', 2], ['cleaning', 1], ['security', 1]]) {
    const account = findStaffAccount(`demo-${role}`);
    assert.equal(getScopedTasks(account).length, count);
    assert.ok(!canViewTab(account, 'refund-form'));
    assert.ok(!canViewTab(account, 'settings'));
    assert.ok(getScopedTasks(account).every(task => task.department !== 'Tài chính'));
  }
});
test('CSKH and accounting have distinct work queues', () => {
  assert.equal(getScopedTasks(findStaffAccount('demo-cskh')).length, 3);
  assert.ok(getScopedTasks(findStaffAccount('demo-cskh')).every(item => item.department === 'CSKH'));
  assert.equal(getScopedTasks(findStaffAccount('demo-accountant')).length, 1);
});
test('notifications refer only to visible tasks', () => {
  for (const account of staffAccounts) {
    const ids = new Set(getScopedTasks(account).map(item => item.id));
    assert.ok(getScopedNotifications(account).every(item => !item.taskId || ids.has(item.taskId)));
  }
});
test('unknown account and corrupt sessions are rejected; stored roles are not trusted', () => {
  assert.equal(findStaffAccount('unknown'), null);
  for (const raw of ['{', '{}', '{"accountId":"unknown"}']) assert.equal(loadStaffSession({ getItem: () => raw }), null);
  const account = loadStaffSession({ getItem: () => JSON.stringify({ accountId: 'demo-cleaning', refund: 'approve', menu: ['settings'] }) });
  assert.equal(account.id, 'cleaning');
  assert.equal(account.refund, 'none');
  assert.ok(!canViewTab(account, 'settings'));
});
test('assistant history storage is separated by account', () => {
  const map = new Map();
  const storage = { getItem: key => map.get(key), setItem: (key, value) => map.set(key, value) };
  const first = createAssistantState(createConversation('first'));
  persistAssistantHistory(storage, first, 'assistant:accountant');
  assert.equal(loadAssistantHistory(storage, 'assistant:accountant').activeId, 'first');
  assert.notEqual(loadAssistantHistory(storage, 'assistant:cleaning').activeId, 'first');
});
