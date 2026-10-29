import test from 'node:test';
import assert from 'node:assert/strict';
import { parkingPeriod, parkingUsagePayload } from '../src/data/parkingReconciliation.js';
import { createAuthenticatedAccount, getStaffTabFromHash, canViewTab } from '../src/data/authSession.js';
import { getAllowedNav } from '../src/data/authSession.js';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

test('usage input normalizes plate and dates, retains observed references and optional missing data', () => {
  const form = { resource_id: 'park', source_reference: ' SYN ', starts_at: '2026-01-01T00:00:00Z', ends_at: '2026-01-02T00:00:00Z', completeness: 'PARTIAL' };
  const payload = parkingUsagePayload(form, [{ event_reference: ' E1 ', occurred_at: '2026-01-01T01:00:00Z', plate: ' ab 123 ', holder_account_id: 'observed-holder', slot_code: '', unit_id: '' }]);
  assert.equal(payload.entries[0].plate, 'AB123'); assert.equal(payload.source_reference, 'SYN');
  assert.equal(payload.entries[0].holder_account_id, 'observed-holder'); assert.equal(payload.entries[0].slot_code, null);
  assert.equal(payload.completeness, 'PARTIAL');
});

test('usage bounds and duplicate references fail before a command is sent', () => {
  const form = { starts_at: '2026-01-01T00:00:00Z', ends_at: '2026-01-02T00:00:00Z', source_reference: 'SYN' };
  const entry = { event_reference: 'E1', plate: 'SYN-01', occurred_at: '2026-01-01T01:00:00Z' };
  assert.throws(() => parkingUsagePayload(form, [entry, entry]), /không trùng/);
  assert.throws(() => parkingUsagePayload(form, [{ ...entry, occurred_at: form.ends_at }]), /khoảng nguồn/);
  assert.throws(() => parkingPeriod({ ...form, ends_at: form.starts_at }), /kết thúc/);
  assert.throws(() => parkingPeriod({ ...form, starts_at: 'invalid' }), /hợp lệ/);
});

test('all nine roles can reach their self account screen without gaining administration', () => {
  for (const role of ['admin', 'director', 'accountant', 'cskh', 'technical_lead', 'technician', 'cleaning', 'security', 'resident']) {
    const account = createAuthenticatedAccount({ account_id: 'self', roles: [role], allowed_sites: [] });
    assert.ok(canViewTab(account, 'settings'));
    assert.equal(getStaffTabFromHash('#/settings'), 'settings');
  }
});

test('rendered sidebar contains every allowed destination including account and parking workspace', async () => {
  const result = await build({ stdin: { contents: `import React from 'react'; import { renderToStaticMarkup } from 'react-dom/server'; import { Sidebar } from './src/components/Sidebar.jsx'; export const render = (account, navItems) => renderToStaticMarkup(<Sidebar account={account} navItems={navItems} currentTab="settings" taskCount={0} unreadCount={0} collapsed={false} allowedSites={[]} />);`, resolveDir: fileURLToPath(new URL('..', import.meta.url)), loader: 'jsx' }, bundle: true, write: false, platform: 'node', format: 'cjs' });
  const module = { exports: {} };
  new Function('require', 'module', 'exports', result.outputFiles[0].text)(createRequire(import.meta.url), module, module.exports);
  for (const role of ['admin', 'director', 'accountant', 'cskh', 'technical_lead', 'technician', 'cleaning', 'security']) {
    const account = createAuthenticatedAccount({ account_id: 'self', roles: [role], allowed_sites: [] });
    const nav = getAllowedNav(account); const html = module.exports.render(account, nav);
    for (const item of nav) assert.ok(html.includes(`aria-label="${item.label.replaceAll('&', '&amp;')}"`), `${role}: ${item.id} must be reachable`);
  }
});
