const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const { randomUUID } = require('node:crypto');

const siteId = randomUUID();
const buildingId = randomUUID();
const unitId = randomUUID();
const categoryId = randomUUID();
const requestId = randomUUID();
const cskhId = randomUUID();
const leadId = randomUUID();
const techId = randomUUID();
const correlationId = randomUUID();
const identities = { cskh: cskhId, technical_lead: leadId, technician: techId };
const requestRecord = {
  id: requestId, code: 'SR-GF02-001', tenant_id: randomUUID(), site_id: siteId, building_id: buildingId,
  unit_id: unitId, category_id: categoryId, linked_request_id: null, link_type: null, link_reason: null,
  title: 'Đèn hành lang không sáng', description: 'Tầng ba mất đèn từ sáng nay.', priority: 'HIGH', status: 'NEW',
  sla_started_at: '2026-09-25T00:00:00Z', sla_duration_minutes: 240, sla_deadline: '2026-09-25T04:00:00Z',
  sla_breached_at: null, owner_account_id: cskhId, resolved_at: null, closed_at: null, csat_score: null, version: 1,
  unit_number: 'A-0301', building_code: 'A', building_name: 'Tòa A', created_at: '2026-09-25T00:00:00Z',
};
let workOrders = [];
let evidence = [];
let costLines = [];
let checklist = [];
let nextVersion = 1;
const contexts = [];
const checks = [];
const errors = [];

const json = (payload, status = 200) => ({
  status,
  headers: { 'Content-Type': 'application/json', 'X-Correlation-ID': correlationId },
  body: JSON.stringify(payload),
});
const workOrderView = () => ({
  id: workOrders[0].id, code: workOrders[0].code, tenant_id: requestRecord.tenant_id, site_id: siteId,
  building_id: buildingId, service_request_id: requestId, maintenance_occurrence_id: null,
  title: workOrders[0].title, description: workOrders[0].description, status: workOrders[0].status,
  assigned_to_id: workOrders[0].assigned_to_id, acceptance_mode: workOrders[0].acceptance_mode || null,
  acceptance_reason: workOrders[0].acceptance_reason || null, acceptance_evidence_id: workOrders[0].acceptance_evidence_id || null,
  result_summary: workOrders[0].result_summary || null, completed_at: workOrders[0].completed_at || null,
  closed_at: workOrders[0].closed_at || null, version: workOrders[0].version,
  checklist: checklist.map(item => ({ ...item })), evidence_count: evidence.length,
});

function check(name, value = true) { assert.ok(value, name); checks.push(name); console.log(`PASS ${name}`); }

