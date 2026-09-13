const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const { installAuthApiMocks, loginAs } = require('./staff-helpers.cjs');

(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 }, locale: 'vi-VN' });
  const checks = [];
  const errors = [];
  const check = (name, value = true) => { assert.ok(value, name); checks.push(name); console.log(`PASS ${name}`); };
  page.on('pageerror', error => errors.push(error.message));
  try {
    await installAuthApiMocks(page);
    await page.goto(process.env.UX_BASE_URL || 'http://127.0.0.1:3000/');
    await page.waitForLoadState('networkidle');
    await loginAs(page);
    await page.getByRole('button', { name: 'Mở Green Assistant', exact: true }).click();
    const panel = page.getByRole('dialog', { name: 'Green Assistant' });
    const input = panel.getByRole('textbox', { name: 'Nhập tin nhắn cho Green Assistant' });
    check('assistant opens only after authenticated workspace mounts', await panel.isVisible());

    await input.fill('Công việc quá hạn');
    await panel.getByRole('button', { name: 'Gửi tin nhắn', exact: true }).click();
    await page.waitForFunction(() => !document.querySelector('.assistant-message.is-pending'));
    check('assistant uses only the visible service-request page', await panel.locator('.assistant-message-assistant').innerText().then(text => text.includes('1 công việc')));

    await input.fill('thử lỗi');
    await panel.getByRole('button', { name: 'Gửi tin nhắn', exact: true }).click();
    await page.waitForFunction(() => !document.querySelector('.assistant-message.is-pending'));
    check('assistant error has a retry action', await panel.getByRole('button', { name: 'Gửi lại câu hỏi', exact: true }).isVisible());
    await panel.getByRole('button', { name: 'Gửi lại câu hỏi', exact: true }).click();
    await page.waitForFunction(() => !document.querySelector('.assistant-message.is-pending'));
    check('assistant retry recovers without duplicating the user message', await panel.locator('.assistant-message-user').count() === 2 && await panel.locator('.assistant-message.is-error').count() === 0);

    await page.reload();
    check('reload drops the auth token and returns to real login', await page.getByRole('heading', { name: 'Đăng nhập không gian làm việc' }).isVisible());
    check('no runtime JavaScript errors', errors.length === 0);
    console.log(`ASSISTANT AUTH UX: ${checks.length} checks passed.`);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
