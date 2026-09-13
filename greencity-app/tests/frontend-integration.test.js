import test from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { ApiError, createApiClient } from '../src/services/apiClient.js';
import { canViewTab, createAuthenticatedAccount } from '../src/data/authSession.js';
import { mapServiceRequest } from '../src/data/serviceRequestView.js';

const correlationId = '11111111-1111-4111-8111-111111111111';
const userInfo = (roles = ['cskh']) => ({
  account_id: randomUUID(),
  tenant_id: randomUUID(),
  username: 'cskh.integration',
  full_name: 'Nhân viên CSKH',
  roles,
  active_site_id: '22222222-2222-4222-8222-222222222222',
  allowed_sites: [{ id: '22222222-2222-4222-8222-222222222222', code: 'CENTRAL', name: 'GreenCity Central' }],
});

const unit360 = (id = '33333333-3333-4333-8333-333333333333') => ({
  id,
  unit_number: 'A-1201',
  floor: 12,
  area_m2: 72.5,
  status: 'OCCUPIED',
  version: 3,
  building_id: '44444444-4444-4444-8444-444444444444',
  building_code: 'A',
  building_name: 'Tòa A',
  site_id: '22222222-2222-4222-8222-222222222222',
  site_code: 'CENTRAL',
  site_name: 'GreenCity Central',
  residents_visible: true,
  residents: [{
    person_id: '55555555-5555-4555-8555-555555555555',
    full_name: 'Nguyễn Minh Anh',
    phone_masked: '09******12',
    email_masked: 'n***@example.test',
    relationship_type: 'OWNER',
    is_active: true,
    ownership_ratio: '1.0000',
    valid_from: '2025-01-01',
    valid_to: null,
  }],
});

const jsonResponse = (payload, status = 200, id = correlationId) => new Response(JSON.stringify(payload), {
  status,
  headers: { 'Content-Type': 'application/json', 'X-Correlation-ID': id },
});

test('API client performs login then /auth/me and keeps the issued token in memory', async () => {
  const issuedToken = randomUUID();
  const calls = [];
  const client = createApiClient({
    baseUrl: 'https://api.example.test/api/v1',
    correlationIdFactory: () => correlationId,
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      if (url.endsWith('/auth/login')) return jsonResponse({ access_token: issuedToken, token_type: 'Bearer', user: userInfo(['admin']) });
      return jsonResponse(userInfo(['cskh']));
    },
  });

  const me = await client.authenticate('cskh.integration', 'local-test-password');

  assert.deepEqual(calls.map(call => call.url), [
    'https://api.example.test/api/v1/auth/login',
    'https://api.example.test/api/v1/auth/me',
  ]);
  assert.deepEqual(JSON.parse(calls[0].options.body), { username: 'cskh.integration', password: 'local-test-password' });
  assert.equal(calls[0].options.headers.Authorization, undefined);
  assert.equal(calls[1].options.headers.Authorization, `Bearer ${issuedToken}`);
  assert.deepEqual(me.roles, ['cskh'], 'the UI identity must come from /auth/me, not the login response');
  assert.equal(client.hasSession(), true);
});

test('service-request query is allow-listed and Authorization is attached', async () => {
  const issuedToken = randomUUID();
  const calls = [];
  const responses = [
    jsonResponse({ access_token: issuedToken }),
    jsonResponse(userInfo()),
    jsonResponse({ items: [], page: 2, page_size: 10, total: 0 }),
  ];
  const client = createApiClient({ baseUrl: '/api/v1', fetchImpl: async (url, options) => { calls.push({ url, options }); return responses.shift(); } });
  await client.authenticate('cskh.integration', 'local-test-password');
  await client.listServiceRequests({ status: 'IN_PROGRESS', page: 2, page_size: 10, tenant_id: randomUUID(), role: 'admin', building_id: randomUUID() });

  assert.equal(calls[2].url, '/api/v1/service-requests?status=IN_PROGRESS&page=2&page_size=10');
  assert.equal(calls[2].options.headers.Authorization, `Bearer ${issuedToken}`);
  assert.ok(!calls[2].url.includes('tenant_id'));
  assert.ok(!calls[2].url.includes('building_id'));
  assert.ok(!calls[2].url.includes('role='));
});

