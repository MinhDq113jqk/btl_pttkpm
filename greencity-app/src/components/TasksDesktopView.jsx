import React from 'react';
import { AlertCircle, ArrowDown, ArrowUp, ArrowUpRight, ChevronLeft, ChevronRight, ListFilter, LoaderCircle, RefreshCw, Search } from 'lucide-react';
import { normalizeSearch } from '../data/desktopData';
import { SERVICE_REQUEST_STATUSES } from '../data/serviceRequestView';

export const StatusBadge = ({ task }) => <span className={`status-badge status-${task.statusColor}`}>{task.status}</span>;

const errorCopy = error => {
  if (error?.code === 'ERR-SCOPE-NOTFOUND') return {
    title: 'Chưa xác định được phạm vi dữ liệu',
    message: 'Máy chủ không tìm thấy site hoặc tòa nhà mà phiên hiện tại được phép xem. Hãy liên hệ quản trị viên nếu lỗi tiếp diễn.',
  };
  if (error?.code === 'ERR-NETWORK') return {
    title: 'Mất kết nối tới máy chủ',
    message: 'Danh sách chưa được cập nhật. Kiểm tra mạng hoặc trạng thái backend rồi thử lại.',
  };
  return { title: 'Không tải được danh sách yêu cầu', message: error?.message || 'Máy chủ chưa thể trả dữ liệu. Vui lòng thử lại.' };
};

