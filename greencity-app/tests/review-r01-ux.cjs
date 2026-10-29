const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { randomUUID } = require('node:crypto');

const output = path.resolve(__dirname, '../../documents/deploy_review/evidence/R01');
const baseUrl = process.env.UX_BASE_URL || 'http://127.0.0.1:3000/';
const siteId = randomUUID();
const unitId = randomUUID();
const buildingId = randomUUID();
const personId = randomUUID();
const checks = [];
const errors = [];
const privateRequests = [];
const screenshots = [];
let mode = 'loading';
let releaseProfile;
const profileGate = new Promise(resolve => { releaseProfile = resolve; });
const check = (name, value = true) => { assert.ok(value, name); checks.push(name); console.log(`PASS ${name}`); };

(async () => {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'vi-VN' });
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  const screenshot = async name => {
    await page.screenshot({ path: path.join(output, name), fullPage: true });
    screenshots.push(name);
  };
  await context.route('**/api/v1/**', async route => {
    const request = route.request();
    const url = new URL(request.url());
    const respond = (payload, status = 200) => route.fulfill({ status,
      headers: { 'Content-Type': 'application/json', 'X-Correlation-ID': 'review-r01-fixture' },
      body: JSON.stringify(payload) });
    if (url.pathname.endsWith('/auth/login')) return respond({ access_token: 'review-r01-fixture-only' });
    if (url.pathname.endsWith('/auth/me')) return respond({
      account_id: randomUUID(), tenant_id: randomUUID(), username: 'resident.review', full_name: 'Cư dân kiểm tra',
      roles: ['resident'], active_site_id: siteId, must_change_password: false,
      allowed_sites: [{ id: siteId, code: 'GC-WEST', name: 'GreenCity West' }],
      resident_person_id: personId, resident_unit_ids: [unitId],
    });
    if (url.pathname.endsWith('/portal/profile')) {
      if (mode === 'loading') await profileGate;
      if (mode === 'error') return respond({ error: { code: 'ERR-PROFILE', message: 'Chưa tải được hồ sơ căn hộ.', correlation_id: 'review-r01-fixture' } }, 503);
      return respond({ person: { id: personId, full_name: 'Cư dân kiểm tra' },
        selected_unit_id: mode === 'missing' ? null : unitId,
        units: mode === 'missing' ? [] : [{ id: unitId, unit_number: 'W1-0101', building_id: buildingId,
          building_name: 'Tòa W1', area_m2: 50, permissions: mode === 'granted' ? ['requests', 'finance'] : [] }],
        relationships: [], relationship_history: [],
      });
    }
    if (url.pathname.endsWith('/resident/service-request-options')) return respond({
      buildings: [{ id: buildingId, code: 'W1', name: 'Tòa W1' }], categories: [],
      units: [{ id: unitId, unit_number: 'W1-0101', building_id: buildingId }],
    });
    if (url.pathname.endsWith('/resident/notifications')) return respond({ items: [], unread_count: 0, total: 0, page: 1, page_size: 50 });
    if (url.pathname.endsWith('/portal/assistant/conversations')) return respond({ items: [] });
    if (url.pathname.endsWith('/portal/assistant/options')) return respond({ requests: [], records: [], categories: [] });
    if (url.pathname.endsWith('/resident/service-requests') || url.pathname.includes('/resident/billing/') || url.pathname.endsWith('/portal/finance/ar')) {
      privateRequests.push({ path: url.pathname, unit_id: url.searchParams.get('unit_id'), mode });
      assert.equal(mode, 'granted', 'Private data must wait for confirmed unit permission');
      if (url.pathname.endsWith('/resident/service-requests')) return respond({ items: [], total: 0, page: 1, page_size: 50 });
      if (url.pathname.endsWith('/resident/billing/summary')) return respond({ as_of: url.searchParams.get('as_of'), items: [], total_ar_balance_vnd: 0 });
      if (url.pathname.endsWith('/portal/finance/ar')) return respond({ items: [], cases: [], ledger: [], aging: {}, ledger_balance_vnd: 0 });
      return respond({ as_of: url.searchParams.get('as_of'), items: [] });
    }
    return respond({ error: { code: 'ERR-NOTFOUND', message: 'Fixture không định nghĩa API này.' } }, 404);
  });

  let passed = false;
  try {
    await page.goto(baseUrl);
    await screenshot('login-current.png');
    await page.getByLabel('Tên đăng nhập').fill('resident.review');
    await page.getByLabel('Mật khẩu').fill('fixture-password');
    await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
    await page.locator('.resident-shell').waitFor();
    const requestsTab = page.getByRole('tab', { name: 'Yêu cầu dịch vụ', exact: true });
    const billingTab = page.getByRole('tab', { name: 'Công nợ & hóa đơn', exact: true });
    const notice = page.getByRole('region', { name: 'Xác minh quyền sử dụng căn hộ' });
    const retry = () => notice.getByRole('button', { name: 'Tải lại thông tin căn hộ', exact: true }).click();
    await requestsTab.click();
    await notice.getByRole('heading', { name: 'Đang xác minh căn hộ', exact: true }).waitFor();
    check('loading preserves both core tabs and disables profile retry', await requestsTab.isVisible()
      && await billingTab.isVisible() && await notice.getByRole('button', { name: 'Tải lại thông tin căn hộ', exact: true }).isDisabled());
    check('loading does not request private data', privateRequests.length === 0);
    await screenshot('resident-profile-loading.png');

    mode = 'error'; releaseProfile();
    await notice.getByRole('heading', { name: 'Chưa tải được thông tin căn hộ', exact: true }).waitFor();
    check('profile failure offers retry and support without private data', await notice.getByRole('button', { name: 'Mở Trợ lý & CSKH', exact: true }).isVisible() && privateRequests.length === 0);
    await screenshot('resident-profile-error.png');

    mode = 'missing'; await retry();
    await notice.getByRole('heading', { name: 'Chưa có căn hộ có hiệu lực', exact: true }).waitFor();
    check('missing unit keeps the core tabs and explanation', await requestsTab.isVisible() && await billingTab.isVisible() && privateRequests.length === 0);
    await page.setViewportSize({ width: 390, height: 844 });
    await requestsTab.scrollIntoViewIfNeeded();
    check('missing-unit notice fits within the mobile viewport', await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
    await screenshot('resident-missing-unit-mobile.png');
    await notice.getByRole('button', { name: 'Mở Trợ lý & CSKH', exact: true }).click();
    await page.getByRole('heading', { name: 'Trợ lý & hỗ trợ trực tiếp', exact: true }).waitFor();
    check('support navigation works without an effective unit', await page.getByLabel('Nội dung cần hỗ trợ').isVisible() && privateRequests.length === 0);
    await screenshot('resident-support-mobile.png');

    await page.setViewportSize({ width: 1440, height: 900 });
    await billingTab.click();
    mode = 'denied'; await retry();
    await notice.getByRole('heading', { name: 'Cần xác nhận quyền sử dụng', exact: true }).waitFor();
    check('denied unit keeps billing visible without billing data', await billingTab.isVisible() && privateRequests.length === 0);
    await screenshot('resident-permission-denied.png');

    mode = 'granted'; await retry();
    await page.getByRole('heading', { name: 'Công nợ & hóa đơn', exact: true }).waitFor();
    check('retry restores billing when the server grants unit permission', await notice.count() === 0 && privateRequests.length >= 4);
    await screenshot('resident-billing-granted.png');
    await requestsTab.click();
    await page.getByText('Chưa có yêu cầu nào', { exact: true }).waitFor();
    check('retry restores the request form for the confirmed unit', await page.getByRole('button', { name: 'Tạo yêu cầu', exact: true }).first().isVisible());
    check('all private requests use the confirmed unit', privateRequests.every(request => request.unit_id === unitId));
    await screenshot('resident-requests-granted.png');
    check('no unhandled browser errors', errors.length === 0);
    passed = true;
    console.log(`REVIEW R01 UX: ${checks.length} checks passed.`);
  } finally {
    releaseProfile();
    fs.writeFileSync(path.join(output, 'review-r01-ux-results.json'), JSON.stringify({
      source: 'Edge headless + API fixtures; no live backend/database', baseUrl, passed,
      checks, errors, screenshots, privateRequests, captured_at: new Date().toISOString(),
    }, null, 2));
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
