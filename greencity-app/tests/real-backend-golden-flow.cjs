const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const baseUrl = process.env.REAL_BROWSER_BASE_URL || 'http://127.0.0.1:3300';
const backendUrl = process.env.REAL_BROWSER_BACKEND_URL || 'http://127.0.0.1:8800';
const credentialsPath = process.env.REAL_BROWSER_CREDENTIALS_FILE;
const evidenceDir = path.resolve(process.env.REAL_BROWSER_EVIDENCE_DIR || path.join(__dirname, '../artifacts/real-backend'));

if (!credentialsPath) throw new Error('REAL_BROWSER_CREDENTIALS_FILE is required');
const credentials = JSON.parse(fs.readFileSync(credentialsPath, 'utf8'));
const resident = credentials.resident_west;
if (!resident?.initial_password || !resident?.new_password) throw new Error('resident credential fixture is incomplete');

fs.mkdirSync(evidenceDir, { recursive: true });
const checks = [];
const requests = [];
const failures = [];
const check = (name, value = true) => {
  assert.ok(value, name);
  checks.push(name);
  console.log(`PASS ${name}`);
};
const recordRequest = request => {
  const url = new URL(request.url());
  if (!url.pathname.startsWith('/api/v1/')) return;
  const headers = request.headers();
  requests.push({
    path: url.pathname,
    search: url.search,
    method: request.method(),
    authorization: headers.authorization || '',
    idempotencyKey: headers['idempotency-key'] || '',
    body: request.postDataJSON?.(),
  });
};

async function launchBrowser() {
  try {
    return await chromium.launch({ headless: true, channel: 'msedge' });
  } catch {
    return chromium.launch({ headless: true });
  }
}

async function main() {
  const browser = await launchBrowser();
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'vi-VN' });
  const page = await context.newPage();
  page.on('request', recordRequest);
  page.on('pageerror', error => failures.push(error.message));
  const title = `N2 browser request ${Date.now()}`;
  let createRecord;
  let authHeader = '';
  try {
    await page.goto(`${baseUrl}/`, { waitUntil: 'domcontentloaded' });
    check('real backend browser starts on the credential form', await page.getByRole('heading', { name: 'Đăng nhập GreenCity' }).isVisible());
    const health = await fetch(`${backendUrl}/api/v1/health`);
    check('the backend health endpoint is reachable during the browser run', health.ok);

    const login = async (password) => {
      await page.locator('#staff-username').fill('resident_west');
      await page.locator('#staff-password').fill(password);
      await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
    };

    await login(resident.initial_password);
    await page.getByRole('heading', { name: 'Đổi mật khẩu' }).waitFor();
    check('backend enforces the first-login password change in the browser');
    await page.locator('#current-password').fill(resident.initial_password);
    await page.locator('#new-password').fill(resident.new_password);
    await page.locator('#confirm-password').fill(resident.new_password);
    await page.getByRole('button', { name: 'Đổi mật khẩu', exact: true }).click();
    await page.getByRole('heading', { name: 'Đăng nhập GreenCity' }).waitFor();

    await login(resident.new_password);
    await page.getByRole('heading', { name: 'Yêu cầu dịch vụ' }).waitFor();
    await page.getByText('Yêu cầu của tôi', { exact: true }).waitFor();
    check('browser login then /auth/me loads the resident workspace');
    check('resident service options and list came from the real API',
      requests.some(item => item.path === '/api/v1/resident/service-request-options')
      && requests.some(item => item.path === '/api/v1/resident/service-requests'));
    const meRequest = [...requests].reverse().find(item => item.path === '/api/v1/auth/me' && item.authorization);
    authHeader = meRequest?.authorization || '';
    check('the browser keeps the bearer session in memory', Boolean(authHeader));

    await page.getByRole('button', { name: 'Tạo yêu cầu', exact: true }).first().click();
    await page.locator('#resident-create-unit').waitFor();
    const unitId = await page.locator('#resident-create-unit option').nth(1).getAttribute('value');
    await page.locator('#resident-create-unit').selectOption(unitId);
    const categoryId = await page.locator('#resident-create-category option').nth(1).getAttribute('value');
    await page.locator('#resident-create-category').selectOption(categoryId);
    await page.locator('#resident-create-title').fill(title);
    await page.locator('#resident-create-description').fill('Kiểm tra đèn hành lang tại căn hộ mẫu trong dữ liệu disposable.');
    const submitButton = page.getByRole('button', { name: 'Gửi yêu cầu', exact: true });
    const createResponse = page.waitForResponse(response => response.url().includes('/api/v1/resident/service-requests') && response.request().method() === 'POST');
    await Promise.allSettled([submitButton.click(), submitButton.click()]);
    const response = await createResponse;
    const payload = await response.json();
    createRecord = [...requests].reverse().find(item => item.path === '/api/v1/resident/service-requests' && item.method === 'POST');
    check('resident create request reaches the real backend', response.status() === 201 && typeof payload.id === 'string' && typeof payload.code === 'string');
    check('double submit sends one idempotent intent', requests.filter(item => item.path === '/api/v1/resident/service-requests' && item.method === 'POST').length === 1);
    await page.getByText(`Đã gửi yêu cầu ${payload.code}.`, { exact: true }).waitFor();
    await page.getByText(title, { exact: true }).first().waitFor();
    await page.screenshot({ path: path.join(evidenceDir, 'n2-resident-request-created.png'), fullPage: true });

    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.getByRole('heading', { name: 'Đăng nhập GreenCity' }).waitFor();
    await login(resident.new_password);
    await page.getByRole('heading', { name: 'Yêu cầu dịch vụ' }).waitFor();
    await page.getByText(title, { exact: true }).first().waitFor();
    check('created request remains after browser reload and re-authentication');
    await page.screenshot({ path: path.join(evidenceDir, 'n2-resident-request-after-reload.png'), fullPage: true });

    const duplicate = await fetch(`${backendUrl}/api/v1/resident/service-requests`, {
      method: 'POST',
      headers: {
        Authorization: authHeader,
        'Content-Type': 'application/json',
        'Idempotency-Key': createRecord.idempotencyKey,
      },
      body: JSON.stringify(createRecord.body),
    });
    const duplicatePayload = await duplicate.json();
    check('replaying the same Idempotency-Key returns the original request',
      (duplicate.status === 200 || duplicate.status === 201) && duplicatePayload.id === payload.id);

    const timeline = await fetch(`${backendUrl}/api/v1/resident/service-requests/${payload.id}/timeline`, {
      headers: { Authorization: authHeader },
    });
    const timelinePayload = await timeline.json();
    check('the real backend exposes an audit timeline for the created request',
      timeline.ok && Array.isArray(timelinePayload.items) && timelinePayload.items.length >= 1);

    const me = await fetch(`${backendUrl}/api/v1/auth/me`, { headers: { Authorization: authHeader } });
    const mePayload = await me.json();
    check('server-owned resident scope is one site and one linked unit',
      me.ok && Array.isArray(mePayload.allowed_sites) && mePayload.allowed_sites.length === 1
      && Array.isArray(mePayload.resident_unit_ids) && mePayload.resident_unit_ids.length >= 1);

    check('no browser page errors occurred', failures.length === 0);
    console.log(`REAL_BACKEND_GF_01_02 PASS (${checks.length} checks)`);
  } finally {
    try {
      if (failures.length) console.error(`PAGE_ERRORS=${failures.length}`);
    } finally {
      await context.close();
      await browser.close();
    }
  }
}

main().catch(error => {
  console.error(`REAL_BACKEND_GF_FAILED: ${error.message}`);
  process.exitCode = 1;
});
