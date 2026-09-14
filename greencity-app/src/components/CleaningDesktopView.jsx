import React, { useEffect, useRef, useState } from 'react';
import { AlertCircle, CalendarPlus, CheckCircle2, ClipboardCheck, LoaderCircle, Play, RefreshCw, Send, UserRoundPlus } from 'lucide-react';

const STATUS_META = {
  PLANNED: ['Đã lên kế hoạch', 'blue'],
  ASSIGNED: ['Đã phân công', 'blue'],
  IN_PROGRESS: ['Đang thực hiện', 'amber'],
  SUBMITTED: ['Chờ nghiệm thu', 'amber'],
  ACCEPTED: ['Đã nghiệm thu', 'emerald'],
  MISSED: ['Bỏ lỡ', 'rose'],
  REWORK_REQUIRED: ['Cần làm lại', 'rose'],
  CANCELLED: ['Đã hủy', 'rose'],
};

const commandKey = prefix => `${prefix}-${globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`}`;
const displayTime = value => value ? new Intl.DateTimeFormat('vi-VN', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value)) : '—';

const errorCopy = error => {
  if (error?.code === 'ERR-CHECKLIST-INCOMPLETE') return 'Hoàn tất các mục checklist bắt buộc với kết quả Đạt hoặc Không đạt trước khi nộp.';
  if (error?.code === 'ERR-SCOPE-NOTFOUND') return 'Dữ liệu không còn nằm trong phạm vi phiên hiện tại. Tải lại danh sách để tiếp tục.';
  return error?.message || 'Máy chủ chưa thể xử lý thao tác này.';
};

function TaskStatus({ status }) {
  const [label, color] = STATUS_META[status] || [status, 'blue'];
  return <span className={`status-badge status-${color}`}>{label}</span>;
}

export function CleaningDesktopView({ account, client, onToast }) {
  const [state, setState] = useState({ items: [], loading: true, error: null });
  const [routes, setRoutes] = useState([]);
  const [assignees, setAssignees] = useState({});
  const [assignment, setAssignment] = useState({});
  const [busy, setBusy] = useState({});
  const [taskErrors, setTaskErrors] = useState({});
  const [createError, setCreateError] = useState('');
  const [shiftForm, setShiftForm] = useState({ route_id: '', scheduled_start_at: '', scheduled_end_at: '' });
  const formErrorRef = useRef(null);

  const replaceTask = updated => setState(previous => ({
    ...previous,
    items: previous.items.map(item => item.id === updated.id ? updated : item),
  }));
  const refresh = async () => {
    setState(previous => ({ ...previous, loading: true, error: null }));
    try {
      const [tasks, routeOptions] = await Promise.all([
        client.listCleaningTasks(),
        account.canManageCleaning ? client.listCleaningRoutes() : Promise.resolve([]),
      ]);
      setState({ items: tasks.items, loading: false, error: null });
      setRoutes(routeOptions);
    } catch (error) {
      if (error?.name !== 'AbortError') setState(previous => ({ ...previous, loading: false, error }));
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    setState(previous => ({ ...previous, loading: true, error: null }));
    Promise.all([
      client.listCleaningTasks({ signal: controller.signal }),
      account.canManageCleaning ? client.listCleaningRoutes({ signal: controller.signal }) : Promise.resolve([]),
    ]).then(([tasks, routeOptions]) => {
      setState({ items: tasks.items, loading: false, error: null });
      setRoutes(routeOptions);
    }).catch(error => {
      if (error?.name !== 'AbortError') setState(previous => ({ ...previous, loading: false, error }));
    });
    return () => controller.abort();
  }, [account.canManageCleaning, client]);

  useEffect(() => {
    if (createError) formErrorRef.current?.focus();
  }, [createError]);

  const runTaskCommand = async (task, action, successMessage) => {
    const key = `${task.id}:${action.name}`;
    setBusy(previous => ({ ...previous, [key]: true }));
    setTaskErrors(previous => ({ ...previous, [task.id]: null }));
    try {
      const updated = await action();
      replaceTask(updated);
      onToast?.(successMessage);
    } catch (error) {
      if (error?.name !== 'AbortError') setTaskErrors(previous => ({ ...previous, [task.id]: error }));
    } finally {
      setBusy(previous => ({ ...previous, [key]: false }));
    }
  };

  const loadAssignees = async buildingId => {
    if (assignees[buildingId]) return;
    try {
      const people = await client.listCleaningAssignees(buildingId);
      setAssignees(previous => ({ ...previous, [buildingId]: people }));
    } catch (error) {
      onToast?.(errorCopy(error), 'error');
    }
  };

  const createShift = async event => {
    event.preventDefault();
    const start = new Date(shiftForm.scheduled_start_at);
    const end = new Date(shiftForm.scheduled_end_at);
    if (!shiftForm.route_id || Number.isNaN(start.valueOf()) || Number.isNaN(end.valueOf()) || end <= start) {
      setCreateError('Chọn tuyến và nhập thời gian kết thúc sau thời gian bắt đầu.');
      return;
    }
    setCreateError('');
    setBusy(previous => ({ ...previous, create: true }));
    try {
      const shift = await client.createCleaningShift({
        route_id: shiftForm.route_id,
        scheduled_start_at: start.toISOString(),
        scheduled_end_at: end.toISOString(),
      }, { idempotencyKey: commandKey('cleaning-shift') });
      setShiftForm({ route_id: '', scheduled_start_at: '', scheduled_end_at: '' });
      await refresh();
      onToast?.(`Đã tạo ca vệ sinh với ${shift.tasks.length} khu vực.`);
    } catch (error) {
      setCreateError(errorCopy(error));
    } finally {
      setBusy(previous => ({ ...previous, create: false }));
    }
  };

  const title = account.canManageCleaning ? 'Điều phối ca vệ sinh' : 'Ca vệ sinh của tôi';
  const canWork = task => task.assigned_to_id === account.accountId;

  return <div className="desktop-page cleaning-page">
    <div className="page-heading"><div><p className="eyebrow">Vận hành môi trường</p><h1>{title}</h1><p>{account.scope} · Danh sách và quyền thao tác do máy chủ cấp theo phiên.</p></div><span className="subtle-badge">{state.items.length} task</span></div>

    {account.canManageCleaning && <section className="surface cleaning-create" aria-label="Tạo ca vệ sinh">
      <div><h2><CalendarPlus size={19} aria-hidden="true" />Tạo ca theo tuyến</h2><p>Checklist được snapshot theo từng khu vực khi tạo ca.</p></div>
      <form onSubmit={createShift} noValidate>
        {createError && <div id="cleaning-shift-error" ref={formErrorRef} className="cleaning-error-summary" role="alert" tabIndex={-1}><AlertCircle size={18} aria-hidden="true" /><span>{createError}</span></div>}
        <label>Tuyến<select value={shiftForm.route_id} onChange={event => setShiftForm(previous => ({ ...previous, route_id: event.target.value }))} required aria-describedby={createError ? 'cleaning-shift-error' : undefined}><option value="">Chọn tuyến được cấp quyền</option>{routes.map(route => <option key={route.id} value={route.id}>{route.code} · {route.name}</option>)}</select></label>
        <label>Bắt đầu<input type="datetime-local" value={shiftForm.scheduled_start_at} onChange={event => setShiftForm(previous => ({ ...previous, scheduled_start_at: event.target.value }))} required /></label>
        <label>Kết thúc<input type="datetime-local" value={shiftForm.scheduled_end_at} onChange={event => setShiftForm(previous => ({ ...previous, scheduled_end_at: event.target.value }))} required /></label>
        <button className="button-primary" type="submit" disabled={busy.create}><CalendarPlus size={16} aria-hidden="true" />{busy.create ? 'Đang tạo…' : 'Tạo ca'}</button>
      </form>
    </section>}

    <section className="surface cleaning-workspace" aria-label="Danh sách task vệ sinh" aria-busy={state.loading}>
      {state.loading && <div className="request-state request-loading" role="status"><LoaderCircle className="request-spinner" size={20} aria-hidden="true" />Đang tải task vệ sinh đúng phạm vi…</div>}
      {state.error && <div className="request-state request-error" role="alert"><AlertCircle size={22} aria-hidden="true" /><div><strong>Không tải được ca vệ sinh</strong><p>{errorCopy(state.error)}</p>{state.error.correlationId && <small>Mã đối chiếu: {state.error.correlationId}</small>}</div><button type="button" className="button-secondary" onClick={refresh}><RefreshCw size={16} aria-hidden="true" />Thử lại</button></div>}
      {!state.loading && !state.error && state.items.length === 0 && <div className="empty-state"><ClipboardCheck size={32} aria-hidden="true" /><h2>Chưa có task vệ sinh trong phạm vi</h2><p>{account.canManageCleaning ? 'Tạo ca theo tuyến để sinh các khu vực cần thực hiện.' : 'Khi được phân công, task của bạn sẽ xuất hiện tại đây.'}</p></div>}
      {!state.loading && !state.error && state.items.length > 0 && <div className="cleaning-task-list">{state.items.map(task => {
        const taskBusy = Object.entries(busy).some(([key, value]) => value && key.startsWith(`${task.id}:`));
        const canExecute = canWork(task);
        const people = assignees[task.building_id] || [];
        return <article className="cleaning-task-card" key={task.id}>
          <header><div><p className="eyebrow">{task.route_code} · {task.area_code}</p><h2>{task.area_name}</h2><p className="task-meta">Ca {displayTime(task.scheduled_start_at)} – {displayTime(task.scheduled_end_at)}</p></div><TaskStatus status={task.status} /></header>
          <dl className="cleaning-task-meta"><div><dt>Người thực hiện</dt><dd>{task.assigned_to_id ? (canExecute ? 'Bạn' : 'Đã phân công') : 'Chưa phân công'}</dd></div><div><dt>Bắt đầu</dt><dd>{displayTime(task.started_at)}</dd></div><div><dt>Nộp kết quả</dt><dd>{displayTime(task.submitted_at)}</dd></div></dl>
          {taskErrors[task.id] && <div className="cleaning-task-error" role="alert"><AlertCircle size={17} aria-hidden="true" /><span>{errorCopy(taskErrors[task.id])}{taskErrors[task.id].correlationId ? ` Mã đối chiếu: ${taskErrors[task.id].correlationId}` : ''}</span></div>}
          {account.canManageCleaning && ['PLANNED', 'ASSIGNED'].includes(task.status) && <div className="cleaning-manager-actions"><label>Phân công<select value={assignment[task.id] || ''} onFocus={() => loadAssignees(task.building_id)} onChange={event => setAssignment(previous => ({ ...previous, [task.id]: event.target.value }))}><option value="">Chọn nhân viên</option>{people.map(person => <option key={person.id} value={person.id}>{person.full_name}</option>)}</select></label><button className="button-secondary" type="button" disabled={!assignment[task.id] || taskBusy} onClick={() => runTaskCommand(task, () => client.assignCleaningTask(task.id, { assignee_id: assignment[task.id], expected_version: task.version }), 'Đã phân công task vệ sinh.')}><UserRoundPlus size={16} aria-hidden="true" />Phân công</button></div>}
          {task.checklist.length > 0 && <div className="cleaning-checklist"><h3>Checklist bắt buộc</h3><p id={`checklist-help-${task.id}`}>{task.status === 'IN_PROGRESS' ? 'Chọn Đạt hoặc Không đạt cho từng mục. Kết quả Không đạt sẽ tạo Work Order và Case làm lại khi nộp.' : 'Kết quả checklist là lịch sử của ca này và chỉ đọc sau khi task đã được nộp hoặc đóng.'}</p>{task.checklist.map(item => <label className="cleaning-checklist-item" key={item.id}><span><strong>{item.position}. {item.label}</strong>{item.is_required && <small>Bắt buộc</small>}</span><select aria-label={`Kết quả ${item.label}`} aria-describedby={`checklist-help-${task.id}`} value={item.result} disabled={task.status !== 'IN_PROGRESS' || !canExecute || taskBusy} onChange={event => runTaskCommand(task, () => client.updateCleaningChecklist(task.id, item.id, { expected_version: item.version, result: event.target.value }), 'Đã lưu kết quả checklist.')}><option value="PENDING">Chưa đánh giá</option><option value="PASS">Đạt</option><option value="FAIL">Không đạt</option><option value="NOT_APPLICABLE">Không áp dụng</option></select></label>)}</div>}
          <footer className="cleaning-actions">
            {task.status === 'ASSIGNED' && canExecute && <button className="button-primary" type="button" disabled={taskBusy} onClick={() => runTaskCommand(task, () => client.startCleaningTask(task.id, task.version), 'Đã bắt đầu task vệ sinh.')}><Play size={16} aria-hidden="true" />Bắt đầu</button>}
            {task.status === 'IN_PROGRESS' && canExecute && <button className="button-primary" type="button" disabled={taskBusy} onClick={() => runTaskCommand(task, () => client.submitCleaningTask(task.id, task.version, { idempotencyKey: commandKey('cleaning-submit') }), 'Đã nộp kết quả checklist.')}><Send size={16} aria-hidden="true" />Nộp kết quả</button>}
            {task.status === 'SUBMITTED' && account.canManageCleaning && <button className="button-primary" type="button" disabled={taskBusy} onClick={() => runTaskCommand(task, () => client.acceptCleaningTask(task.id, task.version), 'Đã nghiệm thu task vệ sinh.')}><CheckCircle2 size={16} aria-hidden="true" />Nghiệm thu</button>}
            {task.status === 'REWORK_REQUIRED' && <p className="context-note">Đã tạo Work Order và Case làm lại; checklist lỗi của ca này được giữ nguyên.</p>}
          </footer>
        </article>;
      })}</div>}
    </section>
  </div>;
}
