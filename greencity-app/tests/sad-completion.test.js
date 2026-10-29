import test from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const directory = fileURLToPath(new URL('../src/components/', import.meta.url));
async function bundle(contents, externalIcons = false) {
  const result = await build({ stdin: { contents, resolveDir: directory, loader: 'jsx' }, bundle: true, platform: 'node', format: 'cjs', write: false, external: ['react', 'react-dom/server', ...(externalIcons ? ['lucide-react'] : [])], loader: { '.css': 'empty' } });
  return result.outputFiles[0].text;
}

test('SAD workflow UI renders forms and all management destinations without browser or API calls', async () => {
  const code = await bundle(`import React from 'react'; import {renderToStaticMarkup} from 'react-dom/server'; import {PortalManagementView} from './PortalManagementView'; import {SlaControlPanel,InitDatasetPanel,CommunityTasksPanel} from './SadCompletionPanels'; import {SadReportsPanel} from './SadReportsPanel'; export function render(){ const client={};return renderToStaticMarkup(<><PortalManagementView client={client} account={{id:'synthetic',roles:['admin']}}/><SlaControlPanel client={client} buildingId="synthetic" roles={['admin']}/><InitDatasetPanel client={client} buildingId="synthetic"/><CommunityTasksPanel client={client} buildingId="synthetic"/><SadReportsPanel client={client} buildingId="synthetic" roles={['admin']}/></>);}`);
  const module = { exports: {} }; new Function('require', 'module', 'exports', code)(createRequire(import.meta.url), module, module.exports);
  const html = module.exports.render();
  for (const label of ['Quyết định &amp; nhiệm vụ', 'SLA &amp; chất lượng', 'Dữ liệu khởi tạo', 'KPI, chi tiết &amp; chứng từ', 'Căn cứ chính sách BQL đã xác nhận', 'Giá trị kỳ vọng', 'Batch CSV']) assert.ok(html.includes(label), label);
  assert.ok(html.includes('Đang tải')); assert.ok(!html.includes('textarea placeholder="JSON'));
});

// Execute the real hooks against a small hook host; no DOM, browser or backend.
function host() {
  const slots = []; let index = 0; const effects = [];
  const hooks = {
    useState(initial) { const i = index++; if (!(i in slots)) slots[i] = typeof initial === 'function' ? initial() : initial; return [slots[i], value => { slots[i] = typeof value === 'function' ? value(slots[i]) : value; }]; },
    useRef(initial) { const i = index++; slots[i] ||= { current: initial }; return slots[i]; },
    useEffect(fn, deps) { const i = index++; const prev = slots[i]; if (!prev || deps.some((v, n) => v !== prev.deps[n])) { effects.push(() => { prev?.cleanup?.(); slots[i] = { deps, cleanup: fn() }; }); } },
  };
  return { hooks, render(fn) { index = 0; return fn(); }, flush() { effects.splice(0).forEach(fn => fn()); }, unmount() { slots.forEach(slot => slot?.cleanup?.()); } };
}
const settle = async () => { await Promise.resolve(); await Promise.resolve(); };

test('site meeting exposes minutes and site decisions load without a building selection', async () => {
  const require = createRequire(import.meta.url); const React = require('react');
  const { renderToStaticMarkup } = require('react-dom/server'); const h = host(); const calls = [];
  const icons = { LoaderCircle: () => null, RefreshCw: () => null };
  const code = await bundle("export {ContentExecution,CommunityTasksPanel} from './SadCompletionPanels';", true);
  const m = { exports: {} };
  new Function('require', 'module', 'exports', code)(name => name === 'react' ? { ...React, ...h.hooks } : name === 'lucide-react' ? icons : require(name), m, m.exports);
  const client = { portalGet(path, params) { calls.push({ path, params }); return Promise.resolve(path === '/completion-options' ? { accounts: [{ id: 'director', label: 'Synthetic director' }] } : { items: [] }); } };
  const props = { client, manager: true, row: { id: 'synthetic', building_id: null, kind: 'MEETING', status: 'PUBLISHED', version: 1, title: 'Synthetic meeting', body: 'Synthetic body' } };
  const render = () => h.render(() => m.exports.ContentExecution(props));
  let tree = render(); h.flush(); tree.props.children[0].props.onClick(); tree = render(); h.flush(); await settle();
  const html = renderToStaticMarkup(render());
  assert.ok(html.includes('Ghi biên bản và giao nhiệm vụ')); assert.ok(html.includes('Synthetic director'));
  assert.ok(calls.some(c => c.path === '/completion-options' && !c.params.building_id)); h.unmount();
  const taskHost = host(); const tasks = { exports: {} };
  new Function('require', 'module', 'exports', code)(name => name === 'react' ? { ...React, ...taskHost.hooks } : name === 'lucide-react' ? icons : require(name), tasks, tasks.exports);
  taskHost.render(() => tasks.exports.CommunityTasksPanel({ client, buildingId: '' })); taskHost.flush(); await settle();
  assert.ok(calls.some(c => c.path === '/community-tasks')); taskHost.unmount();
});

const hooksCode = await bundle("export {usePortalData,usePortalCommand} from './PortalPanels';", true);
function loadHooks(h) { const m = { exports: {} }; new Function('require', 'module', 'exports', hooksCode)(name => name === 'react' ? h.hooks : {}, m, m.exports); return m.exports; }

test('changing context immediately hides old data and discards a late old response', async () => {
  const h = host(); const { usePortalData } = loadHooks(h); const pending = [];
  const client = { portalGet(path, params, { signal }) { return new Promise(resolve => pending.push({ params, signal, resolve })); } };
  let context = 'A'; const render = () => h.render(() => usePortalData(client, '/dossiers', { unit_id: context }));
  render(); h.flush(); pending[0].resolve({ items: ['A-private'] }); await settle(); assert.equal(render().data.items[0], 'A-private');
  context = 'B'; assert.equal(render().data, null); h.flush(); assert.equal(pending[0].signal.aborted, true);
  context = 'C'; assert.equal(render().data, null); h.flush(); pending[1].resolve({ items: ['B-late'] }); await settle(); assert.equal(render().data, null);
  pending[2].resolve({ items: ['C-current'] }); await settle(); assert.equal(render().data.items[0], 'C-current'); h.unmount();
});

test('mutations deduplicate rapid clicks, retain retry key and suppress callback after context unmount', async () => {
  const h = host(); const { usePortalCommand } = loadHooks(h); const calls = []; let done = 0;
  const client = { portalCommand(path, body, opts) { return new Promise((resolve, reject) => calls.push({ opts, resolve, reject })); } };
  const render = () => h.render(() => usePortalCommand(client, () => done++)); let command = render(); h.flush();
  const first = command.run('/synthetic', { value: 1 }); assert.equal(await command.run('/synthetic', { value: 1 }), null); assert.equal(calls.length, 1);
  calls[0].reject(new Error('Synthetic connection error')); await first; command = render();
  const second = command.run('/synthetic', { value: 1 }); assert.equal(calls[1].opts.idempotencyKey, calls[0].opts.idempotencyKey);
  h.unmount(); assert.equal(calls[1].opts.signal.aborted, true); calls[1].resolve({ id: 'synthetic' }); assert.equal(await second, null); assert.equal(done, 0);
});
