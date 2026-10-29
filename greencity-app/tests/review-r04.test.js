import test from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const React = require('react');
const code = (await build({ stdin: { contents: "export {FinancialControlPanel} from './FinancialControlPanel'; export {GroundedAssistantPanel} from './SadExtensionPanels'; export {DocumentsPanel} from './PortalExtraPanels'; export {InitDatasetPanel} from './SadCompletionPanels'; export {ParameterAction} from './OperationalWorkspacePanel'; export {ImportRunsView} from './ImportRunsView'; export {NotificationsDesktopView} from './NotificationsDesktopView';", resolveDir: fileURLToPath(new URL('../src/components/', import.meta.url)), loader: 'jsx' }, bundle: true, platform: 'node', format: 'cjs', write: false, external: ['react', 'lucide-react'], loader: { '.css': 'empty' } })).outputFiles[0].text;

function harness() {
  const scopes = new Map(), effects = []; let slots, index;
  const hooks = {
    useState(initial) { const i = index++, current = slots; if (!(i in current)) current[i] = typeof initial === 'function' ? initial() : initial; return [current[i], value => { current[i] = typeof value === 'function' ? value(current[i]) : value; }]; },
    useRef(initial) { const i = index++; return slots[i] ||= { current: initial }; },
    useMemo(fn, deps) { const i = index++; if (!slots[i] || deps.some((v,n) => v !== slots[i].deps[n])) slots[i] = { deps, value: fn() }; return slots[i].value; },
    useCallback(fn, deps) { return hooks.useMemo(() => fn, deps); },
    useId() { return hooks.useRef(`id-${index}`).current; },
    useEffect(fn, deps) { const i = index++, current = slots, previous = current[i]; if (!previous || deps.some((v,n) => v !== previous.deps[n])) effects.push(() => { previous?.cleanup?.(); current[i] = { deps, cleanup: fn() }; }); },
  };
  const module = { exports: {} };
  new Function('require','module','exports',code)(name => name === 'react' ? { ...React, ...hooks } : name === 'lucide-react' ? new Proxy({}, { get: () => () => null }) : require(name), module, module.exports);
  return { ...module.exports, render(fn, scope = 'main') { if (!scopes.has(scope)) scopes.set(scope, []); slots = scopes.get(scope); index = 0; return fn(); }, flush() { effects.splice(0).forEach(fn => fn()); }, unmount() { scopes.forEach(current => current.forEach(slot => { if (typeof slot?.cleanup === 'function') { slot.cleanup(); slot.cleanup = null; } })); } };
}
function nodes(tree, predicate) { if (!tree || typeof tree !== 'object') return []; if (Array.isArray(tree)) return tree.flatMap(c => nodes(c,predicate)); return [...(predicate(tree) ? [tree] : []), ...nodes(tree.props?.children,predicate)]; }
function text(tree) { if (typeof tree === 'string' || typeof tree === 'number') return String(tree); if (Array.isArray(tree)) return tree.map(text).join(''); return tree?.props ? text(tree.props.children) : ''; }
const button = (tree, label) => nodes(tree, n => n.type === 'button' && text(n) === label)[0];
const field = (tree, label) => nodes(tree, n => n.type?.name === 'Field' && n.props.label === label)[0];
const control = (tree, label) => field(tree,label).props.children || field(tree,label);
const change = (tree,label,value) => control(tree,label).props.onChange({ target: { value } });
const submit = tree => nodes(tree,n => n.type === 'form')[0].props.onSubmit({ preventDefault() {} });
const tick = () => new Promise(resolve => setImmediate(resolve));
async function settle(h,render,ready) { for (let i=0;i<15;i++) { const tree=render(); h.flush(); await tick(); if (ready(tree)) return tree; } assert.fail('Component did not settle'); }
const deferred = () => { let resolve,reject; const promise = new Promise((a,b) => {resolve=a;reject=b;}); return {promise,resolve,reject}; };
const financeOptions = () => ({ periods: [{id:'p1',building_id:'b1',status:'OPEN'}], payments: [{id:'pay1',building_id:'b1',billing_account_id:'ba1',status:'RECEIVED'}], invoices: [{id:'i1',building_id:'b1',billing_account_id:'ba1',invoice_number:'INV-01',status:'ISSUED',outstanding_vnd:100}], credits: [], deposits: [], accounts: [] });
async function finance(t, client, initial = financeOptions()) {
  const h=harness(); t.after(() => h.unmount()); let options=initial;
  const parentClient={...client,portalGet:async path => path === '/finance/options' ? options : {items:[],units:[]}};
  const renderParent=() => h.render(() => h.FinancialControlPanel({client:parentClient,account:{roles:['accountant']}}));
  let tree=await settle(h,renderParent,tree => !nodes(tree,n => n.type?.name==='State')[0].props.state.loading);
  button(tree,'Hồ sơ tài chính').props.onClick(); tree=renderParent(); h.flush();
  const element=nodes(tree,n => n.type?.name==='FinanceProposal')[0];
  const render=() => h.render(() => element.type({...element.props,options}), 'proposal');
  tree=render();h.flush();await tick();
  for (const [label,value] of [['Kỳ kế toán','p1'],['Đối tượng nguồn','pay1'],['Lý do','Phân bổ thu tiền'],['Căn cứ / mã tài liệu','CT-01']]) { change(tree,label,value);tree=render();h.flush(); }
  change(tree,'INV-01 · Nợ 100 ₫','50'); tree=render();h.flush();
  return {h,render,get tree(){return render();},setOptions(value){options=value;render();h.flush();}};
}

