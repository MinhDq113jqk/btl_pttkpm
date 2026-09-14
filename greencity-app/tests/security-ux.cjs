const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { randomUUID } = require('node:crypto');
const { chromium } = require('playwright');

const output = path.resolve(__dirname, '../artifacts/security-ux');
fs.mkdirSync(output, { recursive: true });

const token = randomUUID();
const correlationId = randomUUID();
const siteId = randomUUID();
const user = {
  account_id: randomUUID(), tenant_id: randomUUID(), username: 'security.browser', full_name: 'Nhân viên An ninh',
  roles: ['security'], active_site_id: siteId, allowed_sites: [{ id: siteId, code: 'CENTRAL', name: 'GreenCity Central' }],
};
const windowId = randomUUID();
const shiftId = randomUUID();
const patrolWindow = {
  id: windowId, security_shift_id: shiftId, patrol_point_id: randomUUID(), patrol_point_code: 'SEC-LOBBY', patrol_point_name: 'Sảnh chính',
  building_id: randomUUID(), window_start_at: '2026-09-14T01:00:00Z', window_end_at: '2026-09-14T01:30:00Z', status: 'SCHEDULED',
  missed_reason: null, completed_at: null, version: 1, logs: [],
};
const shift = {
  id: shiftId, tenant_id: user.tenant_id, site_id: siteId, building_id: patrolWindow.building_id, assigned_to_id: user.account_id,
  scheduled_start_at: '2026-09-14T01:00:00Z', scheduled_end_at: '2026-09-14T03:00:00Z', status: 'PLANNED', version: 1,
  handoffs: [], visitors: [], patrol_windows: [patrolWindow],
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
    if (url.pathname.endsWith('/security/dashboard') && request.method() === 'GET') return route.fulfill({ status: 200, headers, body: JSON.stringify({ shifts: [shift], exceptions: [], incidents: [] }) });
    if (url.pathname.endsWith(`/security/shifts/${shiftId}/start`)) {
      shift.status = 'IN_PROGRESS'; shift.version += 1;
      return route.fulfill({ status: 200, headers, body: JSON.stringify(shift) });
    }
    if (url.pathname.endsWith(`/security/patrol-windows/${windowId}/logs`)) {
      patrolWindow.logs.push({ id: randomUUID(), patrol_window_id: windowId, recorded_by_id: user.account_id, event_type: 'CHECK_IN', note: null, occurred_at: '2026-09-14T01:05:00Z', created_at: '2026-09-14T01:05:00Z' });
      return route.fulfill({ status: 201, headers, body: JSON.stringify(patrolWindow) });
    }
    if (url.pathname.endsWith(`/security/patrol-windows/${windowId}/complete`)) {
      patrolWindow.status = 'COMPLETED'; patrolWindow.completed_at = '2026-09-14T01:10:00Z'; patrolWindow.version += 1;
      return route.fulfill({ status: 200, headers, body: JSON.stringify(patrolWindow) });
    }
    return route.fulfill({ status: 404, headers, body: JSON.stringify({ error: { code: 'ERR-NOTFOUND', message: 'Không tìm thấy.', correlation_id: correlationId } }) });
  });
  try {
    await page.goto(process.env.UX_BASE_URL || 'http://127.0.0.1:3000/');
    await page.getByLabel('Tên đăng nhập').fill(user.username);
    await page.getByLabel('Mật khẩu').fill('browser-only-password');
    await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
    await page.getByRole('navigation', { name: 'Điều hướng chính' }).getByRole('button', { name: 'An ninh & Tuần tra', exact: true }).click();
    await page.getByRole('heading', { name: 'Ca trực và tuần tra của tôi', exact: true }).waitFor();
    await page.getByText('Sảnh chính', { exact: true }).waitFor();
    await page.getByRole('button', { name: 'Bắt đầu ca', exact: true }).click();
    await page.getByRole('button', { name: 'Check-in', exact: true }).click();
    await page.getByRole('button', { name: 'Hoàn thành', exact: true }).click();
    await page.getByText('Đã tuần tra', { exact: true }).waitFor();
    await page.screenshot({ path: path.join(output, 'security-worker-completed.png'), fullPage: true });
    const operationRequests = requests.filter(item => item.path.includes('/security/'));
    assert.ok(operationRequests.filter(item => item.method === 'GET').length >= 3);
    assert.deepEqual(operationRequests.filter(item => item.method !== 'GET').map(item => item.method), ['POST', 'POST', 'POST']);
    assert.ok(operationRequests.every(item => item.authorization === `Bearer ${token}`));
    assert.ok(!JSON.stringify(operationRequests).match(/tenant_id|site_id|role/));
    assert.equal(errors.length, 0);
    fs.writeFileSync(path.join(output, 'test-results.json'), JSON.stringify({ passed: 7, errors }, null, 2));
    console.log('SECURITY UX: 7 checks passed.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
