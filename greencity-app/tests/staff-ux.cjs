const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const { randomUUID } = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

const output = path.resolve(__dirname, '../artifacts/staff-integration');
fs.mkdirSync(output, { recursive: true });

const siteId = randomUUID();
const secondSiteId = randomUUID();
const accountId = randomUUID();
const issuedToken = randomUUID();
const switchedToken = randomUUID();
const correlationId = randomUUID();
const user = {
  account_id: accountId,
  tenant_id: randomUUID(),
  username: 'cskh.browser',
  full_name: 'CSKH Trình Duyệt',
  roles: ['cskh'],
  active_site_id: siteId,
  allowed_sites: [
    { id: siteId, code: 'CENTRAL', name: 'GreenCity Central' },
    { id: secondSiteId, code: 'EAST', name: 'GreenCity East' },
  ],
};
const switchedUser = { ...user, active_site_id: secondSiteId };
const serviceRequest = {
  id: randomUUID(),
  code: 'SR-BROWSER-001',
  title: 'Kiểm tra đèn hành lang',
  unit_id: randomUUID(),
  unit_number: 'A-1201',
  building_id: randomUUID(),
  building_code: 'A',
  building_name: 'Tòa A',
  status: 'IN_PROGRESS',
  priority: 'HIGH',
  sla_deadline: '2026-09-13T02:00:00Z',
  created_at: '2026-09-12T01:00:00Z',
};
const unit360 = {
  id: serviceRequest.unit_id,
  unit_number: 'A-1201',
  floor: 12,
  area_m2: 72.5,
  status: 'OCCUPIED',
  version: 3,
  building_id: serviceRequest.building_id,
  building_code: 'A',
  building_name: 'Tòa A',
  site_id: siteId,
  site_code: 'CENTRAL',
  site_name: 'GreenCity Central',
  residents_visible: true,
  residents: [{
    person_id: randomUUID(), full_name: 'Nguyễn Minh Anh', phone_masked: '09******12',
    email_masked: 'n***@example.test', relationship_type: 'owner', is_active: true,
    ownership_ratio: '1.0000', valid_from: '2025-01-01', valid_to: null,
  }],
};
const serviceRequestFormOptions = {
  buildings: [{ id: serviceRequest.building_id, code: serviceRequest.building_code, name: serviceRequest.building_name }],
  categories: [{ id: randomUUID(), code: 'TECHNICAL', name: 'Kỹ thuật', building_id: serviceRequest.building_id }],
  units: [{ id: serviceRequest.unit_id, unit_number: serviceRequest.unit_number, building_id: serviceRequest.building_id }],
};
const createdServiceRequest = {
  id: randomUUID(), code: 'SR-BROWSER-CREATED', title: 'Đèn hành lang không sáng', priority: 'HIGH', status: 'NEW',
};

