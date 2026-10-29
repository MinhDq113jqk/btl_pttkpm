import test from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const React = require('react');
const code = (await build({ stdin: { contents: "export {ExchangePanel} from './SadExtensionPanels'; export {MyWorkPanel} from './SadWorkDetails'; export {OperationalWorkspacePanel} from './OperationalWorkspacePanel'; export {SchemaFields} from './SchemaFields';", resolveDir: fileURLToPath(new URL('../src/components/', import.meta.url)), loader: 'jsx' }, bundle: true, platform: 'node', format: 'cjs', write: false, external: ['react', 'lucide-react'], loader: { '.css': 'empty' } })).outputFiles[0].text;

function host() {
  const scopes = new Map(), effects = []; let slots, index;
  const hooks = {
    useState(initial) { const i = index++, current = slots; if (!(i in current)) current[i] = typeof initial === 'function' ? initial() : initial; return [current[i], next => { current[i] = typeof next === 'function' ? next(current[i]) : next; }]; },
    useRef(initial) { const i = index++; return slots[i] ||= { current: initial }; },
    useEffect(fn, deps) { const i = index++, current = slots, prior = current[i]; if (!prior || deps.some((v,n) => v !== prior.deps[n])) effects.push(() => { prior?.cleanup?.(); current[i] = { deps, cleanup: fn() }; }); },
  };
  const module = { exports: {} };
  new Function('require', 'module', 'exports', code)(name => name === 'react' ? { ...React, ...hooks } : name === 'lucide-react' ? new Proxy({}, { get: () => () => null }) : require(name), module, module.exports);
  return { ...module.exports, render(fn, scope = 'main') { if (!scopes.has(scope)) scopes.set(scope, []); slots = scopes.get(scope); index = 0; return fn(); }, flush() { effects.splice(0).forEach(fn => fn()); }, unmount() { scopes.forEach(current => current.forEach(slot => slot?.cleanup?.())); } };
}
function nodes(tree, predicate) { if (!tree || typeof tree !== 'object') return []; if (Array.isArray(tree)) return tree.flatMap(c => nodes(c, predicate)); return [...(predicate(tree) ? [tree] : []), ...nodes(tree.props?.children, predicate)]; }
function text(tree) { if (typeof tree === 'string' || typeof tree === 'number') return String(tree); if (Array.isArray(tree)) return tree.map(text).join(''); return tree?.props ? text(tree.props.children) : ''; }
const field = (tree, label) => nodes(tree, n => n.type?.name === 'Field' && n.props.label === label)[0];
const forms = tree => nodes(tree, n => n.type === 'form');
const event = { preventDefault() {} };
const tick = () => new Promise(resolve => setImmediate(resolve));
const endpoint = { id: 'endpoint', building_id: 'building', kind: 'METER', status: 'DISABLED', adapter: 'JSON_FILE', version: 1 };

test('FE-40 saving adapter configuration preserves a paused endpoint', async t => {
  const h = host(); t.after(() => h.unmount()); const commands = [];
  const render = () => h.render(() => h.ExchangePanel({ client: { portalGet: async () => ({}) }, row: endpoint, command: { run: async (...args) => commands.push(args) } }));
  const tree = render();
  assert.equal(field(tree, 'Trạng thái').props.children.props.value, 'DISABLED');
  await forms(tree)[0].props.onSubmit(event);
  assert.equal(commands[0][1].status, 'DISABLED');
});

test('FE-40 incoming validation failures stay in the panel and cannot reject the submit handler', async t => {
  const h = host(); t.after(() => h.unmount()); let writes = 0;
  const schema = { properties: { external_id: { type: 'string' }, amount_vnd: { type: 'integer' } }, required: ['external_id', 'amount_vnd'] };
  const client = { portalGet: async path => path.endsWith('/contract') ? { inputs: { readings: { kind: 'METER', label: 'Chỉ số', schema } } } : { items: [] } };
  const command = { run: async () => { writes++; return {}; } };
  const render = () => h.render(() => h.ExchangePanel({ client, row: endpoint, command }));
  render(); h.flush(); await tick(); let tree = render();
  field(tree, 'Tiếp nhận dữ liệu').props.children.props.onChange({ target: { value: 'readings' } }); tree = render();
  nodes(tree, n => n.type?.name === 'SchemaFields')[0].props.setForm({ external_id: 'EXT-01', amount_vnd: '9007199254740993' }); tree = render();
  await assert.doesNotReject(async () => forms(tree)[2].props.onSubmit(event));
  assert.equal(writes, 0);
  assert.equal(nodes(render(), n => n.type?.name === 'State' && n.props.state.error).length, 1);
  nodes(render(), n => n.type?.name === 'SchemaFields')[0].props.setForm({ external_id: 'EXT-01', amount_vnd: '500' });
  assert.equal(nodes(render(), n => n.type?.name === 'State' && n.props.state.error).length, 0);
  await forms(render())[2].props.onSubmit(event);
  assert.equal(writes, 1);
});

