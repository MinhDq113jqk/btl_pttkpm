const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const { randomUUID } = require('node:crypto');

const siteId = randomUUID();
const buildingId = randomUUID();
const pointId = randomUUID();
const directorId = randomUUID();
const securityId = randomUUID();
const shiftId = randomUUID();
const windowId = randomUUID();
const incidentId = randomUUID();
const correlationId = randomUUID();
const tenantId = randomUUID();
const point = { id: pointId, building_id: buildingId, code: 'SEC-A-01', name: 'Sảnh chính', is_active: true };
let window = null;
let shift = null;
let incidents = [];
const errors = [];
const checks = [];
const callMethods = [];
const respond = (payload, status = 200) => ({
  status,
  headers: { 'Content-Type': 'application/json', 'X-Correlation-ID': correlationId },
  body: JSON.stringify(payload),
});
const check = (name, value = true) => { assert.ok(value, name); checks.push(name); console.log(`PASS ${name}`); };

async function openAs(browser, role) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'vi-VN' });
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(`${role}: ${error.message}`));
  await context.route('**/api/v1/**', async route => {
    const request = route.request();
    const url = new URL(request.url());
    const body = (() => { try { return request.postDataJSON?.(); } catch { return null; } })();
    callMethods.push({ path: url.pathname, method: request.method(), body });
    const currentId = role === 'director' ? directorId : securityId;
    const headers = { 'Content-Type': 'application/json', 'X-Correlation-ID': correlationId };
    if (url.pathname.endsWith('/auth/login')) return route.fulfill(respond({ access_token: `token-${role}` }));
    if (url.pathname.endsWith('/auth/me')) return route.fulfill(respond({
      account_id: currentId, tenant_id: tenantId, username: `${role}.security.ux`, full_name: role,
      roles: [role], active_site_id: siteId, must_change_password: false,
      allowed_sites: [{ id: siteId, code: 'CENTRAL', name: 'GreenCity Central' }],
    }));
    if (url.pathname.endsWith('/service-requests')) return route.fulfill(respond({ items: [], page: 1, page_size: 20, total: 0 }));
    if (url.pathname.endsWith('/notifications')) return route.fulfill(respond({ items: [] }));
    if (url.pathname.endsWith('/security/patrol-points')) return route.fulfill(respond([point]));
    if (url.pathname.endsWith('/security/assignees')) return route.fulfill(respond([{ id: securityId, full_name: 'Nhân viên an ninh A' }]));
    if (url.pathname.endsWith('/security/dashboard')) return route.fulfill(respond({ shifts: shift ? [shift] : [], exceptions: [], incidents }));
    if (url.pathname.endsWith('/security/shifts') && request.method() === 'POST') {
      const patrol = body.patrol_windows[0];
      window = {
        id: windowId, security_shift_id: shiftId, patrol_point_id: patrol.patrol_point_id,
        patrol_point_code: point.code, patrol_point_name: point.name, building_id: body.building_id,
        window_start_at: patrol.window_start_at, window_end_at: patrol.window_end_at,
        status: 'SCHEDULED', missed_reason: null, completed_at: null, version: 1, logs: [],
      };
      shift = {
        id: shiftId, tenant_id: tenantId, site_id: siteId, building_id: body.building_id,
        assigned_to_id: body.assignee_id, scheduled_start_at: body.scheduled_start_at,
        scheduled_end_at: body.scheduled_end_at, status: 'PLANNED', version: 1,
        handoffs: [], visitors: [], patrol_windows: [window],
      };
      return route.fulfill(respond(shift, 201));
    }
    if (url.pathname.endsWith('/security/shifts') && request.method() === 'POST') {
      check('shift creation sends the server-issued point and assignee ids', body.building_id === buildingId && body.assignee_id === securityId && body.patrol_windows[0].patrol_point_id === pointId);
      shift.scheduled_start_at = body.scheduled_start_at; shift.scheduled_end_at = body.scheduled_end_at;
      window.window_start_at = body.patrol_windows[0].window_start_at; window.window_end_at = body.patrol_windows[0].window_end_at;
      return route.fulfill(respond(shift, 201));
    }
    if (url.pathname.endsWith(`/security/shifts/${shiftId}/start`)) { shift.status = 'IN_PROGRESS'; shift.version += 1; return route.fulfill(respond(shift)); }
    if (url.pathname.endsWith(`/security/shifts/${shiftId}/handoffs`)) {
      shift.handoffs.push({ id: randomUUID(), received_by_id: body.received_by_id, summary: body.summary, created_at: '2026-09-27T01:05:00Z' });
      return route.fulfill(respond(shift, 201));
    }
    if (url.pathname.endsWith(`/security/shifts/${shiftId}/visitors`)) {
      shift.visitors.push({ id: randomUUID(), visitor_name: body.visitor_name, visit_purpose: body.visit_purpose, checked_in_at: body.checked_in_at });
      return route.fulfill(respond(shift, 201));
    }
    if (url.pathname.endsWith(`/security/patrol-windows/${windowId}/logs`)) {
      window.logs.push({ id: randomUUID(), event_type: body.event_type, occurred_at: body.occurred_at, created_at: body.occurred_at });
      return route.fulfill(respond(window, 201));
    }
    if (url.pathname.endsWith(`/security/patrol-windows/${windowId}/complete`)) {
      window.status = 'COMPLETED'; window.completed_at = '2026-09-27T01:20:00Z'; window.version += 1; return route.fulfill(respond(window));
    }
    if (url.pathname.endsWith(`/security/incidents/${incidentId}/escalations/${directorId}/acknowledgements`)) {
      const incident = incidents[0];
      incident.escalations.find(item => item.target_role === 'director').acknowledgement = { id: randomUUID(), acknowledged_by_id: directorId, note: body.note, created_at: '2026-09-27T01:30:00Z' };
      incident.version += 1; return route.fulfill(respond(incident, 201));
    }
    if (url.pathname.endsWith(`/security/incidents/${incidentId}/escalations/${securityId}/acknowledgements`)) {
      const incident = incidents[0];
      incident.escalations.find(item => item.target_role === 'security').acknowledgement = { id: randomUUID(), acknowledged_by_id: securityId, note: body.note, created_at: '2026-09-27T01:40:00Z' };
      incident.version += 1; return route.fulfill(respond(incident, 201));
    }
    if (url.pathname.endsWith('/security/incidents') && request.method() === 'POST') {
      incidents = [{
        id: incidentId, patrol_window_id: body.patrol_window_id, building_id: buildingId,
        code: 'INC-GF05-001', incident_type: body.incident_type, severity: body.severity, status: 'NEW',
        title: body.title, description: body.description, occurred_at: body.occurred_at, reported_by_id: currentId,
        conclusion: null, resolved_at: null, closed_at: null, version: 1,
        escalations: body.severity === 'HIGH' || body.severity === 'CRITICAL' ? [
          { id: securityId, security_incident_id: incidentId, target_role: 'security', escalated_by_id: currentId, reason: 'High severity', created_at: body.occurred_at, acknowledgement: null },
          { id: directorId, security_incident_id: incidentId, target_role: 'director', escalated_by_id: currentId, reason: 'High severity', created_at: body.occurred_at, acknowledgement: null },
        ] : [], evidence: [],
      }];
      return route.fulfill(respond(incidents[0], 201));
    }
    if (url.pathname.endsWith(`/security/incidents/${incidentId}/evidence`)) {
      const incident = incidents[0]; incident.evidence.push({ id: randomUUID(), security_incident_id: incidentId, recorded_by_id: currentId, evidence_type: body.evidence_type, description: body.description, storage_reference: null, created_at: '2026-09-27T01:25:00Z' });
      incident.version += 1; return route.fulfill(respond(incident, 201));
    }
    if (url.pathname.endsWith(`/security/incidents/${incidentId}/transition`)) {
      const incident = incidents[0];
      if (body.status === 'CLOSED' && incident.escalations.some(item => !item.acknowledgement)) {
        return route.fulfill(respond({ error: { code: 'ERR-ESCALATION-UNACKNOWLEDGED', message: 'Sự cố mức cao chưa được acknowledgement đầy đủ.', correlation_id: correlationId } }, 422));
      }
      incident.status = body.status; incident.conclusion = body.conclusion || incident.conclusion;
      if (body.status === 'RESOLVED') incident.resolved_at = '2026-09-27T01:50:00Z';
      if (body.status === 'CLOSED') incident.closed_at = '2026-09-27T02:00:00Z';
      incident.version += 1; return route.fulfill(respond(incident));
    }
    return route.fulfill(respond({ error: { code: 'ERR-NOTFOUND', message: 'Không tìm thấy.', correlation_id: correlationId } }, 404));
  });
  await page.goto(process.env.UX_BASE_URL || 'http://127.0.0.1:3000/');
  await page.locator('#staff-username').fill(`${role}.security.ux`);
  await page.locator('#staff-password').fill(`test-${randomUUID()}`);
  await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
  await page.getByRole('navigation', { name: 'Điều hướng chính' }).getByRole('button', { name: 'An ninh & Tuần tra', exact: true }).click();
  await page.getByRole('heading', { name: role === 'director' ? 'Điều phối an ninh và tuần tra' : 'Ca trực và tuần tra của tôi', exact: true }).waitFor();
  return { context, page };
}

