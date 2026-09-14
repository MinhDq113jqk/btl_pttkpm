const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { randomUUID } = require('node:crypto');
const { chromium } = require('playwright');

const output = path.resolve(__dirname, '../artifacts/payment-ux');
fs.mkdirSync(output, { recursive: true });
const token = randomUUID();
const correlationId = randomUUID();
const siteId = randomUUID();
const buildingId = randomUUID();
const accountId = randomUUID();
const periodId = randomUUID();
const invoiceId = randomUUID();
const user = { account_id: randomUUID(), tenant_id: randomUUID(), username: 'accountant.payment', full_name: 'Kế toán payment', roles: ['accountant'], active_site_id: siteId, allowed_sites: [{ id: siteId, code: 'CENTRAL', name: 'GreenCity Central' }] };
const billingAccount = { id: accountId, tenant_id: user.tenant_id, site_id: siteId, building_id: buildingId, unit_id: randomUUID(), account_number: 'BA-PAY-01', status: 'ACTIVE', opened_on: '2026-01-01', version: 1 };
const period = { id: periodId, building_id: buildingId, period_key: '2030-01', period_start: '2030-01-01', period_end: '2030-01-31', cutoff_at: '2030-01-15T00:00:00Z', status: 'OPEN', version: 1 };
let invoices = [{ id: invoiceId, billing_account_id: accountId, billing_run_id: randomUUID(), accounting_period_id: periodId, building_id: buildingId, invoice_number: 'INV-PAY-01', issued_on: '2030-01-01', due_on: '2030-01-31', status: 'ISSUED', total_vnd: 50_000, outstanding_vnd: 50_000, voided_at: null, void_reason: null, version: 1, items: [] }];
  let payments = [];
  let unmatched = [];
  let credits = [];
  const paymentByIdempotencyKey = new Map();
  let loseFirstPaymentResponse = true;
const paymentView = (body, { unmatchedPayment = false } = {}) => ({ id: randomUUID(), billing_account_id: unmatchedPayment ? null : body.billing_account_id, accounting_period_id: body.accounting_period_id, building_id: unmatchedPayment ? body.building_id : buildingId, payment_source: body.payment_source, source_reference: body.source_reference, receipt_number: body.receipt_number, amount_vnd: body.amount_vnd, received_at: body.received_at, status: unmatchedPayment ? 'UNMATCHED' : 'RECEIVED', created_at: '2030-01-10T09:30:00Z', version: 1 });

