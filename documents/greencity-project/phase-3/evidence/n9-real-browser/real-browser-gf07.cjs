const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');

const credentials = JSON.parse(fs.readFileSync(process.env.REAL_BROWSER_CREDENTIALS_FILE, 'utf8'));
const baseUrl = 'https://localhost/';
const evidenceDir = process.env.REAL_BROWSER_EVIDENCE_DIR;
const checks = [];
const errors = [];
const apiFailures = [];
const requests = [];
const billingSnapshots = { accounts: [], periods: [], policies: [], invoices: [] };

const check = (name, value = true) => { assert.ok(value, name); checks.push(name); console.log(`PASS ${name}`); };
const commandKey = prefix => `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
const isoForInput = (year, month, day, hour = 23, minute = 59) => `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}T${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
const waitFor = async (predicate, timeout = 10000) => {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const value = predicate();
    if (value) return value;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error('Timed out waiting for backend snapshot.');
};

function attachObservers(page, label) {
  page.on('pageerror', error => errors.push(`${label}:${error.message}`));
  page.on('request', request => {
    const url = new URL(request.url());
    if (!url.pathname.startsWith('/api/v1/')) return;
    const body = request.postData() ? request.postDataJSON() : null;
    requests.push({ label, path: url.pathname, method: request.method(), body, authorization: request.headers().authorization, idempotencyKey: request.headers()['idempotency-key'], query: Object.fromEntries(url.searchParams.entries()) });
  });
  page.on('response', response => {
    const url = new URL(response.url());
    if (!url.pathname.startsWith('/api/v1/')) return;
    if (response.status() >= 400 && (url.pathname.includes('/billing/') || url.pathname.includes('/resident/billing/'))) {
      apiFailures.push(`${response.status()}:${url.pathname}`);
    }
    if (response.request().method() !== 'GET') return;
    if (url.pathname.endsWith('/billing/accounts') || url.pathname.endsWith('/billing/periods') || url.pathname.endsWith('/billing/fee-policies') || url.pathname.endsWith('/billing/invoices')) {
      response.json().then(payload => {
        if (Array.isArray(payload.items)) {
          if (url.pathname.endsWith('/billing/accounts')) billingSnapshots.accounts = payload.items;
          if (url.pathname.endsWith('/billing/periods')) billingSnapshots.periods = payload.items;
          if (url.pathname.endsWith('/billing/fee-policies')) billingSnapshots.policies = payload.items;
          if (url.pathname.endsWith('/billing/invoices')) billingSnapshots.invoices = payload.items;
        }
      }).catch(() => {});
    }
  });
}

async function login(page, username) {
  await page.goto(baseUrl, { waitUntil: 'networkidle' });
  await page.locator('#staff-username').fill(username);
  await page.locator('#staff-password').fill(credentials[username]);
  await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
}

function chooseHistoricalPeriod(existing) {
  const used = new Set(existing.map(item => item.period_key));
  const now = new Date();
  for (let offset = 1; offset <= 18; offset += 1) {
    const candidate = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - offset, 1));
    const key = `${candidate.getUTCFullYear()}-${String(candidate.getUTCMonth() + 1).padStart(2, '0')}`;
    if (!used.has(key)) {
      const lastDay = new Date(Date.UTC(candidate.getUTCFullYear(), candidate.getUTCMonth() + 1, 0)).getUTCDate();
      return { key, start: `${key}-01`, end: `${key}-${String(lastDay).padStart(2, '0')}`, cutoff: isoForInput(candidate.getUTCFullYear(), candidate.getUTCMonth() + 1, lastDay) };
    }
  }
  throw new Error('No unused historical accounting period is available.');
}

