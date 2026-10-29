import React, { useEffect, useRef, useState } from 'react';
import { CalendarDays, Car, FileText, LoaderCircle, RefreshCw, ShieldCheck } from 'lucide-react';
import './portal-workspace.css';

export const PORTAL_LABELS = {
  ENTERED: 'Đang gửi xe', EXITED: 'Đã ra', RECONCILED: 'Đã đối chiếu', AVAILABLE: 'Sẵn có', DISCARDED: 'Đã loại', SENT: 'Đã gửi', NOT_CONFIGURED: 'Chưa cấu hình kết nối', SUPERSEDED: 'Đã được thay thế', SUCCEEDED: 'Chạy đạt', PART_PAID: 'Đã chi một phần', SETTLED: 'Đã hoàn ứng', HOST_CONFIRMED: 'Đã xác nhận tiếp đón', EXPLAINED: 'Đã giải trình', APPEALED: 'Đang xem xét lại', DECIDED: 'Đã quyết định', ABSENT: 'Vắng mặt', UNKNOWN: 'Cần đối chiếu kết quả gửi', QUEUED: 'Trong hàng đợi', IN_PROGRESS: 'Đang thực hiện', POSTED: 'Đã ghi sổ',
  SUBMITTED: 'Đã gửi', WAITING_INFO: 'Cần bổ sung', APPROVED: 'Đã duyệt', REJECTED: 'Từ chối',
  CANCELLED: 'Đã hủy', COMPLETED: 'Hoàn tất', REVOKED: 'Thu hồi', PENDING: 'Chờ xử lý',
  WAITING: 'Danh sách chờ', OFFERED: 'Được mời nhận suất', ACTIVE: 'Đang hoạt động', PAUSED: 'Tạm dừng',
  AWAITING_DEPOSIT: 'Chờ đủ cọc', CONFIRMED: 'Đã xác nhận', CHECKED_IN: 'Đang sử dụng', NO_SHOW: 'Không đến',
  AWAITING_FUNDS: 'Chờ nhận tiền', HELD: 'Đang giữ cọc', RELEASED: 'Đã giải tỏa', CLOSED: 'Đã kết thúc',
  LOST: 'Báo mất', LOCKED: 'Đã khóa', EXPIRED: 'Hết hạn', ENDED: 'Đã chấm dứt',
  DRAFT: 'Bản nháp', PUBLISHED: 'Đã công bố', WITHDRAWN: 'Ngừng công bố',
  PAID: 'Đã thanh toán', PARTIALLY_PAID: 'Thanh toán một phần', ISSUED: 'Đã phát hành', VOID: 'Đã hủy hóa đơn',
  FAILED: 'Không thành công', RECONCILIATION: 'Chờ đối soát',
  SENDING: 'Đã gửi, chờ kết quả', SCHEDULED: 'Đã lên lịch', VERIFIED: 'Đã xác minh', USED: 'Đã sử dụng',
};
export const DOSSIER_KINDS = {
  PROFILE_CHANGE: 'Cập nhật thông tin', MOVE_IN: 'Đăng ký cư trú', MOVE_OUT: 'Chuyển ra',
  ABSENCE: 'Tạm vắng', RETURN: 'Quay lại', LEASE: 'Đăng ký thuê', DELEGATION: 'Ủy quyền',
  TRANSFER: 'Chuyển nhượng', RENOVATION: 'Sửa chữa / cải tạo',
};
export const money = value => new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(typeof value === 'string' && /^-?\d+$/.test(value) ? BigInt(value) : value || 0);
export const when = value => value ? new Intl.DateTimeFormat('vi-VN', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value)) : '—';
const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };

export function usePortalData(client, path, params = {}, enabled = true) {
  const [state, setState] = useState({ data: null, loading: enabled, error: null });
  const [revision, setRevision] = useState(0);
  const query = JSON.stringify(params);
  const requestKey = `${path}:${query}:${enabled}:${revision}`;
  useEffect(() => {
    if (!enabled) { setState({ data: null, loading: false, error: null, requestKey, client }); return undefined; }
    const controller = new AbortController(); let current = true;
    setState({ data: null, loading: true, error: null, requestKey, client });
    client.portalGet(path, JSON.parse(query), { signal: controller.signal })
      .then(data => { if (current) setState({ data, loading: false, error: null, requestKey, client }); })
      .catch(error => { if (current && error.name !== 'AbortError') setState({ data: null, loading: false, error, requestKey, client }); });
    return () => { current = false; controller.abort(); };
  }, [client, path, query, enabled, revision]);
  const visible = state.requestKey === requestKey && state.client === client ? state : { data: null, loading: enabled, error: null };
  return { ...visible, refresh: () => setRevision(value => value + 1) };
}

