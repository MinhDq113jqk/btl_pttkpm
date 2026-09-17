import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertCircle, Archive, CheckCircle2, ChevronRight, Clock3, Copy, Eye, KeyRound,
  LoaderCircle, MapPin, Package, RefreshCw, Search, ShieldAlert, UserRoundCheck,
  XCircle,
} from 'lucide-react';

const STATUS_META = {
  RECEIVED: ['Đã tiếp nhận', 'blue'],
  READY_FOR_PICKUP: ['Chờ người nhận', 'amber'],
  HANDED_OVER: ['Đã bàn giao', 'emerald'],
  RETURNED: ['Đã trả lại', 'rose'],
  LOST: ['Thất lạc', 'rose'],
  DAMAGED: ['Hư hỏng', 'rose'],
};

const STATUS_FILTERS = [
  ['ALL', 'Tất cả'],
  ['RECEIVED', 'Mới nhận'],
  ['READY_FOR_PICKUP', 'Chờ nhận'],
  ['HANDED_OVER', 'Đã bàn giao'],
  ['EXCEPTIONS', 'Ngoại lệ'],
];

const EXCEPTION_STATUSES = new Set(['RETURNED', 'LOST', 'DAMAGED']);
const CASE_SOURCE_STATUSES = new Set(['HANDED_OVER', ...EXCEPTION_STATUSES]);
const EMPTY_INTAKE = {
  building_id: '', unit_id: '', recipient_person_id: '', parcel_code: '', carrier_reference: '',
  recipient_name_snapshot: '', recipient_contact_snapshot: '', storage_location: '', pin: '', received_at: '',
};