test('Unit 360 sends only the Unit ID path and validates the response contract', async () => {
  const issuedToken = randomUUID();
  const unitId = '33333333-3333-4333-8333-333333333333';
  const calls = [];
  const responses = [
    jsonResponse({ access_token: issuedToken }),
    jsonResponse(userInfo()),
    jsonResponse(unit360(unitId)),
  ];
  const client = createApiClient({ baseUrl: '/api/v1', fetchImpl: async (url, options) => { calls.push({ url, options }); return responses.shift(); } });
  await client.authenticate('cskh.integration', 'local-test-password');
  const result = await client.getUnit360(unitId, { tenant_id: randomUUID(), role: 'admin', site_id: randomUUID(), building_id: randomUUID() });

  assert.equal(calls[2].url, `/api/v1/units/${unitId}/360`);
  assert.equal(calls[2].options.headers.Authorization, `Bearer ${issuedToken}`);
  assert.equal(new URL(calls[2].url, 'https://local.test').search, '');
  assert.equal(result.residents[0].phone_masked, '09******12');
  assert.equal(result.residents_visible, true);
});

test('Unit 360 hidden projection keeps an explicit empty residents list', async () => {
  const unitId = '33333333-3333-4333-8333-333333333333';
  const hiddenProjection = { ...unit360(unitId), residents_visible: false, residents: [] };
  const client = createApiClient({ fetchImpl: async () => jsonResponse(hiddenProjection) });

  const result = await client.getUnit360(unitId);
  assert.equal(result.residents_visible, false);
  assert.deepEqual(result.residents, []);

  const invalidProjection = { ...hiddenProjection };
  delete invalidProjection.residents;
  const invalidClient = createApiClient({ fetchImpl: async () => jsonResponse(invalidProjection) });
  await assert.rejects(
    invalidClient.getUnit360(unitId),
    error => error instanceof ApiError && error.code === 'ERR-INVALID-RESPONSE',
  );
});

test('401 clears the in-memory session and notifies the app', async () => {
  let unauthorized = null;
  const responses = [
    jsonResponse({ access_token: randomUUID() }),
    jsonResponse(userInfo()),
    jsonResponse({ error: { code: 'ERR-UNAUTHORIZED', message: 'Phiên hết hạn', correlation_id: correlationId } }, 401),
  ];
  const client = createApiClient({ fetchImpl: async () => responses.shift(), onUnauthorized: error => { unauthorized = error; } });
  await client.authenticate('cskh.integration', 'local-test-password');

  await assert.rejects(client.listServiceRequests(), error => error instanceof ApiError && error.status === 401);
  assert.equal(client.hasSession(), false);
  assert.equal(unauthorized.correlationId, correlationId);
});

test('site switch sends only site_id, installs the new token, then trusts /auth/me', async () => {
  const oldToken = randomUUID();
  const newToken = randomUUID();
  const nextSiteId = '66666666-6666-4666-8666-666666666666';
  const calls = [];
  const currentUser = userInfo();
  currentUser.allowed_sites.push({ id: nextSiteId, code: 'EAST', name: 'GreenCity East' });
  const switchedUser = { ...currentUser, active_site_id: nextSiteId, roles: ['cleaning'] };
  const responses = [
    jsonResponse({ access_token: oldToken }),
    jsonResponse(currentUser),
    jsonResponse({ access_token: newToken, user: { ...switchedUser, roles: ['admin'] } }),
    jsonResponse(switchedUser),
  ];
  const client = createApiClient({ fetchImpl: async (url, options) => { calls.push({ url, options }); return responses.shift(); } });
  await client.authenticate('cskh.integration', 'local-test-password');
  const me = await client.switchSite(nextSiteId, { tenant_id: randomUUID(), role: 'admin', building_id: randomUUID() });

  assert.equal(calls[2].url, '/api/v1/auth/switch-site');
  assert.deepEqual(JSON.parse(calls[2].options.body), { site_id: nextSiteId });
  assert.equal(calls[2].options.headers.Authorization, `Bearer ${oldToken}`);
  assert.equal(calls[3].url, '/api/v1/auth/me');
  assert.equal(calls[3].options.headers.Authorization, `Bearer ${newToken}`);
  assert.deepEqual(me.roles, ['cleaning'], 'the switched UI identity must come from the follow-up /auth/me');
});

