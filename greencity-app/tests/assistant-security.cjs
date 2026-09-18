const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const appRoot = path.resolve(__dirname, '..');
const sourceRoot = path.join(appRoot, 'src');
const bundleRoot = path.join(appRoot, 'dist');
const forbidden = [
  ['Gemini environment key name', /GEMINI_API_KEY/],
  ['Gemini upstream URL', /generativelanguage\.googleapis\.com/],
  ['Gemini API-key header', /x-goog-api-key/i],
];

function textFiles(root) {
  if (!fs.existsSync(root)) return [];
  const entries = fs.readdirSync(root, { withFileTypes: true });
  return entries.flatMap(entry => {
    const file = path.join(root, entry.name);
    if (entry.isDirectory()) return textFiles(file);
    return /\.(?:js|css|html|map)$/.test(entry.name) ? [file] : [];
  });
}

const sourceFiles = textFiles(sourceRoot);
const bundleFiles = textFiles(bundleRoot);
assert.ok(sourceFiles.length > 0, 'frontend source files must exist');
assert.ok(bundleFiles.length > 0, 'run the frontend build before scanning the bundle');

for (const file of [...sourceFiles, ...bundleFiles]) {
  const content = fs.readFileSync(file, 'utf8');
  for (const [label, pattern] of forbidden) {
    assert.doesNotMatch(content, pattern, `${label} found in ${path.relative(appRoot, file)}`);
  }
}

console.log(`ASSISTANT SECURITY: scanned ${sourceFiles.length} source and ${bundleFiles.length} bundle files.`);
