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
let allowExpectedEscalationBlock = false;
const check = (name, value = true) => { assert.ok(value, name); checks.push(name); console.log(`PASS ${name}`); };

const runSaltMinutes = (Math.floor(Date.now() / 1000) % 120) + Math.floor(Math.random() * 120);
const localInput = hours => {
  const date = new Date(Date.now() + hours * 3_600_000 + runSaltMinutes * 60_000);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
};

async function openRole(browser, username) {
  const context = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 1440, height: 920 }, locale: 'vi-VN' });
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(`${username}: ${error.message}`));
  page.on('response', response => {
    if (response.url().includes('/api/v1/') && response.status() >= 400) {
      const pathName = new URL(response.url()).pathname;
      if (!(allowExpectedEscalationBlock && response.status() === 422 && pathName.endsWith('/transition'))) {
        apiFailures.push(`${username}:${response.status()}:${pathName}`);
      }
    }
  });
  await page.goto(baseUrl, { waitUntil: 'networkidle' });
  await page.locator('#staff-username').fill(username);
  await page.locator('#staff-password').fill(credentials[username]);
  await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
  await page.locator('.desktop-shell').waitFor({ timeout: 15000 });
  await page.getByRole('navigation', { name: 'Điều hướng chính' }).getByRole('button', { name: 'An ninh & Tuần tra', exact: true }).click();
  await page.getByRole('heading', { name: username === 'security_west' ? 'Ca trực và tuần tra của tôi' : 'Điều phối an ninh và tuần tra', exact: true }).waitFor();
  return { context, page };
}

async function createShift(manager) {
  const page = manager.page;
  const form = page.getByRole('region', { name: 'Tạo ca trực an ninh' });
  const point = form.getByLabel('Điểm tuần tra');
  const assigneeResponse = page.waitForResponse(response => response.url().includes('/api/v1/security/assignees') && response.request().method() === 'GET');
  await point.selectOption({ index: 1 });
  assert.equal((await assigneeResponse).status(), 200);
  const assignee = form.getByLabel('Nhân viên trực');
  await assignee.locator('option').nth(1).waitFor({ state: 'attached' });
  await assignee.selectOption({ index: 1 });
  await form.getByLabel('Bắt đầu').fill(localInput(120));
  await form.getByLabel('Kết thúc').fill(localInput(122));
  const responsePromise = page.waitForResponse(response => response.url().endsWith('/api/v1/security/shifts') && response.request().method() === 'POST');
  await form.getByRole('button', { name: 'Tạo ca', exact: true }).click();
  const response = await responsePromise;
  assert.equal(response.status(), 201);
  const shift = await response.json();
  await page.getByText('Đã tạo ca trực và cửa sổ tuần tra.', { exact: true }).waitFor();
  check('GF05 manager creates a scoped security shift and patrol window', shift.patrol_windows.length === 1);
  return shift;
}

