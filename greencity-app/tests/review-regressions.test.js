import test from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { createAuthenticatedAccount, getAllowedNav } from '../src/data/authSession.js';

const require = createRequire(import.meta.url);
const React = require('react');
const code = (await build({
  stdin: { contents: "export {ResidentPortalView} from './ResidentPortalView'; export {FinancialControlPanel} from './FinancialControlPanel'; export {StaffLogin} from './staff/StaffLogin'; export {BillingDesktopView} from './BillingDesktopView'; export {ParkingReconciliationPanel} from './ParkingReconciliationPanel';", resolveDir: fileURLToPath(new URL('../src/components/', import.meta.url)), loader: 'jsx' },
  bundle: true, platform: 'node', format: 'cjs', write: false,
  external: ['react', 'lucide-react'], loader: { '.css': 'empty' },
})).outputFiles[0].text;

// Separate hook slots for the parent and a rendered child; no browser/server.
function hookHost() {
  const scopes = new Map(); const effects = []; let slots; let index;
  const hooks = {
    useState(initial) { const i = index++; const current = slots; if (!(i in current)) current[i] = typeof initial === 'function' ? initial() : initial; return [current[i], value => { current[i] = typeof value === 'function' ? value(current[i]) : value; }]; },
    useRef(initial) { const i = index++; slots[i] ||= { current: initial }; return slots[i]; },
    useMemo(fn, deps) { const i = index++; if (!slots[i] || deps.some((v, n) => v !== slots[i].deps[n])) slots[i] = { deps, value: fn() }; return slots[i].value; },
    useEffect(fn, deps) { const i = index++; const current = slots; const previous = current[i]; if (!previous || deps.some((v, n) => v !== previous.deps[n])) effects.push(() => { previous?.cleanup?.(); current[i] = { deps, cleanup: fn() }; }); },
  };
  return {
    hooks,
    render(fn, scope = 'parent') { if (!scopes.has(scope)) scopes.set(scope, []); slots = scopes.get(scope); index = 0; return fn(); },
    flush() { effects.splice(0).forEach(fn => fn()); },
    unmount() { scopes.forEach(current => current.forEach(slot => slot?.cleanup?.())); },
  };
}
function components(host) {
  const module = { exports: {} };
  const icons = new Proxy({}, { get: () => () => null });
  new Function('require', 'module', 'exports', code)(name => name === 'react' ? { ...React, ...host.hooks } : name === 'lucide-react' ? icons : require(name), module, module.exports);
  return module.exports;
}
function elements(tree, predicate) {
  if (!tree || typeof tree !== 'object') return [];
  if (Array.isArray(tree)) return tree.flatMap(child => elements(child, predicate));
  return [...(predicate(tree) ? [tree] : []), ...elements(tree.props?.children, predicate)];
}
function text(tree) {
  if (typeof tree === 'string' || typeof tree === 'number') return String(tree);
  if (Array.isArray(tree)) return tree.map(text).join('');
  return tree?.props ? text(tree.props.children) : '';
}
const tab = (tree, label) => elements(tree, e => e.type === 'button' && text(e) === label)[0];
const state = tree => elements(tree, e => e.type?.name === 'State')[0].props.state;
const unitSelect = tree => elements(elements(tree, e => e.props?.className === 'portal-unit-selector')[0], e => e.type === 'select')[0];
async function settle(host, render, ready) {
  for (let i = 0; i < 12; i++) {
    const tree = render(); host.flush(); await new Promise(resolve => setImmediate(resolve));
    if (ready(tree)) return tree;
  }
  assert.fail('Component did not reach the expected state');
}
const account = { fullName: 'Cư dân', roles: ['resident'], activeSiteId: 's1', allowedSites: [{ id: 's1', name: 'Khu A' }] };
function residentClient(profile) {
  const calls = [];
  const record = (name, args, result) => { calls.push({ name, args }); return Promise.resolve(result); };
  return { calls, client: {
    portalGet: (...args) => { calls.push({ name: 'profile', args }); assert.equal(args[0], '/profile'); return profile(...args); },
    getResidentServiceRequestOptions: args => record('options', args, { units: [{ id: 'u1', unit_number: 'A-101', building_id: 'b1' }], categories: [], buildings: [] }),
    listResidentServiceRequests: args => record('requests', args, { items: [], total: 0 }),
    getResidentBillingSummary: (_asOf, args) => record('summary', args, { items: [], total_ar_balance_vnd: 0 }),
    listResidentBillingInvoices: (_asOf, args) => record('invoices', args, { items: [] }),
    listResidentBillingPayments: (_asOf, args) => record('payments', args, { items: [] }),
    listResidentNotifications: args => record('notifications', args, { items: [], unread_count: 0 }),
  } };
}
const unit = (id, permissions) => ({ id, unit_number: id, building_id: 'b1', permissions });
const profile = units => ({ selected_unit_id: units[0]?.id, units });
function browserHash(t) {
  const previous = globalThis.window;
  globalThis.window = { location: { hash: '' } };
  t.after(() => { if (previous === undefined) delete globalThis.window; else globalThis.window = previous; });
}
const privateCalls = calls => calls.filter(c => ['requests', 'summary', 'invoices', 'payments'].includes(c.name));

