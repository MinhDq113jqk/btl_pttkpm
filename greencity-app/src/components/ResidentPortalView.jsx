import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowUpRight, Bell, Building2, CalendarClock, CheckCircle2, CircleAlert,
  FileImage, Home, LoaderCircle, LogOut, Paperclip, ReceiptText, RefreshCw,
  Send, ShieldCheck, WalletCards, X,
} from 'lucide-react';
import { GreenCityLogo } from './GreenCityLogo';

const STATUS_LABELS = {
  NEW: 'Mới tiếp nhận',
  TRIAGED: 'Đã phân loại',
  IN_PROGRESS: 'Đang xử lý',
  WAITING_INFO: 'Chờ bổ sung thông tin',
  RESOLVED: 'Đã xử lý',
  CLOSED: 'Đã đóng',
  CANCELLED: 'Đã hủy',
};

const STATUS_CLASS = {
  NEW: 'resident-status-new',
  TRIAGED: 'resident-status-triaged',
  IN_PROGRESS: 'resident-status-progress',
  WAITING_INFO: 'resident-status-waiting',
  RESOLVED: 'resident-status-resolved',
  CLOSED: 'resident-status-resolved',
  CANCELLED: 'resident-status-cancelled',
};

const PRIORITY_LABELS = { LOW: 'Thấp', MEDIUM: 'Trung bình', HIGH: 'Cao', URGENT: 'Khẩn cấp' };
const formatVnd = value => new Intl.NumberFormat('vi-VN', {
  style: 'currency', currency: 'VND', maximumFractionDigits: 0,
}).format(Number(value || 0));
const formatTime = value => value ? new Intl.DateTimeFormat('vi-VN', {
  dateStyle: 'medium', timeStyle: 'short',
}).format(new Date(value)) : '—';
const formatDate = value => value ? new Intl.DateTimeFormat('vi-VN', {
  dateStyle: 'medium',
}).format(new Date(`${value}T00:00:00`)) : '—';
const idempotencyKey = prefix => globalThis.crypto?.randomUUID?.()
  ? `${prefix}-${globalThis.crypto.randomUUID()}`
  : `${prefix}-${Date.now()}`;
const errorText = error => `${error?.message || 'Không thể hoàn tất thao tác.'}${error?.correlationId ? ` · Mã đối chiếu: ${error.correlationId}` : ''}`;

function RequestStatus({ status }) {
  return <span className={`resident-status ${STATUS_CLASS[status] || ''}`}>{STATUS_LABELS[status] || status}</span>;
}

function ResidentError({ title, error, onRetry }) {
  return <div className="resident-error" role="alert">
    <CircleAlert size={19} aria-hidden="true" />
    <div><strong>{title}</strong><p>{errorText(error)}</p></div>
    {onRetry && <button type="button" className="button-secondary" onClick={onRetry}><RefreshCw size={15} aria-hidden="true" />Thử lại</button>}
  </div>;
}

