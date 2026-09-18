import test from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { ApiError, createApiClient } from '../src/services/apiClient.js';
import { canAccessAuditEvents, canAccessCleaning, canAccessExecutiveDashboard, canAccessParcel, canAccessSecurity, canCreateServiceRequests, canManageCleaning, canManageOutbox, canManageSecurity, canViewTab, createAuthenticatedAccount } from '../src/data/authSession.js';
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

const cleaningTask = (overrides = {}) => ({
  id: randomUUID(), shift_id: randomUUID(), route_id: randomUUID(), route_code: 'CLN-LOBBY', route_name: 'Tuyến sảnh',
  area_id: randomUUID(), area_code: 'LOBBY', area_name: 'Sảnh chính', tenant_id: randomUUID(), site_id: randomUUID(),
  building_id: randomUUID(), assigned_to_id: null, status: 'PLANNED', scheduled_start_at: '2026-09-13T01:00:00Z',
  scheduled_end_at: '2026-09-13T03:00:00Z', started_at: null, submitted_at: null, accepted_at: null,
  accepted_by_id: null, rework_work_order_id: null, rework_case_id: null, version: 1,
  checklist: [{ id: randomUUID(), position: 1, label: 'Sàn sạch', is_required: true, result: 'PENDING', note: null, performed_by_id: null, performed_at: null, version: 1 }],
  ...overrides,
});

const securityWindow = (overrides = {}) => ({
  id: randomUUID(), security_shift_id: randomUUID(), patrol_point_id: randomUUID(), patrol_point_code: 'SEC-LOBBY', patrol_point_name: 'Sảnh chính',
  building_id: randomUUID(), window_start_at: '2026-09-14T01:00:00Z', window_end_at: '2026-09-14T01:30:00Z', status: 'SCHEDULED',
  missed_reason: null, completed_at: null, version: 1, logs: [], ...overrides,
});

const securityShift = (overrides = {}) => {
  const window = overrides.patrol_windows?.[0] || securityWindow();
  return {
    id: window.security_shift_id, tenant_id: randomUUID(), site_id: randomUUID(), building_id: window.building_id,
    assigned_to_id: randomUUID(), scheduled_start_at: '2026-09-14T01:00:00Z', scheduled_end_at: '2026-09-14T03:00:00Z',
    status: 'PLANNED', version: 1, handoffs: [], visitors: [], patrol_windows: [{ ...window, security_shift_id: window.security_shift_id }, ...((overrides.patrol_windows || []).slice(1))], ...overrides,
  };
};

