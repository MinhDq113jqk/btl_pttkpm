const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');

const credentials = JSON.parse(fs.readFileSync(process.env.REAL_BROWSER_CREDENTIALS_FILE, 'utf8'));
const baseUrl = 'https://localhost/';
const evidenceDir = process.env.REAL_BROWSER_EVIDENCE_DIR;
const buildingId = '877e70c3-2c79-4472-a4dc-7f751c7e81f2';
const unitId = 'bf5f9baa-fee9-423d-8d57-aeea73205c49';
const checks = [];
const errors = [];
const apiFailures = [];
const check = (name, value = true) => { assert.ok(value, name); checks.push(name); console.log(`PASS ${name}`); };
const pngEvidence = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=', 'base64');

async function openParcelDesk(browser) {
  const context = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 1440, height: 920 }, locale: 'vi-VN' });
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  page.on('response', response => {
    if (response.url().includes('/api/v1/') && response.status() >= 400) {
      const pathName = new URL(response.url()).pathname;
      const requestMethod = response.request().method();
      const expectedMissingLink = requestMethod === 'GET' && (pathName.endsWith('/case') || pathName.endsWith('/incident'));
      if (!(response.status() === 403 && pathName.endsWith('/handover')) && !(response.status() === 404 && expectedMissingLink)) {
        apiFailures.push(`${response.status()}:${pathName}`);
      }
    }
  });
  await page.goto(baseUrl, { waitUntil: 'networkidle' });
  await page.locator('#staff-username').fill('cskh_west');
  await page.locator('#staff-password').fill(credentials.cskh_west);
  await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
  await page.locator('.desktop-shell').waitFor({ timeout: 15000 });
  await page.getByRole('navigation', { name: 'Điều hướng chính' }).getByRole('button', { name: 'Bưu phẩm & Bàn giao', exact: true }).click();
  await page.getByRole('heading', { name: 'Tiếp nhận và bàn giao bưu phẩm', exact: true }).waitFor();
  return { context, page };
}

