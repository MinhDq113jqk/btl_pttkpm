import React from 'react';
import { Search, ArrowDown, ArrowUp, ArrowUpRight, ListFilter } from 'lucide-react';
import { tasks, filterTasks } from '../data/desktopData';

export const StatusBadge = ({ task }) => <span className={`status-badge status-${task.statusColor}`}>{task.status}</span>;

export function TasksDesktopView({ filters, onFiltersChange, onSelectTask }) {
  const { query, status, department, sort } = filters;
  const set = change => onFiltersChange({ ...filters, ...change });
  const filtered = filterTasks(tasks, query, status, department).sort((a, b) => sort === 'asc' ? a.deadlineOrder - b.deadlineOrder : b.deadlineOrder - a.deadlineOrder);
  const reset = () => onFiltersChange({ query: '', status: 'all', department: 'all', sort: 'asc' });
  return <div className="desktop-page">
    <div className="page-heading"><div><p className="eyebrow">Điều phối vận hành</p><h1>Công việc & Yêu cầu</h1><p>Theo dõi hạn xử lý và mở hồ sơ từ một danh sách.</p></div><span className="subtle-badge">{tasks.length} công việc mẫu</span></div>
    <section className="surface task-workspace" aria-label="Danh sách công việc">
      <div className="status-filters" aria-label="Lọc trạng thái">
        {['all', 'Đang xử lý', 'Chờ duyệt', 'Quá hạn'].map(value => <button key={value} onClick={() => set({ status: value })} aria-pressed={status === value} className={status === value ? 'is-selected' : ''}>{value === 'all' ? 'Tất cả' : value}<span>{value === 'all' ? tasks.length : tasks.filter(t => t.status === value).length}</span></button>)}
      </div>
      <div className="table-toolbar">
        <div className="search-field"><Search size={17} aria-hidden="true" /><input aria-label="Tìm trong danh sách công việc" placeholder="Tìm mã, tên hoặc vị trí…" value={query} onChange={e => set({ query: e.target.value })} /></div>
        <label className="inline-field"><span>Bộ phận</span><select value={department} onChange={e => set({ department: e.target.value })}><option value="all">Tất cả bộ phận</option>{['Kỹ thuật', 'Vệ sinh', 'An ninh', 'Tài chính'].map(item => <option key={item}>{item}</option>)}</select></label>
        <button className="button-text" onClick={reset} disabled={!query && status === 'all' && department === 'all'}>Xóa bộ lọc</button>
      </div>
      <div className="table-scroll" role="region" aria-label="Bảng công việc, có thể cuộn ngang" tabIndex={0}>
        <table className="tasks-table"><caption className="sr-only">Công việc minh họa tại GreenCity Central</caption>
          <thead><tr><th scope="col">Công việc / Vị trí</th><th scope="col">Bộ phận</th><th scope="col">Trạng thái</th><th scope="col" aria-sort={sort === 'asc' ? 'ascending' : 'descending'}><button onClick={() => set({ sort: sort === 'asc' ? 'desc' : 'asc' })}>Hạn xử lý {sort === 'asc' ? <ArrowDown size={14} aria-hidden="true" /> : <ArrowUp size={14} aria-hidden="true" />}</button></th><th scope="col"><span className="sr-only">Thao tác</span></th></tr></thead>
          <tbody>{filtered.map(task => <tr key={task.id}>
            <td><button className="task-title" onClick={() => onSelectTask(task)}>{task.title}</button><p className="task-meta"><span>{task.id}</span> · {task.location}</p></td>
            <td>{task.department}</td><td><StatusBadge task={task} /></td><td className={task.statusColor === 'rose' ? 'deadline-overdue' : ''}>{task.deadline}</td>
            <td><button className="icon-button" aria-label={`Mở công việc ${task.id}`} title="Mở chi tiết" onClick={() => onSelectTask(task)}><ArrowUpRight size={18} aria-hidden="true" /></button></td>
          </tr>)}</tbody>
        </table>
      </div>
      {filtered.length === 0 && <div className="empty-state"><ListFilter size={30} aria-hidden="true" /><h2>Không có công việc phù hợp</h2><p>Thử đổi từ khóa hoặc xóa bộ lọc để xem toàn bộ danh sách.</p><button className="button-secondary" onClick={reset}>Hiển thị tất cả công việc</button></div>}
      <div className="table-footer" role="status">Hiển thị {filtered.length} / {tasks.length} công việc<span>Dữ liệu mẫu · Chưa kết nối máy chủ</span></div>
    </section>
  </div>;
}
