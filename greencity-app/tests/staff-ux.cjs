const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { loginAs } = require('./staff-helpers.cjs');
const output = path.resolve(__dirname, '../artifacts/staff');
fs.mkdirSync(output, { recursive: true });

(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const errors = [];
  const checks = [];
  const check = (name, value = true) => { assert.ok(value, name); checks.push(name); console.log(`PASS ${name}`); };
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'vi-VN' });
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    const url = process.env.UX_BASE_URL || 'http://127.0.0.1:3000/';
    const nav = name => page.getByRole('navigation', { name: 'Điều hướng chính' }).getByRole('button', { name, exact: true }).click();
    const shot = name => page.screenshot({ path: path.join(output, name) });
    await page.goto(url);
    await page.waitForLoadState('networkidle');
    console.log(JSON.stringify({ initialHeadings: await page.locator('h1,h2').allTextContents() }));
    check('shared staff login is the initial surface', await page.getByRole('heading', { name: 'Đăng nhập không gian làm việc' }).isVisible());
    check('all eight accounts are available', await page.locator('#staff-account option').count() === 8);
    check('demo does not request a real password', await page.locator('#staff-password').isDisabled());
    check('workspace and assistant are absent before login', await page.locator('.desktop-shell,.green-assistant').count() === 0);
    await shot('01-shared-login.png');
    await page.getByRole('button', { name: 'Cần hỗ trợ đăng nhập?' }).click();
    check('login help explains account ownership', await page.getByText(/tài khoản và quyền do Admin cấp/).isVisible());
    await page.getByRole('button', { name: 'Cần hỗ trợ đăng nhập?' }).click();
    const roles = [
      ['admin', 'Quản trị không gian làm việc', 7, true], ['director', 'Tổng quan điều hành', 7, true],
      ['cskh', 'Tiếp nhận & chăm sóc cư dân', 3, false], ['accountant', 'Tài chính & đối soát', 1, true],
      ['technical', 'Công việc kỹ thuật của tôi', 2, false], ['cleaning', 'Ca vệ sinh của tôi', 1, false],
      ['security', 'Ca trực an ninh của tôi', 1, false], ['auditor', 'Không gian kiểm toán', 7, true],
    ];
    for (const [role, heading, count, financial] of roles) {
      await loginAs(page, role);
      await page.getByRole('heading', { name: heading, exact: true }).waitFor();
      check(`${role}: tailored dashboard`);
      const menu = page.getByRole('navigation', { name: 'Điều hướng chính' });
      check(`${role}: financial navigation follows policy`, await menu.getByRole('button', { name: 'Phiếu hoàn tiền & Hoá đơn', exact: true }).count() === Number(financial));
      check(`${role}: only admin sees settings`, await menu.getByRole('button', { name: 'Quản trị hệ thống', exact: true }).count() === Number(role === 'admin'));
      await shot(`dashboard-${role}.png`);
      await nav('Công việc & Yêu cầu');
      check(`${role}: scoped task count`, await page.locator('tbody tr').count() === count);
      await page.getByRole('button', { name: 'Tìm kiếm công việc và phân hệ' }).click();
      await page.getByLabel('Tìm theo mã, tên công việc hoặc phân hệ').fill('TC-2608-016');
      check(`${role}: search uses the same data scope`, await page.getByRole('dialog', { name: 'Tìm kiếm nhanh' }).locator('.search-result').count() === Number(financial));
      await page.keyboard.press('Escape');
      if (['technical', 'cleaning', 'security'].includes(role)) {
        await page.goto(`${url}#/refund-form`);
        await page.getByRole('heading', { name: 'Không có quyền xem phân hệ này' }).waitFor();
        check(`${role}: direct unauthorized URL does not mount refund`, await page.locator('.refund-page').count() === 0);
      }
    }
    await nav('Phiếu hoàn tiền & Hoá đơn');
    check('auditor has no editable refund fields', await page.locator('.refund-page input,.refund-page textarea').count() === 0);
    check('auditor cannot approve or save a draft', await page.getByRole('button', { name: /Lưu bản nháp|Kiểm tra phê duyệt mẫu/ }).count() === 0);
    await shot('auditor-readonly-refund.png');
    await nav('Báo cáo điều hành');
    check('auditor can read reports', await page.getByRole('heading', { name: 'Báo cáo trong phạm vi' }).isVisible());
    await loginAs(page, 'director');
    await nav('Phiếu hoàn tiền & Hoá đơn');
    check('director reviews without editing account or amount', await page.locator('.refund-page input').count() === 0);
    await page.getByRole('button', { name: 'Kiểm tra phê duyệt mẫu', exact: true }).click();
    check('director sees approval action', await page.getByRole('button', { name: 'Phê duyệt mô phỏng' }).isVisible());
    await page.keyboard.press('Escape');
    await loginAs(page, 'accountant');
    await nav('Phiếu hoàn tiền & Hoá đơn');
    await page.locator('#remarks').fill('Nháp riêng của kế toán');
    await page.getByRole('button', { name: 'Đổi tài khoản hoặc đăng xuất' }).click();
    check('logout warns about unsaved refund', await page.getByRole('dialog', { name: 'Đăng xuất tài khoản mẫu?' }).getByText(/thay đổi chưa lưu/).isVisible());
    await page.getByRole('button', { name: 'Ở lại', exact: true }).click();
    await page.getByRole('button', { name: 'Lưu bản nháp', exact: true }).click();
    await page.getByRole('button', { name: 'Kiểm tra & xác nhận', exact: true }).click();
    check('accountant submits, does not approve', await page.getByRole('button', { name: 'Trình duyệt mô phỏng' }).isVisible() && await page.getByRole('button', { name: 'Phê duyệt mô phỏng' }).count() === 0);
    await page.keyboard.press('Escape');
    await page.getByRole('button', { name: 'Mở Green Assistant', exact: true }).click();
    await page.getByRole('textbox', { name: 'Nhập tin nhắn cho Green Assistant' }).fill('Lịch sử riêng tài khoản kế toán');
    await page.getByRole('button', { name: 'Gửi tin nhắn', exact: true }).click();
    await page.waitForFunction(() => !document.querySelector('.assistant-message.is-pending'));
    await loginAs(page, 'cleaning');
    await page.getByRole('button', { name: 'Mở Green Assistant', exact: true }).click();
    check('assistant history is not exposed to another account', await page.locator('.assistant-message').count() === 0);
    await page.getByRole('textbox', { name: 'Nhập tin nhắn cho Green Assistant' }).fill('công việc quá hạn');
    await page.getByRole('button', { name: 'Gửi tin nhắn', exact: true }).click();
    await page.waitForFunction(() => !document.querySelector('.assistant-message.is-pending'));
    check('assistant does not disclose other teams work', await page.locator('.assistant-message-assistant').innerText().then(text => text.includes('1 công việc, 0 việc quá hạn') && !text.includes('KT-2608-097')));
    await loginAs(page, 'accountant');
    await nav('Phiếu hoàn tiền & Hoá đơn');
    check('account-specific refund draft is restored', await page.locator('#remarks').inputValue() === 'Nháp riêng của kế toán');
    await page.reload();
    await page.locator('#remarks').waitFor();
    check('demo session restores after reload', await page.locator('#remarks').inputValue() === 'Nháp riêng của kế toán');
    await loginAs(page, 'admin');
    await nav('Quản trị hệ thống');
    check('admin account matrix lists eight roles', await page.locator('tbody tr').count() === 8);
    await shot('admin-permission-matrix.png');
    for (const [width, height] of [[1440, 900], [1280, 720], [1024, 768], [800, 600]]) {
      await page.setViewportSize({ width, height });
      await nav('Tổng quan');
      check(`workspace fits ${width}x${height}`, await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth && document.querySelector('main').scrollWidth <= document.querySelector('main').clientWidth + 1));
      check(`logout remains reachable at ${width}`, await page.getByRole('button', { name: 'Đổi tài khoản hoặc đăng xuất' }).isVisible());
      if (width === 1024) await shot('dashboard-1024.png');
    }
    await page.getByRole('button', { name: 'Đổi tài khoản hoặc đăng xuất' }).click();
    await page.getByRole('button', { name: 'Đăng xuất', exact: true }).click();
    check('logout returns to shared login and unmounts account data', await page.locator('#staff-account').isVisible() && await page.locator('.green-assistant').count() === 0);
    for (const [width, height] of [[1280, 720], [1024, 768], [800, 600]]) {
      await page.setViewportSize({ width, height });
      check(`login fits ${width}`, await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    }
    await page.evaluate(() => sessionStorage.setItem('greencity.staff-demo.v1', JSON.stringify({ accountId: 'nonexistent', role: 'admin' })));
    await page.reload();
    check('invalid saved account returns safely to login', await page.locator('#staff-account').isVisible());
    check('no runtime errors across eight roles', errors.length === 0);
    fs.writeFileSync(path.join(output, 'test-results.json'), JSON.stringify({ passed: checks.length, checks, errors }, null, 2));
    console.log(`STAFF UX: ${checks.length} checks passed.`);
  } catch (error) { console.error('Runtime errors:', errors); throw error; }
  finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