test('FE-21 preview uses the API client command contract and saves the exact reviewed hash',async t => {
  const calls=[];
  const f=await finance(t,{portalCommand:async (path,body,options) => { assert.ok(options?.idempotencyKey,'portalCommand requires Idempotency-Key'); calls.push({path,body,options}); return path.endsWith('/preview') ? {amount_vnd:50,calculation_hash:'reviewed-hash',allocations:body.data.allocations} : {id:'cmd1'}; }});
  await submit(f.tree); let tree=f.tree;
  assert.ok(button(tree,'Lưu đề nghị từ bản xem trước'),'Valid preview must be visible');
  await button(tree,'Lưu đề nghị từ bản xem trước').props.onClick();
  assert.equal(calls.length,2);assert.equal(calls[1].body.expected_hash,'reviewed-hash');assert.deepEqual(calls[1].body.data.allocations,[{invoice_id:'i1',amount_vnd:50}]);
});

test('FE-21 obsolete preview success/error is ignored after edit and unmount',async t => {
  for (const fail of [false,true]) await t.test(fail?'late error':'late success',async t => {
    const pending=deferred();let requestOptions;
    const f=await finance(t,{portalCommand:(_path,_body,options) => {requestOptions=options;return pending.promise;}});
    const submitted=submit(f.tree);change(f.tree,'Lý do','Nội dung mới');f.h.flush();
    if(fail) pending.reject(new Error('Lỗi bản xem trước cũ'));else pending.resolve({amount_vnd:50,calculation_hash:'old'});
    await submitted; const tree=f.tree;
    assert.equal(button(tree,'Lưu đề nghị từ bản xem trước'),undefined);
    assert.equal(nodes(tree,n => n.type?.name==='State' && n.props.state.error).length,0);
    assert.ok(requestOptions.signal.aborted);
    const next=submit(tree);f.h.unmount();assert.ok(requestOptions.signal.aborted);await next;
  });
});

test('FE-21 source refresh invalidates preview; changing period clears target and allocations',async t => {
  const f=await finance(t,{portalCommand:async () => ({amount_vnd:50,calculation_hash:'hash'})});
  await submit(f.tree);assert.ok(button(f.tree,'Lưu đề nghị từ bản xem trước'));
  f.setOptions({...financeOptions(),payments:[]});assert.equal(button(f.tree,'Lưu đề nghị từ bản xem trước'),undefined);
  f.setOptions(financeOptions());change(f.tree,'Kỳ kế toán','');const tree=f.tree;f.h.flush();
  assert.equal(control(tree,'Đối tượng nguồn').props.value,'');
});

test('FE-24 invalid document files never reach upload; valid retry keeps idempotency',async t => {
  const h=harness();t.after(() => h.unmount());const uploads=[];
  const client={portalGet:async () => ({items:[]}),uploadPortalDocument:async (file,body,options) => {uploads.push({file,body,options});throw new Error('Đứt kết nối');}};
  const render=() => h.render(() => h.DocumentsPanel({client,unitId:'u1'}));let tree=render();h.flush();await tick();tree=render();
  change(tree,'Tên tài liệu','Tài liệu kiểm tra');tree=render();
  const choose=file => {control(render(),'Tệp PDF / PNG / JPEG (tối đa 10 MB)').props.onChange({target:{files:[file],value:'selected'}});h.flush();};
  for(const file of [{name:'bad.exe',type:'application/x-msdownload',size:1},{name:'huge.pdf',type:'application/pdf',size:10*1024*1024+1},{name:'empty.pdf',type:'application/pdf',size:0}]) {choose(file);await submit(render());assert.equal(uploads.length,0);}
  choose({name:'valid.pdf',type:'application/pdf',size:20,lastModified:1});await submit(render());await submit(render());
  assert.equal(uploads.length,2);assert.equal(uploads[0].options.idempotencyKey,uploads[1].options.idempotencyKey);
});