(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'vi-VN' });
  const page = await context.newPage();
  const errors = [];
  const checks = [];
  const requests = [];
  let listMode = 'slow-success';
  let unitMode = 'slow-success';
  let switchMode = 'success';
  let createRequestCount = 0;
  const check = (name, value = true) => { assert.ok(value, name); checks.push(name); console.log(`PASS ${name}`); };
  page.on('pageerror', error => errors.push(error.message));

  await context.route('**/api/v1/**', async route => {
    const request = route.request();
    const url = new URL(request.url());
    requests.push({ path: url.pathname, search: url.search, method: request.method(), body: request.postDataJSON?.(), authorization: request.headers().authorization, idempotencyKey: request.headers()['idempotency-key'] });
    const headers = { 'Content-Type': 'application/json', 'X-Correlation-ID': correlationId };
    if (url.pathname.endsWith('/auth/login')) return route.fulfill({ status: 200, headers, body: JSON.stringify({ access_token: issuedToken, token_type: 'Bearer', user: { ...user, roles: ['admin'] } }) });
    if (url.pathname.endsWith('/auth/me')) return route.fulfill({ status: 200, headers, body: JSON.stringify(request.headers().authorization === `Bearer ${switchedToken}` ? switchedUser : user) });
    if (url.pathname.endsWith('/auth/switch-site')) {
      if (switchMode === 'scope') return route.fulfill({ status: 404, headers, body: JSON.stringify({ error: { code: 'ERR-SCOPE-NOTFOUND', message: 'Không tìm thấy dữ liệu.', correlation_id: correlationId } }) });
      return route.fulfill({ status: 200, headers, body: JSON.stringify({ access_token: switchedToken, token_type: 'Bearer', user: { ...switchedUser, roles: ['admin'] } }) });
    }
    if (url.pathname.endsWith('/service-request-form-options')) {
      const requestedBuildingId = url.searchParams.get('building_id');
      const body = requestedBuildingId
        ? serviceRequestFormOptions
        : { buildings: serviceRequestFormOptions.buildings, categories: [], units: [] };
      return route.fulfill({ status: 200, headers, body: JSON.stringify(body) });
    }
    if (url.pathname.endsWith('/service-requests')) {
      if (request.method() === 'POST') {
        createRequestCount += 1;
        await new Promise(resolve => setTimeout(resolve, 200));
        return route.fulfill({ status: 201, headers, body: JSON.stringify(createdServiceRequest) });
      }
      if (listMode === 'slow-success') await new Promise(resolve => setTimeout(resolve, 700));
      if (listMode === 'network') return route.abort('failed');
      if (listMode === 'scope') return route.fulfill({ status: 404, headers, body: JSON.stringify({ error: { code: 'ERR-SCOPE-NOTFOUND', message: 'Không tìm thấy dữ liệu.', correlation_id: correlationId } }) });
      if (listMode === 'unauthorized') return route.fulfill({ status: 401, headers, body: JSON.stringify({ error: { code: 'ERR-UNAUTHORIZED', message: 'Phiên hết hạn.', correlation_id: correlationId } }) });
      const items = listMode === 'empty' ? [] : [serviceRequest];
      const responsePage = Number(url.searchParams.get('page') || 1);
      return route.fulfill({ status: 200, headers, body: JSON.stringify({ items, page: responsePage, page_size: 20, total: items.length ? 21 : 0 }) });
    }
    if (/\/units\/[^/]+\/360$/.test(url.pathname)) {
      if (unitMode === 'slow-success') await new Promise(resolve => setTimeout(resolve, 700));
      if (unitMode === 'network') return route.abort('failed');
      if (unitMode === 'scope') return route.fulfill({ status: 404, headers, body: JSON.stringify({ error: { code: 'ERR-SCOPE-NOTFOUND', message: 'Không tìm thấy dữ liệu.', correlation_id: correlationId } }) });
      if (unitMode === 'unauthorized') return route.fulfill({ status: 401, headers, body: JSON.stringify({ error: { code: 'ERR-UNAUTHORIZED', message: 'Phiên hết hạn.', correlation_id: correlationId } }) });
      const requestedId = decodeURIComponent(url.pathname.split('/').at(-2));
      return route.fulfill({ status: 200, headers, body: JSON.stringify({ ...unit360, id: requestedId }) });
    }
    return route.fulfill({ status: 404, headers, body: JSON.stringify({ error: { code: 'ERR-NOTFOUND', message: 'Không tìm thấy.', correlation_id: correlationId } }) });
  });

  try {
    const url = process.env.UX_BASE_URL || 'http://127.0.0.1:3000/';
    await page.goto(url);
    await page.waitForLoadState('networkidle');
    check('real credential form is the initial surface', await page.getByRole('heading', { name: 'Đăng nhập không gian làm việc' }).isVisible());
    check('no account or role picker is rendered', await page.locator('select,#staff-account').count() === 0);
    check('password input accepts credentials', await page.locator('#staff-password').isEnabled());

    await page.locator('#staff-username').fill('cskh.browser');
    await page.locator('#staff-password').fill('browser-only-password');
    await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
    await page.getByRole('heading', { name: 'Tiếp nhận & chăm sóc cư dân' }).waitFor();
    await page.getByRole('navigation', { name: 'Điều hướng chính' }).getByRole('button', { name: 'Công việc & Yêu cầu', exact: true }).click();
    check('loading state is visible while the scoped request is pending', await page.getByText('Đang tải yêu cầu đúng phạm vi…', { exact: true }).isVisible());
    await page.getByText('SR-BROWSER-001', { exact: true }).waitFor();

    check('request order is login then me then service list', requests.slice(0, 3).map(item => item.path).join('|') === '/api/v1/auth/login|/api/v1/auth/me|/api/v1/service-requests');
    check('login sends only username and password', JSON.stringify(Object.keys(requests[0].body).sort()) === JSON.stringify(['password', 'username']));
    check('/auth/me and list receive the Bearer session', requests[1].authorization === `Bearer ${issuedToken}` && requests[2].authorization === `Bearer ${issuedToken}`);
    check('menu comes from /auth/me rather than login response user', await page.getByRole('button', { name: 'Quản trị hệ thống', exact: true }).count() === 0 && await page.getByText('CSKH · Phiên xác thực', { exact: true }).isVisible());
    const rowText = await page.locator('tbody tr').first().innerText();
    check('read-only row renders code, building, unit, priority and status', ['SR-BROWSER-001', 'Tòa A · Căn A-1201', 'Cao', 'Đang xử lý'].every(value => rowText.includes(value)));
    check('issued token is absent from browser storage', await page.evaluate(token => !JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage } }).includes(token), issuedToken));
    const pageTwoRequest = page.waitForRequest(request => request.url().includes('/service-requests?page=2&page_size=20'));
    await page.getByRole('button', { name: 'Trang sau', exact: true }).click();
    await pageTwoRequest;
    await page.getByText('Trang 2 / 2', { exact: true }).waitFor();
    check('pagination is executed on the server without scope query parameters', requests.some(item => item.path.endsWith('/service-requests') && item.search === '?page=2&page_size=20') && requests.filter(item => item.path.endsWith('/service-requests')).every(item => !/tenant_id|building_id|role=/.test(item.search)));
    const pageOneRequest = page.waitForRequest(request => request.url().includes('/service-requests?page=1&page_size=20'));
    await page.getByRole('button', { name: 'Trang trước', exact: true }).click();
    await pageOneRequest;
    await page.getByText('Trang 1 / 2', { exact: true }).waitFor();
    await page.getByText('Đang tải yêu cầu đúng phạm vi…', { exact: true }).waitFor({ state: 'hidden' });
    await page.screenshot({ path: path.join(output, '01-service-list.png'), fullPage: true });

    const initialFormOptionsRequest = page.waitForRequest(request => request.url().endsWith('/service-request-form-options'));
    await page.getByRole('button', { name: 'Tạo yêu cầu', exact: true }).click();
    await initialFormOptionsRequest;
    await page.locator('#service-request-building').waitFor();
    check('CSKH can open a create-request form with visible labels', await page.getByRole('heading', { name: 'Tạo yêu cầu dịch vụ' }).isVisible() && await page.getByLabel(/Tòa nhà/).isVisible());
    const scopedFormOptionsRequest = page.waitForRequest(request => request.url().includes(`/service-request-form-options?building_id=${serviceRequest.building_id}`));
    await page.locator('#service-request-building').selectOption(serviceRequest.building_id);
    await scopedFormOptionsRequest;
    await page.locator('#service-request-category').selectOption(serviceRequestFormOptions.categories[0].id);
    await page.locator('#service-request-unit').selectOption(serviceRequest.unit_id);
    await page.locator('#service-request-priority').selectOption('HIGH');
    await page.locator('#service-request-title').fill(createdServiceRequest.title);
    await page.locator('#service-request-description').fill('Cần kiểm tra bóng đèn và công tắc khu vực hành lang.');
    const createRequestPromise = page.waitForRequest(request => request.url().endsWith('/service-requests') && request.method() === 'POST');
    await page.locator('dialog[open]').getByRole('button', { name: 'Tạo yêu cầu', exact: true }).dblclick();
    await createRequestPromise;
    await page.getByText(`Đã tạo yêu cầu ${createdServiceRequest.code}.`, { exact: true }).waitFor();
    const formRequests = requests.filter(item => item.path.endsWith('/service-request-form-options'));
    const createRequest = requests.find(item => item.path.endsWith('/service-requests') && item.method === 'POST');
    check('form options and submit keep scope server-owned', formRequests.some(item => item.search === '')
      && formRequests.some(item => item.search === `?building_id=${serviceRequest.building_id}`)
      && formRequests.every(item => item.authorization === `Bearer ${issuedToken}` && !/tenant_id|site_id|role=/.test(item.search))
      && createRequest?.authorization === `Bearer ${issuedToken}`
      && Boolean(createRequest?.idempotencyKey)
       && JSON.stringify(Object.keys(createRequest.body).sort()) === JSON.stringify(['building_id', 'category_id', 'description', 'priority', 'title', 'unit_id'])
       && !JSON.stringify(createRequest.body).match(/tenant_id|site_id|role/));
    check('rapid double submit creates only one request', createRequestCount === 1);

    listMode = 'empty';
    await page.getByRole('button', { name: 'Mới tiếp nhận', exact: true }).click();
    await page.getByRole('heading', { name: 'Không có yêu cầu phù hợp' }).waitFor();
    await page.getByRole('button', { name: 'Hiển thị tất cả yêu cầu', exact: true }).click();
    await page.getByRole('heading', { name: 'Chưa có yêu cầu trong phạm vi' }).waitFor();
    check('filtered and unfiltered empty states are distinct');

    listMode = 'network';
    await page.getByRole('button', { name: 'Đang xử lý', exact: true }).click();
    await page.getByRole('alert').filter({ hasText: 'Mất kết nối tới máy chủ' }).waitFor();
    check('network error exposes retry and a correlation identifier', await page.getByRole('button', { name: 'Thử lại', exact: true }).isVisible() && await page.getByText(/Mã đối chiếu:/).isVisible());
    listMode = 'success';
    await page.getByRole('button', { name: 'Thử lại', exact: true }).click();
    await page.getByText('SR-BROWSER-001', { exact: true }).waitFor();
    check('retry recovers the service-request list');

    listMode = 'scope';
    await page.getByRole('button', { name: 'Đã phân loại', exact: true }).click();
    await page.getByRole('alert').filter({ hasText: 'Chưa xác định được phạm vi dữ liệu' }).waitFor();
    check('ERR-SCOPE-NOTFOUND is shown without silently falling back to mock data');

    await page.getByRole('navigation', { name: 'Điều hướng chính' }).getByRole('button', { name: 'Khách hàng & Cư dân', exact: true }).click();
    check('Unit 360 starts with an actionable empty state', await page.getByRole('heading', { name: 'Chưa có căn hộ được chọn' }).isVisible());
    await page.locator('#unit-lookup-id').fill(serviceRequest.unit_id);
    await page.getByRole('button', { name: 'Tra cứu', exact: true }).click();
    check('Unit 360 loading state is announced', await page.getByText('Đang tải căn hộ đúng phạm vi…', { exact: true }).isVisible());
    await page.getByRole('heading', { name: 'Căn A-1201' }).waitFor();
    const unitRequest = requests.find(item => item.path.endsWith(`/units/${serviceRequest.unit_id}/360`));
    check('Unit lookup sends only the ID path with Bearer auth', unitRequest?.search === '' && unitRequest?.authorization === `Bearer ${issuedToken}` && !/tenant_id|site_id|building_id|role=/.test(unitRequest.path + unitRequest.search));
    check('Unit projection renders masked resident data', await page.getByText('Nguyễn Minh Anh', { exact: true }).isVisible() && await page.getByText(/09\*{6}12/).isVisible());

    switchMode = 'scope';
    const rejectedSwitchRequest = page.waitForRequest(request => request.url().endsWith('/auth/switch-site'));
    await page.getByLabel('Site đang hoạt động').selectOption(secondSiteId);
    await rejectedSwitchRequest;
    await page.getByRole('alert').filter({ hasText: 'Site này không còn nằm trong phạm vi phiên hiện tại.' }).waitFor();
    await page.getByRole('heading', { name: 'Chưa có căn hộ được chọn' }).waitFor();
    check('rejected site switch keeps the old scope and clears the prior Unit 360 result',
      await page.locator('#active-site-select').inputValue() === siteId
      && await page.locator('#unit-lookup-id').inputValue() === ''
      && await page.getByRole('heading', { name: 'Căn A-1201' }).count() === 0);

    switchMode = 'success';
    const switchRequestPromise = page.waitForRequest(request => request.url().endsWith('/auth/switch-site'));
    const refreshedMeResponsePromise = page.waitForResponse(response => (
      response.url().endsWith('/auth/me')
      && response.request().method() === 'GET'
      && response.request().headers().authorization === `Bearer ${switchedToken}`
      && response.status() === 200
    ));
    await page.getByLabel('Site đang hoạt động').selectOption(secondSiteId);
    await switchRequestPromise;
    await refreshedMeResponsePromise;
    await page.getByLabel('Site đang hoạt động').waitFor();
    await page.waitForFunction(site => document.querySelector('#active-site-select')?.value === site, secondSiteId);
    const switchRequest = requests.filter(item => item.path.endsWith('/auth/switch-site')).at(-1);
    const switchIndex = requests.indexOf(switchRequest);
    check('site switch sends only site_id with the current Bearer token', JSON.stringify(Object.keys(switchRequest.body)) === JSON.stringify(['site_id']) && switchRequest.body.site_id === secondSiteId && switchRequest.authorization === `Bearer ${issuedToken}`);
    check('site switch always refreshes /auth/me with the newly issued token', requests.slice(switchIndex + 1).some(item => item.path.endsWith('/auth/me') && item.authorization === `Bearer ${switchedToken}`));
    check('switching site remounts Unit 360 and clears its prior lookup', await page.getByRole('heading', { name: 'Chưa có căn hộ được chọn' }).isVisible() && await page.locator('#unit-lookup-id').inputValue() === '');

    unitMode = 'network';
    await page.locator('#unit-lookup-id').fill(randomUUID());
    await page.getByRole('button', { name: 'Tra cứu', exact: true }).click();
    await page.getByRole('alert').filter({ hasText: 'Mất kết nối tới máy chủ' }).waitFor();
    check('Unit network failure shows retry and correlation ID', await page.getByRole('button', { name: 'Thử lại', exact: true }).isVisible() && await page.getByText(/Mã đối chiếu:/).isVisible());
    unitMode = 'success';
    await page.getByRole('button', { name: 'Thử lại', exact: true }).click();
    await page.getByRole('heading', { name: 'Căn A-1201' }).waitFor();
    check('Unit retry recovers the read-only profile');

    unitMode = 'scope';
    await page.locator('#unit-lookup-id').fill(randomUUID());
    await page.getByRole('button', { name: 'Tra cứu', exact: true }).click();
    await page.getByRole('alert').filter({ hasText: 'Không tìm thấy căn hộ trong phạm vi' }).waitFor();
    check('Unit ERR-SCOPE-NOTFOUND does not reveal whether the record exists');

    unitMode = 'unauthorized';
    await page.locator('#unit-lookup-id').fill(randomUUID());
    await page.getByRole('button', { name: 'Tra cứu', exact: true }).click();
    await page.getByRole('heading', { name: 'Đăng nhập không gian làm việc' }).waitFor();
    check('Unit 401 clears the UI session and returns to login', await page.getByText(/Phiên đã hết hạn/).isVisible());
    check('no runtime JavaScript errors', errors.length === 0);

    fs.writeFileSync(path.join(output, 'test-results.json'), JSON.stringify({ passed: checks.length, checks, errors }, null, 2));
    console.log(`STAFF INTEGRATION UX: ${checks.length} checks passed.`);
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
