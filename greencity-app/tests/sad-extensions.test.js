import test from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { requestAssistantReply } from '../src/services/greenAssistant.js';
import { operationKinds, referenceSources, serializeFields } from '../src/data/operationalForms.js';
import { createApiClient } from '../src/services/apiClient.js';
import { canViewTab, createAuthenticatedAccount, getAllowedNav } from '../src/data/authSession.js';

async function render(contents) {
  const result = await build({ stdin:{contents,resolveDir:fileURLToPath(new URL('../src/components/',import.meta.url)),loader:'jsx'},bundle:true,platform:'node',format:'cjs',write:false,external:['react','react-dom/server'],loader:{'.css':'empty'} });
  const module={exports:{}};new Function('require','module','exports',result.outputFiles[0].text)(createRequire(import.meta.url),module,module.exports);
  return module.exports.render();
}

test('energy source selection and project expense references render from their actual domain', async () => {
  const html = await render(`import React from 'react';import {renderToStaticMarkup} from 'react-dom/server';import {SchemaFields} from './SchemaFields';export function render(){return renderToStaticMarkup(<><SchemaFields schema={{properties:{target_id:{type:'string'},procurement_id:{type:'string'}}}} form={{}} setForm={()=>{}} buildingId="B1" options={{operations_records:[{id:'E1',kind:'ENERGY_TARGET',label:'Định mức nước',building_id:'B1'},{id:'P1',kind:'PROJECT',label:'Dự án A',building_id:'B1'},{id:'X1',kind:'RULE',label:'Nội quy khác',building_id:'B1'}]}}/></>);}`);
  assert.ok(html.includes('Định mức nước'));assert.ok(html.includes('Dự án A'));assert.ok(!html.includes('Nội quy khác'));
});

test('assistant shows all support modes and keeps drafting limited to managers', async () => {
  const code = roles => `import React from 'react';import {renderToStaticMarkup} from 'react-dom/server';import {GroundedAssistantPanel} from './SadExtensionPanels';export function render(){return renderToStaticMarkup(<GroundedAssistantPanel client={{}} unitId="U1" roles={${JSON.stringify(roles)}}/>);}`;
  const manager=await render(code(['cskh']));const resident=await render(code(['resident']));
  for(const label of ['Tra cứu sổ tay','Xem trạng thái yêu cầu','Tóm tắt diễn biến','Chuyển đến CSKH']) assert.ok(resident.includes(label));
  assert.ok(manager.includes('Soạn bản nháp'));assert.ok(!resident.includes('Soạn bản nháp'));
});

test('grounded chat sends an idempotent search and uses the persisted answer', async () => {
  const calls=[];const client={supportAssistant:async (...args)=>{calls.push(args);return {messages:[{reply:'Quy định được công bố'}]};}};
  const controller=new AbortController();const reply=await requestAssistantReply({client,question:'Nội quy bãi xe',signal:controller.signal});
  assert.equal(reply,'Quy định được công bố');assert.deepEqual(calls[0][0],{mode:'SEARCH',query:'Nội quy bãi xe'});
  assert.equal(calls[0][1].signal,controller.signal);assert.ok(calls[0][1].idempotencyKey.startsWith('assistant-'));
});

test('extension records expose business names and typed ledger sources', () => {
  for(const kind of ['PROJECT_PROGRESS','PROJECT_DEFECT_RESOLUTION','COMMERCIAL_LEASE','ENERGY_REPORT','INSURANCE_POLICY']) assert.ok(operationKinds[kind]);
  assert.deepEqual(referenceSources.charge_id,['commercial_ledgers']);
  const schema={properties:{actual_quantity:{type:'number'},project_id:{type:'string'}},required:['actual_quantity','project_id']};
  assert.deepEqual(serializeFields(schema,{actual_quantity:'1.25',project_id:'P1'}),{actual_quantity:'1.25',project_id:'P1'});
});

