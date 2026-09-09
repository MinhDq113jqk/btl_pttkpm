import React from 'react';
import { ArrowRight, ShieldCheck, MapPin, Eye, CheckSquare, FileSearch } from 'lucide-react';
import { DashboardView } from '../DashboardView';
import { StatusBadge } from '../TasksDesktopView';
import { staffAccounts, staffRoles } from '../../data/staffRoles';
import { sampleRefundCase } from '../../data/mockData';
import { formatVND } from '../../data/refundForm';

export function StaffDashboard({ account, items, onNavigate, onSelectTask, onFilterTasks }) {
  if (account.id === 'director') return <><div className="staff-context-strip"><span className="staff-role-mark">{account.initials}</span><div><strong>{account.name} · {account.label}</strong><span>{account.scope}</span></div><span className="staff-permission-pill">Xem vận hành & phê duyệt</span></div><DashboardView tasks={items} onSelectTask={onSelectTask} onViewAll={() => onNavigate('tasks')} onFilterTasks={onFilterTasks} /></>;
  const system = account.mode === 'system';
  const audit = account.mode === 'readonly';
  const finance = account.mode === 'finance';
  const metrics = system ? [
    { label: 'Tài khoản mẫu', value: staffAccounts.length, target: 'settings' }, { label: 'Vai trò', value: staffRoles.length, target: 'settings' }, { label: 'Phạm vi site', value: 1, target: 'projects' }, { label: 'Kết nối xác thực', value: 'Chưa có', target: 'settings' },
  ] : finance ? [
    { label: 'Hồ sơ tài chính mẫu', value: items.length, target: 'tasks' }, { label: 'Số dư đề nghị hoàn', value: formatVND(sampleRefundCase.financials.remainingAmount), target: 'refund-form' }, { label: 'Quyền trên phiếu', value: 'Lập / trình', target: 'refund-form' }, { label: 'Người phê duyệt', value: 'Giám đốc', target: 'reports' },
  ] : [
    { label: audit ? 'Hồ sơ được xem' : account.id === 'cskh' ? 'Yêu cầu tại quầy' : 'Việc được giao', value: items.length, status: 'all' },
    { label: 'Đang xử lý', value: items.filter(item => item.status === 'Đang xử lý').length, status: 'Đang xử lý' },
    { label: account.id === 'cskh' ? 'Mới tiếp nhận' : 'Chờ duyệt', value: items.filter(item => item.status === (account.id === 'cskh' ? 'Mới tiếp nhận' : 'Chờ duyệt')).length, status: account.id === 'cskh' ? 'Mới tiếp nhận' : 'Chờ duyệt' },
    { label: 'Quá hạn', value: items.filter(item => item.status === 'Quá hạn').length, status: 'Quá hạn' },
  ];
  return <div className="desktop-page staff-dashboard">
    <div className="page-heading"><div><p className="eyebrow">Không gian {account.label}</p><h1>{account.title}</h1><p>Xin chào {account.name}. {account.summary}</p></div><span className={`staff-permission-pill ${audit ? 'is-readonly' : ''}`}>{audit ? <Eye size={15} aria-hidden="true" /> : <ShieldCheck size={15} aria-hidden="true" />}{audit ? 'Chỉ đọc' : 'Theo quyền được cấp'}</span></div>
    <section className="staff-scope-banner"><div><MapPin size={20} aria-hidden="true" /><div><span>Phạm vi đang làm việc</span><strong>{account.scope}</strong></div></div><button className="button-primary" onClick={() => onNavigate(account.primary)}>{account.primaryLabel}<ArrowRight size={16} aria-hidden="true" /></button></section>
    <div className="metric-grid staff-metrics">{metrics.map(metric => <button className="metric-card" key={metric.label} onClick={() => metric.target ? onNavigate(metric.target) : onFilterTasks(metric.status)}><span className="metric-label">{metric.label}</span><strong>{metric.value}</strong><span className="metric-link">{system || finance ? 'Xem chi tiết' : 'Mở danh sách'}<ArrowRight size={14} aria-hidden="true" /></span></button>)}</div>
    <div className="overview-grid">
      <section className="surface"><div className="section-heading"><div><h2>{system ? 'Tài khoản & vai trò' : audit ? 'Hồ sơ cần đối chiếu' : finance ? 'Phiếu cần chuẩn bị' : 'Ưu tiên trong phạm vi của bạn'}</h2><p>{system ? 'Danh sách tài khoản minh họa, chưa có phiên đăng nhập thật.' : 'Chỉ hiển thị dữ liệu mẫu thuộc phạm vi tài khoản.'}</p></div><button className="button-text" onClick={() => onNavigate(system ? 'settings' : 'tasks')}>Xem tất cả<ArrowRight size={16} aria-hidden="true" /></button></div>
        {system ? <div className="staff-account-preview">{staffAccounts.slice(0, 4).map(item => <div key={item.id}><span className="staff-role-mark">{item.initials}</span><div><strong>{item.name}</strong><span>{item.label}</span></div><span className="subtle-badge">Tài khoản mẫu</span></div>)}</div> : <div className="attention-list">{[...items].sort((a, b) => a.deadlineOrder - b.deadlineOrder).slice(0, 5).map(item => <button className="attention-task" key={item.id} onClick={() => onSelectTask(item)}><div><span className="task-code">{item.id}</span><h3>{item.title}</h3><p>{item.location}</p></div><div className="attention-task-meta"><StatusBadge task={item} /><span>{item.deadline}</span></div></button>)}{!items.length && <div className="empty-state"><CheckSquare size={28} /><h3>Chưa có công việc trong phạm vi</h3><p>Danh sách sẽ cập nhật khi có nhiệm vụ được giao.</p></div>}</div>}
      </section>
      <aside className="surface staff-access-card"><div className="section-heading"><div><h2>{audit ? 'Nguyên tắc kiểm toán' : 'Vai trò của bạn'}</h2><p>{account.label} · {account.name}</p></div></div><div className="staff-access-body"><h3>Trong phạm vi của bạn</h3><ul>{account.allowed.map(item => <li key={item}><CheckSquare size={15} aria-hidden="true" />{item}</li>)}</ul><div className="context-note"><strong>Giới hạn cần nhớ</strong>{account.restricted}</div><p className="helper-text">Mô phỏng phân quyền phía giao diện. Backend chưa được triển khai.</p></div></aside>
    </div>
  </div>;
}

