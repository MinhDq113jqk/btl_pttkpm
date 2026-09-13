import React from 'react';
import { ArrowRight, CheckSquare, Clock, MapPin, ShieldCheck } from 'lucide-react';
import { StatusBadge } from '../TasksDesktopView';

export function SessionDashboard({ account, items, total, loading, onNavigate, onSelectTask, onFilterTasks }) {
  const inProgress = items.filter(item => item.apiStatus === 'IN_PROGRESS').length;
  const waiting = items.filter(item => item.apiStatus === 'WAITING_INFO').length;
  const overdue = items.filter(item => item.isOverdue).length;
  const metrics = [
    { label: 'Tổng yêu cầu', value: total, status: 'all' },
    { label: 'Đang xử lý trong trang', value: inProgress, status: 'IN_PROGRESS' },
    { label: 'Chờ thông tin trong trang', value: waiting, status: 'WAITING_INFO' },
    { label: 'Quá SLA trong trang', value: overdue, status: 'all' },
  ];
  const attention = [...items].sort((a, b) => Number(b.isOverdue) - Number(a.isOverdue) || a.deadlineOrder - b.deadlineOrder).slice(0, 5);

  return <div className="desktop-page staff-dashboard">
    <div className="page-heading"><div><p className="eyebrow">Không gian {account.label}</p><h1>{account.title}</h1><p>Xin chào {account.name}. {account.summary}</p></div><span className="staff-permission-pill"><ShieldCheck size={15} aria-hidden="true" />Theo quyền máy chủ cấp</span></div>
    <section className="staff-scope-banner"><div><MapPin size={20} aria-hidden="true" /><div><span>Phạm vi đang làm việc</span><strong>{account.scope}</strong></div></div>{account.canViewServiceRequests && <button className="button-primary" onClick={() => onNavigate('tasks')}>Mở danh sách yêu cầu<ArrowRight size={16} aria-hidden="true" /></button>}</section>
    {account.canViewServiceRequests ? <>
      <div className="metric-grid staff-metrics" aria-busy={loading}>{metrics.map(metric => <button className="metric-card" key={metric.label} onClick={() => onFilterTasks(metric.status)} disabled={loading}><span className="metric-label">{metric.label}</span><strong>{loading ? '—' : metric.value}</strong><span className="metric-link">Mở danh sách<ArrowRight size={14} aria-hidden="true" /></span></button>)}</div>
      <section className="surface"><div className="section-heading"><div><h2>Ưu tiên trong phạm vi của bạn</h2><p>Dữ liệu từ trang yêu cầu hiện tại, sắp theo hạn SLA.</p></div><button className="button-text" onClick={() => onNavigate('tasks')}>Xem tất cả<ArrowRight size={16} aria-hidden="true" /></button></div>
        <div className="attention-list">{attention.map(item => <button className="attention-task" key={item.recordId} onClick={() => onSelectTask(item)}><div><span className="task-code">{item.id}</span><h3>{item.title}</h3><p>{item.location}</p></div><div className="attention-task-meta"><StatusBadge task={item} /><span className={item.isOverdue ? 'deadline-overdue' : ''}>{item.deadline}</span></div></button>)}{!loading && !attention.length && <div className="empty-state"><CheckSquare size={28} aria-hidden="true" /><h3>Chưa có yêu cầu trong phạm vi</h3><p>Danh sách sẽ cập nhật khi máy chủ có dữ liệu bạn được phép xem.</p></div>}{loading && <div className="empty-state" role="status"><Clock size={28} aria-hidden="true" /><h3>Đang tải dữ liệu</h3><p>Máy chủ đang xác định phạm vi yêu cầu của phiên.</p></div>}</div>
      </section>
    </> : <section className="surface empty-state"><ShieldCheck size={34} aria-hidden="true" /><h2>Chưa có danh sách nghiệp vụ cho vai trò này</h2><p>Phiên đã xác thực, nhưng backend hiện chưa cấp endpoint công việc phù hợp. Frontend không gọi Service Request thay cho một module khác.</p></section>}
    <p className="context-note staff-note"><strong>Giới hạn phiên</strong>{account.restricted}</p>
  </div>;
}