test('resident lease deposit selectors remain separate from insurance and commercial contracts', async () => {
  const contents=title => `import React from 'react';import {renderToStaticMarkup} from 'react-dom/server';import {SchemaFields} from './SchemaFields';export function render(){return renderToStaticMarkup(<SchemaFields schema={${JSON.stringify(title)}} form={{}} setForm={()=>{}} buildingId="B1" options={{lease_contracts:[{id:'L1',label:'Thuê cư trú',building_id:'B1'}],operations_records:[{id:'D1',kind:'DEPOSIT_POLICY',label:'Cọc thuê cư trú',building_id:'B1'},{id:'I1',kind:'INSURANCE_POLICY',label:'Bảo hiểm A',building_id:'B1'},{id:'C1',kind:'COMMERCIAL_LEASE',label:'Thuê thương mại',building_id:'B1'}]}}/>);}`;
  const legacy=await render(contents({title:'LeaseDepositData',properties:{policy_id:{type:'string'},lease_id:{type:'string'}}}));
  assert.ok(legacy.includes('Cọc thuê cư trú'));assert.ok(legacy.includes('Thuê cư trú'));assert.ok(!legacy.includes('Bảo hiểm A'));assert.ok(!legacy.includes('Thuê thương mại'));
  const insurance=await render(contents({title:'InsuranceClaim',properties:{policy_id:{type:'string'},incident_id:{type:'string'}}}));
  assert.ok(insurance.includes('Bảo hiểm A'));assert.ok(!insurance.includes('Cọc thuê cư trú'));
  const commercial=await render(contents({title:'CommercialCharge',properties:{lease_id:{type:'string'}}}));
  assert.ok(commercial.includes('Thuê thương mại'));assert.ok(!commercial.includes('Thuê cư trú'));
});

// Run the real handlers/hooks without a browser or live server.
function hookHost() {
  const slots = []; let index = 0; const effects = [];
  const hooks = {
    useState(initial) { const i = index++; if (!(i in slots)) slots[i] = typeof initial === 'function' ? initial() : initial; return [slots[i], value => { slots[i] = typeof value === 'function' ? value(slots[i]) : value; }]; },
    useRef(initial) { const i = index++; slots[i] ||= { current: initial }; return slots[i]; },
    useEffect(fn, deps) { const i = index++; const previous = slots[i]; if (!previous || deps.some((v, n) => v !== previous.deps[n])) effects.push(() => { previous?.cleanup?.(); slots[i] = { deps, cleanup: fn() }; }); },
  };
  return { hooks, render(fn) { index = 0; return fn(); }, flush() { effects.splice(0).forEach(fn => fn()); }, unmount() { slots.forEach(slot => slot?.cleanup?.()); } };
}
const settle = () => new Promise(resolve => setImmediate(resolve));
const submit = { preventDefault() {} };
function elements(tree, predicate) {
  if (!tree || typeof tree !== 'object') return [];
  if (Array.isArray(tree)) return tree.flatMap(child => elements(child, predicate));
  return [...(predicate(tree) ? [tree] : []), ...elements(tree.props?.children, predicate)];
}
const field = (tree, label) => elements(tree, element => element.props?.label === label)[0];
const forms = tree => elements(tree, element => element.type === 'form');
const require = createRequire(import.meta.url);
const React = require('react');
const handlersCode = (await build({ stdin: { contents: "export {ExchangePanel,DeliveryPackage,GroundedAssistantWorkspace,GroundedAssistantPanel} from './SadExtensionPanels';", resolveDir: fileURLToPath(new URL('../src/components/', import.meta.url)), loader: 'jsx' }, bundle: true, platform: 'node', format: 'cjs', write: false, external: ['react', 'lucide-react'], loader: { '.css': 'empty' } })).outputFiles[0].text;
function components(host) {
  const module = { exports: {} };
  new Function('require', 'module', 'exports', handlersCode)(name => name === 'react' ? { ...React, ...host.hooks } : name === 'lucide-react' ? { LoaderCircle: () => null, RefreshCw: () => null } : require(name), module, module.exports);
  return module.exports;
}
async function api(respond, roles = ['cskh']) {
  const calls = [];
  const client = createApiClient({ baseUrl: '/api/v1', fetchImpl: async (url, options) => {
    calls.push({ url, options });
    const payload = url.endsWith('/auth/login') ? { access_token: 'synthetic-session-token' } : url.endsWith('/auth/me') ? { account_id: 'staff', username: 'synthetic', full_name: 'Synthetic staff', roles, active_site_id: 'site', allowed_sites: [{ id: 'site', name: 'Synthetic site', code: 'SYN' }] } : await respond(url, options);
    return new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } });
  } });
  await client.authenticate('synthetic', 'synthetic-password-only');
  return { client, calls };
}