export function usePortalCommand(client, onDone) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState(null); const [notice, setNotice] = useState('');
  const intents = useRef(new Map());
  const mounted = useRef(true); const running = useRef(false); const pending = useRef(null);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; pending.current?.abort(); }; }, [client]);
  const run = async (path, body, upload) => {
    if (running.current) return null;
    const material = `${path}:${JSON.stringify(body)}:${upload?.name || ''}:${upload?.size || ''}:${upload?.lastModified || ''}`;
    if (!intents.current.has(material)) intents.current.set(material, `portal-${crypto.randomUUID()}`);
    running.current = true; const controller = new AbortController(); pending.current = controller;
    setBusy(true); setError(null); setNotice('');
    try {
      const result = upload
        ? await client.uploadPortalDocument(upload, body, { idempotencyKey: intents.current.get(material), signal: controller.signal })
        : await client.portalCommand(path, body, { idempotencyKey: intents.current.get(material), signal: controller.signal });
      if (!mounted.current || controller.signal.aborted) return null;
      intents.current.delete(material); setNotice('Đã ghi nhận thao tác.'); onDone?.(result); return result;
    } catch (failure) { if (mounted.current && failure.name !== 'AbortError') setError(failure); return null; }
    finally { if (pending.current === controller) { running.current = false; if (mounted.current) setBusy(false); } }
  };
  return { run, busy, error, notice };
}

export function Field({ label, children, ...props }) {
  const control = React.isValidElement(children) && ['input', 'select', 'textarea'].includes(children.type)
    ? React.cloneElement(children, { 'aria-label': children.props['aria-label'] || label })
    : children || <input aria-label={label} {...props} />;
  return <label className="portal-field"><span>{label}</span>{control}</label>;
}
export function State({ state }) {
  return <>{state.loading && <p role="status" className="portal-loading"><LoaderCircle size={18} className="request-spinner" aria-hidden="true" />Đang tải…</p>}
    {state.error && <div role="alert" className="portal-error"><p>{state.error.message || 'Không thể hoàn tất thao tác.'}</p>{state.error.correlationId && <small>Mã hỗ trợ: {state.error.correlationId}</small>}{state.refresh && <button type="button" onClick={state.refresh}>Thử lại</button>}</div>}
    {state.notice && <p role="status" className="portal-notice">{state.notice}</p>}</>;
}
export function Page({ title, description, children, onRefresh }) {
  return <section className="resident-page portal-page"><div className="resident-page-heading"><div><p className="resident-eyebrow">GreenCity · Dịch vụ cư dân</p><h1>{title}</h1><p>{description}</p></div>{onRefresh && <button type="button" className="button-secondary" onClick={onRefresh}><RefreshCw size={16} aria-hidden="true" />Làm mới</button>}</div>{children}</section>;
}
export function Badge({ status }) { return <span className={`portal-badge status-${status?.toLowerCase()}`}>{PORTAL_LABELS[status] || status}</span>; }
export function Records({ items, children, empty = 'Chưa có dữ liệu trong phạm vi đang chọn.' }) {
  return items?.length ? <div className="portal-records">{items.map(item => <article key={item.id} className="surface portal-record">{children(item)}</article>)}</div> : <p className="surface portal-empty">{empty}</p>;
}
export function Action({ row, action, label, path, command, data = {}, children, effectiveDate = false }) {
  const [open, setOpen] = useState(false); const [reason, setReason] = useState('');
  const today = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
  const [effectiveOn, setEffectiveOn] = useState(today);
  return <div className="portal-inline-action"><button type="button" className="button-secondary" disabled={command.busy} onClick={() => setOpen(!open)} aria-expanded={open}>{label}</button>
    {open && <form className="portal-action-form" onSubmit={async event => { event.preventDefault(); const result = await command.run(path, { action, expected_version: row.version, reason, data: effectiveDate ? { ...data, effective_on: effectiveOn } : data }); if (result) { setOpen(false); setReason(''); } }}>
      <Field label={`Lý do — ${label}`} value={reason} onChange={event => setReason(event.target.value)} minLength={3} maxLength={4000} required />{children}
      {effectiveDate && <><Field label="Ngày hiệu lực" type="date" value={effectiveOn} max={today} onChange={event => setEffectiveOn(event.target.value)} required /><p>Ngày bắt đầu/tiếp tục được tính phí; ngày tạm dừng/kết thúc không tính phí. Kỳ đã lập hóa đơn cần hồ sơ điều chỉnh riêng.</p></>}
      <button type="submit" className="resident-primary" disabled={command.busy}>{command.busy ? 'Đang xử lý…' : 'Xác nhận'}</button><button type="button" onClick={() => setOpen(false)}>Đóng</button>
    </form>}
  </div>;
}