test('FE-26 late support reply does not select the previous conversation after opening another',async t => {
  const h=harness();t.after(() => h.unmount());const pending=deferred();const existing={id:'existing',title:'Cuộc trước',version:1,messages:[]};
  const client={portalGet:async path => path.includes('conversations')?{items:[existing]}:{requests:[],records:[],categories:[]},portalCommand:() => pending.promise};
  const render=() => h.render(() => h.GroundedAssistantPanel({client,unitId:'u1',roles:['resident']}));
  let tree=await settle(h,render,tree => !nodes(tree,n => n.type?.name==='State')[0].props.state.loading);
  change(tree,'Nội dung cần hỗ trợ','Tra cứu tài liệu');tree=render();submit(tree);tree=render();
  change(tree,'Cuộc trao đổi','existing');tree=render();
  pending.resolve({id:'old-result',version:1,messages:[{query:'Tra cứu tài liệu',reply:'Kết quả cũ',citations:[]}]});await tick();tree=await settle(h,render,tree => Array.isArray(nodes(tree,n => n.type?.name==='Records')[0].props.items));
  assert.equal(control(tree,'Cuộc trao đổi').props.value,'existing');
  assert.equal(nodes(tree,n => n.type?.name==='Records')[0].props.items.length,0);
});

test('FE-27 duplicate expectation names are rejected before creating dataset',async t => {
  const h=harness();t.after(() => h.unmount());const commands=[];
  const client={portalGet:async () => ({items:[],csv_batches:[{id:'csv1',label:'Batch 1'}],loader_batches:[]}),portalCommand:async (...args) => {commands.push(args);return {id:'dataset'};}};
  const render=() => h.render(() => h.InitDatasetPanel({client,buildingId:'b1'}));let tree=render();h.flush();await tick();tree=render();
  change(tree,'Tên bộ dữ liệu','Bộ kiểm tra');control(tree,'Batch CSV').props.onChange({target:{selectedOptions:[{value:'csv1'}]}});tree=render();
  const selectors=nodes(tree,n => n.type?.name==='Field' && n.props.label==='Chỉ tiêu');selectors[1].props.children.props.onChange({target:{value:'csv_rows'}});tree=render();
  const values=nodes(tree,n => n.type?.name==='Field' && n.props.label==='Giá trị kỳ vọng');for(const value of values)value.props.onChange({target:{value:'1'}});
  await submit(render());assert.equal(commands.length,0,'Duplicate keys must not silently overwrite expectations');
});

test('FE-30 quote selection shows only approved quotations belonging to the purchase',() => {
  const h=harness();const options={operations_records:[{id:'q1',kind:'QUOTATION',status:'APPROVED',related_id:'purchase1',building_id:'b1',label:'Báo giá đúng'},{id:'q2',kind:'QUOTATION',status:'APPROVED',related_id:'purchase2',building_id:'b1',label:'Đơn khác'},{id:'q3',kind:'QUOTATION',status:'DRAFT',related_id:'purchase1',building_id:'b1',label:'Chưa duyệt'}]};
  const render=() => h.render(() => h.ParameterAction({row:{id:'purchase1',version:1,kind:'PURCHASE'},verb:'SELECT_QUOTE',label:'Chọn báo giá',path:'/operations/records/purchase1/actions',command:{busy:false},fields:[['quotation_id','string']],options,buildingId:'b1'}));
  let tree=render();button(tree,'Chọn báo giá').props.onClick();tree=render();
  const element=nodes(tree,n => n.type?.name==='SchemaFields')[0];const fields=element.type(element.props);
  assert.deepEqual(nodes(fields,n => n.type==='option' && n.props.value).map(n => n.props.value),['q1']);h.unmount();
});

test('FE-27 selecting CSV B ignores the late header read for CSV A',async t => {
  const h=harness();t.after(() => h.unmount());const a=deferred();const b=deferred();
  const render=() => h.render(() => h.ImportRunsView({account:{},client:{}}));let tree=render();
  const input=tree => nodes(tree,n => n.type==='input' && n.props.type==='file')[0];
  const first=input(tree).props.onChange({target:{files:[{name:'a.csv',slice:()=>({text:()=>a.promise})}]}});tree=render();
  const second=input(tree).props.onChange({target:{files:[{name:'b.csv',slice:()=>({text:()=>b.promise})}]}});
  b.resolve('unit_number,floor,area_m2,status');await second;a.resolve('old_a,old_b');await first;tree=render();
  assert.ok(text(tree).includes('unit_number'));assert.ok(!text(tree).includes('old_a'));
});