test('exchange forms reach control routes through the real API client', async () => {
  const contract = { inputs: { readings: { kind: 'METER', label: 'Chỉ số', schema: { properties: { external_id: { type: 'string' }, value: { type: 'number' } }, required: ['external_id', 'value'] } } } };
  const { client, calls } = await api(url => {
    if (url === '/api/v1/portal/control/integrations/contract') return contract;
    if (url === '/api/v1/portal/control/integrations/ep/received') return { items: [] };
    assert.ok(['/configure', '/sources', '/readings'].some(suffix => url === '/api/v1/portal/control/integrations/ep' + suffix), url);
    return { id: 'receipt' };
  });
  const host = hookHost(); const { ExchangePanel } = components(host);
  const props = { client, row: { id: 'ep', kind: 'METER', building_id: 'b1', version: 3 }, options: {}, command: { busy: false, run: (path, body) => client.portalCommand(path, body, { idempotencyKey: 'synthetic-exchange' }) } };
  const renderPanel = () => host.render(() => ExchangePanel(props));
  let tree = renderPanel(); host.flush(); await settle(); tree = renderPanel();
  field(tree, 'Kênh nhận').props.children.props.onChange({ target: { value: 'JSON_FILE' } });
  tree = renderPanel(); forms(tree)[0].props.onSubmit(submit); await settle();
  field(tree, 'Mã hồ sơ nguồn').props.onChange({ target: { value: 'meter-1' } });
  tree = renderPanel(); forms(tree)[1].props.onSubmit(submit); await settle();
  field(tree, 'Tiếp nhận dữ liệu').props.children.props.onChange({ target: { value: 'readings' } });
  tree = renderPanel(); elements(tree, element => element.type?.name === 'SchemaFields')[0].props.setForm({ external_id: 'read-1', value: '110' });
  tree = renderPanel(); forms(tree)[2].props.onSubmit(submit); await settle(); renderPanel(); host.flush(); await settle();
  const commands = calls.filter(call => call.options.method === 'POST' && !call.url.endsWith('/auth/login'));
  assert.deepEqual(commands.map(call => call.url), ['/configure', '/sources', '/readings'].map(suffix => '/api/v1/portal/control/integrations/ep' + suffix));
  assert.equal(JSON.parse(commands[0].options.body).adapter, 'JSON_FILE');
  assert.deepEqual(JSON.parse(commands[1].options.body).data, { source_type: 'METER', source_id: 'meter-1' });
  assert.deepEqual(JSON.parse(commands[2].options.body), { external_id: 'read-1', value: '110' });
  assert.ok(calls.some(call => call.url === '/api/v1/portal/control/integrations/contract'));
  assert.deepEqual(calls.filter(call => call.url.endsWith('/ep/received')).map(call => call.url), Array(2).fill('/api/v1/portal/control/integrations/ep/received'));
  host.unmount();
});

test('delivery open and download use the returned JSON package', async () => {
  const payload = { correlation_id: 'correlation-1', source_version: 2, sha256: 'a'.repeat(64), payload: { meter: 'meter-1' } };
  const { client, calls } = await api(url => { assert.equal(url, '/api/v1/portal/control/deliveries/d1/package'); return payload; });
  const host = hookHost(); const { DeliveryPackage } = components(host);
  const renderPanel = () => host.render(() => DeliveryPackage({ client, row: { id: 'd1' } }));
  let tree = renderPanel(); host.flush(); assert.equal(calls.filter(call => call.url.includes('/package')).length, 0);
  elements(tree, element => element.type === 'button')[0].props.onClick(); renderPanel(); host.flush(); await settle(); tree = renderPanel();
  const documentBefore = globalThis.document; const createBefore = URL.createObjectURL; let downloaded, clicked = false; const anchor = {};
  try {
    globalThis.document = { createElement: tag => { assert.equal(tag, 'a'); return Object.assign(anchor, { click() { clicked = true; } }); } };
    URL.createObjectURL = blob => { downloaded = blob; return createBefore(blob); };
    elements(tree, element => element.type === 'button' && element.props.children === 'Tải gói JSON')[0].props.onClick();
    assert.ok(clicked); assert.equal(anchor.download, 'greencity-d1.json'); assert.deepEqual(JSON.parse(await downloaded.text()), payload);
  } finally { URL.createObjectURL = createBefore; if (documentBefore === undefined) delete globalThis.document; else globalThis.document = documentBefore; host.unmount(); }
});

test('technician can open the assistant from the sidebar without resident management access', async () => {
  const account = createAuthenticatedAccount({ account_id: 'tech', username: 'synthetic', full_name: 'Kỹ thuật viên', roles: ['technician'], active_site_id: 's1', allowed_sites: [{ id: 's1', name: 'Site A' }] });
  assert.ok(canViewTab(account, 'assistant')); assert.equal(canViewTab(account, 'portal'), false);
  const html = await render(`import React from 'react';import {renderToStaticMarkup} from 'react-dom/server';import {Sidebar} from './Sidebar';export function render(){return renderToStaticMarkup(<Sidebar navItems={${JSON.stringify(getAllowedNav(account))}} account={${JSON.stringify(account)}} currentTab="assistant"/>);}`);
  assert.ok(html.includes('aria-label="Trợ lý &amp; CSKH"')); assert.ok(html.includes('aria-current="page"'));
});

