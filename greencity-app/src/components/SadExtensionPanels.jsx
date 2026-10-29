import React, { useRef, useState } from 'react';
import { Field, Page, Records, State, Badge, money, usePortalCommand, usePortalData } from './PortalPanels';
import { StructuredDetails } from './SadWorkDetails';
import { SchemaFields } from './SchemaFields';
import { serializeFields } from '../data/operationalForms';

export function ExtensionProgress({ client, row }) {
  const [open, setOpen] = useState(false);
  const state = usePortalData(client, `/operations/records/${row.id}/progress`, {}, open);
  return <section><button type="button" className="button-secondary" onClick={() => setOpen(!open)} aria-expanded={open}>Tiến độ, nghĩa vụ & nguồn kết quả</button>{open && <><State state={state} />{state.data?.debt_vnd != null && <p>Công nợ: {money(state.data.debt_vnd)} · Cọc đang giữ: {money(state.data.deposit_held_vnd)}</p>}{state.data?.remaining_commitment_vnd != null && <p>Cam kết chưa phân bổ: {money(state.data.remaining_commitment_vnd)}</p>}<StructuredDetails value={state.data} /></>}</section>;
}

export function ClaimOutcome({ row, command, path }) {
  const [form, setForm] = useState({ decision: row.status === 'ACCEPTED' ? 'PAID' : 'ACCEPTED', amount_vnd: '', provider_reference: '', evidence_reference: '', decided_on: '' });
  return <form className="portal-action-form" onSubmit={e => { e.preventDefault(); command.run(`${path}/${row.id}/actions`, { action: 'CLAIM_OUTCOME', expected_version: row.version, reason: form.evidence_reference, data: { ...form, amount_vnd: Number(form.amount_vnd) } }); }}><Field label="Kết quả của bên bảo hiểm"><select value={form.decision} onChange={e => setForm(v => ({ ...v, decision: e.target.value }))}>{(row.status === 'ACCEPTED' ? [['PAID', 'Đã chi trả']] : [['ACCEPTED', 'Chấp nhận'], ['REJECTED', 'Từ chối']]).map(([k,l]) => <option key={k} value={k}>{l}</option>)}</select></Field>{[['provider_reference', 'Mã quyết định / chứng từ chi trả', 'text'], ['amount_vnd', 'Số tiền theo quyết định (VND)', 'number'], ['evidence_reference', 'Căn cứ đối chiếu', 'text'], ['decided_on', 'Ngày kết quả', 'date']].map(([key,label,type]) => <Field key={key} label={label} type={type} required min={type === 'number' ? 0 : undefined} value={form[key]} onChange={e => setForm(v => ({ ...v, [key]:e.target.value }))} />)}<button className="button-secondary" disabled={command.busy}>Ghi kết quả bảo hiểm</button></form>;
}

