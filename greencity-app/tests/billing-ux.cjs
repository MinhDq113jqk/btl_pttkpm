const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { randomUUID } = require('node:crypto');
const { chromium } = require('playwright');

const output = path.resolve(__dirname, '../artifacts/billing-ux');
fs.mkdirSync(output, { recursive: true });

const token = randomUUID();
const correlationId = randomUUID();
const siteId = randomUUID();
const buildingId = randomUUID();
const billingAccountId = randomUUID();
const user = {
  account_id: randomUUID(), tenant_id: randomUUID(), username: 'accountant.browser', full_name: 'Kế toán demo',
  roles: ['accountant'], active_site_id: siteId, allowed_sites: [{ id: siteId, code: 'CENTRAL', name: 'GreenCity Central' }],
};
const billingAccount = {
  id: billingAccountId, tenant_id: user.tenant_id, site_id: siteId, building_id: buildingId, unit_id: randomUUID(),
  account_number: 'BA-0101', status: 'ACTIVE', opened_on: '2026-01-01', version: 1,
};
let policies = [];
let periods = [];
let runs = [];
let invoices = [];
let payments = [];
let unmatched = [];
let credits = [];

const policyView = body => ({
  id: randomUUID(), building_id: body.building_id, code: body.code, name: body.name, is_active: true,
  versions: [{
    id: randomUUID(), fee_policy_id: randomUUID(), version_number: 1, effective_from: body.effective_from,
    effective_to: null, unit_rate_vnd: body.unit_rate_vnd, basis: 'UNIT_AREA_M2',
    rounding_unit_vnd: body.rounding_unit_vnd, published_at: '2026-10-01T00:00:00Z',
  }],
});

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
    const headers = { 'Content-Type': 'application/json', 'X-Correlation-ID': correlationId };
    const body = request.postData() ? request.postDataJSON() : null;
    requests.push({ path: url.pathname, method: request.method(), body, authorization: request.headers().authorization, idempotencyKey: request.headers()['idempotency-key'] });
    if (url.pathname.endsWith('/auth/login')) return route.fulfill({ status: 200, headers, body: JSON.stringify({ access_token: token }) });
    if (url.pathname.endsWith('/auth/me')) return route.fulfill({ status: 200, headers, body: JSON.stringify(user) });
    if (url.pathname.endsWith('/service-requests') && request.method() === 'GET') {
      return route.fulfill({ status: 200, headers, body: JSON.stringify({ items: [], page: 1, page_size: 20, total: 0 }) });
    }
    if (url.pathname.endsWith('/billing/accounts') && request.method() === 'GET') {
      return route.fulfill({ status: 200, headers, body: JSON.stringify({ items: [billingAccount] }) });
    }
    if (url.pathname.endsWith('/billing/fee-policies') && request.method() === 'GET') {
      return route.fulfill({ status: 200, headers, body: JSON.stringify({ items: policies }) });
    }
    if (url.pathname.endsWith('/billing/fee-policies') && request.method() === 'POST') {
      const policy = policyView(body);
      policies = [...policies, policy];
      return route.fulfill({ status: 201, headers, body: JSON.stringify(policy) });
    }
    if (url.pathname.endsWith('/billing/periods') && request.method() === 'GET') {
      return route.fulfill({ status: 200, headers, body: JSON.stringify({ items: periods }) });
    }
    if (url.pathname.endsWith('/billing/periods') && request.method() === 'POST') {
      const period = { id: randomUUID(), building_id: body.building_id, period_key: body.period_key, period_start: body.period_start, period_end: body.period_end, cutoff_at: body.cutoff_at, status: 'OPEN', version: 1 };
      periods = [...periods, period];
      return route.fulfill({ status: 201, headers, body: JSON.stringify(period) });
    }
    if (url.pathname.endsWith('/billing/runs') && request.method() === 'GET') {
      return route.fulfill({ status: 200, headers, body: JSON.stringify({ items: runs }) });
    }
    if (url.pathname.endsWith('/billing/runs') && request.method() === 'POST') {
      const run = {
        id: randomUUID(), accounting_period_id: body.accounting_period_id, fee_policy_version_id: body.fee_policy_version_id,
        building_id: buildingId, run_key: body.run_key, status: 'POSTED', cutoff_at: periods[0].cutoff_at,
        retry_count: 0, failure_code: null, failure_detail: null, failed_at: null, completed_at: '2026-10-31T00:00:00Z', version: 2,
      };
      const invoice = {
        id: randomUUID(), billing_account_id: billingAccountId, billing_run_id: run.id, accounting_period_id: body.accounting_period_id,
        building_id: buildingId, invoice_number: 'INV-2026-10-BA0101', issued_on: '2026-10-31', due_on: '2026-10-31',
        status: 'ISSUED', total_vnd: 963000, outstanding_vnd: 963000, voided_at: null, void_reason: null, version: 1,
        items: [{ id: randomUUID(), line_number: 1, description: 'UNIT AREA M2', basis: 'UNIT_AREA_M2', basis_quantity: 80.25, unit_rate_vnd_snapshot: 12000, rounding_unit_vnd_snapshot: 1, amount_vnd: 963000, source_pending_charge_id: null }],
      };
      runs = [...runs, run];
      invoices = [...invoices, invoice];
      return route.fulfill({ status: 201, headers, body: JSON.stringify(run) });
    }
    if (url.pathname.endsWith('/billing/invoices') && request.method() === 'GET') {
      return route.fulfill({ status: 200, headers, body: JSON.stringify({ items: invoices }) });
    }
    if (url.pathname.endsWith('/billing/payments') && request.method() === 'GET') {
      return route.fulfill({ status: 200, headers, body: JSON.stringify({ items: payments }) });
    }
    if (url.pathname.endsWith('/billing/unmatched-payments') && request.method() === 'GET') {
      return route.fulfill({ status: 200, headers, body: JSON.stringify({ items: unmatched }) });
    }
    if (url.pathname.endsWith('/billing/overpayment-credits') && request.method() === 'GET') {
      return route.fulfill({ status: 200, headers, body: JSON.stringify({ items: credits }) });
    }
    return route.fulfill({ status: 404, headers, body: JSON.stringify({ error: { code: 'ERR-NOTFOUND', message: 'Không tìm thấy.', correlation_id: correlationId } }) });
  });
  try {
    await page.goto(process.env.UX_BASE_URL || 'http://127.0.0.1:3000/');
    await page.getByLabel('Tên đăng nhập').fill(user.username);
    await page.getByLabel('Mật khẩu').fill('browser-only-password');
    await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
    await page.getByRole('navigation', { name: 'Điều hướng chính' }).getByRole('button', { name: 'Tài chính & Công nợ', exact: true }).click();
    await page.getByRole('heading', { name: 'Thiết lập phí và phát hành hóa đơn', exact: true }).waitFor();

    const policyForm = page.getByRole('heading', { name: 'Chính sách phí cơ bản', exact: true }).locator('..');
    await policyForm.getByLabel('Tòa nhà').selectOption(buildingId);
    await policyForm.getByLabel('Mã policy').fill('PHI-QL');
    await policyForm.getByLabel('Tên policy').fill('Phí quản lý vận hành');
    await policyForm.getByLabel('Hiệu lực từ').fill('2026-10-01');
    await policyForm.getByLabel('Đơn giá (VND/m²)').fill('12000');
    await policyForm.getByLabel('Làm tròn (VND)').fill('1');
    await policyForm.getByRole('button', { name: 'Publish policy', exact: true }).click();
    await page.getByRole('option', { name: /PHI-QL v1/ }).waitFor({ state: 'attached' });

    const periodForm = page.getByRole('heading', { name: 'Mở kỳ kế toán', exact: true }).locator('..');
    await periodForm.getByLabel('Tòa nhà').selectOption(buildingId);
    await periodForm.getByLabel('Mã kỳ').fill('2026-10');
    await periodForm.getByLabel('Bắt đầu').fill('2026-10-01');
    await periodForm.getByLabel('Kết thúc').fill('2026-10-31');
    await periodForm.getByLabel('Cutoff').fill('2026-10-15T00:00');
    await periodForm.getByRole('button', { name: 'Mở kỳ', exact: true }).click();
    await page.getByLabel('Chạy Billing Run').getByRole('option', { name: /2026-10.*OPEN/ }).waitFor({ state: 'attached' });

    const runPanel = page.getByLabel('Chạy Billing Run');
    await runPanel.getByLabel('Kỳ').selectOption(periods[0].id);
    await runPanel.getByLabel('Version phí').selectOption(policies[0].versions[0].id);
    await runPanel.getByRole('button', { name: 'Chạy & phát hành', exact: true }).click();
    await page.getByText('INV-2026-10-BA0101', { exact: true }).waitFor();
    await page.getByText('963.000 ₫', { exact: true }).first().waitFor();
    await page.getByLabel('Hóa đơn đã phát hành').scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(output, 'billing-golden-flow.png'), fullPage: true });

    const billingRequests = requests.filter(item => item.path.includes('/billing/'));
    const commands = billingRequests.filter(item => item.method !== 'GET');
    assert.deepEqual(commands.map(item => item.method), ['POST', 'POST', 'POST']);
    assert.ok(billingRequests.every(item => item.authorization === `Bearer ${token}`));
    assert.ok(commands.every(item => typeof item.idempotencyKey === 'string' && item.idempotencyKey.length > 0));
    assert.ok(commands.every(item => !/"(?:tenant_id|site_id|role)"/.test(JSON.stringify(item.body))));
    assert.equal(errors.length, 0);
    fs.writeFileSync(path.join(output, 'test-results.json'), JSON.stringify({ passed: 10, errors }, null, 2));
    console.log('BILLING UX: 10 checks passed.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
