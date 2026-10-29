import React, { useState } from 'react';
import { Field, Records, State, usePortalCommand, usePortalData } from './PortalPanels';
import { fieldLabels } from '../data/operationalForms';

export function StructuredDetails({ value }) {
  if (Array.isArray(value)) return <ol>{value.map((item, i) => <li key={i}><StructuredDetails value={item} /></li>)}</ol>;
  if (value && typeof value === 'object') return <dl>{Object.entries(value).filter(([key]) => !['preview', 'hash', 'snapshot'].includes(key)).map(([key, item]) => <div key={key}><dt>{fieldLabels[key] || key}</dt><dd><StructuredDetails value={item} /></dd></div>)}</dl>;
  return <span>{value == null ? 'Chưa ghi nhận' : typeof value === 'boolean' ? value ? 'Có' : 'Không' : String(value)}</span>;
}

export function FeeImpact({ row }) {
  const impact = row.data?.preview?.snapshot;
  if (!impact) return null;
  return <section className="portal-detail"><h3>Tác động phiên bản phí</h3><p>Đơn giá trước: {impact.before_unit_rate_vnd ?? 'Chưa có'} · Đơn giá dự kiến: {impact.unit_rate_vnd}</p><p>{impact.note}</p><table><thead><tr><th>Căn</th><th>Trước (VND)</th><th>Dự kiến (VND)</th><th>Chênh lệch</th><th>Dữ liệu</th></tr></thead><tbody>{impact.items.map(r => <tr key={r.unit_id}><td>{r.unit_number}</td><td>{r.before_vnd ?? 'Chưa đủ'}</td><td>{r.after_vnd ?? 'Chưa đủ'}</td><td>{r.difference_vnd ?? 'Chưa đủ'}</td><td>{r.status === 'ESTIMATED' ? 'Ước tính kỳ đầy đủ' : r.status === 'MEASURED_VOLUME_REQUIRED' ? 'Cần sản lượng' : 'Thiếu diện tích'}</td></tr>)}</tbody></table></section>;
}

export function BudgetComparison({ client, row }) {
  const [open, setOpen] = useState(false); const state = usePortalData(client, `/operations/treasury/${row.id}/comparison`, {}, open);
  return <section><button type="button" className="button-secondary" onClick={() => setOpen(!open)} aria-expanded={open}>So sánh ngân sách & chứng từ</button>{open && <><State state={state} />{state.data && <><dl className="portal-grid">{[['planned_vnd', 'Dự toán'], ['committed_vnd', 'Cam kết còn lại'], ['accepted_vnd', 'Giá trị nghiệm thu'], ['actual_vnd', 'Thực chi & quyết toán tạm ứng'], ['unsettled_advance_vnd', 'Tạm ứng chưa quyết toán'], ['cash_disbursed_vnd', 'Dòng tiền đã chi'], ['variance_vnd', 'Dự toán trừ chi phí']].map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{state.data[key]} VND</dd></div>)}</dl><Records items={state.data.expenses}>{expense => <details><summary>{expense.reference} · {expense.status}</summary><StructuredDetails value={expense} /></details>}</Records><Records items={state.data.explanations}>{explanation => <p>{explanation.data.explanation} · {explanation.status}</p>}</Records></>}</>}</section>;
}

export function MyWorkPanel({ client }) {
  const state = usePortalData(client, '/operations/my-work'); const command = usePortalCommand(client, state.refresh);
  const [forms, setForms] = useState({});
  const items = [...(state.data?.items || []), ...(state.data?.handoffs || [])];
  return <section className="portal-detail"><h2>Đào tạo, tiếp nhận & bàn giao của tôi</h2><State state={state} /><State state={command} /><Records items={items}>{row => {
    const form = forms[row.id] || {}; const action = row.kind === 'TRAINING' ? 'ACK_TRAINING' : row.kind === 'ROSTER' ? 'ACK_HANDOVER' : 'ACCEPT_WORK';
    const set = key => e => setForms(v => ({ ...v, [row.id]: { ...v[row.id], [key]: e.target.value } }));
    return <><h3>{row.title}</h3><StructuredDetails value={row.data} />{row.kind === 'TRAINING' && row.my_acknowledgement ? <section><p role="status">Đã xác nhận đào tạo đúng phiên bản.</p><StructuredDetails value={row.my_acknowledgement} /></section> : <form onSubmit={e => { e.preventDefault(); command.run(`/operations/my-work/${row.id}/acknowledge`, { action, expected_version: row.version, reason: form.result, data: form }); }}><Field label="Kết quả / nội dung đã tiếp nhận" required minLength={3} maxLength={1000} value={form.result || ''} onChange={set('result')} /><Field label="Căn cứ xác nhận" required minLength={3} maxLength={1000} value={form.evidence_reference || ''} onChange={set('evidence_reference')} /><button className="resident-primary" disabled={command.busy}>Xác nhận {row.kind === 'TRAINING' ? 'đào tạo đúng phiên bản' : row.kind === 'ROSTER' ? 'nhận bàn giao' : 'nhận công việc'}</button></form>}</>;
  }}</Records></section>;
}