(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const opened = [];
  try {
    const director = await openAs(browser, 'director'); opened.push(director);
    const form = director.page.getByRole('region', { name: 'Tạo ca trực an ninh' });
    await form.getByLabel('Điểm tuần tra').selectOption(pointId);
    await form.getByLabel('Nhân viên trực').selectOption(securityId);
    await form.getByLabel('Bắt đầu').fill('2026-09-27T08:00');
    await form.getByLabel('Kết thúc').fill('2026-09-27T10:00');
    await form.getByRole('button', { name: 'Tạo ca', exact: true }).click();
    await director.page.getByText('Đã tạo ca trực và cửa sổ tuần tra.', { exact: true }).waitFor();
    await director.page.getByText('Đã tạo ca trực và cửa sổ tuần tra.', { exact: true }).waitFor();
    await director.page.getByRole('button', { name: 'Bắt đầu ca', exact: true }).click();
    await director.page.getByText('Đang trực', { exact: true }).waitFor();
    check('manager creates a scoped shift and starts the assigned patrol', shift.status === 'IN_PROGRESS');

    await director.page.getByLabel('Người nhận').selectOption(securityId);
    await director.page.getByLabel('Tóm tắt bàn giao').fill('Ca bắt đầu bình thường.');
    await director.page.getByRole('button', { name: 'Bàn giao', exact: true }).click();
    await director.page.getByText('Đã thêm bản ghi bàn giao.', { exact: true }).waitFor();
    await director.page.getByRole('textbox', { name: 'Khách', exact: true }).fill('Khách giao hàng');
    await director.page.getByLabel('Mục đích').fill('Giao thiết bị cho cư dân.');
    await director.page.getByRole('button', { name: 'Ghi khách', exact: true }).click();
    await director.page.getByText('Đã ghi nhận khách.', { exact: true }).waitFor();
    await director.page.getByRole('button', { name: 'Check-in', exact: true }).click();
    await director.page.getByText('Đã ghi nhận đến điểm tuần tra.', { exact: true }).waitFor();
    await director.page.getByRole('button', { name: 'Hoàn thành', exact: true }).click();
    await director.page.getByText('Đã tuần tra', { exact: true }).waitFor();
    check('handoff, visitor and patrol results persist through the dashboard refresh', shift.handoffs.length === 1 && shift.visitors.length === 1 && window.logs.length === 1 && window.status === 'COMPLETED');

    await director.page.getByText('Báo sự cố hoặc PCCC', { exact: true }).click();
    await director.page.getByLabel('Tiêu đề').fill('Phát hiện người lạ tại tầng hầm');
    await director.page.getByLabel('Mô tả').fill('Bảo vệ phát hiện người lạ ở khu vực kỹ thuật.');
    await director.page.getByRole('button', { name: 'Gửi sự cố' }).click();
    await director.page.getByText('Đã lập sự cố và escalation nếu mức độ cao.', { exact: true }).waitFor();
    check('high severity incident creates both security and director escalations', incidents[0].escalations.length === 2);
    await director.page.getByRole('button', { name: 'Xác nhận director' }).click();
    await director.page.getByText('Đã acknowledgement escalation.', { exact: true }).waitFor();
    const incidentPanel = director.page.getByLabel('Sự cố an ninh và PCCC');
    await incidentPanel.getByLabel('Bằng chứng / ghi chú').fill('Đã kiểm tra camera và vị trí hiện trường.');
    await incidentPanel.getByRole('button', { name: 'Thêm bằng chứng' }).click();
    await director.page.getByText('Đã thêm bằng chứng.', { exact: true }).waitFor();
    for (const [buttonName, status] of [['Tiếp nhận', 'TRIAGED'], ['Xử lý', 'IN_PROGRESS'], ['Đánh dấu đã giải quyết', 'RESOLVED']]) {
      await incidentPanel.getByRole('button', { name: buttonName, exact: true }).click();
      await incidentPanel.getByText(new RegExp(`${status}`)).waitFor();
    }
    const conclusion = incidentPanel.getByLabel('Kết luận');
    await conclusion.fill('Đã bàn giao cho cơ quan chức năng.');
    await incidentPanel.getByRole('button', { name: 'Đóng sự cố', exact: true }).click();
    await director.page.getByRole('alert').filter({ hasText: 'Sự cố mức cao cần đủ acknowledgement' }).waitFor();
    check('high incident closure remains blocked until Security acknowledgement', incidents[0].status === 'RESOLVED');
    await director.context.close();

    const security = await openAs(browser, 'security'); opened.push(security);
    await security.page.getByRole('button', { name: 'Xác nhận security' }).click();
    await security.page.getByText('Đã acknowledgement escalation.', { exact: true }).waitFor();
    check('Security account acknowledges its own escalation target', Boolean(incidents[0].escalations.find(item => item.target_role === 'security').acknowledgement));
    await security.context.close();

    const directorClose = await openAs(browser, 'director'); opened.push(directorClose);
    const closePanel = directorClose.page.getByLabel('Sự cố an ninh và PCCC');
    await closePanel.getByLabel('Kết luận').fill('Đã bàn giao cho cơ quan chức năng.');
    await closePanel.getByRole('button', { name: 'Đóng sự cố', exact: true }).click();
    await closePanel.getByText(/CLOSED/).waitFor();
    check('incident closes after evidence, conclusion and both acknowledgements', incidents[0].status === 'CLOSED' && incidents[0].evidence.length === 1);
    check('no unhandled browser errors', errors.length === 0);
    console.log(`SECURITY MANAGER UX: ${checks.length} checks passed.`);
  } finally {
    await Promise.all(opened.map(item => item.context.close().catch(() => {})));
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
