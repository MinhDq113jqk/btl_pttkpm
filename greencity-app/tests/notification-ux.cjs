const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { randomUUID } = require('node:crypto');

const output = path.resolve(__dirname, '../artifacts/notification-ux');
fs.mkdirSync(output, { recursive: true });

(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'vi-VN' });
  const page = await context.newPage();
  const checks = [];
  const errors = [];
  const requests = [];
  const check = (name, value = true) => { assert.ok(value, name); checks.push(name); console.log(`PASS ${name}`); };
  page.on('pageerror', error => errors.push(error.message));

  const siteId = randomUUID();
  let currentRole = 'cskh';
  const notifId1 = randomUUID();
  const notifId2 = randomUUID();
  const eventId1 = randomUUID();
  let loseFirstRetry = true;
  let shouldFailOutboxLoad = false;

  let notifications = [
    {
      id: notifId1,
      domain_event_id: randomUUID(),
      template_code: 'SRV_ASSIGNED',
      template_snapshot: { title: 'Yêu cầu kiểm tra hệ thống điện', detail: 'Yêu cầu SR-001 đã được tiếp nhận.' },
      delivery_status: 'PUBLISHED',
      delivered_at: '2026-09-15T02:00:00Z',
      read_at: null,
      last_error: null,
      created_at: '2026-09-15T01:50:00Z',
    },
    {
      id: notifId2,
      domain_event_id: randomUUID(),
      template_code: 'SEC_ALERT',
      template_snapshot: { title: 'Cảnh báo an ninh cửa thoát hiểm', detail: 'Cửa tầng 5 mở bất thường.' },
      delivery_status: 'DEAD_LETTER',
      delivered_at: null,
      read_at: null,
      last_error: 'ERR-PUSH-GATEWAY-DOWN',
      created_at: '2026-09-15T01:55:00Z',
    },
  ];

  let outboxEvents = [
    {
      id: eventId1,
      event_type: 'SecurityIncidentReported',
      resource_type: 'SecurityIncident',
      resource_id: randomUUID(),
      correlation_id: randomUUID(),
      delivery_status: 'DEAD_LETTER',
      attempt_count: 3,
      next_attempt_at: '2026-09-15T02:30:00Z',
      last_error: 'ERR-DOWNSTREAM-TIMEOUT',
      created_at: '2026-09-15T01:45:00Z',
      published_at: null,
    },
  ];

  await context.route('**/api/v1/**', async route => {
    const request = route.request();
    const url = new URL(request.url());
    const headers = { 'Content-Type': 'application/json', 'X-Correlation-ID': randomUUID() };
    const idempotencyKey = request.headers()['idempotency-key'];
    requests.push({
      path: url.pathname,
      method: request.method(),
      idempotencyKey,
    });
    const respond = (payload, status = 200) => route.fulfill({ status, headers, body: JSON.stringify(payload) });

    if (url.pathname.endsWith('/auth/login')) return respond({ access_token: 'valid-token' });
    if (url.pathname.endsWith('/auth/me')) {
      return respond({
        account_id: randomUUID(),
        tenant_id: randomUUID(),
        username: `${currentRole}.ux`,
        full_name: `Tài khoản ${currentRole}`,
        roles: [currentRole],
        active_site_id: siteId,
        allowed_sites: [{ id: siteId, code: 'CENTRAL', name: 'GreenCity Central' }],
      });
    }
    if (url.pathname.endsWith('/service-requests')) return respond({ items: [], page: 1, page_size: 20, total: 0 });
    if (url.pathname.endsWith('/notifications') && request.method() === 'GET') {
      return respond({ items: notifications });
    }
    const readMatch = url.pathname.match(/\/notifications\/([^/]+)\/read$/);
    if (readMatch && request.method() === 'POST') {
      notifications = notifications.map(item => item.id === readMatch[1] ? { ...item, read_at: '2026-09-15T02:10:00Z' } : item);
      return respond(notifications.find(item => item.id === readMatch[1]));
    }
    if (url.pathname.endsWith('/outbox/events') && request.method() === 'GET') {
      if (!['admin', 'director'].includes(currentRole)) {
        return respond({ error: { code: 'ERR-FORBIDDEN', message: 'Forbidden' } }, 403);
      }
      if (shouldFailOutboxLoad) {
        return respond({ error: { code: 'ERR-DOWNSTREAM', message: 'Không thể tải trạng thái worker.', correlation_id: 'outbox-load-correlation-id' } }, 503);
      }
      return respond({ items: outboxEvents });
    }
    const retryMatch = url.pathname.match(/\/outbox\/events\/([^/]+)\/retry$/);
    if (retryMatch && request.method() === 'POST') {
      if (loseFirstRetry) {
        loseFirstRetry = false;
        return route.abort('connectionreset');
      }
      outboxEvents = outboxEvents.map(item => item.id === retryMatch[1] ? { ...item, delivery_status: 'PENDING', attempt_count: 0, last_error: null } : item);
      return respond(outboxEvents.find(item => item.id === retryMatch[1]));
    }
    return respond({ error: { code: 'ERR-NOTFOUND', message: 'Not found' } }, 404);
  });

  page.on('console', msg => console.log('PAGE LOG:', msg.text()));
  page.on('pageerror', err => console.log('PAGE ERROR:', err.message));
  page.on('requestfailed', req => console.log('REQ FAILED:', req.url(), req.failure()?.errorText));

  try {
    await page.goto(process.env.UX_BASE_URL || 'http://127.0.0.1:3000/');
    await page.waitForLoadState('networkidle');

    // 1. Test CSKH login & Role visibility
    await page.locator('#staff-username').fill('cskh.ux');
    await page.locator('#staff-password').fill('password');
    await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
    await page.locator('.desktop-shell').waitFor();

    await page.getByRole('navigation', { name: 'Điều hướng chính' }).getByRole('button', { name: /Thông báo/ }).click();
    await page.getByRole('heading', { name: 'Thông báo', exact: true }).waitFor();
    await page.locator('.notifications-page section[aria-label="Danh sách thông báo"]').waitFor();

    check('CSKH sees Inbox', await page.getByRole('tabpanel', { name: 'Danh sách thông báo' }).isVisible());
    check('CSKH does NOT see Outbox tab', await page.locator('.tab-button', { hasText: 'Hàng đợi Outbox' }).count() === 0);
    check('CSKH sees delivery status badge (Đã gửi)', await page.getByText('Đã gửi', { exact: true }).first().isVisible());
    check('CSKH sees delivery status badge (Thất bại)', await page.getByText('Thất bại', { exact: true }).first().isVisible());

    // Mark as read
    await page.getByRole('button', { name: 'Đánh dấu đã đọc' }).first().click();
    await page.getByText('Đã đọc (').first().waitFor();
    check('Mark as read updates UI without page reload', true);

    await page.screenshot({ path: path.join(output, 'cskh-notifications.png'), fullPage: true });

    // 2. Switch to Director role
    currentRole = 'director';
    loseFirstRetry = true;
    shouldFailOutboxLoad = true;
    await page.goto(process.env.UX_BASE_URL || 'http://127.0.0.1:3000/');
    await page.locator('#staff-username').fill('director.ux');
    await page.locator('#staff-password').fill('password');
    await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
    await page.locator('.desktop-shell').waitFor();

    await page.getByRole('navigation', { name: 'Điều hướng chính' }).getByRole('button', { name: /Thông báo/ }).click();
    await page.getByRole('heading', { name: 'Thông báo', exact: true }).waitFor();

    check('Director sees Outbox tab', await page.locator('.tab-button', { hasText: 'Hàng đợi Outbox' }).isVisible());

    // Click Outbox tab
    await page.locator('.tab-button', { hasText: 'Hàng đợi Outbox' }).click();
    await page.getByRole('tabpanel', { name: 'Hàng đợi Outbox & Kênh gửi' }).waitFor();
    await page.getByText('Không thể tải hàng đợi outbox').waitFor();
    check('Outbox loading failure is shown, not rendered as an empty queue', await page.getByText('outbox-load-correlation-id').isVisible());

    shouldFailOutboxLoad = false;
    await page.getByRole('button', { name: 'Thử lại', exact: true }).click();
    await page.getByText('ERR-DOWNSTREAM-TIMEOUT').waitFor();
    check('Outbox retry recovers after its own load failure', true);

    check('Outbox table displays DEAD_LETTER status', await page.getByText('ERR-DOWNSTREAM-TIMEOUT').isVisible());
    const retryBtn = page.getByRole('button', { name: 'Thử lại gửi' }).first();
    check('Retry button is available for failed outbox event', await retryBtn.isVisible());

    // Click Retry - First attempt will lose connection (loseFirstRetry = true)
    await retryBtn.click();
    await page.locator('.error-summary-banner').waitFor();
    check('Lost connection shows error alert banner and does NOT report false success', await page.getByText('Thử lại gửi outbox chưa thành công').isVisible());
    check('Lost connection triggers offline banner', await page.locator('.notification-offline-banner').isVisible());

    // Click Retry again - Second attempt will succeed with same Idempotency-Key
    await retryBtn.click();
    await page.getByText('Đang xử lý', { exact: true }).waitFor();
    check('Successful retry updates outbox event to PENDING/Processing', true);

    const retryCommands = requests.filter(r => r.path.includes('/outbox/events/') && r.path.endsWith('/retry'));
    check('Two retry requests recorded', retryCommands.length === 2);
    check('Both retry requests retained identical Idempotency-Key (AC-36)', retryCommands[0].idempotencyKey === retryCommands[1].idempotencyKey);
    check('Idempotency-Key is not empty', typeof retryCommands[0].idempotencyKey === 'string' && retryCommands[0].idempotencyKey.length > 0);

    await page.screenshot({ path: path.join(output, 'director-outbox-success.png'), fullPage: true });

    check('No unhandled console errors', errors.length === 0);
    fs.writeFileSync(path.join(output, 'test-results.json'), JSON.stringify({ passed: checks.length, errors }, null, 2));
    console.log(`NOTIFICATION UX: ${checks.length} checks passed.`);
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