(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 }, locale: 'vi-VN' });
  const page = await context.newPage();
  const requests = [];
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await context.route('**/api/v1/**', async route => {
    const request = route.request();
    const url = new URL(request.url());
    const headers = { 'Content-Type': 'application/json', 'X-Correlation-ID': correlationId };
    const body = request.postData() ? request.postDataJSON() : null;
    const requestIdempotencyKey = request.headers()['idempotency-key'];
    requests.push({ path: url.pathname, method: request.method(), body, authorization: request.headers().authorization, idempotencyKey: requestIdempotencyKey });
    const respond = (payload, status = 200) => route.fulfill({ status, headers, body: JSON.stringify(payload) });
    if (url.pathname.endsWith('/auth/login')) return respond({ access_token: token });
    if (url.pathname.endsWith('/auth/me')) return respond(user);
    if (url.pathname.endsWith('/service-requests') && request.method() === 'GET') return respond({ items: [], page: 1, page_size: 20, total: 0 });
    if (url.pathname.endsWith('/billing/accounts') && request.method() === 'GET') return respond({ items: [billingAccount] });
    if (url.pathname.endsWith('/billing/fee-policies') && request.method() === 'GET') return respond({ items: [] });
    if (url.pathname.endsWith('/billing/periods') && request.method() === 'GET') return respond({ items: [period] });
    if (url.pathname.endsWith('/billing/runs') && request.method() === 'GET') return respond({ items: [] });
    if (url.pathname.endsWith('/billing/invoices') && request.method() === 'GET') return respond({ items: invoices });
    if (url.pathname.endsWith('/billing/payments') && request.method() === 'GET') return respond({ items: payments });
    if (url.pathname.endsWith('/billing/unmatched-payments') && request.method() === 'GET') return respond({ items: unmatched });
    if (url.pathname.endsWith('/billing/overpayment-credits') && request.method() === 'GET') return respond({ items: credits });
    if (url.pathname.endsWith('/billing/payments') && request.method() === 'POST') {
      const replay = paymentByIdempotencyKey.get(requestIdempotencyKey);
      if (replay) return respond(replay, 201);
      const entry = paymentView(body, { unmatchedPayment: Boolean(body.building_id) });
      payments = [...payments, entry];
      if (entry.status === 'UNMATCHED') unmatched = [...unmatched, { id: randomUUID(), payment_id: entry.id, building_id: buildingId, amount_vnd: entry.amount_vnd, reason: 'Thiếu mã Billing Account khi nhận thanh toán.', status: 'OPEN', source_reference: entry.source_reference, receipt_number: entry.receipt_number, received_at: entry.received_at, created_at: entry.created_at, version: 1 }];
      paymentByIdempotencyKey.set(requestIdempotencyKey, entry);
      if (body.source_reference === 'bank-offline-browser-001' && loseFirstPaymentResponse) {
        loseFirstPaymentResponse = false;
        return route.abort('connectionreset');
      }
      return respond(entry, 201);
    }
    const matchPath = url.pathname.match(/\/billing\/unmatched-payments\/([^/]+)\/match$/);
    if (matchPath && request.method() === 'POST') {
      const item = unmatched.find(entry => entry.id === matchPath[1]);
      unmatched = unmatched.map(entry => entry.id === item.id ? { ...entry, status: 'RESOLVED', version: 2 } : entry);
      const payment = payments.find(entry => entry.id === item.payment_id);
      const matched = { ...payment, billing_account_id: body.billing_account_id, status: 'RECEIVED', version: 2 };
      payments = payments.map(entry => entry.id === matched.id ? matched : entry);
      return respond(matched);
    }
    const allocationPath = url.pathname.match(/\/billing\/payments\/([^/]+)\/allocate$/);
    if (allocationPath && request.method() === 'POST') {
      const payment = payments.find(entry => entry.id === allocationPath[1]);
      const invoice = invoices.find(entry => entry.billing_account_id === payment.billing_account_id && entry.outstanding_vnd > 0);
      const allocated = Math.min(payment.amount_vnd, invoice?.outstanding_vnd || 0);
      if (invoice) invoices = invoices.map(entry => entry.id === invoice.id ? { ...entry, outstanding_vnd: entry.outstanding_vnd - allocated, status: entry.outstanding_vnd === allocated ? 'PAID' : 'PARTIALLY_PAID', version: entry.version + 1 } : entry);
      const excess = payment.amount_vnd - allocated;
      const credit = excess ? { id: randomUUID(), billing_account_id: payment.billing_account_id, payment_id: payment.id, original_vnd: excess, remaining_vnd: excess, status: 'OPEN', created_at: payment.received_at, version: 1 } : null;
      if (credit) credits = [...credits, credit];
      const allocatedPayment = { ...payment, status: credit ? 'OVERPAID' : 'ALLOCATED', version: payment.version + 1 };
      payments = payments.map(entry => entry.id === payment.id ? allocatedPayment : entry);
      return respond({ payment: allocatedPayment, allocations: allocated ? [{ id: randomUUID(), payment_id: payment.id, billing_invoice_id: invoice.id, amount_vnd: allocated, created_at: payment.received_at }] : [], overpayment_credit: credit });
    }
    return respond({ error: { code: 'ERR-NOTFOUND', message: 'Không tìm thấy.', correlation_id: correlationId } }, 404);
  });
  try {
    await page.goto(process.env.UX_BASE_URL || 'http://127.0.0.1:3000/');
    await page.getByLabel('Tên đăng nhập').fill(user.username);
    await page.getByLabel('Mật khẩu').fill('browser-only-password');
    await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
    await page.getByRole('navigation', { name: 'Điều hướng chính' }).getByRole('button', { name: 'Tài chính & Công nợ', exact: true }).click();
    const paymentPanel = page.getByLabel('Nhận payment thủ công');
    await paymentPanel.getByRole('combobox').first().selectOption(accountId);
    await paymentPanel.getByLabel('Kỳ kế toán').selectOption(periodId);
    await paymentPanel.getByLabel('Source/reference').fill('bank-payment-browser-001');
    await paymentPanel.getByLabel('Số biên lai').fill('RCPT-PAY-001');
    await paymentPanel.getByLabel('Số tiền (VND)').fill('20000');
    await paymentPanel.getByLabel('Thời gian nhận').fill('2030-01-10T09:30');
    await paymentPanel.getByRole('button', { name: 'Ghi nhận payment', exact: true }).click();
    await page.getByText('RCPT-PAY-001', { exact: true }).waitFor();
    await page.getByLabel('Payment đã nhận').getByRole('button', { name: 'Phân bổ', exact: true }).click();
    await page.getByText('30.000 ₫', { exact: true }).waitFor();

    await paymentPanel.getByLabel('Source/reference').fill('bank-offline-browser-001');
    await paymentPanel.getByLabel('Số biên lai').fill('RCPT-OFFLINE-001');
    await paymentPanel.getByLabel('Số tiền (VND)').fill('10000');
    await paymentPanel.getByLabel('Thời gian nhận').fill('2030-01-10T10:30');
    await paymentPanel.getByRole('button', { name: 'Ghi nhận payment', exact: true }).click();
    await page.getByRole('alert').waitFor();
    assert.equal(await page.getByText('RCPT-OFFLINE-001', { exact: true }).count(), 0);
    await paymentPanel.getByRole('button', { name: 'Ghi nhận payment', exact: true }).click();
    await page.getByText('RCPT-OFFLINE-001', { exact: true }).waitFor();

    await paymentPanel.getByLabel('Thiếu mã Billing Account').check();
    await paymentPanel.getByLabel('Tòa nhà').selectOption(buildingId);
    await paymentPanel.getByLabel('Kỳ kế toán').selectOption(periodId);
    await paymentPanel.getByLabel('Source/reference').fill('bank-missing-browser-001');
    await paymentPanel.getByLabel('Số biên lai').fill('RCPT-MISSING-001');
    await paymentPanel.getByLabel('Số tiền (VND)').fill('10000');
    await paymentPanel.getByLabel('Thời gian nhận').fill('2030-01-11T09:30');
    await paymentPanel.getByRole('button', { name: 'Đưa vào unmatched', exact: true }).click();
    const unmatchedPanel = page.getByLabel('Hàng đợi unmatched');
    await unmatchedPanel.getByText('RCPT-MISSING-001', { exact: true }).waitFor();
    await unmatchedPanel.getByLabel('Match RCPT-MISSING-001').selectOption(accountId);
    await unmatchedPanel.getByRole('button', { name: 'Match', exact: true }).click();
    await page.getByLabel('Payment đã nhận').getByRole('button', { name: 'Phân bổ', exact: true }).last().click();
    await page.screenshot({ path: path.join(output, 'payment-golden-flow.png'), fullPage: true });

    const commands = requests.filter(item => item.path.includes('/billing/') && item.method !== 'GET');
    assert.deepEqual(commands.map(item => item.method), ['POST', 'POST', 'POST', 'POST', 'POST', 'POST', 'POST']);
    assert.ok(commands.every(item => item.authorization === `Bearer ${token}`));
    assert.ok(commands.every(item => typeof item.idempotencyKey === 'string' && item.idempotencyKey.length > 0));
    assert.ok(commands.every(item => !/"(?:tenant_id|site_id|role)"/.test(JSON.stringify(item.body))));
    const offlineAttempts = commands.filter(item => item.body?.source_reference === 'bank-offline-browser-001');
    assert.equal(offlineAttempts.length, 2);
    assert.equal(offlineAttempts[0].idempotencyKey, offlineAttempts[1].idempotencyKey);
    assert.equal(payments.filter(item => item.source_reference === 'bank-offline-browser-001').length, 1);
    assert.equal(payments.filter(item => item.source_reference === 'bank-missing-browser-001')[0].status, 'ALLOCATED');
    assert.equal(unmatched[0].status, 'RESOLVED');
    assert.equal(errors.length, 0);
    fs.writeFileSync(path.join(output, 'test-results.json'), JSON.stringify({ passed: 14, errors }, null, 2));
    console.log('PAYMENT UX: 14 checks passed.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
