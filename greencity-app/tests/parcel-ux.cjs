const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { randomUUID } = require('node:crypto');
const { chromium } = require('playwright');

const output = path.resolve(__dirname, '../artifacts/parcel-ux');
fs.mkdirSync(output, { recursive: true });

const token = randomUUID();
const correlationId = randomUUID();
const siteId = randomUUID();
const buildingId = randomUUID();
const unitId = randomUUID();
const parcelId = randomUUID();
const user = {
  account_id: randomUUID(), tenant_id: randomUUID(), username: 'cskh.parcel.browser', full_name: 'Nhân viên CSKH',
  roles: ['cskh'], active_site_id: siteId, allowed_sites: [{ id: siteId, code: 'CENTRAL', name: 'GreenCity Central' }],
};
let parcel = {
  id: parcelId, tenant_id: user.tenant_id, site_id: siteId, building_id: buildingId, unit_id: unitId,
  recipient_person_id: null, parcel_code: 'P-UX-001', carrier_reference: 'carrier-001',
  recipient_name_snapshot: 'Người nhận demo', recipient_contact_snapshot: '09******12', storage_location: 'Locker A-01',
  pin_attempt_count: 0, pin_locked_until: null, status: 'RECEIVED', received_at: '2026-09-17T02:00:00Z',
  ready_for_pickup_at: null, handed_over_at: null, handed_over_by_id: null, exception_reason: null,
  created_by_id: user.account_id, updated_by_id: user.account_id, version: 1,
  created_at: '2026-09-17T02:00:00Z', updated_at: '2026-09-17T02:00:00Z',
};
const evidence = {
  id: randomUUID(), parcel_id: parcelId, original_name: 'locker.png', mime_type: 'image/png',
  size_bytes: 68,
  sha256: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
  created_at: '2026-09-17T02:01:00Z',
};
const evidencePng = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
  'base64',
);

