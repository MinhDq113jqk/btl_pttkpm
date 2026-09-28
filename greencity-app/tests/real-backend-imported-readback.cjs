/**
 * Post-restart browser and API readback of the imported synthetic pack.
 * This exercises imported synthetic records and same-tenant mutations after restart.
 */
const assert = require('node:assert/strict');
const { randomUUID } = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const baseUrl = process.env.REAL_BROWSER_BASE_URL;
const backendUrl = process.env.REAL_BROWSER_BACKEND_URL;
const credentialsFile = process.env.REAL_BROWSER_IMPORTED_CREDENTIALS_FILE;
const targetsFile = process.env.REAL_BROWSER_IMPORTED_TARGETS_FILE;
const evidenceDir = process.env.REAL_BROWSER_EVIDENCE_DIR;
if (![baseUrl, backendUrl, credentialsFile, targetsFile, evidenceDir].every(Boolean)) {
  throw new Error('Real-backend imported readback environment is incomplete');
}
const credentials = JSON.parse(fs.readFileSync(credentialsFile, 'utf8'));
const residentLinksFile = process.env.REAL_BROWSER_SYNTHETIC_RESIDENT_LINKS_FILE;
if (!residentLinksFile) throw new Error('Synthetic resident sidecar is required');
const residentSidecar = JSON.parse(fs.readFileSync(residentLinksFile, 'utf8'));
if (residentSidecar.classification !== 'SYNTHETIC_TEST_ONLY') {
  throw new Error('Resident identity sidecar must be synthetic test data');
}
const importedRole = role => {
  const matches = Object.keys(credentials).filter(name => name.startsWith(`syn_${role}_`));
  if (['technician', 'cleaning', 'security'].includes(role)) {
    assert.ok(matches.length >= 1, `Expected an imported ${role} account`);
  }
  else assert.equal(matches.length, 1, `Expected one imported ${role} account`);
  return matches[0];
};
const actorNames = {
  techlead_west: importedRole('technical_lead'),
  technician_west: importedRole('technician'),
  director_west: importedRole('director'),
  cskh_west: importedRole('cskh'),
  accountant_west: importedRole('accountant'),
  cleaning_west: importedRole('cleaning'),
  security_west: importedRole('security'),
};
const targets = JSON.parse(fs.readFileSync(targetsFile, 'utf8'));
const checks = [];
const counts = {};
const findings = [];
const pageErrors = [];
const sessions = new Map();
const check = (name, condition) => {
  assert.ok(condition, name);
  checks.push(name);
  console.log(`PASS ${name}`);
};
const imported = (type) => new Set(targets.references[type] || []);
const dbIds = (type) => new Set(targets.finance[type] || []);
const intersect = (items, ids) => items.filter(item => ids.has(item.id));

async function loginApi(username) {
  const actualUsername = actorNames[username] || username;
  const fixture = credentials[actualUsername];
  assert.ok(fixture?.initial_password && fixture?.new_password, 'Credential fixture is incomplete');
  let password = fixture.initial_password;
  const login = async candidate => {
    const response = await fetch(`${backendUrl}/api/v1/auth/login`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: actualUsername, password: candidate }),
    });
    assert.equal(response.status, 200, `API login failed for ${username}`);
    return response.json();
  };
  let session = await login(password);
  if (session.user.must_change_password) {
    const change = await fetch(`${backendUrl}/api/v1/auth/change-password`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${session.access_token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ current_password: password, new_password: fixture.new_password }),
    });
    assert.equal(change.status, 204, `First-login password change failed for ${username}`);
    password = fixture.new_password;
    session = await login(password);
  }
  const me = await fetch(`${backendUrl}/api/v1/auth/me`, {
    headers: { Authorization: `Bearer ${session.access_token}` },
  });
  assert.equal(me.status, 200, `/auth/me failed for ${username}`);
  const user = await me.json();
  assert.equal(user.must_change_password, false);
  sessions.set(username, { token: session.access_token, password, user, actualUsername });
  return sessions.get(username);
}

async function api(username, route) {
  const session = sessions.get(username);
  assert.ok(session, `Missing authenticated session for ${username}`);
  const response = await fetch(`${backendUrl}/api/v1${route}`, {
    headers: { Authorization: `Bearer ${session.token}` },
  });
  assert.equal(response.status, 200, `${username} GET ${route} failed`);
  return response.json();
}

async function apiCommand(username, method, route, body, expectedStatus = 200, key = randomUUID()) {
  const session = sessions.get(username);
  const response = await fetch(`${backendUrl}/api/v1${route}`, {
    method,
    headers: { Authorization: `Bearer ${session.token}`, 'Content-Type': 'application/json',
      'Idempotency-Key': key },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  assert.equal(response.status, expectedStatus, `${username} ${method} ${route} failed`);
  return response.json();
}

const apiPost = (username, route, body, key) => apiCommand(username, 'POST', route, body, 200, key);
const atHours = hours => new Date(Date.now() + hours * 3_600_000).toISOString();

async function openRole(browser, username, menu, heading) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'vi-VN' });
  const page = await context.newPage();
  page.on('pageerror', error => pageErrors.push(`${username}: ${error.message}`));
  await page.goto(`${baseUrl}/`, { waitUntil: 'domcontentloaded' });
  await page.locator('#staff-username').fill(sessions.get(username).actualUsername);
  await page.locator('#staff-password').fill(sessions.get(username).password);
  await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
  await page.locator('.desktop-shell').waitFor({ timeout: 20000 });
  if (menu) {
    await page.getByRole('navigation', { name: 'Điều hướng chính' })
      .getByRole('button', { name: menu, exact: true }).click();
  }
  if (heading) await page.getByRole('heading', { name: heading, exact: true }).waitFor();
  return { context, page };
}