test('FE-25 notification refresh ignores the late inbox result from an older cutoff',async t => {
  const previous=globalThis.window;globalThis.window={addEventListener(){},removeEventListener(){}};
  t.after(() => {if(previous===undefined)delete globalThis.window;else globalThis.window=previous;});
  const h=harness();t.after(() => h.unmount());const pending=[];const counts=[];let asOf='2026-10-01T00:00:00Z';
  const client={listNotifications:options => {const d=deferred();pending.push({...d,options});return d.promise;}};
  const render=() => h.render(() => h.NotificationsDesktopView({client,account:{canManageOutbox:false},asOf,onUnreadChange:n=>counts.push(n)}));
  render();h.flush();asOf='2026-10-11T00:00:00Z';render();h.flush();
  pending[1].resolve({items:[{id:'new',title:'Thông báo mới',body:'Nội dung mới',read_at:null,created_at:'2026-10-11T00:00:00Z',delivery_status:'QUEUED'}]});await tick();
  pending[0].resolve({items:[]});await tick();const tree=render();
  assert.ok(text(tree).includes('Thông báo mới'));assert.equal(counts.at(-1),1);
  button(tree,'Làm mới').props.onClick();render();h.unmount();assert.ok(pending[2].options.signal.aborted);
  pending[2].resolve({items:[]});await tick();assert.equal(counts.at(-1),1);
});

test('FE-25 staff mandatory notification offers ACK even when already read',async t => {
  const h=harness();const previous=globalThis.window;globalThis.window={addEventListener(){},removeEventListener(){}};
  t.after(() => {h.unmount();if(previous===undefined)delete globalThis.window;else globalThis.window=previous;});
  let row={id:'notice1',read_at:'2026-10-11',acknowledged_at:null,template_snapshot:{title:'Bắt buộc',body:'Nội dung máy chủ gửi trong body',requires_ack:true}};const calls=[];
  const client={listNotifications:async () => ({items:[{...row}]}),portalCommand:async(path,_body,options) => {calls.push({path,options});row={...row,acknowledged_at:'2026-10-11'};return row;}};
  const render=() => h.render(() => h.NotificationsDesktopView({client,account:{canManageOutbox:false}}));
  let tree=await settle(h,render,tree => nodes(tree,n => n.type?.name==='NotificationAcknowledgement').length>0);
  assert.ok(text(tree).includes('Nội dung máy chủ gửi trong body'));
  const acknowledgement=nodes(tree,n => n.type?.name==='NotificationAcknowledgement')[0];
  const child=() => h.render(() => acknowledgement.type(acknowledgement.props),'ack');
  tree=child();h.flush();assert.ok(button(tree,'Xác nhận tiếp nhận'));await button(tree,'Xác nhận tiếp nhận').props.onClick();
  assert.equal(calls[0].path,'/control/notifications/notice1/ack');assert.ok(calls[0].options.idempotencyKey);
  tree=await settle(h,render,tree => nodes(tree,n => n.type?.name==='NotificationAcknowledgement')[0]?.props.row.acknowledged_at);
  const updated=nodes(tree,n => n.type?.name==='NotificationAcknowledgement')[0];tree=h.render(() => updated.type(updated.props),'ack');
  assert.equal(button(tree,'Xác nhận tiếp nhận'),undefined);assert.ok(text(tree).includes('Đã xác nhận tiếp nhận.'));
});

test('FE-27 unchanged import retry reuses key; changed building starts a different intent',async t => {
  const h=harness();t.after(() => h.unmount());const attempts=[];
  const client={uploadUnitCsvImport:async(_file,options) => {attempts.push(options);throw new Error('Mất kết nối');}};
  const render=() => h.render(() => h.ImportRunsView({account:{},client}));let tree=render();h.flush();
  const input=tree => nodes(tree,n => n.type==='input' && n.props.type==='file')[0];
  await input(tree).props.onChange({target:{files:[{name:'units.csv',size:20,lastModified:1,slice:()=>({text:async()=> 'unit_number,floor,area_m2,status'})}]}});
  tree=render();nodes(tree,n => n.props?.id==='import-building-code')[0].props.onChange({target:{value:'A'}});tree=render();
  await button(tree,'Tải CSV lên').props.onClick();await button(render(),'Tải CSV lên').props.onClick();
  assert.equal(attempts[0].idempotencyKey,attempts[1].idempotencyKey);
  tree=render();nodes(tree,n => n.props?.id==='import-building-code')[0].props.onChange({target:{value:'B'}});await button(render(),'Tải CSV lên').props.onClick();
  assert.notEqual(attempts[1].idempotencyKey,attempts[2].idempotencyKey);
});
