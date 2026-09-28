import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import { marked } from 'marked';

const require = createRequire(import.meta.url);
const markedVersion = require('marked/package.json').version;
const scriptPath = fileURLToPath(import.meta.url);
const defaultRoot = path.resolve(path.dirname(scriptPath), '../..');
const skippedDirectories = new Set([
  '.git', '.local', '.test-runtime', '.venv', 'node_modules', 'dist',
  '__pycache__', '.pytest_cache', 'excel-data', 'data_that',
]);

function markdownFiles(root) {
  const files = [];
  function visit(directory) {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      if (entry.isDirectory()) {
        if (!skippedDirectories.has(entry.name) && !entry.name.startsWith('.pytest-temp')) {
          visit(path.join(directory, entry.name));
        }
      } else if (entry.isFile() && entry.name.toLowerCase().endsWith('.md')) {
        files.push(path.join(directory, entry.name));
      }
    }
  }
  visit(root);
  return files.sort();
}

function plainText(tokens = []) {
  return tokens.map((token) => {
    if (token.tokens) return plainText(token.tokens);
    return token.text ?? '';
  }).join('');
}

function slug(text) {
  return [...text.normalize('NFC').trim().toLowerCase()]
    .filter((character) => /[\p{L}\p{M}\p{N}_\-\s]/u.test(character))
    .join('')
    .replace(/\s/g, '-');
}

function anchorsFor(tokens) {
  const anchors = new Set();
  const repeated = new Map();
  for (const token of tokens) {
    if (token.type === 'heading') {
      const base = slug(plainText(token.tokens));
      const count = repeated.get(base) ?? 0;
      repeated.set(base, count + 1);
      anchors.add(count ? `${base}-${count}` : base);
    }
    if (token.type === 'html') {
      for (const match of token.raw.matchAll(/<a\s+[^>]*\b(?:id|name)=["']([^"']+)["'][^>]*>/gi)) {
        anchors.add(match[1]);
      }
    }
  }
  return anchors;
}

function targetsFor(tokens) {
  const targets = [];
  function visit(item) {
    if (Array.isArray(item)) {
      item.forEach(visit);
      return;
    }
    if (!item || typeof item !== 'object') return;
    if (['link', 'image', 'def'].includes(item.type) && item.href) {
      targets.push({ kind: item.type, href: item.href });
    }
    if (item.type === 'text' && item.raw) {
      for (const match of item.raw.matchAll(/!?\[([^\]\n]+)\]\[([^\]\n]*)\]/g)) {
        if (match.index > 0 && item.raw[match.index - 1] === '\\') continue;
        targets.push({ kind: 'missing-reference', href: match[2] || match[1] });
      }
      for (const match of item.raw.matchAll(/!\[([^\]\n]+)\](?!\(|\[)/g)) {
        if (match.index > 0 && item.raw[match.index - 1] === '\\') continue;
        targets.push({ kind: 'missing-image-reference', href: match[1] });
      }
    }
    if (item.tokens) visit(item.tokens);
    if (item.items) visit(item.items);
    if (item.header) visit(item.header);
    if (item.rows) visit(item.rows);
  }
  visit(tokens);
  return targets;
}

function exactCasePath(root, target) {
  const relative = path.relative(root, target);
  if (relative === '..' || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) {
    return { error: 'outside-package' };
  }
  let current = root;
  for (const component of relative.split(path.sep).filter(Boolean)) {
    if (!fs.existsSync(current)) return { error: 'missing-target' };
    const names = fs.readdirSync(current);
    if (!names.includes(component)) {
      return { error: names.some((name) => name.toLowerCase() === component.toLowerCase())
        ? 'case-mismatch' : 'missing-target' };
    }
    current = path.join(current, component);
  }
  return { path: current };
}

function safeTarget(href) {
  return `sha256:${createHash('sha256').update(href).digest('hex').slice(0, 12)}`;
}

export function checkMarkdownRoot(root = defaultRoot) {
  const packageRoot = path.resolve(root);
  const files = markdownFiles(packageRoot);
  const parsed = new Map();
  const issues = [];
  let targetCount = 0;
  for (const file of files) {
    const tokens = marked.lexer(fs.readFileSync(file, 'utf8'), { gfm: true });
    parsed.set(file, { tokens, anchors: anchorsFor(tokens) });
  }
  for (const file of files) {
    const relativeFile = path.relative(packageRoot, file).split(path.sep).join('/');
    for (const { kind, href } of targetsFor(parsed.get(file).tokens)) {
      targetCount += 1;
      if (kind.startsWith('missing-')) {
        issues.push({ file: relativeFile, reason: kind, target: safeTarget(href) });
        continue;
      }
      if (/^(?:[a-z][a-z\d+.-]*:|\/\/)/i.test(href)
          && !/^(?:file:|[a-z]:[\\/])/i.test(href)) continue;
      const hashIndex = href.indexOf('#');
      const rawPath = hashIndex < 0 ? href : href.slice(0, hashIndex);
      const rawAnchor = hashIndex < 0 ? '' : href.slice(hashIndex + 1);
      let localPath;
      let anchor;
      try {
        localPath = decodeURIComponent(rawPath.split('?')[0]);
        anchor = decodeURIComponent(rawAnchor);
      } catch {
        issues.push({ file: relativeFile, reason: 'bad-url-encoding', target: safeTarget(href) });
        continue;
      }
      if (path.isAbsolute(localPath) || /^[a-z]:[\\/]/i.test(localPath)) {
        issues.push({ file: relativeFile, reason: 'absolute-local-path', target: safeTarget(href) });
        continue;
      }
      const target = localPath ? path.resolve(path.dirname(file), localPath) : file;
      const resolved = exactCasePath(packageRoot, target);
      if (resolved.error) {
        issues.push({ file: relativeFile, reason: resolved.error, target: safeTarget(href) });
        continue;
      }
      if (!fs.existsSync(resolved.path)) {
        issues.push({ file: relativeFile, reason: 'missing-target', target: safeTarget(href) });
        continue;
      }
      if (!anchor) continue;
      if (!fs.statSync(resolved.path).isFile()) {
        issues.push({ file: relativeFile, reason: 'anchor-on-directory', target: safeTarget(href) });
        continue;
      }
      if (!resolved.path.toLowerCase().endsWith('.md')) {
        issues.push({ file: relativeFile, reason: 'anchor-on-non-markdown', target: safeTarget(href) });
        continue;
      }
      const destination = parsed.get(resolved.path)
        ?? { anchors: anchorsFor(marked.lexer(fs.readFileSync(resolved.path, 'utf8'), { gfm: true })) };
      if (!destination.anchors.has(anchor)) {
        issues.push({ file: relativeFile, reason: 'missing-anchor', target: safeTarget(href) });
      }
    }
  }
  return { files: files.length, targets: targetCount, markedVersion, issues };
}

if (process.argv[1] && path.resolve(process.argv[1]) === scriptPath) {
  const root = process.argv[2] ? path.resolve(process.argv[2]) : defaultRoot;
  const result = checkMarkdownRoot(root);
  console.log(`FS05_LINKS=${result.issues.length ? 'FAIL' : 'PASS'} files=${result.files} targets=${result.targets} marked=${result.markedVersion} issues=${result.issues.length}`);
  for (const issue of result.issues) {
    console.log(`${issue.file}: ${issue.reason} target=${issue.target}`);
  }
  if (result.issues.length) process.exitCode = 1;
}