(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const context = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 1440, height: 960 }, locale: 'vi-VN' });
  const page = await context.newPage();
  attachObservers(page, 'accountant');
  try {
    await login(page, 'accountant_west');
    await page.locator('.desktop-shell').waitFor({ timeout: 15000 });
    const financeButton = page.getByRole('navigation', { name: 'Điều hướng chính' }).getByRole('button', { name: 'Tài chính & Công nợ', exact: true });
    await financeButton.click();
    await page.getByRole('heading', { name: 'Thiết lập phí và phát hành hóa đơn', exact: true }).waitFor();
    await page.waitForTimeout(500);
    check('GF07 accountant can open the real finance workspace');

    const account = billingSnapshots.accounts[0];
    assert.ok(account?.id && account.building_id, 'A scoped Billing Account is required for GF07.');
    const buildingId = account.building_id;
    const periodInput = chooseHistoricalPeriod(billingSnapshots.periods);
    const policyCode = `GF07-${Date.now()}`;
    const policyForm = page.getByRole('heading', { name: 'Chính sách phí cơ bản', exact: true }).locator('..');
    await policyForm.getByLabel('Tòa nhà').selectOption(buildingId);
    await policyForm.getByLabel('Mã policy').fill(policyCode);
    await policyForm.getByLabel('Tên policy').fill('Phí GF07 đối soát thật');
    await policyForm.getByLabel('Hiệu lực từ').fill(periodInput.start);
    await policyForm.getByLabel('Đơn giá (VND/m²)').fill('12000');
    await policyForm.getByLabel('Làm tròn (VND)').fill('1');
    const policyResponse = page.waitForResponse(response => response.url().endsWith('/api/v1/billing/fee-policies') && response.request().method() === 'POST');
    await policyForm.getByRole('button', { name: 'Publish policy', exact: true }).click();
    assert.equal((await policyResponse).status(), 201);
    await page.getByRole('option', { name: new RegExp(`${policyCode} v1`) }).waitFor({ state: 'attached' });
    check('GF07 Fee Policy is published through the real backend');

    const periodForm = page.getByRole('heading', { name: 'Mở kỳ kế toán', exact: true }).locator('..');
    await periodForm.getByLabel('Tòa nhà').selectOption(buildingId);
    await periodForm.getByLabel('Mã kỳ').fill(periodInput.key);
    await periodForm.getByLabel('Bắt đầu').fill(periodInput.start);
    await periodForm.getByLabel('Kết thúc').fill(periodInput.end);
    await periodForm.getByLabel('Cutoff').fill(periodInput.cutoff);
    const periodResponse = page.waitForResponse(response => response.url().endsWith('/api/v1/billing/periods') && response.request().method() === 'POST');
    await periodForm.getByRole('button', { name: 'Mở kỳ', exact: true }).click();
    const period = await periodResponse.then(async response => { assert.equal(response.status(), 201); return response.json(); });
    check('GF07 Accounting Period is opened with a timezone-aware cutoff');

    const runPanel = page.getByLabel('Chạy Billing Run');
    await runPanel.getByLabel('Kỳ').selectOption(period.id);
    const policy = await waitFor(() => billingSnapshots.policies.find(item => item.code === policyCode));
    const policyVersion = policy.versions[0];
    await runPanel.getByLabel('Version phí').selectOption(policyVersion.id);
    const runResponse = page.waitForResponse(response => response.url().endsWith('/api/v1/billing/runs') && response.request().method() === 'POST');
    await runPanel.getByRole('button', { name: 'Chạy & phát hành', exact: true }).click();
    const run = await runResponse.then(async response => { assert.equal(response.status(), 201); return response.json(); });
    const invoiceRow = page.getByLabel('Hóa đơn đã phát hành').locator('tbody tr').first();
    await invoiceRow.waitFor({ timeout: 20000 });
    const invoice = await waitFor(() => billingSnapshots.invoices.find(item => item.billing_run_id === run.id), 20000);
    assert.ok(invoice && invoice.total_vnd > 0, 'Billing Run should issue a positive invoice.');
    await page.getByText(invoice.invoice_number, { exact: true }).waitFor();
    check('GF07 Billing Run posts and creates a real invoice');

    const paymentPanel = page.getByLabel('Nhận payment thủ công');
    await paymentPanel.locator('select').first().selectOption(account.id);
    await paymentPanel.getByLabel('Kỳ kế toán').selectOption(period.id);
    const paymentReference = `GF07-PAY-${Date.now()}`;
    const paymentReceipt = `GF07-RCPT-${Date.now()}`;
    const outstandingBeforePayment = await waitFor(() => {
      const total = billingSnapshots.invoices
        .filter(item => ['ISSUED', 'PARTIALLY_PAID'].includes(item.status))
        .reduce((sum, item) => sum + item.outstanding_vnd, 0);
      return total > 0 ? total : null;
    });
    await paymentPanel.getByLabel('Source/reference').fill(paymentReference);
    await paymentPanel.getByLabel('Số biên lai').fill(paymentReceipt);
    await paymentPanel.getByLabel('Số tiền (VND)').fill(String(outstandingBeforePayment + 10000));
    await paymentPanel.getByLabel('Thời gian nhận').fill('2026-09-01T10:00');
    const paymentResponse = page.waitForResponse(response => response.url().endsWith('/api/v1/billing/payments') && response.request().method() === 'POST');
    await paymentPanel.getByRole('button', { name: 'Ghi nhận payment', exact: true }).click();
    const payment = await paymentResponse.then(async response => { assert.equal(response.status(), 201); return response.json(); });
    const paymentRow = page.getByLabel('Payment đã nhận').locator('tbody tr').filter({ hasText: paymentReceipt });
    await paymentRow.waitFor();
    check('GF07 payment receipt is recorded against the scoped Billing Account');
    const allocateResponse = page.waitForResponse(response => response.url().includes(`/api/v1/billing/payments/${payment.id}/allocate`) && response.request().method() === 'POST');
    await paymentRow.getByRole('button', { name: 'Phân bổ', exact: true }).click();
    const allocation = await allocateResponse.then(async response => { assert.equal(response.status(), 200); return response.json(); });
    assert.ok(allocation.overpayment_credit, 'Overpayment allocation should return a credit record.');
    const creditPanel = page.getByLabel('Overpayment Credit');
    await creditPanel.locator('tbody tr').first().waitFor();
    check('GF07 payment allocation creates an explicit Overpayment Credit');

    await paymentPanel.getByLabel('Thiếu mã Billing Account').check();
    await paymentPanel.locator('select').first().selectOption(buildingId);
    await paymentPanel.getByLabel('Kỳ kế toán').selectOption(period.id);
    const unmatchedReference = `GF07-UNMATCHED-${Date.now()}`;
    const unmatchedReceipt = `GF07-UNMATCHED-RCPT-${Date.now()}`;
    await paymentPanel.getByLabel('Source/reference').fill(unmatchedReference);
    await paymentPanel.getByLabel('Số biên lai').fill(unmatchedReceipt);
    await paymentPanel.getByLabel('Số tiền (VND)').fill('5000');
    await paymentPanel.getByLabel('Thời gian nhận').fill('2026-09-02T10:00');
    const unmatchedResponse = page.waitForResponse(response => response.url().endsWith('/api/v1/billing/payments') && response.request().method() === 'POST');
    await paymentPanel.getByRole('button', { name: 'Đưa vào unmatched', exact: true }).click();
    const unmatchedPayment = await unmatchedResponse.then(async response => { assert.equal(response.status(), 201); return response.json(); });
    const unmatchedPanel = page.getByLabel('Hàng đợi unmatched');
    const unmatchedRow = unmatchedPanel.locator('tbody tr').filter({ hasText: unmatchedReceipt });
    await unmatchedRow.waitFor();
    check('GF07 missing Billing Account payment enters the unmatched queue');
    await unmatchedRow.getByLabel(`Match ${unmatchedReceipt}`).selectOption(account.id);
    const matchResponse = page.waitForResponse(response => response.url().includes(`/api/v1/billing/unmatched-payments/`) && response.url().endsWith('/match') && response.request().method() === 'POST');
    await unmatchedRow.getByRole('button', { name: 'Match', exact: true }).click();
    const matchedPayment = await matchResponse.then(async response => { assert.equal(response.status(), 200); return response.json(); });
    const matchedRow = page.getByLabel('Payment đã nhận').locator('tbody tr').filter({ hasText: unmatchedReceipt });
    await matchedRow.waitFor();
    check('GF07 unmatched payment is matched to the correct Billing Account');
    const matchedAllocateResponse = page.waitForResponse(response => response.url().includes(`/api/v1/billing/payments/${matchedPayment.id}/allocate`) && response.request().method() === 'POST');
    await matchedRow.getByRole('button', { name: 'Phân bổ', exact: true }).click();
    const matchedAllocation = await matchedAllocateResponse.then(async response => { assert.equal(response.status(), 200); return response.json(); });
    assert.ok(matchedAllocation.overpayment_credit, 'Matched payment allocation should return a credit record.');
    await creditPanel.locator('tbody tr').last().waitFor();
    check('GF07 matched payment can be allocated and leaves a controlled credit');
    await page.screenshot({ path: path.join(evidenceDir, 'gf07-accountant-billing-payment-credit.png'), fullPage: true });

    const residentContext = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 1440, height: 960 }, locale: 'vi-VN' });
    const residentPage = await residentContext.newPage();
    const residentAsOf = [];
    residentPage.on('pageerror', error => errors.push(`resident:${error.message}`));
    residentPage.on('request', request => {
      const url = new URL(request.url());
      if (url.pathname.startsWith('/api/v1/resident/billing/')) residentAsOf.push(url.searchParams.get('as_of'));
    });
    await residentPage.goto(baseUrl, { waitUntil: 'networkidle' });
    await residentPage.locator('#staff-username').fill('resident_west');
    await residentPage.locator('#staff-password').fill(credentials.resident_west);
    await residentPage.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
    await residentPage.getByRole('tab', { name: 'Công nợ & hóa đơn', exact: true }).click();
    await residentPage.getByRole('heading', { name: 'Công nợ & hóa đơn', exact: true }).waitFor({ timeout: 15000 });
    await residentPage.getByText(invoice.invoice_number, { exact: true }).waitFor({ timeout: 15000 });
    check('GF07 resident portal shows the newly issued invoice');
    check('GF07 resident billing summary, invoices and payments share one as_of', residentAsOf.length >= 3 && new Set(residentAsOf).size === 1 && residentAsOf.every(Boolean));
    await residentPage.screenshot({ path: path.join(evidenceDir, 'gf07-resident-billing.png'), fullPage: true });
    await residentContext.close();

    const billingCommands = requests.filter(item => item.label === 'accountant' && item.path.includes('/billing/') && item.method !== 'GET');
    check('GF07 billing commands carry authorization and idempotency keys', billingCommands.length >= 7 && billingCommands.every(item => item.authorization?.startsWith('Bearer ') && item.idempotencyKey));
    check('GF07 billing command payloads keep tenant/site/role server-owned', billingCommands.every(item => !/(tenant_id|site_id|role)/.test(JSON.stringify(item.body || {}))));
    check('GF07 browser has no page errors', errors.length === 0);
    check('GF07 billing APIs have no unexpected failed responses', apiFailures.length === 0);
    fs.writeFileSync(path.join(evidenceDir, 'gf07-real-browser.json'), JSON.stringify({ flow: 'GF-07', checks, errors, apiFailures, residentAsOf, invoice: { invoice_number: invoice.invoice_number, total_vnd: invoice.total_vnd }, period: periodInput.key }, null, 2));
    console.log(`REAL_BROWSER_GF07 PASS (${checks.length} checks)`);
  } finally {
    await context.close().catch(() => {});
    await browser.close();
  }
})().catch(error => { console.error(`REAL_BROWSER_GF07_FAILED: ${error.message}`); process.exitCode = 1; });