async function openAs(browser, role) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 920 }, locale: 'vi-VN' });
  contexts.push(context);
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(`${role}: ${error.message}`));
  await context.route('**/api/v1/**', async route => {
    const req = route.request();
    const url = new URL(req.url());
    const body = (() => { try { return req.postDataJSON?.(); } catch { return null; } })();
    const headers = { 'Content-Type': 'application/json', 'X-Correlation-ID': correlationId };
    if (url.pathname.endsWith('/auth/login')) return route.fulfill(json({ access_token: `token-${role}` }));
    if (url.pathname.endsWith('/auth/me')) return route.fulfill(json({
      account_id: identities[role], tenant_id: requestRecord.tenant_id, username: `${role}.ux`, full_name: role,
      roles: [role], active_site_id: siteId, must_change_password: false,
      allowed_sites: [{ id: siteId, code: 'WEST', name: 'GreenCity West' }],
    }));
    if (url.pathname.endsWith('/auth/logout')) return route.fulfill({ status: 204, headers });
    if (url.pathname.endsWith('/notifications')) return route.fulfill(json({ items: [] }));
    if (url.pathname.endsWith('/service-requests') && req.method() === 'GET') return route.fulfill(json({
      items: [{ id: requestId, code: requestRecord.code, title: requestRecord.title, unit_id: unitId,
        unit_number: 'A-0301', building_id: buildingId, building_code: 'A', building_name: 'Tòa A',
        status: requestRecord.status, priority: requestRecord.priority, sla_deadline: requestRecord.sla_deadline,
        created_at: requestRecord.created_at }], page: 1, page_size: 20, total: 1,
    }));
    if (url.pathname.endsWith(`/service-requests/${requestId}/assignees`)) {
      return route.fulfill(json(url.searchParams.get('purpose') === 'triage'
        ? [{ id: cskhId, full_name: 'CSKH', role: 'cskh' }, { id: leadId, full_name: 'Trưởng kỹ thuật', role: 'technical_lead' }]
        : [{ id: techId, full_name: 'Kỹ thuật viên A', role: 'technician' }]));
    }
    if (url.pathname.endsWith(`/service-requests/${requestId}/work-orders`) && req.method() === 'GET') return route.fulfill(json(workOrders.map(() => workOrderView())));
    if (url.pathname.endsWith(`/service-requests/${requestId}/triage`) && req.method() === 'POST') {
      requestRecord.status = 'TRIAGED'; requestRecord.priority = body.priority; requestRecord.owner_account_id = body.owner_account_id; requestRecord.version += 1;
      return route.fulfill(json(requestRecord));
    }
    if (url.pathname.endsWith(`/service-requests/${requestId}/work-orders`) && req.method() === 'POST') {
      const wo = { id: randomUUID(), code: 'WO-GF02-001', title: body.title, description: body.description, status: 'DRAFT', assigned_to_id: null, version: nextVersion++ };
      checklist = body.checklist.map((item, index) => ({ id: randomUUID(), label: item.label, position: index + 1,
        is_required: item.required, is_completed: false, result: null, version: 1 }));
      workOrders = [wo]; requestRecord.status = 'IN_PROGRESS'; requestRecord.version += 1;
      return route.fulfill(json(workOrderView(), 201));
    }
    if (url.pathname.endsWith(`/service-requests/${requestId}/close`)) { requestRecord.status = 'CLOSED'; requestRecord.version += 1; return route.fulfill(json(requestRecord)); }
    if (url.pathname.endsWith(`/service-requests/${requestId}`)) return route.fulfill(json(requestRecord));
    if (url.pathname.endsWith(`/work-orders/${workOrders[0]?.id}/assignees`)) return route.fulfill(json([{ id: techId, full_name: 'Kỹ thuật viên A', role: 'technician' }]));
    if (url.pathname.endsWith(`/work-orders/${workOrders[0]?.id}/evidence`) && req.method() === 'GET') return route.fulfill(json(evidence));
    if (url.pathname.endsWith(`/work-orders/${workOrders[0]?.id}/evidence`) && req.method() === 'POST') {
      const item = { id: randomUUID(), work_order_id: workOrders[0].id, original_name: req.headers()['x-file-name'], mime_type: 'image/png', size_bytes: 4, sha256: 'b'.repeat(64) };
      evidence.push(item); return route.fulfill(json(item, 201));
    }
    if (url.pathname.endsWith(`/work-orders/${workOrders[0]?.id}/cost-lines`) && req.method() === 'GET') return route.fulfill(json(costLines));
    if (url.pathname.endsWith(`/work-orders/${workOrders[0]?.id}/cost-lines`) && req.method() === 'POST') {
      const item = { id: randomUUID(), work_order_id: workOrders[0].id, description: body.description,
        amount_vnd: body.amount_vnd, cost_bearer: body.cost_bearer, status: 'SUBMITTED', evidence_attachment_id: body.evidence_attachment_id || null, version: 1, pending_charge_id: null };
      costLines.push(item); return route.fulfill(json(item, 201));
    }
    if (url.pathname.endsWith(`/work-orders/${workOrders[0]?.id}/assign`)) { workOrders[0].assigned_to_id = body.assignee_id; workOrders[0].status = 'ASSIGNED'; workOrders[0].version += 1; return route.fulfill(json(workOrderView())); }
    if (url.pathname.endsWith(`/work-orders/${workOrders[0]?.id}/start`)) { workOrders[0].status = 'IN_PROGRESS'; workOrders[0].version += 1; return route.fulfill(json(workOrderView())); }
    if (/\/work-orders\/[^/]+\/checklist\/[^/]+$/.test(url.pathname)) {
      const item = checklist.find(entry => url.pathname.endsWith(`/${entry.id}`));
      item.is_completed = body.is_completed; item.result = body.result; item.version += 1;
      return route.fulfill(json(item));
    }
    if (url.pathname.endsWith(`/work-orders/${workOrders[0]?.id}/submit`)) { workOrders[0].status = 'WAITING_ACCEPTANCE'; workOrders[0].result_summary = body.result_summary; workOrders[0].version += 1; return route.fulfill(json(workOrderView())); }
    if (url.pathname.endsWith(`/work-orders/${workOrders[0]?.id}/accept`)) {
      workOrders[0].status = 'COMPLETED'; workOrders[0].acceptance_mode = body.mode; workOrders[0].acceptance_reason = body.reason;
      workOrders[0].acceptance_evidence_id = body.evidence_id; workOrders[0].version += 1; requestRecord.status = 'RESOLVED'; requestRecord.version += 1;
      return route.fulfill(json(workOrderView()));
    }
    if (url.pathname.endsWith(`/work-orders/${workOrders[0]?.id}/close`)) { workOrders[0].status = 'CLOSED'; workOrders[0].version += 1; return route.fulfill(json(workOrderView())); }
    if (url.pathname.endsWith(`/work-orders/${workOrders[0]?.id}`)) return route.fulfill(json(workOrderView()));
    return route.fulfill(json({ error: { code: 'ERR-NOTFOUND', message: 'Không tìm thấy.', correlation_id: correlationId } }, 404));
  });
  await page.goto(process.env.UX_BASE_URL || 'http://127.0.0.1:3000/');
  await page.locator('#staff-username').fill(`${role}.ux`);
  await page.locator('#staff-password').fill(`test-${randomUUID()}`);
  await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
  await page.getByRole('navigation', { name: 'Điều hướng chính' }).getByRole('button', { name: 'Công việc & Yêu cầu', exact: true }).click();
  await page.getByText('SR-GF02-001', { exact: true }).waitFor();
  await page.getByRole('button', { name: 'Mở yêu cầu SR-GF02-001' }).click();
  await page.getByRole('dialog').getByText('Đèn hành lang không sáng').waitFor();
  return { context, page };
}