export function StaffAdminView() {
  return <div className="desktop-page"><div className="page-heading"><div><p className="eyebrow">Quản trị hệ thống</p><h1>Tài khoản & phân quyền</h1><p>Kiểm tra vai trò và phạm vi cấp cho nhân viên. Chưa có chức năng thay đổi quyền thật.</p></div><span className="subtle-badge">8 tài khoản mẫu</span></div><section className="surface"><div className="table-scroll"><table className="tasks-table"><caption className="sr-only">Danh sách tài khoản nhân viên mẫu</caption><thead><tr><th>Nhân viên</th><th>Vai trò</th><th>Phạm vi</th><th>Quyền hoàn tiền</th></tr></thead><tbody>{staffAccounts.map(account => <tr key={account.accountId}><td><strong>{account.name}</strong><p className="task-meta">{account.email}</p></td><td>{account.label}</td><td>{account.scope}</td><td>{{ view: 'Chỉ xem', approve: 'Phê duyệt', submit: 'Lập / trình', none: 'Không truy cập' }[account.refund]}</td></tr>)}</tbody></table></div></section><p className="context-note staff-note">Trong hệ thống thật, Admin cấp quyền theo site và nhiệm vụ; không tự nâng quyền từ màn đăng nhập. Trưởng kỹ thuật chưa được tách thành tài khoản trong bản thiết kế 8 vai trò này.</p></div>;
}

export function StaffReportsView({ account, items }) {
  const departments = [...new Set(items.map(item => item.department))];
  return <div className="desktop-page"><div className="page-heading"><div><p className="eyebrow">Báo cáo & đối chiếu</p><h1>Báo cáo trong phạm vi</h1><p>{account.scope} · Tất cả chỉ số bên dưới là dữ liệu mẫu.</p></div><span className="staff-permission-pill is-readonly"><FileSearch size={16} />Chế độ xem</span></div><section className="surface"><div className="section-heading"><div><h2>Tổng hợp theo bộ phận</h2><p>Số đếm lấy từ cùng danh sách công việc được phép xem.</p></div></div><div className="table-scroll"><table className="tasks-table"><thead><tr><th>Bộ phận</th><th>Tổng hồ sơ</th><th>Đang xử lý</th><th>Chờ duyệt</th><th>Quá hạn</th></tr></thead><tbody>{departments.map(department => { const rows = items.filter(item => item.department === department); return <tr key={department}><td>{department}</td><td>{rows.length}</td><td>{rows.filter(item => item.status === 'Đang xử lý').length}</td><td>{rows.filter(item => item.status === 'Chờ duyệt').length}</td><td>{rows.filter(item => item.status === 'Quá hạn').length}</td></tr>; })}</tbody></table></div></section><section className="surface staff-note form-section"><h2>Dấu vết trên hồ sơ hoàn tiền mẫu</h2><dl className="profile-grid"><div><dt>Người lập</dt><dd>Phạm Ngọc Linh · Kế toán</dd></div><div><dt>Người kiểm tra dự kiến</dt><dd>Trần Hoàng Nam · Giám đốc</dd></div><div><dt>Trạng thái</dt><dd>Chờ kiểm tra · Dữ liệu mẫu</dd></div><div><dt>Nhật ký thật</dt><dd>Chưa kết nối backend</dd></div></dl><p className="context-note">Không thể suy ra hồ sơ đã được phê duyệt hoặc ghi sổ từ bản giao diện này.</p></section></div>;
}