async function openResident(browser, username) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'vi-VN' });
  const page = await context.newPage();
  page.on('pageerror', error => pageErrors.push(`${username}: ${error.message}`));
  await page.goto(`${baseUrl}/`, { waitUntil: 'domcontentloaded' });
  await page.locator('#staff-username').fill(sessions.get(username).actualUsername);
  await page.locator('#staff-password').fill(sessions.get(username).password);
  await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
  await page.getByRole('tab', { name: 'Công nợ & hóa đơn', exact: true }).waitFor({ timeout: 20000 });
  return { context, page };
}

async function gf03(browser) {
  const buildings = await api('techlead_west', '/maintenance/buildings');
  check('GF03 imported DB exposes a scoped maintenance building', buildings.length > 0);
  let match;
  for (const building of buildings) {
    const assets = await api('techlead_west', `/maintenance/assets?building_id=${building.id}`);
    const occurrences = await api('techlead_west', `/maintenance/occurrences?building_id=${building.id}`);
    const sourceAsset = intersect(assets, imported('Asset'))
      .find(asset => occurrences.items.some(item => item.asset_id === asset.id));
    if (sourceAsset) { match = { building, asset: sourceAsset, occurrences }; break; }
  }
  check('GF03 imported Asset and linked occurrence are visible through the live API', Boolean(match));
  const plans = await api('techlead_west', `/maintenance/assets/${match.asset.id}/plans`);
  const historyBefore = await api('techlead_west', `/assets/${match.asset.id}/maintenance-history`);
  check('GF03 imported Asset has a persisted plan and linked occurrence',
    plans.length > 0 && match.occurrences.items.some(item => item.asset_id === match.asset.id));
  const occurrence = match.occurrences.items.find(item => item.asset_id === match.asset.id && item.work_order_id);
  check('GF03 imported occurrence retains its Work Order link', Boolean(occurrence));
  const schedulerBody = { as_of: new Date().toISOString() };
  const schedulerKey = randomUUID();
  const firstRun = await apiPost('techlead_west', '/maintenance/scheduler/run', schedulerBody, schedulerKey);
  const replayRun = await apiPost('techlead_west', '/maintenance/scheduler/run', schedulerBody, schedulerKey);
  const freshRun = await apiPost('techlead_west', '/maintenance/scheduler/run', schedulerBody, randomUUID());
  const afterScheduler = await api('techlead_west', `/maintenance/occurrences?building_id=${match.building.id}`);
  check('GF03 scheduler same-key retry returns its original result',
    JSON.stringify(firstRun) === JSON.stringify(replayRun));
  check('GF03 scheduler fresh-key rerun preserves occurrence and Work Order identity',
    JSON.stringify(firstRun) === JSON.stringify(replayRun)
    && freshRun.items.some(item => item.occurrence_id === occurrence.id
      && item.work_order_id === occurrence.work_order_id && item.replayed)
    && afterScheduler.items.length === match.occurrences.items.length
    && afterScheduler.items.some(item => item.id === occurrence.id && item.work_order_id === occurrence.work_order_id));
  const { context, page } = await openRole(browser, 'techlead_west', 'Kỹ thuật & Bảo trì', 'Kỹ thuật & Bảo trì');
  try {
    await page.getByLabel('Tòa nhà').selectOption(match.building.id);
    await page.locator('.maintenance-asset').filter({ hasText: match.asset.code }).waitFor();
    check('GF03 browser renders the imported Asset from PostgreSQL', true);
    const row = page.locator('.maintenance-occurrence-row').filter({ hasText: occurrence.id.slice(0, 8) });
    await row.getByRole('button', { name: 'Mở Work Order' }).click();
    const workOrderCode = (await page.locator('.maintenance-work-detail h3').innerText()).split(' · ')[0];
    await page.getByLabel('Giao cho kỹ thuật viên').selectOption(sessions.get('technician_west').user.account_id);
    const assign = page.waitForResponse(response => response.url().includes(`/work-orders/${occurrence.work_order_id}/assign`)
      && response.request().method() === 'POST');
    await page.getByRole('button', { name: 'Phân công', exact: true }).click();
    check('GF03 assignment reaches the real backend', (await assign).status() === 200);
    await page.getByText('Đã phân công Work Order.', { exact: true }).waitFor();
    check('GF03 imported Work Order is assigned by its technical lead through the browser', true);

    const technician = await openRole(browser, 'technician_west', 'Kỹ thuật & Bảo trì', 'Bảo trì của tôi');
    try {
      const card = technician.page.locator('.maintenance-work-card').filter({ hasText: workOrderCode });
      await card.getByRole('button', { name: 'Mở Work Order' }).click();
      const start = technician.page.waitForResponse(response => response.url().includes(`/work-orders/${occurrence.work_order_id}/start`)
        && response.request().method() === 'POST');
      await technician.page.getByRole('button', { name: 'Bắt đầu xử lý' }).click();
      check('GF03 technician start reaches the real backend', (await start).status() === 200);
      await technician.page.getByText('Đã bắt đầu xử lý.', { exact: true }).waitFor();
      const checklist = technician.page.locator('.workflow-checklist-row');
      const totalChecklist = await checklist.count();
      check('GF03 imported Work Order has a structured checklist', totalChecklist > 0);
      for (let index = 0; index < totalChecklist; index += 1) {
        const item = technician.page.locator('.workflow-checklist-row').nth(index);
        await item.getByRole('textbox').fill(`Synthetic maintenance check ${index + 1}.`);
        const update = technician.page.waitForResponse(response => response.url().includes(`/work-orders/${occurrence.work_order_id}/checklist/`)
          && response.request().method() === 'PATCH');
        await item.locator('input[type="checkbox"]').click();
        check(`GF03 checklist item ${index + 1} is persisted`, (await update).status() === 200);
        await technician.page.getByText('Đã lưu checklist.', { exact: true }).waitFor();
      }
      const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=', 'base64');
      const upload = technician.page.waitForResponse(response => response.url().includes('/evidence')
        && response.request().method() === 'POST');
      await technician.page.locator('.workflow-file-button input').setInputFiles({
        name: 'synthetic-maintenance.png', mimeType: 'image/png', buffer: png,
      });
      check('GF03 technician uploads synthetic image evidence', (await upload).status() === 201);
      await technician.page.getByLabel('Kết quả xử lý').fill('Synthetic maintenance completed.');
      const submit = technician.page.waitForResponse(response => response.url().includes(`/work-orders/${occurrence.work_order_id}/submit`)
        && response.request().method() === 'POST');
      await technician.page.getByRole('button', { name: 'Gửi nghiệm thu' }).click();
      check('GF03 technician submit reaches the real backend', (await submit).status() === 200);
      await technician.page.getByText('Đã gửi Work Order nghiệm thu.', { exact: true }).waitFor();
      check('GF03 technician submits the persisted Work Order for acceptance', true);
    } finally { await technician.context.close(); }

    const acceptor = await openRole(browser, 'techlead_west', 'Kỹ thuật & Bảo trì', 'Kỹ thuật & Bảo trì');
    try {
      await acceptor.page.getByLabel('Tòa nhà').selectOption(match.building.id);
      const acceptedRow = acceptor.page.locator('.maintenance-occurrence-row').filter({ hasText: occurrence.id.slice(0, 8) });
      await acceptedRow.getByRole('button', { name: 'Mở Work Order' }).click();
      const accept = acceptor.page.waitForResponse(response => response.url().includes(`/work-orders/${occurrence.work_order_id}/accept`)
        && response.request().method() === 'POST');
      await acceptor.page.getByRole('button', { name: 'Nghiệm thu kỹ thuật' }).click();
      check('GF03 technical acceptance reaches the real backend', (await accept).status() === 200);
      await acceptor.page.getByText('Đã nghiệm thu kỹ thuật.', { exact: true }).waitFor();
      await acceptor.page.locator('.maintenance-asset').filter({ hasText: match.asset.code }).click();
      await acceptor.page.locator('.maintenance-history-row').first().waitFor();
      check('GF03 acceptance produces visible Asset history in the browser', true);
      await acceptor.page.reload({ waitUntil: 'domcontentloaded' });
      await acceptor.page.getByRole('heading', { name: 'Đăng nhập GreenCity' }).waitFor();
      await acceptor.page.locator('#staff-username').fill(sessions.get('techlead_west').actualUsername);
      await acceptor.page.locator('#staff-password').fill(sessions.get('techlead_west').password);
      await acceptor.page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
      await acceptor.page.getByRole('navigation', { name: 'Điều hướng chính' })
        .getByRole('button', { name: 'Kỹ thuật & Bảo trì', exact: true }).click();
      await acceptor.page.getByLabel('Tòa nhà').selectOption(match.building.id);
      await acceptor.page.locator('.maintenance-asset').filter({ hasText: match.asset.code }).click();
      await acceptor.page.locator('.maintenance-history-row').first().waitFor();
      check('GF03 accepted history survives browser reload and re-authentication', true);
    } finally { await acceptor.context.close(); }
    const historyAfter = await api('techlead_west', `/assets/${match.asset.id}/maintenance-history`);
    check('GF03 history links the same imported Asset, occurrence and Work Order',
      historyAfter.items.length === historyBefore.items.length + 1
      && historyAfter.items.some(item => item.asset_id === match.asset.id
        && item.occurrence_id === occurrence.id && item.work_order_id === occurrence.work_order_id));
    counts.GF03 = { plans: plans.length, occurrences: afterScheduler.items.length,
      historyBefore: historyBefore.items.length, historyAfter: historyAfter.items.length };
  } finally { await context.close(); }
}

