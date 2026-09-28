const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const { randomUUID } = require('node:crypto');

const siteId = randomUUID();
const buildingId = randomUUID();
const assetId = randomUUID();
const planId = randomUUID();
const occurrenceId = randomUUID();
const workOrderId = randomUUID();
const technicianId = randomUUID();
const technicalLeadId = randomUUID();
const correlationId = randomUUID();
const workOrderCode = 'MWO-GF03-001';
let asset = null;
let plan = null;
let occurrence = null;
let workOrder = null;
let evidence = [];
let history = [];
let checklist = [];
const contexts = [];
const checks = [];
const errors = [];

const json = (payload, status = 200) => ({ status, headers: { 'Content-Type': 'application/json', 'X-Correlation-ID': correlationId }, body: JSON.stringify(payload) });
const orderView = () => ({
  id: workOrderId, code: workOrderCode, tenant_id: randomUUID(), site_id: siteId, building_id: buildingId,
  service_request_id: null, maintenance_occurrence_id: occurrenceId, title: 'Kiểm tra bơm nước',
  description: 'Bảo trì định kỳ cho kế hoạch PUMP-MONTHLY', status: workOrder.status,
  assigned_to_id: workOrder.assigned_to_id, acceptance_mode: workOrder.acceptance_mode || null,
  acceptance_reason: workOrder.acceptance_reason || null, acceptance_evidence_id: null,
  result_summary: workOrder.result_summary || null, completed_at: workOrder.completed_at || null,
  closed_at: null, version: workOrder.version,
  checklist: checklist.map(item => ({ ...item })), evidence_count: evidence.length,
});
const check = (name, value = true) => { assert.ok(value, name); checks.push(name); console.log(`PASS ${name}`); };

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
      account_id: role === 'technician' ? technicianId : technicalLeadId, tenant_id: randomUUID(),
      username: `${role}.maintenance`, full_name: role, roles: [role], active_site_id: siteId,
      must_change_password: false, allowed_sites: [{ id: siteId, code: 'WEST', name: 'GreenCity West' }],
    }));
    if (url.pathname.endsWith('/service-requests')) return route.fulfill(json({ items: [], page: 1, page_size: 20, total: 0 }));
    if (url.pathname.endsWith('/notifications')) return route.fulfill(json({ items: [] }));
    if (url.pathname.endsWith('/maintenance/buildings')) return route.fulfill(json([{ id: buildingId, code: 'A', name: 'Tòa A' }]));
    if (url.pathname.endsWith('/maintenance/assigned-work-orders')) return route.fulfill(json(role === 'technician' && workOrder?.assigned_to_id === technicianId ? [orderView()] : []));
    if (url.pathname.endsWith('/maintenance/assets') && req.method() === 'GET') return route.fulfill(json(asset ? [asset] : []));
    if (url.pathname.endsWith('/assets') && req.method() === 'POST') {
      asset = { id: assetId, tenant_id: randomUUID(), site_id: siteId, building_id: body.building_id, unit_id: null, code: body.code, name: body.name, description: body.description, status: 'ACTIVE', version: 1 };
      return route.fulfill(json(asset, 201));
    }
    if (url.pathname.endsWith(`/maintenance/assets/${assetId}/plans`) && req.method() === 'GET') return route.fulfill(json(plan ? [plan] : []));
    if (url.pathname.endsWith('/maintenance-plans') && req.method() === 'POST') {
      plan = { id: planId, tenant_id: randomUUID(), site_id: siteId, building_id: buildingId, asset_id: body.asset_id,
        code: body.code, title: body.title, interval_days: body.interval_days, next_due_at: body.next_due_at,
        checklist_template: body.checklist, evidence_required: body.evidence_required, is_active: true, version: 1 };
      return route.fulfill(json(plan, 201));
    }
    if (url.pathname.endsWith('/maintenance/scheduler/run')) {
      if (!occurrence) {
        occurrence = { id: occurrenceId, asset_id: assetId, plan_id: planId, due_at: plan.next_due_at,
          status: 'WO_CREATED', defer_until: null, defer_reason: null, completed_at: null, work_order_id: workOrderId, version: 1 };
        workOrder = { status: 'DRAFT', assigned_to_id: null, version: 1, result_summary: null };
        checklist = body ? plan.checklist_template.map((item, index) => ({ id: randomUUID(), position: index + 1,
          label: item.label, is_required: item.required, is_completed: false, result: null, version: 1 })) : [];
      }
      return route.fulfill(json({ items: [{ occurrence_id: occurrenceId, work_order_id: workOrderId, plan_id: planId, due_at: occurrence.due_at, replayed: false }] }));
    }
    if (url.pathname.endsWith('/maintenance/occurrences')) return route.fulfill(json({ items: occurrence ? [occurrence] : [] }));
    if (url.pathname.endsWith(`/assets/${assetId}/maintenance-history`)) return route.fulfill(json({ items: history }));
    if (url.pathname.endsWith(`/work-orders/${workOrderId}/assignees`)) return route.fulfill(json([{ id: technicianId, full_name: 'Kỹ thuật viên A', role: 'technician' }]));
    if (url.pathname.endsWith(`/work-orders/${workOrderId}/evidence`) && req.method() === 'GET') return route.fulfill(json(evidence));
    if (url.pathname.endsWith(`/work-orders/${workOrderId}/evidence`) && req.method() === 'POST') {
      const item = { id: randomUUID(), work_order_id: workOrderId, original_name: req.headers()['x-file-name'], mime_type: 'image/png', size_bytes: 4, sha256: 'c'.repeat(64) };
      evidence.push(item); return route.fulfill(json(item, 201));
    }
    if (url.pathname.endsWith(`/work-orders/${workOrderId}/cost-lines`) && req.method() === 'GET') return route.fulfill(json([]));
    if (url.pathname.endsWith(`/work-orders/${workOrderId}/assign`)) { workOrder.assigned_to_id = body.assignee_id; workOrder.status = 'ASSIGNED'; workOrder.version += 1; return route.fulfill(json(orderView())); }
    if (url.pathname.endsWith(`/work-orders/${workOrderId}/start`)) { workOrder.status = 'IN_PROGRESS'; workOrder.version += 1; occurrence.status = 'IN_PROGRESS'; occurrence.version += 1; return route.fulfill(json(orderView())); }
    if (/\/work-orders\/[^/]+\/checklist\/[^/]+$/.test(url.pathname)) {
      const item = checklist.find(entry => url.pathname.endsWith(`/${entry.id}`));
      item.is_completed = body.is_completed; item.result = body.result; item.version += 1;
      return route.fulfill(json(item));
    }
    if (url.pathname.endsWith(`/work-orders/${workOrderId}/submit`)) { workOrder.status = 'WAITING_ACCEPTANCE'; workOrder.result_summary = body.result_summary; workOrder.version += 1; return route.fulfill(json(orderView())); }
    if (url.pathname.endsWith(`/work-orders/${workOrderId}/accept`)) {
      workOrder.status = 'COMPLETED'; workOrder.acceptance_mode = body.mode; workOrder.completed_at = '2026-09-25T03:00:00Z'; workOrder.version += 1;
      occurrence.status = 'COMPLETED'; occurrence.completed_at = workOrder.completed_at; occurrence.version += 1;
      history = [{ id: randomUUID(), asset_id: assetId, occurrence_id: occurrenceId, work_order_id: workOrderId,
        performed_by_id: technicianId, accepted_by_id: technicalLeadId, result_summary: workOrder.result_summary, completed_at: workOrder.completed_at }];
      return route.fulfill(json(orderView()));
    }
    if (url.pathname.endsWith(`/work-orders/${workOrderId}`)) return route.fulfill(json(orderView()));
    return route.fulfill(json({ error: { code: 'ERR-NOTFOUND', message: 'Không tìm thấy.', correlation_id: correlationId } }, 404));
  });
  await page.goto(process.env.UX_BASE_URL || 'http://127.0.0.1:3000/');
  await page.locator('#staff-username').fill(`${role}.maintenance`);
  await page.locator('#staff-password').fill(`test-${randomUUID()}`);
  await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
  await page.getByRole('navigation', { name: 'Điều hướng chính' }).getByRole('button', { name: 'Kỹ thuật & Bảo trì', exact: true }).click();
  await page.getByRole('heading', { name: role === 'technician' ? 'Bảo trì của tôi' : 'Kỹ thuật & Bảo trì' }).waitFor();
  return { context, page };
}

