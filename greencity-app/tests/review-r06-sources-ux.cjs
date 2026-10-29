const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { randomUUID } = require('node:crypto');
const { chromium } = require('playwright');

const output = path.resolve(__dirname, '../../documents/deploy_review/evidence/R06/source-browser');
const reportsCode = fs.readFileSync(path.resolve(__dirname, '../src/components/SadReportsPanel.jsx'), 'utf8');
const sources = [...reportsCode.match(/const linkedSources = new Set\(\[([^\]]+)\]/)[1].matchAll(/'([^']+)'/g)].map(match => match[1]);
const ids = Object.fromEntries(['site', 'building', 'unit', 'user', 'report', 'source', 'related'].map(key => [key, randomUUID()]));
const rows = sources.map((source, index) => ({ source, data: { id: ids.source, code: 'SNAP-' + index, status: 'APPROVED' } }));
const report = { id: ids.report, building_id: ids.building, kind: 'FINANCIAL', as_of: '2026-10-12T02:00:00Z', definition_version: 'R06-FIXTURE', digest: 'synthetic-digest', filters: {}, metrics: {}, counts: Object.fromEntries(sources.map(source => [source, 1])), rows, row_count: rows.length };
const checks = [], requests = [], errors = [], unexpected = [];
let sourceFailure = 0;
const check = name => { checks.push(name); console.log('PASS ' + name); };

