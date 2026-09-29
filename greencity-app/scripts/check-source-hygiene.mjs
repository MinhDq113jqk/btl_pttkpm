import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const root = path.resolve(process.cwd(), 'src');
const allowedExtensions = new Set(['.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx', '.css']);
const forbiddenBasenames = new Set([
  'mockData.js',
  'desktopData.js',
  'staffRoles.js',
  'MediaChannelsView.jsx',
  'UrbanAmenitiesView.jsx',
  'RefundFormView.jsx',
  'RefundReview.jsx',
  'StaffDashboard.jsx',
  'TasksMobileView.jsx',
  'MobileFolderModal.jsx',
  'MobileBottomNav.jsx',
]);
const forbiddenSourceTokens = [
  ['legacy prototype symbol', /\b(sampleRefundCase|mediaData|amenitiesData)\b/],
  ['debugger statement', /(^|[^\w])debugger\s*;/m],
  ['console.log debug call', /\bconsole\.log\s*\(/],
  ['OpenAI-style secret literal', /\bsk-[A-Za-z0-9_-]{16,}\b/],
  ['Google API key literal', /\bAIza[A-Za-z0-9_-]{20,}\b/],
  ['JWT-like bearer literal', /Bearer\s+eyJ[A-Za-z0-9._-]{20,}/],
];
const absoluteUrl = /https?:\/\/[^\s'"`)]+/g;
const allowedAbsoluteUrls = new Set([
  // Product runtime should use same-origin or environment-driven endpoints.
]);

function walk(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap(entry => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return walk(full);
    return [full];
  });
}

const issues = [];
const files = walk(root).filter(file => allowedExtensions.has(path.extname(file).toLowerCase()));
for (const file of files) {
  const relative = path.relative(process.cwd(), file).split(path.sep).join('/');
  const basename = path.basename(file);
  if (forbiddenBasenames.has(basename)) {
    issues.push(`${relative}: forbidden legacy/prototype file`);
    continue;
  }
  const text = fs.readFileSync(file, 'utf8');
  for (const [label, pattern] of forbiddenSourceTokens) {
    if (pattern.test(text)) issues.push(`${relative}: ${label}`);
  }
  for (const match of text.matchAll(absoluteUrl)) {
    if (!allowedAbsoluteUrls.has(match[0])) {
      issues.push(`${relative}: hard-coded absolute URL`);
    }
  }
}

if (issues.length) {
  for (const issue of issues) console.error(`SOURCE_HYGIENE_ISSUE ${issue}`);
  console.error(`P2_SOURCE_HYGIENE=FAIL files=${files.length} issues=${issues.length}`);
  process.exit(1);
}

console.log(`P2_SOURCE_HYGIENE=PASS files=${files.length} issues=0`);
