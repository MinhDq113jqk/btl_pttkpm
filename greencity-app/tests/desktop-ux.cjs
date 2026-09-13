const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { installAuthApiMocks, loginAs } = require('./staff-helpers.cjs');

const output = path.resolve(__dirname, '../artifacts/desktop-integration');
fs.mkdirSync(output, { recursive: true });

(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, locale: 'vi-VN' });
  const checks = [];
  const errors = [];
  const check = (name, value = true) => { assert.ok(value, name); checks.push(name); console.log(`PASS ${name}`); };
  page.on('pageerror', error => errors.push(error.message));
  try {
    await installAuthApiMocks(page);
    await page.goto(process.env.UX_BASE_URL || 'http://127.0.0.1:3000/');
    await page.waitForLoadState('networkidle');
    await loginAs(page);
    await page.getByRole('navigation', { name: 'Điều hướng chính' }).getByRole('button', { name: 'Công việc & Yêu cầu', exact: true }).click();
    await page.getByText('SR-UX-001', { exact: true }).waitFor();

    check('task table is labelled as a scoped service-request list', await page.getByRole('region', { name: 'Bảng yêu cầu dịch vụ, có thể cuộn ngang' }).isVisible());
    check('sort control exposes its direction', await page.getByRole('columnheader', { name: /SLA/ }).getAttribute('aria-sort') === 'ascending');
    await page.getByRole('columnheader', { name: /SLA/ }).getByRole('button').click();
    check('sort direction toggles from keyboard-reachable control', await page.getByRole('columnheader', { name: /SLA/ }).getAttribute('aria-sort') === 'descending');

    await page.getByRole('button', { name: 'Mở yêu cầu SR-UX-001' }).click();
    check('read-only detail shows record id and SLA', await page.getByRole('dialog', { name: 'SR-UX-001' }).getByText('ID hồ sơ', { exact: true }).isVisible() && await page.getByRole('dialog', { name: 'SR-UX-001' }).getByText('Hạn SLA', { exact: true }).isVisible());
    await page.getByRole('button', { name: 'Đóng chi tiết' }).click();

    await page.getByRole('button', { name: 'Tìm kiếm công việc và phân hệ' }).click();
    await page.getByLabel('Tìm theo mã, tên công việc hoặc phân hệ').fill('SR-UX-001');
    check('global search is limited to the visible server page', await page.getByRole('dialog', { name: 'Tìm kiếm nhanh' }).getByText('Kiểm tra đèn hành lang', { exact: true }).isVisible());
    await page.keyboard.press('Escape');

    await page.goto(`${process.env.UX_BASE_URL || 'http://127.0.0.1:3000/'}#/refund-form`);
    await page.getByRole('heading', { name: 'Không có quyền xem phân hệ này' }).waitFor();
    check('deep link cannot mount a hidden mock operation', await page.locator('.refund-page').count() === 0);

    for (const [width, height] of [[1440, 900], [1024, 768], [800, 600]]) {
      await page.setViewportSize({ width, height });
      check(`workspace fits ${width}x${height}`, await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth && document.querySelector('main').scrollWidth <= document.querySelector('main').clientWidth + 1));
    }
    await page.screenshot({ path: path.join(output, 'desktop-800.png'), fullPage: true });
    check('no runtime JavaScript errors', errors.length === 0);
    console.log(`DESKTOP INTEGRATION UX: ${checks.length} checks passed.`);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
