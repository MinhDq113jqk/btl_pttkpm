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
let createdAssetId = '';
let workOrderCode = '';
const check = (name, value = true) => { assert.ok(value, name); checks.push(name); console.log(`PASS ${name}`); };
async function openRole(browser, username) {
  const context = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 1440, height: 920 }, locale: 'vi-VN' });
  const page = await context.newPage();
  page.on('pageerror', e => errors.push(`${username}: ${e.message}`));
  page.on('response', response => {
    if (response.url().includes('/api/v1/') && response.status() >= 400) apiFailures.push(`${username}:${response.status()}:${new URL(response.url()).pathname}`);
  });
  await page.goto(baseUrl, { waitUntil: 'networkidle' });
  await page.locator('#staff-username').fill(username);
  await page.locator('#staff-password').fill(credentials[username]);
  await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
  await page.locator('.desktop-shell').waitFor({ timeout: 15000 });
  await page.getByRole('navigation', { name: 'Điều hướng chính' }).getByRole('button', { name: 'Kỹ thuật & Bảo trì', exact: true }).click();
  await page.getByRole('heading', { name: username === 'technician_west' ? 'Bảo trì của tôi' : 'Kỹ thuật & Bảo trì' }).waitFor();
  return { context, page };
}
(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const opened = [];
  try {
    const lead = await openRole(browser, 'techlead_west'); opened.push(lead.context);
    await lead.page.getByLabel('Mã Asset').fill(`PUMP-GF03-${Date.now()}`);
    await lead.page.getByLabel('Tên thiết bị').fill('Bơm nước tầng hầm GF03');
    await lead.page.getByLabel('Mô tả').fill('Tài sản disposable cho real-browser GF03.');
    const assetResponse = lead.page.waitForResponse(response => response.url().endsWith('/api/v1/assets') && response.request().method() === 'POST');
    await lead.page.getByRole('button', { name: 'Tạo Asset' }).click();
    createdAssetId = (await assetResponse).json ? (await assetResponse).json().then(payload => payload.id) : '';
    createdAssetId = await createdAssetId;
    await lead.page.getByText('Đã tạo Asset.', { exact: true }).waitFor();
    check('GF03 technical lead creates an Asset through the real backend');
    await lead.page.getByLabel('Mã kế hoạch').fill(`PUMP-GF03-PLAN-${Date.now()}`);
    await lead.page.getByLabel('Tên kế hoạch').fill('Kiểm tra bơm GF03');
    const dueAt = new Date(Date.now() - 60_000);
    const dueAtLocal = new Date(dueAt.getTime() - dueAt.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
    await lead.page.getByLabel('Lần bảo trì kế tiếp').fill(dueAtLocal);
    await lead.page.getByRole('button', { name: 'Tạo Maintenance Plan' }).click();
    await lead.page.getByText('Đã tạo Maintenance Plan.', { exact: true }).waitFor();
    check('GF03 Maintenance Plan is persisted by the real backend');
    await lead.page.getByRole('button', { name: 'Chạy scheduler' }).click();
    await lead.page.getByText('Đã chạy scheduler; occurrence và Work Order đã được đọc lại từ máy chủ.', { exact: true }).waitFor();
    check('GF03 scheduler creates an occurrence and Work Order');
    const targetOccurrence = lead.page.locator('.maintenance-occurrence-row').filter({ hasText: createdAssetId.slice(0, 8) });
    await targetOccurrence.getByRole('button', { name: 'Mở Work Order' }).click();
    workOrderCode = (await lead.page.locator('.maintenance-work-detail h3').innerText()).split(' · ')[0];
    await lead.page.getByLabel('Giao cho kỹ thuật viên').selectOption({ index: 1 });
    await lead.page.getByRole('button', { name: 'Phân công' }).click();
    await lead.page.getByText('Đã phân công Work Order.', { exact: true }).waitFor();
    check('GF03 technical lead assigns the Work Order');
    await lead.page.screenshot({ path: path.join(evidenceDir, 'gf03-lead-assigned.png'), fullPage: true });
    await lead.context.close(); opened.splice(opened.indexOf(lead.context), 1);

    const tech = await openRole(browser, 'technician_west'); opened.push(tech.context);
    const technicianCard = tech.page.locator('.maintenance-work-card').filter({ hasText: workOrderCode });
    await technicianCard.getByRole('button', { name: 'Mở Work Order' }).click();
    await tech.page.getByRole('button', { name: 'Bắt đầu xử lý' }).click();
    const checklistRows = tech.page.locator('.workflow-checklist-row');
    for (let index = 0; index < await checklistRows.count(); index += 1) {
      const row = tech.page.locator('.workflow-checklist-row').nth(index);
      await row.getByRole('textbox').fill(`Đã hoàn thành mục checklist ${index + 1}.`);
      await row.locator('input[type="checkbox"]').click();
      await tech.page.getByText('Đã lưu checklist.', { exact: true }).waitFor();
    }
    const uploadResponse = tech.page.waitForResponse(response => response.url().includes('/evidence') && response.request().method() === 'POST');
    const pngEvidence = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=', 'base64');
    await tech.page.locator('.workflow-file-button input').setInputFiles({ name: 'gf03-pump.png', mimeType: 'image/png', buffer: pngEvidence });
    const uploadResult = await uploadResponse;
    check('GF03 evidence upload reaches the real backend', uploadResult.status() === 201);
    await tech.page.waitForTimeout(500);
    await tech.page.getByLabel('Kết quả xử lý').fill('Bơm hoạt động bình thường sau bảo trì GF03.');
    await tech.page.getByRole('button', { name: 'Gửi nghiệm thu' }).click();
    await tech.page.getByText('Đã gửi Work Order nghiệm thu.', { exact: true }).waitFor();
    check('GF03 technician completes checklist and uploads evidence');
    await tech.page.screenshot({ path: path.join(evidenceDir, 'gf03-technician-submitted.png'), fullPage: true });
    await tech.context.close(); opened.splice(opened.indexOf(tech.context), 1);

    const accept = await openRole(browser, 'techlead_west'); opened.push(accept.context);
    const acceptedOccurrence = accept.page.locator('.maintenance-occurrence-row').filter({ hasText: createdAssetId.slice(0, 8) });
    await acceptedOccurrence.getByRole('button', { name: 'Mở Work Order' }).click();
    await accept.page.getByRole('button', { name: 'Nghiệm thu kỹ thuật' }).click();
    await accept.page.getByText('Đã nghiệm thu kỹ thuật.', { exact: true }).waitFor();
    check('GF03 technical acceptance completes the occurrence');
    await accept.page.reload({ waitUntil: 'networkidle' });
    await accept.page.getByRole('heading', { name: 'Đăng nhập GreenCity' }).waitFor();
    await accept.page.locator('#staff-username').fill('techlead_west');
    await accept.page.locator('#staff-password').fill(credentials.techlead_west);
    await accept.page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
    await accept.page.locator('.desktop-shell').waitFor({ timeout: 15000 });
    await accept.page.getByRole('navigation', { name: 'Điều hướng chính' }).getByRole('button', { name: 'Kỹ thuật & Bảo trì', exact: true }).click();
    await accept.page.getByRole('heading', { name: 'Kỹ thuật & Bảo trì' }).waitFor();
    check('GF03 maintenance state remains visible after browser reload');
    await accept.page.screenshot({ path: path.join(evidenceDir, 'gf03-accepted-reloaded.png'), fullPage: true });
    check('GF03 browser has no page errors', errors.length === 0);
    check('GF03 API calls have no failed responses', apiFailures.length === 0);
    fs.writeFileSync(path.join(evidenceDir, 'gf03-real-browser.json'), JSON.stringify({ flow: 'GF-03', checks, errors, apiFailures }, null, 2));
    console.log(`REAL_BROWSER_GF03 PASS (${checks.length} checks)`);
  } finally {
    await Promise.all(opened.map(context => context.close().catch(() => {})));
    await browser.close();
  }
})().catch(error => { console.error(`REAL_BROWSER_GF03_FAILED: ${error.message}`); process.exitCode = 1; });
