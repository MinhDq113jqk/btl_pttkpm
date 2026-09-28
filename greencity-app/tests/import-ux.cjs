const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const { randomUUID } = require('node:crypto');

const siteId = randomUUID();
const runId = randomUUID();
const token = randomUUID();
const correlationId = randomUUID();
const calls = [];
const uploadKeys = [];
let uploadAttempts = 0;
let run = {
  id: runId, mode: 'PARTIAL', status: 'UPLOADED', source_filename: 'units.csv', source_mime_type: 'text/csv',
  source_size_bytes: 84, source_sha256: 'a'.repeat(64), source_is_quarantined: false, total_rows: 2,
  valid_rows: 1, warning_rows: 0, error_rows: 1, skipped_rows: 0, applied_rows: 0,
  error_file_available: false, failure_code: null, previewed_at: null, applied_at: null, failed_at: null, version: 1,
};

const response = (payload, status = 200, headers = {}) => ({
  status,
  headers: { 'Content-Type': 'application/json', 'X-Correlation-ID': correlationId, ...headers },
  body: JSON.stringify(payload),
});

(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, locale: 'vi-VN', acceptDownloads: true });
  const errors = [];
  const checks = [];
  const check = (name, value = true) => { assert.ok(value, name); checks.push(name); console.log(`PASS ${name}`); };
  page.on('pageerror', error => errors.push(error.message));

  await page.route('**/api/v1/**', async route => {
    const request = route.request();
    const url = new URL(request.url());
    let body = null;
    try { body = request.postDataJSON?.(); } catch { /* CSV upload is an intentionally raw body. */ }
    calls.push({ path: url.pathname, search: url.search, method: request.method(), headers: request.headers(), body });
    const headers = { 'Content-Type': 'application/json', 'X-Correlation-ID': correlationId };
    if (url.pathname.endsWith('/auth/login')) return route.fulfill(response({ access_token: token }));
    if (url.pathname.endsWith('/auth/me')) return route.fulfill(response({
      account_id: randomUUID(), tenant_id: randomUUID(), username: 'cskh.browser', full_name: 'CSKH Trình duyệt',
      roles: ['cskh'], active_site_id: siteId, must_change_password: false,
      allowed_sites: [{ id: siteId, code: 'WEST', name: 'GreenCity West' }],
    }));
    if (url.pathname.endsWith('/service-requests')) return route.fulfill(response({ items: [], page: 1, page_size: 20, total: 0 }));
    if (url.pathname.endsWith('/notifications')) return route.fulfill(response({ items: [] }));
    if (url.pathname.endsWith('/import-runs/template')) return route.fulfill({ status: 200, headers: { 'Content-Type': 'text/csv', 'Content-Disposition': 'attachment; filename="unit-import-template.csv"' }, body: 'unit_number,floor,area_m2,status\n' });
    if (url.pathname.endsWith('/units/export')) return route.fulfill({ status: 200, headers: { 'Content-Type': 'text/csv', 'Content-Disposition': 'attachment; filename="unit-export.csv"' }, body: 'unit_number,floor,area_m2,status\nA-0101,1,50,occupied\n' });
    if (url.pathname.endsWith('/import-runs') && request.method() === 'POST') {
      uploadAttempts += 1;
      uploadKeys.push(request.headers()['idempotency-key']);
      const raw = request.postDataBuffer().toString('utf8');
      if (uploadAttempts === 1) return route.abort('failed');
      assert.ok(raw.startsWith('unit_number,floor,area_m2,status'));
      run = { ...run, source_filename: request.headers()['x-file-name'] || run.source_filename };
      return route.fulfill(response(run, 201));
    }
    if (url.pathname.endsWith(`/import-runs/${runId}/preview`)) {
      check('preview request carries version and four mapped CSV fields', body?.expected_version === 1
        && Object.keys(body?.mapping || {}).sort().join(',') === 'area_m2,floor,status,unit_number');
      run = { ...run, status: 'PREVIEWED', previewed_at: '2026-09-25T02:00:00Z', error_file_available: true, version: 2 };
      return route.fulfill(response(run));
    }
    if (url.pathname.endsWith(`/import-runs/${runId}/apply`)) {
      check('apply request uses latest preview version', body?.expected_version === 2);
      run = { ...run, status: 'APPLIED', applied_at: '2026-09-25T02:01:00Z', applied_rows: 1, version: 3 };
      return route.fulfill(response(run));
    }
    if (url.pathname.endsWith(`/import-runs/${runId}/rows`)) return route.fulfill(response({
      items: run.status === 'UPLOADED' ? [] : [{ row_number: 3, status: run.status === 'APPLIED' ? 'IMPORTED' : 'ERROR', issues: run.status === 'APPLIED' ? [] : [{ code: 'INVALID_FLOOR', column: 'floor', message: 'Tầng không hợp lệ.' }] }],
      page: 1, page_size: 100, total: run.status === 'UPLOADED' ? 0 : 1,
    }));
    if (url.pathname.endsWith(`/import-runs/${runId}/error-file/signed-link`)) return route.fulfill(response({
      url: `/api/v1/import-runs/${runId}/error-file?signed_token=short-lived`, expires_at: '2026-09-25T02:10:00Z',
    }));
    if (url.pathname.endsWith(`/import-runs/${runId}/error-file`)) return route.fulfill({ status: 200, headers: { 'Content-Type': 'text/csv', 'Content-Disposition': 'attachment; filename="units-errors.csv"' }, body: 'row_number,code\n3,INVALID_FLOOR\n' });
    if (url.pathname.endsWith(`/import-runs/${runId}`)) return route.fulfill(response(run));
    return route.fulfill(response({ error: { code: 'ERR-NOTFOUND', message: 'Không tìm thấy.', correlation_id: correlationId } }, 404));
  });

  try {
    const base = process.env.UX_BASE_URL || 'http://127.0.0.1:3000/';
    await page.goto(base);
    await page.locator('#staff-username').fill('cskh.browser');
    await page.locator('#staff-password').fill(`test-${randomUUID()}`);
    await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
    const navigation = page.getByRole('navigation', { name: 'Điều hướng chính' });
    await navigation.getByRole('button', { name: 'Nhập dữ liệu căn hộ', exact: true }).click();
    await page.getByRole('heading', { name: 'Nhập dữ liệu căn hộ' }).waitFor();
    check('CSKH can open the server-backed import page', await page.getByLabel('Mã tòa nhà').isVisible());
    await page.getByLabel('Mã tòa nhà').fill('B1');
    await page.locator('#unit-import-file').setInputFiles({
      name: 'units.csv', mimeType: 'text/csv', buffer: Buffer.from('unit_number,floor,area_m2,status\nA-0101,1,50,occupied\n'),
    });
    await page.getByRole('button', { name: 'Tải CSV lên', exact: true }).click();
    await page.getByRole('alert').filter({ hasText: 'Không thể kết nối máy chủ' }).waitFor();
    check('failed upload shows a real error and keeps retry available', await page.getByRole('button', { name: 'Tải CSV lên', exact: true }).isEnabled());
    await page.getByRole('button', { name: 'Tải CSV lên', exact: true }).click();
    await page.getByText(runId, { exact: true }).waitFor();
    check('upload retry reuses one idempotency key', uploadKeys.length === 2 && uploadKeys[0] && uploadKeys[0] === uploadKeys[1]);
    check('upload request contains building code only and no client scope claims', calls.some(call => call.path.endsWith('/import-runs') && call.search.includes('building_code=B1') && !/tenant_id|site_id|building_id|role=/.test(call.search)));
    await page.getByRole('button', { name: 'Kiểm tra dữ liệu', exact: true }).click();
    await page.getByText('INVALID_FLOOR', { exact: true }).waitFor();
    check('preview surfaces row-level error returned by the API');
    await page.getByRole('button', { name: 'Áp dụng vào database', exact: true }).click();
    await page.getByText('Đã nhập 1 dòng.', { exact: true }).waitFor();
    check('success notice appears only after API apply response');
    const errorDownload = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Tải tệp dòng lỗi', exact: true }).click();
    check('error CSV is downloaded through its short-lived signed API link', (await errorDownload).suggestedFilename() === 'units-errors.csv');
    const templateDownload = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Tải mẫu CSV', exact: true }).click();
    check('server CSV template downloads with its API filename', (await templateDownload).suggestedFilename() === 'unit-import-template.csv');
    const exportDownload = page.waitForEvent('download', { timeout: 7000 }).catch(() => null);
    await page.getByRole('button', { name: 'Xuất CSV tòa nhà này', exact: true }).click();
    const downloadedExport = await exportDownload;
    if (!downloadedExport) console.error('Export diagnostics:', calls.filter(call => call.path.endsWith('/units/export')), await page.locator('body').innerText());
    check('scoped Unit export downloads the fixed schema', downloadedExport?.suggestedFilename() === 'unit-export.csv');
    check('no runtime browser errors', errors.length === 0);
    console.log(`IMPORT UX: ${checks.length} checks passed.`);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
