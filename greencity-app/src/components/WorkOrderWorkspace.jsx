import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AlertCircle, CheckCircle2, ClipboardCheck, RefreshCw, Upload } from 'lucide-react';
import './WorkOrderWorkspace.css';

const STATUS_LABELS = {
  NEW: 'Mới', TRIAGED: 'Đã phân loại', IN_PROGRESS: 'Đang xử lý', WAITING_INFO: 'Chờ thông tin',
  RESOLVED: 'Đã giải quyết', CLOSED: 'Đã đóng', CANCELLED: 'Đã hủy', DRAFT: 'Bản nháp',
  ASSIGNED: 'Đã giao', ON_HOLD: 'Tạm dừng', WAITING_ACCEPTANCE: 'Chờ nghiệm thu', COMPLETED: 'Đã nghiệm thu',
};

const textError = error => error?.message || 'Máy chủ chưa thể xử lý yêu cầu.';
const commandKey = () => globalThis.crypto.randomUUID();

export function WorkOrderWorkspace({ account, client, selectedTask }) {
  const roles = new Set(account.roles || []);
  const canTriage = roles.has('cskh');
  const canLead = roles.has('technical_lead');
  const canCreate = canTriage || canLead;
  const requestId = selectedTask.recordId;
  const [request, setRequest] = useState(null);
  const [workOrders, setWorkOrders] = useState([]);
  const [triageAssignees, setTriageAssignees] = useState([]);
  const [technicians, setTechnicians] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState('');
  const [ownerId, setOwnerId] = useState('');
  const [priority, setPriority] = useState(selectedTask.priority);
  const [woTitle, setWoTitle] = useState('');
  const [woDescription, setWoDescription] = useState('');
  const [checklistText, setChecklistText] = useState('');
  const commandKeys = useRef(new Map());

  const load = useCallback(async signal => {
    setLoading(true);
    setError(null);
    try {
      const tasks = [
        client.getServiceRequest(requestId, { signal }),
        client.listServiceRequestWorkOrders(requestId, { signal }),
        canTriage ? client.listServiceRequestAssignees(requestId, 'triage', { signal }) : Promise.resolve([]),
        canLead ? client.listServiceRequestAssignees(requestId, 'work_order', { signal }) : Promise.resolve([]),
      ];
      const [nextRequest, nextOrders, nextTriageAssignees, nextTechnicians] = await Promise.all(tasks);
      setRequest(nextRequest);
      setWorkOrders(nextOrders);
      setTriageAssignees(nextTriageAssignees);
      setTechnicians(nextTechnicians);
      setPriority(nextRequest.priority);
      if (!ownerId && nextTriageAssignees.length) setOwnerId(nextTriageAssignees[0].id);
    } catch (caught) {
      if (caught?.name !== 'AbortError') setError(caught);
    } finally {
      setLoading(false);
    }
  }, [canLead, canTriage, client, ownerId, requestId]);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const keyFor = name => {
    if (!commandKeys.current.has(name)) commandKeys.current.set(name, commandKey());
    return commandKeys.current.get(name);
  };

  const perform = async (name, callback, successText) => {
    setBusy(name);
    setError(null);
    setNotice('');
    try {
      await callback();
      await load();
      commandKeys.current.delete(name);
      setNotice(successText);
      return true;
    } catch (caught) {
      setError(caught);
      return false;
    } finally {
      setBusy('');
    }
  };

  const triage = () => request && perform('triage', () => client.triageServiceRequest(request.id, {
    expected_version: request.version, owner_account_id: ownerId, priority,
  }), 'Đã lưu phân loại yêu cầu.');

  const createWorkOrder = async () => {
    const checklist = checklistText.split(/\r?\n/).map(label => label.trim()).filter(Boolean).map(label => ({ label, required: true }));
    if (checklist.length === 0) {
      setError(new Error('Thêm ít nhất một mục checklist trước khi tạo Work Order.'));
      return;
    }
    const name = 'create-work-order';
    const completed = await perform(name, () => client.createWorkOrder(request.id, {
      title: woTitle, description: woDescription, checklist,
    }, { idempotencyKey: keyFor(name) }), 'Đã tạo Work Order.');
    if (completed) {
      setWoTitle('');
      setWoDescription('');
      setChecklistText('');
    }
  };

  const requestClose = () => request && perform('close-request', () => client.closeServiceRequest(request.id, {
    expected_version: request.version,
  }), 'Đã đóng yêu cầu.');

  return <div className="workflow-workspace">
    {loading && <div className="workflow-state" role="status"><RefreshCw size={17} className="workflow-spin" />Đang tải hồ sơ và Work Order từ máy chủ…</div>}
    {error && <div className="workflow-error" role="alert"><AlertCircle size={18} /><div><strong>Không hoàn tất được thao tác.</strong><p>{textError(error)}</p>{error.correlationId && <small>Mã đối chiếu: {error.correlationId}</small>}</div><button className="button-text" onClick={() => load()}>Tải lại</button></div>}
    {!loading && request && <>
      <section className="workflow-request-summary">
        <div className="workflow-summary-heading"><div><span className={`workflow-status workflow-status-${request.status.toLowerCase()}`}>{STATUS_LABELS[request.status] || request.status}</span><h3>{request.title}</h3></div><span className="workflow-request-code">{request.code}</span></div>
        <p>{request.description}</p>
        <dl><div><dt>Ưu tiên</dt><dd>{request.priority}</dd></div><div><dt>Yêu cầu được tạo</dt><dd>{selectedTask.createdAt}</dd></div><div><dt>Hạn SLA</dt><dd>{selectedTask.deadline}</dd></div><div><dt>Phiên bản</dt><dd>{request.version}</dd></div></dl>
      </section>

      {canTriage && ['NEW', 'TRIAGED'].includes(request.status) && <section className="workflow-section">
        <div className="workflow-section-heading"><ClipboardCheck size={18} /><div><h3>Tiếp nhận và phân loại</h3><p>Máy chủ kiểm tra người được giao trong đúng tòa nhà.</p></div></div>
        <div className="workflow-form-grid">
          <label>Người phụ trách<select value={ownerId} onChange={event => setOwnerId(event.target.value)}><option value="">Chọn người phụ trách</option>{triageAssignees.map(person => <option value={person.id} key={`${person.id}-${person.role}`}>{person.full_name} · {person.role}</option>)}</select></label>
          <label>Ưu tiên<select value={priority} onChange={event => setPriority(event.target.value)}>{['LOW', 'MEDIUM', 'HIGH', 'URGENT'].map(value => <option key={value}>{value}</option>)}</select></label>
        </div>
        <button className="button-primary" type="button" disabled={Boolean(busy) || !ownerId} onClick={triage}>{busy === 'triage' ? 'Đang lưu…' : 'Lưu phân loại'}</button>
      </section>}

      {canCreate && !['RESOLVED', 'CLOSED', 'CANCELLED'].includes(request.status) && <section className="workflow-section">
        <div className="workflow-section-heading"><ClipboardCheck size={18} /><div><h3>Tạo Work Order</h3><p>Mỗi dòng trong checklist trở thành một mục cần ghi nhận kết quả.</p></div></div>
        <div className="workflow-form-grid">
          <label>Tiêu đề<input value={woTitle} onChange={event => setWoTitle(event.target.value)} maxLength={200} /></label>
          <label>Mô tả<textarea value={woDescription} onChange={event => setWoDescription(event.target.value)} rows={2} maxLength={4000} /></label>
          <label className="workflow-wide">Checklist<textarea value={checklistText} onChange={event => setChecklistText(event.target.value)} rows={3} placeholder={'Kiểm tra nguyên nhân\nThực hiện sửa chữa\nChạy thử và ghi nhận kết quả'} /></label>
        </div>
        <button className="button-primary" type="button" disabled={Boolean(busy) || woTitle.trim().length < 3 || woDescription.trim().length < 3} onClick={createWorkOrder}>{busy === 'create-work-order' ? 'Đang tạo…' : 'Tạo Work Order'}</button>
      </section>}

      <section className="workflow-section workflow-orders">
        <div className="workflow-section-heading"><div><h3>Work Orders</h3><p>{workOrders.length} công việc trong yêu cầu này.</p></div></div>
        {workOrders.length === 0 && <div className="workflow-empty">Chưa có Work Order. Khi được phân loại, yêu cầu có thể được chuyển thành công việc xử lý.</div>}
        {workOrders.map(workOrder => <WorkOrderCard key={workOrder.id} account={account} client={client} workOrder={workOrder}
          technicians={technicians} busy={busy} setBusy={setBusy} setError={setError} setNotice={setNotice} reload={load} commandKeys={commandKeys} />)}
      </section>

      {canTriage && request.status === 'RESOLVED' && <section className="workflow-section workflow-close-request">
        <div><h3>Đóng yêu cầu</h3><p>Chỉ yêu cầu đã giải quyết mới được đóng.</p></div>
        <button className="button-secondary" type="button" disabled={Boolean(busy)} onClick={requestClose}>Đóng yêu cầu</button>
      </section>}
      {notice && <p className="workflow-notice" role="status"><CheckCircle2 size={16} />{notice}</p>}
    </>}
  </div>;
}

