import test from 'node:test';
import assert from 'node:assert/strict';
import {
  canViewTab,
  createAuthenticatedAccount,
  getAllowedNav,
  getStaffTabFromHash,
} from '../src/data/authSession.js';
import {
  loadAssistantHistory,
  persistAssistantHistory,
  createAssistantState,
  createConversation,
} from '../src/data/assistantStore.js';

const makeUser = (roles, extras = {}) => ({
  account_id: 'account-1',
  username: 'staff-1',
  full_name: 'Nguyễn Nhân viên',
  roles,
  allowed_sites: [{ id: 'site-a', code: 'GC-A', name: 'GreenCity A' }],
  active_site_id: 'site-a',
  ...extras,
});

test('workspace menu is derived from the server roles for all supported roles', () => {
  const expectedMenus = new Map([
    ['admin', ['overview', 'tasks', 'cleaning', 'security', 'parcels', 'finance', 'residents', 'imports', 'notifications']],
    ['director', ['overview', 'tasks', 'cleaning', 'security', 'parcels', 'finance', 'residents', 'notifications']],
    ['accountant', ['overview', 'tasks', 'finance', 'residents', 'notifications']],
    ['cskh', ['overview', 'tasks', 'parcels', 'residents', 'imports', 'notifications']],
    ['technical_lead', ['overview', 'tasks', 'maintenance', 'residents', 'notifications']],
    ['technician', ['overview', 'tasks', 'maintenance', 'notifications']],
    ['cleaning', ['overview', 'cleaning', 'notifications']],
    ['security', ['overview', 'security', 'parcels', 'residents', 'notifications']],
    ['resident', ['overview', 'notifications']],
  ]);

  for (const [role, expected] of expectedMenus) {
    const account = createAuthenticatedAccount(makeUser([role]));
    const expectedSet = [...expected].sort();
    assert.deepEqual([...account.menu].sort(), expectedSet, role);
    assert.deepEqual(getAllowedNav(account).map(item => item.id).sort(), expectedSet, role);
  }
});

test('unrecognized and client-supplied menu values never grant extra pages', () => {
  const account = createAuthenticatedAccount(makeUser(['custom_role'], {
    menu: ['refund-form', 'settings', 'media'],
    refund: 'approve',
  }));

  assert.deepEqual(account.menu, ['overview', 'notifications']);
  for (const tab of ['refund-form', 'settings', 'media', 'amenities', 'reports']) {
    assert.equal(canViewTab(account, tab), false, tab);
  }
});

test('only supported workspace hashes resolve to a tab', () => {
  assert.equal(getStaffTabFromHash('#/maintenance'), 'maintenance');
  for (const hash of ['#/refund-form', '#/media', '#/unknown', '']) {
    assert.equal(getStaffTabFromHash(hash), 'overview', hash);
  }
});

test('assistant history storage is separated by account', () => {
  const map = new Map();
  const storage = { getItem: key => map.get(key), setItem: (key, value) => map.set(key, value) };
  const first = createAssistantState(createConversation('first'));
  persistAssistantHistory(storage, first, 'assistant:accountant');
  assert.equal(loadAssistantHistory(storage, 'assistant:accountant').activeId, 'first');
  assert.notEqual(loadAssistantHistory(storage, 'assistant:cleaning').activeId, 'first');
});