(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'vi-VN', reducedMotion: 'reduce' });
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
    const respond = (payload, status = 200) => route.fulfill({ status, headers, body: JSON.stringify(payload) });
    if (url.pathname.endsWith('/auth/login')) return respond({ access_token: token });
    if (url.pathname.endsWith('/auth/me')) return respond(user);
    if (url.pathname.endsWith('/service-requests') && request.method() === 'GET') return respond({ items: [], page: 1, page_size: 20, total: 0 });
    if (url.pathname.endsWith('/notifications') && request.method() === 'GET') return respond({ items: [] });
    if (url.pathname.endsWith('/parcels') && request.method() === 'GET') return respond({ items: [parcel], page: 1, page_size: 50, total: 1 });
    if (url.pathname.endsWith('/parcels') && request.method() === 'POST') {
      parcel = { ...parcel, ...body, id: randomUUID(), recipient_person_id: body.recipient_person_id || null, status: 'RECEIVED', version: 1, pin_attempt_count: 0, created_at: '2026-09-17T02:00:00Z', updated_at: '2026-09-17T02:00:00Z' };
      return respond(parcel, 201);
    }
    if (url.pathname.endsWith(`/parcels/${parcel.id}/case`) && request.method() === 'GET') return respond({ error: { code: 'ERR-SCOPE-NOTFOUND', message: 'Chưa có Case.', correlation_id: correlationId } }, 404);
    if (url.pathname.endsWith(`/parcels/${parcel.id}/incident`) && request.method() === 'GET') return respond({ error: { code: 'ERR-SCOPE-NOTFOUND', message: 'Chưa có incident.', correlation_id: correlationId } }, 404);
    if (url.pathname.endsWith(`/parcels/${parcel.id}/evidence/${evidence.id}/signed-link`) && request.method() === 'GET') {
      return respond({
        url: `/api/v1/parcels/${parcel.id}/evidence/${evidence.id}/content?signed_token=ux-signed-token`,
        expires_at: '2026-09-17T03:01:00Z',
      });
    }
    if (url.pathname.endsWith(`/parcels/${parcel.id}/evidence/${evidence.id}/content`) && request.method() === 'GET') {
      return route.fulfill({ status: 200, headers: { 'Content-Type': 'image/png', 'X-Correlation-ID': correlationId }, body: evidencePng });
    }
    if (url.pathname.endsWith(`/parcels/${parcel.id}/evidence`) && request.method() === 'GET') return respond({ items: [evidence] });
    if (url.pathname.endsWith(`/parcels/${parcel.id}/timeline`) && request.method() === 'GET') return respond({ items: [] });
    if (url.pathname.endsWith(`/parcels/${parcel.id}/ready`)) {
      parcel = { ...parcel, status: 'READY_FOR_PICKUP', ready_for_pickup_at: '2026-09-17T02:05:00Z', version: parcel.version + 1 };
      return respond(parcel);
    }
    if (url.pathname.endsWith(`/parcels/${parcel.id}/handover`)) {
      parcel = { ...parcel, status: 'HANDED_OVER', handed_over_at: '2026-09-17T02:06:00Z', handed_over_by_id: user.account_id, version: parcel.version + 1 };
      return respond(parcel);
    }
    return respond({ error: { code: 'ERR-NOTFOUND', message: 'Không tìm thấy.', correlation_id: correlationId } }, 404);
  });

  try {
    await page.goto(process.env.UX_BASE_URL || 'http://127.0.0.1:3000/');
    await page.getByLabel('Tên đăng nhập').fill(user.username);
    await page.getByLabel('Mật khẩu').fill('browser-only-password');
    await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
    await page.getByRole('navigation', { name: 'Điều hướng chính' }).getByRole('button', { name: 'Bưu phẩm & Bàn giao', exact: true }).click();
    await page.getByRole('heading', { name: 'Tiếp nhận và bàn giao bưu phẩm', exact: true }).waitFor();
    await page.getByText('P-UX-001', { exact: true }).first().waitFor();
    await page.getByRole('button', { name: 'Xem bằng chứng locker.png', exact: true }).click();
    await page.getByRole('img', { name: 'Xem trước locker.png', exact: true }).waitFor();
    await page.getByRole('button', { name: 'Đóng xem', exact: true }).click();

    await page.getByRole('button', { name: 'Tiếp nhận bưu phẩm', exact: true }).click();
    await page.locator('#parcel-intake-building').fill(buildingId);
    await page.locator('#parcel-intake-unit').fill(unitId);
    await page.locator('#parcel-intake-code').fill('P-UX-002');
    await page.locator('#parcel-intake-name').fill('Nguyễn Người Nhận');
    await page.locator('#parcel-intake-pin').fill('1234');
    await page.getByRole('button', { name: 'Lưu bưu phẩm', exact: true }).click();
    await page.getByText('P-UX-002', { exact: true }).first().waitFor();

    await page.getByRole('button', { name: 'Đánh dấu sẵn sàng', exact: true }).click();
    await page.getByText('Chờ người nhận', { exact: true }).first().waitFor();
    await page.getByLabel('PIN người nhận').fill('1234');
    await page.getByRole('button', { name: 'Xác nhận bàn giao', exact: true }).click();
    await page.getByText('Đã bàn giao', { exact: true }).first().waitFor();

    await page.setViewportSize({ width: 390, height: 844 });
    const noHorizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
    assert.equal(noHorizontalOverflow, true, 'parcel desk must not create horizontal overflow on a small viewport');
    await page.screenshot({ path: path.join(output, 'parcel-handover-mobile.png'), fullPage: true });

    const parcelRequests = requests.filter(item => item.path.includes('/parcels'));
    const commands = parcelRequests.filter(item => item.method !== 'GET');
    assert.deepEqual(commands.map(item => item.method), ['POST', 'POST', 'POST']);
    assert.ok(parcelRequests.every(item => item.authorization === `Bearer ${token}`));
    assert.ok(commands.every(item => typeof item.idempotencyKey === 'string' && item.idempotencyKey.length > 0));
    assert.ok(commands.every(item => !/tenant_id|site_id|role/.test(JSON.stringify(item.body))));
    const bodyText = await page.locator('body').innerText();
    assert.equal(bodyText.includes('1234'), false, 'plaintext PIN must not be rendered after handover');
    assert.equal(errors.length, 0);
    fs.writeFileSync(path.join(output, 'test-results.json'), JSON.stringify({ passed: 13, errors }, null, 2));
    console.log('PARCEL UX: 13 checks passed.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