const securityIncident = (overrides = {}) => ({
  id: randomUUID(), patrol_window_id: randomUUID(), building_id: randomUUID(), code: 'INC-TEST-001', incident_type: 'FIRE', severity: 'HIGH',
  status: 'NEW', title: 'Khói tại phòng kỹ thuật', description: 'Kích hoạt quy trình PCCC.', occurred_at: '2026-09-14T01:10:00Z',
  reported_by_id: randomUUID(), conclusion: null, resolved_at: null, closed_at: null, version: 1,
  escalations: [{ id: randomUUID(), target_role: 'security', acknowledgement: null }, { id: randomUUID(), target_role: 'director', acknowledgement: null }], evidence: [], ...overrides,
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

test('assistant client posts only the message with the authenticated session and correlation ID', async () => {
  const issuedToken = randomUUID();
  const calls = [];
  const client = createApiClient({
    baseUrl: '/api/v1',
    correlationIdFactory: () => correlationId,
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      if (url.endsWith('/auth/login')) return jsonResponse({ access_token: issuedToken });
      if (url.endsWith('/auth/me')) return jsonResponse(userInfo());
      return jsonResponse({ reply: 'Câu trả lời từ backend' });
    },
  });

  await client.authenticate('cskh.integration', 'local-test-password');
  const reply = await client.chatAssistant('  Xin chào  ', {
    tenant_id: randomUUID(), site_id: randomUUID(), building_id: randomUUID(), role: 'admin',
  });

  assert.equal(reply, 'Câu trả lời từ backend');
  assert.equal(calls[2].url, '/api/v1/assistant/chat');
  assert.equal(calls[2].options.method, 'POST');
  assert.deepEqual(JSON.parse(calls[2].options.body), { message: 'Xin chào' });
  assert.equal(calls[2].options.headers.Authorization, `Bearer ${issuedToken}`);
  assert.equal(calls[2].options.headers['X-Correlation-ID'], correlationId);
  assert.ok(!JSON.stringify(calls[2].options).match(/tenant_id|site_id|building_id|role/));
});

test('assistant client rejects malformed backend replies', async () => {
  const client = createApiClient({ fetchImpl: async () => jsonResponse({ answer: 'wrong field' }) });
  await assert.rejects(client.chatAssistant('Xin chào'), error => (
    error instanceof ApiError && error.code === 'ERR-INVALID-RESPONSE'
  ));
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

test('parcel client keeps scope server-owned and sends stable command contracts', async () => {
  const issuedToken = randomUUID();
  const buildingId = randomUUID();
  const unitId = randomUUID();
  const parcelId = randomUUID();
  const calls = [];
  const parcel = {
    id: parcelId, tenant_id: randomUUID(), site_id: randomUUID(), building_id: buildingId, unit_id: unitId,
    recipient_person_id: null, parcel_code: 'P-UX-001', carrier_reference: 'carrier-001',
    recipient_name_snapshot: 'Người nhận demo', recipient_contact_snapshot: '09******12', storage_location: 'Locker A-01',
    pin_attempt_count: 0, pin_locked_until: null, status: 'RECEIVED', received_at: '2026-09-17T02:00:00Z',
    ready_for_pickup_at: null, handed_over_at: null, handed_over_by_id: null, exception_reason: null,
    created_by_id: randomUUID(), updated_by_id: randomUUID(), version: 1,
    created_at: '2026-09-17T02:00:00Z', updated_at: '2026-09-17T02:00:00Z',
  };
  const ready = { ...parcel, status: 'READY_FOR_PICKUP', ready_for_pickup_at: '2026-09-17T02:05:00Z', version: 2 };
  const handed = { ...ready, status: 'HANDED_OVER', handed_over_at: '2026-09-17T02:06:00Z', handed_over_by_id: randomUUID(), version: 3 };
  const responses = [
    jsonResponse({ access_token: issuedToken }), jsonResponse(userInfo(['security'])),
    jsonResponse({ items: [parcel], page: 1, page_size: 50, total: 1 }),
    jsonResponse(parcel, 201), jsonResponse(ready), jsonResponse(handed),
  ];
  const client = createApiClient({ baseUrl: '/api/v1', fetchImpl: async (url, options) => { calls.push({ url, options }); return responses.shift(); } });
  await client.authenticate('security.integration', 'local-test-password');
  const listed = await client.listParcels({ status: 'RECEIVED', buildingId, tenant_id: randomUUID(), role: 'admin' });
  await client.createParcel({ building_id: buildingId, unit_id: unitId, parcel_code: parcel.parcel_code, recipient_name_snapshot: parcel.recipient_name_snapshot, pin: '1234', tenant_id: randomUUID(), site_id: randomUUID(), role: 'admin' }, { idempotencyKey: 'parcel-create-ux-001' });
  await client.markParcelReady(parcelId, 1, { idempotencyKey: 'parcel-ready-ux-001' });
  await client.handoverParcel(parcelId, { expected_version: 2, pin: '1234' }, { idempotencyKey: 'parcel-handover-ux-001' });

  assert.equal(listed.items[0].id, parcelId);
  assert.equal(calls[2].url, `/api/v1/parcels?${new URLSearchParams({ page: '1', page_size: '50', status: 'RECEIVED', building_id: buildingId })}`);
  assert.deepEqual(JSON.parse(calls[3].options.body), {
    building_id: buildingId, unit_id: unitId, recipient_person_id: null, parcel_code: parcel.parcel_code,
    carrier_reference: null, recipient_name_snapshot: parcel.recipient_name_snapshot,
    recipient_contact_snapshot: null, storage_location: null, pin: '1234',
  });
  assert.equal(calls[3].options.headers['Idempotency-Key'], 'parcel-create-ux-001');
  assert.deepEqual(JSON.parse(calls[4].options.body), { expected_version: 1 });
  assert.deepEqual(JSON.parse(calls[5].options.body), { expected_version: 2, pin: '1234' });
  assert.ok(calls.slice(2).every(call => call.options.headers.Authorization === `Bearer ${issuedToken}`));
  assert.ok(calls.slice(2).every(call => !JSON.stringify(call).match(/tenant_id|site_id|role/)));
  assert.equal(canAccessParcel({ roles: ['security'] }), true);
  assert.equal(createAuthenticatedAccount(userInfo(['security'])).menu.includes('parcels'), true);
});

test('parcel linkage and evidence client keep private file and audit requests scoped', async () => {
  const issuedToken = randomUUID();
  const parcelId = randomUUID();
  const attachmentId = randomUUID();
  const incidentId = randomUUID();
  const caseView = {
    id: randomUUID(), source_work_order_id: null, source_parcel_id: parcelId,
    building_id: randomUUID(), reason: 'Locker audit', status: 'NEW',
    created_by_id: randomUUID(), updated_by_id: randomUUID(), version: 1,
    created_at: '2026-09-17T02:00:00Z', updated_at: '2026-09-17T02:00:00Z',
  };
  const incidentView = {
    id: incidentId, parcel_id: parcelId, patrol_window_id: null, building_id: caseView.building_id,
    code: 'INC-P-001', incident_type: 'SECURITY', severity: 'LOW', status: 'NEW', title: 'Parcel incident',
    description: 'Locker audit', occurred_at: '2026-09-17T02:00:00Z', reported_by_id: randomUUID(), version: 1,
  };
  const evidence = {
    id: attachmentId, parcel_id: parcelId, original_name: 'locker.png', mime_type: 'image/png',
    size_bytes: 32, sha256: 'a'.repeat(64), created_at: '2026-09-17T02:00:00Z',
  };
  const timeline = { items: [{ id: randomUUID(), event_type: 'ParcelCaseOpened', action: 'create', resource_type: 'Case', resource_id: caseView.id, correlation_id: correlationId, reason: 'Locker audit', before_data: null, after_data: { status: 'NEW' }, created_at: '2026-09-17T02:00:00Z' }] };
  const calls = [];
  const responses = [
    jsonResponse({ access_token: issuedToken }), jsonResponse(userInfo(['security'])),
    jsonResponse(caseView), jsonResponse(caseView, 201), jsonResponse(incidentView), jsonResponse(incidentView),
    jsonResponse({ items: [evidence] }), jsonResponse(evidence, 201),
    jsonResponse({ url: `/api/v1/parcels/${parcelId}/evidence/${attachmentId}/content?signed_token=signed`, expires_at: '2026-09-17T03:00:00Z' }),
    jsonResponse(timeline),
  ];
  const client = createApiClient({ baseUrl: '/api/v1', fetchImpl: async (url, options) => { calls.push({ url, options }); return responses.shift(); } });
  await client.authenticate('security.integration', 'local-test-password');
  await client.getParcelCase(parcelId);
  await client.openParcelCase(parcelId, 'Locker audit', { idempotencyKey: 'parcel-case-001' });
  await client.getParcelIncident(parcelId);
  await client.linkParcelIncident(parcelId, { incident_id: incidentId, reason: 'Chốt bảo vệ' }, { idempotencyKey: 'parcel-incident-001' });
  await client.listParcelEvidence(parcelId);
  await client.uploadParcelEvidence(parcelId, new Uint8Array([1, 2, 3]), { idempotencyKey: 'parcel-evidence-001', fileName: 'locker.png', contentType: 'image/png' });
  const signed = await client.getParcelEvidenceLink(parcelId, attachmentId);
  await client.getParcelTimeline(parcelId);

  assert.equal(calls[2].url, `/api/v1/parcels/${parcelId}/case`);
  assert.equal(calls[3].options.headers['Idempotency-Key'], 'parcel-case-001');
  assert.equal(calls[4].url, `/api/v1/parcels/${parcelId}/incident`);
  assert.deepEqual(JSON.parse(calls[5].options.body), { incident_id: incidentId, reason: 'Chốt bảo vệ' });
  assert.equal(calls[6].url, `/api/v1/parcels/${parcelId}/evidence`);
  assert.equal(calls[7].options.headers['Content-Type'], 'image/png');
  assert.equal(calls[7].options.headers['X-File-Name'], 'locker.png');
  assert.equal(calls[8].url, `/api/v1/parcels/${parcelId}/evidence/${attachmentId}/signed-link`);
  assert.equal(signed.url.includes('signed_token='), true);
  assert.equal(calls[9].url, `/api/v1/parcels/${parcelId}/timeline`);
  assert.ok(calls.slice(2).every(call => call.options.headers.Authorization === `Bearer ${issuedToken}`));
  assert.ok(calls.slice(2).every(call => !JSON.stringify(call).match(/tenant_id|site_id|role/)));
});

test('parcel evidence view replays signed-link with Bearer and omits blank optional incident reason', async () => {
  const issuedToken = randomUUID();
  const parcelId = randomUUID();
  const attachmentId = randomUUID();
  const incidentView = {
    id: randomUUID(), parcel_id: parcelId, patrol_window_id: null, building_id: randomUUID(),
    code: 'INC-P-OPTIONAL', incident_type: 'SECURITY', severity: 'LOW', status: 'NEW',
    title: 'Parcel incident', description: 'Optional reason', occurred_at: '2026-09-17T02:00:00Z',
    reported_by_id: randomUUID(), version: 1,
  };
  const imageBytes = new Uint8Array([137, 80, 78, 71, 1, 2, 3]);
  const calls = [];
  const client = createApiClient({
    baseUrl: '/api/v1',
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      if (url.endsWith('/auth/login')) return jsonResponse({ access_token: issuedToken });
      if (url.endsWith('/auth/me')) return jsonResponse(userInfo(['security']));
      if (url.endsWith('/incident-link')) return jsonResponse(incidentView);
      if (url.endsWith('/signed-link')) return jsonResponse({
        url: `/api/v1/parcels/${parcelId}/evidence/${attachmentId}/content?signed_token=signed`,
        expires_at: '2026-09-17T03:00:00Z',
      });
      if (url.includes('/content?signed_token=')) return new Response(imageBytes, {
        status: 200, headers: { 'Content-Type': 'image/png', 'X-Correlation-ID': correlationId },
      });
      return jsonResponse({ error: { code: 'ERR-NOTFOUND', message: 'not found' } }, 404);
    },
  });

  await client.authenticate('security.integration', 'local-test-password');
  await client.linkParcelIncident(parcelId, { incident_id: randomUUID(), reason: '   ' }, { idempotencyKey: 'parcel-incident-optional-001' });
  const { downloadParcelEvidence } = client;
  const downloaded = await downloadParcelEvidence(parcelId, attachmentId);

  const linkCall = calls.find(call => call.url.endsWith('/incident-link'));
  const linkBody = JSON.parse(linkCall.options.body);
  assert.equal(typeof linkBody.incident_id, 'string');
  assert.equal(Object.hasOwn(linkBody, 'reason'), false);
  assert.equal(downloaded.contentType, 'image/png');
  assert.deepEqual(new Uint8Array(await downloaded.blob.arrayBuffer()), imageBytes);
  const contentCall = calls.find(call => call.url.includes('/content?signed_token='));
  assert.equal(contentCall.options.headers.Authorization, `Bearer ${issuedToken}`);
});

test('CSKH form choices and create payload stay scoped to server-issued resources', async () => {
  const issuedToken = randomUUID();
  const buildingId = randomUUID();
  const categoryId = randomUUID();
  const unitId = randomUUID();
  const calls = [];
  const formOptions = {
    buildings: [{ id: buildingId, code: 'A', name: 'Tòa A' }],
    categories: [{ id: categoryId, code: 'TECHNICAL', name: 'Kỹ thuật', building_id: buildingId }],
    units: [{ id: unitId, unit_number: 'A-1201', building_id: buildingId }],
  };
  const responses = [
    jsonResponse({ access_token: issuedToken }),
    jsonResponse(userInfo()),
    jsonResponse({ buildings: formOptions.buildings, categories: [], units: [] }),
    jsonResponse(formOptions),
    jsonResponse({ id: randomUUID(), code: 'SR-NEW-001', title: 'Kiểm tra đèn', priority: 'HIGH', status: 'NEW' }, 201),
  ];
  const client = createApiClient({ baseUrl: '/api/v1', fetchImpl: async (url, options) => { calls.push({ url, options }); return responses.shift(); } });
  await client.authenticate('cskh.integration', 'local-test-password');
  await client.getServiceRequestFormOptions({ tenant_id: randomUUID(), role: 'admin' });
  const options = await client.getServiceRequestFormOptions({ buildingId, tenant_id: randomUUID(), role: 'admin', site_id: randomUUID() });
  const created = await client.createServiceRequest({
    category_id: categoryId,
    building_id: buildingId,
    unit_id: unitId,
    title: 'Kiểm tra đèn',
    description: 'Đèn hành lang không sáng.',
    priority: 'HIGH',
    tenant_id: randomUUID(),
    site_id: randomUUID(),
    role: 'admin',
  }, { idempotencyKey: 'create-intent-001' });

  assert.equal(calls[2].url, '/api/v1/service-request-form-options');
  assert.equal(calls[3].url, `/api/v1/service-request-form-options?building_id=${buildingId}`);
  assert.equal(calls[3].options.headers.Authorization, `Bearer ${issuedToken}`);
  assert.equal(new URL(calls[3].url, 'https://local.test').searchParams.get('tenant_id'), null);
  assert.equal(new URL(calls[3].url, 'https://local.test').searchParams.get('role'), null);
  assert.deepEqual(options, formOptions);
  assert.equal(calls[4].url, '/api/v1/service-requests');
  assert.equal(calls[4].options.headers.Authorization, `Bearer ${issuedToken}`);
  assert.equal(calls[4].options.headers['Idempotency-Key'], 'create-intent-001');
  assert.deepEqual(JSON.parse(calls[4].options.body), {
    category_id: categoryId,
    building_id: buildingId,
    unit_id: unitId,
    title: 'Kiểm tra đèn',
    description: 'Đèn hành lang không sáng.',
    priority: 'HIGH',
  });
  assert.equal(created.code, 'SR-NEW-001');
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

test('cleaning client uses only server-owned route, building and task identifiers', async () => {
  const token = randomUUID();
  const initial = cleaningTask();
  const assigned = cleaningTask({ ...initial, status: 'ASSIGNED', assigned_to_id: randomUUID(), version: 2 });
  const inProgress = cleaningTask({ ...assigned, status: 'IN_PROGRESS', version: 3 });
  const checked = cleaningTask({ ...inProgress, version: 4, checklist: [{ ...inProgress.checklist[0], result: 'PASS', version: 2 }] });
  const submitted = cleaningTask({ ...checked, status: 'SUBMITTED', version: 5, submitted_at: '2026-09-13T02:00:00Z' });
  const accepted = cleaningTask({ ...submitted, status: 'ACCEPTED', version: 6, accepted_at: '2026-09-13T02:05:00Z' });
  const route = { id: initial.route_id, code: initial.route_code, name: initial.route_name, building_id: initial.building_id };
  const calls = [];
  const responses = [
    jsonResponse({ access_token: token }), jsonResponse(userInfo(['admin'])), jsonResponse({ items: [initial] }),
    jsonResponse([route]), jsonResponse([{ id: randomUUID(), full_name: 'Nhân viên A' }]),
    jsonResponse({ id: initial.shift_id, route_id: initial.route_id, scheduled_start_at: initial.scheduled_start_at, scheduled_end_at: initial.scheduled_end_at, status: 'PLANNED', version: 1, tasks: [initial] }, 201),
    jsonResponse(assigned), jsonResponse(inProgress), jsonResponse(checked), jsonResponse(submitted), jsonResponse(accepted),
  ];
  const client = createApiClient({ baseUrl: '/api/v1', fetchImpl: async (url, options) => { calls.push({ url, options }); return responses.shift(); } });
  await client.authenticate('manager.integration', 'local-test-password');
  await client.listCleaningTasks({ tenant_id: randomUUID(), role: 'admin' });
  await client.listCleaningRoutes({ site_id: randomUUID() });
  await client.listCleaningAssignees(initial.building_id, { tenant_id: randomUUID(), role: 'admin' });
  await client.createCleaningShift({ route_id: initial.route_id, scheduled_start_at: initial.scheduled_start_at, scheduled_end_at: initial.scheduled_end_at, tenant_id: randomUUID() }, { idempotencyKey: 'cleaning-shift-001' });
  await client.assignCleaningTask(initial.id, { assignee_id: assigned.assigned_to_id, expected_version: initial.version, role: 'admin' });
  await client.startCleaningTask(initial.id, assigned.version);
  await client.updateCleaningChecklist(initial.id, initial.checklist[0].id, { expected_version: initial.checklist[0].version, result: 'PASS', tenant_id: randomUUID() });
  await client.submitCleaningTask(initial.id, checked.version, { idempotencyKey: 'cleaning-submit-001' });
  await client.acceptCleaningTask(initial.id, submitted.version);

  assert.equal(calls[2].url, '/api/v1/cleaning/tasks');
  assert.equal(calls[3].url, '/api/v1/cleaning/routes');
  assert.equal(calls[4].url, `/api/v1/cleaning/assignees?building_id=${initial.building_id}`);
  assert.equal(calls[5].options.headers['Idempotency-Key'], 'cleaning-shift-001');
  assert.deepEqual(JSON.parse(calls[5].options.body), { route_id: initial.route_id, scheduled_start_at: initial.scheduled_start_at, scheduled_end_at: initial.scheduled_end_at });
  assert.deepEqual(JSON.parse(calls[6].options.body), { assignee_id: assigned.assigned_to_id, expected_version: 1 });
  assert.deepEqual(JSON.parse(calls[8].options.body), { expected_version: 1, result: 'PASS', note: null });
  assert.equal(calls[9].options.headers['Idempotency-Key'], 'cleaning-submit-001');
  assert.ok(calls.slice(2).every(call => call.options.headers.Authorization === `Bearer ${token}`));
  assert.ok(calls.slice(2).every(call => !JSON.stringify(call).match(/tenant_id|site_id|role/)));
});

test('security client keeps scope server-owned across shift, patrol and incident commands', async () => {
  const token = randomUUID();
  const window = securityWindow();
  const shift = securityShift({ patrol_windows: [window] });
  const incident = securityIncident({ patrol_window_id: window.id, building_id: shift.building_id });
  const dashboard = { shifts: [shift], exceptions: [], incidents: [incident] };
  const point = { id: window.patrol_point_id, code: window.patrol_point_code, name: window.patrol_point_name, building_id: shift.building_id };
  const missed = { ...window, status: 'MISSED', missed_reason: 'Phong tỏa tạm thời', version: 2 };
  const evidence = { ...incident, evidence: [{ id: randomUUID(), evidence_type: 'NOTE', description: 'Biên bản đã ghi nhận.' }] };
  const acknowledged = { ...evidence, escalations: evidence.escalations.map(item => ({ ...item, acknowledgement: { id: randomUUID() } })) };
  const triaged = { ...acknowledged, status: 'TRIAGED', version: 2 };
  const calls = [];
  const responses = [
    jsonResponse({ access_token: token }), jsonResponse(userInfo(['admin'])), jsonResponse(dashboard), jsonResponse([point]),
    jsonResponse([{ id: shift.assigned_to_id, full_name: 'Nhân viên An ninh' }]), jsonResponse(shift, 201), jsonResponse(missed),
    jsonResponse(incident, 201), jsonResponse(evidence, 201), jsonResponse(acknowledged, 201), jsonResponse(triaged),
  ];
  const client = createApiClient({ baseUrl: '/api/v1', fetchImpl: async (url, options) => { calls.push({ url, options }); return responses.shift(); } });
  await client.authenticate('security.manager', 'local-test-password');
  await client.listSecurityDashboard({ tenant_id: randomUUID(), role: 'admin' });
  await client.listSecurityPatrolPoints({ site_id: randomUUID() });
  await client.listSecurityAssignees(shift.building_id, { tenant_id: randomUUID(), role: 'admin' });
  await client.createSecurityShift({ building_id: shift.building_id, assignee_id: shift.assigned_to_id, scheduled_start_at: shift.scheduled_start_at, scheduled_end_at: shift.scheduled_end_at, patrol_windows: [{ patrol_point_id: window.patrol_point_id, window_start_at: window.window_start_at, window_end_at: window.window_end_at }], tenant_id: randomUUID() }, { idempotencyKey: 'security-shift-001' });
  await client.missPatrolWindow(window.id, { expected_version: window.version, reason: 'Phong tỏa tạm thời', role: 'admin' });
  await client.createSecurityIncident({ patrol_window_id: window.id, incident_type: 'FIRE', severity: 'HIGH', title: incident.title, description: incident.description, occurred_at: incident.occurred_at, tenant_id: randomUUID() }, { idempotencyKey: 'security-incident-001' });
  await client.addSecurityIncidentEvidence(incident.id, { evidence_type: 'NOTE', description: 'Biên bản đã ghi nhận.', tenant_id: randomUUID() }, { idempotencyKey: 'security-evidence-001' });
  await client.acknowledgeSecurityEscalation(incident.id, incident.escalations[0].id, 'Đã tiếp nhận.', { idempotencyKey: 'security-ack-001' });
  await client.transitionSecurityIncident(incident.id, { expected_version: incident.version, status: 'TRIAGED', role: 'admin' });

  assert.equal(calls[2].url, '/api/v1/security/dashboard');
  assert.equal(calls[3].url, '/api/v1/security/patrol-points');
  assert.equal(calls[4].url, `/api/v1/security/assignees?building_id=${shift.building_id}`);
  assert.equal(calls[5].options.headers['Idempotency-Key'], 'security-shift-001');
  assert.deepEqual(JSON.parse(calls[5].options.body), {
    building_id: shift.building_id, assignee_id: shift.assigned_to_id, scheduled_start_at: shift.scheduled_start_at, scheduled_end_at: shift.scheduled_end_at,
    patrol_windows: [{ patrol_point_id: window.patrol_point_id, window_start_at: window.window_start_at, window_end_at: window.window_end_at }],
  });
  assert.deepEqual(JSON.parse(calls[6].options.body), { expected_version: 1, reason: 'Phong tỏa tạm thời' });
  assert.equal(calls[7].options.headers['Idempotency-Key'], 'security-incident-001');
  assert.equal(calls[9].options.headers['Idempotency-Key'], 'security-ack-001');
  assert.deepEqual(JSON.parse(calls[10].options.body), { expected_version: 1, status: 'TRIAGED', conclusion: null });
  assert.ok(calls.slice(2).every(call => call.options.headers.Authorization === `Bearer ${token}`));
  assert.ok(calls.slice(2).every(call => !JSON.stringify(call).match(/tenant_id|site_id|role/)));
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
  assert.deepEqual(cleaning.menu, ['overview', 'cleaning', 'notifications']);
  assert.ok(canViewTab(cleaning, 'cleaning'));
  assert.equal(canAccessCleaning(cleaning), true);
  assert.equal(canManageCleaning(cleaning), false);
  const manager = createAuthenticatedAccount(userInfo(['director']));
  assert.ok(canViewTab(manager, 'cleaning'));
  assert.equal(canManageCleaning(manager), true);

  const security = createAuthenticatedAccount(userInfo(['security']));
  assert.ok(canViewTab(security, 'residents'));
  assert.ok(canViewTab(security, 'security'));
  assert.ok(!canViewTab(security, 'tasks'));
  assert.equal(canAccessSecurity(security), true);
  assert.equal(canManageSecurity(security), false);
  assert.equal(security.primary, 'security');

  const technician = createAuthenticatedAccount(userInfo(['technician']));
  assert.ok(!canViewTab(technician, 'residents'), 'Unit 360 stays hidden until backend exposes technician assignment scope');
  assert.equal(canCreateServiceRequests(cskh), true);
  assert.equal(canCreateServiceRequests(technician), false);
  assert.equal(cskh.canCreateServiceRequests, true);
  assert.equal(technician.canCreateServiceRequests, false);
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

test('notifications API client lists notifications and marks read with schema assertion', async () => {
  const issuedToken = randomUUID();
  const notifId = randomUUID();
  const notif = {
    id: notifId,
    domain_event_id: randomUUID(),
    template_code: 'SRV_ASSIGNED',
    template_snapshot: { title: 'Yêu cầu được phân công', detail: 'Yêu cầu SR-001' },
    delivery_status: 'PUBLISHED',
    delivered_at: '2026-09-15T02:00:00Z',
    read_at: null,
    last_error: null,
    created_at: '2026-09-15T01:50:00Z',
  };
  const calls = [];
  const client = createApiClient({
    baseUrl: 'https://api.example.test/api/v1',
    correlationIdFactory: () => correlationId,
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      if (url.endsWith('/auth/login')) return jsonResponse({ access_token: issuedToken });
      if (url.endsWith('/auth/me')) return jsonResponse(userInfo(['cskh']));
      if (url.includes('/notifications?') || url.endsWith('/notifications')) {
        return jsonResponse({ items: [notif] });
      }
      if (url.endsWith(`/notifications/${notifId}/read`)) {
        return jsonResponse({ ...notif, read_at: '2026-09-15T02:05:00Z' });
      }
      return jsonResponse({ error: { code: 'ERR-NOTFOUND', message: 'Not found' } }, 404);
    },
  });

  await client.authenticate('cskh.integration', 'password');
  const list = await client.listNotifications({ includeRead: true });
  assert.equal(list.items.length, 1);
  assert.equal(list.items[0].id, notifId);
  assert.equal(list.items[0].delivery_status, 'PUBLISHED');
  assert.equal(calls[2].url, 'https://api.example.test/api/v1/notifications?include_read=true');
  assert.equal(calls[2].options.headers.Authorization, `Bearer ${issuedToken}`);

  const marked = await client.markNotificationRead(notifId);
  assert.equal(marked.id, notifId);
  assert.equal(marked.read_at, '2026-09-15T02:05:00Z');
  assert.equal(calls[3].options.method, 'POST');
});

test('outbox API client lists events and retries with Idempotency-Key (AC-22, AC-36)', async () => {
  const issuedToken = randomUUID();
  const eventId = randomUUID();
  const event = {
    id: eventId,
    event_type: 'ServiceRequestCreated',
    resource_type: 'ServiceRequest',
    resource_id: randomUUID(),
    correlation_id: correlationId,
    delivery_status: 'DEAD_LETTER',
    attempt_count: 3,
    next_attempt_at: '2026-09-15T02:30:00Z',
    last_error: 'ERR-CHANNEL-TIMEOUT',
    created_at: '2026-09-15T01:00:00Z',
    published_at: null,
  };
  const calls = [];
  const client = createApiClient({
    baseUrl: 'https://api.example.test/api/v1',
    correlationIdFactory: () => correlationId,
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      if (url.endsWith('/auth/login')) return jsonResponse({ access_token: issuedToken });
      if (url.endsWith('/auth/me')) return jsonResponse(userInfo(['director']));
      if (url.includes('/outbox/events?')) {
        return jsonResponse({ items: [event] });
      }
      if (url.endsWith(`/outbox/events/${eventId}/retry`)) {
        return jsonResponse({ ...event, delivery_status: 'PENDING', attempt_count: 0, last_error: null });
      }
      return jsonResponse({ error: { code: 'ERR-NOTFOUND', message: 'Not found' } }, 404);
    },
  });

  await client.authenticate('director.integration', 'password');
  const events = await client.listOutboxEvents({ deliveryStatus: 'DEAD_LETTER' });
  assert.equal(events.items.length, 1);
  assert.equal(events.items[0].delivery_status, 'DEAD_LETTER');
  assert.equal(calls[2].url, 'https://api.example.test/api/v1/outbox/events?delivery_status=DEAD_LETTER&limit=50');

  const retried = await client.retryOutboxEvent(eventId, { idempotencyKey: 'retry-intent-001' });
  assert.equal(retried.delivery_status, 'PENDING');
  assert.equal(retried.attempt_count, 0);
  assert.equal(calls[3].options.method, 'POST');
  assert.equal(calls[3].options.headers['Idempotency-Key'], 'retry-intent-001');
});

test('AC-36: lost response retains Idempotency-Key on retry and does not report false success', async () => {
  const eventId = randomUUID();
  let firstAttempt = true;
  const calls = [];
  const client = createApiClient({
    baseUrl: 'https://api.example.test/api/v1',
    correlationIdFactory: () => correlationId,
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      if (url.endsWith('/auth/login')) return jsonResponse({ access_token: 'token-abc' });
      if (url.endsWith('/auth/me')) return jsonResponse(userInfo(['admin']));
      if (url.endsWith(`/outbox/events/${eventId}/retry`)) {
        if (firstAttempt) {
          firstAttempt = false;
          throw new TypeError('Network connection lost');
        }
        return jsonResponse({
          id: eventId,
          event_type: 'ServiceRequestCreated',
          resource_type: 'ServiceRequest',
          resource_id: randomUUID(),
          correlation_id: correlationId,
          delivery_status: 'PENDING',
          attempt_count: 0,
          next_attempt_at: '2026-09-15T02:30:00Z',
          last_error: null,
          created_at: '2026-09-15T01:00:00Z',
          published_at: null,
        });
      }
      return jsonResponse({ items: [] });
    },
  });

  await client.authenticate('admin.integration', 'password');
  const intent = { key: 'retry-event-001' };

  await assert.rejects(
    async () => {
      await client.retryOutboxEvent(eventId, { idempotencyKey: intent.key });
    },
    err => {
      assert.equal(err.code, 'ERR-NETWORK');
      return true;
    },
  );

  const recovered = await client.retryOutboxEvent(eventId, { idempotencyKey: intent.key });
  assert.equal(recovered.delivery_status, 'PENDING');

  const retryCalls = calls.filter(c => c.url.includes(`/outbox/events/${eventId}/retry`));
  assert.equal(retryCalls.length, 2);
  assert.equal(retryCalls[0].options.headers['Idempotency-Key'], 'retry-event-001');
  assert.equal(retryCalls[1].options.headers['Idempotency-Key'], 'retry-event-001');
});

test('role visibility: outbox management is restricted to admin and director', () => {
  const admin = createAuthenticatedAccount(userInfo(['admin']));
  const director = createAuthenticatedAccount(userInfo(['director']));
  const cskh = createAuthenticatedAccount(userInfo(['cskh']));
  const technician = createAuthenticatedAccount(userInfo(['technician']));
  const cleaning = createAuthenticatedAccount(userInfo(['cleaning']));
  const security = createAuthenticatedAccount(userInfo(['security']));
  const accountant = createAuthenticatedAccount(userInfo(['accountant']));

  assert.equal(canManageOutbox(admin), true);
  assert.equal(canManageOutbox(director), true);
  assert.equal(canManageOutbox(cskh), false);
  assert.equal(canManageOutbox(technician), false);
  assert.equal(canManageOutbox(cleaning), false);
  assert.equal(canManageOutbox(security), false);
  assert.equal(canManageOutbox(accountant), false);

  assert.equal(admin.canManageOutbox, true);
  assert.equal(director.canManageOutbox, true);
  assert.equal(cskh.canManageOutbox, false);
});

test('dashboard API client fetches KPI snapshot with as_of and validates schema (AC-25)', async () => {
  const cutoff = '2026-09-15T02:00:00Z';
  const calls = [];
  const client = createApiClient({
    baseUrl: 'https://api.example.test/api/v1',
    correlationIdFactory: () => correlationId,
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      if (url.endsWith('/auth/login')) return jsonResponse({ access_token: 'valid-token' });
      if (url.endsWith('/auth/me')) return jsonResponse(userInfo(['director']));
      if (url.includes('/dashboard?as_of=')) {
        return jsonResponse({
          as_of: cutoff,
          sla_overdue_count: 3,
          maintenance_due_count: 2,
          cleaning_rework_count: 1,
          open_incident_count: 4,
          ar_debt_vnd: 15400000,
        });
      }
      return jsonResponse({ error: 'not found' }, 404);
    },
  });

  await client.authenticate('director.integration', 'password');
  const dashboard = await client.getDashboard({ asOf: cutoff });

  assert.equal(dashboard.as_of, cutoff);
  assert.equal(dashboard.sla_overdue_count, 3);
  assert.equal(dashboard.maintenance_due_count, 2);
  assert.equal(dashboard.cleaning_rework_count, 1);
  assert.equal(dashboard.open_incident_count, 4);
  assert.equal(dashboard.ar_debt_vnd, 15400000);

  const dashCall = calls.find(c => c.url.includes('/dashboard?as_of='));
  assert.ok(dashCall);
  assert.ok(dashCall.url.includes(encodeURIComponent(cutoff)));
});

test('dashboard drill-down API client fetches source items for KPI reconciliation (AC-25)', async () => {
  const cutoff = '2026-09-15T02:00:00Z';
  const incidentId = randomUUID();
  const bldgId = randomUUID();
  const calls = [];
  const client = createApiClient({
    baseUrl: 'https://api.example.test/api/v1',
    correlationIdFactory: () => correlationId,
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      if (url.endsWith('/auth/login')) return jsonResponse({ access_token: 'valid-token' });
      if (url.endsWith('/auth/me')) return jsonResponse(userInfo(['director']));
      if (url.includes('/dashboard/drill-down/open_incidents')) {
        return jsonResponse({
          as_of: cutoff,
          metric: 'open_incidents',
          items: [{
            metric: 'open_incidents',
            resource_type: 'SecurityIncident',
            resource_id: incidentId,
            building_id: bldgId,
            reference: 'INC-001',
            title: 'Khói tại phòng kỹ thuật',
            status: 'NEW',
            occurred_at: '2026-09-15T01:30:00Z',
            amount_vnd: null,
          }],
        });
      }
      return jsonResponse({ error: 'not found' }, 404);
    },
  });

  await client.authenticate('director.integration', 'password');
  const drillDown = await client.getDashboardDrillDown('open_incidents', { asOf: cutoff });

  assert.equal(drillDown.metric, 'open_incidents');
  assert.equal(drillDown.items.length, 1);
  assert.equal(drillDown.items[0].reference, 'INC-001');
  assert.equal(drillDown.items[0].resource_type, 'SecurityIncident');
});

test('audit events API client lists events and supports correlation filtering', async () => {
  const eventId = randomUUID();
  const targetCorrId = randomUUID();
  const resourceId = randomUUID();
  const cutoff = '2026-09-15T02:00:00Z';
  const calls = [];
  const client = createApiClient({
    baseUrl: 'https://api.example.test/api/v1',
    correlationIdFactory: () => correlationId,
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      if (url.endsWith('/auth/login')) return jsonResponse({ access_token: 'valid-token' });
      if (url.endsWith('/auth/me')) return jsonResponse(userInfo(['director']));
      if (url.includes('/audit-events')) {
        return jsonResponse({
          items: [{
            id: eventId,
            actor_account_id: randomUUID(),
            event_type: 'SecurityIncidentReported',
            action: 'CREATE',
            resource_type: 'SecurityIncident',
            resource_id: randomUUID(),
            building_id: randomUUID(),
            before_data: null,
            after_data: { title: 'Báo khói' },
            reason: 'Tự động từ cảm biến',
            correlation_id: targetCorrId,
            created_at: '2026-09-15T01:30:00Z',
          }],
        });
      }
      return jsonResponse({ error: 'not found' }, 404);
    },
  });

  await client.authenticate('director.integration', 'password');
  const result = await client.listAuditEvents({
    correlationId: targetCorrId,
    resourceType: 'SecurityIncident',
    resourceId,
    asOf: cutoff,
  });

  assert.equal(result.items.length, 1);
  assert.equal(result.items[0].id, eventId);
  assert.equal(result.items[0].correlation_id, targetCorrId);
  assert.ok(calls.some(c => c.url.includes(`correlation_id=${targetCorrId}`)));
  assert.ok(calls.some(c => c.url.includes(`resource_id=${resourceId}`)));
  assert.ok(calls.some(c => c.url.includes(`as_of=${encodeURIComponent(cutoff)}`)));
});