export function AssignmentCandidates({ client, buildingId, form, onChoose }) {
  const enabled = !!(buildingId && form.target_id && form.target_type && form.required_skill);
  const state = usePortalData(client, '/operations/eligible-workers', { building_id: buildingId, target_id: form.target_id, target_type: form.target_type, required_skill: form.required_skill, ...(form.sop_id ? { sop_id: form.sop_id } : {}) }, enabled);
  if (!enabled) return <p>Chọn công việc và năng lực yêu cầu để xem ca đủ điều kiện.</p>;
  return <section><h3>Ca và nhân sự đủ điều kiện</h3><State state={state} /><Records items={state.data?.items}>{item => <p>{item.name} · {item.eligible ? <button type="button" className="button-secondary" onClick={() => onChoose(item.roster_id)}>Chọn ca này</button> : item.reason}</p>}</Records></section>;
}

export function ContractProgress({ client, row }) {
  const [open, setOpen] = useState(false); const state = usePortalData(client, `/operations/records/${row.id}/contract-progress`, {}, open);
  return <section><button type="button" className="button-secondary" aria-expanded={open} onClick={() => setOpen(!open)}>Mốc nghiệm thu và nghĩa vụ còn lại</button>{open && <><State state={state} /><Records items={state.data?.milestones}>{m => <details><summary>{m.code} · {m.due_on} · {m.amount_vnd} VND · {m.status === 'COMPLETED' ? 'Đã nghiệm thu' : m.status === 'PENDING' ? 'Chưa có hồ sơ nghiệm thu' : 'Đang xử lý'}</summary><p>{m.obligation}</p>{m.acceptance && <StructuredDetails value={m.acceptance.data} />}</details>}</Records>{state.data?.financial && <p>Cam kết còn lại: {state.data.financial.committed_vnd} · Đề nghị AP/chi: {state.data.financial.payable_vnd} · Đã chi: {state.data.financial.paid_vnd} VND</p>}{state.data?.closing_decision && <StructuredDetails value={state.data.closing_decision} />}</>}</section>;
}

export function StockReplenishment({ client, row, options, onDone }) {
  const [open, setOpen] = useState(false); const [form, setForm] = useState({ budget_id: '', quantity: '', estimated_vnd: '', specification: '' });
  const command = usePortalCommand(client, onDone); const set = key => e => setForm(v => ({ ...v, [key]: e.target.value }));
  return <section><button type="button" className="button-secondary" aria-expanded={open} onClick={() => setOpen(!open)}>Lập đề nghị bổ sung từ tồn thấp</button>{open && <form onSubmit={async e => { e.preventDefault(); if (await command.run('/operations/records', { building_id: row.building_id, kind: 'PURCHASE', title: 'Bổ sung ' + row.name, data: { ...form, item_id: row.id, uom: row.uom, estimated_vnd: Number(form.estimated_vnd) } })) setOpen(false); }}><State state={command} /><Field label="Ngân sách"><select required value={form.budget_id} onChange={set('budget_id')}><option value="">Chọn ngân sách</option>{options?.treasury_accounts?.filter(b => b.kind === 'BUDGET' && b.building_id === row.building_id).map(b => <option key={b.id} value={b.id}>{b.label}</option>)}</select></Field><Field label={`Lượng bổ sung (${row.uom})`} type="number" step="0.0001" min="0.0001" required value={form.quantity} onChange={set('quantity')} /><Field label="Dự toán (VND)" type="number" min="1" max="999999999999" required value={form.estimated_vnd} onChange={set('estimated_vnd')} /><Field label="Yêu cầu mua" minLength={3} maxLength={4000} required value={form.specification} onChange={set('specification')} /><button className="resident-primary" disabled={command.busy}>Lưu đề nghị mua nháp</button></form>}</section>;
}