(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  try {
    const lead = await openAs(browser, 'technical_lead');
    await lead.page.getByLabel('Mã Asset').fill('PUMP-001');
    await lead.page.getByLabel('Tên thiết bị').fill('Bơm nước tầng hầm');
    await lead.page.getByLabel('Mô tả').fill('Thiết bị bơm chính tòa A.');
    await lead.page.getByRole('button', { name: 'Tạo Asset' }).click();
    await lead.page.getByText('Đã tạo Asset.', { exact: true }).waitFor();
    check('technical lead creates Asset through the scoped API', asset?.building_id === buildingId);
    await lead.page.getByLabel('Mã kế hoạch').fill('PUMP-MONTHLY');
    await lead.page.getByLabel('Tên kế hoạch').fill('Kiểm tra bơm nước');
    await lead.page.getByRole('button', { name: 'Tạo Maintenance Plan' }).click();
    await lead.page.getByText('Đã tạo Maintenance Plan.', { exact: true }).waitFor();
    check('Maintenance Plan is saved with checklist and next due date', plan?.asset_id === assetId && plan.checklist_template.length === 3);
    await lead.page.getByRole('button', { name: 'Chạy scheduler' }).click();
    await lead.page.getByText('Đã chạy scheduler; occurrence và Work Order đã được đọc lại từ máy chủ.', { exact: true }).waitFor();
    check('scheduler creates one occurrence linked to a Work Order', occurrence?.work_order_id === workOrderId);
    await lead.page.getByRole('button', { name: 'Mở Work Order' }).click();
    await lead.page.getByLabel('Giao cho kỹ thuật viên').selectOption(technicianId);
    await lead.page.getByRole('button', { name: 'Phân công' }).click();
    check('technical lead assigns the maintenance Work Order to the listed technician', workOrder.assigned_to_id === technicianId);
    await lead.context.close();

    const tech = await openAs(browser, 'technician');
    await tech.page.getByRole('button', { name: 'Mở Work Order' }).click();
    await tech.page.getByRole('button', { name: 'Bắt đầu xử lý' }).click();
    const result = tech.page.getByLabel('Kết quả Kiểm tra thiết bị');
    await result.fill('Đã kiểm tra áp lực và vận hành.');
    await tech.page.locator('.workflow-checklist-row input[type="checkbox"]').first().click();
    await tech.page.waitForFunction(() => document.querySelector('.workflow-checklist-row input[type="checkbox"]')?.checked === true);
    await tech.page.locator('.workflow-file-button input').setInputFiles({ name: 'pump.png', mimeType: 'image/png', buffer: Buffer.from([1, 2, 3, 4]) });
    await tech.page.getByText('Đã tải bằng chứng lên.', { exact: true }).waitFor();
    await tech.page.getByLabel('Kết quả xử lý').fill('Bơm hoạt động bình thường sau bảo trì.');
    await tech.page.getByRole('button', { name: 'Gửi nghiệm thu' }).click();
    await tech.page.getByText('Đã gửi Work Order nghiệm thu.', { exact: true }).waitFor();
    check('assigned technician completes the maintenance checklist and submits evidence', workOrder.status === 'WAITING_ACCEPTANCE' && evidence.length === 1);
    await tech.context.close();

    const leadAccept = await openAs(browser, 'technical_lead');
    await leadAccept.page.getByRole('button', { name: 'Mở Work Order' }).click();
    await leadAccept.page.getByRole('button', { name: 'Nghiệm thu kỹ thuật' }).click();
    await leadAccept.page.getByText('Đã nghiệm thu kỹ thuật.', { exact: true }).waitFor();
    await leadAccept.page.getByText(/1 lần nghiệm thu/).waitFor();
    check('technical acceptance writes the Asset maintenance history', occurrence.status === 'COMPLETED' && history.length === 1);
    check('no runtime browser errors', errors.length === 0);
    console.log(`MAINTENANCE UX: ${checks.length} checks passed.`);
  } finally {
    await Promise.all(contexts.map(context => context.close().catch(() => {})));
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
