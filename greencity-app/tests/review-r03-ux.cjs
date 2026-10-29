const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { randomUUID } = require('node:crypto');
const { chromium } = require('playwright');
const schemas = require('./fixtures/review-r03-schemas.json');
const output = path.resolve(__dirname, '../../documents/deploy_review/evidence/R03/browser');
const ids = Object.fromEntries(['site', 'buildingA', 'buildingB', 'unitA', 'unitB', 'zoneA', 'zoneB', 'floorA', 'floorB', 'person', 'admin', 'resident', 'parking', 'facility', 'service', 'vehicle', 'card', 'booking', 'enrollment', 'reportA', 'reportB', 'policy', 'feeVersion'].map(key => [key, randomUUID()]));
const buildings = [{ id: ids.buildingA, zone_id: ids.zoneA, code: 'A', name: 'Tòa A', status: 'ACTIVE' }, { id: ids.buildingB, zone_id: ids.zoneB, code: 'B', name: 'Tòa B', status: 'ACTIVE' }];
const units = [{ id: ids.unitA, building_id: ids.buildingA, unit_number: 'A-101', area_m2: 70 }, { id: ids.unitB, building_id: ids.buildingB, unit_number: 'B-201', area_m2: 60 }];
let nodes = [
  { id: ids.zoneA, code: 'ZA', name: 'Phân khu A', kind: 'ZONE', status: 'ACTIVE', version: 1 },
  { id: ids.zoneB, code: 'ZB', name: 'Phân khu B', kind: 'ZONE', status: 'ACTIVE', version: 1 },
  { id: ids.floorA, code: 'FA', name: 'Tầng A1', kind: 'FLOOR', building_id: ids.buildingA, parent_id: ids.zoneA, status: 'ACTIVE', version: 1 },
  { id: ids.floorB, code: 'FB', name: 'Tầng B2', kind: 'FLOOR', building_id: ids.buildingB, parent_id: ids.zoneB, status: 'ACTIVE', version: 1 },
];
let resources = [
  { id: ids.parking, kind: 'PARKING', name: 'Bãi A', building_id: ids.buildingA, status: 'OPEN', capacity: 10, fee_vnd: 100000, deposit_vnd: 0, version: 1, policy: { quota_per_unit: 2, offer_minutes: 30, credential_days: 365, rounding_unit_vnd: 1 } },
  { id: ids.facility, kind: 'FACILITY', name: 'Phòng sinh hoạt', building_id: ids.buildingA, status: 'OPEN', capacity: 10, fee_vnd: 50000, deposit_vnd: 100000, version: 1, policy: { slot_minutes: 60, cancel_before_minutes: 60, cancel_fee_vnd: 20000, no_show_fee_vnd: 50000 } },
  { id: ids.service, kind: 'SERVICE', name: 'Vệ sinh định kỳ', building_id: ids.buildingA, status: 'OPEN', capacity: 100, fee_vnd: 200000, deposit_vnd: 0, version: 1, policy: { recurring: true, rounding_unit_vnd: 1 } },
  { id: randomUUID(), kind: 'FACILITY', name: 'Tiện ích đã đóng', building_id: ids.buildingA, status: 'CLOSED', capacity: 10, fee_vnd: 0, deposit_vnd: 0, version: 1, policy: {} },
];
let vehicles = [{ id: ids.vehicle, unit_id: ids.unitA, building_id: ids.buildingA, resource_id: ids.parking, plate: '30A-12345', vehicle_type: 'CAR', status: 'PENDING', version: 1, policy_snapshot: { fee_vnd: 100000, charge_when_paused: false } }];
let credentials = [{ id: ids.card, unit_id: ids.unitA, building_id: ids.buildingA, code: 'CARD-A1', status: 'ACTIVE', version: 1, valid_to: '2027-10-01', sync_status: 'PENDING', access_scope: ['Bãi A'] }];
let bookings = [{ id: ids.booking, unit_id: ids.unitA, building_id: ids.buildingA, resource_id: ids.facility, status: 'CONFIRMED', version: 1, starts_at: '2026-10-11T08:00:00Z', ends_at: '2026-10-11T09:00:00Z', quantity: 1, policy_snapshot: { fee_vnd: 50000, deposit_vnd: 100000 } }];
let enrollments = [{ id: ids.enrollment, unit_id: ids.unitA, building_id: ids.buildingA, resource_id: ids.service, status: 'PENDING', version: 1, policy_snapshot: { fee_vnd: 200000, recurring: true } }];
let dossiers = []; let detailFails = true; let bookingConflict = true;
const controls = Object.fromEntries(schemas.controls.map(s => [s.kind, []]));
const report = id => ({ id, resource_id: ids.parking, building_id: ids.buildingA, as_of: '2026-10-11T00:00:00Z', starts_at: '2026-10-01T00:00:00Z', ends_at: '2026-11-01T00:00:00Z', policy_reference: id === ids.reportA ? 'Căn cứ báo cáo A' : 'Căn cứ báo cáo B', usage_data_status: 'PARTIAL', finding_count: 0, snapshot: { usage_data_status: 'PARTIAL', held_count: 1, visitor_count: 0, vehicles: [], slots: [], usage_batches: [] }, findings: [] });
const checks = []; const errors = []; const unexpected = []; const commands = [];
const check = (task, name, value = true) => { assert.ok(value, `${task} ${name}`); checks.push({ task, name }); console.log(`PASS ${task} ${name}`); };
const scoped = (rows, url) => rows.filter(r => !url.searchParams.get('unit_id') || r.unit_id === url.searchParams.get('unit_id'));