(async () => {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'vi-VN' });
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  await context.route('**/api/v1/**', async route => {
    const request = route.request(), url = new URL(request.url()), api = url.pathname.replace('/api/v1', '');
    const respond = (payload, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(payload) });
    if (api === '/auth/login') return respond({ access_token: 'synthetic-r06-session' });
    if (api === '/auth/me') return respond({ account_id: ids.user, tenant_id: ids.site, full_name: 'Người kiểm tra R06', username: 'review.r06', roles: ['director'], active_site_id: ids.site, allowed_sites: [{ id: ids.site, code: 'R06', name: 'GreenCity R06' }] });
    assert.equal(request.headers().authorization, 'Bearer synthetic-r06-session');
    if (api === '/service-requests') return respond({ items: [], page: 1, page_size: 20, total: 0 });
    if (api === '/notifications' || api === '/outbox/events') return respond({ items: [] });
    if (api === '/dashboard') return respond({ as_of: url.searchParams.get('as_of'), sla_overdue_count: 0, maintenance_due_count: 0, cleaning_rework_count: 0, open_incident_count: 0, ar_debt_vnd: 0 });
    if (api === '/portal/options') return respond({ buildings: [{ id: ids.building, code: 'R06', name: 'Tòa R06' }], units: [{ id: ids.unit, building_id: ids.building, unit_number: 'R06-101' }] });
    if (api === '/portal/capabilities') return respond({ items: [] });
    if (api === '/portal/property/persons' || api === '/portal/property/duplicates' || api === '/portal/property/nodes') return respond({ items: [] });
    if (api === '/portal/property/buildings') return respond({ items: [], units: [] });
    if (api === '/portal/finance/options') return respond({ periods: [] });
    if (api === '/portal/control/reports') return respond({ items: [report] });
    if (api === `/portal/control/reports/${ids.report}`) return respond(report);
    const match = api.match(/^\/portal\/(?:control\/reports\/([^/]+)\/)?sources\/([^/]+)\/([^/]+)$/);
    if (match) {
      const [, reportId, source, identifier] = match;
      assert.equal(request.method(), 'GET'); assert.ok(sources.includes(source));
      if (reportId) { assert.equal(reportId, ids.report); assert.equal(identifier, ids.source); }
      else { assert.equal(source, 'operations_records'); assert.equal(identifier, ids.related); }
      requests.push({ api, source, reportId: reportId || null, status: sourceFailure || 200 });
      if (sourceFailure) return respond({ error: { code: 'ERR-SOURCE-' + sourceFailure, message: 'Không mở được nguồn.', correlation_id: 'R06-SOURCE' } }, sourceFailure);
      return respond({ source, current: { id: identifier, code: 'LIVE-' + source, status: 'APPROVED' }, notice: 'Nguồn hiện tại từ API.', evidence_reference: 'R06-' + source, current_differs: true, snapshot_as_of: report.as_of, evidence_documents: [], links: reportId ? [{ source: 'operations_records', id: ids.related, label: 'Biên bản R06' }] : [] });
    }
    unexpected.push(api);
    return respond({ error: { code: 'ERR-UNEXPECTED-API', message: 'Thiếu fixture ' + api } }, 404);
  });
  try {
    await page.goto(process.env.UX_BASE_URL || 'http://127.0.0.1:3100');
    await page.locator('#staff-username').fill('review.r06');
    await page.locator('#staff-password').fill('synthetic-password-only');
    await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
    await page.getByRole('navigation', { name: 'Điều hướng chính' }).getByRole('button', { name: 'Dịch vụ cư dân', exact: true }).click();
    await page.getByLabel('Tòa nhà', { exact: true }).selectOption(ids.building);
    await page.getByRole('navigation', { name: 'Phân hệ dịch vụ cư dân' }).getByRole('button', { name: 'Báo cáo & xuất', exact: true }).click();
    await page.getByRole('button', { name: 'Xem chỉ tiêu & chi tiết', exact: true }).click();
    await page.getByRole('heading', { name: /^Snapshot / }).waitFor();
    await page.waitForLoadState('networkidle');
    assert.equal(await page.getByRole('button', { name: 'Mở hồ sơ nguồn & căn cứ', exact: true }).count(), 19);
    check('19 nguồn báo cáo có đường mở hồ sơ');
    const filter = page.getByLabel('Nguồn chi tiết', { exact: true });
    const open = () => page.getByRole('button', { name: 'Mở hồ sơ nguồn & căn cứ', exact: true });
    for (const source of sources) {
      await filter.selectOption(source); await open().click();
      await page.getByRole('heading', { name: 'LIVE-' + source, exact: true }).waitFor();
      assert.ok(requests.some(request => request.source === source && request.reportId === ids.report));
      await page.getByText('Căn cứ: R06-' + source, { exact: true }).waitFor();
      await page.getByText(/^Nguồn hiện tại đã khác snapshot/).waitFor();
      check(source + ': hồ sơ và căn cứ đúng nguồn snapshot');
    }
    await filter.selectOption('billing_invoices'); await open().click();
    await page.getByRole('heading', { name: 'LIVE-billing_invoices', exact: true }).waitFor();
    await page.screenshot({ path: path.join(output, 'invoice-source.png'), fullPage: true });
    await page.getByRole('button', { name: 'Mở Biên bản R06', exact: true }).click();
    await page.getByRole('heading', { name: 'LIVE-operations_records', exact: true }).waitFor();
    assert.ok(requests.some(request => !request.reportId && request.source === 'operations_records'));
    check('Nguồn liên quan có dấu _ mở bằng /sources');
    await page.getByRole('button', { name: 'Về nguồn ban đầu', exact: true }).click();
    await page.getByRole('heading', { name: 'LIVE-billing_invoices', exact: true }).waitFor();
    check('Quay lại hồ sơ gốc');
    for (const status of [403, 404, 409, 500]) {
      await open().click(); sourceFailure = status; await open().click();
      await page.getByText('Không mở được nguồn.', { exact: true }).waitFor();
      await page.getByText('Mã hỗ trợ: R06-SOURCE', { exact: true }).waitFor();
      assert.equal(await page.getByRole('heading', { name: 'LIVE-billing_invoices', exact: true }).count(), 0);
      sourceFailure = 0;
      await page.getByRole('button', { name: 'Thử lại', exact: true }).click();
      await page.getByRole('heading', { name: 'LIVE-billing_invoices', exact: true }).waitFor();
      check('API ' + status + ': lỗi có mã hỗ trợ, ẩn dữ liệu cũ và thử lại thành công');
    }
    await page.reload();
    await page.locator('#staff-username').fill('review.r06');
    await page.locator('#staff-password').fill('synthetic-password-only');
    await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
    await page.getByRole('navigation', { name: 'Điều hướng chính' }).getByRole('button', { name: 'Dịch vụ cư dân', exact: true }).click();
    await page.getByLabel('Tòa nhà', { exact: true }).selectOption(ids.building);
    await page.getByRole('navigation', { name: 'Phân hệ dịch vụ cư dân' }).getByRole('button', { name: 'Báo cáo & xuất', exact: true }).click();
    await page.getByRole('button', { name: 'Xem chỉ tiêu & chi tiết', exact: true }).click();
    await page.getByLabel('Nguồn chi tiết', { exact: true }).selectOption('billing_invoices'); await open().click();
    await page.getByRole('heading', { name: 'LIVE-billing_invoices', exact: true }).waitFor();
    check('Tải lại trang, đăng nhập lại rồi mở nguồn hóa đơn');
    assert.deepEqual(errors, []); assert.deepEqual(unexpected, []);
    check('Không có pageerror hoặc API ngoài fixture');
    fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify({ passed: checks.length, checks, requests, errors, unexpected }, null, 2));
    console.log('R06 SOURCE UX PASS: ' + checks.length);
  } catch (error) {
    await page.screenshot({ path: path.join(output, 'failure.png'), fullPage: true });
    fs.writeFileSync(path.join(output, 'failure.json'), JSON.stringify({ error: error.message, checks, requests, errors, unexpected }, null, 2));
    throw error;
  } finally { await context.close(); await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