function ResidentRequestsPanel({
  account, options, optionsError, requestState, selectedRequestId, setSelectedRequestId,
  detail, showCreate, setShowCreate, form, setForm, busy, feedback, setFeedback,
  onCreate, onUpdate, editForm, setEditForm, evidenceFile, setEvidenceFile, onUploadEvidence,
  onRetry,
}) {
  const categories = useMemo(() => {
    const unit = options.units.find(item => item.id === form.unit_id);
    return options.categories.filter(item => item.building_id === null || !unit || item.building_id === unit.building_id);
  }, [form.unit_id, options.categories, options.units]);
  const editable = detail.item && ['NEW', 'WAITING_INFO'].includes(detail.item.status);

  return <div className="resident-page resident-request-page">
    <div className="resident-page-heading">
      <div><p className="resident-eyebrow">Không gian của tôi</p><h1>Yêu cầu dịch vụ</h1><p>Gửi phản ánh tới Ban quản lý và theo dõi tiến độ theo căn hộ đã xác minh.</p></div>
      <div className="resident-heading-actions"><span className="resident-scope-pill"><ShieldCheck size={14} aria-hidden="true" />Phạm vi cư dân do máy chủ cấp</span><button className="resident-primary" type="button" onClick={() => { setFeedback(null); setShowCreate(true); }}><Send size={16} aria-hidden="true" />Tạo yêu cầu</button></div>
    </div>
    {feedback && <div className={`resident-feedback resident-feedback-${feedback.type}`} role={feedback.type === 'error' ? 'alert' : 'status'}><span>{feedback.message}</span>{feedback.correlationId && <code>{feedback.correlationId}</code>}<button type="button" aria-label="Đóng thông báo" onClick={() => setFeedback(null)}><X size={15} aria-hidden="true" /></button></div>}
    {showCreate && <section className="surface resident-form-card" aria-label="Tạo yêu cầu dịch vụ">
      <div className="resident-card-heading"><div><p className="resident-eyebrow">Yêu cầu mới</p><h2>Nội dung cần Ban quản lý hỗ trợ</h2><p>Chọn căn hộ từ danh sách máy chủ trả về. Không nhập tenant, site hoặc quyền vào biểu mẫu.</p></div><button type="button" className="resident-icon-button" aria-label="Đóng biểu mẫu" onClick={() => setShowCreate(false)}><X size={18} aria-hidden="true" /></button></div>
      {optionsError && <ResidentError title="Không tải được lựa chọn tạo yêu cầu" error={optionsError} />}
      {!optionsError && <form className="resident-form-grid" onSubmit={onCreate} noValidate>
        <label>Căn hộ<select value={form.unit_id} onChange={event => setForm(previous => ({ ...previous, unit_id: event.target.value, category_id: '' }))} required><option value="">Chọn căn hộ</option>{options.units.map(item => <option key={item.id} value={item.id}>{item.unit_number}</option>)}</select></label>
        <label>Loại yêu cầu<select value={form.category_id} onChange={event => setForm(previous => ({ ...previous, category_id: event.target.value }))} required><option value="">Chọn loại hỗ trợ</option>{categories.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        <label>Ưu tiên<select value={form.priority} onChange={event => setForm(previous => ({ ...previous, priority: event.target.value }))}><option value="LOW">{PRIORITY_LABELS.LOW}</option><option value="MEDIUM">{PRIORITY_LABELS.MEDIUM}</option><option value="HIGH">{PRIORITY_LABELS.HIGH}</option><option value="URGENT">{PRIORITY_LABELS.URGENT}</option></select></label>
        <label className="resident-form-wide">Tiêu đề<input value={form.title} onChange={event => setForm(previous => ({ ...previous, title: event.target.value }))} minLength={3} maxLength={200} required placeholder="Ví dụ: Rò rỉ nước dưới chậu rửa" /></label>
        <label className="resident-form-wide">Mô tả<textarea value={form.description} onChange={event => setForm(previous => ({ ...previous, description: event.target.value }))} minLength={3} maxLength={4000} rows={4} required placeholder="Mô tả vị trí, thời điểm và mức độ ảnh hưởng…" /></label>
        <div className="resident-form-actions resident-form-wide"><button type="button" className="button-secondary" onClick={() => setShowCreate(false)}>Hủy</button><button className="resident-primary" type="submit" disabled={busy === 'create'}>{busy === 'create' ? <><LoaderCircle className="request-spinner" size={16} aria-hidden="true" />Đang gửi…</> : <><Send size={16} aria-hidden="true" />Gửi yêu cầu</>}</button></div>
      </form>}
    </section>}
    {requestState.loading && <div className="resident-loading" role="status"><LoaderCircle className="request-spinner" size={20} aria-hidden="true" />Đang tải yêu cầu của bạn…</div>}
    {requestState.error && <ResidentError title="Không tải được yêu cầu" error={requestState.error} onRetry={onRetry} />}
    {!requestState.loading && !requestState.error && <div className="resident-request-layout">
      <section className="surface resident-list-card" aria-label="Danh sách yêu cầu">
        <div className="resident-card-heading"><div><h2>Yêu cầu của tôi</h2><p>{requestState.total} hồ sơ trong phạm vi hiện tại</p></div><span className="resident-count-badge">{requestState.total}</span></div>
        {requestState.items.length === 0 ? <div className="resident-empty"><ClipboardEmpty /><h3>Chưa có yêu cầu nào</h3><p>Gửi yêu cầu đầu tiên để Ban quản lý có thể hỗ trợ bạn.</p><button type="button" className="button-secondary" onClick={() => setShowCreate(true)}>Tạo yêu cầu</button></div> : <div className="resident-request-list">{requestState.items.map(item => <button key={item.id} type="button" className={`resident-request-row ${selectedRequestId === item.id ? 'is-selected' : ''}`} onClick={() => setSelectedRequestId(item.id)}><div><strong>{item.title}</strong><span>{item.code} · {formatTime(item.created_at)}</span></div><div><RequestStatus status={item.status} /><small>Hạn SLA {formatTime(item.sla_deadline)}</small></div></button>)}</div>}
      </section>
      <section className="surface resident-detail-card" aria-label="Chi tiết yêu cầu">
        {!selectedRequestId && <div className="resident-detail-empty"><ArrowUpRight size={28} aria-hidden="true" /><h2>Chọn một yêu cầu</h2><p>Chi tiết, lịch sử và ảnh bằng chứng sẽ hiển thị ở đây.</p></div>}
        {selectedRequestId && detail.loading && <div className="resident-detail-empty"><LoaderCircle className="request-spinner" size={24} aria-hidden="true" /><p>Đang tải hồ sơ…</p></div>}
        {selectedRequestId && detail.error && <div className="resident-detail-empty"><ResidentError title="Không tải được chi tiết" error={detail.error} /></div>}
        {selectedRequestId && !detail.loading && !detail.error && detail.item && <>
          <div className="resident-detail-heading"><div><p className="resident-eyebrow">{detail.item.code}</p><h2>{detail.item.title}</h2><p>{detail.item.unit_id} · Cập nhật {formatTime(detail.item.updated_at)}</p></div><RequestStatus status={detail.item.status} /></div>
          <dl className="resident-detail-facts"><div><dt>Ưu tiên</dt><dd>{PRIORITY_LABELS[detail.item.priority] || detail.item.priority}</dd></div><div><dt>Hạn SLA</dt><dd>{formatTime(detail.item.sla_deadline)}</dd></div><div><dt>Ngày tạo</dt><dd>{formatTime(detail.item.created_at)}</dd></div><div><dt>Phiên bản</dt><dd>{detail.item.version}</dd></div></dl>
          <p className="resident-description">{detail.item.description}</p>
          {editable && <form className="resident-edit-form" onSubmit={onUpdate}><h3>Chỉnh sửa khi đang tiếp nhận</h3><label>Tiêu đề<input value={editForm.title} onChange={event => setEditForm(previous => ({ ...previous, title: event.target.value }))} minLength={3} maxLength={200} /></label><label>Ưu tiên<select value={editForm.priority} onChange={event => setEditForm(previous => ({ ...previous, priority: event.target.value }))}><option value="LOW">{PRIORITY_LABELS.LOW}</option><option value="MEDIUM">{PRIORITY_LABELS.MEDIUM}</option><option value="HIGH">{PRIORITY_LABELS.HIGH}</option><option value="URGENT">{PRIORITY_LABELS.URGENT}</option></select></label><label>Mô tả<textarea rows={3} value={editForm.description} onChange={event => setEditForm(previous => ({ ...previous, description: event.target.value }))} minLength={3} maxLength={4000} /></label><button className="button-secondary" type="submit" disabled={busy === 'update'}>{busy === 'update' ? 'Đang lưu…' : 'Lưu thay đổi'}</button></form>}
          <section className="resident-subsection"><h3><CalendarClock size={16} aria-hidden="true" />Lịch sử xử lý</h3>{detail.timeline.length === 0 ? <p className="resident-muted">Chưa có sự kiện hiển thị.</p> : <ol className="resident-timeline">{detail.timeline.map(event => <li key={event.id}><span className="resident-timeline-dot" /><div><strong>{event.event_type}</strong><span>{formatTime(event.created_at)} · {event.action}</span>{event.after_status && <small>{STATUS_LABELS[event.after_status] || event.after_status}{event.after_priority ? ` · ${PRIORITY_LABELS[event.after_priority] || event.after_priority}` : ''}</small>}</div></li>)}</ol>}</section>
          <section className="resident-subsection"><div className="resident-subsection-heading"><h3><Paperclip size={16} aria-hidden="true" />Ảnh bằng chứng</h3><span>{detail.evidence.length}</span></div>{detail.evidence.length > 0 && <ul className="resident-evidence-list">{detail.evidence.map(item => <li key={item.id}><FileImage size={17} aria-hidden="true" /><div><strong>{item.original_name}</strong><span>{Math.max(1, Math.round(item.size_bytes / 1024))} KB · {formatTime(item.created_at)}</span></div></li>)}</ul>}{editable && <div className="resident-upload-row"><label className="resident-file-input"><Paperclip size={16} aria-hidden="true" /><span>{evidenceFile?.name || 'Chọn ảnh PNG/JPEG'}</span><input type="file" accept="image/png,image/jpeg" onChange={event => setEvidenceFile(event.target.files?.[0] || null)} /></label><button type="button" className="button-secondary" onClick={onUploadEvidence} disabled={!evidenceFile || busy === 'evidence'}>{busy === 'evidence' ? 'Đang tải…' : 'Tải ảnh lên'}</button></div>}</section>
        </>}
      </section>
    </div>}
  </div>;
}

function ClipboardEmpty() {
  return <div className="resident-empty-icon"><ReceiptText size={25} aria-hidden="true" /></div>;
}

function ResidentBillingPanel({ billingState, onRetry, asOf }) {
  return <div className="resident-page">
    <div className="resident-page-heading"><div><p className="resident-eyebrow">Minh bạch tài chính</p><h1>Công nợ & hóa đơn</h1><p>Số liệu chỉ đọc từ AR ledger và snapshot hóa đơn tại một mốc xem cố định.</p></div><span className="resident-asof"><CalendarClock size={15} aria-hidden="true" />As of {formatTime(asOf)}</span></div>
    {billingState.error && <ResidentError title="Không tải được dữ liệu tài chính" error={billingState.error} onRetry={onRetry} />}
    {billingState.loading && <div className="resident-loading" role="status"><LoaderCircle className="request-spinner" size={20} aria-hidden="true" />Đang đối soát công nợ…</div>}
    {!billingState.loading && !billingState.error && <>
      <section className="resident-billing-hero"><div><p>Tổng công nợ tại mốc xem</p><strong>{formatVnd(billingState.summary?.total_ar_balance_vnd)}</strong><span>Không bao gồm dữ liệu phát sinh sau {formatTime(asOf)}</span></div><WalletCards size={38} aria-hidden="true" /></section>
      <div className="resident-billing-grid"><section className="surface resident-table-card" aria-label="Công nợ theo căn hộ"><div className="resident-card-heading"><div><h2>Số dư theo căn hộ</h2><p>Balance tính từ các bút toán AR đã ghi nhận.</p></div></div>{billingState.summary?.items?.length ? <table className="resident-table"><thead><tr><th>Căn hộ</th><th className="numeric">Còn phải thu</th></tr></thead><tbody>{billingState.summary.items.map(item => <tr key={item.unit_id}><td>{item.unit_id}</td><td className="numeric">{formatVnd(item.ar_balance_vnd)}</td></tr>)}</tbody></table> : <p className="resident-muted resident-table-empty">Chưa có số dư trong phạm vi.</p>}</section>
        <section className="surface resident-table-card" aria-label="Payment của tôi"><div className="resident-card-heading"><div><h2>Payment đã ghi nhận</h2><p>Payment hiển thị sau khi backend xác nhận.</p></div></div>{billingState.payments.length ? <table className="resident-table"><thead><tr><th>Biên lai</th><th>Nguồn</th><th className="numeric">Số tiền</th></tr></thead><tbody>{billingState.payments.map(item => <tr key={item.id}><td><strong>{item.receipt_number}</strong><small>{formatTime(item.received_at)}</small></td><td>{item.payment_source}</td><td className="numeric">{formatVnd(item.amount_vnd)}</td></tr>)}</tbody></table> : <p className="resident-muted resident-table-empty">Chưa có payment.</p>}</section></div>
      <section className="surface resident-table-card" aria-label="Hóa đơn của tôi"><div className="resident-card-heading"><div><h2>Hóa đơn đã phát hành</h2><p>Toàn bộ dòng phí giữ nguyên snapshot lịch sử.</p></div><span className="resident-count-badge">{billingState.invoices.length}</span></div>{billingState.invoices.length ? <div className="resident-invoice-list">{billingState.invoices.map(invoice => <article key={invoice.id} className="resident-invoice"><div className="resident-invoice-head"><div><strong>{invoice.invoice_number}</strong><span>Phát hành {formatDate(invoice.issued_on)}{invoice.due_on ? ` · Hạn ${formatDate(invoice.due_on)}` : ''}</span></div><strong>{formatVnd(invoice.total_vnd)}</strong></div><ul>{invoice.items.map(item => <li key={`${invoice.id}-${item.line_number}`}><span>{item.description} · {item.basis_quantity} {item.basis === 'UNIT_AREA_M2' ? 'm²' : ''} × {formatVnd(item.unit_rate_vnd_snapshot)}</span><strong>{formatVnd(item.amount_vnd)}</strong></li>)}</ul></article>)}</div> : <p className="resident-muted resident-table-empty">Chưa có hóa đơn phát hành.</p>}</section>
    </>}
  </div>;
}

function ResidentNotificationsPanel({ notificationState, showRead, setShowRead, onMarkRead, onRetry }) {
  return <div className="resident-page">
    <div className="resident-page-heading"><div><p className="resident-eyebrow">Kết nối với Ban quản lý</p><h1>Thông báo</h1><p>Thông tin gửi tới đúng tài khoản và site hiện hành; mã đối chiếu giúp tra cứu khi cần hỗ trợ.</p></div><label className="resident-toggle"><input type="checkbox" checked={showRead} onChange={event => setShowRead(event.target.checked)} />Hiện đã đọc</label></div>
    {notificationState.error && <ResidentError title="Không tải được hộp thư" error={notificationState.error} onRetry={onRetry} />}
    {notificationState.loading && <div className="resident-loading" role="status"><LoaderCircle className="request-spinner" size={20} aria-hidden="true" />Đang tải thông báo…</div>}
    {!notificationState.loading && !notificationState.error && <section className="surface resident-notification-card" aria-label="Hộp thư cư dân"><div className="resident-card-heading"><div><h2>{showRead ? 'Tất cả thông báo' : 'Chưa đọc'}</h2><p>{notificationState.unreadCount} thông báo chưa đọc</p></div><Bell size={20} aria-hidden="true" /></div>{notificationState.items.length === 0 ? <div className="resident-empty"><Bell size={28} aria-hidden="true" /><h3>Hộp thư đang trống</h3><p>Thông báo mới sẽ xuất hiện tại đây.</p></div> : <div className="resident-notification-list">{notificationState.items.map(item => { const title = item.template_snapshot?.title || item.template_code; const body = item.template_snapshot?.body || item.template_snapshot?.detail || ''; return <article key={item.id} className={`resident-notification ${item.read_at ? 'is-read' : 'is-unread'}`}><div className="resident-notification-icon"><Bell size={17} aria-hidden="true" /></div><div className="resident-notification-copy"><div><strong>{title}</strong>{!item.read_at && <span className="resident-unread-dot" aria-label="Chưa đọc" />}</div><p>{body}</p><small>{formatTime(item.created_at)} · Mã đối chiếu {item.correlation_id}</small></div>{!item.read_at && <button type="button" className="button-text" onClick={() => onMarkRead(item)}>Đánh dấu đã đọc</button>}</article>; })}</div>}</section>}
  </div>;
}

export function ResidentPortalView({ account, client, onLogout, onSwitchSite, isSwitchingSite = false, siteSwitchError }) {
  const [activeSection, setActiveSection] = useState('requests');
  const [showCreate, setShowCreate] = useState(false);
  const [selectedRequestId, setSelectedRequestId] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [showRead, setShowRead] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const [busy, setBusy] = useState('');
  const [options, setOptions] = useState({ buildings: [], categories: [], units: [] });
  const [optionsError, setOptionsError] = useState(null);
  const [requestState, setRequestState] = useState({ items: [], total: 0, loading: true, error: null });
  const [billingState, setBillingState] = useState({ summary: null, invoices: [], payments: [], loading: true, error: null });
  const [notificationState, setNotificationState] = useState({ items: [], unreadCount: 0, loading: true, error: null });
  const [detail, setDetail] = useState({ item: null, timeline: [], evidence: [], loading: false, error: null });
  const [form, setForm] = useState({ unit_id: '', category_id: '', title: '', description: '', priority: 'MEDIUM' });
  const [editForm, setEditForm] = useState({ title: '', description: '', priority: 'MEDIUM' });
  const [evidenceFile, setEvidenceFile] = useState(null);
  const intentKeys = useRef(new Map());
  const asOf = useMemo(() => new Date().toISOString(), []);
  const makeIntent = name => {
    if (!intentKeys.current.has(name)) intentKeys.current.set(name, idempotencyKey(name));
    return intentKeys.current.get(name);
  };
  const clearIntent = name => intentKeys.current.delete(name);
  const retryAll = () => setRefreshKey(value => value + 1);

  useEffect(() => {
    const controller = new AbortController();
    setOptionsError(null);
    client.getResidentServiceRequestOptions({ signal: controller.signal }).then(setOptions).catch(error => {
      if (error?.name !== 'AbortError') setOptionsError(error);
    });
    return () => controller.abort();
  }, [client, refreshKey]);

  useEffect(() => {
    const controller = new AbortController();
    setRequestState(previous => ({ ...previous, loading: true, error: null }));
    client.listResidentServiceRequests({ page: 1, page_size: 50, signal: controller.signal }).then(result => {
      setRequestState({ items: result.items, total: result.total, loading: false, error: null });
      if (selectedRequestId && !result.items.some(item => item.id === selectedRequestId)) setSelectedRequestId(null);
    }).catch(error => {
      if (error?.name !== 'AbortError') setRequestState(previous => ({ ...previous, loading: false, error }));
    });
    return () => controller.abort();
  }, [client, refreshKey, selectedRequestId]);

  useEffect(() => {
    const controller = new AbortController();
    setBillingState(previous => ({ ...previous, loading: true, error: null }));
    Promise.all([
      client.getResidentBillingSummary(asOf, { signal: controller.signal }),
      client.listResidentBillingInvoices(asOf, { signal: controller.signal }),
      client.listResidentBillingPayments(asOf, { signal: controller.signal }),
    ]).then(([summary, invoices, payments]) => setBillingState({ summary, invoices: invoices.items, payments: payments.items, loading: false, error: null }))
      .catch(error => { if (error?.name !== 'AbortError') setBillingState(previous => ({ ...previous, loading: false, error })); });
    return () => controller.abort();
  }, [asOf, client, refreshKey]);

  useEffect(() => {
    const controller = new AbortController();
    setNotificationState(previous => ({ ...previous, loading: true, error: null }));
    client.listResidentNotifications({ includeRead: showRead, page: 1, page_size: 50, signal: controller.signal }).then(result => setNotificationState({ items: result.items, unreadCount: result.unread_count, loading: false, error: null }))
      .catch(error => { if (error?.name !== 'AbortError') setNotificationState(previous => ({ ...previous, loading: false, error })); });
    return () => controller.abort();
  }, [client, refreshKey, showRead]);

  useEffect(() => {
    if (!selectedRequestId) {
      setDetail({ item: null, timeline: [], evidence: [], loading: false, error: null });
      return undefined;
    }
    const controller = new AbortController();
    setDetail(previous => ({ ...previous, loading: true, error: null }));
    Promise.all([
      client.getResidentServiceRequest(selectedRequestId, { signal: controller.signal }),
      client.getResidentServiceRequestTimeline(selectedRequestId, { signal: controller.signal }),
      client.listResidentServiceRequestEvidence(selectedRequestId, { signal: controller.signal }),
    ]).then(([item, timeline, evidence]) => {
      setDetail({ item, timeline: timeline.items, evidence: evidence.items, loading: false, error: null });
      setEditForm({ title: item.title, description: item.description, priority: item.priority });
    }).catch(error => { if (error?.name !== 'AbortError') setDetail(previous => ({ ...previous, loading: false, error })); });
    return () => controller.abort();
  }, [client, refreshKey, selectedRequestId]);

  const createRequest = async event => {
    event.preventDefault();
    if (!form.unit_id || !form.category_id || form.title.trim().length < 3 || form.description.trim().length < 3) {
      setFeedback({ type: 'error', message: 'Chọn căn hộ, loại yêu cầu và nhập đủ tiêu đề/mô tả.' });
      return;
    }
    setBusy('create'); setFeedback(null);
    try {
      const created = await client.createResidentServiceRequest(form, { idempotencyKey: makeIntent('resident-create') });
      clearIntent('resident-create');
      setForm({ unit_id: '', category_id: '', title: '', description: '', priority: 'MEDIUM' });
      setShowCreate(false); setSelectedRequestId(created.id); setActiveSection('requests'); setRefreshKey(value => value + 1);
      setFeedback({ type: 'success', message: `Đã gửi yêu cầu ${created.code}.` });
    } catch (error) {
      setFeedback({ type: 'error', message: errorText(error), correlationId: error?.correlationId });
    } finally { setBusy(''); }
  };

  const updateRequest = async event => {
    event.preventDefault();
    if (!detail.item) return;
    setBusy('update'); setFeedback(null);
    try {
      const updated = await client.updateResidentServiceRequest(detail.item.id, {
        expected_version: detail.item.version, title: editForm.title, description: editForm.description, priority: editForm.priority,
      }, { idempotencyKey: makeIntent(`resident-update-${detail.item.id}`) });
      clearIntent(`resident-update-${detail.item.id}`); setDetail(previous => ({ ...previous, item: updated })); setRefreshKey(value => value + 1); setFeedback({ type: 'success', message: 'Đã lưu thay đổi yêu cầu.' });
    } catch (error) { setFeedback({ type: 'error', message: errorText(error), correlationId: error?.correlationId }); }
    finally { setBusy(''); }
  };

  const uploadEvidence = async () => {
    if (!detail.item || !evidenceFile) return;
    setBusy('evidence'); setFeedback(null);
    try {
      await client.uploadResidentServiceRequestEvidence(detail.item.id, evidenceFile, { idempotencyKey: makeIntent(`resident-evidence-${detail.item.id}-${evidenceFile.name}`) });
      clearIntent(`resident-evidence-${detail.item.id}-${evidenceFile.name}`); setEvidenceFile(null); setRefreshKey(value => value + 1); setFeedback({ type: 'success', message: 'Đã tải ảnh bằng chứng.' });
    } catch (error) { setFeedback({ type: 'error', message: errorText(error), correlationId: error?.correlationId }); }
    finally { setBusy(''); }
  };

  const markRead = async item => {
    try {
      const marked = await client.markResidentNotificationRead(item.id);
      setNotificationState(previous => ({ ...previous, items: previous.items.map(entry => entry.id === marked.id ? marked : entry), unreadCount: Math.max(0, previous.unreadCount - 1) }));
    } catch (error) { setFeedback({ type: 'error', message: errorText(error), correlationId: error?.correlationId }); }
  };

  const sections = [
    { id: 'requests', label: 'Yêu cầu dịch vụ', icon: Home, count: requestState.total },
    { id: 'billing', label: 'Công nợ & hóa đơn', icon: ReceiptText },
    { id: 'notifications', label: 'Thông báo', icon: Bell, count: notificationState.unreadCount },
  ];

  return <div className="resident-shell">
    <header className="resident-header"><div className="resident-brand"><GreenCityLogo /><span className="resident-brand-divider" /><div><strong>Cổng cư dân</strong><span>Self‑Service</span></div></div><div className="resident-header-scope"><Building2 size={17} aria-hidden="true" /><label htmlFor="resident-site-select">Site hiện hành</label><select id="resident-site-select" value={account.activeSiteId || ''} disabled={isSwitchingSite || account.allowedSites.length < 2} onChange={event => onSwitchSite?.(event.target.value)}>{account.allowedSites.map(site => <option key={site.id} value={site.id}>{site.name}</option>)}</select>{siteSwitchError && <small role="alert">{errorText(siteSwitchError)}</small>}</div><div className="resident-header-user"><div><strong>{account.name}</strong><span>{account.site}</span></div><button type="button" className="resident-logout" onClick={onLogout}><LogOut size={16} aria-hidden="true" />Đăng xuất</button></div></header>
    <div className="resident-body"><aside className="resident-nav" aria-label="Điều hướng cổng cư dân"><p className="resident-nav-caption">Không gian cá nhân</p>{sections.map(section => { const Icon = section.icon; return <button key={section.id} type="button" role="tab" aria-selected={activeSection === section.id} className={activeSection === section.id ? 'is-active' : ''} onClick={() => setActiveSection(section.id)}><Icon size={18} aria-hidden="true" /><span>{section.label}</span>{section.count > 0 && <b>{section.count}</b>}</button>; })}<div className="resident-nav-note"><ShieldCheck size={18} aria-hidden="true" /><p><strong>Dữ liệu riêng tư</strong>Danh tính và căn hộ được đối chiếu ở máy chủ cho mỗi request.</p></div></aside><main className="resident-main" role="tabpanel" tabIndex={-1}>{activeSection === 'requests' && <ResidentRequestsPanel account={account} options={options} optionsError={optionsError} requestState={requestState} selectedRequestId={selectedRequestId} setSelectedRequestId={setSelectedRequestId} detail={detail} showCreate={showCreate} setShowCreate={setShowCreate} form={form} setForm={setForm} busy={busy} feedback={feedback} setFeedback={setFeedback} onCreate={createRequest} onUpdate={updateRequest} editForm={editForm} setEditForm={setEditForm} evidenceFile={evidenceFile} setEvidenceFile={setEvidenceFile} onUploadEvidence={uploadEvidence} onRetry={retryAll} />}{activeSection === 'billing' && <ResidentBillingPanel billingState={billingState} asOf={asOf} onRetry={retryAll} />}{activeSection === 'notifications' && <ResidentNotificationsPanel notificationState={notificationState} showRead={showRead} setShowRead={setShowRead} onMarkRead={markRead} onRetry={retryAll} />}</main></div>
    <footer className="resident-footer"><span>GreenCity · Phiên cư dân đã xác minh</span><span>Scope: {account.scope}</span></footer>
  </div>;
}