async function gf04(browser) {
  const response = await api('director_west', '/cleaning/tasks');
  const shiftIds = imported('CleaningShift');
  const sourceTasks = response.items.filter(item => shiftIds.has(item.shift_id));
  check('GF04 imported cleaning shift tasks are visible through the live API', sourceTasks.length > 0);
  check('GF04 imported cleaning task checklist and state survived restart',
    sourceTasks.every(item => item.status && Array.isArray(item.checklist) && item.checklist.length > 0));
  const sourceRoute = sourceTasks[0].route_id;
  const routes = await api('director_west', '/cleaning/routes');
  check('GF04 imported task route is a live, scoped route',
    routes.some(item => item.id === sourceRoute));
  const assignees = await api('director_west', `/cleaning/assignees?building_id=${sourceTasks[0].building_id}`);
  const cleaner = sessions.get('cleaning_west').user.account_id;
  check('GF04 imported cleaning account can be assigned at the source building',
    assignees.some(item => item.id === cleaner));
  const shift = await apiCommand('director_west', 'POST', '/cleaning/shifts', {
    route_id: sourceRoute, scheduled_start_at: atHours(1), scheduled_end_at: atHours(2),
  }, 201);
  check('GF04 source route produces a new snapshotted task on imported data',
    shift.tasks.length > 0 && shift.tasks.every(item => item.route_id === sourceRoute));
  let task = shift.tasks[0];
  task = await apiPost('director_west', `/cleaning/tasks/${task.id}/assign`,
    { expected_version: task.version, assignee_id: cleaner });
  task = await apiPost('cleaning_west', `/cleaning/tasks/${task.id}/start`,
    { expected_version: task.version });
  for (const item of task.checklist) {
    task = await apiCommand('cleaning_west', 'PATCH',
      `/cleaning/tasks/${task.id}/checklist/${item.id}`,
      { expected_version: item.version, result: 'PASS', note: 'Synthetic checklist result.' });
  }
  task = await apiPost('cleaning_west', `/cleaning/tasks/${task.id}/submit`,
    { expected_version: task.version });
  check('GF04 imported route supports assign, start, checklist and submit',
    task.status === 'SUBMITTED' && task.checklist.every(item => item.result === 'PASS'));
  task = await apiPost('director_west', `/cleaning/tasks/${task.id}/accept`,
    { expected_version: task.version });
  const accepted = await api('director_west', `/cleaning/tasks/${task.id}`);
  check('GF04 synthetic task acceptance persists on the same PostgreSQL backend',
    task.status === 'ACCEPTED' && accepted.status === 'ACCEPTED');
  const failedShift = await apiCommand('director_west', 'POST', '/cleaning/shifts', {
    route_id: sourceRoute, scheduled_start_at: atHours(3), scheduled_end_at: atHours(4),
  }, 201);
  let failedTask = failedShift.tasks[0];
  failedTask = await apiPost('director_west', `/cleaning/tasks/${failedTask.id}/assign`,
    { expected_version: failedTask.version, assignee_id: cleaner });
  failedTask = await apiPost('cleaning_west', `/cleaning/tasks/${failedTask.id}/start`,
    { expected_version: failedTask.version });
  for (const [index, item] of failedTask.checklist.entries()) {
    failedTask = await apiCommand('cleaning_west', 'PATCH',
      `/cleaning/tasks/${failedTask.id}/checklist/${item.id}`,
      { expected_version: item.version, result: index === 0 ? 'FAIL' : 'PASS',
        note: 'Synthetic failed checklist branch.' });
  }
  failedTask = await apiPost('cleaning_west', `/cleaning/tasks/${failedTask.id}/submit`,
    { expected_version: failedTask.version });
  const persistedFailed = await api('director_west', `/cleaning/tasks/${failedTask.id}`);
  check('GF04 failed checklist creates a persisted rework Work Order and Case',
    failedTask.status === 'REWORK_REQUIRED' && Boolean(failedTask.rework_work_order_id)
    && Boolean(failedTask.rework_case_id)
    && persistedFailed.rework_work_order_id === failedTask.rework_work_order_id);
  counts.GF04 = { tasks: sourceTasks.length, rework: sourceTasks.filter(item => item.status === 'REWORK_REQUIRED').length };
  const { context, page } = await openRole(browser, 'director_west', 'Vệ sinh môi trường', 'Điều phối ca vệ sinh');
  try {
    await page.locator('.cleaning-task-card').filter({ hasText: sourceTasks[0].area_name }).first().waitFor();
    check('GF04 browser renders an imported cleaning task from PostgreSQL', true);
    await page.locator('.cleaning-task-card').filter({ hasText: task.area_name })
      .filter({ hasText: 'Đã nghiệm thu' }).first().waitFor();
    check('GF04 browser renders the accepted same-tenant task', true);
    await page.locator('.cleaning-task-card').filter({ hasText: failedTask.area_name })
      .filter({ hasText: 'Cần làm lại' }).first().waitFor();
    check('GF04 browser renders rework from a synthetic failed checklist', true);
  } finally { await context.close(); }
}