test('resident core tabs remain available during profile loading/failure and retry restores scoped data', async t => {
  browserHash(t);
  let reject; let retry = false;
  const pending = new Promise((_resolve, failure) => { reject = failure; });
  const { client, calls } = residentClient(() => retry ? Promise.resolve(profile([unit('u1', ['requests', 'finance'])])) : pending);
  const host = hookHost(); t.after(() => host.unmount()); const { ResidentPortalView } = components(host);
  const render = () => host.render(() => ResidentPortalView({ account, client }));
  let tree = render(); host.flush();
  for (const label of ['Yêu cầu dịch vụ', 'Công nợ & hóa đơn']) assert.ok(tab(tree, label));
  tab(tree, 'Yêu cầu dịch vụ').props.onClick(); tree = render(); host.flush();
  assert.ok(text(tree).includes('Đang xác minh quyền truy cập căn hộ'));
  assert.equal(privateCalls(calls).length, 0);
  reject(new Error('Synthetic profile failure'));
  tree = await settle(host, render, tree => !!state(tree).error);
  assert.ok(tab(tree, 'Yêu cầu dịch vụ')); assert.ok(tab(tree, 'Công nợ & hóa đơn'));
  assert.ok(text(tree).includes('Bạn có thể tải lại thông tin căn hộ'));
  assert.equal(privateCalls(calls).length, 0);
  retry = true; tab(tree, 'Tải lại thông tin căn hộ').props.onClick();
  tree = await settle(host, render, tree => elements(tree, e => e.type?.name === 'ResidentRequestsPanel').length > 0 && privateCalls(calls).length === 4);
  assert.ok(privateCalls(calls).every(c => c.args.unitId === 'u1'));
  assert.equal(state(tree).error, null);
});

test('resident with no effective unit has a help route without requesting private data', async t => {
  browserHash(t);
  const { client, calls } = residentClient(() => Promise.resolve(profile([])));
  const host = hookHost(); t.after(() => host.unmount()); const { ResidentPortalView } = components(host);
  const render = () => host.render(() => ResidentPortalView({ account, client }));
  let tree = await settle(host, render, tree => !state(tree).loading);
  tab(tree, 'Yêu cầu dịch vụ').props.onClick(); tree = render(); host.flush();
  assert.ok(text(tree).includes('Ban quản lý cần xác nhận căn hộ'));
  assert.equal(elements(tree, e => e.type?.name === 'ResidentRequestsPanel').length, 0);
  assert.equal(privateCalls(calls).length, 0);
  assert.equal(tab(tree, 'Tải lại thông tin căn hộ').props.disabled, false);
  tab(tree, 'Mở Trợ lý & CSKH').props.onClick(); tree = render(); host.flush();
  assert.equal(elements(tree, e => e.type?.name === 'GroundedAssistantPanel').length, 1);
  assert.equal(privateCalls(calls).length, 0);
});