test('assistant workspace selects scoped units, resets context and submits technician handoff', async () => {
  const options = { units: [{ id: 'u1', unit_number: 'A-101', building_name: 'Tòa A' }, { id: 'u2', unit_number: 'A-102', building_name: 'Tòa A' }], requests: [{ id: 'request-1', label: 'Yêu cầu được giao' }], records: [], categories: [{ id: 'cat-1', label: 'Hỗ trợ' }] };
  const { client, calls } = await api((url, request) => {
    if (url.startsWith('/api/v1/portal/assistant/options')) return options;
    if (url === '/api/v1/portal/assistant/conversations') return { items: [] };
    assert.equal(url, '/api/v1/portal/assistant/support'); assert.ok(request.headers['Idempotency-Key']);
    return { id: 'conversation-1', version: 1, messages: [] };
  }, ['technician']);
  const workspaceHost = hookHost(); const workspace = components(workspaceHost);
  const renderWorkspace = () => workspaceHost.render(() => workspace.GroundedAssistantWorkspace({ client, roles: ['technician'] }));
  let tree = renderWorkspace(); workspaceHost.flush(); await settle(); tree = renderWorkspace();
  const initial = elements(tree, element => element.type === workspace.GroundedAssistantPanel)[0]; assert.equal(initial.props.unitId, '');
  const unitField = field(tree, 'Căn hộ cần hỗ trợ'); assert.equal(unitField.props.children.props.children[1][0].props.children.join(''), 'A-101 · Tòa A');
  unitField.props.children.props.onChange({ target: { value: 'u1' } }); tree = renderWorkspace();
  const selected = elements(tree, element => element.type === workspace.GroundedAssistantPanel)[0]; assert.equal(selected.key, 'u1'); assert.notEqual(selected.key, initial.key);
  const panelHost = hookHost(); const panel = components(panelHost); const renderPanel = () => panelHost.render(() => panel.GroundedAssistantPanel(selected.props));
  let panelTree = renderPanel(); panelHost.flush(); await settle(); panelTree = renderPanel();
  const modeField = field(panelTree, 'Thao tác'); assert.deepEqual(modeField.props.children.props.children.map(option => option.props.value), ['SEARCH', 'STATUS', 'SUMMARY', 'HANDOFF']);
  modeField.props.children.props.onChange({ target: { value: 'HANDOFF' } }); panelTree = renderPanel();
  field(panelTree, 'Danh mục tiếp nhận').props.children.props.onChange({ target: { value: 'cat-1' } });
  field(panelTree, 'Nội dung cần hỗ trợ').props.onChange({ target: { value: 'Cần hỗ trợ kiểm tra thiết bị' } });
  panelTree = renderPanel(); forms(panelTree)[0].props.onSubmit(submit); await settle();
  const body = JSON.parse(calls.find(call => call.url.endsWith('/assistant/support')).options.body);
  assert.equal(body.mode, 'HANDOFF'); assert.equal(body.unit_id, 'u1'); assert.equal(body.category_id, 'cat-1'); assert.equal(body.request_id, null);
  assert.ok(calls.some(call => call.url.endsWith('/assistant/options?unit_id=u1')));
  field(tree, 'Căn hộ cần hỗ trợ').props.children.props.onChange({ target: { value: 'u2' } }); tree = renderWorkspace();
  assert.equal(elements(tree, element => element.type === workspace.GroundedAssistantPanel)[0].key, 'u2');
  panelHost.unmount(); workspaceHost.unmount();
});

test('assistant workspace hides controls on options failure and can retry', async () => {
  let failed = true;
  const { client } = await api(url => { assert.equal(url, '/api/v1/portal/assistant/options'); if (failed) throw new Error('Synthetic connection failure'); return { units: [] }; }, ['technician']);
  const host = hookHost(); const panel = components(host);
  const renderWorkspace = () => host.render(() => panel.GroundedAssistantWorkspace({ client, roles: ['technician'] }));
  let tree = renderWorkspace(); host.flush(); await settle(); tree = renderWorkspace();
  const state = elements(tree, element => element.type?.name === 'State')[0].props.state;
  assert.ok(state.error); assert.equal(elements(tree, element => element.type === panel.GroundedAssistantPanel).length, 0);
  failed = false; state.refresh(); renderWorkspace(); host.flush(); await settle(); tree = renderWorkspace();
  assert.equal(elements(tree, element => element.type?.name === 'State')[0].props.state.error, null);
  assert.equal(elements(tree, element => element.type === panel.GroundedAssistantPanel).length, 1);
  host.unmount();
});
