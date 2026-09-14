import React, { useEffect, useRef, useState } from 'react';
import { AlertCircle, CalendarPlus, CheckCircle2, ClipboardCheck, LoaderCircle, Play, RefreshCw, Send, ShieldCheck, UserRoundPlus } from 'lucide-react';

const SHIFT_STATUS = {
  PLANNED: ['Đã lên kế hoạch', 'blue'], IN_PROGRESS: ['Đang trực', 'amber'],
  COMPLETED: ['Đã hoàn thành', 'emerald'], CANCELLED: ['Đã hủy', 'rose'],
};
const WINDOW_STATUS = {
  SCHEDULED: ['Chờ tuần tra', 'blue'], COMPLETED: ['Đã tuần tra', 'emerald'],
  MISSED: ['Ngoại lệ bỏ lượt', 'rose'], CANCELLED: ['Đã hủy', 'rose'],
};
const INCIDENT_NEXT = { NEW: ['TRIAGED', 'Tiếp nhận'], TRIAGED: ['IN_PROGRESS', 'Xử lý'], IN_PROGRESS: ['RESOLVED', 'Đánh dấu đã giải quyết'], RESOLVED: ['CLOSED', 'Đóng sự cố'] };
const commandKey = prefix => `${prefix}-${globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`}`;
const displayTime = value => value ? new Intl.DateTimeFormat('vi-VN', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value)) : '—';

const errorCopy = error => {
  if (error?.code === 'ERR-INCIDENT-CLOSE-REQUIREMENTS') return 'Cần có kết luận và ít nhất một bằng chứng trước khi đóng sự cố.';
  if (error?.code === 'ERR-ESCALATION-UNACKNOWLEDGED') return 'Sự cố mức cao cần đủ acknowledgement của An ninh và Giám đốc.';
  if (error?.code === 'ERR-SCOPE-NOTFOUND') return 'Dữ liệu không còn nằm trong phạm vi phiên hiện tại. Hãy tải lại danh sách.';
  return error?.message || 'Máy chủ chưa thể xử lý thao tác này.';
};

function Status({ meta, value }) {
  const [label, color] = meta[value] || [value, 'blue'];
  return <span className={`status-badge status-${color}`}>{label}</span>;
}

export function SecurityDesktopView({ account, client, onToast }) {
  const [state, setState] = useState({ data: null, loading: true, error: null });
  const [points, setPoints] = useState([]);
  const [assignees, setAssignees] = useState({});
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState('');
  const [shiftForm, setShiftForm] = useState({ patrol_point_id: '', assignee_id: '', scheduled_start_at: '', scheduled_end_at: '' });
  const [missReasons, setMissReasons] = useState({});
  const [visitorForms, setVisitorForms] = useState({});
  const [handoffForms, setHandoffForms] = useState({});
  const [incidentForms, setIncidentForms] = useState({});
  const formErrorRef = useRef(null);

  const refresh = async () => {
    setState(previous => ({ ...previous, loading: true, error: null }));
    try {
      const [dashboard, patrolPoints] = await Promise.all([
        client.listSecurityDashboard(),
        account.canManageSecurity ? client.listSecurityPatrolPoints() : Promise.resolve([]),
      ]);
      setState({ data: dashboard, loading: false, error: null });
      setPoints(patrolPoints);
    } catch (error) {
      if (error?.name !== 'AbortError') setState(previous => ({ ...previous, loading: false, error }));
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      client.listSecurityDashboard({ signal: controller.signal }),
      account.canManageSecurity ? client.listSecurityPatrolPoints({ signal: controller.signal }) : Promise.resolve([]),
    ]).then(([dashboard, patrolPoints]) => {
      setState({ data: dashboard, loading: false, error: null });
      setPoints(patrolPoints);
    }).catch(error => {
      if (error?.name !== 'AbortError') setState({ data: null, loading: false, error });
    });
    return () => controller.abort();
  }, [account.canManageSecurity, client]);

  useEffect(() => { if (formError) formErrorRef.current?.focus(); }, [formError]);

  const loadAssignees = async buildingId => {
    if (!account.canManageSecurity || assignees[buildingId]) return;
    try {
      const people = await client.listSecurityAssignees(buildingId);
      setAssignees(previous => ({ ...previous, [buildingId]: people }));
    } catch (error) { setFormError(errorCopy(error)); }
  };

  const run = async (action, success) => {
    setBusy(true);
    setFormError('');
    try {
      await action();
      await refresh();
      if (success) onToast?.(success);
    } catch (error) {
      if (error?.name !== 'AbortError') setFormError(errorCopy(error));
    } finally { setBusy(false); }
  };

  const selectedPoint = points.find(point => point.id === shiftForm.patrol_point_id);
  const selectedAssignees = selectedPoint ? assignees[selectedPoint.building_id] || [] : [];
  const createShift = event => {
    event.preventDefault();
    const start = new Date(shiftForm.scheduled_start_at);
    const end = new Date(shiftForm.scheduled_end_at);
    if (!selectedPoint || !shiftForm.assignee_id || Number.isNaN(start.valueOf()) || Number.isNaN(end.valueOf()) || end <= start) {
      setFormError('Chọn điểm tuần tra, nhân viên và thời gian kết thúc sau thời gian bắt đầu.');
      return;
    }
    run(async () => {
      await client.createSecurityShift({
        building_id: selectedPoint.building_id, assignee_id: shiftForm.assignee_id,
        scheduled_start_at: start.toISOString(), scheduled_end_at: end.toISOString(),
        patrol_windows: [{ patrol_point_id: selectedPoint.id, window_start_at: start.toISOString(), window_end_at: end.toISOString() }],
      }, { idempotencyKey: commandKey('security-shift') });
      setShiftForm({ patrol_point_id: '', assignee_id: '', scheduled_start_at: '', scheduled_end_at: '' });
    }, 'Đã tạo ca trực và cửa sổ tuần tra.');
  };

  const dashboard = state.data || { shifts: [], exceptions: [], incidents: [] };
  const canOperate = shift => account.canManageSecurity || shift.assigned_to_id === account.accountId;
  const title = account.canManageSecurity ? 'Điều phối an ninh và tuần tra' : 'Ca trực và tuần tra của tôi';

  return <div className="desktop-page security-page">
    <div className="page-heading"><div><p className="eyebrow">An ninh và PCCC</p><h1>{title}</h1><p>{account.scope} · Danh sách ca và ngoại lệ được backend lọc theo phiên.</p></div><span className="subtle-badge">{dashboard.shifts.length} ca trực</span></div>

    {formError && <div ref={formErrorRef} className="security-error-summary" role="alert" tabIndex={-1}><AlertCircle size={18} aria-hidden="true" /><span>{formError}</span></div>}

    {account.canManageSecurity && <section className="surface security-create" aria-label="Tạo ca trực an ninh">
      <div><h2><CalendarPlus size={19} aria-hidden="true" />Tạo ca và cửa sổ tuần tra</h2><p>Mỗi điểm chỉ có một cửa sổ trong ca; quyền và roster do máy chủ kiểm tra.</p></div>
      <form onSubmit={createShift} noValidate>
        <label>Điểm tuần tra<select value={shiftForm.patrol_point_id} onFocus={() => points.forEach(point => loadAssignees(point.building_id))} onChange={event => { const point = points.find(item => item.id === event.target.value); setShiftForm(previous => ({ ...previous, patrol_point_id: event.target.value, assignee_id: '' })); if (point) loadAssignees(point.building_id); }}><option value="">Chọn điểm được cấp quyền</option>{points.map(point => <option key={point.id} value={point.id}>{point.code} · {point.name}</option>)}</select></label>
        <label>Nhân viên trực<select value={shiftForm.assignee_id} disabled={!selectedPoint} onChange={event => setShiftForm(previous => ({ ...previous, assignee_id: event.target.value }))}><option value="">Chọn nhân viên</option>{selectedAssignees.map(person => <option key={person.id} value={person.id}>{person.full_name}</option>)}</select></label>
        <label>Bắt đầu<input type="datetime-local" value={shiftForm.scheduled_start_at} onChange={event => setShiftForm(previous => ({ ...previous, scheduled_start_at: event.target.value }))} /></label>
        <label>Kết thúc<input type="datetime-local" value={shiftForm.scheduled_end_at} onChange={event => setShiftForm(previous => ({ ...previous, scheduled_end_at: event.target.value }))} /></label>
        <button type="submit" className="button-primary" disabled={busy}><CalendarPlus size={16} aria-hidden="true" />{busy ? 'Đang tạo…' : 'Tạo ca'}</button>
      </form>
    </section>}

    {dashboard.exceptions.length > 0 && <section className="security-exceptions" aria-label="Ngoại lệ tuần tra"><h2><AlertCircle size={19} aria-hidden="true" />Ngoại lệ cần theo dõi</h2>{dashboard.exceptions.map(window => <article key={window.id}><div><strong>{window.patrol_point_code} · {window.patrol_point_name}</strong><p>{displayTime(window.window_start_at)} – {displayTime(window.window_end_at)}</p></div><p><span className="sr-only">Lý do bỏ lượt: </span>{window.missed_reason}</p></article>)}</section>}

    <section className="surface security-workspace" aria-label="Ca trực an ninh" aria-busy={state.loading}>
      {state.loading && <div className="request-state request-loading" role="status"><LoaderCircle className="request-spinner" size={20} aria-hidden="true" />Đang tải ca trực trong phạm vi…</div>}
      {state.error && <div className="request-state request-error" role="alert"><AlertCircle size={22} aria-hidden="true" /><div><strong>Không tải được ca trực</strong><p>{errorCopy(state.error)}</p></div><button type="button" className="button-secondary" onClick={refresh}><RefreshCw size={16} aria-hidden="true" />Thử lại</button></div>}
      {!state.loading && !state.error && dashboard.shifts.length === 0 && <div className="empty-state"><ShieldCheck size={32} aria-hidden="true" /><h2>Chưa có ca trực trong phạm vi</h2><p>{account.canManageSecurity ? 'Tạo ca để lập cửa sổ tuần tra theo điểm.' : 'Khi được phân công, ca trực sẽ xuất hiện tại đây.'}</p></div>}
      {!state.loading && !state.error && dashboard.shifts.map(shift => {
        const operator = canOperate(shift);
        const handoff = handoffForms[shift.id] || { received_by_id: '', summary: '' };
        const people = assignees[shift.building_id] || [];
        return <article className="security-shift-card" key={shift.id}>
          <header><div><p className="eyebrow">Ca trực · {shift.building_id.slice(0, 8)}</p><h2>{displayTime(shift.scheduled_start_at)} – {displayTime(shift.scheduled_end_at)}</h2><p className="task-meta">{shift.assigned_to_id === account.accountId ? 'Bạn được phân công ca này.' : 'Ca trong phạm vi điều phối.'}</p></div><Status meta={SHIFT_STATUS} value={shift.status} /></header>
          {shift.status === 'PLANNED' && operator && <button type="button" className="button-primary" disabled={busy} onClick={() => run(() => client.startSecurityShift(shift.id, shift.version), 'Đã bắt đầu ca trực.')}><Play size={16} aria-hidden="true" />Bắt đầu ca</button>}
          {account.canManageSecurity && <form className="security-inline-form" onSubmit={event => { event.preventDefault(); run(() => client.createSecurityHandoff(shift.id, handoff, { idempotencyKey: commandKey('security-handoff') }), 'Đã thêm bản ghi bàn giao.'); }}><label>Người nhận<select value={handoff.received_by_id} onFocus={() => loadAssignees(shift.building_id)} onChange={event => setHandoffForms(previous => ({ ...previous, [shift.id]: { ...handoff, received_by_id: event.target.value } }))}><option value="">Chọn nhân viên</option>{people.map(person => <option key={person.id} value={person.id}>{person.full_name}</option>)}</select></label><label>Tóm tắt bàn giao<input value={handoff.summary} onChange={event => setHandoffForms(previous => ({ ...previous, [shift.id]: { ...handoff, summary: event.target.value } }))} /></label><button type="submit" className="button-secondary" disabled={busy || !handoff.received_by_id || handoff.summary.trim().length < 3}><UserRoundPlus size={16} aria-hidden="true" />Bàn giao</button></form>}
          {shift.handoffs.length > 0 && <ol className="security-timeline" aria-label="Timeline bàn giao">{shift.handoffs.map(item => <li key={item.id}><strong>Bàn giao</strong><span>{displayTime(item.created_at)} · {item.summary}</span></li>)}</ol>}
          {operator && <form className="security-inline-form" onSubmit={event => { event.preventDefault(); const visitor = visitorForms[shift.id] || {}; if (!visitor.visitor_name?.trim() || !visitor.visit_purpose?.trim()) { setFormError('Nhập tên khách và mục đích trước khi ghi nhận.'); return; } run(() => client.createSecurityVisitor(shift.id, { ...visitor, checked_in_at: new Date().toISOString() }, { idempotencyKey: commandKey('security-visitor') }), 'Đã ghi nhận khách.'); }}><label>Khách<input value={(visitorForms[shift.id] || {}).visitor_name || ''} onChange={event => setVisitorForms(previous => ({ ...previous, [shift.id]: { ...previous[shift.id], visitor_name: event.target.value } }))} /></label><label>Mục đích<input value={(visitorForms[shift.id] || {}).visit_purpose || ''} onChange={event => setVisitorForms(previous => ({ ...previous, [shift.id]: { ...previous[shift.id], visit_purpose: event.target.value } }))} /></label><button type="submit" className="button-secondary" disabled={busy}><UserRoundPlus size={16} aria-hidden="true" />Ghi khách</button></form>}
          <div className="security-window-list">{shift.patrol_windows.map(window => {
            const draft = incidentForms[window.id] || { incident_type: 'SECURITY', severity: 'HIGH', title: '', description: '' };
            return <section className="security-window" key={window.id}><header><div><p className="eyebrow">{window.patrol_point_code}</p><h3>{window.patrol_point_name}</h3><p>{displayTime(window.window_start_at)} – {displayTime(window.window_end_at)}</p></div><Status meta={WINDOW_STATUS} value={window.status} /></header>
              {window.status === 'SCHEDULED' && operator && <div className="security-actions"><button type="button" className="button-secondary" disabled={busy} onClick={() => run(() => client.createPatrolLog(window.id, { event_type: 'CHECK_IN', occurred_at: new Date().toISOString() }, { idempotencyKey: commandKey('patrol-checkin') }), 'Đã ghi nhận đến điểm tuần tra.')}><CheckCircle2 size={16} aria-hidden="true" />Check-in</button><button type="button" className="button-primary" disabled={busy} onClick={() => run(() => client.completePatrolWindow(window.id, { expected_version: window.version }), 'Đã hoàn thành lượt tuần tra.')}><ClipboardCheck size={16} aria-hidden="true" />Hoàn thành</button><label className="security-reason">Lý do bỏ lượt<input value={missReasons[window.id] || ''} onChange={event => setMissReasons(previous => ({ ...previous, [window.id]: event.target.value }))} /></label><button type="button" className="button-danger" disabled={busy || (missReasons[window.id] || '').trim().length < 3} onClick={() => run(() => client.missPatrolWindow(window.id, { expected_version: window.version, reason: missReasons[window.id] }), 'Đã ghi ngoại lệ bỏ lượt.')}><AlertCircle size={16} aria-hidden="true" />Bỏ lượt</button></div>}
              {window.status === 'MISSED' && <p className="security-missed-reason">Lý do bỏ lượt: {window.missed_reason}</p>}
              {operator && <details className="security-incident-form"><summary>Báo sự cố hoặc PCCC</summary><div><label>Loại<select value={draft.incident_type} onChange={event => setIncidentForms(previous => ({ ...previous, [window.id]: { ...draft, incident_type: event.target.value } }))}><option value="SECURITY">An ninh</option><option value="FIRE">PCCC</option></select></label><label>Mức độ<select value={draft.severity} onChange={event => setIncidentForms(previous => ({ ...previous, [window.id]: { ...draft, severity: event.target.value } }))}><option value="LOW">Thấp</option><option value="MEDIUM">Trung bình</option><option value="HIGH">Cao</option><option value="CRITICAL">Nghiêm trọng</option></select></label><label>Tiêu đề<input value={draft.title} onChange={event => setIncidentForms(previous => ({ ...previous, [window.id]: { ...draft, title: event.target.value } }))} /></label><label>Mô tả<textarea value={draft.description} onChange={event => setIncidentForms(previous => ({ ...previous, [window.id]: { ...draft, description: event.target.value } }))} /></label><button type="button" className="button-danger" disabled={busy || draft.title.trim().length < 3 || draft.description.trim().length < 3} onClick={() => run(() => client.createSecurityIncident({ ...draft, patrol_window_id: window.id, occurred_at: new Date().toISOString() }, { idempotencyKey: commandKey('security-incident') }), 'Đã lập sự cố và escalation nếu mức độ cao.')}><Send size={16} aria-hidden="true" />Gửi sự cố</button></div></details>}
            </section>;
          })}</div>
        </article>;
      })}
    </section>

    {dashboard.incidents.length > 0 && <section className="surface security-incidents" aria-label="Sự cố an ninh và PCCC"><h2><AlertCircle size={19} aria-hidden="true" />Sự cố trong phạm vi</h2>{dashboard.incidents.map(incident => {
      const form = incidentForms[`incident-${incident.id}`] || { evidence: '', conclusion: '' };
      const next = INCIDENT_NEXT[incident.status];
      return <article key={incident.id}><header><div><p className="eyebrow">{incident.code} · {incident.incident_type}</p><h3>{incident.title}</h3><p>{incident.description}</p></div><span className={`status-badge status-${['HIGH', 'CRITICAL'].includes(incident.severity) ? 'rose' : 'amber'}`}>{incident.severity} · {incident.status}</span></header><p className="task-meta">Escalation: {incident.escalations.map(item => `${item.target_role}${item.acknowledgement ? ' đã xác nhận' : ' chờ xác nhận'}`).join(' · ') || 'Không yêu cầu'}</p><div className="security-actions">{incident.escalations.filter(item => !item.acknowledgement && account.roles.includes(item.target_role)).map(item => <button key={item.id} type="button" className="button-secondary" disabled={busy} onClick={() => run(() => client.acknowledgeSecurityEscalation(incident.id, item.id, 'Đã tiếp nhận.', { idempotencyKey: commandKey('security-ack') }), 'Đã acknowledgement escalation.')}><CheckCircle2 size={16} aria-hidden="true" />Xác nhận {item.target_role}</button>)}{next && <button type="button" className={next[0] === 'CLOSED' ? 'button-danger' : 'button-primary'} disabled={busy || (next[0] === 'CLOSED' && !account.canManageSecurity)} onClick={() => run(() => client.transitionSecurityIncident(incident.id, { expected_version: incident.version, status: next[0], conclusion: form.conclusion }), `${next[1]} sự cố thành công.`)}><ShieldCheck size={16} aria-hidden="true" />{next[1]}</button>}</div><div className="security-evidence"><label>Bằng chứng / ghi chú<textarea value={form.evidence} onChange={event => setIncidentForms(previous => ({ ...previous, [`incident-${incident.id}`]: { ...form, evidence: event.target.value } }))} /></label><button type="button" className="button-secondary" disabled={busy || form.evidence.trim().length < 3} onClick={() => run(() => client.addSecurityIncidentEvidence(incident.id, { evidence_type: 'NOTE', description: form.evidence }, { idempotencyKey: commandKey('security-evidence') }), 'Đã thêm bằng chứng.')}><ClipboardCheck size={16} aria-hidden="true" />Thêm bằng chứng</button><label>Kết luận<input value={form.conclusion} onChange={event => setIncidentForms(previous => ({ ...previous, [`incident-${incident.id}`]: { ...form, conclusion: event.target.value } }))} /></label></div></article>;
    })}</section>}
    <div className="sr-only" aria-live="polite">{busy ? 'Đang gửi thao tác an ninh.' : ''}</div>
  </div>;
}