const commandKey = prefix => `${prefix}-${globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`}`;
const formatTime = value => value ? new Intl.DateTimeFormat('vi-VN', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value)) : '—';
const toIso = value => {
  if (!value) return undefined;
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf()) ? '' : parsed.toISOString();
};
const shortId = value => value ? `${value.slice(0, 8)}…${value.slice(-4)}` : '—';

const errorCopy = error => {
  if (error?.code === 'ERR-SCOPE-NOTFOUND') return 'Bản ghi không còn trong phạm vi phiên hiện tại. Hãy tải lại danh sách.';
  if (error?.code === 'ERR-PIN-INVALID') return 'PIN chưa đúng. Kiểm tra lại mã người nhận trước khi thử lại.';
  if (error?.code === 'ERR-PIN-LOCKED') return 'PIN đang bị khóa tạm thời sau nhiều lần sai. Chờ hết thời gian khóa rồi thử lại.';
  if (error?.code === 'ERR-CONFLICT') return 'Bản ghi vừa được cập nhật ở nơi khác. Tải lại để lấy version mới.';
  if (error?.code === 'ERR-STATE-TRANSITION') return 'Trạng thái hiện tại không cho phép thao tác này.';
  if (error?.code === 'ERR-DUPLICATE') return 'Mã bưu phẩm đã tồn tại trong site này. Kiểm tra mã rồi thử lại.';
  return error?.message || 'Máy chủ chưa thể hoàn tất thao tác.';
};

function StatusBadge({ value }) {
  const [label, color] = STATUS_META[value] || [value, 'blue'];
  return <span className={`status-badge status-${color}`}><span className="parcel-status-dot" aria-hidden="true" />{label}</span>;
}

export function ParcelDeskView({ account, client, onToast }) {
  const [state, setState] = useState({ items: [], total: 0, loading: true, error: null });
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [query, setQuery] = useState('');
  const [selectedId, setSelectedId] = useState(null);
  const [intakeOpen, setIntakeOpen] = useState(false);
  const [intake, setIntake] = useState(EMPTY_INTAKE);
  const [handoverPin, setHandoverPin] = useState('');
  const [exception, setException] = useState({ status: 'RETURNED', reason: '' });
  const [formError, setFormError] = useState('');
  const [busy, setBusy] = useState('');
  const [context, setContext] = useState({ loading: false, error: null, caseRecord: null, incident: null, evidence: [], timeline: [] });
  const [contextNonce, setContextNonce] = useState(0);
  const [caseReason, setCaseReason] = useState('');
  const [incidentForm, setIncidentForm] = useState({ incident_id: '', reason: '' });
  const [evidenceFile, setEvidenceFile] = useState(null);
  const [evidencePreview, setEvidencePreview] = useState(null);
  const errorRef = useRef(null);
  const intakeRef = useRef(null);
  const intentsRef = useRef(new Map());

  const intentFor = (name, payload) => {
    const fingerprint = JSON.stringify(payload);
    const existing = intentsRef.current.get(name);
    if (existing?.fingerprint === fingerprint) return existing;
    const next = { fingerprint, idempotencyKey: commandKey(`parcel-${name}`) };
    intentsRef.current.set(name, next);
    return next;
  };
  const clearIntent = name => intentsRef.current.delete(name);

  const load = async signal => {
    setState(previous => ({ ...previous, loading: true, error: null }));
    try {
      const result = await client.listParcels({
        status: statusFilter === 'ALL' || statusFilter === 'EXCEPTIONS' ? undefined : statusFilter,
        page: 1, page_size: 50, signal,
      });
      setState({ items: result.items, total: result.total, loading: false, error: null });
      setSelectedId(previous => result.items.some(item => item.id === previous) ? previous : (result.items[0]?.id || null));
      return result;
    } catch (error) {
      if (error?.name !== 'AbortError') setState(previous => ({ ...previous, loading: false, error }));
      return null;
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [client, statusFilter]);

  useEffect(() => { if (formError) errorRef.current?.focus(); }, [formError]);
  useEffect(() => {
    if (intakeOpen) window.requestAnimationFrame(() => document.getElementById('parcel-intake-code')?.focus());
  }, [intakeOpen]);
  useEffect(() => {
    setHandoverPin('');
    setException({ status: 'RETURNED', reason: '' });
    setCaseReason('');
    setIncidentForm({ incident_id: '', reason: '' });
    setEvidenceFile(null);
    setEvidencePreview(null);
  }, [selectedId]);

  useEffect(() => () => {
    if (evidencePreview?.url) URL.revokeObjectURL(evidencePreview.url);
  }, [evidencePreview?.url]);

  useEffect(() => {
    if (!selectedId) {
      setContext({ loading: false, error: null, caseRecord: null, incident: null, evidence: [], timeline: [] });
      return undefined;
    }
    const controller = new AbortController();
    const optional = promise => promise.catch(error => {
      if (error?.code === 'ERR-SCOPE-NOTFOUND') return null;
      throw error;
    });
    setContext(previous => ({ ...previous, loading: true, error: null }));
    Promise.all([
      optional(client.getParcelCase(selectedId, { signal: controller.signal })),
      optional(client.getParcelIncident(selectedId, { signal: controller.signal })),
      client.listParcelEvidence(selectedId, { signal: controller.signal }),
      client.getParcelTimeline(selectedId, { signal: controller.signal }),
    ]).then(([caseRecord, incident, evidence, timeline]) => {
      setContext({ loading: false, error: null, caseRecord, incident, evidence: evidence.items, timeline: timeline.items });
    }).catch(error => {
      if (error?.name !== 'AbortError') setContext(previous => ({ ...previous, loading: false, error }));
    });
    return () => controller.abort();
  }, [client, selectedId, contextNonce]);

  const filteredItems = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase('vi-VN');
    return state.items.filter(item => {
      if (statusFilter === 'EXCEPTIONS' && !EXCEPTION_STATUSES.has(item.status)) return false;
      if (!normalized) return true;
      return [item.parcel_code, item.recipient_name_snapshot, item.recipient_contact_snapshot,
        item.storage_location, item.unit_id].filter(Boolean)
        .some(value => String(value).toLocaleLowerCase('vi-VN').includes(normalized));
    });
  }, [query, state.items, statusFilter]);

  const selected = state.items.find(item => item.id === selectedId) || null;
  const counts = useMemo(() => ({
    total: state.total,
    received: state.items.filter(item => item.status === 'RECEIVED').length,
    ready: state.items.filter(item => item.status === 'READY_FOR_PICKUP').length,
    exceptions: state.items.filter(item => EXCEPTION_STATUSES.has(item.status)).length,
  }), [state.items, state.total]);

  const refresh = () => load();
  const run = async (name, action, success) => {
    setBusy(name);
    setFormError('');
    try {
      const result = await action();
      await load();
      setContextNonce(value => value + 1);
      setSelectedId(result?.id || selectedId);
      onToast?.(success?.(result) || 'Đã cập nhật bưu phẩm.');
      return result;
    } catch (error) {
      if (error?.name !== 'AbortError') setFormError(`${errorCopy(error)}${error?.correlationId ? ` Mã đối chiếu: ${error.correlationId}` : ''}`);
      return null;
    } finally {
      setBusy('');
    }
  };

  const updateIntake = event => {
    const { name, value } = event.target;
    setIntake(previous => ({ ...previous, [name]: value }));
    clearIntent('create');
  };

  const openIntake = () => {
    if (selected) {
      setIntake(previous => ({ ...previous, building_id: previous.building_id || selected.building_id, unit_id: previous.unit_id || selected.unit_id }));
    }
    setFormError('');
    setIntakeOpen(true);
    window.setTimeout(() => intakeRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 0);
  };

  const createParcel = event => {
    event.preventDefault();
    const receivedAt = toIso(intake.received_at);
    if (!intake.building_id.trim() || !intake.unit_id.trim() || !intake.parcel_code.trim()
      || !intake.recipient_name_snapshot.trim() || intake.pin.trim().length < 4 || (intake.received_at && !receivedAt)) {
      setFormError('Nhập đủ Building ID, Unit ID, mã bưu phẩm, tên người nhận và PIN tối thiểu 4 ký tự. Thời điểm nhận phải hợp lệ.');
      return;
    }
    const body = {
      building_id: intake.building_id.trim(), unit_id: intake.unit_id.trim(),
      recipient_person_id: intake.recipient_person_id.trim() || null,
      parcel_code: intake.parcel_code.trim(), carrier_reference: intake.carrier_reference.trim() || null,
      recipient_name_snapshot: intake.recipient_name_snapshot.trim(),
      recipient_contact_snapshot: intake.recipient_contact_snapshot.trim() || null,
      storage_location: intake.storage_location.trim() || null, pin: intake.pin,
      ...(receivedAt ? { received_at: receivedAt } : {}),
    };
    const intent = intentFor('create', body);
    run('create', () => client.createParcel(body, { idempotencyKey: intent.idempotencyKey }), result => `Đã tiếp nhận ${result.parcel_code}.`).then(result => {
      if (!result) return;
      clearIntent('create');
      setIntake(EMPTY_INTAKE);
      setIntakeOpen(false);
    });
  };

  const markReady = () => {
    if (!selected) return;
    const payload = { parcel_id: selected.id, expected_version: selected.version };
    const intent = intentFor(`ready:${selected.id}`, payload);
    run(`ready:${selected.id}`, () => client.markParcelReady(selected.id, selected.version, { idempotencyKey: intent.idempotencyKey }), () => 'Đã chuyển bưu phẩm sang chờ người nhận.').then(result => {
      if (result) clearIntent(`ready:${selected.id}`);
    });
  };

  const handover = event => {
    event.preventDefault();
    if (!selected || handoverPin.trim().length < 1) {
      setFormError('Nhập PIN người nhận trước khi xác nhận bàn giao.');
      return;
    }
    const payload = { parcel_id: selected.id, expected_version: selected.version, pin: handoverPin };
    const intent = intentFor(`handover:${selected.id}`, payload);
    run(`handover:${selected.id}`, () => client.handoverParcel(selected.id, { expected_version: selected.version, pin: handoverPin }, { idempotencyKey: intent.idempotencyKey }), () => 'Đã bàn giao bưu phẩm và ghi nhận actor.').then(result => {
      if (result) { clearIntent(`handover:${selected.id}`); setHandoverPin(''); }
    });
  };

  const recordException = event => {
    event.preventDefault();
    if (!selected || exception.reason.trim().length < 3) {
      setFormError('Nhập lý do ngoại lệ ít nhất 3 ký tự trước khi ghi nhận.');
      return;
    }
    const payload = { parcel_id: selected.id, expected_version: selected.version, ...exception };
    const intent = intentFor(`exception:${selected.id}`, payload);
    run(`exception:${selected.id}`, () => client.recordParcelException(selected.id, { ...exception, expected_version: selected.version }, { idempotencyKey: intent.idempotencyKey }), result => `Đã ghi nhận ngoại lệ: ${STATUS_META[result.status]?.[0] || result.status}.`).then(result => {
      if (result) { clearIntent(`exception:${selected.id}`); setException({ status: 'RETURNED', reason: '' }); }
    });
  };

  const openCase = event => {
    event.preventDefault();
    if (!selected || caseReason.trim().length < 3) {
      setFormError('Nhập lý do Case ít nhất 3 ký tự để giữ được bối cảnh xử lý.');
      return;
    }
    const payload = { parcel_id: selected.id, reason: caseReason.trim() };
    const intent = intentFor(`case:${selected.id}`, payload);
    run(`case:${selected.id}`, () => client.openParcelCase(selected.id, caseReason.trim(), { idempotencyKey: intent.idempotencyKey }), () => 'Đã mở Case dùng chung cho bưu phẩm.').then(result => {
      if (result) { clearIntent(`case:${selected.id}`); setCaseReason(''); }
    });
  };

  const linkIncident = event => {
    event.preventDefault();
    if (!selected || !incidentForm.incident_id.trim()) {
      setFormError('Nhập Incident ID trong cùng Building trước khi liên kết.');
      return;
    }
    const payload = { parcel_id: selected.id, incident_id: incidentForm.incident_id.trim(), reason: incidentForm.reason.trim() };
    const intent = intentFor(`incident:${selected.id}`, payload);
    run(`incident:${selected.id}`, () => client.linkParcelIncident(selected.id, { ...incidentForm, incident_id: incidentForm.incident_id.trim(), reason: incidentForm.reason.trim() }, { idempotencyKey: intent.idempotencyKey }), () => 'Đã liên kết incident vào hồ sơ bưu phẩm.').then(result => {
      if (result) { clearIntent(`incident:${selected.id}`); setIncidentForm({ incident_id: '', reason: '' }); }
    });
  };

  const viewEvidence = async item => {
    if (!selected) return;
    setBusy(`evidence-view:${item.id}`);
    setFormError('');
    try {
      const result = await client.downloadParcelEvidence(selected.id, item.id);
      const objectUrl = URL.createObjectURL(result.blob);
      setEvidencePreview({ id: item.id, name: item.original_name, url: objectUrl, contentType: result.contentType });
    } catch (error) {
      if (error?.name !== 'AbortError') setFormError(`${errorCopy(error)}${error?.correlationId ? ` Mã đối chiếu: ${error.correlationId}` : ''}`);
    } finally {
      setBusy('');
    }
  };

  const closeEvidencePreview = () => {
    setEvidencePreview(null);
  };

  const uploadEvidence = event => {
    event.preventDefault();
    if (!selected || !evidenceFile) {
      setFormError('Chọn một ảnh PNG/JPEG làm bằng chứng trước khi tải lên.');
      return;
    }
    const payload = { parcel_id: selected.id, name: evidenceFile.name, size: evidenceFile.size, lastModified: evidenceFile.lastModified };
    const intent = intentFor(`evidence:${selected.id}`, payload);
    run(`evidence:${selected.id}`, () => client.uploadParcelEvidence(selected.id, evidenceFile, {
      idempotencyKey: intent.idempotencyKey, fileName: evidenceFile.name, contentType: evidenceFile.type,
    }), () => 'Đã lưu bằng chứng private và ghi audit.').then(result => {
      if (result) { clearIntent(`evidence:${selected.id}`); setEvidenceFile(null); event.target.reset(); }
    });
  };

  const copyScopeId = async value => {
    if (!value || !navigator.clipboard?.writeText) return;
    try { await navigator.clipboard.writeText(value); onToast?.('Đã sao chép mã phạm vi.'); } catch { /* clipboard is optional */ }
  };

  return <div className="desktop-page parcel-page">
    <div className="page-heading">
      <div><p className="eyebrow">Vận hành bưu phẩm</p><h1>Tiếp nhận và bàn giao bưu phẩm</h1><p>{account.scope} · PIN chỉ dùng để xác minh tại thời điểm bàn giao; dữ liệu phạm vi do máy chủ cấp.</p></div>
      <div className="page-heading-actions"><span className="subtle-badge"><MapPin size={13} aria-hidden="true" /> {counts.total} bản ghi trong scope</span><button type="button" className="button-secondary" onClick={refresh} disabled={state.loading || Boolean(busy)}><RefreshCw size={16} aria-hidden="true" />Tải lại</button><button type="button" className="button-primary" onClick={openIntake} disabled={Boolean(busy)}><Package size={16} aria-hidden="true" />Tiếp nhận bưu phẩm</button></div>
    </div>

    {formError && <div ref={errorRef} className="parcel-error-summary" role="alert" tabIndex={-1}><AlertCircle size={18} aria-hidden="true" /><div><strong>Chưa hoàn tất thao tác</strong><p>{formError}</p><small>Kiểm tra trường nhập hoặc tải lại để lấy version mới.</small></div></div>}

    <section className="parcel-kpi-grid" aria-label="Tổng quan bưu phẩm">
      <article className="parcel-kpi parcel-kpi-total"><span><Archive size={18} aria-hidden="true" />Tổng bản ghi</span><strong>{counts.total}</strong><small>Trong phạm vi phiên</small></article>
      <article className="parcel-kpi parcel-kpi-received"><span><Package size={18} aria-hidden="true" />Mới tiếp nhận</span><strong>{counts.received}</strong><small>Chờ chuẩn bị tại quầy</small></article>
      <article className="parcel-kpi parcel-kpi-ready"><span><Clock3 size={18} aria-hidden="true" />Chờ người nhận</span><strong>{counts.ready}</strong><small>Cần PIN hợp lệ để bàn giao</small></article>
      <article className="parcel-kpi parcel-kpi-exception"><span><ShieldAlert size={18} aria-hidden="true" />Ngoại lệ</span><strong>{counts.exceptions}</strong><small>Trả lại, thất lạc hoặc hư hỏng</small></article>
    </section>

    {intakeOpen && <section ref={intakeRef} className="surface parcel-intake" aria-labelledby="parcel-intake-title">
      <div className="parcel-card-heading"><div><p className="eyebrow">Bước 1 · Ghi nhận</p><h2 id="parcel-intake-title">Tiếp nhận bưu phẩm mới</h2><p>Snapshot người nhận được lưu tại thời điểm nhận; không nhập tenant hoặc site vào request.</p></div><button type="button" className="icon-button" aria-label="Đóng form tiếp nhận" onClick={() => setIntakeOpen(false)} disabled={busy === 'create'}><XCircle size={19} aria-hidden="true" /></button></div>
      <form className="parcel-form" onSubmit={createParcel} noValidate>
        <fieldset><legend>Phạm vi do máy chủ cấp</legend><div className="parcel-form-grid">
          <label htmlFor="parcel-intake-building">Building ID <span aria-hidden="true">*</span><input id="parcel-intake-building" name="building_id" value={intake.building_id} onChange={updateIntake} autoComplete="off" required aria-describedby="parcel-scope-help" /><small id="parcel-scope-help">Dùng Building ID đã được cấp trong site hiện tại.</small></label>
          <label htmlFor="parcel-intake-unit">Unit ID <span aria-hidden="true">*</span><input id="parcel-intake-unit" name="unit_id" value={intake.unit_id} onChange={updateIntake} autoComplete="off" required /><small>Cặp Building/Unit sẽ được backend kiểm tra cùng scope.</small></label>
          <label htmlFor="parcel-intake-person">Recipient Person ID <small>(tùy chọn)</small><input id="parcel-intake-person" name="recipient_person_id" value={intake.recipient_person_id} onChange={updateIntake} autoComplete="off" /><small>Bỏ trống nếu chỉ có snapshot người nhận.</small></label>
        </div></fieldset>
        <fieldset><legend>Thông tin kiện hàng</legend><div className="parcel-form-grid">
          <label htmlFor="parcel-intake-code">Mã bưu phẩm <span aria-hidden="true">*</span><input id="parcel-intake-code" name="parcel_code" value={intake.parcel_code} onChange={updateIntake} maxLength={80} required /></label>
          <label htmlFor="parcel-intake-carrier">Mã vận đơn / hãng <small>(tùy chọn)</small><input id="parcel-intake-carrier" name="carrier_reference" value={intake.carrier_reference} onChange={updateIntake} maxLength={120} /></label>
          <label htmlFor="parcel-intake-storage">Vị trí lưu <small>(tùy chọn)</small><input id="parcel-intake-storage" name="storage_location" value={intake.storage_location} onChange={updateIntake} maxLength={120} placeholder="Ví dụ: Locker A-01" /></label>
          <label htmlFor="parcel-intake-received">Thời điểm nhận <small>(tùy chọn)</small><input id="parcel-intake-received" name="received_at" type="datetime-local" value={intake.received_at} onChange={updateIntake} /></label>
        </div></fieldset>
        <fieldset><legend>Snapshot người nhận và PIN</legend><div className="parcel-form-grid">
          <label htmlFor="parcel-intake-name">Tên người nhận <span aria-hidden="true">*</span><input id="parcel-intake-name" name="recipient_name_snapshot" value={intake.recipient_name_snapshot} onChange={updateIntake} maxLength={200} required /></label>
          <label htmlFor="parcel-intake-contact">Liên hệ snapshot <small>(tùy chọn)</small><input id="parcel-intake-contact" name="recipient_contact_snapshot" value={intake.recipient_contact_snapshot} onChange={updateIntake} maxLength={200} /></label>
          <label htmlFor="parcel-intake-pin">PIN bàn giao <span aria-hidden="true">*</span><input id="parcel-intake-pin" name="pin" type="password" inputMode="numeric" autoComplete="new-password" value={intake.pin} onChange={updateIntake} minLength={4} maxLength={64} required /><small>PIN không hiển thị lại sau khi lưu và chỉ được hash ở backend.</small></label>
        </div></fieldset>
        <div className="parcel-form-actions"><button type="button" className="button-secondary" onClick={() => setIntakeOpen(false)} disabled={busy === 'create'}>Hủy</button><button type="submit" className="button-primary" disabled={Boolean(busy)}>{busy === 'create' ? <LoaderCircle className="request-spinner" size={16} aria-hidden="true" /> : <CheckCircle2 size={16} aria-hidden="true" />}{busy === 'create' ? 'Đang lưu…' : 'Lưu bưu phẩm'}</button></div>
      </form>
    </section>}

    <div className="parcel-workspace">
      <section className="surface parcel-queue" aria-labelledby="parcel-queue-title" aria-busy={state.loading}>
        <div className="parcel-card-heading"><div><p className="eyebrow">Hàng đợi tại quầy</p><h2 id="parcel-queue-title">Bản ghi trong phạm vi</h2><p>Chọn một bưu phẩm để xem version, snapshot và hành động kế tiếp.</p></div><span className="subtle-badge">{filteredItems.length} đang hiển thị</span></div>
        <div className="parcel-toolbar"><label className="search-field" htmlFor="parcel-search"><Search size={16} aria-hidden="true" /><span className="sr-only">Tìm bưu phẩm</span><input id="parcel-search" value={query} onChange={event => setQuery(event.target.value)} placeholder="Tìm mã, người nhận, vị trí…" /></label><div className="parcel-filter-chips" role="group" aria-label="Lọc trạng thái">{STATUS_FILTERS.map(([value, label]) => <button key={value} type="button" className={statusFilter === value ? 'is-selected' : ''} aria-pressed={statusFilter === value} onClick={() => setStatusFilter(value)}>{label}{value !== 'ALL' && <span>{value === 'EXCEPTIONS' ? counts.exceptions : state.items.filter(item => item.status === value).length}</span>}</button>)}</div></div>
        {state.loading && <div className="parcel-loading" role="status"><LoaderCircle className="request-spinner" size={20} aria-hidden="true" />Đang tải hàng đợi theo phạm vi phiên…</div>}
        {state.error && !state.loading && <div className="parcel-request-error" role="alert"><AlertCircle size={20} aria-hidden="true" /><div><strong>Không tải được hàng đợi</strong><p>{errorCopy(state.error)}{state.error.correlationId ? ` Mã đối chiếu: ${state.error.correlationId}` : ''}</p></div><button type="button" className="button-secondary" onClick={refresh}><RefreshCw size={16} aria-hidden="true" />Thử lại</button></div>}
        {!state.loading && !state.error && filteredItems.length === 0 && <div className="parcel-empty"><Package size={34} aria-hidden="true" /><h3>{state.items.length ? 'Không có bản ghi khớp bộ lọc' : 'Chưa có bưu phẩm trong phạm vi'}</h3><p>{state.items.length ? 'Thử xóa từ khóa hoặc chọn trạng thái khác.' : 'Tiếp nhận bưu phẩm đầu tiên để bắt đầu hàng đợi.'}</p>{!state.items.length && <button type="button" className="button-primary" onClick={openIntake}><Package size={16} aria-hidden="true" />Tiếp nhận bưu phẩm</button>}</div>}
        {!state.loading && !state.error && filteredItems.length > 0 && <div className="parcel-list" role="list">{filteredItems.map(item => <button type="button" role="listitem" key={item.id} className={`parcel-row ${selectedId === item.id ? 'is-selected' : ''}`} aria-pressed={selectedId === item.id} onClick={() => setSelectedId(item.id)}><span className="parcel-row-main"><strong>{item.parcel_code}</strong><span>{item.recipient_name_snapshot}</span><small>{shortId(item.unit_id)} · {item.storage_location || 'Chưa có vị trí'}</small></span><span className="parcel-row-meta"><StatusBadge value={item.status} /><small>{formatTime(item.received_at)}</small></span><ChevronRight size={16} aria-hidden="true" /></button>)}</div>}
      </section>

      <aside className="surface parcel-detail" aria-labelledby="parcel-detail-title">
        {!selected && <div className="parcel-detail-empty"><Package size={34} aria-hidden="true" /><h2 id="parcel-detail-title">Chọn một bưu phẩm</h2><p>Thông tin snapshot và các bước xử lý sẽ hiển thị ở đây.</p></div>}
        {selected && <><div className="parcel-card-heading"><div><p className="eyebrow">Chi tiết · version {selected.version}</p><h2 id="parcel-detail-title">{selected.parcel_code}</h2><p>{selected.recipient_name_snapshot} · {formatTime(selected.received_at)}</p></div><StatusBadge value={selected.status} /></div><dl className="parcel-detail-facts"><div><dt>Người nhận</dt><dd>{selected.recipient_name_snapshot}</dd></div><div><dt>Liên hệ snapshot</dt><dd>{selected.recipient_contact_snapshot || '—'}</dd></div><div><dt>Unit ID</dt><dd><code>{shortId(selected.unit_id)}</code><button type="button" className="parcel-copy" aria-label="Sao chép Unit ID" onClick={() => copyScopeId(selected.unit_id)}><Copy size={13} aria-hidden="true" /></button></dd></div><div><dt>Vị trí lưu</dt><dd>{selected.storage_location || '—'}</dd></div><div><dt>Đã sẵn sàng lúc</dt><dd>{formatTime(selected.ready_for_pickup_at)}</dd></div><div><dt>Bàn giao lúc</dt><dd>{formatTime(selected.handed_over_at)}</dd></div></dl><p className="parcel-snapshot-note"><CheckCircle2 size={16} aria-hidden="true" /><span>Snapshot lịch sử không đổi sau khi bàn giao. PIN attempts hiện tại: <strong>{selected.pin_attempt_count}</strong>{selected.pin_locked_until ? ` · khóa tới ${formatTime(selected.pin_locked_until)}` : ''}.</span></p>
          <div className="parcel-actions" aria-label="Thao tác bưu phẩm">
            {selected.status === 'RECEIVED' && <button type="button" className="button-primary" disabled={Boolean(busy)} onClick={markReady}><CheckCircle2 size={16} aria-hidden="true" />Đánh dấu sẵn sàng</button>}
            {selected.status === 'READY_FOR_PICKUP' && <form className="parcel-handover-form" onSubmit={handover}><label htmlFor="parcel-handover-pin"><KeyRound size={15} aria-hidden="true" />PIN người nhận<input id="parcel-handover-pin" type="password" inputMode="numeric" autoComplete="one-time-code" value={handoverPin} onChange={event => { setHandoverPin(event.target.value); clearIntent(`handover:${selected.id}`); }} placeholder="Nhập PIN tại quầy" /></label><button type="submit" className="button-primary" disabled={Boolean(busy)}><UserRoundCheck size={16} aria-hidden="true" />{busy === `handover:${selected.id}` ? 'Đang xác minh…' : 'Xác nhận bàn giao'}</button></form>}
            {['RECEIVED', 'READY_FOR_PICKUP'].includes(selected.status) && <details className="parcel-exception"><summary><ShieldAlert size={15} aria-hidden="true" />Ghi nhận ngoại lệ</summary><form onSubmit={recordException}><label htmlFor="parcel-exception-status">Trạng thái ngoại lệ<select id="parcel-exception-status" value={exception.status} onChange={event => { setException(previous => ({ ...previous, status: event.target.value })); clearIntent(`exception:${selected.id}`); }}><option value="RETURNED">Trả lại hãng</option><option value="LOST">Thất lạc</option><option value="DAMAGED">Hư hỏng</option></select></label><label htmlFor="parcel-exception-reason">Lý do<textarea id="parcel-exception-reason" value={exception.reason} onChange={event => { setException(previous => ({ ...previous, reason: event.target.value })); clearIntent(`exception:${selected.id}`); }} minLength={3} maxLength={500} rows={3} placeholder="Mô tả ngắn gọn, có thể kiểm tra lại" /></label><button type="submit" className="button-danger" disabled={Boolean(busy)}><ShieldAlert size={16} aria-hidden="true" />Ghi nhận ngoại lệ</button></form></details>}
            {EXCEPTION_STATUSES.has(selected.status) && <p className="parcel-terminal"><XCircle size={16} aria-hidden="true" />Bản ghi terminal: {selected.exception_reason || 'đã có lý do trong audit'}. Không thể mở lại từ màn hình này.</p>}
            {selected.status === 'HANDED_OVER' && <p className="parcel-terminal parcel-terminal-success"><CheckCircle2 size={16} aria-hidden="true" />Đã bàn giao thành công. Không còn thao tác thay đổi trạng thái.</p>}
          </div>
          <section className="parcel-linked-workspace" aria-labelledby="parcel-linked-title">
            <div className="parcel-card-heading"><div><p className="eyebrow">Bước 3 · Theo dõi</p><h3 id="parcel-linked-title">Case, incident và bằng chứng</h3><p>Liên kết dùng chung với lịch sử vận hành; tệp private không lộ storage key.</p></div>{context.loading && <span className="subtle-badge"><LoaderCircle className="request-spinner" size={14} aria-hidden="true" />Đang tải</span>}</div>
            {context.error && <div className="parcel-context-error" role="alert"><AlertCircle size={16} aria-hidden="true" /><span>{errorCopy(context.error)}{context.error.correlationId ? ` Mã đối chiếu: ${context.error.correlationId}` : ''}</span></div>}
            <div className="parcel-linked-grid">
              <article className="parcel-linked-card">
                <div className="parcel-linked-card-title"><Archive size={16} aria-hidden="true" /><strong>Case dùng chung</strong>{context.caseRecord && <span className="subtle-badge">{context.caseRecord.status}</span>}</div>
                {context.caseRecord ? <><p>{context.caseRecord.reason}</p><small>Case <code>{shortId(context.caseRecord.id)}</code> · version {context.caseRecord.version}</small></> : CASE_SOURCE_STATUSES.has(selected.status) ? <form className="parcel-linked-form" onSubmit={openCase}><label htmlFor="parcel-case-reason">Lý do mở Case<input id="parcel-case-reason" value={caseReason} onChange={event => { setCaseReason(event.target.value); clearIntent(`case:${selected.id}`); }} minLength={3} maxLength={500} placeholder="Ví dụ: kiện thất lạc tại locker" /></label><button type="submit" className="button-secondary" disabled={Boolean(busy)}>{busy === `case:${selected.id}` ? 'Đang mở…' : 'Mở Case'}</button></form> : <p className="parcel-muted-copy">Case chỉ mở sau khi bàn giao hoặc khi đã ghi nhận ngoại lệ.</p>}
              </article>
              <article className="parcel-linked-card">
                <div className="parcel-linked-card-title"><ShieldAlert size={16} aria-hidden="true" /><strong>Security incident</strong>{context.incident && <span className="subtle-badge">{context.incident.severity}</span>}</div>
                {context.incident ? <><p>{context.incident.title}</p><small>{context.incident.code} · {context.incident.status} · <code>{shortId(context.incident.id)}</code></small></> : <details className="parcel-link-details"><summary>Liên kết incident có sẵn</summary><form className="parcel-linked-form" onSubmit={linkIncident}><label htmlFor="parcel-incident-id">Incident ID<input id="parcel-incident-id" value={incidentForm.incident_id} onChange={event => { setIncidentForm(previous => ({ ...previous, incident_id: event.target.value })); clearIntent(`incident:${selected.id}`); }} placeholder="UUID do máy chủ cấp" /></label><label htmlFor="parcel-incident-reason">Lý do <small>(tùy chọn)</small><input id="parcel-incident-reason" value={incidentForm.reason} onChange={event => { setIncidentForm(previous => ({ ...previous, reason: event.target.value })); clearIntent(`incident:${selected.id}`); }} placeholder="Bổ sung bối cảnh" /></label><button type="submit" className="button-secondary" disabled={Boolean(busy)}>{busy === `incident:${selected.id}` ? 'Đang liên kết…' : 'Liên kết incident'}</button></form></details>}
              </article>
            </div>
            <div className="parcel-evidence-panel">
              <div className="parcel-linked-card-title"><CheckCircle2 size={16} aria-hidden="true" /><strong>Bằng chứng private</strong><span className="subtle-badge">{context.evidence.length} tệp</span></div>
              {context.evidence.length > 0 && <ul className="parcel-evidence-list">{context.evidence.map(item => <li key={item.id}><span><strong>{item.original_name}</strong><small>{item.mime_type} · {Math.max(1, Math.round(item.size_bytes / 1024))} KB · SHA-256 {shortId(item.sha256)}</small></span><span className="parcel-evidence-meta"><time dateTime={item.created_at}>{formatTime(item.created_at)}</time><button type="button" className="button-text parcel-evidence-view" onClick={() => viewEvidence(item)} disabled={Boolean(busy)} aria-label={`Xem bằng chứng ${item.original_name}`}>{busy === `evidence-view:${item.id}` ? <LoaderCircle className="request-spinner" size={14} aria-hidden="true" /> : <Eye size={14} aria-hidden="true" />}Xem</button></span></li>)}</ul>}
              {evidencePreview && <div className="parcel-evidence-preview" aria-label={`Xem trước ${evidencePreview.name}`}><div className="parcel-evidence-preview-heading"><strong>{evidencePreview.name}</strong><button type="button" className="button-text" onClick={closeEvidencePreview}>Đóng xem</button></div><img src={evidencePreview.url} alt={`Xem trước ${evidencePreview.name}`} /></div>}
              {context.evidence.length === 0 && !context.loading && <p className="parcel-muted-copy">Chưa có ảnh bằng chứng được lưu.</p>}
              <form className="parcel-evidence-upload" onSubmit={uploadEvidence}><label htmlFor="parcel-evidence-file">Tải ảnh PNG/JPEG <input id="parcel-evidence-file" type="file" accept="image/png,image/jpeg" onChange={event => setEvidenceFile(event.target.files?.[0] || null)} /></label><small>Private, tối đa 10 MB; server kiểm tra magic bytes, MIME và checksum.</small><button type="submit" className="button-secondary" disabled={Boolean(busy) || !evidenceFile}>{busy === `evidence:${selected.id}` ? 'Đang tải lên…' : 'Thêm bằng chứng'}</button></form>
            </div>
            <div className="parcel-timeline" aria-label="Timeline audit bưu phẩm"><div className="parcel-linked-card-title"><Clock3 size={16} aria-hidden="true" /><strong>Timeline audit</strong><span className="subtle-badge">{context.timeline.length} sự kiện</span></div>{context.timeline.length === 0 && !context.loading && <p className="parcel-muted-copy">Chưa có sự kiện liên kết.</p>}{context.timeline.length > 0 && <ol>{context.timeline.map(item => <li key={item.id}><div><strong>{item.event_type}</strong><small>{item.action} · {item.resource_type} · correlation <code>{shortId(item.correlation_id)}</code></small></div><time dateTime={item.created_at}>{formatTime(item.created_at)}</time></li>)}</ol>}</div>
          </section>
        </>}
      </aside>
    </div>
    <div className="sr-only" aria-live="polite">{busy ? 'Đang gửi thao tác bưu phẩm.' : ''}</div>
  </div>;
}