(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  try {
    const cskh = await openAs(browser, 'cskh');
    await cskh.page.getByLabel('Người phụ trách').selectOption(leadId);
    await cskh.page.getByRole('button', { name: 'Lưu phân loại', exact: true }).click();
    await cskh.page.getByText('Đã lưu phân loại yêu cầu.', { exact: true }).waitFor();
    check('CSKH triage persists owner and priority from the server response', requestRecord.status === 'TRIAGED' && requestRecord.owner_account_id === leadId);
    await cskh.page.getByLabel('Tiêu đề').fill('Sửa đèn tầng ba');
    await cskh.page.getByLabel('Mô tả').fill('Thay bóng đèn và kiểm tra mạch.');
    await cskh.page.getByLabel('Checklist').fill('Kiểm tra mạch\nThay bóng\nChạy thử');
    await cskh.page.getByRole('button', { name: 'Tạo Work Order', exact: true }).click();
    await cskh.page.getByText('WO-GF02-001', { exact: false }).waitFor();
    check('CSKH creates a Work Order with server-owned idempotency key', workOrders.length === 1 && workOrders[0].status === 'DRAFT');
    check('CSKH does not receive technician start controls', await cskh.page.getByRole('button', { name: 'Bắt đầu xử lý' }).count() === 0);
    await cskh.context.close();

    const lead = await openAs(browser, 'technical_lead');
    await lead.page.getByLabel('Giao cho kỹ thuật viên').selectOption(techId);
    await lead.page.getByRole('button', { name: 'Phân công', exact: true }).click();
    await lead.page.getByRole('button', { name: 'Bắt đầu xử lý' }).waitFor({ state: 'detached' });
    check('Technical Lead assigns only a server-listed technician', workOrders[0].status === 'ASSIGNED' && workOrders[0].assigned_to_id === techId);
    await lead.context.close();

    const technician = await openAs(browser, 'technician');
    await technician.page.getByRole('button', { name: 'Bắt đầu xử lý' }).click();
    await technician.page.getByText('Đã bắt đầu xử lý.', { exact: true }).waitFor();
    const result = technician.page.getByLabel('Kết quả Kiểm tra mạch');
    await result.fill('Đã kiểm tra an toàn.');
    const checklistBox = technician.page.locator('.workflow-checklist-row input[type="checkbox"]').first();
    await checklistBox.click();
    await technician.page.waitForFunction(() => document.querySelector('.workflow-checklist-row input[type="checkbox"]')?.checked === true);
    await technician.page.locator('.workflow-file-button input').setInputFiles({ name: 'evidence.png', mimeType: 'image/png', buffer: Buffer.from([1, 2, 3, 4]) });
    await technician.page.getByText('Đã tải bằng chứng lên.', { exact: true }).waitFor();
    const cost = technician.page.locator('.workflow-cost-section');
    await cost.getByLabel('Mô tả').fill('Bóng đèn thay mới');
    await cost.getByLabel('Số tiền (₫)').fill('50000');
    await cost.getByRole('button', { name: 'Ghi nhận chi phí' }).click();
    await technician.page.getByText('Đã ghi nhận chi phí.', { exact: true }).waitFor();
    await technician.page.getByLabel('Kết quả xử lý').fill('Đã thay bóng, kiểm tra hoạt động bình thường.');
    await technician.page.getByRole('button', { name: 'Gửi nghiệm thu' }).click();
    await technician.page.getByText('Đã gửi Work Order nghiệm thu.', { exact: true }).waitFor();
    check('Technician checklist, private evidence, cost and submit are persisted in the mocked API flow', workOrders[0].status === 'WAITING_ACCEPTANCE' && evidence.length === 1 && costLines.length === 1);
    await technician.context.close();

    const cskhAccept = await openAs(browser, 'cskh');
    await cskhAccept.page.getByLabel('Lý do nghiệm thu thay mặt').fill('Đã xác nhận với cư dân.');
    await cskhAccept.page.getByLabel('Bằng chứng').selectOption(evidence[0].id);
    await cskhAccept.page.getByRole('button', { name: 'Nghiệm thu thay mặt' }).click();
    await cskhAccept.page.getByText('Đã nghiệm thu thay mặt cư dân.', { exact: true }).waitFor();
    await cskhAccept.page.getByRole('button', { name: 'Đóng Work Order' }).click();
    await cskhAccept.page.getByText('Đã đóng Work Order.', { exact: true }).waitFor();
    await cskhAccept.page.getByRole('button', { name: 'Đóng yêu cầu', exact: true }).click();
    await cskhAccept.page.getByText('Đã đóng yêu cầu.', { exact: true }).waitFor();
    check('CSKH proxy accepts with evidence, then closes the resolved request', workOrders[0].status === 'CLOSED' && requestRecord.status === 'CLOSED');
    check('no runtime browser errors', errors.length === 0);
    console.log(`WORK ORDER UX: ${checks.length} checks passed.`);
  } finally {
    await Promise.all(contexts.map(context => context.close().catch(() => {})));
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