async function createParcel(page, code, pin) {
  await page.getByRole('button', { name: 'Tiếp nhận bưu phẩm', exact: true }).first().click();
  await page.locator('#parcel-intake-building').fill(buildingId);
  await page.locator('#parcel-intake-unit').fill(unitId);
  await page.locator('#parcel-intake-code').fill(code);
  await page.locator('#parcel-intake-name').fill('Người nhận disposable GF06');
  await page.locator('#parcel-intake-contact').fill('090***0001');
  await page.locator('#parcel-intake-storage').fill('Locker GF06');
  await page.locator('#parcel-intake-pin').fill(pin);
  const responsePromise = page.waitForResponse(response => response.url().endsWith('/api/v1/parcels') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Lưu bưu phẩm', exact: true }).click();
  const response = await responsePromise;
  assert.equal(response.status(), 201);
  const parcel = await response.json();
  await page.getByText(code, { exact: true }).first().waitFor();
  await page.getByRole('heading', { name: code, exact: true }).waitFor();
  check(`GF06 intake persists parcel ${code} in the real backend`);
  return parcel;
}

(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const opened = [];
  try {
    const desk = await openParcelDesk(browser); opened.push(desk.context);
    const page = desk.page;
    const okCode = `GF06-OK-${Date.now()}`;
    const okParcel = await createParcel(page, okCode, '1234');

    const readyResponse = page.waitForResponse(response => response.url().includes(`/api/v1/parcels/${okParcel.id}/ready`) && response.request().method() === 'POST');
    await page.getByRole('button', { name: 'Đánh dấu sẵn sàng', exact: true }).click();
    assert.equal((await readyResponse).status(), 200);
    await page.getByText('Chờ người nhận', { exact: true }).first().waitFor();
    check('GF06 parcel moves from received to ready-for-pickup');

    await page.getByLabel('PIN người nhận').fill('1234');
    const handoverResponse = page.waitForResponse(response => response.url().includes(`/api/v1/parcels/${okParcel.id}/handover`) && response.request().method() === 'POST');
    await page.getByRole('button', { name: 'Xác nhận bàn giao', exact: true }).click();
    assert.equal((await handoverResponse).status(), 200);
    await page.getByText('Đã bàn giao', { exact: true }).first().waitFor();
    check('GF06 correct PIN completes one-time parcel handover');
    check('GF06 plaintext PIN is absent from the rendered UI', !(await page.locator('body').innerText()).includes('1234'));

    const caseForm = page.getByRole('article').filter({ hasText: 'Case dùng chung' });
    await caseForm.getByLabel('Lý do mở Case').fill('Đối chiếu bàn giao GF06 và lưu vết xử lý.');
    const caseResponse = page.waitForResponse(response => response.url().includes(`/api/v1/parcels/${okParcel.id}/case`) && response.request().method() === 'POST');
    await caseForm.getByRole('button', { name: 'Mở Case', exact: true }).click();
    assert.equal((await caseResponse).status(), 201);
    await page.getByText('Đã mở Case dùng chung cho bưu phẩm.', { exact: true }).waitFor();
    check('GF06 handed-over parcel can open a shared Case');

    const evidenceFileName = `gf06-${Date.now()}.png`;
    console.log(`EVIDENCE_INPUT_COUNT=${await page.locator('#parcel-evidence-file').count()}`);
    await page.locator('#parcel-evidence-file').setInputFiles({ name: evidenceFileName, mimeType: 'image/png', buffer: pngEvidence });
    const evidenceResponse = page.waitForResponse(response => response.url().includes(`/api/v1/parcels/${okParcel.id}/evidence`) && response.request().method() === 'POST');
    await page.getByRole('button', { name: 'Thêm bằng chứng', exact: true }).click();
    assert.equal((await evidenceResponse).status(), 201);
    await page.getByText('Đã lưu bằng chứng private và ghi audit.', { exact: true }).waitFor();
    check('GF06 private evidence upload returns a server-scoped attachment');
    const evidenceButton = page.getByRole('button', { name: `Xem bằng chứng ${evidenceFileName}`, exact: true });
    await evidenceButton.click();
    await page.getByRole('img', { name: `Xem trước ${evidenceFileName}`, exact: true }).waitFor();
    check('GF06 private evidence is retrieved through the signed-link preview');
    await page.getByRole('button', { name: 'Đóng xem', exact: true }).click();
    await page.screenshot({ path: path.join(evidenceDir, 'gf06-handover-case-evidence.png'), fullPage: true });

    const exceptionCode = `GF06-EX-${Date.now()}`;
    const exceptionParcel = await createParcel(page, exceptionCode, '5678');
    const exceptionReadyResponse = page.waitForResponse(response => response.url().includes(`/api/v1/parcels/${exceptionParcel.id}/ready`) && response.request().method() === 'POST');
    await page.getByRole('button', { name: 'Đánh dấu sẵn sàng', exact: true }).click();
    assert.equal((await exceptionReadyResponse).status(), 200);
    await page.getByText('Chờ người nhận', { exact: true }).first().waitFor();

    await page.getByLabel('PIN người nhận').fill('0000');
    const wrongPinResponse = page.waitForResponse(response => response.url().includes(`/api/v1/parcels/${exceptionParcel.id}/handover`) && response.request().method() === 'POST');
    await page.getByRole('button', { name: 'Xác nhận bàn giao', exact: true }).click();
    assert.equal((await wrongPinResponse).status(), 403);
    await page.getByRole('alert').filter({ hasText: 'PIN chưa đúng' }).waitFor();
    check('GF06 wrong PIN is rejected without handing over the parcel');

    await page.locator('details.parcel-exception > summary').click();
    await page.locator('#parcel-exception-status').selectOption('LOST');
    await page.locator('#parcel-exception-reason').fill('Không tìm thấy kiện trong khu vực locker GF06.');
    const exceptionResponse = page.waitForResponse(response => response.url().includes(`/api/v1/parcels/${exceptionParcel.id}/exception`) && response.request().method() === 'POST');
    await page.getByRole('button', { name: 'Ghi nhận ngoại lệ', exact: true }).click();
    assert.equal((await exceptionResponse).status(), 200);
    await page.getByText('Thất lạc', { exact: true }).first().waitFor();
    check('GF06 parcel exception records a terminal LOST state with reason');
    await page.setViewportSize({ width: 390, height: 844 });
    check('GF06 parcel desk has no horizontal mobile overflow', await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
    await page.screenshot({ path: path.join(evidenceDir, 'gf06-exception-mobile.png'), fullPage: true });

    check('GF06 browser has no page errors', errors.length === 0);
    check('GF06 API calls have no unexpected failed responses', apiFailures.length === 0);
    fs.writeFileSync(path.join(evidenceDir, 'gf06-real-browser.json'), JSON.stringify({ flow: 'GF-06', checks, errors, apiFailures }, null, 2));
    console.log(`REAL_BROWSER_GF06 PASS (${checks.length} checks)`);
  } finally {
    await Promise.all(opened.map(context => context.close().catch(() => {})));
    await browser.close();
  }
})().catch(error => { console.error(`REAL_BROWSER_GF06_FAILED: ${error.message}`); process.exitCode = 1; });