test('AC-25 / AC-45: API error does not silently fallback to mock and propagates structured error with correlationId', async () => {
  const errorCorrId = 'err-corr-9999';
  const client = createApiClient({
    baseUrl: 'https://api.example.test/api/v1',
    correlationIdFactory: () => correlationId,
    fetchImpl: async url => {
      if (url.endsWith('/auth/login')) return jsonResponse({ access_token: 'valid-token' });
      if (url.endsWith('/auth/me')) return jsonResponse(userInfo(['director']));
      if (url.includes('/dashboard')) {
        return jsonResponse({
          error: {
            code: 'ERR-INTERNAL',
            message: 'Database query timeout at cutoff.',
            correlation_id: errorCorrId,
          },
        }, 500, errorCorrId);
      }
      return jsonResponse({ error: 'not found' }, 404);
    },
  });

  await client.authenticate('director.integration', 'password');

  await assert.rejects(
    async () => {
      await client.getDashboard({ asOf: '2026-09-15T02:00:00Z' });
    },
    err => {
      assert.ok(err instanceof ApiError);
      assert.equal(err.code, 'ERR-INTERNAL');
      assert.equal(err.correlationId, errorCorrId);
      return true;
    },
  );
});

test('role visibility: executive dashboard is restricted to admin and director, audit events to admin, director and accountant', () => {
  const admin = createAuthenticatedAccount(userInfo(['admin']));
  const director = createAuthenticatedAccount(userInfo(['director']));
  const cskh = createAuthenticatedAccount(userInfo(['cskh']));
  const technician = createAuthenticatedAccount(userInfo(['technician']));
  const cleaning = createAuthenticatedAccount(userInfo(['cleaning']));
  const security = createAuthenticatedAccount(userInfo(['security']));
  const accountant = createAuthenticatedAccount(userInfo(['accountant']));

  // Executive Dashboard
  assert.equal(canAccessExecutiveDashboard(admin), true);
  assert.equal(canAccessExecutiveDashboard(director), true);
  assert.equal(canAccessExecutiveDashboard(cskh), false);
  assert.equal(canAccessExecutiveDashboard(technician), false);
  assert.equal(canAccessExecutiveDashboard(cleaning), false);
  assert.equal(canAccessExecutiveDashboard(security), false);
  assert.equal(canAccessExecutiveDashboard(accountant), false);

  assert.equal(admin.canViewExecutiveDashboard, true);
  assert.equal(director.canViewExecutiveDashboard, true);
  assert.equal(cskh.canViewExecutiveDashboard, false);

  // Audit Events
  assert.equal(canAccessAuditEvents(admin), true);
  assert.equal(canAccessAuditEvents(director), true);
  assert.equal(canAccessAuditEvents(accountant), true);
  assert.equal(canAccessAuditEvents(cskh), false);
  assert.equal(canAccessAuditEvents(technician), false);
  assert.equal(canAccessAuditEvents(cleaning), false);
  assert.equal(canAccessAuditEvents(security), false);

  assert.equal(admin.canViewAuditEvents, true);
  assert.equal(accountant.canViewAuditEvents, true);
  assert.equal(cskh.canViewAuditEvents, false);
});

