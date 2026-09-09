import React from 'react';
import { ArrowRight, AlertTriangle, Briefcase, Clock, CheckSquare } from 'lucide-react';
import { tasks as defaultTasks } from '../data/desktopData';
import { StatusBadge } from './TasksDesktopView';

export const DashboardView = ({ onSelectTask, onViewAll, onFilterTasks, tasks = defaultTasks }) => {
  const pending = tasks.filter(task => task.status === 'Chờ duyệt').length;
  const overdue = tasks.filter(task => task.status === 'Quá hạn').length;
  const metrics = [
    { label: 'Tổng công việc', count: tasks.length, status: 'all', Icon: Briefcase, color: 'emerald' },
    { label: 'Đang xử lý', count: tasks.filter(task => task.status === 'Đang xử lý').length, status: 'Đang xử lý', Icon: CheckSquare, color: 'blue' },
    { label: 'Chờ duyệt', count: pending, status: 'Chờ duyệt', Icon: Clock, color: 'amber' },
    { label: 'Quá hạn', count: overdue, status: 'Quá hạn', Icon: AlertTriangle, color: 'rose' },
  ];
  const attention = [...tasks].filter(task => task.status !== 'Đang xử lý').sort((a, b) => a.deadlineOrder - b.deadlineOrder);
  return <div className="desktop-page dashboard-page">
    <div className="page-heading"><div><p className="eyebrow">GreenCity Central</p><h1>Tổng quan điều hành</h1><p>Tập trung vào công việc cần quyết định và xử lý tiếp theo.</p></div><span className="subtle-badge">Ban quản lý khu đô thị</span></div>
    <section className="attention-banner"><div><p>Ưu tiên xử lý</p><h2>{overdue} việc quá hạn · {pending} hồ sơ chờ duyệt</h2><span>Kiểm tra công việc quá hạn trước, sau đó rà soát các hồ sơ chờ duyệt.</span></div><button className="button-light" onClick={() => onFilterTasks('Quá hạn')}>Xem việc quá hạn<ArrowRight size={18} aria-hidden="true" /></button></section>
    <div className="metric-grid">{metrics.map(({ label, count, status, Icon, color }) => <button key={label} className="metric-card" onClick={() => onFilterTasks(status)}><span className="metric-label">{label}<span className={`metric-icon status-${color}`}><Icon size={19} aria-hidden="true" /></span></span><strong>{count}</strong><span className="metric-link">Mở danh sách <ArrowRight size={14} aria-hidden="true" /></span></button>)}</div>
    <div className="overview-grid">
      <section className="surface"><div className="section-heading"><div><h2>Cần chú ý</h2><p>Quá hạn trước, sau đó theo hạn xử lý.</p></div><button className="button-text" onClick={onViewAll}>Xem tất cả<ArrowRight size={16} aria-hidden="true" /></button></div>
        <div className="attention-list">{attention.map(task => <button className="attention-task" key={task.id} onClick={() => onSelectTask(task)}><div><span className="task-code">{task.id}</span><h3>{task.title}</h3><p>{task.location}</p></div><div className="attention-task-meta"><StatusBadge task={task} /><span className={task.statusColor === 'rose' ? 'deadline-overdue' : ''}>{task.deadline}</span></div></button>)}</div>
      </section>
      <section className="surface department-panel"><div className="section-heading"><div><h2>Phân bổ công việc</h2><p>{tasks.length} công việc trong bộ dữ liệu mẫu.</p></div></div><div className="department-list">{['Kỹ thuật', 'Vệ sinh', 'An ninh', 'Tài chính'].map(department => { const count = tasks.filter(task => task.department === department).length; return <div key={department}><div><span>{department}</span><strong>{count} việc</strong></div><meter min="0" max={tasks.length} value={count} aria-label={`${department}: ${count} trên ${tasks.length} công việc`} /></div>; })}</div><div className="context-note"><strong>Phạm vi dữ liệu</strong><p>Số đếm được tính từ danh sách công việc, không phải chỉ số vận hành trực tiếp.</p></div></section>
    </div>
  </div>;
};