export function WorkOrderCard({ account, client, workOrder, technicians, busy, setBusy, setError, setNotice, reload, commandKeys }) {
  const roles = new Set(account.roles || []);
  const isAssignedTechnician = roles.has('technician') && workOrder.assigned_to_id === account.accountId;
  const isLead = roles.has('technical_lead');
  const isCskh = roles.has('cskh');
  const canPerform = isAssignedTechnician;
  const canAddCost = canPerform || isLead;
  const fileRef = useRef(null);
  const [evidence, setEvidence] = useState([]);
  const [costLines, setCostLines] = useState([]);
  const [assigneeId, setAssigneeId] = useState(workOrder.assigned_to_id || '');
  const [checklistResults, setChecklistResults] = useState(() => Object.fromEntries(workOrder.checklist.map(item => [item.id, item.result || ''])));
  const [resultSummary, setResultSummary] = useState(workOrder.result_summary || '');
  const [acceptanceReason, setAcceptanceReason] = useState('');
  const [evidenceId, setEvidenceId] = useState('');
  const [costDescription, setCostDescription] = useState('');
  const [costAmount, setCostAmount] = useState('');
  const [costBearer, setCostBearer] = useState('MANAGEMENT');
  const [costEvidenceId, setCostEvidenceId] = useState('');
  const [reason, setReason] = useState('');

  const loadDetails = useCallback(async signal => {
    const [nextEvidence, nextCosts] = await Promise.all([
      client.listWorkOrderEvidence(workOrder.id, { signal }),
      client.listWorkOrderCostLines(workOrder.id, { signal }),
    ]);
    setEvidence(nextEvidence);
    setCostLines(nextCosts);
    if (!evidenceId && nextEvidence.length) setEvidenceId(nextEvidence[0].id);
  }, [client, evidenceId, workOrder.id]);

  useEffect(() => {
    const controller = new AbortController();
    loadDetails(controller.signal).catch(caught => { if (caught?.name !== 'AbortError') setError(caught); });
    return () => controller.abort();
  }, [loadDetails, workOrder.version]);

  const perform = async (name, callback, message) => {
    setBusy(name);
    setError(null);
    setNotice('');
    try {
      await callback();
      commandKeys.current.delete(name);
      await reload();
      await loadDetails();
      setNotice(message);
      return true;
    } catch (caught) {
      setError(caught);
      return false;
    } finally {
      setBusy('');
    }
  };

  const updateChecklist = (item, completed) => {
    if (completed && !(checklistResults[item.id] || '').trim()) {
      setError(new Error('Ghi kết quả cho mục checklist trước khi đánh dấu hoàn tất.'));
      return;
    }
    return perform(`checklist:${item.id}`, () => client.updateWorkOrderChecklist(workOrder.id, item.id, {
    expected_version: item.version,
    is_completed: completed,
    result: checklistResults[item.id] || null,
    }), 'Đã lưu checklist.');
  };

  const uploadEvidence = async event => {
    const file = event.target.files?.[0];
    if (!file) return;
    const action = `evidence:${workOrder.id}:${file.name}:${file.size}:${file.lastModified}`;
    const completed = await perform(action, () => client.uploadWorkOrderEvidence(workOrder.id, file, {
      idempotencyKey: commandKeys.current.get(action) || (commandKeys.current.set(action, commandKey()), commandKeys.current.get(action)),
    }), 'Đã tải bằng chứng lên.');
    if (completed && fileRef.current) fileRef.current.value = '';
  };

  const submitCost = () => {
    const amount = Number(costAmount);
    if (!Number.isSafeInteger(amount) || amount <= 0) {
      setError(new Error('Nhập số tiền nguyên dương bằng đồng Việt Nam.'));
      return;
    }
    const action = `cost:${workOrder.id}:${costDescription}:${amount}:${costBearer}`;
    return perform(action, () => client.createWorkOrderCostLine(workOrder.id, {
      description: costDescription, amount_vnd: amount, cost_bearer: costBearer,
      evidence_attachment_id: costBearer === 'RESIDENT' ? costEvidenceId : undefined,
    }, { idempotencyKey: commandKeys.current.get(action) || (commandKeys.current.set(action, commandKey()), commandKeys.current.get(action)) }), 'Đã ghi nhận chi phí.');
  };

  const status = workOrder.status;
  return <article className="workflow-order-card">
    <div className="workflow-order-header"><div><span className={`workflow-status workflow-status-${status.toLowerCase()}`}>{STATUS_LABELS[status] || status}</span><h4>{workOrder.code} · {workOrder.title}</h4><p>{workOrder.description}</p></div><span className="workflow-order-version">v{workOrder.version}</span></div>
    <div className="workflow-order-grid">
      <section className="workflow-order-section"><h5>Checklist</h5>
        {workOrder.checklist.map(item => <div className="workflow-checklist-row" key={item.id}>
          <label><input type="checkbox" checked={item.is_completed} disabled={!canPerform || status !== 'IN_PROGRESS' || Boolean(busy)} onChange={event => updateChecklist(item, event.target.checked)} />{item.label}{item.is_required && <span className="workflow-required">Bắt buộc</span>}</label>
          {canPerform && status === 'IN_PROGRESS' && <input aria-label={`Kết quả ${item.label}`} placeholder="Ghi kết quả" value={checklistResults[item.id] || ''} onChange={event => setChecklistResults(previous => ({ ...previous, [item.id]: event.target.value }))} />}
          {item.result && <small>{item.result}</small>}
        </div>)}
      </section>
      <section className="workflow-order-section"><h5>Bằng chứng ảnh</h5>
        <p>{workOrder.evidence_count} tệp được máy chủ ghi nhận.</p>
        {evidence.map(item => <div className="workflow-list-row" key={item.id}><span>{item.original_name}</span><code>{item.id.slice(0, 8)}</code></div>)}
        {canPerform && status === 'IN_PROGRESS' && <label className="workflow-file-button"><Upload size={15} />Tải ảnh<input ref={fileRef} type="file" accept="image/png,image/jpeg" onChange={uploadEvidence} disabled={Boolean(busy)} /></label>}
      </section>
    </div>

    {isLead && ['DRAFT', 'ASSIGNED'].includes(status) && <div className="workflow-action-row"><label>Giao cho kỹ thuật viên<select value={assigneeId} onChange={event => setAssigneeId(event.target.value)}><option value="">Chọn kỹ thuật viên</option>{technicians.map(person => <option value={person.id} key={person.id}>{person.full_name}</option>)}</select></label><button className="button-secondary" type="button" disabled={Boolean(busy) || !assigneeId} onClick={() => perform('assign', () => client.assignWorkOrder(workOrder.id, { assignee_id: assigneeId, expected_version: workOrder.version }), 'Đã phân công Work Order.')}>Phân công</button></div>}
    {canPerform && ['ASSIGNED', 'ON_HOLD'].includes(status) && <button className="button-primary" type="button" disabled={Boolean(busy)} onClick={() => perform('start', () => client.startWorkOrder(workOrder.id, workOrder.version), 'Đã bắt đầu xử lý.')}>Bắt đầu xử lý</button>}

    {canAddCost && ['IN_PROGRESS', 'WAITING_ACCEPTANCE'].includes(status) && <section className="workflow-order-section workflow-cost-section"><h5>Chi phí</h5>
      {costLines.map(line => <div className="workflow-list-row" key={line.id}><span>{line.description} · {line.amount_vnd.toLocaleString('vi-VN')} ₫</span><span>{line.cost_bearer === 'RESIDENT' ? 'Cư dân' : 'Ban quản lý'} · {line.status}</span></div>)}
      <div className="workflow-form-grid"><label>Mô tả<input value={costDescription} onChange={event => setCostDescription(event.target.value)} /></label><label>Số tiền (₫)<input inputMode="numeric" value={costAmount} onChange={event => setCostAmount(event.target.value.replace(/\D/g, ''))} /></label><label>Đơn vị chịu<select value={costBearer} onChange={event => setCostBearer(event.target.value)}><option value="MANAGEMENT">Ban quản lý</option><option value="RESIDENT">Cư dân</option></select></label>
        {costBearer === 'RESIDENT' && <label>Bằng chứng<select value={costEvidenceId} onChange={event => setCostEvidenceId(event.target.value)}><option value="">Chọn ảnh</option>{evidence.map(item => <option key={item.id} value={item.id}>{item.original_name}</option>)}</select></label>}</div>
      <button className="button-secondary" type="button" disabled={Boolean(busy) || costDescription.trim().length < 2 || !costAmount || (costBearer === 'RESIDENT' && !costEvidenceId)} onClick={submitCost}>Ghi nhận chi phí</button>
    </section>}

    {canPerform && status === 'IN_PROGRESS' && <section className="workflow-action-row"><label>Kết quả xử lý<textarea rows={2} value={resultSummary} onChange={event => setResultSummary(event.target.value)} /></label><button className="button-primary" type="button" disabled={Boolean(busy) || resultSummary.trim().length < 3} onClick={() => perform('submit', () => client.submitWorkOrder(workOrder.id, { expected_version: workOrder.version, result_summary: resultSummary }), 'Đã gửi Work Order nghiệm thu.')}>Gửi nghiệm thu</button></section>}

    {status === 'WAITING_ACCEPTANCE' && isCskh && <section className="workflow-action-row"><label>Lý do nghiệm thu thay mặt<input value={acceptanceReason} onChange={event => setAcceptanceReason(event.target.value)} /></label><label>Bằng chứng<select value={evidenceId} onChange={event => setEvidenceId(event.target.value)}><option value="">Chọn ảnh</option>{evidence.map(item => <option key={item.id} value={item.id}>{item.original_name}</option>)}</select></label><button className="button-primary" type="button" disabled={Boolean(busy) || acceptanceReason.trim().length < 3 || !evidenceId} onClick={() => perform('accept-proxy', () => client.acceptWorkOrder(workOrder.id, { expected_version: workOrder.version, mode: 'PROXY', reason: acceptanceReason, evidence_id: evidenceId }), 'Đã nghiệm thu thay mặt cư dân.')}>Nghiệm thu thay mặt</button></section>}
    {status === 'WAITING_ACCEPTANCE' && isLead && <button className="button-primary" type="button" disabled={Boolean(busy)} onClick={() => perform('accept-technical', () => client.acceptWorkOrder(workOrder.id, { expected_version: workOrder.version, mode: 'TECHNICAL' }), 'Đã nghiệm thu kỹ thuật.')}>Nghiệm thu kỹ thuật</button>}
    {status === 'COMPLETED' && (isLead || isCskh) && <button className="button-secondary" type="button" disabled={Boolean(busy)} onClick={() => perform('close-work-order', () => client.closeWorkOrder(workOrder.id, workOrder.version), 'Đã đóng Work Order.')}>Đóng Work Order</button>}
    {isLead && ['CANCELLED', 'CLOSED'].includes(status) && <div className="workflow-action-row"><label>Lý do mở lại<input value={reason} onChange={event => setReason(event.target.value)} /></label><button className="button-secondary" type="button" disabled={Boolean(busy) || reason.trim().length < 3} onClick={() => perform('reopen', () => client.reopenWorkOrder(workOrder.id, { expected_version: workOrder.version, reason }), 'Đã mở lại Work Order.')}>Mở lại</button></div>}
    {isLead && ['DRAFT', 'ASSIGNED'].includes(status) && <div className="workflow-action-row"><label>Lý do hủy<input value={reason} onChange={event => setReason(event.target.value)} /></label><button className="button-text" type="button" disabled={Boolean(busy) || reason.trim().length < 3} onClick={() => perform('cancel', () => client.cancelWorkOrder(workOrder.id, { expected_version: workOrder.version, reason }), 'Đã hủy Work Order.')}>Hủy Work Order</button></div>}
  </article>;
}