test('a 401 response from the previous site cannot clear the switched session', async () => {
  const oldToken = randomUUID();
  const newToken = randomUUID();
  const nextSiteId = '66666666-6666-4666-8666-666666666666';
  let resolveOldRequest;
  let unauthorizedCalls = 0;
  const oldRequestResponse = new Promise(resolve => { resolveOldRequest = resolve; });
  let meCalls = 0;
  const client = createApiClient({
    onUnauthorized: () => { unauthorizedCalls += 1; },
    fetchImpl: async url => {
      if (url.endsWith('/auth/login')) return jsonResponse({ access_token: oldToken });
      if (url.endsWith('/auth/me')) {
        meCalls += 1;
        const me = userInfo();
        if (meCalls > 1) {
          me.active_site_id = nextSiteId;
          me.allowed_sites.push({ id: nextSiteId, code: 'EAST', name: 'GreenCity East' });
        }
        return jsonResponse(me);
      }
      if (url.includes('/service-requests?')) return oldRequestResponse;
      if (url.endsWith('/auth/switch-site')) return jsonResponse({ access_token: newToken });
      throw new Error(`Unexpected URL: ${url}`);
    },
  });
  await client.authenticate('cskh.integration', 'local-test-password');
  const oldRequest = client.listServiceRequests();
  await client.switchSite(nextSiteId);
  resolveOldRequest(jsonResponse({ error: { code: 'ERR-UNAUTHORIZED', message: 'Old site token rejected' } }, 401));

  await assert.rejects(oldRequest, error => error.name === 'AbortError');
  assert.equal(unauthorizedCalls, 0);
  assert.equal(client.hasSession(), true);
});

test('scope and network failures keep actionable structured errors', async () => {
  const scopeResponses = [
    jsonResponse({ access_token: randomUUID() }),
    jsonResponse(userInfo()),
    jsonResponse({ error: { code: 'ERR-SCOPE-NOTFOUND', message: 'Không tìm thấy dữ liệu.', correlation_id: correlationId } }, 404),
  ];
  const scopedClient = createApiClient({ fetchImpl: async () => scopeResponses.shift() });
  await scopedClient.authenticate('cskh.integration', 'local-test-password');
  await assert.rejects(scopedClient.listServiceRequests(), error => error.code === 'ERR-SCOPE-NOTFOUND' && error.correlationId === correlationId);

  const networkClient = createApiClient({ fetchImpl: async () => { throw new TypeError('offline'); }, correlationIdFactory: () => correlationId });
  await assert.rejects(networkClient.authenticate('cskh.integration', 'local-test-password'), error => error.code === 'ERR-NETWORK' && error.correlationId === correlationId);
});

test('account menus are derived only from roles returned by /auth/me', () => {
  const cskh = createAuthenticatedAccount({ ...userInfo(['cskh']), role: 'admin', menu: ['settings'] });
  assert.ok(canViewTab(cskh, 'tasks'));
  assert.ok(canViewTab(cskh, 'residents'));
  assert.ok(!canViewTab(cskh, 'settings'));
  assert.ok(!canViewTab(cskh, 'refund-form'));
  assert.match(cskh.scope, /Phạm vi do máy chủ cấp/);

  const siteTwo = '66666666-6666-4666-8666-666666666666';
  const switched = createAuthenticatedAccount({
    ...userInfo(['cskh']),
    active_site_id: siteTwo,
    allowed_sites: [...userInfo(['cskh']).allowed_sites, { id: siteTwo, code: 'EAST', name: 'GreenCity East' }],
  });
  assert.notEqual(cskh.workspaceKey, switched.workspaceKey, 'changing active site must remount and reset the workspace state');

  const cleaning = createAuthenticatedAccount(userInfo(['cleaning']));
  assert.ok(!canViewTab(cleaning, 'tasks'));
  assert.deepEqual(cleaning.menu, ['overview', 'notifications']);

  const security = createAuthenticatedAccount(userInfo(['security']));
  assert.ok(canViewTab(security, 'residents'));
  assert.ok(!canViewTab(security, 'tasks'));

  const technician = createAuthenticatedAccount(userInfo(['technician']));
  assert.ok(!canViewTab(technician, 'residents'), 'Unit 360 stays hidden until backend exposes technician assignment scope');
});

test('service-request adapter exposes the fields needed by the read-only table', () => {
  const task = mapServiceRequest({
    id: '33333333-3333-4333-8333-333333333333',
    code: 'SR-2026-001',
    title: 'Kiểm tra đèn hành lang',
    unit_number: 'A-1201',
    building_code: 'A',
    building_name: 'Tòa A',
    status: 'IN_PROGRESS',
    priority: 'HIGH',
    sla_deadline: '2026-09-12T02:00:00Z',
    created_at: '2026-09-11T02:00:00Z',
  }, new Date('2026-09-12T03:00:00Z'));

  assert.equal(task.id, 'SR-2026-001');
  assert.equal(task.recordId, '33333333-3333-4333-8333-333333333333');
  assert.equal(task.location, 'Tòa A · Căn A-1201');
  assert.equal(task.status, 'Đang xử lý');
  assert.equal(task.priorityLabel, 'Cao');
  assert.equal(task.isOverdue, true);
  assert.notEqual(task.createdAt, 'Không xác định');
});
