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
    const firstAssistantRequest = page.waitForRequest(request => request.url().endsWith('/api/v1/assistant/chat') && request.method() === 'POST');
    await panel.getByRole('button', { name: 'Gửi tin nhắn', exact: true }).click();
    check('assistant shows loading while backend request is pending', await panel.getByText('Green Assistant đang trả lời...', { exact: true }).isVisible());
    const firstRequestBody = await (await firstAssistantRequest).postDataJSON();
    check('assistant sends only the question body without client scope', JSON.stringify(firstRequestBody) === JSON.stringify({ message: 'Công việc quá hạn' }) && !JSON.stringify(firstRequestBody).match(/tenant_id|site_id|building_id|role/));
    await page.waitForFunction(() => !document.querySelector('.assistant-message.is-pending'));
    check('assistant renders the backend reply', await panel.locator('.assistant-message-assistant').innerText().then(text => text.includes('Backend đã xử lý')));

    await input.fill('thử lỗi');
    await panel.getByRole('button', { name: 'Gửi tin nhắn', exact: true }).click();
    await page.waitForFunction(() => !document.querySelector('.assistant-message.is-pending'));
    check('assistant error has a retry action', await panel.getByRole('button', { name: 'Gửi lại câu hỏi', exact: true }).isVisible());
    await panel.getByRole('button', { name: 'Gửi lại câu hỏi', exact: true }).click();
    await page.waitForFunction(() => !document.querySelector('.assistant-message.is-pending'));
    check('assistant retry recovers without duplicating the user message', await panel.locator('.assistant-message-user').count() === 2 && await panel.locator('.assistant-message.is-error').count() === 0);

    await page.reload();
    check('reload drops the auth token and returns to real login', await page.getByRole('heading', { name: 'Đăng nhập GreenCity' }).isVisible());
    check('no runtime JavaScript errors', errors.length === 0);
    console.log(`ASSISTANT AUTH UX: ${checks.length} checks passed.`);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