test('resident denied or missing selected unit cannot inherit another unit permissions', async t => {
  browserHash(t);
  let current = profile([unit('u1', []), unit('u2', [])]);
  const { client, calls } = residentClient(() => Promise.resolve(current));
  const host = hookHost(); t.after(() => host.unmount()); const { ResidentPortalView } = components(host);
  const render = () => host.render(() => ResidentPortalView({ account, client }));
  let tree = await settle(host, render, tree => !state(tree).loading && calls.filter(c => c.name === 'profile').length === 2);
  tab(tree, 'Công nợ & hóa đơn').props.onClick(); tree = render(); host.flush();
  assert.ok(text(tree).includes('chưa cấp quyền')); assert.equal(privateCalls(calls).length, 0);
  current = profile([unit('u1', ['requests', 'finance'])]);
  unitSelect(tree).props.onChange({ target: { value: 'u2' } });
  tree = await settle(host, render, tree => !state(tree).loading && calls.filter(c => c.name === 'profile').length === 3);
  tab(tree, 'Yêu cầu dịch vụ').props.onClick(); tree = render(); host.flush();
  assert.ok(text(tree).includes('chưa cấp quyền'));
  assert.equal(elements(tree, e => e.type?.name === 'ResidentRequestsPanel').length, 0);
  assert.equal(privateCalls(calls).length, 0);
});

test('resident request validation summary links to each invalid field', async t => {
  browserHash(t);
  const { client } = residentClient(() => Promise.resolve(profile([unit('u1', ['requests'])])));
  const host = hookHost(); t.after(() => host.unmount()); const { ResidentPortalView } = components(host);
  const render = () => host.render(() => ResidentPortalView({ account, client }));
  let tree = await settle(host, render, tree => !state(tree).loading && unitSelect(tree).props.value === 'u1');
  tab(tree, 'Yêu cầu dịch vụ').props.onClick(); tree = render();
  const panel = elements(tree, e => e.type?.name === 'ResidentRequestsPanel')[0];
  const errors = { unit_id: 'Chọn căn', category_id: 'Chọn loại', title: 'Nhập tiêu đề', description: 'Nhập mô tả' };
  const form = host.render(() => panel.type({ ...panel.props, showCreate: true, createErrors: errors }), 'requests');
  const summary = elements(form, e => e.props?.className?.includes('resident-validation-summary'))[0];
  assert.deepEqual(elements(summary, e => e.type === 'a').map(e => e.props.href), ['#resident-create-unit', '#resident-create-category', '#resident-create-title', '#resident-create-description']);
  assert.equal(elements(form, e => e.props?.['aria-invalid'] === true).length, 4);
});

test('financial controls retry options before loading only the active tab', async t => {
  const calls = []; let failed = true;
  const client = { portalGet: async path => { calls.push(path); if (path === '/finance/options') { if (failed) throw new Error('Synthetic options failure'); return { periods: [] }; } assert.ok(['/finance/reviews', '/finance/commands'].includes(path)); return { items: [] }; } };
  const host = hookHost(); t.after(() => host.unmount()); const { FinancialControlPanel } = components(host);
  const render = () => host.render(() => FinancialControlPanel({ client, account }));
  let tree = await settle(host, render, tree => !!state(tree).error);
  assert.deepEqual(calls, ['/finance/options']);
  assert.equal(elements(tree, e => e.type?.name === 'State' && e.props.state.error).length, 1);
  assert.ok(elements(tree, e => e.type === 'button').every(e => e.props.disabled));
  failed = false; state(tree).refresh();
  tree = await settle(host, render, tree => elements(tree, e => e.type?.name === 'State').length === 2 && !elements(tree, e => e.type?.name === 'State')[1].props.state.loading);
  assert.deepEqual(calls, ['/finance/options', '/finance/options', '/finance/reviews']);
  tab(tree, 'Hồ sơ tài chính').props.onClick();
  tree = await settle(host, render, tree => calls.includes('/finance/commands') && !elements(tree, e => e.type?.name === 'State')[1].props.state.loading);
  assert.deepEqual(calls, ['/finance/options', '/finance/options', '/finance/reviews', '/finance/commands']);
  failed = true; state(tree).refresh();
  tree = await settle(host, render, tree => !!state(tree).error);
  assert.equal(elements(tree, e => e.type?.name === 'FinanceProposal').length, 0);
  assert.equal(calls.filter(path => path === '/finance/commands').length, 1);
});

