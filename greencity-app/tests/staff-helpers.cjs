async function loginAs(page, role = 'director') {
  const accountSelector = page.getByLabel('Tài khoản nhân viên mẫu', { exact: true });
  if (!await accountSelector.isVisible()) {
    const chatClose = page.getByRole('button', { name: 'Thu gọn Green Assistant', exact: true });
    if (await chatClose.isVisible()) await chatClose.click();
    await page.getByRole('button', { name: 'Đổi tài khoản hoặc đăng xuất', exact: true }).click();
    await page.getByRole('dialog', { name: 'Đăng xuất tài khoản mẫu?' }).getByRole('button', { name: 'Đăng xuất', exact: true }).click();
  }
  await accountSelector.selectOption(`demo-${role}`);
  await page.getByRole('button', { name: 'Vào không gian mẫu', exact: true }).click();
  await page.getByRole('navigation', { name: 'Điều hướng chính' }).waitFor();
}
module.exports = { loginAs };
