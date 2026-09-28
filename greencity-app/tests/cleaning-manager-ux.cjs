const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const { randomUUID } = require('node:crypto');

const token = randomUUID();
const accountId = randomUUID();
const siteId = randomUUID();
const buildingId = randomUUID();
const routeId = randomUUID();
const correlationId = randomUUID();
const user = {
  account_id: accountId, tenant_id: randomUUID(), username: 'director.cleaning.ux', full_name: 'Giám đốc',
  roles: ['director'], active_site_id: siteId, allowed_sites: [{ id: siteId, code: 'CENTRAL', name: 'GreenCity Central' }],
};
const cleanerId = randomUUID();
const route = { id: routeId, code: 'CLN-LOBBY', name: 'Tuyến sảnh', building_id: buildingId };
const makeTask = (areaCode, areaName, status, assignedTo = null) => ({
  id: randomUUID(), shift_id: randomUUID(), route_id: routeId, route_code: route.code, route_name: route.name,
  area_id: randomUUID(), area_code: areaCode, area_name: areaName, tenant_id: user.tenant_id, site_id: siteId,
  building_id: buildingId, assigned_to_id: assignedTo, status,
  scheduled_start_at: '2026-09-27T01:00:00Z', scheduled_end_at: '2026-09-27T03:00:00Z',
  started_at: status === 'SUBMITTED' ? '2026-09-27T01:10:00Z' : null,
  submitted_at: status === 'SUBMITTED' ? '2026-09-27T01:25:00Z' : null,
  accepted_at: null, accepted_by_id: null, rework_work_order_id: null, rework_case_id: null, version: 2,
  checklist: [{ id: randomUUID(), position: 1, label: 'Sàn sạch', is_required: true, result: status === 'SUBMITTED' ? 'PASS' : 'PENDING', note: null, performed_by_id: status === 'SUBMITTED' ? cleanerId : null, performed_at: status === 'SUBMITTED' ? '2026-09-27T01:20:00Z' : null, version: 2 }],
});
const submittedTask = makeTask('LOBBY', 'Sảnh đã nộp', 'SUBMITTED', cleanerId);
let tasks = [submittedTask];
let createdShift = null;
const calls = [];
const errors = [];

