const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { randomUUID } = require('node:crypto');
const { chromium } = require('playwright');

const output = path.resolve(__dirname, '../artifacts/billing-ux');
fs.mkdirSync(output, { recursive: true });
const token = randomUUID();
const checkerToken = randomUUID();
const correlationId = randomUUID();
const siteId = randomUUID();
const buildingId = randomUUID();
const billingAccountId = randomUUID();
const user = {
  account_id: randomUUID(), tenant_id: randomUUID(), username: 'accountant.browser', full_name: 'Kế toán',
  roles: ['accountant'], active_site_id: siteId, allowed_sites: [{ id: siteId, code: 'CENTRAL', name: 'GreenCity Central' }],
};
const checker = { ...user, account_id: randomUUID(), username: 'checker.browser', full_name: 'Người duyệt', roles: ['admin'] };
const billingAccount = {
  id: billingAccountId, tenant_id: user.tenant_id, site_id: siteId, building_id: buildingId, unit_id: randomUUID(),
  account_number: 'BA-0101', status: 'ACTIVE', opened_on: '2026-01-01', version: 1,
};
const policyView = (body, published_at = null) => {
  const id = randomUUID();
  return { id, building_id: body.building_id, code: body.code, name: body.name, is_active: true,
    versions: [{ id: randomUUID(), fee_policy_id: id, version_number: 1, effective_from: body.effective_from,
      effective_to: null, unit_rate_vnd: body.unit_rate_vnd, basis: 'UNIT_AREA_M2',
      rounding_unit_vnd: body.rounding_unit_vnd, published_at }] };
};
// Previously approved policy is input data. New policies stay unpublished drafts.
const publishedPolicy = policyView({ building_id: buildingId, code: 'PHI-QL', name: 'Phí quản lý',
  effective_from: '2026-10-01', unit_rate_vnd: 12000, rounding_unit_vnd: 1 }, '2026-10-01T00:00:00Z');
const fixedPolicy = policyView({ building_id: buildingId, code: 'PHI-CO-DINH', name: 'Phí cố định',
  effective_from: '2026-10-01', unit_rate_vnd: 100000, rounding_unit_vnd: 1 }, '2026-10-01T00:00:00Z');
fixedPolicy.versions[0].basis = 'FIXED_UNIT';
const otherPolicy = policyView({ building_id: randomUUID(), code: 'PHI-TOA-KHAC', name: 'Phí tòa khác',
  effective_from: '2026-10-01', unit_rate_vnd: 12000, rounding_unit_vnd: 1 }, '2026-10-01T00:00:00Z');
let policies = [publishedPolicy, fixedPolicy, otherPolicy];
let periods = [];
let runs = [];
let reviews = [];
let invoices = [];

function invoiceFor(run) {
  return { id: randomUUID(), billing_account_id: billingAccountId, billing_run_id: run.id,
    accounting_period_id: run.accounting_period_id, building_id: buildingId,
    invoice_number: 'INV-2026-10-BA0101', issued_on: '2026-10-31', due_on: '2026-10-31',
    status: 'ISSUED', total_vnd: 963000, outstanding_vnd: 963000, voided_at: null, void_reason: null, version: 1,
    items: [{ id: randomUUID(), line_number: 1, description: 'Phí quản lý tháng 10', basis: 'UNIT_AREA_M2',
      basis_quantity: 80.25, unit_rate_vnd_snapshot: 12000, rounding_unit_vnd_snapshot: 1, amount_vnd: 963000, source_pending_charge_id: null }] };
}

