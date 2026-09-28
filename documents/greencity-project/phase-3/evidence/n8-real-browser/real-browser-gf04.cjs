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
const check = (name, value = true) => { assert.ok(value, name); checks.push(name); console.log(`PASS ${name}`); };

const runSaltMinutes = Math.floor(Date.now() / 1000) % 120;
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
      apiFailures.push(`${username}:${response.status()}:${new URL(response.url()).pathname}`);
    }
  });
  await page.goto(baseUrl, { waitUntil: 'networkidle' });
  await page.locator('#staff-username').fill(username);
  await page.locator('#staff-password').fill(credentials[username]);
  await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
  await page.locator('.desktop-shell').waitFor({ timeout: 15000 });
  await page.getByRole('navigation', { name: 'Điều hướng chính' }).getByRole('button', { name: 'Vệ sinh môi trường', exact: true }).click();
  await page.getByRole('heading', { name: username === 'cleaning_west' ? 'Ca vệ sinh của tôi' : 'Điều phối ca vệ sinh', exact: true }).waitFor();
  return { context, page };
}

async function createShift(manager, startHours, endHours) {
  const page = manager.page;
  await page.getByLabel('Tuyến').selectOption({ index: 1 });
  await page.getByLabel('Bắt đầu').fill(localInput(startHours));
  await page.getByLabel('Kết thúc').fill(localInput(endHours));
  const responsePromise = page.waitForResponse(response => response.url().endsWith('/api/v1/cleaning/shifts') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Tạo ca', exact: true }).click();
  const response = await responsePromise;
  const responseBody = await response.text();
  if (response.status() !== 201) throw new Error(`cleaning shift create ${response.status()}: ${responseBody}`);
  const shift = JSON.parse(responseBody);
  await page.getByText(`Đã tạo ca vệ sinh với ${shift.tasks.length} khu vực.`, { exact: true }).waitFor();
  check(`GF04 cleaning shift creates ${shift.tasks.length} server-snapshotted task(s)` , shift.tasks.length === 1);
  return shift;
}

async function assignTask(manager, task) {
  const card = manager.page.locator('.cleaning-task-card').filter({ hasText: task.area_name }).first();
  await card.waitFor();
  const assignee = card.getByLabel('Phân công');
  const assigneeResponse = manager.page.waitForResponse(response => response.url().includes('/api/v1/cleaning/assignees') && response.request().method() === 'GET');
  await assignee.focus();
  assert.equal((await assigneeResponse).status(), 200);
  await assignee.locator('option').nth(1).waitFor({ state: 'attached' });
  await assignee.selectOption({ index: 1 });
  const responsePromise = manager.page.waitForResponse(response => response.url().includes(`/api/v1/cleaning/tasks/${task.id}/assign`) && response.request().method() === 'POST');
  await card.getByRole('button', { name: 'Phân công', exact: true }).click();
  const response = await responsePromise;
  assert.equal(response.status(), 200);
  await card.locator('.status-badge').filter({ hasText: 'Đã phân công' }).waitFor();
  check(`GF04 manager assigns ${task.area_name} to a cleaning worker`);
}

async function completeTask(worker, task, result) {
  const page = worker.page;
  const status = result === 'PASS' ? 'Đang thực hiện' : 'Đang thực hiện';
  const card = page.locator('.cleaning-task-card').filter({ hasText: task.area_name }).first();
  await card.waitFor();
  const startResponse = page.waitForResponse(response => response.url().includes(`/api/v1/cleaning/tasks/${task.id}/start`) && response.request().method() === 'POST');
  await card.getByRole('button', { name: 'Bắt đầu', exact: true }).click();
  assert.equal((await startResponse).status(), 200);
  await card.locator('.status-badge').filter({ hasText: status }).waitFor();
  check(`GF04 worker starts ${task.area_name}`);

  const results = result === 'FAIL' ? ['FAIL', 'PASS'] : ['PASS', 'PASS'];
  const checklist = card.locator('select[aria-label^="Kết quả "]');
  assert.equal(await checklist.count(), results.length);
  for (let index = 0; index < results.length; index += 1) {
    const patchResponse = page.waitForResponse(response => response.url().includes('/checklist/') && response.request().method() === 'PATCH');
    await card.locator('select[aria-label^="Kết quả "]').nth(index).selectOption(results[index]);
    assert.equal((await patchResponse).status(), 200);
    await page.waitForTimeout(250);
  }
  check(`GF04 worker records ${result === 'FAIL' ? 'a failed and a passed' : 'all passed'} checklist`, true);

  const submitResponse = page.waitForResponse(response => response.url().includes(`/api/v1/cleaning/tasks/${task.id}/submit`) && response.request().method() === 'POST');
  await card.getByRole('button', { name: 'Nộp kết quả', exact: true }).click();
  const submitted = await submitResponse;
  assert.equal(submitted.status(), 200);
  await page.waitForTimeout(300);
  if (result === 'PASS') await card.locator('.status-badge').filter({ hasText: 'Chờ nghiệm thu' }).waitFor();
  else await card.locator('.status-badge').filter({ hasText: 'Cần làm lại' }).waitFor();
  check(`GF04 worker submits the ${result === 'PASS' ? 'passing' : 'failing'} cleaning path`);
  return card;
}

(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const opened = [];
  try {
    const manager = await openRole(browser, 'director_west'); opened.push(manager.context);
    const passShift = await createShift(manager, 1, 2);
    const passTask = passShift.tasks[0];
    await assignTask(manager, passTask);
    await manager.context.close(); opened.splice(opened.indexOf(manager.context), 1);

    const workerPass = await openRole(browser, 'cleaning_west'); opened.push(workerPass.context);
    await completeTask(workerPass, passTask, 'PASS');
    await workerPass.page.screenshot({ path: path.join(evidenceDir, 'gf04-worker-passed.png'), fullPage: true });
    await workerPass.context.close(); opened.splice(opened.indexOf(workerPass.context), 1);

    const acceptor = await openRole(browser, 'director_west'); opened.push(acceptor.context);
    const acceptedCard = acceptor.page.locator('.cleaning-task-card').filter({ hasText: passTask.area_name }).first();
    const acceptResponse = acceptor.page.waitForResponse(response => response.url().includes(`/api/v1/cleaning/tasks/${passTask.id}/accept`) && response.request().method() === 'POST');
    await acceptedCard.getByRole('button', { name: 'Nghiệm thu', exact: true }).click();
    const response = await acceptResponse;
    assert.equal(response.status(), 200);
    await acceptedCard.locator('.status-badge').filter({ hasText: 'Đã nghiệm thu' }).waitFor();
    check('GF04 manager accepts the passing cleaning task');
    await acceptor.page.screenshot({ path: path.join(evidenceDir, 'gf04-manager-accepted.png'), fullPage: true });

    const failShift = await createShift(acceptor, 3, 4);
    const failTask = failShift.tasks[0];
    await assignTask(acceptor, failTask);
    await acceptor.context.close(); opened.splice(opened.indexOf(acceptor.context), 1);

    const workerFail = await openRole(browser, 'cleaning_west'); opened.push(workerFail.context);
    const failCard = await completeTask(workerFail, failTask, 'FAIL');
    await failCard.locator('.cleaning-rework-note').getByText('Đã tạo Work Order và Case làm lại', { exact: false }).waitFor();
    check('GF04 failed checklist creates a visible rework Work Order and Case');
    await workerFail.page.screenshot({ path: path.join(evidenceDir, 'gf04-worker-rework.png'), fullPage: true });

    check('GF04 browser has no page errors', errors.length === 0);
    check('GF04 API calls have no failed responses', apiFailures.length === 0);
    fs.writeFileSync(path.join(evidenceDir, 'gf04-real-browser.json'), JSON.stringify({ flow: 'GF-04', checks, errors, apiFailures }, null, 2));
    console.log(`REAL_BROWSER_GF04 PASS (${checks.length} checks)`);
  } finally {
    await Promise.all(opened.map(context => context.close().catch(() => {})));
    await browser.close();
  }
})().catch(error => { console.error(`REAL_BROWSER_GF04_FAILED: ${error.message}`); process.exitCode = 1; });