export function TasksDesktopView({
  filters = { query: '', status: 'all', sort: 'asc' },
  onFiltersChange,
  onSelectTask,
  tasks = [],
  title = 'Công việc & Yêu cầu',
  scopeLabel = 'Phạm vi hiện tại',
  loading = false,
  error = null,
  onRetry,
  pagination = { page: 1, pageSize: 20, total: tasks.length },
  onPageChange,
}) {
  const { query = '', status = 'all', sort = 'asc' } = filters;
  const set = change => onFiltersChange?.({ ...filters, ...change });
  const normalizedQuery = normalizeSearch(query);
  const filtered = tasks
    .filter(task => !normalizedQuery || normalizeSearch(`${task.id} ${task.recordId} ${task.title} ${task.location}`).includes(normalizedQuery))
    .filter(task => status === 'all' || task.apiStatus === status)
    .sort((a, b) => sort === 'asc' ? a.deadlineOrder - b.deadlineOrder : b.deadlineOrder - a.deadlineOrder);
  const reset = () => onFiltersChange?.({ query: '', status: 'all', sort: 'asc' });
  const errorMessage = errorCopy(error);
  const pageCount = Math.max(1, Math.ceil(pagination.total / pagination.pageSize));
  const hasFilters = Boolean(query) || status !== 'all';

  return <div className="desktop-page">
    <div className="page-heading"><div><p className="eyebrow">Điều phối vận hành</p><h1>{title}</h1><p>{scopeLabel} · Dữ liệu đọc từ máy chủ theo quyền của phiên.</p></div><span className="subtle-badge">{pagination.total} yêu cầu</span></div>
    <section className="surface task-workspace" aria-label="Danh sách yêu cầu dịch vụ" aria-busy={loading}>
      <div className="status-filters" aria-label="Lọc trạng thái">
        {SERVICE_REQUEST_STATUSES.map(option => <button key={option.value} onClick={() => set({ status: option.value })} aria-pressed={status === option.value} className={status === option.value ? 'is-selected' : ''}>{option.label}{option.value === 'all' && <span>{pagination.total}</span>}</button>)}
      </div>
      <div className="table-toolbar">
        <div className="search-field"><Search size={17} aria-hidden="true" /><input aria-label="Tìm trong trang yêu cầu hiện tại" placeholder="Tìm mã, tiêu đề, căn hộ hoặc tòa nhà…" value={query} onChange={event => set({ query: event.target.value })} /></div>
        <button className="button-text" onClick={reset} disabled={!hasFilters}>Xóa bộ lọc</button>
      </div>

      {loading && <div className="request-state request-loading" role="status"><LoaderCircle className="request-spinner" size={20} aria-hidden="true" /><span>Đang tải yêu cầu đúng phạm vi…</span></div>}
      {error && <div className="request-state request-error" role="alert"><AlertCircle size={22} aria-hidden="true" /><div><strong>{errorMessage.title}</strong><p>{errorMessage.message}</p>{error.correlationId && <small>Mã đối chiếu: {error.correlationId}</small>}</div><button className="button-secondary" type="button" onClick={onRetry}><RefreshCw size={16} aria-hidden="true" />Thử lại</button></div>}

      {!loading && !error && filtered.length === 0 && <div className="empty-state"><ListFilter size={30} aria-hidden="true" /><h2>{hasFilters ? 'Không có yêu cầu phù hợp' : 'Chưa có yêu cầu trong phạm vi'}</h2><p>{hasFilters ? 'Thử đổi từ khóa hoặc xóa bộ lọc. Bộ lọc trạng thái được áp dụng tại máy chủ.' : 'Khi có yêu cầu thuộc site hoặc tòa nhà được cấp, danh sách sẽ xuất hiện tại đây.'}</p>{hasFilters && <button className="button-secondary" onClick={reset}>Hiển thị tất cả yêu cầu</button>}</div>}

      {filtered.length > 0 && <div className="table-scroll" role="region" aria-label="Bảng yêu cầu dịch vụ, có thể cuộn ngang" tabIndex={0}>
        <table className="tasks-table"><caption className="sr-only">Yêu cầu dịch vụ trong phạm vi phiên hiện tại</caption>
          <thead><tr><th scope="col">Yêu cầu / Vị trí</th><th scope="col">Trạng thái</th><th scope="col">Ưu tiên</th><th scope="col">Thời điểm tạo</th><th scope="col" aria-sort={sort === 'asc' ? 'ascending' : 'descending'}><button onClick={() => set({ sort: sort === 'asc' ? 'desc' : 'asc' })}>SLA / Hạn xử lý {sort === 'asc' ? <ArrowDown size={14} aria-hidden="true" /> : <ArrowUp size={14} aria-hidden="true" />}</button></th><th scope="col"><span className="sr-only">Thao tác</span></th></tr></thead>
          <tbody>{filtered.map(task => <tr key={task.recordId}>
            <td><button className="task-title" onClick={() => onSelectTask(task)}>{task.title}</button><p className="task-meta"><span>{task.id}</span> · {task.location}</p></td>
            <td><StatusBadge task={task} /></td><td><span className={`priority-badge priority-${String(task.priority).toLowerCase()}`}>{task.priorityLabel}</span></td><td>{task.createdAt}</td><td className={task.isOverdue ? 'deadline-overdue' : ''}>{task.isOverdue && <span className="sr-only">Đã quá hạn. </span>}{task.deadline}</td>
            <td><button className="icon-button" aria-label={`Mở yêu cầu ${task.id}`} title="Mở chi tiết" onClick={() => onSelectTask(task)}><ArrowUpRight size={18} aria-hidden="true" /></button></td>
          </tr>)}</tbody>
        </table>
      </div>}

      <div className="table-footer" role="status"><span>Hiển thị {filtered.length} / {pagination.total} yêu cầu</span><div className="pagination-controls"><button className="button-text" type="button" disabled={loading || pagination.page <= 1} onClick={() => onPageChange?.(pagination.page - 1)}><ChevronLeft size={16} aria-hidden="true" />Trang trước</button><span>Trang {pagination.page} / {pageCount}</span><button className="button-text" type="button" disabled={loading || pagination.page >= pageCount} onClick={() => onPageChange?.(pagination.page + 1)}>Trang sau<ChevronRight size={16} aria-hidden="true" /></button></div></div>
    </section>
  </div>;
}