(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const requests = []; const errors = []; const checks = [];
  const check = (name, value) => { assert.ok(value, name); checks.push(name); console.log(`PASS ${name}`); };
  const fixture = async route => {
    const request = route.request(); const url = new URL(request.url());
    const headers = { 'Content-Type': 'application/json', 'X-Correlation-ID': correlationId };
    const body = request.postData() ? request.postDataJSON() : null;
    const authorization = request.headers().authorization;
    const actor = authorization === `Bearer ${checkerToken}` ? checker : user;
    const respond = (payload, status = 200) => route.fulfill({ status, headers, body: JSON.stringify(payload) });
    const reject = (message, status = 403) => respond({ error: { code: 'ERR-FORBIDDEN', message, correlation_id: correlationId } }, status);
    requests.push({ path: url.pathname, method: request.method(), body, authorization, idempotencyKey: request.headers()['idempotency-key'] });
    if (url.pathname.endsWith('/auth/login')) return respond({ access_token: body.username === checker.username ? checkerToken : token });
    if (url.pathname.endsWith('/auth/me')) return respond(actor);
    if (url.pathname.endsWith('/service-requests')) return respond({ items: [], page: 1, page_size: 20, total: 0 });
    if (url.pathname.endsWith('/portal/finance/options')) return respond({ accounts: [billingAccount], periods, invoices, payments: [], credits: [], deposits: [], staff_accounts: [user, checker] });
    if (url.pathname.endsWith('/portal/finance/reviews')) return respond({ items: reviews });
    if (url.pathname.endsWith('/portal/finance/commands')) return respond({ items: [] });
    const decision = url.pathname.match(/\/portal\/finance\/reviews\/([^/]+)\/actions$/);
    if (decision && request.method() === 'POST') {
      const review = reviews.find(row => row.id === decision[1]);
      if (!review) return reject('Không tìm thấy bản tính', 404);
      if (body.expected_version !== review.version) return reject('Phiên bản đã thay đổi', 409);
      if (body.action === 'SUBMIT' && review.status === 'DRAFT' && actor.account_id === review.account_id) review.status = 'SUBMITTED';
      else if (body.action === 'APPROVE' && review.status === 'SUBMITTED' && actor.account_id !== review.account_id && actor.roles.includes('admin')) {
        review.status = 'APPROVED'; review.approved_by_id = actor.account_id;
      } else if (body.action === 'ISSUE' && review.status === 'APPROVED') {
        const run = runs.find(row => row.id === review.billing_run_id);
        const invoice = invoiceFor(run); invoices.push(invoice);
        review.status = 'ISSUED'; review.issued_invoice_ids = [invoice.id];
        run.status = 'POSTED'; run.version += 1; run.completed_at = '2026-10-31T00:00:00Z';
      } else return reject('Cần đúng trạng thái và người duyệt độc lập');
      review.version += 1; return respond(review);
    }
    if (url.pathname.endsWith('/billing/accounts')) return respond({ items: [billingAccount] });
    if (url.pathname.endsWith('/billing/fee-policies')) {
      if (request.method() === 'GET') return respond({ items: policies });
      const policy = policyView(body); policies.push(policy); return respond(policy, 201);
    }
    if (url.pathname.endsWith('/billing/periods')) {
      if (request.method() === 'GET') return respond({ items: periods });
      const period = { id: randomUUID(), building_id: body.building_id, period_key: body.period_key,
        period_start: body.period_start, period_end: body.period_end, cutoff_at: body.cutoff_at, status: 'OPEN', version: 1 };
      periods.push(period); return respond(period, 201);
    }
    if (url.pathname.endsWith('/billing/runs')) {
      if (request.method() === 'GET') return respond({ items: runs });
      const run = { id: randomUUID(), accounting_period_id: body.accounting_period_id, fee_policy_version_id: body.fee_policy_version_id,
        building_id: buildingId, run_key: body.run_key, status: 'REVIEW', cutoff_at: periods[0].cutoff_at,
        retry_count: 0, failure_code: null, failure_detail: null, failed_at: null, completed_at: null, version: 1 };
      runs.push(run);
      reviews.push({ id: randomUUID(), account_id: actor.account_id, billing_run_id: run.id,
        period_id: run.accounting_period_id, status: 'DRAFT', version: 1, approved_by_id: null, issued_invoice_ids: [],
        snapshot: { invoices: [{ billing_account_id: billingAccountId, unit_id: billingAccount.unit_id, total_vnd: 963000,
          responsibility: { basis: 'owner' }, items: [{ description: 'Phí quản lý tháng 10', amount_vnd: 963000 }] }] } });
      return respond(run, 201);
    }
    if (url.pathname.endsWith('/billing/invoices')) return respond({ items: invoices });
    if (['/billing/payments', '/billing/unmatched-payments', '/billing/overpayment-credits'].some(suffix => url.pathname.endsWith(suffix))) return respond({ items: [] });
    return respond({ error: { code: 'ERR-NOTFOUND', message: 'Không tìm thấy fixture.', correlation_id: correlationId } }, 404);
  };
  const openAs = async actor => {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'vi-VN' });
    await context.route('**/api/v1/**', fixture);
    const page = await context.newPage(); page.on('pageerror', error => errors.push(error.message));
    await page.goto(process.env.UX_BASE_URL || 'http://127.0.0.1:3000/');
    await page.getByLabel('Tên đăng nhập').fill(actor.username);
    await page.getByLabel('Mật khẩu').fill('browser-only-password');
    await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
    await page.getByRole('navigation', { name: 'Điều hướng chính' }).getByRole('button', { name: 'Tài chính & Công nợ', exact: true }).click();
    await page.getByRole('heading', { name: 'Thiết lập phí và phát hành hóa đơn', exact: true }).waitFor();
    return page;
  };
  const card = page => page.locator('#finance-control-panel article.portal-record').filter({ hasText: periods[0].id }).first();
  const decide = async (page, action, afterLabel) => {
    const review = card(page);
    await review.getByLabel('Thao tác', { exact: true }).selectOption(action);
    await review.getByLabel('Lý do quyết định').fill('Đã kiểm tra căn cứ tính phí');
    await review.getByRole('button', { name: 'Xác nhận', exact: true }).click();
    await review.getByText(afterLabel, { exact: true }).waitFor();
  };
  try {
    const page = await openAs(user);
    const policyForm = page.getByRole('heading', { name: 'Chính sách phí cơ bản', exact: true }).locator('..');
    await policyForm.getByLabel('Tòa nhà').selectOption(buildingId);
    await policyForm.getByLabel('Mã policy').fill('PHI-QL-NEXT');
    await policyForm.getByLabel('Tên policy').fill('Biểu phí kỳ tiếp theo');
    await policyForm.getByLabel('Hiệu lực từ').fill('2026-11-01');
    await policyForm.getByLabel('Đơn giá (VND/m²)').fill('12000');
    await policyForm.getByLabel('Làm tròn (VND)').fill('1');
    await policyForm.getByRole('button', { name: 'Lưu biểu phí nháp', exact: true }).click();
    await page.getByText('Đã lưu bản nháp PHI-QL-NEXT.', { exact: false }).waitFor();
    check('new fee policy stays an unpublished draft', policies.length === 4 && policies.at(-1).versions[0].published_at === null);

    const periodForm = page.getByRole('heading', { name: 'Mở kỳ kế toán', exact: true }).locator('..');
    await periodForm.getByLabel('Tòa nhà').selectOption(buildingId);
    await periodForm.getByLabel('Mã kỳ').fill('2026-10');
    await periodForm.getByLabel('Bắt đầu').fill('2026-10-01');
    await periodForm.getByLabel('Kết thúc').fill('2026-10-31');
    await periodForm.getByLabel('Cutoff').fill('2026-10-15T00:00');
    await periodForm.getByRole('button', { name: 'Mở kỳ', exact: true }).click();
    const runPanel = page.getByRole('region', { name: 'Tính nháp định kỳ', exact: true });
    await runPanel.getByRole('option', { name: /2026-10.*OPEN/ }).waitFor({ state: 'attached' });
    await runPanel.getByLabel('Kỳ', { exact: true }).selectOption(periods[0].id);
    check('unpublished policy is excluded from billing run choices', await runPanel.getByRole('option', { name: /PHI-QL-NEXT/ }).count() === 0);
    check('policy from another building is excluded', await runPanel.getByRole('option', { name: /PHI-TOA-KHAC/ }).count() === 0);
    check('fixed-unit fee displays VND per unit', await runPanel.getByRole('option', { name: /PHI-CO-DINH.*\/căn/ }).count() === 1);
    await runPanel.getByLabel('Version phí').selectOption(publishedPolicy.versions[0].id);
    await runPanel.screenshot({ path: path.join(output, 'billing-run-form.png') });
    await runPanel.getByRole('button', { name: 'Tính nháp', exact: true }).click();
    await card(page).getByText('Bản nháp', { exact: true }).waitFor();
    check('draft run refreshes reviews and creates no invoices', runs[0].status === 'REVIEW' && invoices.length === 0 && reviews[0].status === 'DRAFT');
    await decide(page, 'SUBMIT', 'Đã gửi');
    check('submitted review still creates no debt', invoices.length === 0 && reviews[0].status === 'SUBMITTED');
    await card(page).getByLabel('Thao tác', { exact: true }).selectOption('APPROVE');
    await card(page).getByLabel('Lý do quyết định').fill('Kiểm tra duyệt độc lập');
    await card(page).getByRole('button', { name: 'Xác nhận', exact: true }).click();
    await card(page).getByRole('alert').waitFor();
    check('maker cannot approve their own review and no debt is created', reviews[0].status === 'SUBMITTED' && invoices.length === 0);

    const checkerPage = await openAs(checker);
    await decide(checkerPage, 'APPROVE', 'Đã duyệt');
    check('approval comes from an independent account', reviews[0].approved_by_id === checker.account_id && checker.account_id !== reviews[0].account_id);
    await page.locator('#finance-control-panel').getByRole('button', { name: 'Làm mới', exact: true }).click();
    await card(page).getByText('Đã duyệt', { exact: true }).waitFor();
    await decide(page, 'ISSUE', 'Đã phát hành');
    await page.getByText('INV-2026-10-BA0101', { exact: true }).waitFor();
    check('invoice is issued after approval and refreshes the invoice list', invoices.length === 1 && runs[0].status === 'POSTED' && await page.getByText('963.000 ₫', { exact: true }).first().isVisible());
    await page.getByLabel('Hóa đơn đã phát hành').scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(output, 'billing-golden-flow.png'), fullPage: false });
    await card(page).screenshot({ path: path.join(output, 'billing-issued-review.png') });

    const financialRequests = requests.filter(item => item.path.includes('/billing/') || item.path.includes('/portal/finance/'));
    const commands = financialRequests.filter(item => item.method === 'POST');
    check('billing commands include a rejected self-approval before independent approval and issue', commands.length === 7 && commands.slice(3).map(item => item.body.action).join(',') === 'SUBMIT,APPROVE,APPROVE,ISSUE');
    check('financial reads and commands use authenticated sessions', financialRequests.every(item => [token, checkerToken].some(value => item.authorization === `Bearer ${value}`)));
    check('all commands carry idempotency keys and no forged scope', commands.every(item => item.idempotencyKey && !/"(?:tenant_id|site_id|role)"/.test(JSON.stringify(item.body))));
    check('no unhandled browser errors', errors.length === 0);
    fs.writeFileSync(path.join(output, 'test-results.json'), JSON.stringify({ passed: checks.length, checks, errors }, null, 2));
    console.log(`BILLING UX: ${checks.length} checks passed.`);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