export function ResidentProfilePanel({ profile, unitId, onOpenDossiers }) {
  const selected = profile?.units?.find(unit => unit.id === unitId);
  const relationshipLabel = value => ({ owner: 'Chủ sở hữu', tenant: 'Người thuê', family_member: 'Thành viên' }[value] || value);
  return <Page title="Hồ sơ của tôi" description="Thông tin cá nhân và căn hộ đã được xác minh.">
    <div className="portal-grid"><article className="surface portal-record"><h2>{profile?.person?.full_name}</h2><dl className="portal-facts"><div><dt>Điện thoại</dt><dd>{profile?.person?.phone_masked}</dd></div><div><dt>Email</dt><dd>{profile?.person?.email_masked}</dd></div></dl><p>Thông tin do Ban quản lý quản lý được cập nhật qua hồ sơ đề nghị.</p><button type="button" className="resident-primary" onClick={onOpenDossiers} disabled={!onOpenDossiers}>Gửi đề nghị cập nhật</button></article>
      <article className="surface portal-record"><h2>{selected?.unit_number || 'Chưa có căn hộ có hiệu lực'}</h2><p>{selected?.building_name}</p>{selected && <dl className="portal-facts"><div><dt>Diện tích</dt><dd>{selected.area_m2} m²</dd></div><div><dt>Quan hệ</dt><dd>{profile?.relationships?.map(r => relationshipLabel(r.relationship_type)).join(', ') || 'Theo ủy quyền'}</dd></div><div><dt>Cư trú đã khai báo</dt><dd>{{ ABSENCE: 'Tạm vắng', RETURN: 'Đã trở lại', MOVE_OUT: 'Đã chuyển ra' }[profile?.presence?.status] || 'Chưa có khai báo tạm vắng/chuyển ra'}</dd></div><div><dt>Người chịu phí</dt><dd>{profile?.liability ? (profile.liability.is_self ? 'Tôi' : 'Theo hồ sơ đã được BQL duyệt') : 'Chưa thiết lập hồ sơ riêng'}</dd></div></dl>}{profile?.relationship_history?.length > 0 && <details><summary>Lịch sử quan hệ căn hộ</summary>{profile.relationship_history.map((r, index) => <p key={index}>{relationshipLabel(r.relationship_type)} · {r.valid_from} → {r.valid_to || 'Chưa kết thúc'}{r.ownership_ratio ? ` · ${Number(r.ownership_ratio) * 100}%` : ''}</p>)}</details>}</article></div>
  </Page>;
}