test('resident API client keeps scope identifiers server-owned and reuses one as_of snapshot', async () => {
  const token = randomUUID();
  const unitId = randomUUID();
  const categoryId = randomUUID();
  const requestId = randomUUID();
  const attachmentId = randomUUID();
  const notificationId = randomUUID();
  const asOf = '2026-09-30T23:59:59.000Z';
  const calls = [];
  const requestView = {
    id: requestId, code: 'SR-R6-001', unit_id: unitId, category_id: categoryId,
    title: 'Rò rỉ nước', description: 'Nước rò dưới chậu rửa.', priority: 'HIGH', status: 'NEW',
    sla_deadline: '2026-10-01T04:00:00Z', sla_breached_at: null, resolved_at: null, closed_at: null,
    version: 1, created_at: '2026-09-30T01:00:00Z', updated_at: '2026-09-30T01:00:00Z',
  };
  const client = createApiClient({
    baseUrl: '/api/v1',
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      if (url.endsWith('/auth/login')) return jsonResponse({ access_token: token });
      if (url.endsWith('/auth/me')) return jsonResponse({
        ...userInfo(['resident']), resident_person_id: randomUUID(), resident_unit_ids: [unitId],
      });
      if (url.endsWith('/resident/service-request-options')) return jsonResponse({
        buildings: [{ id: randomUUID(), code: 'A', name: 'Tòa A' }],
        categories: [{ id: categoryId, code: 'TECH', name: 'Kỹ thuật', building_id: null }],
        units: [{ id: unitId, unit_number: 'A-0101', building_id: randomUUID() }],
      });
      if (url.includes('/resident/service-requests/') && url.endsWith('/timeline')) return jsonResponse({ items: [{
        id: randomUUID(), event_type: 'ResidentServiceRequestCreated', action: 'create', before_status: null,
        after_status: 'NEW', before_priority: null, after_priority: 'HIGH', created_at: requestView.created_at,
      }] });
      if (url.includes('/resident/service-requests/') && url.endsWith('/evidence')) return jsonResponse({ items: [] });
      if (url.split('?')[0].endsWith('/resident/service-requests')) return jsonResponse({ items: [requestView], page: 1, page_size: 20, total: 1 });
      if (url.includes(`/resident/service-requests/${requestId}`) && !url.includes('/signed-link')) return jsonResponse(requestView);
      if (url.includes('/resident/billing/summary')) return jsonResponse({ as_of: asOf, total_ar_balance_vnd: 200000, items: [{ unit_id: unitId, ar_balance_vnd: 200000 }] });
      if (url.includes('/resident/billing/invoices')) return jsonResponse({ as_of: asOf, items: [] });
      if (url.includes('/resident/billing/payments')) return jsonResponse({ as_of: asOf, items: [] });
      if (url.includes('/resident/notifications') && options.method === 'GET') return jsonResponse({
        items: [{ id: notificationId, template_code: 'R6_NOTICE', template_snapshot: { title: 'Thông báo', body: 'Nội dung' }, delivery_status: 'PUBLISHED', delivered_at: '2026-09-30T02:00:00Z', read_at: null, correlation_id: randomUUID(), created_at: '2026-09-30T02:00:00Z' }], page: 1, page_size: 20, total: 1, unread_count: 1,
      });
      if (url.includes('/resident/notifications/') && options.method === 'POST') return jsonResponse({
        id: notificationId, template_code: 'R6_NOTICE', template_snapshot: { title: 'Thông báo', body: 'Nội dung' }, delivery_status: 'PUBLISHED', delivered_at: '2026-09-30T02:00:00Z', read_at: '2026-09-30T03:00:00Z', correlation_id: randomUUID(), created_at: '2026-09-30T02:00:00Z',
      });
      if (url.includes('/signed-link')) return jsonResponse({ url: '/api/v1/evidence/signed', expires_at: '2026-09-30T04:00:00Z' });
      if (url.includes('/resident/service-requests/') && options.method === 'POST') return jsonResponse(requestView, 201);
      return jsonResponse({ error: { code: 'ERR-NOTFOUND', message: 'not found' } }, 404);
    },
  });

  const me = await client.authenticate('resident_west', 'Password@123');
  assert.equal(createAuthenticatedAccount(me).isResident, true);
  await client.getResidentServiceRequestOptions({ tenant_id: randomUUID(), role: 'admin' });
  await client.listResidentServiceRequests({ building_id: randomUUID(), role: 'admin' });
  await client.getResidentServiceRequest(requestId);
  await client.getResidentServiceRequestTimeline(requestId);
  await client.listResidentServiceRequestEvidence(requestId);
  const signedLink = await client.getResidentEvidenceLink(requestId, attachmentId);
  assert.equal(signedLink.url, '/api/v1/evidence/signed');
  await client.getResidentBillingSummary(asOf);
  await client.listResidentBillingInvoices(asOf);
  await client.listResidentBillingPayments(asOf);
  await client.listResidentNotifications();

  const residentCalls = calls.slice(2);
  assert.ok(residentCalls.every(call => !call.url.includes('tenant_id') && !call.url.includes('role=') && !call.url.includes('building_id=')));
  const billingCalls = residentCalls.filter(call => call.url.includes('/resident/billing/'));
  assert.equal(billingCalls.length, 3);
  assert.ok(billingCalls.every(call => new URL(call.url, 'https://local.test').searchParams.get('as_of') === asOf));
  assert.ok(residentCalls.every(call => call.options.headers.Authorization === `Bearer ${token}`));
  const invalidClient = createApiClient({ fetchImpl: async () => jsonResponse({ items: [] }) });
  await assert.rejects(invalidClient.getResidentBillingSummary(asOf), error => error instanceof ApiError && error.code === 'ERR-INVALID-RESPONSE');
});