test('login guidance stays within one text span and CSKH menu names personal settings clearly', () => {
  const host = hookHost(); const { StaffLogin } = components(host);
  const tree = host.render(() => StaffLogin({}));
  const disclaimer = elements(tree, e => e.props?.className === 'staff-login-disclaimer')[0];
  assert.ok(disclaimer);
  assert.ok(elements(disclaimer, e => e.type === 'span' && text(e).includes('Quyền truy cập được xác nhận')).length === 1);
  assert.ok(!text(disclaimer).includes('/auth/me'));
  const cskh = createAuthenticatedAccount({ account_id: 'staff', username: 'staff', full_name: 'CSKH', roles: ['cskh'], active_site_id: 's1', allowed_sites: [{ id: 's1', name: 'Khu A' }] });
  const labels = getAllowedNav(cskh).map(item => item.label);
  assert.ok(labels.includes('Nhập dữ liệu căn hộ')); assert.ok(labels.includes('Tài khoản'));
  assert.ok(!labels.includes('Tài khoản & Quyền')); assert.ok(!labels.includes('Kỹ thuật & Bảo trì'));
  host.unmount();
});

test('external billing revision reloads the active financial tab without resetting it', async t => {
  const calls = []; let revision = 0;
  const client = { portalGet: async path => { calls.push(path); return path === '/finance/options' ? { periods: [] } : { items: [] }; } };
  const host = hookHost(); t.after(() => host.unmount()); const { FinancialControlPanel } = components(host);
  const render = () => host.render(() => FinancialControlPanel({ client, account, revision }));
  let tree = await settle(host, render, tree => elements(tree, e => e.type?.name === 'State').length === 2 && !elements(tree, e => e.type?.name === 'State')[1].props.state.loading);
  tab(tree, 'Hồ sơ tài chính').props.onClick();
  tree = await settle(host, render, tree => calls.includes('/finance/commands') && !elements(tree, e => e.type?.name === 'State')[1].props.state.loading);
  revision++;
  tree = await settle(host, render, tree => calls.filter(path => path === '/finance/commands').length === 2 && !elements(tree, e => e.type?.name === 'State')[1].props.state.loading);
  assert.equal(tab(tree, 'Hồ sơ tài chính').props['aria-selected'], true);
  assert.equal(calls.filter(path => path === '/finance/options').length, 2);
  assert.equal(calls.filter(path => path === '/finance/reviews').length, 1);
});

test('draft billing run tells financial controls to reload after the command succeeds', async t => {
  const lists = {
    listBillingAccounts: [{ id: 'ba1', building_id: 'b1', account_number: 'BA1' }],
    listBillingFeePolicies: [{ code: 'PHI', building_id: 'b1', versions: [{ id: 'fv1', basis: 'UNIT_AREA_M2', published_at: '2026-10-01T00:00:00Z' }] }],
    listAccountingPeriods: [{ id: 'p1', building_id: 'b1', period_key: '2026-10', status: 'OPEN' }],
    listBillingRuns: [], listBillingInvoices: [], listBillingPayments: [], listUnmatchedPayments: [], listOverpaymentCredits: [],
  };
  const calls = []; const client = Object.fromEntries(Object.entries(lists).map(([name, items]) => [name, async () => ({ items })]));
  client.startBillingRun = async (body, options) => { calls.push({ body, options }); return { run_key: body.run_key, status: 'REVIEW' }; };
  const host = hookHost(); t.after(() => host.unmount()); const { BillingDesktopView } = components(host);
  const render = () => host.render(() => BillingDesktopView({ account, client }));
  const region = tree => elements(tree, e => e.props?.['aria-label'] === 'Tính nháp định kỳ')[0];
  const select = (tree, label) => elements(region(tree), e => e.type === 'select' && e.props.id === (label === 'Kỳ' ? 'billing-run-period' : 'billing-run-version'))[0];
  let tree = await settle(host, render, tree => !!region(tree));
  const control = tree => elements(tree, e => e.type?.name === 'FinancialControlPanel')[0];
  assert.equal(control(tree).props.revision, 0);
  assert.ok(text(region(tree)).includes('Bản tính chưa ghi công nợ'));
  select(tree, 'Kỳ').props.onChange({ target: { value: 'p1' } }); tree = render();
  select(tree, 'Version phí').props.onChange({ target: { value: 'fv1' } }); tree = render();
  elements(region(tree), e => e.type === 'form')[0].props.onSubmit({ preventDefault() {} });
  tree = await settle(host, render, tree => control(tree).props.revision === 1 && !!region(tree));
  assert.equal(calls.length, 1); assert.ok(calls[0].options.idempotencyKey);
  assert.equal(calls[0].body.accounting_period_id, 'p1'); assert.equal(calls[0].body.fee_policy_version_id, 'fv1');
  await control(tree).props.onChange(); tree = render();
  assert.equal(control(tree).props.revision, 1); // Child refresh must not cause a parent/child reload loop.
  client.listBillingFeePolicies = async () => ({ items: lists.listBillingFeePolicies.map(p => ({ ...p, versions: p.versions.map(v => ({ ...v, published_at: null })) })) });
  await control(tree).props.onChange(); tree = render();
  elements(region(tree), e => e.type === 'form')[0].props.onSubmit({ preventDefault() {} });
  assert.equal(calls.length, 1, 'A selected version invalidated by refresh must not start another run');
  client.listBillingFeePolicies = async () => ({ items: [...lists.listBillingFeePolicies] });
  client.listAccountingPeriods = async () => ({ items: lists.listAccountingPeriods.map(p => ({ ...p, status: 'LOCKED' })) });
  await control(tree).props.onChange(); tree = render();
  elements(region(tree), e => e.type === 'form')[0].props.onSubmit({ preventDefault() {} });
  assert.equal(calls.length, 1, 'A period locked after selection must not start another run');
});