export function ExchangePanel({ client, row, command, options }) {
  const [adapter, setAdapter] = useState(row.adapter === 'JSON_FILE' ? 'JSON_FILE' : 'JSON_REGISTRY');
  const [status, setStatus] = useState(row.status === 'ACTIVE' ? 'ACTIVE' : 'DISABLED'); const [type, setType] = useState('CREDENTIAL'); const [identifier, setIdentifier] = useState('');
  const contract = usePortalData(client, '/control/integrations/contract');
  const received = usePortalData(client, `/control/integrations/${row.id}/received`);
  const [feed, setFeed] = useState(''); const [form, setForm] = useState({}); const [inputError, setInputError] = useState(null);
  const schema = contract.data?.inputs?.[feed]?.schema;
  const sources = { ACCESS: ['CREDENTIAL'], PARKING: ['CREDENTIAL'], METER: ['METER'], ACCOUNTING: ['INVOICE','PAYMENT','EXPENSE'], BANK: ['PAYMENT'] }[row.kind] || [];
  const selectedType = sources.includes(type) ? type : sources[0];
  return <details><summary>Thiết lập & trao đổi dữ liệu</summary><State state={contract} /><State state={{ error: inputError }} />
    <fieldset disabled={command.busy} style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
      <form className="portal-action-form" onSubmit={e => { e.preventDefault(); command.run(`/control/integrations/${row.id}/configure`, { expected_version:row.version, adapter, status, reason:'Thiết lập kênh trao đổi GreenCity JSON' }); }}>
        <Field label="Kênh nhận"><select value={adapter} onChange={e => setAdapter(e.target.value)}><option value="JSON_REGISTRY">Sổ nhận GreenCity</option><option value="JSON_FILE">Gói JSON và xác nhận đối chiếu</option></select></Field>
        <Field label="Trạng thái"><select value={status} onChange={e => setStatus(e.target.value)}><option value="ACTIVE">Hoạt động</option><option value="DISABLED">Tạm dừng</option></select></Field><button className="button-secondary" disabled={command.busy}>Lưu cấu hình</button>
      </form>
      <form className="portal-action-form" onSubmit={e => { e.preventDefault(); command.run(`/control/integrations/${row.id}/sources`, { action:'QUEUE', expected_version:row.version, reason:'Lập gói dữ liệu nguồn', data:{ source_type:selectedType, source_id:identifier } }); }}>
        <Field label="Nguồn trao đổi"><select value={selectedType} onChange={e => {setType(e.target.value); setIdentifier('');}}>{sources.map(k => <option key={k} value={k}>{({CREDENTIAL:'Thẻ',METER:'Đồng hồ',INVOICE:'Hóa đơn',PAYMENT:'Thu tiền',EXPENSE:'Chứng từ chi'})[k]}</option>)}</select></Field><Field label="Mã hồ sơ nguồn" value={identifier} onChange={e => setIdentifier(e.target.value)} required /><button className="button-secondary" disabled={command.busy}>Lập gói trao đổi</button>
      </form>
      <Field label="Tiếp nhận dữ liệu"><select value={feed} onChange={e => {setFeed(e.target.value);setForm({});setInputError(null);}}><option value="">Chọn loại dữ liệu</option>{Object.entries(contract.data?.inputs || {}).filter(([,d]) => d.kind === row.kind).map(([k,d]) => <option key={k} value={k}>{d.label}</option>)}</select></Field>
      {schema && <form className="portal-action-form" onSubmit={async e => {
        e.preventDefault(); if (command.busy) return; setInputError(null);
        try { const result = await command.run(`/control/integrations/${row.id}/${feed}`, serializeFields(schema, form)); if (result) { setForm({}); received.refresh(); } }
        catch (error) { setInputError(error); }
      }}><SchemaFields schema={schema} form={form} setForm={update => { setInputError(null); setForm(update); }} options={options} buildingId={row.building_id} /><button className="button-secondary" disabled={command.busy}>Nhận và kiểm tra bản tin</button></form>}
    </fieldset><State state={received} /><StructuredDetails value={received.data} />
  </details>;
}

export function DeliveryPackage({ client, row }) {
  const [open, setOpen] = useState(false); const state = usePortalData(client, `/control/deliveries/${row.id}/package`, {}, open);
  return <section><button type="button" className="button-secondary" onClick={() => setOpen(!open)} aria-expanded={open}>Mở gói dữ liệu & mã đối chiếu</button>{open && <><State state={state} />{state.data && <><StructuredDetails value={state.data} /><button className="button-secondary" type="button" onClick={() => { const url=URL.createObjectURL(new Blob([JSON.stringify(state.data,null,2)],{type:'application/json'})); const a=document.createElement('a');a.href=url;a.download=`greencity-${row.id}.json`;a.click();setTimeout(() => URL.revokeObjectURL(url),1000); }}>Tải gói JSON</button></>}</>}</section>;
}

function CitationSource({ client, citation, unitId }) {
  const [open, setOpen] = useState(false);
  const state = usePortalData(client, `/assistant/sources/${citation.source.replaceAll('_','-')}/${citation.id}`, {unit_id:unitId}, open);
  return <li>{citation.title} · Phiên bản {citation.version} <button type="button" className="button-secondary" aria-expanded={open} onClick={() => setOpen(!open)}>Xem nguồn</button>{open && <><State state={state} />{state.data && <><p>{state.data.version !== citation.version ? 'Nguồn đã thay phiên bản sau phản hồi này.' : 'Nguồn khớp phiên bản phản hồi.'}</p><StructuredDetails value={state.data} /></>}</>}</li>;
}

export function GroundedAssistantWorkspace({ client, roles = [] }) {
  const options = usePortalData(client, '/assistant/options');
  const [selected, setSelected] = useState('');
  const units = options.data?.units || [];
  const unitId = units.some(unit => unit.id === selected) ? selected : '';
  return <section className="portal-page" aria-label="Trợ lý & CSKH">
    <State state={options} />
    {options.data && <><div className="surface portal-form"><Field label="Căn hộ cần hỗ trợ"><select value={unitId} onChange={event => setSelected(event.target.value)}><option value="">Tra cứu trong phạm vi được giao</option>{units.map(unit => <option key={unit.id} value={unit.id}>{unit.unit_number} · {unit.building_name}</option>)}</select></Field></div>
      <GroundedAssistantPanel key={unitId || 'all'} client={client} unitId={unitId} roles={roles} />
    </>}
  </section>;
}

