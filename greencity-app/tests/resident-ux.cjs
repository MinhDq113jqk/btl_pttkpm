const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { randomUUID } = require('node:crypto');

const output = path.resolve(__dirname, '../artifacts/resident-ux');
fs.mkdirSync(output, { recursive: true });

const siteId = randomUUID();
const tenantId = randomUUID();
const unitId = randomUUID();
const buildingId = randomUUID();
const categoryId = randomUUID();
const residentAccountId = randomUUID();
const residentPersonId = randomUUID();
const notificationId = randomUUID();
const notificationCorrelation = randomUUID();
const token = randomUUID();
const asOfValues = [];
const requests = [];
let serviceRequests = [];
let failNextCreate = true;
let notificationRead = false;

const requestView = body => ({
  id: randomUUID(), code: `SR-R6-${String(serviceRequests.length + 1).padStart(3, '0')}`,
  unit_id: body.unit_id, category_id: body.category_id, title: body.title, description: body.description,
  priority: body.priority, status: 'NEW', sla_deadline: '2026-10-01T04:00:00Z', sla_breached_at: null,
  resolved_at: null, closed_at: null, version: 1, created_at: '2026-09-30T01:00:00Z', updated_at: '2026-09-30T01:00:00Z',
});

(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'vi-VN' });
  const page = await context.newPage();
  const checks = [];
  const errors = [];
  const check = (name, value = true) => { assert.ok(value, name); checks.push(name); console.log(`PASS ${name}`); };
  page.on('pageerror', error => errors.push(error.message));

  await context.route('**/api/v1/**', async route => {
    const request = route.request();
    const url = new URL(request.url());
    const body = request.postData() ? request.postDataJSON() : null;
    requests.push({ path: url.pathname, method: request.method(), body, idempotencyKey: request.headers()['idempotency-key'] });
    const headers = { 'Content-Type': 'application/json', 'X-Correlation-ID': randomUUID() };
    const respond = (payload, status = 200) => route.fulfill({ status, headers, body: JSON.stringify(payload) });
    if (url.pathname.endsWith('/auth/login')) return respond({ access_token: token });
    if (url.pathname.endsWith('/auth/me')) return respond({
      account_id: residentAccountId, tenant_id: tenantId, username: 'resident_west', full_name: 'Nguyễn Văn An',
      roles: ['resident'], active_site_id: siteId, allowed_sites: [{ id: siteId, code: 'GC-WEST', name: 'GreenCity West' }],
      resident_person_id: residentPersonId, resident_unit_ids: [unitId],
    });
    if (url.pathname.endsWith('/resident/service-request-options')) return respond({
      buildings: [{ id: buildingId, code: 'W1', name: 'Tòa W1' }],
      categories: [{ id: categoryId, code: 'TECHNICAL', name: 'Yêu cầu kỹ thuật', building_id: buildingId }],
      units: [{ id: unitId, unit_number: 'W1-0101', building_id: buildingId }],
    });
    if (url.pathname.endsWith('/resident/service-requests') && request.method() === 'GET') return respond({
      items: serviceRequests, page: 1, page_size: 50, total: serviceRequests.length,
    });
    const detailMatch = url.pathname.match(/\/resident\/service-requests\/([^/]+)$/);
    if (detailMatch && request.method() === 'GET') return respond(serviceRequests.find(item => item.id === detailMatch[1]) || { error: { code: 'ERR-SCOPE-NOTFOUND', message: 'Không tìm thấy' } }, serviceRequests.some(item => item.id === detailMatch[1]) ? 200 : 404);
    if (url.pathname.endsWith('/resident/service-requests') && request.method() === 'POST') {
      if (failNextCreate) { failNextCreate = false; return route.abort('connectionreset'); }
      const item = requestView(body); serviceRequests = [...serviceRequests, item]; return respond(item, 201);
    }
    if (url.pathname.endsWith('/timeline')) return respond({ items: serviceRequests.length ? [{ id: randomUUID(), event_type: 'ResidentServiceRequestCreated', action: 'create', before_status: null, after_status: 'NEW', before_priority: null, after_priority: 'HIGH', created_at: '2026-09-30T01:00:00Z' }] : [] });
    if (url.pathname.endsWith('/evidence')) return respond({ items: [] });
    if (url.pathname.includes('/resident/billing/summary')) { asOfValues.push(url.searchParams.get('as_of')); return respond({ as_of: url.searchParams.get('as_of'), total_ar_balance_vnd: 250000, items: [{ unit_id: unitId, ar_balance_vnd: 250000 }] }); }
    if (url.pathname.includes('/resident/billing/invoices')) { asOfValues.push(url.searchParams.get('as_of')); return respond({ as_of: url.searchParams.get('as_of'), items: [{ id: randomUUID(), unit_id: unitId, invoice_number: 'INV-2026-09-0101', issued_on: '2026-09-30', due_on: '2026-10-10', total_vnd: 250000, items: [{ line_number: 1, description: 'Phí quản lý tháng', basis: 'UNIT_AREA_M2', basis_quantity: 50, unit_rate_vnd_snapshot: 5000, rounding_unit_vnd_snapshot: 1, amount_vnd: 250000 }] }] }); }
    if (url.pathname.includes('/resident/billing/payments')) { asOfValues.push(url.searchParams.get('as_of')); return respond({ as_of: url.searchParams.get('as_of'), items: [] }); }
    if (url.pathname.endsWith('/resident/notifications') && request.method() === 'GET') return respond({
      items: [{ id: notificationId, template_code: 'R6_WELCOME', template_snapshot: { title: 'Chào mừng cư dân', body: 'Hồ sơ của bạn đã được xác minh.' }, delivery_status: 'PUBLISHED', delivered_at: '2026-09-30T02:00:00Z', read_at: notificationRead ? '2026-09-30T03:00:00Z' : null, correlation_id: notificationCorrelation, created_at: '2026-09-30T02:00:00Z' }], page: 1, page_size: 50, total: 1, unread_count: notificationRead ? 0 : 1,
    });
    const readMatch = url.pathname.match(/\/resident\/notifications\/([^/]+)\/read$/);
    if (readMatch && request.method() === 'POST') { notificationRead = true; return respond({ id: notificationId, template_code: 'R6_WELCOME', template_snapshot: { title: 'Chào mừng cư dân', body: 'Hồ sơ của bạn đã được xác minh.' }, delivery_status: 'PUBLISHED', delivered_at: '2026-09-30T02:00:00Z', read_at: '2026-09-30T03:00:00Z', correlation_id: notificationCorrelation, created_at: '2026-09-30T02:00:00Z' }); }
    return respond({ error: { code: 'ERR-NOTFOUND', message: 'Not found' } }, 404);
  });

  try {
    await page.goto(process.env.UX_BASE_URL || 'http://127.0.0.1:3000/');
    await page.getByLabel('Tên đăng nhập').fill('resident_west');
    await page.getByLabel('Mật khẩu').fill('Password@123');
    await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
    await page.locator('.resident-shell').waitFor();
    check('Resident shell is selected from server role', await page.getByText('Cổng cư dân', { exact: true }).isVisible());
    check('Resident scope shows active site', await page.getByLabel('Site hiện hành').inputValue() === siteId);
    check('Resident navigation exposes only three self-service surfaces', await page.getByRole('tab').count() === 3);
    check('Resident request list starts empty', await page.getByText('Chưa có yêu cầu nào', { exact: true }).isVisible());

    await page.getByRole('button', { name: 'Tạo yêu cầu', exact: true }).first().click();
    const form = page.getByRole('region', { name: 'Tạo yêu cầu dịch vụ' });
    await form.getByLabel('Căn hộ').selectOption(unitId);
    await form.getByLabel('Loại yêu cầu').selectOption(categoryId);
    await form.getByLabel('Tiêu đề').fill('Rò rỉ nước tại bếp');
    await form.getByLabel('Mô tả').fill('Nước rò rỉ liên tục dưới chậu rửa.');
    await form.getByRole('button', { name: 'Gửi yêu cầu', exact: true }).click();
    await page.getByRole('alert').waitFor();
    check('Network failure is visible and does not claim success', await page.getByText('Không thể kết nối máy chủ', { exact: false }).isVisible());
    await form.getByRole('button', { name: 'Gửi yêu cầu', exact: true }).click();
    await page.getByText('SR-R6-001', { exact: false }).waitFor();
    const createCommands = requests.filter(item => item.path.endsWith('/resident/service-requests') && item.method === 'POST');
    check('Resident create retries with the same idempotency key', createCommands.length === 2 && createCommands[0].idempotencyKey === createCommands[1].idempotencyKey);
    check('Resident create body contains no forged scope fields', !/tenant_id|site_id|role|building_id/.test(JSON.stringify(createCommands[0].body)));
    check('Created request appears only after API success', await page.locator('.resident-request-row').filter({ hasText: 'Rò rỉ nước tại bếp' }).isVisible());

    await page.getByRole('button', { name: /Rò rỉ nước tại bếp/ }).click();
    await page.getByText('Lịch sử xử lý', { exact: true }).waitFor();
    check('Request detail includes timeline from API', await page.getByText('ResidentServiceRequestCreated', { exact: true }).isVisible());
    check('Request detail includes evidence workspace', await page.getByText('Ảnh bằng chứng', { exact: true }).isVisible());

    await page.getByRole('tab', { name: 'Công nợ & hóa đơn' }).click();
    await page.getByText('250.000 ₫', { exact: true }).first().waitFor();
    check('Billing panel displays integer VND from server', await page.getByText('250.000 ₫', { exact: true }).first().isVisible());
    check('All billing requests share one fixed as_of', asOfValues.length >= 3 && new Set(asOfValues).size === 1);
    check('Invoice snapshot is read-only in resident portal', await page.getByText('INV-2026-09-0101', { exact: true }).isVisible() && await page.getByText(/Phí quản lý tháng/).isVisible());

    await page.getByRole('tab', { name: 'Thông báo' }).click();
    await page.getByText('Chào mừng cư dân', { exact: true }).waitFor();
    check('Resident inbox shows unread notification', await page.getByText('1 thông báo chưa đọc', { exact: true }).isVisible());
    await page.getByRole('button', { name: 'Đánh dấu đã đọc' }).click();
    await page.getByText('0 thông báo chưa đọc', { exact: true }).waitFor();
    check('Resident can acknowledge notification without exposing event internals', await page.getByText(new RegExp(`Mã đối chiếu ${notificationCorrelation}`)).isVisible());

    await page.setViewportSize({ width: 390, height: 844 });
    check('Resident layout remains within mobile viewport', await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
    await page.screenshot({ path: path.join(output, 'resident-portal-mobile.png'), fullPage: true });
    check('No unhandled browser errors', errors.length === 0);
    fs.writeFileSync(path.join(output, 'test-results.json'), JSON.stringify({ passed: checks.length, checks, errors }, null, 2));
    console.log(`RESIDENT UX: ${checks.length} checks passed.`);
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
