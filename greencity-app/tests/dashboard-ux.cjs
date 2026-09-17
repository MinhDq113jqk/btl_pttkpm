const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { randomUUID } = require('node:crypto');

const output = path.resolve(__dirname, '../artifacts/dashboard-ux');
fs.mkdirSync(output, { recursive: true });

(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'vi-VN' });
  const page = await context.newPage();
  const checks = [];
  const errors = [];
  const check = (name, value = true) => { assert.ok(value, name); checks.push(name); console.log(`PASS ${name}`); };
  page.on('pageerror', error => errors.push(error.message));

  const siteId = randomUUID();
  let currentRole = 'director';
  let shouldFailDashboard = false;
  let shouldLoseDashboardConnection = false;
  const dashboardRequests = [];
  const cutoff = '2026-09-15T02:00:00Z';
  const incidentId = randomUUID();
  const bldgId = randomUUID();
  const corrAuditId = randomUUID();
  let auditRequest;

  await context.route('**/api/v1/**', async route => {
    const request = route.request();
    const url = new URL(request.url());
    const headers = { 'Content-Type': 'application/json', 'X-Correlation-ID': randomUUID() };
    const respond = (payload, status = 200) => route.fulfill({ status, headers, body: JSON.stringify(payload) });

    if (url.pathname.endsWith('/auth/login')) return respond({ access_token: 'valid-token' });
    if (url.pathname.endsWith('/auth/me')) {
      return respond({
        account_id: randomUUID(),
        tenant_id: randomUUID(),
        username: `${currentRole}.ux`,
        full_name: `Tài khoản ${currentRole}`,
        roles: [currentRole],
        active_site_id: siteId,
        allowed_sites: [{ id: siteId, code: 'CENTRAL', name: 'GreenCity Central' }],
      });
    }
    if (url.pathname.endsWith('/service-requests')) return respond({ items: [], page: 1, page_size: 20, total: 0 });
    if (url.pathname.endsWith('/notifications')) return respond({ items: [] });
    if (url.pathname.endsWith('/outbox/events')) return respond({ items: [] });

    // Dashboard endpoint
    if (url.pathname.endsWith('/dashboard')) {
      dashboardRequests.push(url);
      if (!['admin', 'director'].includes(currentRole)) {
        return respond({ error: { code: 'ERR-FORBIDDEN', message: 'Forbidden' } }, 403);
      }
      if (shouldLoseDashboardConnection) return route.abort('connectionreset');
      if (shouldFailDashboard) {
        return respond({
          error: {
            code: 'ERR-DOWNSTREAM',
            message: 'Không thể kết nối cơ sở dữ liệu phân tích tại mốc cutoff.',
            correlation_id: 'err-test-correlation-uuid',
          },
        }, 500);
      }
      return respond({
        as_of: cutoff,
        sla_overdue_count: 3,
        maintenance_due_count: 2,
        cleaning_rework_count: 1,
        open_incident_count: 4,
        ar_debt_vnd: 15400000,
      });
    }

    // Drill-down endpoint
    const drillMatch = url.pathname.match(/\/dashboard\/drill-down\/([^/]+)$/);
    if (drillMatch) {
      const metric = drillMatch[1];
      if (!['admin', 'director'].includes(currentRole)) {
        return respond({ error: { code: 'ERR-FORBIDDEN', message: 'Forbidden' } }, 403);
      }
      return respond({
        as_of: cutoff,
        metric,
        items: [
          {
            metric,
            resource_type: 'SecurityIncident',
            resource_id: incidentId,
            building_id: bldgId,
            reference: 'INC-2026-09-001',
            title: 'Khói tại phòng máy tầng hầm B1',
            status: 'NEW',
            occurred_at: '2026-09-15T01:15:00Z',
            amount_vnd: null,
          },
          {
            metric,
            resource_type: 'SecurityIncident',
            resource_id: randomUUID(),
            building_id: bldgId,
            reference: 'INC-2026-09-002',
            title: 'Cửa thoát hiểm tầng 5 mở bất thường',
            status: 'INVESTIGATING',
            occurred_at: '2026-09-15T01:45:00Z',
            amount_vnd: null,
          },
        ],
      });
    }

    // Audit-events endpoint
    if (url.pathname.endsWith('/audit-events')) {
      auditRequest = url;
      return respond({
        items: [
          {
            id: randomUUID(),
            actor_account_id: randomUUID(),
            event_type: 'SecurityIncidentReported',
            action: 'CREATE',
            resource_type: 'SecurityIncident',
            resource_id: incidentId,
            building_id: bldgId,
            before_data: null,
            after_data: { severity: 'HIGH', title: 'Khói tại phòng máy' },
            reason: 'Tín hiệu cảm biến PCCC',
            correlation_id: corrAuditId,
            created_at: '2026-09-15T01:15:00Z',
          },
        ],
      });
    }

    return respond({ error: { code: 'ERR-NOTFOUND', message: 'Not found' } }, 404);
  });

  try {
    await page.goto(process.env.UX_BASE_URL || 'http://127.0.0.1:3000/');
    await page.waitForLoadState('networkidle');

    // =========================================================================
    // 1. Test Director Login & Executive KPI Dashboard (AC-25)
    // =========================================================================
    await page.locator('#staff-username').fill('director.ux');
    await page.locator('#staff-password').fill('password');
    await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
    await page.locator('.desktop-shell').waitFor();

    // Verify Executive Dashboard is rendered on overview
    await page.locator('.executive-dashboard').waitFor();
    check('Director sees Executive Dashboard', await page.getByText('BẢNG ĐIỀU HÀNH TỔNG HỢP CAP-BI (R5)').isVisible());
    check('Scope banner shows active site', await page.getByRole('heading', { name: 'GreenCity Central' }).isVisible());

    // Verify 5 real KPI cards
    check('KPI SLA overdue displays 3', await page.getByRole('button', { name: /Yêu cầu CSKH quá hạn SLA.*3/i }).isVisible());
    check('KPI Maintenance due displays 2', await page.getByRole('button', { name: /Bảo trì kỹ thuật đến hạn.*2/i }).isVisible());
    check('KPI Cleaning rework displays 1', await page.getByRole('button', { name: /Vệ sinh cần làm lại.*1/i }).isVisible());
    check('KPI Open incidents displays 4', await page.getByRole('button', { name: /Sự cố an ninh đang mở.*4/i }).isVisible());
    check('KPI AR debt displays currency', await page.getByRole('button', { name: /Tổng công nợ quá hạn/i }).isVisible());

    const dashboardCountBeforeCutoffChange = dashboardRequests.length;
    await page.getByRole('button', { name: 'Đầu ngày UTC', exact: true }).click();
    await page.waitForTimeout(250);
    check('Changing cutoff issues exactly one fresh dashboard request', dashboardRequests.length === dashboardCountBeforeCutoffChange + 1);
    const selectedCutoff = dashboardRequests.at(-1).searchParams.get('as_of');

    await page.screenshot({ path: path.join(output, 'director-kpi-dashboard.png'), fullPage: true });

    // =========================================================================
    // 2. Test Drill-Down Modal & Keyboard ESC (AC-25)
    // =========================================================================
    // Click Open Incidents KPI card
    await page.getByRole('button', { name: /Sự cố an ninh đang mở/i }).click();
    await page.locator('.drilldown-dialog').waitFor();
    check('Drill-down dialog opens on click', await page.getByText('ĐỐI SOÁT BẢN GHI NGUỒN (AC-25)').isVisible());
    check('Drill-down displays source records', await page.getByText('INC-2026-09-001').isVisible());
    check('Drill-down displays second source record', await page.getByText('INC-2026-09-002').isVisible());

    await page.screenshot({ path: path.join(output, 'director-drilldown.png') });

    // Click Audit button in row
    await page.getByRole('button', { name: 'Xem lịch sử thay đổi của tài nguyên này' }).first().click();
    await page.locator('.audit-dialog').waitFor();
    check('Audit Explorer dialog opens from drill-down row', await page.getByText('SecurityIncidentReported').isVisible());
    check('Audit timeline keeps drill-down resource and cutoff filters',
      auditRequest?.searchParams.get('resource_type') === 'SecurityIncident'
      && auditRequest?.searchParams.get('resource_id') === incidentId
      && auditRequest?.searchParams.get('as_of') === selectedCutoff);

    await page.screenshot({ path: path.join(output, 'director-audit-explorer.png') });

    // Close Audit dialog via Escape key (keyboard smoke)
    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);
    check('Escape key closes Audit Explorer', await page.locator('.audit-dialog').count() === 0);

    // Close Drill-down dialog via Escape key
    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);
    check('Escape key closes Drill-down Dialog', await page.locator('.drilldown-dialog').count() === 0);

    // =========================================================================
    // 3. Test Error Handling: NO SILENT MOCK FALLBACK (AC-45)
    // =========================================================================
    shouldFailDashboard = true;
    await page.getByRole('button', { name: 'Làm mới', exact: false }).first().click();
    await page.locator('.request-error').waitFor();
    check('API error displays error alert banner', await page.getByText('Không thể tải bảng điều hành KPI').isVisible());
    check('Error displays correlationId', await page.getByText('err-test-correlation-uuid').isVisible());
    check('Does NOT silently display mock KPI cards during API error', await page.locator('.kpi-grid').count() === 0);

    await page.screenshot({ path: path.join(output, 'dashboard-error-state.png') });

    // Recover from error
    shouldFailDashboard = false;
    await page.getByRole('button', { name: 'Thử lại' }).click();
    await page.locator('.kpi-grid').waitFor();
    check('Retry successfully recovers dashboard', await page.getByRole('button', { name: /Yêu cầu CSKH quá hạn SLA.*3/i }).isVisible());

    shouldLoseDashboardConnection = true;
    await page.getByRole('button', { name: 'Làm mới', exact: false }).first().click();
    await page.getByText('Đang ngoại tuyến').waitFor();
    check('Lost dashboard connection shows offline state and no KPI snapshot', await page.locator('.kpi-grid').count() === 0);
    shouldLoseDashboardConnection = false;
    await page.getByRole('button', { name: 'Kiểm tra lại', exact: true }).click();
    await page.locator('.kpi-grid').waitFor();
    check('Dashboard offline recovery reloads the API snapshot', true);

    // =========================================================================
    // 4. Test Role Visibility: CSKH sees Staff Dashboard, NOT Executive KPI
    // =========================================================================
    currentRole = 'cskh';
    await page.goto(process.env.UX_BASE_URL || 'http://127.0.0.1:3000/');
    await page.locator('#staff-username').fill('cskh.ux');
    await page.locator('#staff-password').fill('password');
    await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
    await page.locator('.desktop-shell').waitFor();

    check('CSKH sees Staff Dashboard', await page.getByText('Ưu tiên trong phạm vi của bạn').isVisible());
    check('CSKH does NOT see Executive KPI Dashboard', await page.locator('.executive-dashboard').count() === 0);

    await page.screenshot({ path: path.join(output, 'cskh-overview.png'), fullPage: true });

    check('No unhandled console errors', errors.length === 0);

    console.log(`DASHBOARD UX: ${checks.length} checks passed.`);
    fs.writeFileSync(path.join(output, 'test-results.json'), JSON.stringify({ passed: checks.length, checks }, null, 2));
  } catch (err) {
    console.error(err);
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