export function DossierForm({ unitId, command, isOwner }) {
  const [kind, setKind] = useState('PROFILE_CHANGE'); const [values, setValues] = useState({ title: '', valid_from: today(), valid_to: '', full_name: '', phone: '', email: '', target_username: '', delegate_username: '', contract_reference: '', description: '', contractor: '', ownership_ratio: '1' });
  const [permissions, setPermissions] = useState(['profile', 'documents']);
  const set = field => event => setValues(previous => ({ ...previous, [field]: event.target.value }));
  const submit = async event => {
    event.preventDefault(); let data = {};
    if (kind === 'PROFILE_CHANGE') data = { full_name: values.full_name, ...(values.phone ? { phone: values.phone } : {}), ...(values.email ? { email: values.email } : {}) };
    if (kind === 'MOVE_IN') data = { full_name: values.full_name, relationship_type: 'family_member' };
    if (kind === 'LEASE') data = { target_person_id: values.target_username, contract_reference: values.contract_reference };
    if (kind === 'DELEGATION') data = { delegate_username: values.delegate_username, permissions };
    if (kind === 'TRANSFER') data = { target_username: values.target_username, ownership_ratio: values.ownership_ratio };
    if (kind === 'RENOVATION') data = { description: values.description, contractor: values.contractor };
    const result = await command.run('/dossiers', { unit_id: unitId, kind, title: values.title, valid_from: values.valid_from, valid_to: values.valid_to || null, data });
    if (result) setValues(previous => ({ ...previous, title: '', description: '' }));
  };
  return <form className="surface portal-form" onSubmit={submit}><h2>Gửi hồ sơ mới</h2><div className="portal-grid">
    <Field label="Loại hồ sơ"><select value={kind} onChange={event => setKind(event.target.value)}>{Object.entries(DOSSIER_KINDS).filter(([key]) => isOwner || ['PROFILE_CHANGE', 'MOVE_OUT', 'ABSENCE', 'RETURN'].includes(key)).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></Field>
    <Field label="Tiêu đề" value={values.title} onChange={set('title')} minLength={3} maxLength={200} required />
    <Field label="Ngày có hiệu lực" type="date" value={values.valid_from} onChange={set('valid_from')} required />
    <Field label="Ngày kết thúc" type="date" value={values.valid_to} onChange={set('valid_to')} required={['LEASE', 'DELEGATION', 'RENOVATION'].includes(kind)} />
    {['PROFILE_CHANGE', 'MOVE_IN'].includes(kind) && <Field label={kind === 'PROFILE_CHANGE' ? 'Họ tên đề nghị cập nhật' : 'Họ tên thành viên'} value={values.full_name} onChange={set('full_name')} minLength={3} maxLength={200} required />}
    {kind === 'PROFILE_CHANGE' && <><Field label="Số điện thoại đề nghị" type="tel" maxLength={30} value={values.phone} onChange={set('phone')} /><Field label="Email đề nghị" type="email" maxLength={254} value={values.email} onChange={set('email')} /></>}{['LEASE', 'TRANSFER'].includes(kind) && <Field label="Mã người thuê (hợp đồng) / tên đăng nhập người nhận (chuyển nhượng)" value={values.target_username} onChange={set('target_username')} required />}
    {kind === 'LEASE' && <Field label="Mã hợp đồng thuê" value={values.contract_reference} onChange={set('contract_reference')} required />}
    {kind === 'TRANSFER' && <Field label="Tỷ lệ chuyển nhượng (1 = toàn phần)" type="number" min="0.0001" max="1" step="0.0001" value={values.ownership_ratio} onChange={set('ownership_ratio')} required />}
    {kind === 'DELEGATION' && <><Field label="Tên đăng nhập người được ủy quyền" value={values.delegate_username} onChange={set('delegate_username')} required /><fieldset className="portal-permissions"><legend>Phạm vi ủy quyền</legend>{[['profile', 'Xem hồ sơ'], ['documents', 'Tài liệu'], ['requests', 'Yêu cầu dịch vụ'], ['parking', 'Xe/thẻ'], ['booking', 'Đặt tiện ích']].map(([key, label]) => <label key={key}><input type="checkbox" checked={permissions.includes(key)} onChange={event => setPermissions(previous => event.target.checked ? [...previous, key] : previous.filter(value => value !== key))} />{label}</label>)}</fieldset></>}
    {kind === 'RENOVATION' && <><Field label="Nội dung thi công" value={values.description} onChange={set('description')} minLength={3} required /><Field label="Nhà thầu / đơn vị thi công" value={values.contractor} onChange={set('contractor')} required /></>}
  </div><p className="portal-help">Sau khi gửi, mở hồ sơ để bổ sung tài liệu PDF hoặc ảnh. Thông tin có hiệu lực sau khi Ban quản lý xử lý.</p><button className="resident-primary" disabled={command.busy} type="submit">{command.busy ? 'Đang gửi…' : 'Gửi hồ sơ'}</button></form>;
}

function DossierDetail({ row, client, unitId, onChange, manager = false }) {
  const detail = usePortalData(client, `/dossiers/${row.id}`); const [file, setFile] = useState(null); const [supplement, setSupplement] = useState('');
  const command = usePortalCommand(client, () => { detail.refresh(); documents.refresh(); onChange(); });
  const data = detail.data || row;
  const documents = usePortalData(client, '/documents', { unit_id: data.unit_id || unitId });
  const [downloadError, setDownloadError] = useState(null);
  const [supplementData, setSupplementData] = useState(row.data || {});
  const [renovationAllowed, setRenovationAllowed] = useState([]); const [renovationReason, setRenovationReason] = useState('');
  return <div className="portal-detail"><State state={detail} /><State state={command} /><p>{data.decision_reason}</p>
    <State state={{ error: downloadError }} /><ul>{documents.data?.items?.filter(d => d.dossier_id === data.id).map(d => <li key={d.id}><button className="button-secondary" onClick={async () => { try { const result = await client.downloadPortalDocument(d.id, data.unit_id || unitId); const url = URL.createObjectURL(result.blob); const a = document.createElement("a"); a.href = url; a.download = result.filename; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); } catch (error) { setDownloadError(error); } }}>{d.title} · phiên bản {d.content_version}</button></li>)}</ul><p>Hiệu lực {data.valid_from}{data.valid_to ? ` → ${data.valid_to}` : ''}</p>
    <dl className="portal-facts">{Object.entries(data.data || {}).map(([key, value]) => <div key={key}><dt>{{ full_name: 'Họ tên', phone: 'Điện thoại', email: 'Email', target_username: 'Người nhận', delegate_username: 'Người được ủy quyền', contractor: 'Nhà thầu', description: 'Nội dung', contract_reference: 'Hợp đồng', ownership_ratio: 'Tỷ lệ', permissions: 'Phạm vi', allowed_operations: 'Nghiệp vụ được phép khi thi công' }[key] || key}</dt><dd>{Array.isArray(value) ? value.join(', ') : String(value)}</dd></div>)}</dl>
    {['SUBMITTED', 'WAITING_INFO'].includes(data.status) && <form className="portal-upload" onSubmit={async event => { event.preventDefault(); if (file && await command.run('/documents', { unit_id: data.unit_id || unitId, dossier_id: data.id, title: file.name }, file)) setFile(null); }}><Field label="Tài liệu minh chứng"><input type="file" accept="application/pdf,image/png,image/jpeg" onChange={event => setFile(event.target.files?.[0] || null)} /></Field><button className="button-secondary" disabled={!file || command.busy} type="submit">Tải tài liệu</button></form>}
    <div className="portal-actions">{manager && ['SUBMITTED', 'WAITING_INFO'].includes(data.status) && <><Action row={data} command={command} path={`/dossiers/${data.id}/actions`} action="REJECT" label="Từ chối" />{data.status === 'SUBMITTED' && <><Action row={data} command={command} path={`/dossiers/${data.id}/actions`} action="REQUEST_INFO" label="Yêu cầu bổ sung" /><Action row={data} command={command} path={`/dossiers/${data.id}/actions`} action="APPROVE" label="Phê duyệt" /></>}</>}
      {!manager && ['SUBMITTED', 'WAITING_INFO'].includes(data.status) && <Action row={data} command={command} path={`/dossiers/${data.id}/actions`} action="CANCEL" label="Hủy hồ sơ" />}
      {data.status === 'WAITING_INFO' && <form className="portal-action-form" onSubmit={async event => { event.preventDefault(); await command.run(`/dossiers/${data.id}/actions`, { action: 'SUPPLEMENT', expected_version: data.version, reason: supplement, data: supplementData }); }}><div className="portal-grid">{Object.entries(supplementData).filter(([, value]) => typeof value === "string").map(([key, value]) => <Field key={key} label={{ full_name: "Họ tên", phone: "Điện thoại", email: "Email", target_username: "Người nhận / người thuê", delegate_username: "Người được ủy quyền", ownership_ratio: "Tỷ lệ sở hữu", contractor: "Nhà thầu", description: "Nội dung", contract_reference: "Hợp đồng" }[key] || key} value={value} onChange={event => setSupplementData(v => ({ ...v, [key]: event.target.value }))} required />)}</div><Field label="Phản hồi bổ sung" value={supplement} onChange={event => setSupplement(event.target.value)} minLength={3} required /><button className="resident-primary" disabled={command.busy}>Gửi bổ sung</button></form>}
      {manager && data.kind === 'RENOVATION' && data.status === 'APPROVED' && <form onSubmit={async event => { event.preventDefault(); await command.run(`/dossiers/${data.id}/actions`, { action: 'START', expected_version: data.version, reason: renovationReason, data: { allowed_operations: renovationAllowed } }); }}><fieldset><legend>Nghiệp vụ BQL cho phép khi thi công</legend>{[['LEASE', 'Hợp đồng thuê'], ['MOVE_IN', 'Chuyển vào'], ['BOOKING', 'Đặt tiện ích'], ['SERVICE', 'Đăng ký dịch vụ'], ['PARKING', 'Đăng ký xe']].map(([k, label]) => <label key={k}><input type="checkbox" checked={renovationAllowed.includes(k)} onChange={event => setRenovationAllowed(v => event.target.checked ? [...v, k] : v.filter(x => x !== k))} />{label}</label>)}</fieldset><Field label="Căn cứ bắt đầu thi công" required minLength={3} value={renovationReason} onChange={event => setRenovationReason(event.target.value)} /><button disabled={command.busy}>Bắt đầu thi công</button></form>}{manager && (data.status === 'IN_PROGRESS' || (data.status === 'APPROVED' && data.kind !== 'RENOVATION')) && <Action row={data} command={command} path={`/dossiers/${data.id}/actions`} action="COMPLETE" label="Kết thúc hồ sơ" />}
      {manager && data.kind === 'DELEGATION' && ['APPROVED', 'COMPLETED'].includes(data.status) && <Action row={data} command={command} path={`/dossiers/${data.id}/actions`} action="REVOKE" label="Thu hồi ủy quyền" />}
    </div>{data.history?.length > 0 && <ol className="portal-history">{data.history.map(event => <li key={event.id}><strong>{when(event.created_at)}</strong><span>{event.message}</span></li>)}</ol>}
  </div>;
}