export function GroundedAssistantPanel({ client, unitId, roles = [] }) {
  const history = usePortalData(client, '/assistant/conversations'); const options = usePortalData(client, '/assistant/options', {unit_id:unitId});
  const [selected, setSelected] = useState(''); const [mode, setMode] = useState('SEARCH'); const [query, setQuery] = useState(''); const [requestId,setRequestId] = useState(''); const [categoryId,setCategoryId] = useState('');
  const [statusReference,setStatusReference] = useState('');
  const [statusSource,statusId] = statusReference.split(':');
  const statusChoices = [...(options.data?.requests || []).map(r => ({...r,source:'service_requests'})),...(options.data?.records || [])];
  const statusField = <Field label="Hồ sơ cần tra cứu"><select required value={statusReference} onChange={e => setStatusReference(e.target.value)}><option value="">Chọn hồ sơ hoặc yêu cầu</option>{statusChoices.map(r => <option key={`${r.source}:${r.id}`} value={`${r.source}:${r.id}`}>{r.label}</option>)}</select></Field>;
  const contextRevision = useRef(0); const submittedRevision = useRef(null);
  const [result,setResult] = useState(null); const command = usePortalCommand(client, row => { if (submittedRevision.current === contextRevision.current) { setResult(row); setSelected(row.id); } history.refresh(); });
  const row = result?.id === selected ? result : history.data?.items?.find(r => r.id === selected);
  return <Page title="Trợ lý & hỗ trợ trực tiếp" description="Tra cứu nguồn được công bố, xem hồ sơ và chuyển nội dung tới CSKH." onRefresh={history.refresh}>
    <State state={history} /><State state={options} /><State state={command} />
    <Field label="Cuộc trao đổi"><select value={selected} onChange={e => { contextRevision.current += 1; setSelected(e.target.value); setResult(null); }}><option value="">Mở cuộc mới</option>{history.data?.items?.map(r => <option key={r.id} value={r.id}>{r.title}</option>)}</select></Field>
    <form className="portal-form" onSubmit={e => {
      e.preventDefault();
      if (command.busy) return;
      submittedRevision.current = contextRevision.current;
      const record = mode === 'STATUS' && statusSource && statusSource !== 'service_requests';
      command.run('/assistant/support',{mode,query,unit_id:unitId || null,
        request_id:mode === 'STATUS' ? (statusSource === 'service_requests' ? statusId : null) : ['SUMMARY','DRAFT'].includes(mode) ? requestId || null : null,
        record_source:record ? statusSource : null,record_id:record ? statusId : null,
        category_id:categoryId || null,conversation_id:row?.id || null,expected_version:row?.version || null});
    }}>
      <Field label="Nội dung cần hỗ trợ" required minLength={3} maxLength={2000} value={query} onChange={e => setQuery(e.target.value)} />
      <Field label="Thao tác"><select value={mode} onChange={e => setMode(e.target.value)}>{[['SEARCH','Tra cứu sổ tay / quy định'],['STATUS','Xem trạng thái yêu cầu / hồ sơ'],['SUMMARY','Tóm tắt diễn biến'],...(roles.some(r => ['admin','director','cskh'].includes(r)) ? [['DRAFT','Soạn bản nháp phản hồi']] : []),['HANDOFF','Chuyển đến CSKH']].map(([k,l]) => <option key={k} value={k}>{l}</option>)}</select></Field>
      {mode === 'STATUS' && statusField}
      {['SUMMARY','DRAFT'].includes(mode) && <Field label="Yêu cầu nguồn"><select value={requestId} onChange={e => setRequestId(e.target.value)} required={mode !== 'DRAFT'}><option value="">Chọn yêu cầu</option>{options.data?.requests?.map(r => <option key={r.id} value={r.id}>{r.label}</option>)}</select></Field>}
      {mode === 'HANDOFF' && <Field label="Danh mục tiếp nhận"><select value={categoryId} onChange={e => setCategoryId(e.target.value)} required><option value="">Chọn danh mục</option>{options.data?.categories?.map(r => <option key={r.id} value={r.id}>{r.label}</option>)}</select></Field>}
      <button className="resident-primary" disabled={command.busy || mode === 'HANDOFF' && !unitId}>{mode === 'HANDOFF' ? 'Chuyển đến CSKH' : 'Tra cứu và lưu trao đổi'}</button>
      {mode === 'HANDOFF' && !unitId && <p>Chọn căn hộ để chuyển yêu cầu đến CSKH.</p>}
    </form>
    <Records items={row?.messages?.map((m,i) => ({...m,id:`${row.id}:${i}`}))}>{m => <><h2>{m.query}</h2><p style={{whiteSpace:'pre-wrap'}}>{m.reply}</p><ul>{m.citations?.map(c => <CitationSource key={`${c.source}:${c.id}`} client={client} citation={c} unitId={unitId} />)}</ul>{m.needs_handoff && <button type="button" className="button-secondary" onClick={() => setMode('HANDOFF')}>Chuyển tới người phụ trách</button>}</>}</Records>
  </Page>;
}
