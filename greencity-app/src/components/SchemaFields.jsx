import React from 'react';
import { Field } from './PortalPanels';
import { fieldLabels, fieldShape, referenceSources } from '../data/operationalForms';

export function resolveShape(property, root) {
  const shape = fieldShape(property);
  return shape.$ref ? root.$defs?.[shape.$ref.split('/').pop()] || shape : shape;
}

function Allocation({ value = {}, change, options, buildingId, amount }) {
  const rows = Object.entries(value); const total = rows.reduce((sum, [, v]) => sum + Number(v || 0), 0);
  const choices = [ ...(buildingId ? [{ id: `BUILDING:${buildingId}`, label: 'Tòa đang chọn' }] : []), ...[['units', 'UNIT'], ['assets', 'ASSET'], ['property_nodes', 'SPACE'], ['work_orders', 'WORK_ORDER']].flatMap(([source, kind]) => (options?.[source] || []).filter(r => r.building_id === buildingId).map(r => ({ id: `${kind}:${r.id}`, label: r.label }))) ];
  const replace = (index, key, money) => change(Object.fromEntries(rows.map((r, i) => i === index ? [key, money] : r)));
  return <fieldset><legend>Phân bổ chứng từ</legend>{rows.map(([key, money], index) => <div className="portal-grid" key={index}><Field label={`Đối tượng ${index + 1}`}><select required value={key} onChange={e => replace(index, e.target.value, money)}><option value="">Chọn đối tượng</option>{choices.filter(c => c.id === key || !value[c.id]).map(c => <option key={c.id} value={c.id}>{c.label}</option>)}</select></Field><Field label="Số tiền phân bổ (VND)" type="number" min="1" step="1" required value={money} onChange={e => replace(index, key, e.target.value)} /><button type="button" className="button-secondary" onClick={() => change(Object.fromEntries(rows.filter((_, i) => i !== index)))}>Xóa dòng {index + 1}</button></div>)}<button type="button" className="button-secondary" disabled={rows.some(([key]) => !key)} onClick={() => change({ ...value, '': '' })}>Thêm đối tượng</button><p role="status">Đã phân bổ: {total} VND · Còn lại: {Number(amount || 0) - total} VND</p></fieldset>;
}