test('parking detail ignores late results and errors, supports retry, and aborts on unmount', async t => {
  for (const obsoleteFailure of [false, true]) await t.test(obsoleteFailure ? 'late error' : 'late response', async t => {
    const pending = [];
    const reports = [{ id: 'report-a' }, { id: 'report-b' }];
    const client = { portalGet(path, _params, options) {
      if (path === '/resources') return Promise.resolve({ items: [] });
      if (path === '/control/parking-reconciliations') return Promise.resolve({ items: reports });
      return new Promise((resolve, reject) => pending.push({ path, options, resolve, reject }));
    } };
    const host = hookHost(); t.after(() => host.unmount());
    const { ParkingReconciliationPanel } = components(host);
    const render = () => host.render(() => ParkingReconciliationPanel({ client, buildingId: 'b1', roles: ['admin'] }));
    const list = tree => elements(tree, e => e.type?.name === 'Records' && e.props.items === reports)[0];
    const open = (tree, row) => elements(list(tree).props.children(row), e => e.type === 'button')[0].props.onClick();
    const detailState = tree => elements(tree, e => e.type?.name === 'State').at(-1).props.state;
    const snapshot = id => ({ id, policy_reference: `Căn cứ ${id}`, snapshot: { vehicles: [], slots: [], usage_batches: [] }, findings: [] });
    let tree = await settle(host, render, tree => !!list(tree));
    open(tree, reports[0]); tree = render(); host.flush();
    open(tree, reports[1]); tree = render(); host.flush();
    assert.equal(pending[0].options.signal.aborted, true);
    assert.equal(detailState(tree).loading, true);
    pending[1].resolve(snapshot('report-b'));
    tree = await settle(host, render, tree => detailState(tree).data?.id === 'report-b');
    if (obsoleteFailure) pending[0].reject(new Error('Lỗi từ báo cáo cũ'));
    else pending[0].resolve(snapshot('report-a'));
    await new Promise(resolve => setImmediate(resolve)); tree = render();
    assert.equal(detailState(tree).data.id, 'report-b'); assert.equal(detailState(tree).error, null);
    open(tree, reports[1]); tree = render(); host.flush();
    assert.equal(detailState(tree).data, null);
    pending[2].reject(new Error('Tải chi tiết chưa thành công'));
    tree = await settle(host, render, tree => !!detailState(tree).error);
    detailState(tree).refresh(); tree = render(); host.flush();
    pending[3].resolve(snapshot('report-b'));
    tree = await settle(host, render, tree => detailState(tree).data?.id === 'report-b');
    open(tree, reports[0]); render(); host.flush(); host.unmount();
    assert.equal(pending[4].options.signal.aborted, true);
    pending[4].resolve(snapshot('report-a'));
  });
});
