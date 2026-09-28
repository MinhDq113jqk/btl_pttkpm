import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { test } from 'node:test';
import { checkMarkdownRoot } from '../scripts/check-markdown-links.mjs';

function fixture(t, files) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'greencity-links-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  for (const [name, content] of Object.entries(files)) {
    const file = path.join(root, name);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, content);
  }
  return root;
}

test('accepts local Unicode paths, fragments, images, and external URLs', (t) => {
  const root = fixture(t, {
    'README.md': '# Mở đầu\n[Xem tài liệu](tài liệu.md#tiêu-đề)\n![Sơ đồ](ảnh.png)\n[Web](https://example.org)\n',
    'tài liệu.md': '# Tiêu đề\n',
    'ảnh.png': 'fixture',
  });
  assert.deepEqual(checkMarkdownRoot(root).issues, []);
});

test('reports missing files, fragments, references, and wrong path case', (t) => {
  const root = fixture(t, {
    'README.md': '[Lost](missing.md)\n[Section](Guide.md#lost)\n[Case](guide.md)\n[Reference][absent]\n![Image][unknown]\n',
    'Guide.md': '# Present\n',
  });
  const reasons = checkMarkdownRoot(root).issues.map(({ reason }) => reason);
  assert.deepEqual(reasons.sort(), [
    'case-mismatch',
    'missing-anchor',
    'missing-reference',
    'missing-reference',
    'missing-target',
  ].sort());
});

test('resolves directories, encoded spaces, reference definitions, and duplicate headings', (t) => {
  const root = fixture(t, {
    'README.md': '[Folder](docs/)\n[Second][guide]\n[Space](docs/file%20name.md)\n\n[guide]: docs/guide.md#same-1\n',
    'docs/guide.md': '# Same\n# Same\n',
    'docs/file name.md': '# File\n',
  });
  assert.deepEqual(checkMarkdownRoot(root).issues, []);
});