test('FE-40 exchange inputs are locked during a command so late receipt cannot erase new input', t => {
  const h = host(); t.after(() => h.unmount());
  const tree = h.render(() => h.ExchangePanel({ client: {}, row: endpoint, command: { busy: true } }));
  assert.ok(nodes(tree, n => n.type === 'fieldset' && n.props.disabled).length);
});

async function actions(t, row) {
  const h = host(); t.after(() => h.unmount());
  const client = { portalGet: async path => path.endsWith('/catalog') ? path.includes('/control/') ? { items: [{ kind: 'integrations', can_create: false }] } : { items: [] } : path.endsWith('/options') ? {} : { items: [row] } };
  const render = () => h.render(() => h.OperationalWorkspacePanel({ client, buildingId: 'building' }));
  render(); h.flush(); await tick(); let tree = render();
  let section = nodes(tree, n => n.type?.name === 'WorkspaceSection')[0];
  const renderSection = () => h.render(() => section.type(section.props), 'section');
  renderSection(); h.flush(); await tick(); tree = renderSection();
  const records = nodes(tree, n => n.type?.name === 'Records')[0];
  tree = records.props.children(row);
  const domain = nodes(tree, n => n.type?.name === 'DomainActions')[0];
  return domain.type(domain.props);
}

test('FE-40 legacy card queue is restricted to ACCESS and PARKING endpoints', async t => {
  for (const kind of ['METER', 'ACCOUNTING', 'BANK', 'ACCESS', 'PARKING']) await t.test(kind, async t => {
    const tree = await actions(t, { ...endpoint, kind });
    const cardQueue = nodes(tree, n => n.type?.name === 'ParameterAction' && n.props.label === 'Lập lệnh đồng bộ thẻ');
    assert.equal(cardQueue.length, ['ACCESS','PARKING'].includes(kind) ? 1 : 0);
  });
});

test('FE-40 refreshed endpoint versions remount configuration from current values', async t => {
  const first = await actions(t, endpoint);
  const next = await actions(t, { ...endpoint, version: 2, adapter: 'JSON_REGISTRY', status: 'ACTIVE' });
  const panel = tree => nodes(tree, n => n.type?.name === 'ExchangePanel')[0];
  assert.notEqual(panel(first).key, panel(next).key);
});

test('FE-36 acknowledged training displays evidence without offering a duplicate acknowledgement', async t => {
  const h = host(); t.after(() => h.unmount());
  const rows = [{ id: 'training-done', kind: 'TRAINING', version: 2, title: 'Đã học SOP', data: {}, my_acknowledgement: { result: 'Đã tiếp nhận', evidence_reference: 'ACK-01' } }, { id: 'training-new', kind: 'TRAINING', version: 1, title: 'SOP mới', data: {} }];
  const client = { portalGet: async () => ({ items: rows }) };
  const render = () => h.render(() => h.MyWorkPanel({ client }));
  render(); h.flush(); await tick(); const tree = render();
  const records = nodes(tree, n => n.type?.name === 'Records')[0];
  const done = records.props.children(rows[0]); const pending = records.props.children(rows[1]);
  assert.equal(forms(done).length, 0);
  assert.ok(text(done).includes('Đã xác nhận đào tạo'));
  assert.deepEqual(nodes(done, n => n.type?.name === 'StructuredDetails').at(-1).props.value, rows[0].my_acknowledgement);
  assert.equal(forms(pending).length, 1);
});

test('FE-36 changing assignment target or requirements clears dependent work and roster selections', t => {
  const h = host(); t.after(() => h.unmount());
  const schema = { properties: { target_type: { type: 'string', enum: ['WORK_ORDER','CLEANING','SECURITY'] }, target_id: { type: 'string' }, roster_id: { type: 'string' }, required_skill: { type: 'string' }, sop_id: { type: 'string' } } };
  const initial = { target_type:'WORK_ORDER', target_id:'wo1', roster_id:'roster1', required_skill:'electricity', sop_id:'sop1' };
  let form;
  const render = () => h.render(() => h.SchemaFields({ schema, form, setForm: update => {form=update(form);}, options:{}, buildingId:'b1' }));
  for (const key of ['target_type','target_id','required_skill','sop_id']) {
    form={...initial}; const tree=render();
    const node=nodes(tree,n=>n.key===key)[0]; const control=node.props.children || node;
    control.props.onChange({target:{value:key==='target_type'?'CLEANING':'new-source'}});
    assert.equal(form.roster_id,'',`${key}: old roster must be cleared`);
    if(key==='target_type')assert.equal(form.target_id,'');else if(key!=='target_id')assert.equal(form.target_id,'wo1');
  }
});
