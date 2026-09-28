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
const requests = { dashboard: [], drillDown: [], audit: [], notifications: [], outbox: [] };
const responses = { dashboard: [], drillDown: [], audit: [], notifications: [], outbox: [] };

const check = (name, value = true) => { assert.ok(value, name); checks.push(name); console.log(`PASS ${name}`); };
const waitFor = async (predicate, timeout = 15000) => {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const value = predicate();
    if (value) return value;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error('Timed out waiting for the dashboard backend response.');
};
const canonical = value => new Date(value).toISOString();
const escapeRegExp = value => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

function observe(page) {
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => {
    const url = new URL(request.url());
    if (!url.pathname.startsWith('/api/v1/')) return;
    const item = { path: url.pathname, method: request.method(), query: Object.fromEntries(url.searchParams.entries()), authorization: request.headers().authorization };
    if (url.pathname.endsWith('/dashboard')) requests.dashboard.push(item);
    else if (url.pathname.includes('/dashboard/drill-down/')) requests.drillDown.push(item);
    else if (url.pathname.endsWith('/audit-events')) requests.audit.push(item);
    else if (url.pathname.endsWith('/notifications')) requests.notifications.push(item);
    else if (url.pathname.endsWith('/outbox/events')) requests.outbox.push(item);
  });
  page.on('response', response => {
    const url = new URL(response.url());
    if (!url.pathname.startsWith('/api/v1/')) return;
    if (response.status() >= 400 && (url.pathname.endsWith('/dashboard') || url.pathname.includes('/dashboard/drill-down/') || url.pathname.endsWith('/audit-events') || url.pathname.endsWith('/notifications') || url.pathname.endsWith('/outbox/events'))) {
      apiFailures.push(`${response.status()}:${url.pathname}`);
    }
    let bucket = null;
    if (url.pathname.endsWith('/dashboard')) bucket = responses.dashboard;
    else if (url.pathname.includes('/dashboard/drill-down/')) bucket = responses.drillDown;
    else if (url.pathname.endsWith('/audit-events')) bucket = responses.audit;
    else if (url.pathname.endsWith('/notifications')) bucket = responses.notifications;
    else if (url.pathname.endsWith('/outbox/events')) bucket = responses.outbox;
    if (!bucket || response.request().method() !== 'GET') return;
    const record = { status: response.status(), path: url.pathname, query: Object.fromEntries(url.searchParams.entries()), payload: null };
    bucket.push(record);
    response.json().then(payload => { record.payload = payload; }).catch(() => { record.payload = {}; });
  });
}

async function login(page) {
  await page.goto(baseUrl, { waitUntil: 'networkidle' });
  await page.locator('#staff-username').fill('director_west');
  await page.locator('#staff-password').fill(credentials.director_west);
  await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
  await page.locator('.desktop-shell').waitFor({ timeout: 15000 });
}