export function DossiersPanel({ client, unitId, profile, manager = false }) {
  const state = usePortalData(client, '/dossiers', { unit_id: unitId }); const command = usePortalCommand(client, state.refresh); const [selected, setSelected] = useState(null);
  const isOwner = profile?.relationships?.some(r => r.relationship_type === 'owner');
  return <Page title={manager ? 'Tiếp nhận hồ sơ cư dân' : 'Hồ sơ đăng ký'} description="Theo dõi đề nghị, minh chứng và quyết định xử lý." onRefresh={state.refresh}><State state={state} /><State state={command} />{!manager && <DossierForm unitId={unitId} command={command} isOwner={isOwner} />}
    {!state.loading && !state.error && <Records items={state.data?.items}>{row => <><div className="portal-record-head"><div><p>{DOSSIER_KINDS[row.kind]}</p><h2>{row.title}</h2><small>{when(row.created_at)}</small></div><Badge status={row.status} /></div><button className="button-secondary" type="button" onClick={() => setSelected(selected === row.id ? null : row.id)} aria-expanded={selected === row.id}>Chi tiết hồ sơ</button>{selected === row.id && <DossierDetail row={row} unitId={unitId} client={client} onChange={state.refresh} manager={manager} />}</>}</Records>}
  </Page>;
}

