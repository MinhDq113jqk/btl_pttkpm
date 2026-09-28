const { spawn, spawnSync } = require('node:child_process');
const path = require('node:path');

const appRoot = path.resolve(__dirname, '..');
const baseUrl = process.env.UX_BASE_URL || 'http://127.0.0.1:3000';
const flows = [
  { id: 'GF-01', label: 'Đăng nhập, /auth/me, menu vai trò, đổi site/mật khẩu, đăng xuất', suites: ['staff-ux.cjs'] },
  { id: 'GF-02', label: 'Cư dân tạo yêu cầu và nhân viên xử lý Work Order', suites: ['resident-ux.cjs', 'work-order-ux.cjs'] },
  { id: 'GF-03', label: 'Asset, maintenance plan, occurrence và history', suites: ['maintenance-ux.cjs'] },
  { id: 'GF-04', label: 'Ca vệ sinh, checklist đạt/trượt và xử lý lại', suites: ['cleaning-ux.cjs', 'cleaning-manager-ux.cjs'] },
  { id: 'GF-05', label: 'Ca an ninh, bàn giao, tuần tra và incident mức cao', suites: ['security-ux.cjs', 'security-manager-ux.cjs'] },
  { id: 'GF-06', label: 'Parcel intake, PIN, exception, evidence và liên kết hồ sơ', suites: ['parcel-ux.cjs'] },
  { id: 'GF-07', label: 'Billing, invoice, payment, unmatched và credit', suites: ['billing-ux.cjs', 'payment-ux.cjs'] },
  { id: 'GF-08', label: 'KPI, drill-down, audit và notifications cùng as_of', suites: ['dashboard-ux.cjs', 'notification-ux.cjs'] },
];

const delay = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));

async function isUiReady(url) {
  try {
    return (await fetch(url)).ok;
  } catch {
    return false;
  }
}

async function waitForUi(url, serverProcess) {
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) {
    if (serverProcess?.exitCode !== null && serverProcess?.exitCode !== undefined) {
      throw new Error(`Vite exited with code ${serverProcess.exitCode} before serving the UI.`);
    }
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {}
    await delay(300);
  }
  throw new Error(`Frontend did not become ready at ${url}.`);
}

async function main() {
  let serverProcess;
  let ownsServer = false;
  let failed = false;
  try {
    if (process.env.UX_BASE_URL) {
      await waitForUi(baseUrl);
    } else if (!await isUiReady(baseUrl)) {
      const viteEntry = path.join(appRoot, 'node_modules', 'vite', 'bin', 'vite.js');
      serverProcess = spawn(process.execPath, [viteEntry, '--configLoader', 'runner', '--host', '127.0.0.1'], {
        cwd: appRoot,
        stdio: 'ignore',
        windowsHide: true,
      });
      ownsServer = true;
      await waitForUi(baseUrl, serverProcess);
    }

    process.env.UX_BASE_URL = baseUrl;
    for (const flow of flows) {
      console.log(`\n${flow.id}: ${flow.label}`);
      for (const suite of flow.suites) {
        const result = spawnSync(process.execPath, [path.join(__dirname, suite)], {
          cwd: appRoot,
          stdio: 'inherit',
          env: process.env,
        });
        if (result.error) {
          console.error(`${suite}: could not start (${result.error.message})`);
          failed = true;
        } else if (result.status !== 0) {
          console.error(`${suite}: failed with exit code ${result.status}`);
          failed = true;
        }
      }
    }

    console.log('\nBrowser Golden Flow suites use deterministic API fixtures. Database persistence, scope, audit, and state-transition evidence is provided by the isolated PostgreSQL integration suite.');
  } finally {
    if (ownsServer && serverProcess && serverProcess.exitCode === null) {
      serverProcess.kill();
      await Promise.race([
        new Promise(resolve => serverProcess.once('exit', resolve)),
        delay(3000),
      ]);
    }
  }
  if (failed) process.exitCode = 1;
}

main().catch(error => {
  console.error(error.message);
  process.exitCode = 1;
});