(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const context = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 1440, height: 960 }, locale: 'vi-VN' });
  const page = await context.newPage();
  observe(page);
  try {
    await login(page);
    await page.locator('.executive-dashboard').waitFor({ timeout: 15000 });
    const dashboardResponse = await waitFor(() => responses.dashboard.find(item => item.payload));
    const dashboardRequest = requests.dashboard[0];
    assert.equal(dashboardResponse.status, 200);
    assert.ok(dashboardRequest?.query.as_of);
    const requestedAsOf = dashboardRequest.query.as_of;
    const responseAsOf = dashboardResponse.payload.as_of;
    check('GF08 director sees the real executive dashboard');
    check('GF08 dashboard response preserves one timezone-aware as_of', canonical(responseAsOf) === canonical(requestedAsOf));
    check('GF08 dashboard UI exposes the exact request as_of', await page.locator('.cutoff-iso-badge').getAttribute('title') === requestedAsOf);
    check('GF08 dashboard renders all five KPI groups', await page.locator('[aria-label="5 Chỉ số điều hành cốt lõi"] .kpi-card').count() === 5);
    await page.screenshot({ path: path.join(evidenceDir, 'gf08-dashboard.png'), fullPage: true });

    const metrics = [
      ['sla_overdue', 'Yêu cầu CSKH quá hạn SLA'],
      ['maintenance_due', 'Bảo trì kỹ thuật đến hạn'],
      ['cleaning_rework', 'Vệ sinh cần làm lại (Rework)'],
      ['open_incidents', 'Sự cố an ninh đang mở'],
      ['ar_debt', 'Tổng công nợ quá hạn (AR)'],
    ];
    let auditFromDrilldown = false;
    for (const [metric, title] of metrics) {
      const before = responses.drillDown.length;
      await page.getByRole('button', { name: new RegExp(escapeRegExp(title)) }).click();
      await page.locator('.drilldown-dialog').waitFor();
      const drill = await waitFor(() => {
        const candidate = responses.drillDown.slice(before).find(item => item.payload);
        return candidate;
      });
      assert.equal(drill.status, 200);
      assert.equal(drill.payload.metric, metric);
      check(`GF08 ${metric} drill-down uses the shared as_of`, canonical(drill.payload.as_of) === canonical(requestedAsOf) && drill.query.as_of === requestedAsOf);
      if (!auditFromDrilldown && drill.payload.items.length > 0) {
        const item = drill.payload.items[0];
        const auditBefore = responses.audit.length;
        await page.getByRole('button', { name: 'Xem lịch sử thay đổi của tài nguyên này' }).first().click();
        await page.locator('.audit-dialog').waitFor();
        const audit = await waitFor(() => responses.audit.slice(auditBefore).find(entry => entry.payload));
        assert.equal(audit.status, 200);
        check('GF08 audit timeline opens from a drill-down source record');
        check('GF08 drill-down audit request preserves resource scope and as_of', audit.query.resource_type === item.resource_type && audit.query.resource_id === item.resource_id && audit.query.as_of === requestedAsOf);
        check('GF08 audit timeline renders backend events without a mock fallback', await page.locator('.audit-timeline-card').count() > 0 || await page.getByText('Không tìm thấy sự kiện kiểm toán', { exact: true }).count() > 0);
        await page.getByRole('button', { name: 'Đóng cửa sổ kiểm toán', exact: true }).click();
        await page.locator('.audit-dialog').waitFor({ state: 'detached' });
        auditFromDrilldown = true;
      }
      await page.locator('.drilldown-footer').getByRole('button', { name: 'Đóng', exact: true }).click();
      await page.locator('.drilldown-dialog').waitFor({ state: 'detached' });
    }

    const globalAuditBefore = responses.audit.length;
    const globalAuditButton = page.locator('.dashboard-quick-footer').getByRole('button', { name: 'Mở Audit Explorer', exact: true });
    await globalAuditButton.scrollIntoViewIfNeeded();
    await globalAuditButton.evaluate(element => element.click());
    await page.locator('.audit-dialog').waitFor();
    const globalAuditRecord = await waitFor(() => responses.audit.slice(globalAuditBefore).find(item => item.payload));
    const globalAudit = globalAuditRecord.payload;
    check('GF08 global Audit Explorer opens from the dashboard');
    check('GF08 global audit query shares the dashboard as_of', globalAuditRecord.query.as_of === requestedAsOf && canonical(globalAudit.as_of || requestedAsOf) === canonical(requestedAsOf));
    await page.waitForFunction(() => !document.querySelector('.audit-content .request-state.request-loading')
      && (document.querySelector('.audit-timeline-stream') || document.querySelector('.audit-content .request-state.request-error')), null, { timeout: 15000 });
    const globalAuditError = await page.locator('.audit-content .request-state.request-error').count();
    check('GF08 global audit view is backed by the real API', globalAuditError === 0 && (await page.locator('.audit-timeline-card').count() > 0 || await page.getByText('Không tìm thấy sự kiện kiểm toán', { exact: true }).count() > 0));
    await page.screenshot({ path: path.join(evidenceDir, 'gf08-audit-explorer.png'), fullPage: true });
    await page.getByRole('button', { name: 'Đóng cửa sổ kiểm toán', exact: true }).click();
    await page.locator('.audit-dialog').waitFor({ state: 'detached' });

    await page.getByRole('navigation', { name: 'Điều hướng chính' }).getByRole('button', { name: 'Thông báo', exact: true }).click();
    await page.getByRole('heading', { name: 'Thông báo', exact: true }).waitFor();
    await page.getByText(/Danh sách giới hạn bản ghi tạo trước/).waitFor();
    await waitFor(() => responses.notifications.some(item => item.payload));
    check('GF08 notification inbox loads from the real backend');
    check('GF08 notification requests keep the dashboard as_of', requests.notifications.length > 0 && requests.notifications.every(item => item.query.as_of === requestedAsOf));
    check('GF08 notification outbox requests keep the dashboard as_of', requests.outbox.length === 0 || requests.outbox.every(item => item.query.as_of === requestedAsOf));
    await page.screenshot({ path: path.join(evidenceDir, 'gf08-notifications.png'), fullPage: true });

    check('GF08 dashboard and control APIs have no unexpected failed responses', apiFailures.length === 0);
    check('GF08 browser has no page errors', errors.length === 0);
    fs.writeFileSync(path.join(evidenceDir, 'gf08-real-browser.json'), JSON.stringify({ flow: 'GF-08', checks, errors, apiFailures, requestedAsOf, dashboardResponseAsOf: responseAsOf, drillDownRequests: requests.drillDown.map(item => item.path), notificationAsOf: requests.notifications.map(item => item.query.as_of), auditCount: responses.audit.length }, null, 2));
    console.log(`REAL_BROWSER_GF08 PASS (${checks.length} checks)`);
  } finally {
    await context.close().catch(() => {});
    await browser.close();
  }
})().catch(error => { console.error(`REAL_BROWSER_GF08_FAILED: ${error.message}`); process.exitCode = 1; });