(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, locale: 'vi-VN' });
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/v1/**', async routeRequest => {
    const request = routeRequest.request();
    const url = new URL(request.url());
    const body = (() => { try { return request.postDataJSON?.(); } catch { return null; } })();
    calls.push({ path: url.pathname, method: request.method(), body, authorization: request.headers().authorization, key: request.headers()['idempotency-key'] });
    const headers = { 'Content-Type': 'application/json', 'X-Correlation-ID': correlationId };
    const respond = (payload, status = 200) => routeRequest.fulfill({ status, headers, body: JSON.stringify(payload) });
    if (url.pathname.endsWith('/auth/login')) return respond({ access_token: token });
    if (url.pathname.endsWith('/auth/me')) return respond(user);
    if (url.pathname.endsWith('/service-requests')) return respond({ items: [], page: 1, page_size: 20, total: 0 });
    if (url.pathname.endsWith('/notifications')) return respond({ items: [] });
    if (url.pathname.endsWith('/cleaning/routes')) return respond([route]);
    if (url.pathname.endsWith('/cleaning/tasks') && request.method() === 'GET') return respond({ items: tasks });
    if (url.pathname.endsWith('/cleaning/assignees')) return respond([{ id: cleanerId, full_name: 'Nhân viên vệ sinh A' }]);
    if (url.pathname.endsWith('/cleaning/shifts') && request.method() === 'POST') {
      const newTasks = [makeTask('LOBBY-2', 'Sảnh phụ', 'PLANNED'), makeTask('YARD', 'Sân vườn', 'PLANNED')];
      createdShift = { id: randomUUID(), route_id: routeId, status: 'PLANNED', version: 1, scheduled_start_at: body.scheduled_start_at, scheduled_end_at: body.scheduled_end_at, tasks: newTasks };
      tasks = [...tasks, ...newTasks];
      return respond(createdShift, 201);
    }
    const task = tasks.find(item => url.pathname.includes(item.id));
    if (task && url.pathname.endsWith('/assign')) { task.assigned_to_id = body.assignee_id; task.status = 'ASSIGNED'; task.version += 1; return respond(task); }
    if (task && url.pathname.endsWith('/accept')) { task.status = 'ACCEPTED'; task.accepted_at = '2026-09-27T02:00:00Z'; task.accepted_by_id = accountId; task.version += 1; return respond(task); }
    if (task && url.pathname.endsWith('/missed')) { task.status = 'MISSED'; task.version += 1; return respond(task); }
    if (task && url.pathname.endsWith('/cancel')) { task.status = 'CANCELLED'; task.version += 1; return respond(task); }
    return respond({ error: { code: 'ERR-NOTFOUND', message: 'Không tìm thấy.', correlation_id: correlationId } }, 404);
  });

  try {
    await page.goto(process.env.UX_BASE_URL || 'http://127.0.0.1:3000/');
    await page.locator('#staff-username').fill(user.username);
    await page.locator('#staff-password').fill(`test-${randomUUID()}`);
    await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
    await page.getByRole('navigation', { name: 'Điều hướng chính' }).getByRole('button', { name: 'Vệ sinh môi trường', exact: true }).click();
    await page.getByRole('heading', { name: 'Điều phối ca vệ sinh', exact: true }).waitFor();
    await page.getByLabel('Tuyến').selectOption(routeId);
    await page.getByLabel('Bắt đầu').fill('2026-09-27T08:00');
    await page.getByLabel('Kết thúc').fill('2026-09-27T10:00');
    await page.getByRole('button', { name: 'Tạo ca', exact: true }).click();
    await page.getByText('Đã tạo ca vệ sinh với 2 khu vực.', { exact: true }).waitFor();
    assert.ok(createdShift && createdShift.tasks.length === 2);

    const assignedCard = page.locator('.cleaning-task-card').filter({ hasText: 'Sảnh phụ' });
    await assignedCard.getByLabel('Phân công').focus();
    await assignedCard.getByLabel('Phân công').selectOption(cleanerId);
    await assignedCard.getByRole('button', { name: 'Phân công', exact: true }).click();
    await assignedCard.locator('.status-badge').filter({ hasText: 'Đã phân công' }).waitFor();
    assert.equal(tasks.find(item => item.area_name === 'Sảnh phụ').assigned_to_id, cleanerId);

    const missedCard = page.locator('.cleaning-task-card').filter({ hasText: 'Sảnh đã nộp' });
    await missedCard.getByRole('button', { name: 'Nghiệm thu', exact: true }).click();
    await missedCard.getByText('Đã nghiệm thu', { exact: true }).waitFor();
    assert.equal(submittedTask.status, 'ACCEPTED');

    const missedNewTask = page.locator('.cleaning-task-card').filter({ hasText: 'Sân vườn' });
    await missedNewTask.getByLabel(/Lý do ngoại lệ/).fill('Không bố trí được nhân sự trong ca.');
    await missedNewTask.getByRole('button', { name: 'Bỏ lỡ task', exact: true }).click();
    await missedNewTask.getByText('Bỏ lỡ', { exact: true }).waitFor();
    const cancelledTask = page.locator('.cleaning-task-card').filter({ hasText: 'Sảnh phụ' });
    await cancelledTask.getByLabel(/Lý do ngoại lệ/).fill('Tuyến được điều chỉnh.');
    await cancelledTask.getByRole('button', { name: 'Hủy task', exact: true }).click();
    await cancelledTask.getByText('Đã hủy', { exact: true }).waitFor();
    assert.deepEqual(tasks.slice(1).map(item => item.status), ['CANCELLED', 'MISSED']);
    assert.ok(calls.filter(item => item.path.includes('/cleaning/') && item.method !== 'GET').every(item => item.authorization === `Bearer ${token}`));
    assert.ok(!JSON.stringify(calls).match(/tenant_id|site_id|role/));
    assert.equal(errors.length, 0);
    console.log('CLEANING MANAGER UX: 8 checks passed.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