(async () => {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const contexts = [];
  const open = async role => {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, locale: 'vi-VN' }); contexts.push(context);
    await context.route('**/api/v1/**', async route => {
      const request = route.request(); const url = new URL(request.url()); const api = url.pathname.replace('/api/v1', '');
      const body = request.postData() ? request.postDataJSON() : null;
      const respond = (data, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
      const reject = (message, status = 409) => respond({ error: { code: 'ERR-REVIEW-FIXTURE', message, correlation_id: 'R03-FIXTURE' } }, status);
      if (api === '/auth/login') return respond({ access_token: 'r03-fixture-session' });
      if (api === '/auth/me') return respond({ account_id: ids[role], tenant_id: randomUUID(), username: `${role}.review`, full_name: role === 'admin' ? 'BQL kiểm tra' : 'Cư dân kiểm tra', roles: [role], active_site_id: ids.site, allowed_sites: [{ id: ids.site, code: 'GC', name: 'GreenCity' }], resident_person_id: role === 'resident' ? ids.person : null, resident_unit_ids: role === 'resident' ? [ids.unitA, ids.unitB] : [] });
      assert.equal(request.headers().authorization, 'Bearer r03-fixture-session');
      if (request.method() === 'POST') {
        assert.ok(request.headers()['idempotency-key'], `${api}: missing idempotency`);
        commands.push({ api, body });
      }
      if (api === '/service-requests') return respond({ items: [], page: 1, page_size: 20, total: 0 });
      if (api === '/notifications') return respond({ items: [] });
      if (api === '/dashboard') return respond({ as_of: url.searchParams.get('as_of') || '2026-10-11T00:00:00Z', sla_overdue_count: 0, maintenance_due_count: 0, cleaning_rework_count: 0, open_incident_count: 0, ar_debt_vnd: 0 });
      if (api === `/units/${ids.unitA}/360`) return respond({ ...units[0], floor: 1, version: 1, status: 'OCCUPIED', building_code: 'A', building_name: 'Tòa A', site_id: ids.site, site_code: 'GC', site_name: 'GreenCity', residents_visible: true, residents: [{ person_id: ids.person, full_name: 'Cư dân kiểm tra', phone_masked: '09******00', email_masked: 'r***@example.test', relationship_type: 'owner', is_active: true, ownership_ratio: '1.0000', valid_from: '2026-01-01', valid_to: null }] });
      if (api === '/resident/service-request-options') return respond({ buildings, units, categories: [] });
      if (api === '/resident/notifications') return respond({ items: [], total: 0, unread_count: 0, page: 1, page_size: 50 });
      if (api === '/resident/service-requests') return respond({ items: [], total: 0, page: 1, page_size: 50 });
      if (api.startsWith('/resident/billing/')) return respond({ items: [], as_of: url.searchParams.get('as_of'), total_ar_balance_vnd: 0 });
      if (!api.startsWith('/portal/')) { unexpected.push(api); return reject('API chưa có trong fixture', 404); }
      const p = api.replace('/portal', '');
      if (p === '/profile') return respond({ person: { id: ids.person, full_name: 'Cư dân kiểm tra', phone_masked: '09******00', email_masked: 'r***@example.test' }, units: units.map(u => ({ ...u, building_name: u.building_id === ids.buildingA ? 'Tòa A' : 'Tòa B', permissions: ['profile', 'requests', 'finance', 'parking', 'booking', 'documents'] })), selected_unit_id: url.searchParams.get('unit_id') || ids.unitA, relationships: [{ relationship_type: 'owner' }], relationship_history: [] });
      if (p === '/options') return respond({ buildings, units });
      if (p === '/capabilities') return respond({ items: [] });
      if (p === '/property/persons') return respond({ items: [{ id: ids.person, full_name: 'Cư dân kiểm tra' }] });
      if (p === '/property/duplicates') return respond({ items: [] });
      if (p === '/property/buildings') return respond({ items: buildings, units });
      if (p === '/property/nodes') {
        if (request.method() === 'POST') { const row = { id: randomUUID(), ...body, status: 'ACTIVE', version: 1 }; nodes.push(row); return respond(row, 201); }
        return respond({ items: nodes });
      }
      if (/^\/property\/units\/[^/]+\/history$/.test(p)) return respond({ leases: [{ id: 'lease-source', reference: 'LEASE-01', valid_from: '2026-01-01', valid_to: '2026-12-31', status: 'ACTIVE' }], profiles: [], liabilities: [], relationships: [], events: dossiers.map(d => ({ id: d.id, reason: d.title, status: d.status, created_at: '2026-10-11T00:00:00Z' })) });
      if (p === '/dossiers') {
        if (request.method() === 'POST') { const row = { id: randomUUID(), ...body, status: 'SUBMITTED', version: 1, created_at: '2026-10-11T00:00:00Z', events: [] }; dossiers.push(row); return respond(row, 201); }
        return respond({ items: scoped(dossiers, url) });
      }
      if (/^\/dossiers\/[^/]+$/.test(p)) return respond(dossiers.find(d => d.id === p.split('/')[2]));
      if (p === '/documents') return respond({ items: [] });
      if (p === '/resources') {
        if (request.method() === 'POST') { const row = { id: randomUUID(), ...body, status: 'OPEN', version: 1 }; resources.push(row); return respond(row, 201); }
        const unit = units.find(u => u.id === url.searchParams.get('unit_id'));
        return respond({ items: resources.filter(r => (!url.searchParams.get('kind') || r.kind === url.searchParams.get('kind')) && (!unit || r.building_id === unit.building_id)) });
      }
      if (/^\/resources\/[^/]+\/closures$/.test(p)) return respond({ items: [] });
      if (/^\/resources\/[^/]+\/availability$/.test(p)) return respond({ capacity: 10, available: 9 });
      if (/^\/resources\/[^/]+\/actions$/.test(p)) { const row = resources.find(r => r.id === p.split('/')[2]); assert.equal(body.expected_version, row.version); row.status = body.action === 'CLOSE' ? 'CLOSED' : 'OPEN'; row.version++; return respond(row); }
      if (p === '/vehicles') {
        if (request.method() === 'POST') { const row = { id: randomUUID(), ...body, status: 'PENDING', version: 1, policy_snapshot: { fee_vnd: 100000 } }; vehicles.push(row); return respond(row, 201); }
        return respond({ items: scoped(vehicles, url) });
      }
      if (p === '/credentials') return respond({ items: scoped(credentials, url) });
      if (p === '/bookings') {
        if (request.method() === 'POST') { if (bookingConflict) return reject('Khung giờ đã hết sức chứa'); const row = { id: randomUUID(), ...body, status: 'AWAITING_DEPOSIT', version: 1, policy_snapshot: { fee_vnd: 50000, deposit_vnd: 100000 } }; bookings.push(row); return respond(row, 201); }
        return respond({ items: scoped(bookings, url) });
      }
      if (p === '/enrollments') {
        if (request.method() === 'POST') { const row = { id: randomUUID(), ...body, status: 'PENDING', version: 1, policy_snapshot: { fee_vnd: 200000, recurring: true } }; enrollments.push(row); return respond(row, 201); }
        return respond({ items: scoped(enrollments, url) });
      }
      const change = p.match(/^\/(vehicles|bookings|enrollments|credentials)\/([^/]+)\/actions$/);
      if (change) {
        const data = { vehicles, bookings, enrollments, credentials }[change[1]];
        const row = data.find(r => r.id === change[2]); assert.equal(body.expected_version, row.version);
        if (change[1] === 'bookings' && body.action === 'CONFIRM') return reject('Khoản cọc chưa được xác nhận');
        row.status = { APPROVE: 'ACTIVE', PAUSE: 'PAUSED', RESUME: 'ACTIVE', END: 'ENDED', CANCEL: 'CANCELLED', LOCK: 'LOCKED', CHECK_IN: 'CHECKED_IN', COMPLETE: 'COMPLETED' }[body.action]; row.version++; return respond(row);
      }
      if (p === '/operations/catalog') return respond({ items: schemas.records });
      if (p === '/control/catalog') return respond({ items: schemas.controls });
      if (p === '/operations/options') return respond({ accounts: [{ id: ids.admin, label: 'BQL kiểm tra' }], units: units.map(u => ({ ...u, label: u.unit_number })), property_nodes: nodes.map(n => ({ ...n, label: n.name })), portal_resources: resources.map(r => ({ ...r, label: r.name })), billing_fee_policies: [{ id: ids.policy, building_id: ids.buildingA, label: 'Phí quản lý' }], all_fee_versions: [{ id: ids.feeVersion, building_id: ids.buildingA, label: 'Phí quản lý v2' }], vehicles, operations_records: [], resident_credentials: credentials.map(c => ({ ...c, label: c.code })) });
      if (p === '/operations/records') return respond({ items: [] });
      if (/^\/control\/(parking-slots|visitor-parking|access-cards|card-blanks)$/.test(p)) return respond({ items: controls[p.split('/')[2]] });
      if (p === '/control/parking-reconciliations') return respond({ items: [report(ids.reportA), report(ids.reportB)].filter(r => !url.searchParams.get('building_id') || r.building_id === url.searchParams.get('building_id')) });
      if (/^\/control\/parking-reconciliations\/[^/]+$/.test(p)) { if (detailFails) return reject('Chưa tải được chi tiết đối chiếu', 503); return respond(report(p.split('/')[3])); }
      unexpected.push(p); return reject('API chưa có trong fixture', 404);
    });
    const page = await context.newPage(); page.on('pageerror', error => errors.push(error.message));
    await page.goto(process.env.UX_BASE_URL || 'http://127.0.0.1:3100');
    await page.getByLabel('Tên đăng nhập').fill(`${role}.review`); await page.getByLabel('Mật khẩu').fill('fixture-local-only');
    await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
    return page;
  };
  const shot = (page, name) => page.screenshot({ path: path.join(output, name), fullPage: true });
  const tab = (page, name) => page.getByRole('navigation', { name: 'Phân hệ dịch vụ cư dân', exact: true }).getByRole('button', { name, exact: true }).click();
  const formFor = (page, title) => page.locator('form').filter({ has: page.getByRole('heading', { name: title, exact: true }) });
  const perform = async (card, label) => {
    await card.getByRole('button', { name: label, exact: true }).click();
    const form = card.locator('form').filter({ hasText: `Lý do — ${label}` });
    await form.getByLabel(`Lý do — ${label}`).fill('Đã kiểm tra căn cứ hồ sơ');
    await form.getByRole('button', { name: 'Xác nhận', exact: true }).click();
  };
  try {
    const admin = await open('admin');
    const nav = admin.getByRole('navigation', { name: 'Điều hướng chính' });
    await nav.getByRole('button', { name: 'Khách hàng & Cư dân', exact: true }).click();
    await admin.locator('#unit-lookup-id').fill(ids.unitA); await admin.getByRole('button', { name: 'Tra cứu', exact: true }).click();
    await admin.getByRole('heading', { name: 'Căn A-101', exact: true }).waitFor();
    check('FE-12.01', 'Unit 360 hiển thị căn và dữ liệu liên hệ đã che', await admin.getByText('09******00', { exact: false }).isVisible());
    await nav.getByRole('button', { name: 'Dịch vụ cư dân', exact: true }).click();
    await admin.getByRole('heading', { name: 'Quản lý dịch vụ cư dân', exact: true }).waitFor();
    const top = admin.locator('.desktop-page.portal-page > .portal-grid');
    await top.getByLabel('Tòa nhà').selectOption(ids.buildingA); await top.getByLabel('Căn hộ').selectOption(ids.unitA);
    const spatial = formFor(admin, 'Tạo không gian');
    await spatial.getByLabel('Tòa', { exact: true }).selectOption(ids.buildingA);
    check('FE-12.02', 'Tầng chỉ chọn phân khu đã gán của tòa', (await spatial.getByLabel('Không gian cha').locator('option').allTextContents()).join('|') === 'Chưa chọn|ZA · Phân khu A');
    await spatial.getByLabel('Không gian cha').selectOption(ids.zoneA);
    await spatial.getByLabel('Tòa', { exact: true }).selectOption(ids.buildingB);
    check('FE-12.02', 'Đổi tòa xóa nguồn cha cũ', await spatial.getByLabel('Không gian cha').inputValue() === '');
    await spatial.getByLabel('Loại', { exact: true }).selectOption('COMMON_AREA');
    check('FE-12.02', 'Khu chung chỉ chọn tầng cùng tòa', (await spatial.getByLabel('Không gian cha').locator('option').allTextContents()).join('|') === 'Chưa chọn|FB · Tầng B2');
    await spatial.getByLabel('Loại', { exact: true }).selectOption('ZONE');
    check('FE-12.02', 'Phân khu không gửi tòa hoặc tầng cha', await spatial.getByLabel('Tòa', { exact: true }).isDisabled() && await spatial.getByLabel('Không gian cha').isDisabled());
    const property = formFor(admin, 'Lập hồ sơ bất động sản');
    await property.getByLabel('Nghiệp vụ').selectOption('LEASE_RENEW');
    check('FE-13.03', 'Gia hạn chọn hợp đồng gốc trong lịch sử', await property.getByLabel('Hợp đồng gốc').locator('option').count() === 2);
    await property.getByLabel('Nghiệp vụ').selectOption('HANDOVER');
    check('FE-12.04', 'Bàn giao có biên bản, hạng mục và tồn tại', await property.getByLabel('Mã biên bản').isVisible() && await property.getByLabel('Tồn tại / lỗi, mỗi dòng một mục').isVisible());
    await property.getByLabel('Nghiệp vụ').selectOption('PERSON_MERGE');
    check('FE-12.05', 'BQL có form xác minh hợp nhất người', await property.getByLabel('Hồ sơ người giữ lại').isVisible());
    await shot(admin, 'property.png');

    await tab(admin, 'Chính sách');
    const resource = formFor(admin, 'Thêm tài nguyên');
    await resource.getByLabel('Tên', { exact: true }).fill('Chính sách kiểm tra');
    for (const [kind, policy] of [['PARKING', { 'Quota xe / căn hộ': '2', 'Thời hạn nhận suất (phút)': '30', 'Hạn thẻ (ngày)': '365' }], ['FACILITY', { 'Độ dài khung (phút)': '60', 'Thời lượng tối đa (phút)': '120', 'Hạn hủy trước giờ đặt (phút)': '30', 'Phí hủy muộn (VND)': '10000', 'Phí không đến (VND)': '20000', 'Quota lượt đặt / căn': '3', 'Cửa sổ hạn mức (ngày)': '7' }], ['SERVICE', {}]]) {
      await resource.getByLabel('Loại', { exact: true }).selectOption(kind);
      for (const [label, value] of Object.entries(policy)) await resource.getByLabel(label).fill(value);
      if (kind === 'SERVICE') await resource.getByLabel('Thu phí định kỳ').check();
      await resource.getByRole('button', { name: 'Lưu chính sách', exact: true }).click();
      await resource.getByText('Đã ghi nhận thao tác.', { exact: true }).waitFor();
      const body = commands.at(-1).body;
      check('FE-14.01', `Lưu đúng trường chính sách ${kind}`, body.kind === kind && (kind !== 'SERVICE' || !('slot_minutes' in body.policy)));
    }
    const parkingCard = admin.locator('article.portal-record').filter({ has: admin.getByRole('heading', { name: 'Bãi A', exact: true }) });
    await perform(parkingCard, 'Ngừng nhận đăng ký mới');
    await parkingCard.getByRole('button', { name: 'Mở nhận đăng ký', exact: true }).waitFor();
    check('FE-14.03', 'Đóng tài nguyên tải lại khả năng đăng ký', resources[0].status === 'CLOSED');
    check('FE-14.04', 'Lịch đóng tiện ích có form công bố và giải thích tác động', await admin.getByRole('button', { name: 'Công bố lịch đóng và xử lý lượt đặt', exact: true }).count() > 0);
    await shot(admin, 'resources.png');
    // Open again so resident vehicle registration can use this parking resource.
    await perform(parkingCard, 'Mở nhận đăng ký'); await parkingCard.getByRole('button', { name: 'Ngừng nhận đăng ký mới', exact: true }).waitFor();
    await tab(admin, 'Xe & thẻ');
    const vehicleCard = admin.locator('.resident-page article.portal-record').filter({ has: admin.getByRole('heading', { name: '30A-12345', exact: true }) });
    await perform(vehicleCard, 'Duyệt đăng ký'); await vehicleCard.getByText('Đang hoạt động', { exact: true }).waitFor();
    check('FE-15.01', 'Duyệt xe gửi version rồi tải trạng thái mới', vehicles[0].version === 2);
    await perform(vehicleCard, 'Tạm dừng thu phí (giữ suất)'); await vehicleCard.getByText('Tạm dừng', { exact: true }).waitFor();
    check('FE-15.05', 'Tạm dừng gửi ngày hiệu lực theo chính sách', !!commands.at(-1).body.data.effective_on);
    await perform(vehicleCard, 'Tiếp tục'); await vehicleCard.getByText('Đang hoạt động', { exact: true }).waitFor();
    const card = admin.locator('.resident-page article.portal-record').filter({ has: admin.getByRole('heading', { name: 'CARD-A1', exact: true }) });
    await perform(card, 'Khóa thẻ'); await card.getByText('Đã khóa', { exact: true }).waitFor();
    check('FE-15.04', 'Khóa thẻ phản ánh trạng thái tải lại', credentials[0].status === 'LOCKED');

    await tab(admin, 'Đối chiếu bãi xe');
    await admin.getByRole('button', { name: 'Xem nguồn và hồ sơ xử lý', exact: true }).first().click();
    const error = admin.getByRole('alert').filter({ hasText: 'Chưa tải được chi tiết đối chiếu' }); await error.waitFor();
    detailFails = false; await error.getByRole('button', { name: 'Thử lại', exact: true }).click();
    await admin.getByText(/Căn cứ báo cáo A/).waitFor();
    check('FE-16.03', 'Chi tiết đối chiếu lỗi có thử lại và giữ mức đầy đủ PARTIAL');
    await admin.getByRole('button', { name: 'Xem nguồn và hồ sơ xử lý', exact: true }).nth(1).click();
    await admin.getByText(/Căn cứ báo cáo B/).waitFor();
    check('FE-16.05', 'Đổi báo cáo thay đúng nguồn chi tiết', await admin.getByText(/Căn cứ báo cáo A/).count() === 0);
    await top.getByLabel('Tòa nhà').selectOption(ids.buildingB);
    await admin.getByText('Chưa có dữ liệu trong phạm vi đang chọn.', { exact: true }).first().waitFor();
    check('FE-16.05', 'Đổi tòa xóa chi tiết trước đó', await admin.getByText(/Căn cứ báo cáo B/).count() === 0);
    await top.getByLabel('Tòa nhà').selectOption(ids.buildingA); await top.getByLabel('Căn hộ').selectOption(ids.unitA);
    await tab(admin, 'Tiện ích');
    const booking = admin.locator('article.portal-record').filter({ hasText: 'Đã xác nhận' });
    await perform(booking, 'Ghi nhận sử dụng'); await admin.getByText('Đang sử dụng', { exact: true }).waitFor();
    const inUse = admin.locator('article.portal-record').filter({ hasText: 'Đang sử dụng' });
    await perform(inUse, 'Hoàn tất sử dụng'); await admin.getByText('Hoàn tất', { exact: true }).waitFor();
    check('FE-17.03', 'Check-in và hoàn tất tải lại theo version', bookings[0].version === 3);
    await tab(admin, 'Dịch vụ');
    const service = admin.locator('article.portal-record').filter({ hasText: 'Vệ sinh định kỳ' });
    await perform(service, 'Phê duyệt'); await service.getByText('Đang hoạt động', { exact: true }).waitFor();
    check('FE-18.02', 'Phê duyệt dịch vụ lưu ngày hiệu lực', !!commands.at(-1).body.data.effective_on);
    await perform(service, 'Tạm dừng dịch vụ và thu phí'); await service.getByText('Tạm dừng', { exact: true }).waitFor();
    await perform(service, 'Tiếp tục dịch vụ và thu phí'); await service.getByText('Đang hoạt động', { exact: true }).waitFor();
    check('FE-18.03', 'Dịch vụ định kỳ tạm dừng và tiếp tục tải lại trạng thái');

    await tab(admin, 'Vận hành & nguồn lực');
    for (const [kind, task] of [['PARCEL_CUSTODY', 'FE-11.05'], ['LOST_FOUND', 'FE-11.05'], ['ORGANIZATION', 'FE-12.03'], ['BUILDING_ZONE', 'FE-12.02'], ['BUILDING_PROFILE', 'FE-12.03'], ['SITE_PROFILE', 'FE-12.03'], ['parking-slots', 'FE-15.02'], ['card-blanks', 'FE-15.03'], ['access-cards', 'FE-15.03'], ['visitor-parking', 'FE-16.01'], ['FEE_PUBLICATION', 'FE-19.02'], ['FEE_BENEFIT', 'FE-19.04']]) {
      await admin.getByLabel('Nghiệp vụ', { exact: true }).selectOption(kind);
      await admin.locator('.resident-page form').getByRole('button', { name: 'Lưu hồ sơ', exact: true }).waitFor();
      check(task, `Form ${kind} render từ schema backend, không nhập JSON thô`, await admin.locator('.resident-page form input, .resident-page form select, .resident-page form textarea').count() > 0);
    }
    await shot(admin, 'fee-benefit.png');

    const resident = await open('resident');
    await resident.getByRole('heading', { name: 'Cư dân kiểm tra', exact: true }).waitFor();
    await resident.getByRole('tab', { name: 'Hồ sơ đăng ký', exact: true }).click();
    const dossier = formFor(resident, 'Gửi hồ sơ mới');
    for (const kind of ['PROFILE_CHANGE', 'MOVE_IN', 'MOVE_OUT', 'ABSENCE', 'RETURN', 'DELEGATION', 'TRANSFER']) {
      await dossier.getByLabel('Loại hồ sơ').selectOption(kind);
      check(['DELEGATION', 'TRANSFER'].includes(kind) ? 'FE-13.04' : 'FE-13.02', `Form hồ sơ ${kind} có ngày hiệu lực và trường đúng loại`, await dossier.getByLabel('Ngày có hiệu lực').isVisible());
    }
    await dossier.getByLabel('Loại hồ sơ').selectOption('DELEGATION');
    await dossier.getByLabel('Tiêu đề').fill('Ủy quyền theo căn'); await dossier.getByLabel('Ngày kết thúc', { exact: true }).fill('2027-01-01');
    await dossier.getByLabel('Tên đăng nhập người được ủy quyền').fill('delegate.review'); await dossier.getByLabel('Xe/thẻ', { exact: true }).check();
    await dossier.getByRole('button', { name: 'Gửi hồ sơ', exact: true }).click();
    await resident.getByRole('heading', { name: 'Ủy quyền theo căn', exact: true }).waitFor();
    check('FE-13.04', 'Ủy quyền gửi căn và phạm vi đã chọn', dossiers.at(-1).unit_id === ids.unitA && dossiers.at(-1).data.permissions.includes('parking') && !dossiers.at(-1).data.permissions.includes('finance'));
    await resident.getByRole('tab', { name: 'Đặt tiện ích', exact: true }).click();
    const bookingForm = resident.locator('.resident-main form');
    check('FE-14.03', 'Cư dân không chọn tài nguyên đã đóng', await bookingForm.getByRole('option', { name: 'Tiện ích đã đóng', exact: true }).count() === 0);
    await bookingForm.getByLabel('Tiện ích').selectOption(ids.facility);
    await bookingForm.getByLabel('Bắt đầu', { exact: true }).fill('2026-12-01T10:00'); await bookingForm.getByLabel('Kết thúc', { exact: true }).fill('2026-12-01T11:00');
    await resident.getByText('Còn 9 / 10 suất trong khung đã chọn.', { exact: false }).waitFor();
    await bookingForm.getByRole('button', { name: 'Xác nhận điều kiện và đặt', exact: true }).click();
    await resident.getByRole('alert').filter({ hasText: 'Khung giờ đã hết sức chứa' }).waitFor();
    check('FE-17.01', 'Lỗi sức chứa từ API hiển thị và không tạo lượt thành công', bookings.length === 1);
    bookingConflict = false; await bookingForm.getByRole('button', { name: 'Xác nhận điều kiện và đặt', exact: true }).click();
    await resident.getByText('Chờ đủ cọc', { exact: true }).waitFor();
    const deposit = resident.locator('article.portal-record').filter({ hasText: 'Chờ đủ cọc' });
    await perform(deposit, 'Kiểm tra cọc và xác nhận');
    await resident.getByRole('alert').filter({ hasText: 'Khoản cọc chưa được xác nhận' }).waitFor();
    check('FE-17.02', 'Bấm kiểm tra cọc không tự xác nhận khi API từ chối', bookings.at(-1).status === 'AWAITING_DEPOSIT');
    await shot(resident, 'resident-booking.png');
    await resident.getByLabel('Căn hộ đang xem').selectOption(ids.unitB);
    await resident.getByRole('tab', { name: 'Đặt tiện ích', exact: true }).click();
    check('FE-17.05', 'Đổi căn xóa lựa chọn và lượt đặt cũ', await resident.getByLabel('Tiện ích').inputValue() === '' && await resident.getByText('Chờ đủ cọc', { exact: true }).count() === 0);
    await resident.getByLabel('Căn hộ đang xem').selectOption(ids.unitA);
    await resident.getByRole('tab', { name: 'Dịch vụ bổ sung', exact: true }).click();
    await resident.getByLabel('Dịch vụ', { exact: false }).selectOption(ids.service);
    await resident.getByRole('button', { name: 'Đồng ý phí và gửi đăng ký', exact: true }).click();
    await resident.getByText('Chờ xử lý', { exact: true }).waitFor();
    check('FE-18.01', 'Cư dân đăng ký dịch vụ theo căn và phí công bố', enrollments.at(-1).unit_id === ids.unitA);
    await resident.setViewportSize({ width: 390, height: 844 });
    await shot(resident, 'resident-services-mobile.png');
    check('COMMON', 'Giao diện dịch vụ ở chiều rộng 390px không tràn ngang', await resident.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    check('COMMON', 'Không có lỗi JS không xử lý hoặc API ngoài fixture', errors.length === 0 && unexpected.length === 0);
    fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify({ source: 'FIXTURE', passed: checks.length, checks, errors, unexpected }, null, 2));
    console.log(`R03 UX: ${checks.length} checks passed.`);
  } catch (error) {
    for (const [i, context] of contexts.entries()) for (const page of context.pages()) await shot(page, `failure-${i}.png`);
    fs.writeFileSync(path.join(output, 'failure.json'), JSON.stringify({ source: 'FIXTURE', checks, errors, unexpected, failure: error.message }, null, 2));
    throw error;
  } finally { await Promise.all(contexts.map(c => c.close())); await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