export function VehiclesPanel({ client, unitId, manager = false, roles = [] }) {
  const state = usePortalData(client, '/vehicles', { unit_id: unitId }); const cards = usePortalData(client, '/credentials', { unit_id: unitId });
  const resources = usePortalData(client, '/resources', { kind: 'PARKING', unit_id: unitId });
  const command = usePortalCommand(client, () => { state.refresh(); cards.refresh(); });
  const [values, setValues] = useState({ resource_id: '', plate: '', vehicle_type: 'MOTORBIKE' });
  const canApprove = roles.some(role => ['admin', 'director', 'cskh'].includes(role));
  const canCard = roles.some(role => ['admin', 'director', 'security'].includes(role));
  return <Page title="Xe & thẻ" description="Đăng ký suất xe, theo dõi danh sách chờ và báo mất thẻ." onRefresh={() => { state.refresh(); cards.refresh(); }}><State state={state} /><State state={cards} /><State state={command} />
    {!manager && <form className="surface portal-form" onSubmit={async event => { event.preventDefault(); await command.run('/vehicles', { ...values, unit_id: unitId }); }}><h2>Đăng ký phương tiện</h2><State state={resources} /><div className="portal-grid"><Field label="Bãi xe"><select value={values.resource_id} onChange={event => setValues(v => ({ ...v, resource_id: event.target.value }))} required><option value="">Chọn bãi xe</option>{resources.data?.items?.filter(row => row.status === 'OPEN').map(row => <option key={row.id} value={row.id}>{row.name} · {money(row.fee_vnd)}/kỳ</option>)}</select></Field><Field label="Biển số" value={values.plate} onChange={event => setValues(v => ({ ...v, plate: event.target.value }))} required minLength={3} maxLength={30} /><Field label="Loại xe"><select value={values.vehicle_type} onChange={event => setValues(v => ({ ...v, vehicle_type: event.target.value }))}><option value="MOTORBIKE">Xe máy</option><option value="CAR">Ô tô</option><option value="BICYCLE">Xe đạp</option></select></Field></div><button className="resident-primary" disabled={command.busy}>Gửi đăng ký</button></form>}
    {!state.loading && !state.error && <Records items={state.data?.items}>{row => <><div className="portal-record-head"><h2><Car size={20} aria-hidden="true" />{row.plate}</h2><Badge status={row.status} /></div><p>Phí đã công bố: {money(row.policy_snapshot?.fee_vnd)}/kỳ{row.offer_expires_at ? ` · Xác nhận trước ${when(row.offer_expires_at)}` : ''}</p><div className="portal-actions">
      {manager && canApprove && row.status === 'PENDING' && <Action row={row} command={command} path={`/vehicles/${row.id}/actions`} action="APPROVE" label="Duyệt đăng ký" />}
      {manager && canApprove && row.status === 'WAITING' && <Action row={row} command={command} path={`/vehicles/${row.id}/actions`} action="OFFER" label="Mời nhận suất" />}
      {!manager && row.status === 'OFFERED' && <Action row={row} command={command} path={`/vehicles/${row.id}/actions`} action="CONFIRM" label="Nhận suất" />}
      {(!manager || canApprove) && row.status === 'ACTIVE' && <Action row={row} command={command} path={`/vehicles/${row.id}/actions`} action="PAUSE" effectiveDate={row.policy_snapshot?.charge_when_paused === false} label={row.policy_snapshot?.charge_when_paused === false ? "Tạm dừng thu phí (giữ suất)" : "Tạm dừng (giữ suất và phí)"} />}
      {(!manager || canApprove) && row.status === 'PAUSED' && <Action row={row} command={command} path={`/vehicles/${row.id}/actions`} action="RESUME" effectiveDate={row.policy_snapshot?.charge_when_paused === false} label="Tiếp tục" />}
      {(!manager || canApprove) && row.status !== 'CANCELLED' && <Action row={row} command={command} path={`/vehicles/${row.id}/actions`} action="CANCEL" effectiveDate={['ACTIVE', 'PAUSED'].includes(row.status)} label="Hủy đăng ký" />}
      {manager && canCard && row.status === 'ACTIVE' && <Action row={row} command={command} path={`/vehicles/${row.id}/credential`} action="ISSUE" label="Cấp thẻ" />}
    </div></>}</Records>}
    <h2>Thẻ ra vào</h2>{!cards.loading && !cards.error && <Records items={cards.data?.items}>{row => <><div className="portal-record-head"><h3>{row.code}</h3><Badge status={row.status} /></div><p>Hết hạn {row.valid_to} · {row.sync_status === 'APPLIED' ? 'Thiết bị đã xác nhận' : row.sync_status === 'PENDING' ? 'Chờ thiết bị xác nhận' : 'Chưa kết nối thiết bị'}</p><div className="portal-actions">{!manager && row.status === 'ACTIVE' && <Action row={row} command={command} path={`/credentials/${row.id}/actions`} action="LOST" label="Báo mất / khóa khẩn cấp" />}{manager && canCard && <>{row.status !== 'REVOKED' && <Action row={row} command={command} path={`/credentials/${row.id}/actions`} action="REVOKE" label="Thu hồi" />}{row.status === 'ACTIVE' && <Action row={row} command={command} path={`/credentials/${row.id}/actions`} action="LOCK" label="Khóa thẻ" />}{row.status === 'LOCKED' && <Action row={row} command={command} path={`/credentials/${row.id}/actions`} action="UNLOCK" label="Mở khóa thẻ" />}{row.status === 'ACTIVE' && <Action row={row} command={command} path={`/credentials/${row.id}/actions`} action="RENEW" label="Gia hạn" />}{['LOST', 'LOCKED', 'EXPIRED'].includes(row.status) && <Action row={row} command={command} path={`/credentials/${row.id}/actions`} action="REPLACE" label="Cấp lại" />}</>}</div></>}</Records>}
  </Page>;
}