async function gf05(browser) {
  const shifts = await api('director_west', '/security/shifts');
  const dashboard = await api('director_west', '/security/dashboard');
  const sourceShifts = intersect(shifts.items, imported('SecurityShift'));
  const sourceIncidents = intersect(dashboard.incidents, imported('SecurityIncident'));
  check('GF05 imported security shifts are visible through the live API', sourceShifts.length > 0);
  const asOf = encodeURIComponent(new Date().toISOString());
  const incidentDrill = await api('director_west', `/dashboard/drill-down/open_incidents?as_of=${asOf}`);
  const sourceDrillRows = incidentDrill.items.filter(item => imported('SecurityIncident').has(item.resource_id));
  check('GF05 imported open incidents are persisted and visible in executive drill-down', sourceDrillRows.length > 0);
  check('GF05 security dashboard returns complete incident objects when visible',
    sourceIncidents.every(item => item.status && Array.isArray(item.escalations) && Array.isArray(item.evidence)));
  if (sourceIncidents.length === 0) findings.push('GF05_IMPORTED_INCIDENTS_NOT_IN_SECURITY_DASHBOARD');
  const sourceBuilding = sourceShifts[0].building_id;
  const patrolPoints = await api('director_west', `/security/patrol-points?building_id=${sourceBuilding}`);
  const assignees = await api('director_west', `/security/assignees?building_id=${sourceBuilding}`);
  const guard = sessions.get('security_west').user.account_id;
  check('GF05 imported building has a scoped patrol point and security account',
    patrolPoints.length > 0 && assignees.some(item => item.id === guard));
  let shift = await apiCommand('director_west', 'POST', '/security/shifts', {
    building_id: sourceBuilding, assignee_id: guard,
    scheduled_start_at: atHours(3), scheduled_end_at: atHours(5),
    patrol_windows: [{ patrol_point_id: patrolPoints[0].id,
      window_start_at: atHours(3.5), window_end_at: atHours(4.5) }],
  }, 201);
  shift = await apiPost('security_west', `/security/shifts/${shift.id}/start`,
    { expected_version: shift.version });
  let window = shift.patrol_windows[0];
  window = await apiCommand('security_west', 'POST', `/security/patrol-windows/${window.id}/logs`,
    { event_type: 'CHECK_IN', note: 'Synthetic patrol check-in.', occurred_at: new Date().toISOString() }, 201);
  check('GF05 imported building supports shift start and patrol check-in',
    shift.status === 'IN_PROGRESS' && window.logs.some(item => item.event_type === 'CHECK_IN'));
  let incident = await apiCommand('security_west', 'POST', '/security/incidents', {
    patrol_window_id: window.id, incident_type: 'SECURITY', severity: 'HIGH',
    title: 'Synthetic security incident', description: 'Controlled synthetic incident for imported site.',
    occurred_at: new Date().toISOString(),
  }, 201);
  check('GF05 synthetic high incident opens both escalation roles',
    incident.escalations.length === 2 && incident.status === 'NEW');
  incident = await apiCommand('security_west', 'POST', `/security/incidents/${incident.id}/evidence`,
    { evidence_type: 'NOTE', description: 'Synthetic incident review evidence.' }, 201);
  for (const status of ['TRIAGED', 'IN_PROGRESS', 'RESOLVED']) {
    incident = await apiPost('security_west', `/security/incidents/${incident.id}/transition`,
      { expected_version: incident.version, status });
  }
  for (const escalation of incident.escalations) {
    incident = await apiCommand(escalation.target_role === 'director' ? 'director_west' : 'security_west',
      'POST', `/security/incidents/${incident.id}/escalations/${escalation.id}/acknowledgements`,
      { note: 'Synthetic acknowledgement.' }, 201);
  }
  check('GF05 both escalation acknowledgements are attributed to their roles',
    incident.escalations.every(item => Boolean(item.acknowledgement?.acknowledged_by_id)));
  incident = await apiPost('director_west', `/security/incidents/${incident.id}/transition`,
    { expected_version: incident.version, status: 'CLOSED', conclusion: 'Synthetic issue resolved.' });
  const persistedShift = await api('security_west', `/security/shifts/${shift.id}`);
  const persistedIncident = (await api('director_west', '/security/dashboard')).incidents
    .find(item => item.id === incident.id);
  check('GF05 synthetic incident closure and patrol state persist in PostgreSQL',
    incident.status === 'CLOSED' && persistedShift.status === 'IN_PROGRESS'
    && persistedIncident?.status === 'CLOSED');
  const incidentAudit = await api('director_west',
    `/audit-events?resource_type=SecurityIncident&resource_id=${incident.id}`);
  check('GF05 high incident retains a scoped audit timeline',
    incidentAudit.items.some(item => item.event_type === 'SecurityIncidentCreated')
    && incidentAudit.items.some(item => item.event_type === 'SecurityIncidentTransitioned'));
  const unrelatedRole = await fetch(`${backendUrl}/api/v1/security/dashboard`, {
    headers: { Authorization: `Bearer ${sessions.get('cskh_west').token}` },
  });
  check('GF05 unrelated CSKH role cannot read the security dashboard',
    unrelatedRole.status === 403);
  counts.GF05 = { shifts: sourceShifts.length, securityDashboardIncidents: sourceIncidents.length,
    executiveDrillIncidents: sourceDrillRows.length };
  const { context, page } = await openRole(browser, 'director_west', 'An ninh & Tuần tra', 'Điều phối an ninh và tuần tra');
  try {
    await page.locator('.security-shift-card').first().waitFor();
    check('GF05 browser renders security shifts from the live backend', true);
    await page.locator('.security-incidents article').filter({ hasText: incident.code }).waitFor();
    check('GF05 browser renders the synthetic closed incident on imported site', true);
    if (sourceIncidents.length) {
      await page.locator('.security-incidents article').filter({ hasText: sourceIncidents[0].code }).waitFor();
      check('GF05 browser renders an imported incident from PostgreSQL', true);
    }
  } finally { await context.close(); }
}

