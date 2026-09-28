import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Activity, CalendarClock, ClipboardList, Plus, RefreshCw, Wrench } from 'lucide-react';
import { WorkOrderCard } from './WorkOrderWorkspace';
import './MaintenanceDesktopView.css';

const OCCURRENCE_LABELS = { DUE: 'Đến hạn', WO_CREATED: 'Đã tạo việc', IN_PROGRESS: 'Đang xử lý', COMPLETED: 'Hoàn tất', DEFERRED: 'Đã hoãn', CANCELLED: 'Đã hủy' };
const nowForInput = () => {
  const date = new Date(Date.now() + 86_400_000);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
};
const localDateTimeToIso = value => new Date(value).toISOString();
const messageFor = error => error?.message || 'Máy chủ chưa thể xử lý yêu cầu.';

export function MaintenanceDesktopView({ account, client }) {
  const isTechnician = account.roles?.includes('technician');
  const isLead = account.roles?.includes('technical_lead');
  const commandKeys = useRef(new Map());
  const [buildings, setBuildings] = useState([]);
  const [buildingId, setBuildingId] = useState('');
  const [assets, setAssets] = useState([]);
  const [assetId, setAssetId] = useState('');
  const [plans, setPlans] = useState([]);
  const [occurrences, setOccurrences] = useState([]);
  const [history, setHistory] = useState([]);
  const [assignedWorkOrders, setAssignedWorkOrders] = useState([]);
  const [selectedWorkOrder, setSelectedWorkOrder] = useState(null);
  const [technicians, setTechnicians] = useState([]);
  const [assetCode, setAssetCode] = useState('');
  const [assetName, setAssetName] = useState('');
  const [assetDescription, setAssetDescription] = useState('');
  const [planCode, setPlanCode] = useState('');
  const [planTitle, setPlanTitle] = useState('');
  const [intervalDays, setIntervalDays] = useState('30');
  const [nextDueAt, setNextDueAt] = useState(nowForInput);
  const [planChecklist, setPlanChecklist] = useState('Kiểm tra thiết bị\nGhi nhận kết quả\nXác nhận vận hành');
  const [evidenceRequired, setEvidenceRequired] = useState(true);
  const [deferId, setDeferId] = useState('');
  const [deferUntil, setDeferUntil] = useState(nowForInput);
  const [deferReason, setDeferReason] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState('');

  const loadTechnician = useCallback(async signal => {
    const items = await client.listAssignedMaintenanceWorkOrders({ signal });
    setAssignedWorkOrders(items);
    if (selectedWorkOrder?.id) {
      const updated = items.find(item => item.id === selectedWorkOrder.id);
      if (updated) setSelectedWorkOrder(updated);
    }
  }, [client, selectedWorkOrder?.id]);

  const loadLead = useCallback(async (requestedBuildingId = buildingId, signal) => {
    if (!requestedBuildingId) {
      setAssets([]); setOccurrences([]); setPlans([]); setHistory([]); setAssetId('');
      return;
    }
    const [nextAssets, nextOccurrences] = await Promise.all([
      client.listMaintenanceAssets(requestedBuildingId, { signal }),
      client.listMaintenanceOccurrences(requestedBuildingId, { signal }),
    ]);
    setAssets(nextAssets);
    setOccurrences(nextOccurrences.items);
    const selected = nextAssets.find(item => item.id === assetId) || nextAssets[0];
    setAssetId(selected?.id || '');
    if (selected) {
      const [nextPlans, nextHistory] = await Promise.all([
        client.listMaintenancePlans(selected.id, { signal }),
        client.getMaintenanceHistory(selected.id, { signal }),
      ]);
      setPlans(nextPlans);
      setHistory(nextHistory.items);
    } else {
      setPlans([]); setHistory([]);
    }
    if (selectedWorkOrder?.id) {
      const [updated, nextTechnicians] = await Promise.all([
        client.getWorkOrder(selectedWorkOrder.id, { signal }),
        client.listWorkOrderAssignees(selectedWorkOrder.id, { signal }),
      ]);
      setSelectedWorkOrder(updated);
      setTechnicians(nextTechnicians);
    }
  }, [assetId, buildingId, client, selectedWorkOrder?.id]);

  const refresh = useCallback(async signal => {
    setError(null);
    if (isTechnician && !isLead) return loadTechnician(signal);
    return loadLead(buildingId, signal);
  }, [buildingId, isLead, isTechnician, loadLead, loadTechnician]);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const loadPage = async () => {
      setLoading(true);
      try {
        if (isTechnician && !isLead) await loadTechnician(controller.signal);
        else {
          const options = await client.listMaintenanceBuildings({ signal: controller.signal });
          if (!active) return;
          setBuildings(options);
          if (options.length) setBuildingId(current => current || options[0].id);
          else setLoading(false);
        }
      } catch (caught) {
        if (caught?.name !== 'AbortError' && active) setError(caught);
      } finally {
        if (active) setLoading(false);
      }
    };
    loadPage();
    return () => { active = false; controller.abort(); };
  }, [client, isLead, isTechnician, loadTechnician]);

  useEffect(() => {
    if (!isLead || !buildingId) return undefined;
    const controller = new AbortController();
    setLoading(true);
    loadLead(buildingId, controller.signal)
      .catch(caught => { if (caught?.name !== 'AbortError') setError(caught); })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [buildingId, isLead, loadLead]);

  const actionKey = name => {
    if (!commandKeys.current.has(name)) commandKeys.current.set(name, globalThis.crypto.randomUUID());
    return commandKeys.current.get(name);
  };

  const perform = async (name, callback, successText) => {
    setBusy(name);
    setError(null);
    setNotice('');
    try {
      const result = await callback();
      await refresh();
      commandKeys.current.delete(name);
      setNotice(successText);
      return result;
    } catch (caught) {
      setError(caught);
      return null;
    } finally {
      setBusy('');
    }
  };

  const createAsset = async () => {
    if (!buildingId) return;
    const name = 'create-asset';
    const created = await perform(name, () => client.createMaintenanceAsset({
      building_id: buildingId, code: assetCode, name: assetName, description: assetDescription,
    }, { idempotencyKey: actionKey(name) }), 'Đã tạo Asset.');
    if (created) {
      setAssetCode(''); setAssetName(''); setAssetDescription(''); setAssetId(created.id);
    }
  };

  const createPlan = async () => {
    const checklist = planChecklist.split(/\r?\n/).map(label => label.trim()).filter(Boolean).map(label => ({ label, required: true }));
    if (!assetId || checklist.length === 0) {
      setError(new Error('Chọn Asset và thêm ít nhất một mục checklist.'));
      return;
    }
    const name = `create-plan:${assetId}:${planCode}`;
    const created = await perform(name, () => client.createMaintenancePlan({
      asset_id: assetId, code: planCode, title: planTitle, interval_days: Number(intervalDays),
      next_due_at: localDateTimeToIso(nextDueAt), checklist, evidence_required: evidenceRequired,
    }, { idempotencyKey: actionKey(name) }), 'Đã tạo Maintenance Plan.');
    if (created) { setPlanCode(''); setPlanTitle(''); }
  };

  const runScheduler = () => {
    const asOf = new Date().toISOString();
    const name = `scheduler:${buildingId}:${asOf}`;
    return perform(name, () => client.runMaintenanceScheduler(asOf, { idempotencyKey: actionKey(name) }), 'Đã chạy scheduler; occurrence và Work Order đã được đọc lại từ máy chủ.');
  };

  const openWorkOrder = async workOrderId => {
    setBusy('load-work-order'); setError(null); setNotice('');
    try {
      const [workOrder, assignees] = await Promise.all([
        client.getWorkOrder(workOrderId),
        isLead ? client.listWorkOrderAssignees(workOrderId) : Promise.resolve([]),
      ]);
      setSelectedWorkOrder(workOrder); setTechnicians(assignees);
    } catch (caught) { setError(caught); }
    finally { setBusy(''); }
  };

  const deferOccurrence = occurrence => perform(`defer:${occurrence.id}`, () => client.deferMaintenanceOccurrence(occurrence.id, {
    expected_version: occurrence.version,
    defer_until: localDateTimeToIso(deferUntil),
    reason: deferReason,
  }), 'Đã hoãn occurrence.');

  const selectAsset = async id => {
    setAssetId(id);
    if (!id) { setPlans([]); setHistory([]); return; }
    setError(null);
    try {
      const [nextPlans, nextHistory] = await Promise.all([client.listMaintenancePlans(id), client.getMaintenanceHistory(id)]);
      setPlans(nextPlans); setHistory(nextHistory.items);
    } catch (caught) { setError(caught); }
  };

  const selectedAsset = useMemo(() => assets.find(asset => asset.id === assetId) || null, [assetId, assets]);

  if (isTechnician && !isLead) return <div className="desktop-page maintenance-page">
    <div className="page-heading"><div><p className="eyebrow">Kỹ thuật · Công việc được giao</p><h1>Bảo trì của tôi</h1><p>Chỉ hiển thị Work Order bảo trì được máy chủ giao cho phiên hiện tại.</p></div></div>
    {loading && <p role="status">Đang tải Work Order bảo trì…</p>}
    {error && <p className="maintenance-error" role="alert">{messageFor(error)}</p>}
    {!loading && assignedWorkOrders.length === 0 && <section className="surface maintenance-empty"><Wrench size={28} /><h2>Chưa có Work Order bảo trì được giao</h2><p>Khi trưởng kỹ thuật phân công công việc, hồ sơ sẽ xuất hiện tại đây.</p></section>}
    <div className="maintenance-work-list">{assignedWorkOrders.map(item => <section className="surface maintenance-work-card" key={item.id}>
      <div><span className={`maintenance-status maintenance-status-${item.status.toLowerCase()}`}>{item.status}</span><h2>{item.code} · {item.title}</h2><p>{item.description}</p></div>
      <button className="button-secondary" type="button" onClick={() => openWorkOrder(item.id)}>Mở Work Order</button>
      {selectedWorkOrder?.id === item.id && <WorkOrderCard account={account} client={client} workOrder={selectedWorkOrder} technicians={[]}
        busy={busy} setBusy={setBusy} setError={setError} setNotice={setNotice} reload={refresh} commandKeys={commandKeys} />}
    </section>)}</div>
    {notice && <p className="maintenance-notice" role="status">{notice}</p>}
  </div>;

  return <div className="desktop-page maintenance-page">
    <div className="page-heading"><div><p className="eyebrow">Tài sản · Kế hoạch · Lịch sử</p><h1>Kỹ thuật & Bảo trì</h1><p>Tạo kế hoạch bảo trì, sinh Work Order và theo dõi lịch sử nghiệm thu theo tòa nhà được cấp.</p></div><button className="button-primary" type="button" onClick={runScheduler} disabled={Boolean(busy) || !buildingId}><RefreshCw size={16} />Chạy scheduler</button></div>
    <section className="surface maintenance-toolbar"><label>Tòa nhà<select value={buildingId} onChange={event => { setBuildingId(event.target.value); setAssetId(''); setSelectedWorkOrder(null); }}><option value="">Chọn tòa nhà</option>{buildings.map(item => <option key={item.id} value={item.id}>{item.code} · {item.name}</option>)}</select></label><span>Site hiện tại · {account.site}</span></section>
    {loading && <p role="status">Đang tải Asset, kế hoạch và occurrence…</p>}
    {error && <p className="maintenance-error" role="alert">{messageFor(error)}</p>}
    {!loading && buildings.length === 0 && <section className="surface maintenance-empty"><Wrench size={28} /><h2>Chưa có tòa nhà kỹ thuật được cấp</h2><p>Kiểm tra role và building grant của tài khoản trên máy chủ.</p></section>}
    {buildingId && <div className="maintenance-grid">
      <section className="surface maintenance-panel">
        <div className="maintenance-panel-heading"><div><h2>Assets</h2><p>{assets.length} thiết bị trong phạm vi tòa nhà.</p></div><span className="maintenance-count">{selectedAsset?.status || '—'}</span></div>
        <div className="maintenance-asset-list">{assets.map(asset => <button key={asset.id} className={`maintenance-asset ${asset.id === assetId ? 'is-selected' : ''}`} onClick={() => selectAsset(asset.id)}><span><strong>{asset.code}</strong><small>{asset.name}</small></span><span aria-hidden="true">›</span></button>)}{assets.length === 0 && <p className="maintenance-empty-copy">Chưa có Asset. Tạo thiết bị để bắt đầu lập kế hoạch.</p>}</div>
        <div className="maintenance-form"><h3><Plus size={16} />Tạo Asset</h3><label>Mã Asset<input value={assetCode} onChange={event => setAssetCode(event.target.value.toUpperCase())} maxLength={50} /></label><label>Tên thiết bị<input value={assetName} onChange={event => setAssetName(event.target.value)} maxLength={200} /></label><label>Mô tả<textarea value={assetDescription} onChange={event => setAssetDescription(event.target.value)} rows={2} maxLength={4000} /></label><button className="button-secondary" type="button" disabled={Boolean(busy) || !buildingId || assetCode.trim().length < 2 || assetName.trim().length < 2} onClick={createAsset}>Tạo Asset</button></div>
      </section>

      <section className="surface maintenance-panel">
        <div className="maintenance-panel-heading"><div><h2>Maintenance Plan</h2><p>{selectedAsset ? `${selectedAsset.code} · ${plans.length} kế hoạch` : 'Chọn Asset để xem hoặc tạo kế hoạch.'}</p></div><CalendarClock size={20} /></div>
        {plans.map(plan => <div className="maintenance-plan-row" key={plan.id}><span><strong>{plan.code} · {plan.title}</strong><small>Mỗi {plan.interval_days} ngày · đến hạn {new Date(plan.next_due_at).toLocaleDateString('vi-VN')}</small></span><span className={plan.is_active ? 'maintenance-active' : 'maintenance-inactive'}>{plan.is_active ? 'Đang hoạt động' : 'Đã dừng'}</span></div>)}
        {selectedAsset && <div className="maintenance-form"><h3><Plus size={16} />Tạo kế hoạch</h3><div className="maintenance-form-grid"><label>Mã kế hoạch<input value={planCode} onChange={event => setPlanCode(event.target.value.toUpperCase())} maxLength={50} /></label><label>Chu kỳ (ngày)<input type="number" min="1" max="3650" value={intervalDays} onChange={event => setIntervalDays(event.target.value)} /></label><label className="maintenance-form-wide">Tên kế hoạch<input value={planTitle} onChange={event => setPlanTitle(event.target.value)} maxLength={200} /></label><label className="maintenance-form-wide">Lần bảo trì kế tiếp<input type="datetime-local" value={nextDueAt} onChange={event => setNextDueAt(event.target.value)} /></label><label className="maintenance-form-wide">Checklist, mỗi dòng một mục<textarea rows={3} value={planChecklist} onChange={event => setPlanChecklist(event.target.value)} /></label></div><label className="maintenance-check"><input type="checkbox" checked={evidenceRequired} onChange={event => setEvidenceRequired(event.target.checked)} />Bắt buộc ảnh trước khi gửi nghiệm thu</label><button className="button-secondary" type="button" disabled={Boolean(busy) || !assetId || planCode.trim().length < 2 || planTitle.trim().length < 3 || !nextDueAt} onClick={createPlan}>Tạo Maintenance Plan</button></div>}
      </section>

      <section className="surface maintenance-panel maintenance-occurrences">
        <div className="maintenance-panel-heading"><div><h2>Occurrence & Work Order</h2><p>{occurrences.length} lịch sử phát sinh trong tòa nhà.</p></div><Activity size={20} /></div>
        {occurrences.length === 0 ? <p className="maintenance-empty-copy">Chưa có occurrence. Tạo plan đến hạn rồi chạy scheduler.</p> : <div className="maintenance-occurrence-list">{occurrences.map(item => <div className="maintenance-occurrence-row" key={item.id}>
          <div><span className={`maintenance-status maintenance-status-${item.status.toLowerCase()}`}>{OCCURRENCE_LABELS[item.status] || item.status}</span><strong>Đến hạn {new Date(item.due_at).toLocaleString('vi-VN')}</strong><small>Occurrence {item.id.slice(0, 8)} · Asset {item.asset_id.slice(0, 8)}</small>{item.defer_reason && <small>Lý do hoãn: {item.defer_reason}</small>}</div>
          {item.work_order_id && <button className="button-secondary" type="button" onClick={() => openWorkOrder(item.work_order_id)}>Mở Work Order</button>}
          {['DUE', 'WO_CREATED'].includes(item.status) && <button className="button-text" type="button" onClick={() => setDeferId(deferId === item.id ? '' : item.id)}>Hoãn lịch</button>}
          {deferId === item.id && <div className="maintenance-defer-form"><label>Thời điểm mới<input type="datetime-local" value={deferUntil} onChange={event => setDeferUntil(event.target.value)} /></label><label>Lý do<input value={deferReason} onChange={event => setDeferReason(event.target.value)} /></label><button className="button-secondary" disabled={Boolean(busy) || deferReason.trim().length < 3} onClick={() => deferOccurrence(item)}>Lưu hoãn</button></div>}
        </div>)}</div>}
        {selectedWorkOrder && <div className="maintenance-work-detail"><div className="maintenance-panel-heading"><div><h3>{selectedWorkOrder.code} · {selectedWorkOrder.title}</h3><p>Occurrence liên kết {selectedWorkOrder.maintenance_occurrence_id?.slice(0, 8)}</p></div><button className="button-text" type="button" onClick={() => setSelectedWorkOrder(null)}>Đóng</button></div><WorkOrderCard account={account} client={client} workOrder={selectedWorkOrder} technicians={technicians}
          busy={busy} setBusy={setBusy} setError={setError} setNotice={setNotice} reload={refresh} commandKeys={commandKeys} /></div>}
      </section>

      {selectedAsset && <section className="surface maintenance-panel maintenance-history"><div className="maintenance-panel-heading"><div><h2>Lịch sử Asset</h2><p>{selectedAsset.code} · {history.length} lần nghiệm thu</p></div><ClipboardList size={20} /></div>{history.length === 0 ? <p className="maintenance-empty-copy">Chưa có lịch sử nghiệm thu cho Asset này.</p> : history.map(item => <div className="maintenance-history-row" key={item.id}><span><strong>{new Date(item.completed_at).toLocaleString('vi-VN')}</strong><small>{item.result_summary}</small></span><code>WO {item.work_order_id.slice(0, 8)}</code></div>)}</section>}
    </div>}
    {notice && <p className="maintenance-notice" role="status">{notice}</p>}
  </div>;
}