export function BookingsPanel({ client, unitId, manager = false }) {
  const state = usePortalData(client, '/bookings', { unit_id: unitId }); const resources = usePortalData(client, '/resources', { kind: 'FACILITY', unit_id: unitId });
  const command = usePortalCommand(client, state.refresh); const [values, setValues] = useState({ resource_id: '', starts_at: '', ends_at: '', quantity: '1' });
  const selected = resources.data?.items?.find(row => row.id === values.resource_id);
  const availability = usePortalData(client, values.resource_id ? `/resources/${values.resource_id}/availability` : '/resources', values.starts_at && values.ends_at ? { unit_id: unitId, starts_at: new Date(values.starts_at).toISOString(), ends_at: new Date(values.ends_at).toISOString() } : {}, !manager && !!unitId && !!values.resource_id && !!values.starts_at && !!values.ends_at);
  return <Page title="Đặt tiện ích" description="Chọn thời gian, xem điều kiện và theo dõi lượt đặt." onRefresh={state.refresh}><State state={state} /><State state={command} />
    {!manager && <form className="surface portal-form" onSubmit={async event => { event.preventDefault(); await command.run('/bookings', { ...values, unit_id: unitId, quantity: Number(values.quantity), starts_at: new Date(values.starts_at).toISOString(), ends_at: new Date(values.ends_at).toISOString() }); }}><State state={resources} /><div className="portal-grid"><Field label="Tiện ích"><select value={values.resource_id} onChange={event => setValues(v => ({ ...v, resource_id: event.target.value }))} required><option value="">Chọn tiện ích</option>{resources.data?.items?.filter(row => row.status === 'OPEN').map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></Field>{[['starts_at', 'Bắt đầu'], ['ends_at', 'Kết thúc']].map(([field, label]) => <Field key={field} label={label} type="datetime-local" value={values[field]} onChange={event => setValues(v => ({ ...v, [field]: event.target.value }))} required />)}<Field label="Số suất" type="number" min="1" value={values.quantity} onChange={event => setValues(v => ({ ...v, quantity: event.target.value }))} required /></div>
      <State state={availability} />{availability.data && <p>Còn {availability.data.available} / {availability.data.capacity} suất trong khung đã chọn. Khi xác nhận, hệ thống kiểm tra lại sức chứa.</p>}{selected?.policy.opening_weekdays && <p>Ngày mở cửa: {selected.policy.opening_weekdays.map(d => d === 7 ? 'Chủ nhật' : `Thứ ${d + 1}`).join(', ')} · {selected.policy.opens_at}–{selected.policy.closes_at} (GMT+7).</p>}{selected && <div className="portal-terms"><p>Phí {money(selected.fee_vnd)}/suất · Cọc {money(selected.deposit_vnd)}/suất · Khung {selected.policy.slot_minutes} phút.</p><p>Hủy trước {selected.policy.cancel_before_minutes} phút; phí hủy muộn {money(selected.policy.cancel_fee_vnd)}, không đến {money(selected.policy.no_show_fee_vnd)}.</p></div>}<button className="resident-primary" disabled={command.busy}>Xác nhận điều kiện và đặt</button></form>}
    {!state.loading && !state.error && <Records items={state.data?.items}>{row => <><div className="portal-record-head"><h2><CalendarDays size={20} aria-hidden="true" />{when(row.starts_at)} → {when(row.ends_at)}</h2><Badge status={row.status} /></div><p>{row.hold_expires_at ? `Giữ suất đến ${when(row.hold_expires_at)} · ` : ""}{row.quantity} suất · Phí {money(row.policy_snapshot?.fee_vnd)} · Cọc {money(row.policy_snapshot?.deposit_vnd)}</p><div className="portal-actions">
      {row.status === 'AWAITING_DEPOSIT' && <Action row={row} command={command} path={`/bookings/${row.id}/actions`} action="CONFIRM" label="Kiểm tra cọc và xác nhận" />}
      {manager && row.status === 'WAITING' && <Action row={row} command={command} path={`/bookings/${row.id}/actions`} action="PROMOTE" label="Nhận lượt chờ" />}
      {manager && row.status === 'CONFIRMED' && <><Action row={row} command={command} path={`/bookings/${row.id}/actions`} action="CHECK_IN" label="Ghi nhận sử dụng" /><Action row={row} command={command} path={`/bookings/${row.id}/actions`} action="NO_SHOW" label="Ghi nhận không đến" /></>}
      {manager && row.status === 'CHECKED_IN' && <Action row={row} command={command} path={`/bookings/${row.id}/actions`} action="COMPLETE" label="Hoàn tất sử dụng" />}
      {['WAITING', 'AWAITING_DEPOSIT', 'CONFIRMED'].includes(row.status) && <Action row={row} command={command} path={`/bookings/${row.id}/actions`} action={manager ? 'CANCEL_BY_FACILITY' : 'CANCEL'} label={manager ? 'Hủy do sự cố' : 'Hủy lượt đặt'} />}
    </div></>}</Records>}
  </Page>;
}

export function RequestConversation({ client, requestId, onChange, manager = false }) {
  const state = usePortalData(client, `/requests/${requestId}/messages`); const command = usePortalCommand(client, () => { state.refresh(); onChange?.(); });
  const [message, setMessage] = useState(''); const [score, setScore] = useState(5); const data = state.data;
  return <section className="portal-conversation"><h3>Trao đổi & phản hồi</h3><State state={state} /><State state={command} /><ol className="portal-history">{data?.items?.map(row => <li key={row.id}><strong>{when(row.created_at)}</strong><span>{row.message}</span></li>)}</ol>
    {data && <>{!["CLOSED", "CANCELLED"].includes(data.status) && <form className="portal-action-form" onSubmit={async event => { event.preventDefault(); if (await command.run(`/requests/${requestId}/messages`, { action: 'REPLY', expected_version: data.version, reason: message, data: {} })) setMessage(''); }}><Field label="Nội dung trao đổi"><textarea value={message} onChange={event => setMessage(event.target.value)} minLength={3} maxLength={4000} required rows={3} /></Field><button className="resident-primary" disabled={command.busy}>Gửi trao đổi</button></form>}<div className="portal-actions">
      {manager && ['NEW', 'TRIAGED', 'IN_PROGRESS'].includes(data.status) && <Action row={data} command={command} path={`/requests/${requestId}/messages`} action="REQUEST_INFO" label="Yêu cầu bổ sung" />}
      {manager && data.status === 'WAITING_INFO' && <Action row={data} command={command} path={`/requests/${requestId}/messages`} action="RESUME" label="Tiếp tục xử lý" />}
      {manager && <Action row={data} command={command} path={`/requests/${requestId}/messages`} action="RESOLVE_COMPLAINT" label="Giải quyết khiếu nại" />}
      {!manager && ['RESOLVED', 'CLOSED'].includes(data.status) && <>{data.status === 'RESOLVED' && <Action row={data} command={command} path={`/requests/${requestId}/messages`} action="CONFIRM" label="Xác nhận kết quả" />}<Action row={data} command={command} path={`/requests/${requestId}/messages`} action="REOPEN" label="Chưa đồng ý / mở lại" /><Action row={data} command={command} path={`/requests/${requestId}/messages`} action="COMPLAINT" label="Gửi khiếu nại" /></>}
      {!manager && data.status === 'CLOSED' && data.csat_score === null && <div><Field label="Mức hài lòng"><select value={score} onChange={event => setScore(Number(event.target.value))}>{[5, 4, 3, 2, 1].map(n => <option key={n} value={n}>{n} / 5</option>)}</select></Field><Action row={data} command={command} path={`/requests/${requestId}/messages`} action="RATE" data={{ score }} label="Gửi đánh giá" /></div>}
    </div>{data.csat_score != null && <p>Đánh giá đã ghi nhận: {data.csat_score}/5.</p>}</>}
  </section>;
}