async function gf06(browser) {
  const list = await api('cskh_west', '/parcels?page_size=100');
  const sourceParcels = intersect(list.items, imported('Parcel'));
  check('GF06 imported parcels are visible through the live API', sourceParcels.length > 0);
  const parcel = await api('cskh_west', `/parcels/${sourceParcels[0].id}`);
  const timeline = await api('cskh_west', `/parcels/${parcel.id}/timeline`);
  check('GF06 parcel status and audit timeline survived restart',
    parcel.status && Array.isArray(timeline.items) && timeline.items.length > 0);
  check('GF06 parcel API does not return a plaintext PIN',
    !Object.keys(parcel).some(key => ['pin', 'pin_value', 'pin_hash'].includes(key)));
  const pin = randomUUID().replace(/-/g, '').slice(0, 12);
  let handover = await apiCommand('cskh_west', 'POST', '/parcels', {
    building_id: parcel.building_id, unit_id: parcel.unit_id,
    parcel_code: `SYN-GF06-${randomUUID().slice(0, 12)}`,
    recipient_name_snapshot: 'Synthetic recipient',
    storage_location: 'Synthetic test shelf', pin,
  }, 201);
  handover = await apiPost('cskh_west', `/parcels/${handover.id}/ready`,
    { expected_version: handover.version });
  handover = await apiPost('cskh_west', `/parcels/${handover.id}/handover`,
    { expected_version: handover.version, pin });
  check('GF06 imported building and unit support intake, ready and PIN handover',
    handover.status === 'HANDED_OVER' && !Object.keys(handover).some(key => key.includes('pin_hash')));
  const parcelCase = await apiCommand('cskh_west', 'POST', `/parcels/${handover.id}/case`,
    { reason: 'Synthetic handover reconciliation.' }, 201);
  const handoverTimeline = await api('cskh_west', `/parcels/${handover.id}/timeline`);
  check('GF06 synthetic handover opens a shared Case and persisted audit timeline',
    parcelCase.source_parcel_id === handover.id && handoverTimeline.items.length >= 4);
  const secondPin = randomUUID().replace(/-/g, '').slice(0, 12);
  let exception = await apiCommand('cskh_west', 'POST', '/parcels', {
    building_id: parcel.building_id, unit_id: parcel.unit_id,
    parcel_code: `SYN-GF06-EX-${randomUUID().slice(0, 10)}`,
    recipient_name_snapshot: 'Synthetic exception recipient',
    storage_location: 'Synthetic exception shelf', pin: secondPin,
  }, 201);
  const readyKey = randomUUID();
  const readyBody = { expected_version: exception.version };
  exception = await apiCommand('cskh_west', 'POST', `/parcels/${exception.id}/ready`,
    readyBody, 200, readyKey);
  const readyReplay = await apiCommand('cskh_west', 'POST', `/parcels/${exception.id}/ready`,
    readyBody, 200, readyKey);
  check('GF06 same-key ready retry preserves the same imported-unit parcel',
    readyReplay.id === exception.id && readyReplay.version === exception.version);
  await apiCommand('cskh_west', 'POST', `/parcels/${exception.id}/handover`,
    { expected_version: exception.version, pin: `${secondPin}invalid` }, 403);
  exception = await api('cskh_west', `/parcels/${exception.id}`);
  check('GF06 wrong PIN is rejected and records one attempt without handover',
    exception.status === 'READY_FOR_PICKUP' && exception.pin_attempt_count === 1);
  exception = await apiPost('cskh_west', `/parcels/${exception.id}/exception`,
    { expected_version: exception.version, status: 'LOST', reason: 'Synthetic missing parcel.' });
  check('GF06 synthetic exception persists its terminal state and reason',
    exception.status === 'LOST' && exception.exception_reason === 'Synthetic missing parcel.');
  counts.GF06 = { parcels: sourceParcels.length, timeline: timeline.items.length };
  const { context, page } = await openRole(browser, 'cskh_west', 'Bưu phẩm & Bàn giao', 'Tiếp nhận và bàn giao bưu phẩm');
  try {
    await page.getByText(parcel.parcel_code, { exact: true }).first().waitFor();
    check('GF06 browser renders an imported parcel from PostgreSQL', true);
    await page.getByText(handover.parcel_code, { exact: true }).first().waitFor();
    check('GF06 browser renders the new handed-over parcel on the imported unit', true);
    await page.getByText(exception.parcel_code, { exact: true }).first().waitFor();
    check('GF06 browser renders the synthetic exception on imported unit', true);
  } finally { await context.close(); }
}

