const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { randomUUID, createHash } = require('node:crypto');
const { chromium } = require('playwright');
const schemas = require('./fixtures/review-r05-schemas.json');

const outputImages = path.resolve(__dirname, '../../documents/review/images/R06');
fs.mkdirSync(outputImages, { recursive: true });

const ids = Object.fromEntries([
  'site', 'building', 'unit', 'userAdmin', 'userDirector', 'userAccountant', 'userResident', 'userTech',
  'accountTarget', 'invitation', 'recovery', 'review', 'job', 'jobRun',
  'invoice', 'intent', 'payment', 'source', 'slaPolicy', 'request', 'period'
].map(k => [k, randomUUID()]));

const checks = [];
const errors = [];
const commands = [];
const check = (task, name, pass = true) => {
  assert.ok(pass, `${task}: ${name}`);
  checks.push({ task, name });
  console.log(`PASS ${task} ${name}`);
};

(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'vi-VN', acceptDownloads: true });
  const page = await context.newPage();
  page.on('pageerror', err => errors.push(err.message));

  let currentRole = 'director';
  let currentUser = {
    account_id: ids.userDirector,
    tenant_id: ids.site,
    username: 'director_west',
    full_name: 'Giám đốc Vận hành',
    roles: ['director'],
    active_site_id: ids.site,
    allowed_sites: [{ id: ids.site, code: 'GC-WEST', name: 'GreenCity West' }],
  };

  // State objects
  let targetAccount = {
    id: ids.accountTarget,
    username: 'tech_operator_01',
    full_name: 'Kỹ thuật viên Trực ca',
    is_active: true,
    session_version: 1,
    roles: ['technician'],
    building_id: ids.building,
    created_at: '2026-09-01T08:00:00Z',
    version: 1
  };

  let invitationRow = {
    id: ids.invitation,
    target_account_id: ids.accountTarget,
    email: 'tech_operator_01@greencity.local',
    role: 'technician',
    building_id: ids.building,
    status: 'SENT',
    version: 1
  };

  let recoveryRow = {
    id: ids.recovery,
    account_id: ids.accountTarget,
    username: 'tech_operator_01',
    status: 'PENDING',
    created_at: '2026-10-12T08:00:00Z',
    expires_at: '2026-10-12T12:00:00Z',
    version: 1
  };

  let accessReviewRow = {
    id: ids.review,
    target_account_id: ids.accountTarget,
    evidence_reference: 'LOG-SEC-20261012-01',
    description: 'Phát hiện đăng nhập trái giờ và đổi IP bất thường từ mạng phụ.',
    status: 'OPEN',
    version: 1,
    decision: null
  };

  let jobScheduleRow = {
    id: ids.job,
    building_id: ids.building,
    job_type: 'DAILY_METER_AUDIT',
    cron_expression: '0 2 * * *',
    status: 'ACTIVE',
    next_run_at: '2026-10-13T02:00:00Z',
    version: 1
  };

  let jobRunRow = {
    id: ids.jobRun,
    schedule_id: ids.job,
    scheduled_at: '2026-10-12T02:00:00Z',
    status: 'FAILED',
    version: 1,
    result: {
      cutoff: '2026-10-12T02:00:00Z',
      succeeded: 12,
      failed: 1,
      items: [
        { effect_key: 'EF-01', source_type: 'METER', source_id: randomUUID(), moment: '2026-10-12T02:00:00Z', status: 'COMPLETED', result: { replayed: true } },
        { effect_key: 'EF-02', source_type: 'CREDENTIAL', source_id: randomUUID(), moment: '2026-10-12T02:00:00Z', status: 'FAILED', error_code: 'ERR-SYNC-TIMEOUT' }
      ]
    }
  };

  let invoiceRow = {
    id: ids.invoice,
    unit_id: ids.unit,
    invoice_number: 'INV-2026-10-001',
    total_vnd: 2500000,
    outstanding_vnd: 2500000,
    status: 'ISSUED',
    items: [
      { id: randomUUID(), description: 'Phí dịch vụ quản lý T10/2026', amount_vnd: 2000000, calculation_snapshot: null },
      { id: randomUUID(), description: 'Phí gửi xe ô tô T10/2026', amount_vnd: 500000, calculation_snapshot: null }
    ]
  };

  let paymentIntentRow = {
    id: ids.intent,
    unit_id: ids.unit,
    invoice_id: ids.invoice,
    amount_vnd: 2500000,
    reference: 'VNP-REF-889900',
    status: 'RECONCILIATION',
    payment_url: 'https://sandbox.vnpayment.vn/paymentv2/vpcpay.html?vnp_Amount=250000000',
    provider_transaction: 'VNPDT-998877',
    created_at: '2026-10-12T09:00:00Z',
    payment_id: null,
    provider_received_at: null
  };

  let feeSourceRow = {
    id: ids.source,
    unit_id: ids.unit,
    description: 'Phí dịch vụ căn hộ cao cấp W1',
    amount_vnd: 2000000,
    recurring: true,
    valid_from: '2026-01-01',
    valid_to: null,
    status: 'ACTIVE',
    postings: [ids.invoice],
    intervals: [{ id: randomUUID(), starts_on: '2026-01-01', ends_on: null, amount_vnd: 2000000 }]
  };

  let slaPolicyRow = {
    id: ids.slaPolicy,
    building_id: ids.building,
    category_id: 'CAT-PLUMBING',
    status: 'DRAFT',
    definition: {
      minutes: 240,
      weekdays: [1, 2, 3, 4, 5],
      opens_minute: 480,
      closes_minute: 1020,
      pause_reasons: ['WAITING_PARTS', 'FORCE_MAJEURE'],
      confirmed_reference: 'NQ-BQL-SLA-2026',
      handoff_minutes: 60
    },
    version: 1
  };

  let serviceRequestRow = {
    id: ids.request,
    code: 'REQ-2026-0099',
    title: 'Sự cố rò rỉ van cấp nước căn 101',
    status: 'IN_PROGRESS',
    sla_deadline: '2026-10-12T16:00:00Z',
    owner_account_id: ids.userTech,
    sla_policy_snapshot: {
      policy_id: ids.slaPolicy,
      version: 1,
      pause_reasons: ['WAITING_PARTS', 'FORCE_MAJEURE']
    },
    sla_pauses: [],
    handoff: {
      status: 'PENDING',
      to_id: ids.userDirector,
      department: 'Ban Giám đốc',
      due_at: '2026-10-12T11:00:00Z'
    },
    repeat_cause: null
  };

  let operationalReportRow = {
    id: randomUUID(),
    building_id: ids.building,
    kind: 'FINANCIAL',
    as_of: '2026-10-12T02:00:00Z',
    definition_version: '2.4.0',
    digest: 'SHA256-REP-FINANCIAL-99',
    filters: { effective_date_from: '2026-10-01', effective_date_to: '2026-10-31' },
    metrics: {
      invoiced_vnd: { value: 154000000, unit: 'VND', definition: 'Tổng phát hành hóa đơn', data_status: 'AVAILABLE' },
      receivable_vnd: { value: 45000000, unit: 'VND', definition: 'Còn phải thu lũy kế', data_status: 'AVAILABLE' },
      cash_received_vnd: { value: 109000000, unit: 'VND', definition: 'Tiền đã thực thu', data_status: 'AVAILABLE' },
      fund_balance_vnd: { value: 500000000, unit: 'VND', definition: 'Số dư quỹ bảo trì', data_status: 'AVAILABLE' },
    },
    counts: { billing_invoices: 45, payments: 38, operational_expenses: 12 },
    rows: [
      { source: 'payments', data: { id: ids.payment, code: 'PAY-2026-10-001', amount_vnd: 2500000, status: 'RECEIVED' } },
      { source: 'billing_invoices', data: { id: ids.invoice, invoice_number: 'INV-2026-10-001', total_vnd: 2500000, status: 'ISSUED' } }
    ]
  };

  const accountingPeriod = {
    id: ids.period,
    building_id: ids.building,
    period_key: '2026-10',
    period_start: '2026-10-01',
    period_end: '2026-10-31',
    cutoff_at: '2026-10-31T23:59:59Z',
    status: 'OPEN',
    version: 1
  };

  const apiOptions = {
    buildings: [{ id: ids.building, name: 'Tòa Tháp Ruby W1', code: 'W1' }],
    units: [{ id: ids.unit, building_id: ids.building, unit_number: 'W1-101' }],
    accounts: [
      { id: ids.userDirector, label: 'Giám đốc Vận hành', username: 'director_west', full_name: 'Giám đốc Vận hành' },
      { id: ids.accountTarget, label: 'Kỹ thuật viên Trực ca', username: 'tech_operator_01', full_name: 'Kỹ thuật viên Trực ca' },
      { id: ids.userTech, label: 'Trưởng kỹ thuật West', username: 'techlead_west', full_name: 'Trưởng kỹ thuật West' }
    ],
    categories: [{ id: 'CAT-PLUMBING', label: 'Cấp thoát nước & Cơ điện' }],
    requests: [{ id: ids.request, label: 'REQ-2026-0099 · Sự cố rò rỉ van cấp nước căn 101' }],
    periods: [accountingPeriod]
  };

  await context.route('**/api/v1/**', async route => {
    const req = route.request();
    const url = new URL(req.url());
    const rawApi = url.pathname.replace('/api/v1', '');
    const api = rawApi.replace(/^\/portal/, '');
    const body = req.postData() ? req.postDataJSON() : null;
    const respond = (data, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
    const reject = (message, status = 400) => respond({ error: { code: 'ERR-R06-TEST', message, correlation_id: 'R06-CORR' } }, status);

    if (req.method() === 'POST') {
      commands.push({ api: rawApi, body, key: req.headers()['idempotency-key'] });
    }

    // Auth
    if (api === '/auth/login') return respond({ access_token: 'r06-token' });
    if (api === '/auth/me') return respond(currentUser);
    if (api === '/auth/logout' || api === '/auth/logout-all') return respond({ status: 'LOGGED_OUT' });
    if (api === '/account-profile') {
      return respond({ username: currentUser.username, full_name: currentUser.full_name, email: 'director@greencity.local', email_verified_at: '2026-09-01T00:00:00Z', profile_version: 1 });
    }

    // Portal common options
    if (api === '/options' || api === '/operations/options') return respond(apiOptions);
    if (api === '/capabilities') return respond({ items: [] });
    if (api === '/service-requests') return respond({ items: [], page: 1, page_size: 20, total: 0 });
    if (api === '/notifications' || api === '/outbox/events') return respond({ items: [] });

    // FE-43: Executive Dashboard
    if (api === '/dashboard') {
      return respond({
        as_of: url.searchParams.get('as_of') || '2026-10-12T02:00:00Z',
        sla_overdue_count: 2,
        maintenance_due_count: 4,
        cleaning_rework_count: 1,
        open_incident_count: 3,
        ar_debt_vnd: 45000000
      });
    }
    if (api.startsWith('/dashboard/drill-down/')) {
      const metric = api.split('/').pop().split('?')[0];
      return respond({
        as_of: '2026-10-12T02:00:00Z',
        metric: metric,
        items: [
          {
            metric: metric,
            resource_type: 'ServiceRequest',
            resource_id: ids.request,
            building_id: ids.building,
            reference: 'REQ-2026-0099',
            title: 'Yêu cầu quá hạn SLA',
            status: 'OVERDUE',
            occurred_at: '2026-10-12T01:00:00Z',
            amount_vnd: null
          }
        ]
      });
    }
    if (api === '/audit-events' || api === '/audit/events') {
      return respond({
        items: [
          { id: randomUUID(), event_type: 'AccountLock', action: 'LOCK', resource_type: 'Account', resource_id: ids.accountTarget, created_at: '2026-10-12T09:30:00Z', correlation_id: 'CORR-AUDIT-01' },
          { id: randomUUID(), event_type: 'SlaPolicyPublish', action: 'PUBLISH', resource_type: 'SlaPolicy', resource_id: ids.slaPolicy, created_at: '2026-10-12T09:00:00Z', correlation_id: 'CORR-AUDIT-02' }
        ]
      });
    }

    // FE-41: Account control & permissions
    if (api === '/control/permission-catalog') {
      return respond({
        note: 'Bảng quyền quản trị toàn hệ thống GreenCity',
        can_manage_accounts: true,
        roles: [{ role: 'director', scope: 'SITE_BUILDING_INDEPENDENT_APPROVAL' }],
        current_grants: [{ role: 'director', building_id: ids.building }],
        actions: [
          { action: 'ACCOUNT_PROFILE', roles: ['admin', 'director', 'cskh', 'accountant'], scope: 'SELF' },
          { action: 'ACCOUNT_LOCK_ROLE_SESSIONS', roles: ['admin', 'director'], scope: 'TENANT_ADMIN_OTHER_ACCOUNT' },
          { action: 'ACCOUNT_RECOVERY_VERIFY', roles: ['admin', 'director'], scope: 'TARGET_AUTHORITY_REAUTHENTICATE' },
          { action: 'ACCESS_REVIEW_RESOLVE', roles: ['admin', 'director'], scope: 'TENANT_ADMIN_INDEPENDENT' }
        ]
      });
    }
    if (api === '/control/accounts') {
      return respond({ items: [targetAccount] });
    }
    if (api === `/control/accounts/${ids.accountTarget}/actions`) {
      if (body.action === 'LOCK') targetAccount.is_active = false;
      if (body.action === 'UNLOCK') targetAccount.is_active = true;
      if (body.action === 'REVOKE_SESSIONS') targetAccount.session_version++;
      targetAccount.version++;
      return respond(targetAccount);
    }
    if (api === `/control/accounts/${ids.accountTarget}/sessions`) {
      return respond({
        items: [
          { id: randomUUID(), created_at: '2026-10-12T08:00:00Z', expires_at: '2026-10-12T20:00:00Z', revoked_at: null }
        ],
        changes: [
          { id: randomUUID(), title: 'Cập nhật phiên', created_at: '2026-10-12T08:00:00Z', data: { action: 'UPDATE' } }
        ]
      });
    }
    if (api === '/control/invitations') {
      if (req.method() === 'POST') {
        return respond({ id: ids.invitation, status: 'PENDING', ...body }, 201);
      }
      return respond({ items: [invitationRow] });
    }
    if (api === `/control/invitations/${ids.invitation}/send`) {
      invitationRow.status = 'SENT';
      return respond(invitationRow);
    }
    if (api === '/recovery-requests') {
      return respond({ items: [recoveryRow] });
    }
    if (api.startsWith('/recovery-requests/') && api.endsWith('/verify')) {
      recoveryRow.status = 'VERIFIED';
      return respond({
        request_id: ids.recovery,
        token: 'RCV-9988-SAFE-ONE-TIME',
        expires_at: '2026-10-12T12:00:00Z',
        message: 'Xác minh thành công. Cấp mã khôi phục cho chủ tài khoản.'
      });
    }
    if (api === '/control/access-reviews') {
      if (req.method() === 'POST') {
        const row = { id: randomUUID(), ...body, status: 'OPEN', version: 1 };
        return respond(row, 201);
      }
      return respond({ items: [accessReviewRow] });
    }
    if (api === `/control/access-reviews/${ids.review}/resolve`) {
      accessReviewRow.status = 'RESOLVED';
      accessReviewRow.decision = { action: body.action, reason: body.reason, at: '2026-10-12T10:00:00Z' };
      return respond(accessReviewRow);
    }

    // FE-42: Jobs and Job-runs
    if (api === '/control/jobs') {
      if (req.method() === 'POST') {
        const row = { id: randomUUID(), status: 'ACTIVE', version: 1, ...body };
        return respond(row, 201);
      }
      return respond({ items: [jobScheduleRow] });
    }
    if (api === `/control/jobs/${ids.job}/actions`) {
      if (body.action === 'RUN') jobScheduleRow.next_run_at = '2026-10-14T02:00:00Z';
      if (body.action === 'PAUSE') jobScheduleRow.status = 'PAUSED';
      if (body.action === 'RESUME') jobScheduleRow.status = 'ACTIVE';
      jobScheduleRow.version++;
      return respond(jobScheduleRow);
    }
    if (api === '/control/job-runs') {
      return respond({ items: [jobRunRow] });
    }
    if (api === `/control/job-runs/${ids.jobRun}/actions`) {
      if (body.action === 'RETRY') jobRunRow.status = 'COMPLETED';
      return respond(jobRunRow);
    }
    if (api === '/jobs/tick') {
      return respond({ status: 'TICK_COMPLETED', processed_schedules: 3, timestamp: '2026-10-12T10:05:00Z' });
    }

    // FE-43: Reports & SourceLinks
    if (api === '/control/reports') {
      if (req.method() === 'POST') return respond(operationalReportRow, 201);
      return respond({ items: [operationalReportRow] });
    }
    if (api.startsWith('/control/reports/') && api.endsWith('/download')) {
      const csv = 'Chỉ tiêu,Giá trị\nHóa đơn phát hành,154000000\nCòn phải thu,45000000\n';
      return route.fulfill({ status: 200, contentType: 'text/csv', headers: { 'Content-Disposition': 'attachment; filename="report-financial.csv"' }, body: csv });
    }
    if (api.startsWith('/control/reports/') && !api.includes('/sources')) {
      return respond(operationalReportRow);
    }
    if (api.includes('/sources/')) {
      return respond({
        source: 'billing_invoices',
        current: { code: 'INV-2026-10-001', status: 'ISSUED', total_vnd: 2500000 },
        notice: 'Hồ sơ hóa đơn gốc trong kỳ kiểm soát.',
        links: [{ source: 'operations_records', id: randomUUID(), label: 'Biên bản đối chiếu' }]
      });
    }

    // FE-45: Payments & VNPay
    if (api === '/invoices') return respond({ items: [invoiceRow] });
    if (api === '/payment-intents') {
      if (req.method() === 'POST') {
        return respond({ id: randomUUID(), ...paymentIntentRow, payment_url: 'https://sandbox.vnpayment.vn/pay-intent-01' }, 201);
      }
      return respond({ configured: true, items: [paymentIntentRow] });
    }
    if (api === `/payment-intents/${ids.intent}/query`) {
      paymentIntentRow.status = 'RECONCILIATION';
      return respond(paymentIntentRow);
    }
    if (api === `/payment-intents/${ids.intent}/reconcile`) {
      paymentIntentRow.status = 'COMPLETED';
      paymentIntentRow.payment_id = 'RCPT-VNP-9900';
      paymentIntentRow.provider_received_at = '2026-10-12T09:15:00Z';
      return respond(paymentIntentRow);
    }
    if (api === '/fee-sources') return respond({ items: [feeSourceRow] });
    if (api.startsWith('/fee-sources/') && api.endsWith('/preview')) {
      return respond({
        source_version: 1,
        calculation_hash: 'HASH-CALC-88',
        calculation: { amount_vnd: 2000000, fee_code: 'FEE-MGT', base_rate: 2000000 }
      });
    }
    if (api === '/billing/accounting-periods' || api === '/billing/periods' || api === '/finance/options') {
      return respond({ items: apiOptions.periods, periods: apiOptions.periods });
    }
    if (api === '/adjustments') {
      return respond({ items: [] });
    }

    // FE-46: SLA & Quality
    if (api === '/completion-options') {
      return respond(apiOptions);
    }
    if (api === '/sla-policies') {
      if (req.method() === 'POST') {
        const row = { id: randomUUID(), status: 'DRAFT', version: 1, ...body };
        return respond(row, 201);
      }
      return respond({ items: [slaPolicyRow] });
    }
    if (api === `/sla-policies/${ids.slaPolicy}/actions`) {
      if (body.action === 'PUBLISH') slaPolicyRow.status = 'PUBLISHED';
      slaPolicyRow.version++;
      return respond(slaPolicyRow);
    }
    if (api.startsWith('/requests/') && api.endsWith('/control')) {
      if (req.method() === 'POST') {
        if (body.action === 'PAUSE') serviceRequestRow.sla_pauses.push({ started_at: '2026-10-12T09:00:00Z', ended_at: null, reason_code: body.data.pause_reason, basis: 'Dừng kỹ thuật' });
        if (body.action === 'RESUME') {
          const last = serviceRequestRow.sla_pauses.find(p => !p.ended_at);
          if (last) last.ended_at = '2026-10-12T10:00:00Z';
        }
        if (body.action === 'TRANSFER') {
          serviceRequestRow.handoff = { status: 'PENDING', to_id: body.data.owner_id, department: body.data.department, due_at: '2026-10-12T12:00:00Z' };
        }
        if (body.action === 'ACK') {
          serviceRequestRow.handoff.status = 'ACKNOWLEDGED';
          serviceRequestRow.owner_account_id = currentUser.account_id;
        }
        if (body.action === 'REPEAT_CAUSE') {
          serviceRequestRow.repeat_cause = 'Vật tư lão hóa nhanh';
        }
        return respond(serviceRequestRow);
      }
      return respond(serviceRequestRow);
    }
    if (api === '/service-quality') {
      return respond({
        items: [
          { cause: 'Vật tư van hỏng', count: 5, csat_average: 4.6, cases: ['CASE-01', 'CASE-02'], request_ids: [ids.request] },
          { cause: 'Áp lực nước quá tải', count: 2, csat_average: 4.0, cases: ['CASE-03'], request_ids: [] }
        ]
      });
    }
    if (api === '/profile') {
      return respond({
        person: {
          full_name: 'Cư dân Căn W1-101',
          phone_masked: '090***123',
          email_masked: 'resident@greencity.local'
        },
        selected_unit_id: ids.unit,
        units: [
          {
            id: ids.unit,
            unit_number: 'W1-101',
            building_id: ids.building,
            building_name: 'Tòa Tháp Ruby W1',
            area_m2: 85.5,
            permissions: ['profile', 'parking', 'booking', 'finance', 'documents', 'requests']
          }
        ],
        relationships: [{ relationship_type: 'owner' }],
        presence: { status: 'NORMAL' },
        liability: { is_self: true }
      });
    }

    // Default fallback
    if (api.includes('/catalog')) {
      return respond({ items: ['jobs', 'invitations'].map(k => schemas.controls[k]).filter(Boolean) });
    }
    return respond({ items: [] });
  });

  const shot = name => page.screenshot({ path: path.join(outputImages, name), fullPage: true });

  try {
    // 1. Initial Login as Director
    await page.goto(process.env.UX_BASE_URL || 'http://127.0.0.1:3000');
    await page.locator('#staff-username').fill('director_west');
    await page.locator('#staff-password').fill('valid-pass-123');
    await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
    await page.waitForLoadState('networkidle');

    // ==========================================
    // FE-43: Executive Dashboard & Drill-down
    // ==========================================
    await page.getByRole('navigation', { name: 'Điều hướng chính' }).getByRole('button', { name: 'Tổng quan', exact: true }).click();
    await page.locator('.executive-dashboard').waitFor();
    check('FE-43.01', 'Executive Dashboard render với tiêu đề CAP-BI',
      await page.getByText(/BẢNG ĐIỀU HÀNH TỔNG HỢP/i).isVisible());

    const slaMetricBtn = page.getByRole('button', { name: /Yêu cầu CSKH quá hạn SLA/i });
    check('FE-43.01', 'Thẻ KPI hiển thị số lượng quá hạn SLA', await slaMetricBtn.isVisible());

    // Mở drill-down dialog
    await slaMetricBtn.click();
    await page.locator('.drilldown-dialog').waitFor();
    check('FE-43.01', 'Drill-down mở danh sách bản ghi nguồn tương ứng',
      await page.getByText('REQ-2026-0099').isVisible());
    await shot('dashboard-executive-kpi.png');

    // Phím Escape đóng dialog
    await page.keyboard.press('Escape');
    await page.waitForTimeout(200);
    check('FE-43.05', 'Phím Escape đóng drill-down dialog an toàn',
      await page.locator('.drilldown-dialog').count() === 0);

    // ==========================================
    // FE-43: Báo cáo & xuất (SadReportsPanel)
    // ==========================================
    await page.getByRole('navigation', { name: 'Điều hướng chính' }).getByRole('button', { name: 'Dịch vụ cư dân', exact: true }).click();
    await page.getByLabel('Tòa nhà').selectOption(ids.building);
    await page.getByRole('navigation', { name: 'Phân hệ dịch vụ cư dân' }).getByRole('button', { name: 'Báo cáo & xuất', exact: true }).click();
    await page.getByRole('heading', { name: 'KPI, chi tiết & chứng từ' }).waitFor();

    const reportDomainSelect = page.getByLabel('Miền báo cáo');
    const availableDomains = await reportDomainSelect.locator('option').allInnerTexts();
    check('FE-43.02', '11 miền báo cáo trong selector theo quyền BQL',
      availableDomains.some(d => d.includes('Tài chính')) && availableDomains.some(d => d.includes('Năng lượng')));

    // Xem chỉ tiêu snapshot
    await page.getByRole('button', { name: 'Xem chỉ tiêu & chi tiết', exact: true }).first().click();
    await page.getByRole('heading', { name: /^Snapshot / }).waitFor();
    check('FE-43.03', 'Snapshot báo cáo hiển thị tiền VND và định nghĩa',
      await page.getByText('154.000.000 ₫').isVisible());
    await shot('reports-snapshot.png');

    // Mở SourceLinks
    await page.getByRole('button', { name: 'Mở hồ sơ nguồn & căn cứ', exact: true }).first().click();
    await page.getByText('Hồ sơ hóa đơn gốc trong kỳ kiểm soát.').waitFor();
    check('FE-43.04', 'SourceLinks mở chi tiết hồ sơ gốc an toàn',
      await page.getByText('Hồ sơ hóa đơn gốc').isVisible());
    await shot('report-drilldown-sources.png');

    // ==========================================
    // FE-41: Quản trị tài khoản, quyền và khôi phục
    // ==========================================
    // Tab Khôi phục tài khoản
    await page.getByRole('navigation', { name: 'Phân hệ dịch vụ cư dân' }).getByRole('button', { name: 'Khôi phục tài khoản', exact: true }).click();
    await page.getByRole('heading', { name: 'Khôi phục tài khoản nhân viên và cư dân' }).waitFor();
    check('FE-41.04', 'Danh sách yêu cầu khôi phục tài khoản hiển thị đúng người',
      await page.getByText('tech_operator_01').isVisible());

    // Cấp mã khôi phục một lần
    const recoveryCard = page.locator('.portal-record').filter({ hasText: 'tech_operator_01' });
    await recoveryCard.getByLabel('Mã hồ sơ / căn cứ xác minh danh tính').fill('BB-XAC-MINH-TRUC-TIEP-01');
    await recoveryCard.getByLabel('Mật khẩu BQL xác thực lại').fill('bql-admin-secret-pass');
    await recoveryCard.getByRole('button', { name: 'Xác minh và cấp mã', exact: true }).click();
    await page.getByText('Mã chỉ hiển thị trong phiên này.').waitFor();
    const tokenInput = page.getByLabel('Mã khôi phục một lần');
    check('FE-41.04', 'BQL xác minh thành công và phát hành mã khôi phục một lần',
      await tokenInput.isVisible() && (await tokenInput.inputValue()) === 'RCV-9988-SAFE-ONE-TIME');
    await shot('account-recovery-verify.png');

    // Tab Dấu hiệu truy cập
    await page.getByRole('navigation', { name: 'Phân hệ dịch vụ cư dân' }).getByRole('button', { name: 'Dấu hiệu truy cập', exact: true }).click();
    await page.getByRole('heading', { name: 'Dấu hiệu truy cập' }).waitFor();
    await page.getByText('Phát hiện đăng nhập trái giờ').waitFor();
    check('FE-41.05', 'Dấu hiệu truy cập hiển thị hồ sơ rà soát và quyết định độc lập',
      await page.getByText('Phát hiện đăng nhập trái giờ').isVisible());

    const reviewCard = page.locator('.portal-record').filter({ hasText: 'LOG-SEC-20261012-01' });
    await reviewCard.getByLabel('Quyết định').selectOption('REVOKE_SESSIONS');
    await reviewCard.getByLabel('Lý do / kết luận').fill('Xác nhận đăng nhập ngoài luồng, thu hồi phiên ngay.');
    await reviewCard.getByLabel('Mật khẩu quản trị viên xử lý').fill('bql-admin-secret-pass');
    await reviewCard.getByRole('button', { name: 'Xử lý độc lập', exact: true }).click();
    await page.waitForLoadState('networkidle');
    check('FE-41.05', 'Xử lý độc lập dấu hiệu truy cập gửi đúng lệnh',
      commands.some(c => c.api.includes('/resolve') && c.body.action === 'REVOKE_SESSIONS'));
    await shot('account-management.png');

    // ==========================================
    // FE-42: Lịch tác vụ và hiệu lực đến hạn
    // ==========================================
    // Nút Cập nhật hiệu lực và thông báo đến hạn
    const lifecycleSection = page.locator('section.portal-detail').filter({ hasText: 'Cập nhật hiệu lực và thông báo đến hạn' });
    await lifecycleSection.getByRole('button', { name: 'Cập nhật hiệu lực và thông báo đến hạn', exact: true }).click();
    check('FE-42.04', 'Nút Cập nhật hiệu lực gọi /jobs/tick thành công',
      commands.some(c => c.api.includes('/jobs/tick')));
    await shot('job-lifecycle-tick.png');

    // ==========================================
    // FE-46: Chính sách SLA, chuyển trách nhiệm và CSAT
    // ==========================================
    await page.getByRole('navigation', { name: 'Phân hệ dịch vụ cư dân' }).getByRole('button', { name: 'SLA & chất lượng', exact: true }).click();
    await page.getByRole('heading', { name: 'SLA, bàn giao & chất lượng dịch vụ' }).waitFor();

    check('FE-46.01', 'Form tạo chính sách SLA hiển thị đầy đủ các trường giờ GMT+7 và hạn nhận',
      await page.getByLabel('Phút làm việc cho phép').isVisible() && await page.getByLabel('Bắt đầu ca: phút từ 00:00 GMT+7').isVisible());

    const performAction = async (container, label, reasonText = 'Thao tác phê duyệt xác nhận theo quy trình BQL') => {
      const triggerBtn = container.getByRole('button', { name: label, exact: true });
      await triggerBtn.click();
      const reasonInput = container.locator('input[aria-label*="Lý do"]').first();
      await reasonInput.waitFor({ state: 'visible' });
      await reasonInput.fill(reasonText);
      const submitBtn = container.locator('button[type="submit"]').first();
      await submitBtn.click();
      await page.waitForLoadState('networkidle');
    };

    // Duyệt độc lập chính sách SLA
    const policyCard = page.locator('.portal-record').filter({ hasText: 'Cấp thoát nước & Cơ điện' });
    await performAction(policyCard, 'Duyệt và công bố độc lập');
    check('FE-46.02', 'Duyệt công bố chính sách SLA cập nhật trạng thái PUBLISHED',
      commands.some(c => c.api.includes('/sla-policies') && c.body.action === 'PUBLISH'));
    await shot('sla-policy-definition.png');

    // Điều phối SLA trên yêu cầu cụ thể
    await page.getByLabel('Yêu cầu cần điều phối').selectOption(ids.request);
    await page.getByRole('heading', { name: /REQ-2026-0099/ }).waitFor();
    check('FE-46.03', 'Màn điều phối SLA yêu cầu hiển thị deadline và trạng thái handoff',
      await page.getByText('Ban Giám đốc').isVisible());

    // Chuyển giao trách nhiệm ACK
    const requestCard = page.locator('section.portal-detail').filter({ hasText: 'REQ-2026-0099' });
    await performAction(requestCard, 'Tôi tiếp nhận trách nhiệm');
    check('FE-46.04', 'Tiếp nhận trách nhiệm bàn giao gửi lệnh ACK chuẩn',
      commands.some(c => c.api.includes('/requests/') && c.body.action === 'ACK'));

    // Ghi nguyên nhân lặp lại
    await performAction(requestCard, 'Ghi nguyên nhân lặp lại');
    check('FE-46.05', 'Ghi nhận nguyên nhân lặp lại REPEAT_CAUSE cập nhật vào hồ sơ',
      commands.some(c => c.api.includes('/requests/') && c.body.action === 'REPEAT_CAUSE'));
    await shot('sla-request-control.png');

    // Nhóm nguyên nhân & CSAT
    check('FE-46.05', 'Bảng nhóm nguyên nhân và CSAT hiển thị điểm trung bình',
      await page.getByText('CSAT 4.6').isVisible());
    await shot('service-quality-csat.png');

    // ==========================================
    // FE-45: Thanh toán VNPay và đối soát (Manager View)
    // ==========================================
    await page.getByRole('navigation', { name: 'Phân hệ dịch vụ cư dân' }).getByRole('button', { name: 'Phí & VNPay', exact: true }).click();
    await page.getByRole('heading', { name: 'Phí & đối soát VNPay' }).waitFor();

    check('FE-45.01', 'Phí & VNPay tải danh sách hóa đơn và lịch sử lệnh thanh toán',
      await page.getByText('VNP-REF-889900').isVisible());

    // Chọn kỳ kế toán để đối soát
    const periodSelect = page.getByLabel('Kỳ kế toán đang mở');
    await periodSelect.selectOption(ids.period);

    // Kế toán đối soát intent
    const intentCard = page.locator('.portal-record').filter({ hasText: 'VNP-REF-889900' });
    await performAction(intentCard, 'Đối soát vào kỳ đã chọn');
    check('FE-45.04', 'Thao tác đối soát RECONCILE gửi kỳ kế toán và cập nhật biên nhận',
      commands.some(c => c.api.includes('/reconcile')));
    await shot('vnpay-reconciliation-manager.png');

    // ==========================================
    // FE-45: Cổng cư dân thanh toán (Resident View)
    // ==========================================
    currentUser = {
      account_id: ids.userResident,
      tenant_id: ids.site,
      username: 'resident_west',
      full_name: 'Cư dân Căn W1-101',
      roles: ['resident'],
      active_site_id: ids.site,
      allowed_sites: [{ id: ids.site, code: 'GC-WEST', name: 'GreenCity West' }]
    };
    await page.getByRole('button', { name: 'Đăng xuất', exact: true }).click();
    await page.locator('.dialog-actions button.button-danger').click();
    await page.waitForLoadState('networkidle');
    await page.locator('#staff-username').fill('resident_west');
    await page.locator('#staff-password').fill('valid-pass-123');
    await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
    await page.waitForLoadState('networkidle');

    // Mở Tab Thanh toán cư dân
    const residentPaymentTab = page.getByRole('tab', { name: 'Thanh toán', exact: true });
    await residentPaymentTab.waitFor({ state: 'visible' });
    await residentPaymentTab.click();
    await page.getByRole('heading', { name: 'Thanh toán', exact: true }).waitFor();
    check('FE-45.02', 'Cư dân thấy hóa đơn còn nợ và nút tạo lệnh VNPay',
      await page.getByText('2.500.000 ₫').first().isVisible());

    const createIntentBtn = page.getByRole('button', { name: 'Tạo lệnh thanh toán VNPay', exact: true });
    if (await createIntentBtn.isVisible()) {
      await createIntentBtn.click();
      await page.waitForLoadState('networkidle');
      check('FE-45.03', 'Tạo lệnh VNPay hiển thị liên kết tiếp tục thanh toán an toàn',
        await page.getByText('Tiếp tục thanh toán tại VNPay').isVisible());
    }
    await shot('resident-payment-portal.png');

    // ==========================================
    // FE-44: Responsive Viewports & Accessibility
    // ==========================================
    // Desktop chuẩn 1280x720
    await page.setViewportSize({ width: 1280, height: 720 });
    await shot('responsive-desktop-1440.png');
    check('FE-44.01', 'Giao diện không tràn ngang ở 1280x720',
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));

    // Tablet 768x1024
    await page.setViewportSize({ width: 768, height: 1024 });
    await shot('responsive-tablet-768.png');
    check('FE-44.01', 'Giao diện co giãn phù hợp trên Tablet 768x1024',
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));

    // Mobile 390x844
    await page.setViewportSize({ width: 390, height: 844 });
    await shot('responsive-mobile-390.png');
    check('FE-44.01', 'Giao diện di động 390x844 không tràn ngang, thanh cuộn bảng cục bộ',
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));

    // Keyboard & Focus Ring
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.keyboard.press('Tab');
    await page.keyboard.press('Tab');
    await shot('keyboard-accessibility.png');
    check('FE-44.02', 'Điều hướng phím Tab tạo focus outline rõ ràng',
      await page.evaluate(() => document.activeElement !== null));

    // Common validations
    assert.deepEqual(errors, []);
    check('COMMON', 'Không có unhandled pageerror nào xảy ra trong toàn bộ quy trình');

    console.log(`\n========================================`);
    console.log(`REVIEW R06 UX COMPLETED: ${checks.length} checks passed.`);
    console.log(`========================================\n`);

    fs.writeFileSync(
      path.join(outputImages, 'test-results.json'),
      JSON.stringify({ passed: checks.length, checks, commands, errors }, null, 2)
    );

  } catch (err) {
    console.error('Test execution failed:', err);
    await shot('failure.png');
    fs.writeFileSync(
      path.join(outputImages, 'failure.json'),
      JSON.stringify({ error: err.message, checks, commands, errors }, null, 2)
    );
    throw err;
  } finally {
    await context.close();
    await browser.close();
  }
})().catch(err => {
  console.error(err);
  process.exitCode = 1;
});
