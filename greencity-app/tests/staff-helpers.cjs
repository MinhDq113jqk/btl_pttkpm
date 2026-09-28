const { randomUUID } = require('node:crypto');

const mockedPages = new WeakSet();

async function installAuthApiMocks(page, { role = 'cskh', items } = {}) {
  if (mockedPages.has(page)) return;
  mockedPages.add(page);
  const siteId = randomUUID();
  const user = {
    account_id: randomUUID(), tenant_id: randomUUID(), username: `${role}.ux`,
    full_name: `Nhân viên ${role.toUpperCase()}`, roles: [role], active_site_id: siteId,
    must_change_password: false,
    allowed_sites: [{ id: siteId, code: 'CENTRAL', name: 'GreenCity Central' }],
  };
  const accessToken = randomUUID();
  const responseItems = items || [{
    id: randomUUID(), code: 'SR-UX-001', title: 'Kiểm tra đèn hành lang',
    unit_id: randomUUID(), unit_number: 'A-1201', building_id: randomUUID(),
    building_code: 'A', building_name: 'Tòa A', status: 'IN_PROGRESS', priority: 'HIGH',
    sla_deadline: '2026-09-13T02:00:00Z', created_at: '2026-09-12T01:00:00Z',
  }];
  const unit = {
    id: responseItems[0]?.unit_id || randomUUID(), unit_number: 'A-1201', floor: 12,
    area_m2: 72.5, status: 'OCCUPIED', version: 1, building_id: responseItems[0]?.building_id || randomUUID(),
    building_code: 'A', building_name: 'Tòa A', site_id: siteId, site_code: 'CENTRAL',
    site_name: 'GreenCity Central', residents_visible: true, residents: [],
  };
  let assistantAttempts = 0;

  await page.route('**/api/v1/**', async route => {
    const pathname = new URL(route.request().url()).pathname;
    const headers = { 'Content-Type': 'application/json', 'X-Correlation-ID': randomUUID() };
    if (pathname.endsWith('/auth/login')) return route.fulfill({ status: 200, headers, body: JSON.stringify({ access_token: accessToken }) });
    if (pathname.endsWith('/auth/me')) return route.fulfill({ status: 200, headers, body: JSON.stringify(user) });
    if (pathname.endsWith('/auth/logout')) return route.fulfill({ status: 204, headers });
    if (pathname.endsWith('/assistant/chat')) {
      const message = route.request().postDataJSON()?.message;
      assistantAttempts += 1;
      if (message === 'hết hạn phiên') return route.fulfill({
        status: 401,
        headers,
        body: JSON.stringify({ error: { code: 'ERR-UNAUTHORIZED', message: 'Phiên đã hết hạn.', correlation_id: headers['X-Correlation-ID'] } }),
      });
      if (message === 'thử lỗi' && assistantAttempts === 2) return route.fulfill({
        status: 503,
        headers,
        body: JSON.stringify({ error: { code: 'ERR-GEMINI-UNAVAILABLE', message: 'Trợ lý tạm thời không khả dụng.', correlation_id: headers['X-Correlation-ID'] } }),
      });
      await new Promise(resolve => setTimeout(resolve, 150));
      return route.fulfill({ status: 200, headers, body: JSON.stringify({ reply: 'Backend đã xử lý câu hỏi. Trong phạm vi phiên có 1 công việc cần kiểm tra.' }) });
    }
    if (/\/service-requests\/[^/]+\/work-orders$/.test(pathname) && route.request().method() === 'GET') return route.fulfill({ status: 200, headers, body: JSON.stringify([]) });
    if (/\/service-requests\/[^/]+\/assignees$/.test(pathname)) return route.fulfill({ status: 200, headers, body: JSON.stringify([]) });
    if (/\/service-requests\/[^/]+$/.test(pathname)) {
      const item = responseItems.find(candidate => candidate.id === decodeURIComponent(pathname.split('/').at(-1))) || responseItems[0];
      return route.fulfill({ status: 200, headers, body: JSON.stringify({
        ...item, tenant_id: user.tenant_id, site_id: siteId, category_id: randomUUID(), linked_request_id: null,
        link_type: null, link_reason: null, description: 'Synthetic request details for the workflow dialog.',
        sla_started_at: item.created_at, sla_duration_minutes: 240, sla_breached_at: null,
        owner_account_id: user.account_id, resolved_at: null, closed_at: null, csat_score: null, version: 1,
      }) });
    }
    if (pathname.endsWith('/service-requests')) return route.fulfill({ status: 200, headers, body: JSON.stringify({ items: responseItems, page: 1, page_size: 20, total: responseItems.length }) });
    if (/\/units\/[^/]+\/360$/.test(pathname)) return route.fulfill({ status: 200, headers, body: JSON.stringify({ ...unit, id: decodeURIComponent(pathname.split('/').at(-2)) }) });
    if (pathname.endsWith('/notifications')) return route.fulfill({ status: 200, headers, body: JSON.stringify({ items: [] }) });
    if (pathname.endsWith('/outbox/events')) return route.fulfill({ status: 200, headers, body: JSON.stringify({ items: [] }) });
    return route.fulfill({ status: 404, headers, body: JSON.stringify({ error: { code: 'ERR-NOTFOUND', message: 'Không tìm thấy.', correlation_id: randomUUID() } }) });
  });
}

async function loginAs(page, role = 'cskh') {
  await installAuthApiMocks(page, { role });
  await page.locator('#staff-username').fill(`${role}.ux`);
  await page.locator('#staff-password').fill('browser-only-password');
  await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
  await page.locator('.desktop-shell').waitFor();
}

module.exports = { installAuthApiMocks, loginAs };