async function gf07(browser) {
  const routes = [
    ['fee_policies', '/billing/fee-policies'], ['periods', '/billing/periods'],
    ['invoices', '/billing/invoices'], ['payments', '/billing/payments'],
    ['unmatched', '/billing/unmatched-payments'], ['credits', '/billing/overpayment-credits'],
  ];
  const live = {};
  for (const [kind, route] of routes) {
    const response = await api('accountant_west', route);
    live[kind] = intersect(response.items, dbIds(kind));
  }
  check('GF07 imported finance records survive restart and are scoped to the accountant',
    routes.every(([kind]) => dbIds(kind).size > 0 && live[kind].length > 0));
  check('GF07 invoice snapshots and balances are internally valid',
    live.invoices.every(item => item.total_vnd > 0 && item.outstanding_vnd >= 0
      && item.outstanding_vnd <= item.total_vnd && Array.isArray(item.items) && item.items.length > 0));
  const accounts = (await api('accountant_west', '/billing/accounts')).items;
  const mappedAccounts = new Set(residentSidecar.links.map(item => item.billing_account_number));
  const invoice = live.invoices.find(item => item.outstanding_vnd > 0
    && accounts.some(account => account.id === item.billing_account_id
      && mappedAccounts.has(account.account_number)));
  const period = live.periods.find(item => item.id === invoice?.accounting_period_id);
  const account = accounts.find(item => item.id === invoice?.billing_account_id);
  const residentLink = residentSidecar.links.find(item => item.billing_account_number === account?.account_number);
  check('GF07 imported outstanding invoice has a live account and open period',
    Boolean(invoice && period?.status === 'OPEN' && account?.status === 'ACTIVE' && residentLink));
  const reference = `SYN-GF07-${randomUUID()}`;
  const paymentBody = {
    billing_account_id: account.id, accounting_period_id: period.id,
    payment_source: 'BANK_TRANSFER', source_reference: reference,
    receipt_number: reference, amount_vnd: invoice.outstanding_vnd + 1000,
    received_at: new Date().toISOString(),
  };
  const paymentKey = randomUUID();
  const payment = await apiCommand('accountant_west', 'POST', '/billing/payments',
    paymentBody, 201, paymentKey);
  const replay = await apiCommand('accountant_west', 'POST', '/billing/payments',
    paymentBody, 201, paymentKey);
  check('GF07 imported account accepts idempotent synthetic receipt',
    payment.status === 'RECEIVED' && replay.id === payment.id);
  const allocated = await apiPost('accountant_west', `/billing/payments/${payment.id}/allocate`);
  const updatedInvoice = await api('accountant_west', `/billing/invoices/${invoice.id}`);
  check('GF07 payment allocates imported invoice and records overpayment credit',
    updatedInvoice.outstanding_vnd === 0
    && allocated.allocations.some(item => item.billing_invoice_id === invoice.id)
    && allocated.overpayment_credit?.original_vnd >= 1000);
  const unmatchedBody = {
    building_id: account.building_id, accounting_period_id: period.id,
    payment_source: 'BANK_TRANSFER', source_reference: `${reference}-U`,
    receipt_number: `${reference}-U`, amount_vnd: 5000, received_at: new Date().toISOString(),
  };
  const unmatchedPayment = await apiCommand('accountant_west', 'POST', '/billing/payments',
    unmatchedBody, 201);
  const unmatchedQueue = await api('accountant_west', '/billing/unmatched-payments');
  const unmatchedRow = unmatchedQueue.items.find(item => item.payment_id === unmatchedPayment.id);
  check('GF07 missing account enters the imported building unmatched queue',
    unmatchedPayment.status === 'UNMATCHED' && unmatchedRow?.status === 'OPEN');
  const matched = await apiPost('accountant_west',
    `/billing/unmatched-payments/${unmatchedRow.id}/match`, { billing_account_id: account.id });
  check('GF07 unmatched receipt matches the same imported account',
    matched.billing_account_id === account.id && matched.status === 'RECEIVED');
  await loginApi(residentLink.username);
  const asOf = new Date().toISOString();
  const cutoffQuery = `?as_of=${encodeURIComponent(asOf)}`;
  const residentInvoices = await api(residentLink.username, `/resident/billing/invoices${cutoffQuery}`);
  const residentPayments = await api(residentLink.username, `/resident/billing/payments${cutoffQuery}`);
  const residentSummary = await api(residentLink.username, `/resident/billing/summary${cutoffQuery}`);
  check('GF07 provisioned synthetic resident reads their imported invoice and new payment',
    residentInvoices.items.some(item => item.id === invoice.id)
    && residentPayments.items.some(item => item.id === payment.id)
    && residentSummary.items.some(item => item.unit_id === account.unit_id)
    && new Date(residentInvoices.as_of).toISOString() === asOf
    && new Date(residentPayments.as_of).toISOString() === asOf
    && new Date(residentSummary.as_of).toISOString() === asOf);
  counts.GF07 = Object.fromEntries(routes.map(([kind]) => [kind, live[kind].length]));
  const { context, page } = await openRole(browser, 'accountant_west', 'Tài chính & Công nợ', 'Thiết lập phí và phát hành hóa đơn');
  try {
    await page.getByText(live.invoices[0].invoice_number, { exact: true }).first().waitFor();
    check('GF07 browser renders a PostgreSQL invoice snapshot', true);
    await page.getByText(payment.receipt_number, { exact: true }).first().waitFor();
    check('GF07 browser renders the synthetic receipt allocated against imported debt', true);
  } finally { await context.close(); }
  const residentBrowser = await openResident(browser, residentLink.username);
  try {
    await residentBrowser.page.getByRole('tab', { name: 'Công nợ & hóa đơn', exact: true }).click();
    await residentBrowser.page.getByText(invoice.invoice_number, { exact: true }).waitFor();
    await residentBrowser.page.getByText(payment.receipt_number, { exact: true }).waitFor();
    check('GF07 imported resident portal renders the same invoice and synthetic payment', true);
    await residentBrowser.page.screenshot({
      path: path.join(evidenceDir, 'gf07-imported-resident-billing.png'), fullPage: true,
    });
  } finally { await residentBrowser.context.close(); }
}