(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const opened = [];
  try {
    const manager = await openRole(browser, 'director_west'); opened.push(manager.context);
    const shift = await createShift(manager);
    const shiftCard = manager.page.locator('.security-shift-card').first();

    const startResponse = manager.page.waitForResponse(response => response.url().includes(`/api/v1/security/shifts/${shift.id}/start`) && response.request().method() === 'POST');
    await shiftCard.getByRole('button', { name: 'Bắt đầu ca', exact: true }).click();
    assert.equal((await startResponse).status(), 200);
    await shiftCard.locator('.status-badge').filter({ hasText: 'Đang trực' }).waitFor();
    check('GF05 manager starts the assigned security shift');

    const handoffAssignee = shiftCard.getByLabel('Người nhận');
    await handoffAssignee.locator('option').nth(1).waitFor({ state: 'attached' });
    await handoffAssignee.selectOption({ index: 1 });
    await shiftCard.getByLabel('Tóm tắt bàn giao').fill('Ca bắt đầu bình thường, bàn giao đủ thiết bị.');
    const handoffResponse = manager.page.waitForResponse(response => response.url().includes(`/api/v1/security/shifts/${shift.id}/handoffs`) && response.request().method() === 'POST');
    await shiftCard.getByRole('button', { name: 'Bàn giao', exact: true }).click();
    assert.equal((await handoffResponse).status(), 201);
    check('GF05 handoff records the receiving security account');

    await shiftCard.getByLabel('Khách').fill('Khách giao hàng GF05');
    await shiftCard.getByLabel('Mục đích').fill('Giao thiết bị cho cư dân nội bộ.');
    const visitorResponse = manager.page.waitForResponse(response => response.url().includes(`/api/v1/security/shifts/${shift.id}/visitors`) && response.request().method() === 'POST');
    await shiftCard.getByRole('button', { name: 'Ghi khách', exact: true }).click();
    assert.equal((await visitorResponse).status(), 201);
    check('GF05 visitor log is saved on the real backend');

    const windowId = shift.patrol_windows[0].id;
    const windowSection = shiftCard.locator('.security-window').first();
    const checkInResponse = manager.page.waitForResponse(response => response.url().includes(`/api/v1/security/patrol-windows/${windowId}/logs`) && response.request().method() === 'POST');
    await windowSection.getByRole('button', { name: 'Check-in', exact: true }).click();
    assert.equal((await checkInResponse).status(), 201);
    await manager.page.getByText('Đã ghi nhận đến điểm tuần tra.', { exact: true }).waitFor();
    check('GF05 patrol check-in is recorded');

    const completeResponse = manager.page.waitForResponse(response => response.url().includes(`/api/v1/security/patrol-windows/${windowId}/complete`) && response.request().method() === 'POST');
    await manager.page.locator('.security-shift-card').first().locator('.security-window').first().getByRole('button', { name: 'Hoàn thành', exact: true }).click();
    assert.equal((await completeResponse).status(), 200);
    await shiftCard.locator('.security-window').first().locator('.status-badge').filter({ hasText: 'Đã tuần tra' }).waitFor();
    check('GF05 patrol window completes after check-in');

    const currentWindow = manager.page.locator('.security-shift-card').first().locator('.security-window').first();
    await currentWindow.getByText('Báo sự cố hoặc PCCC', { exact: true }).click();
    await currentWindow.getByLabel('Tiêu đề').fill('Phát hiện người lạ tại tầng hầm GF05');
    await currentWindow.getByLabel('Mô tả').fill('Bảo vệ phát hiện người lạ ở khu vực kỹ thuật.');
    const incidentResponse = manager.page.waitForResponse(response => response.url().endsWith('/api/v1/security/incidents') && response.request().method() === 'POST');
    await currentWindow.getByRole('button', { name: 'Gửi sự cố', exact: true }).click();
    const incident = await incidentResponse;
    assert.equal(incident.status(), 201);
    const incidentRecord = await incident.json();
    await manager.page.getByText('Đã lập sự cố và escalation nếu mức độ cao.', { exact: true }).waitFor();
    check('GF05 high severity incident creates security and director escalations', incidentRecord.escalations.length === 2 && incidentRecord.severity === 'HIGH');

    let incidentPanel = manager.page.getByLabel('Sự cố an ninh và PCCC').getByRole('article').filter({ hasText: incidentRecord.code });
    const directorEscalation = incidentRecord.escalations.find(item => item.target_role === 'director');
    const directorAckResponse = manager.page.waitForResponse(response => response.url().includes(`/api/v1/security/incidents/${incidentRecord.id}/escalations/${directorEscalation.id}/acknowledgements`) && response.request().method() === 'POST');
    await incidentPanel.getByRole('button', { name: 'Xác nhận director', exact: true }).click();
    assert.equal((await directorAckResponse).status(), 201);
    await manager.page.getByText('Đã acknowledgement escalation.', { exact: true }).waitFor();
    check('GF05 director acknowledges the director escalation');

    incidentPanel = manager.page.getByLabel('Sự cố an ninh và PCCC').getByRole('article').filter({ hasText: incidentRecord.code });
    await incidentPanel.getByLabel('Bằng chứng / ghi chú').fill('Đã kiểm tra camera và vị trí hiện trường GF05.');
    const evidenceResponse = manager.page.waitForResponse(response => response.url().includes(`/api/v1/security/incidents/${incidentRecord.id}/evidence`) && response.request().method() === 'POST');
    await incidentPanel.getByRole('button', { name: 'Thêm bằng chứng', exact: true }).click();
    assert.equal((await evidenceResponse).status(), 201);
    await manager.page.getByText('Đã thêm bằng chứng.', { exact: true }).waitFor();
    check('GF05 incident evidence is stored with the incident');

    for (const [buttonName, status] of [['Tiếp nhận', 'TRIAGED'], ['Xử lý', 'IN_PROGRESS'], ['Đánh dấu đã giải quyết', 'RESOLVED']]) {
      incidentPanel = manager.page.getByLabel('Sự cố an ninh và PCCC').getByRole('article').filter({ hasText: incidentRecord.code });
      const transitionResponse = manager.page.waitForResponse(response => response.url().includes(`/api/v1/security/incidents/${incidentRecord.id}/transition`) && response.request().method() === 'POST');
      await incidentPanel.getByRole('button', { name: buttonName, exact: true }).click();
      const transition = await transitionResponse;
      assert.equal(transition.status(), 200);
      check(`GF05 incident transitions to ${status}`);
    }

    incidentPanel = manager.page.getByLabel('Sự cố an ninh và PCCC').getByRole('article').filter({ hasText: incidentRecord.code });
    await incidentPanel.getByLabel('Kết luận').fill('Đã bàn giao cho cơ quan chức năng và lập biên bản.');
    allowExpectedEscalationBlock = true;
    const blockedCloseResponse = manager.page.waitForResponse(response => response.url().includes(`/api/v1/security/incidents/${incidentRecord.id}/transition`) && response.request().method() === 'POST');
    await incidentPanel.getByRole('button', { name: 'Đóng sự cố', exact: true }).click();
    assert.equal((await blockedCloseResponse).status(), 422);
    allowExpectedEscalationBlock = false;
    await manager.page.getByRole('alert').filter({ hasText: 'Sự cố mức cao cần đủ acknowledgement' }).waitFor();
    check('GF05 high incident closure is blocked until security acknowledgement');
    await manager.page.screenshot({ path: path.join(evidenceDir, 'gf05-director-blocked-close.png'), fullPage: true });
    await manager.context.close(); opened.splice(opened.indexOf(manager.context), 1);

    const security = await openRole(browser, 'security_west'); opened.push(security.context);
    const securityIncidentPanel = security.page.getByLabel('Sự cố an ninh và PCCC').getByRole('article').filter({ hasText: incidentRecord.code });
    const securityEscalation = incidentRecord.escalations.find(item => item.target_role === 'security');
    const securityAckResponse = security.page.waitForResponse(response => response.url().includes(`/api/v1/security/incidents/${incidentRecord.id}/escalations/${securityEscalation.id}/acknowledgements`) && response.request().method() === 'POST');
    await securityIncidentPanel.getByRole('button', { name: 'Xác nhận security', exact: true }).click();
    assert.equal((await securityAckResponse).status(), 201);
    await security.page.getByText('Đã acknowledgement escalation.', { exact: true }).waitFor();
    check('GF05 security account acknowledges the security escalation');
    await security.context.close(); opened.splice(opened.indexOf(security.context), 1);

    const finalManager = await openRole(browser, 'director_west'); opened.push(finalManager.context);
    const finalPanel = finalManager.page.getByLabel('Sự cố an ninh và PCCC').getByRole('article').filter({ hasText: incidentRecord.code });
    await finalPanel.getByLabel('Kết luận').fill('Đã bàn giao cho cơ quan chức năng và lập biên bản.');
    const closeResponse = finalManager.page.waitForResponse(response => response.url().includes(`/api/v1/security/incidents/${incidentRecord.id}/transition`) && response.request().method() === 'POST');
    await finalPanel.getByRole('button', { name: 'Đóng sự cố', exact: true }).click();
    const closed = await closeResponse;
    assert.equal(closed.status(), 200);
    const closedRecord = await closed.json();
    await finalPanel.getByText(/CLOSED/).waitFor();
    check('GF05 incident closes after both acknowledgements, evidence and conclusion', closedRecord.status === 'CLOSED');
    await finalManager.page.screenshot({ path: path.join(evidenceDir, 'gf05-incident-closed.png'), fullPage: true });

    check('GF05 browser has no page errors', errors.length === 0);
    check('GF05 API calls have no unexpected failed responses', apiFailures.length === 0);
    fs.writeFileSync(path.join(evidenceDir, 'gf05-real-browser.json'), JSON.stringify({ flow: 'GF-05', checks, errors, apiFailures }, null, 2));
    console.log(`REAL_BROWSER_GF05 PASS (${checks.length} checks)`);
  } finally {
    await Promise.all(opened.map(context => context.close().catch(() => {})));
    await browser.close();
  }
})().catch(error => { console.error(`REAL_BROWSER_GF05_FAILED: ${error.message}`); process.exitCode = 1; });