export function SchemaFields({ schema, root = schema, form, setForm, options, buildingId, nested = false, sourceRecord }) {
  return <div className="portal-grid">{Object.entries(schema.properties || {}).filter(([key]) => nested || !['building_id', 'unit_id', 'expected_version'].includes(key)).map(([key, property]) => {
    const shape = resolveShape(property, root); const required = schema.required?.includes(key);
    const value = form[key];
    const assignment = !nested && root.properties?.target_type && root.properties?.roster_id;
    const change = next => setForm(v => ({ ...v, [key]: next,
      ...(assignment && ['target_type', 'target_id', 'required_skill', 'sop_id'].includes(key) ? { roster_id: '' } : {}),
      ...(assignment && key === 'target_type' ? { target_id: '' } : {}),
    }));
    const insurance = key === 'policy_id' && root.properties?.incident_id;
    const commercial = key === 'lease_id' && (root.properties?.expected_lease_version || root.title === 'CommercialCharge');
    const label = key === 'policy_id' ? (insurance ? 'Hợp đồng bảo hiểm' : 'Chính sách cọc') : key === 'lease_id' ? (commercial ? 'Hợp đồng mặt bằng' : 'Hợp đồng thuê cư trú') : key === 'target_id' && form.target_type ? 'Công việc nhận phân công' : fieldLabels[key] || property.title || key;
    if (key === 'allocation') return <Allocation key={key} value={value} change={change} options={options} buildingId={buildingId} amount={form.amount_vnd} />;
    const catalogType = { team: 'TEAM', position: 'POSITION', territory: 'TERRITORY' }[key];
    if (catalogType) {
      const entries = (options?.catalog_entries || []).filter(c => c.catalog === catalogType && c.building_id === buildingId).flatMap(c => c.entries.filter(e => e.active).map(e => ({ ...e, catalogId: c.id })));
      return <Field key={key} label={label}><select required={required} value={value || ''} onChange={e => { const entry = entries.find(item => item.code === e.target.value); setForm(v => ({ ...v, [key]: e.target.value, catalog_ids: [...new Set([...(v.catalog_ids || []), ...(entry ? [entry.catalogId] : [])])] })); }}><option value="">Chọn từ danh mục hiện hành</option>{entries.map(e => <option key={`${e.catalogId}:${e.code}`} value={e.code}>{e.code} · {e.name}</option>)}</select></Field>;
    }
    const source = insurance ? ['operations_records','INSURANCE_POLICY'] : commercial ? ['operations_records','COMMERCIAL_LEASE'] : key === 'target_id' && form.target_type ? [{ WORK_ORDER: 'work_orders', CLEANING: 'cleaning_tasks', SECURITY: 'security_shifts' }[form.target_type]] : key === 'procurement_id' ? ['operations_records'] : referenceSources[key]; const choices = source ? options?.[source[0]]?.filter(r => (!source[1] || r.kind === source[1]) && (key !== 'procurement_id' || ['PURCHASE','PROJECT'].includes(r.kind)) && (!r.building_id || !buildingId || r.building_id === buildingId)) || [] : null;
    const eligibleChoices = key === 'quotation_id' && sourceRecord?.kind === 'PURCHASE' ? choices?.filter(r => r.status === 'APPROVED' && r.related_id === sourceRecord.id) : choices;
    if (eligibleChoices) return <Field key={key} label={label}><select multiple={shape.type === 'array'} value={value || (shape.type === 'array' ? [] : '')} onChange={e => change(shape.type === 'array' ? Array.from(e.target.selectedOptions, o => o.value) : e.target.value)} required={required}>{shape.type !== 'array' && <option value="">Chọn {label.toLowerCase()}</option>}{eligibleChoices.map(r => <option key={r.id} value={r.id}>{r.label}</option>)}</select></Field>;
    if (shape.type === 'object') return <fieldset key={key}><legend>{label}</legend><SchemaFields schema={shape} root={root} nested form={value || {}} setForm={update => change(update(value || {}))} options={options} buildingId={buildingId} /></fieldset>;
    if (shape.type === 'array' && resolveShape(shape.items || {}, root).type === 'object') {
      const items = Array.isArray(value) ? value : []; const itemSchema = resolveShape(shape.items, root);
      return <fieldset key={key}><legend>{label}</legend>{items.map((item, index) => <div className="portal-detail" key={index}><SchemaFields schema={itemSchema} root={root} nested form={item} setForm={update => change(items.map((v, i) => i === index ? update(v) : v))} options={options} buildingId={buildingId} /><button type="button" className="button-secondary" onClick={() => change(items.filter((_, i) => i !== index))}>Xóa dòng {index + 1}</button></div>)}<button type="button" className="button-secondary" disabled={items.length >= (shape.maxItems || 200)} onClick={() => change([...items, {}])}>Thêm {label.toLowerCase()}</button></fieldset>;
    }
    if (shape.enum) return <Field key={key} label={label}><select value={value ?? ''} onChange={e => change(e.target.value)} required={required}><option value="">Chọn</option>{shape.enum.map(v => <option key={v} value={v}>{v}</option>)}</select></Field>;
    if (shape.type === 'boolean') return <label key={key}><input type="checkbox" checked={value ?? shape.default ?? false} onChange={e => change(e.target.checked)} /> {label}</label>;
    if (shape.type === 'array' || (shape.maxLength || 0) > 500) return <Field key={key} label={label}><textarea rows={3} value={Array.isArray(value) ? value.join('\n') : value || ''} required={required} onChange={e => change(e.target.value)} maxLength={shape.maxLength || 10000} /></Field>;
    const type = shape.format === 'date' ? 'date' : shape.format === 'date-time' ? 'datetime-local' : ['integer', 'number'].includes(shape.type) ? 'number' : 'text';
    return <Field key={key} label={label} type={type} value={value ?? shape.default ?? ''} required={required} min={shape.minimum} max={shape.maximum} step={shape.type === 'number' ? '0.0001' : type === 'number' ? '1' : undefined} minLength={shape.minLength} maxLength={shape.maxLength} onChange={e => change(e.target.value)} />;
  })}</div>;
}