async function gf08(browser) {
  const asOf = new Date().toISOString();
  const query = `?as_of=${encodeURIComponent(asOf)}`;
  const dashboard = await api('director_west', `/dashboard${query}`);
  const metrics = [
    ['sla_overdue', 'sla_overdue_count', 'Yêu cầu CSKH quá hạn SLA'],
    ['maintenance_due', 'maintenance_due_count', 'Bảo trì kỹ thuật đến hạn'],
    ['cleaning_rework', 'cleaning_rework_count', 'Vệ sinh cần làm lại (Rework)'],
    ['open_incidents', 'open_incident_count', 'Sự cố an ninh đang mở'],
    ['ar_debt', 'ar_debt_vnd', 'Tổng công nợ quá hạn (AR)'],
  ];
  const metricDetails = new Map();
  for (const [metric, field] of metrics) {
    const detail = await api('director_west', `/dashboard/drill-down/${metric}${query}`);
    metricDetails.set(metric, detail);
    const value = metric === 'ar_debt'
      ? detail.items.reduce((sum, item) => sum + item.amount_vnd, 0)
      : detail.items.length;
    check(`GF08 ${metric} KPI reconciles to live drill-down rows at one as_of`,
      value === dashboard[field] && new Date(detail.as_of).toISOString() === asOf
      && detail.items.every(item => item.resource_id && item.building_id));
    if (detail.items.length === 0) {
      check(`GF08 ${metric} has an explicit empty drill-down state`, dashboard[field] === 0);
      continue;
    }
    const first = detail.items[0];
    const scoped = await api('director_west',
      `/audit-events?resource_type=${encodeURIComponent(first.resource_type)}&resource_id=${first.resource_id}&as_of=${encodeURIComponent(asOf)}`);
    check(`GF08 ${metric} source-row audit uses the same resource and as_of`,
      Array.isArray(scoped.items) && scoped.items.every(item => item.resource_type === first.resource_type
        && item.resource_id === first.resource_id && new Date(item.created_at).toISOString() <= asOf));
  }
  const audit = await api('director_west', `/audit-events${query}`);
  check('GF08 audit timeline is available from the same scoped backend', Array.isArray(audit.items));
  counts.GF08 = {
    auditEvents: audit.items.length,
    metrics: Object.fromEntries(metrics.map(([metric]) => [metric, {
      rows: metricDetails.get(metric).items.length,
      audit: metricDetails.get(metric).items.length ? 'SCOPED_QUERY' : 'EMPTY_METRIC',
    }])),
  };
  const { context, page } = await openRole(browser, 'director_west', null, null);
  try {
    await page.locator('[aria-label="5 Chỉ số điều hành cốt lõi"] .kpi-card').first().waitFor();
    check('GF08 browser renders all five live dashboard KPIs',
      await page.locator('[aria-label="5 Chỉ số điều hành cốt lõi"] .kpi-card').count() === 5);
    const browserRequests = [];
    const browserAuditRequests = [];
    page.on('request', request => {
      const url = new URL(request.url());
      if (url.pathname.includes('/dashboard/drill-down/')) browserRequests.push(url.searchParams.get('as_of'));
      if (url.pathname.endsWith('/audit-events')) browserAuditRequests.push(Object.fromEntries(url.searchParams.entries()));
    });
    const browserAsOf = await page.locator('.cutoff-iso-badge').getAttribute('title');
    for (const [metric, , title] of metrics) {
      await page.getByRole('button', { name: new RegExp(title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')) }).click();
      await page.locator('.drilldown-dialog').waitFor();
      if (metricDetails.get(metric).items.length > 0) {
        const priorAudits = browserAuditRequests.length;
        await page.getByRole('button', { name: 'Xem lịch sử thay đổi của tài nguyên này' }).first().click();
        await page.locator('.audit-dialog').waitFor();
        check(`GF08 ${metric} browser opens source-row audit at the dashboard cutoff`,
          browserAuditRequests.length === priorAudits + 1
          && browserAuditRequests.at(-1).as_of === browserAsOf
          && Boolean(browserAuditRequests.at(-1).resource_type)
          && Boolean(browserAuditRequests.at(-1).resource_id));
        await page.getByRole('button', { name: 'Đóng cửa sổ kiểm toán', exact: true }).click();
        await page.locator('.audit-dialog').waitFor({ state: 'detached' });
      }
      await page.locator('.drilldown-footer').getByRole('button', { name: 'Đóng', exact: true }).click();
      await page.locator('.drilldown-dialog').waitFor({ state: 'detached' });
    }
    check('GF08 browser requests all five live drill-downs with one as_of',
      browserRequests.length === 5 && browserRequests.every(Boolean)
      && browserRequests.every(value => value === browserAsOf));
  } finally { await context.close(); }
}

async function main() {
  for (const username of ['techlead_west', 'technician_west', 'director_west', 'cskh_west',
    'accountant_west', 'cleaning_west', 'security_west']) {
    await loginApi(username);
  }
  let browser;
  try {
    browser = await chromium.launch({ headless: true, channel: 'msedge' });
  } catch {
    browser = await chromium.launch({ headless: true });
  }
  try {
    await gf03(browser);
    await gf04(browser);
    await gf05(browser);
    await gf06(browser);
    await gf07(browser);
    await gf08(browser);
    check('GF03..08 browser pages have no JavaScript errors', pageErrors.length === 0);
    fs.writeFileSync(path.join(evidenceDir, 'imported-readback.json'),
      JSON.stringify({ classification: 'SYNTHETIC_TEST_ONLY', scope: 'post-restart API and browser readback',
        coverage: {
          GF03: 'imported Asset and Work Order lifecycle through browser, scheduler retry and persisted history',
          GF04: 'imported route task creation, pass acceptance, fail rework and browser readback',
          GF05: 'imported building patrol, high incident ACK/close, audit and browser readback',
          GF06: 'imported unit intake, PIN handover, wrong PIN, exception, retry and browser readback',
          GF07: 'imported invoice payment, credit, unmatched match and resident portal readback after explicit synthetic-only sidecar provisioning',
          GF08: 'five KPI, drill-down and scoped audit chains with one as_of in API and browser',
        }, checks, counts, findings }, null, 2));
    if (findings.length) throw new Error(`Product findings: ${findings.join(',')}`);
    console.log(`REAL_BACKEND_IMPORTED_READBACK PASS GF03_GF08 (${checks.length} checks)`);
  } finally { await browser.close(); }
}

main().catch(error => {
  console.error(`REAL_BACKEND_IMPORTED_READBACK_FAILED: ${error.message}`);
  process.exitCode = 1;
});
