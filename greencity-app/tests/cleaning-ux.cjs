const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { randomUUID } = require('node:crypto');
const { chromium } = require('playwright');

const output = path.resolve(__dirname, '../artifacts/cleaning-ux');
fs.mkdirSync(output, { recursive: true });

const token = randomUUID();
const correlationId = randomUUID();
const siteId = randomUUID();
const user = {
  account_id: randomUUID(), tenant_id: randomUUID(), username: 'cleaning.browser',
  full_name: 'Nhân viên Vệ sinh', roles: ['cleaning'], active_site_id: siteId,
  allowed_sites: [{ id: siteId, code: 'CENTRAL', name: 'GreenCity Central' }],
};
const task = {
  id: randomUUID(), shift_id: randomUUID(), route_id: randomUUID(), route_code: 'CLN-LOBBY', route_name: 'Tuyến sảnh',
  area_id: randomUUID(), area_code: 'LOBBY', area_name: 'Sảnh chính', tenant_id: user.tenant_id, site_id: siteId,
  building_id: randomUUID(), assigned_to_id: user.account_id, status: 'ASSIGNED',
  scheduled_start_at: '2026-09-13T01:00:00Z', scheduled_end_at: '2026-09-13T03:00:00Z',
  started_at: null, submitted_at: null, accepted_at: null, accepted_by_id: null,
  rework_work_order_id: null, rework_case_id: null, version: 1,
  checklist: [
    { id: randomUUID(), position: 1, label: 'Sàn sạch', is_required: true, result: 'PENDING', note: null, performed_by_id: null, performed_at: null, version: 1 },
    { id: randomUUID(), position: 2, label: 'Thùng rác đã kiểm tra', is_required: true, result: 'PENDING', note: null, performed_by_id: null, performed_at: null, version: 1 },
  ],
};

(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'vi-VN' });
  const page = await context.newPage();
  const requests = [];
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await context.route('**/api/v1/**', async route => {
    const request = route.request();
    const url = new URL(request.url());
    requests.push({ path: url.pathname, method: request.method(), body: request.postDataJSON?.(), authorization: request.headers().authorization });
    const headers = { 'Content-Type': 'application/json', 'X-Correlation-ID': correlationId };
    if (url.pathname.endsWith('/auth/login')) return route.fulfill({ status: 200, headers, body: JSON.stringify({ access_token: token }) });
    if (url.pathname.endsWith('/auth/me')) return route.fulfill({ status: 200, headers, body: JSON.stringify(user) });
    if (url.pathname.endsWith('/cleaning/tasks') && request.method() === 'GET') return route.fulfill({ status: 200, headers, body: JSON.stringify({ items: [task] }) });
    if (url.pathname.endsWith('/start')) {
      task.status = 'IN_PROGRESS'; task.started_at = '2026-09-13T01:10:00Z'; task.version += 1;
      return route.fulfill({ status: 200, headers, body: JSON.stringify(task) });
    }
    if (url.pathname.includes('/checklist/')) {
      const item = task.checklist.find(entry => url.pathname.endsWith(entry.id));
      item.result = request.postDataJSON().result; item.version += 1; item.performed_by_id = user.account_id; item.performed_at = '2026-09-13T01:20:00Z'; task.version += 1;
      return route.fulfill({ status: 200, headers, body: JSON.stringify(task) });
    }
    if (url.pathname.endsWith('/submit')) {
      task.status = 'SUBMITTED'; task.submitted_at = '2026-09-13T01:30:00Z'; task.version += 1;
      return route.fulfill({ status: 200, headers, body: JSON.stringify(task) });
    }
    return route.fulfill({ status: 404, headers, body: JSON.stringify({ error: { code: 'ERR-NOTFOUND', message: 'Không tìm thấy.', correlation_id: correlationId } }) });
  });
  try {
    await page.goto(process.env.UX_BASE_URL || 'http://127.0.0.1:3000/');
    await page.getByLabel('Tên đăng nhập').fill(user.username);
    await page.getByLabel('Mật khẩu').fill('browser-only-password');
    await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
    await page.getByRole('navigation', { name: 'Điều hướng chính' }).getByRole('button', { name: 'Vệ sinh môi trường', exact: true }).click();
    await page.getByRole('heading', { name: 'Ca vệ sinh của tôi', exact: true }).waitFor();
    await page.getByText('Sảnh chính', { exact: true }).waitFor();
    assert.ok(await page.getByText('Sảnh chính', { exact: true }).isVisible());
    await page.getByRole('button', { name: 'Bắt đầu', exact: true }).click();
    await page.getByRole('button', { name: 'Nộp kết quả', exact: true }).waitFor();
    await page.getByLabel('Kết quả Sàn sạch').selectOption('PASS');
    await page.getByLabel('Kết quả Thùng rác đã kiểm tra').selectOption('PASS');
    await page.getByRole('button', { name: 'Nộp kết quả', exact: true }).click();
    await page.getByText('Chờ nghiệm thu', { exact: true }).waitFor();
    await page.screenshot({ path: path.join(output, 'cleaning-worker-submitted.png'), fullPage: true });
    const operationRequests = requests.filter(item => item.path.includes('/cleaning/'));
    assert.ok(operationRequests.filter(item => item.method === 'GET').length >= 1);
    assert.deepEqual(operationRequests.filter(item => item.method !== 'GET').map(item => item.method), ['POST', 'PATCH', 'PATCH', 'POST']);
    assert.ok(operationRequests.every(item => item.authorization === `Bearer ${token}`));
    assert.ok(!JSON.stringify(operationRequests).match(/tenant_id|site_id|role/));
    assert.equal(errors.length, 0);
    fs.writeFileSync(path.join(output, 'test-results.json'), JSON.stringify({ passed: 6, errors }, null, 2));
    console.log('CLEANING UX: 6 checks passed.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
