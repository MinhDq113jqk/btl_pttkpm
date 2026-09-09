import { navItems } from './mockData.js';
import { tasks, initialNotifications } from './desktopData.js';

export const STAFF_SESSION_KEY = 'greencity.staff-demo.v1';
const common = ['overview', 'tasks', 'notifications'];

// UI preview policy, based on roadmap_v2 §2.1 and §9. Not server authorization.
export const staffRoles = [
  { id: 'admin', label: 'Admin', icon: 'Settings', name: 'Nguyễn Minh An', initials: 'MA', title: 'Quản trị không gian làm việc', scope: 'GreenCity Central · Quản trị site', summary: 'Tài khoản, vai trò và danh mục hệ thống.', menu: navItems.map(item => item.id), primary: 'settings', primaryLabel: 'Xem tài khoản & quyền', refund: 'view', mode: 'system', allowed: ['Quản trị tài khoản và danh mục', 'Xem nhật ký và cấu hình mẫu'], restricted: 'Không tự phê duyệt hoàn tiền.' },
  { id: 'director', label: 'Giám đốc', icon: 'Building2', name: 'Trần Hoàng Nam', initials: 'HN', title: 'Tổng quan điều hành', scope: 'GreenCity Central · Toàn site', summary: 'Theo dõi vận hành, phê duyệt và xử lý ngoại lệ.', menu: [...common, 'refund-form', 'technical', 'cleaning', 'security', 'projects', 'residents', 'finance', 'reports'], primary: 'refund-form', primaryLabel: 'Kiểm tra hồ sơ chờ duyệt', refund: 'approve', mode: 'management', allowed: ['Xem công việc trong site', 'Duyệt hồ sơ do người khác lập'], restricted: 'Không lập và tự duyệt cùng một phiếu.' },
  { id: 'cskh', label: 'CSKH', icon: 'Users', name: 'Lê Thu Hà', initials: 'TH', title: 'Tiếp nhận & chăm sóc cư dân', scope: 'GreenCity Central · Quầy tòa A', summary: 'Tiếp nhận phản ánh, tra cứu và theo dõi phản hồi.', menu: [...common, 'residents', 'projects', 'amenities', 'media'], primary: 'tasks', primaryLabel: 'Mở hàng đợi tiếp nhận', refund: 'none', mode: 'service', allowed: ['Theo dõi yêu cầu tại quầy tòa A', 'Tra cứu và hướng dẫn cư dân'], restricted: 'Không duyệt hoặc thực hiện hoàn tiền.' },
  { id: 'accountant', label: 'Kế toán', icon: 'Receipt', name: 'Phạm Ngọc Linh', initials: 'NL', title: 'Tài chính & đối soát', scope: 'GreenCity Central · Tài chính site', summary: 'Đối chiếu chứng từ, lập phiếu và trình phê duyệt.', menu: [...common, 'refund-form', 'finance', 'residents', 'reports'], primary: 'refund-form', primaryLabel: 'Mở phiếu hoàn tiền', refund: 'submit', mode: 'finance', allowed: ['Lập và lưu nháp phiếu hoàn tiền', 'Trình Giám đốc kiểm tra'], restricted: 'Không phê duyệt phiếu do mình lập.' },
  { id: 'technical', label: 'Kỹ thuật', icon: 'Wrench', name: 'Vũ Đức Huy', initials: 'DH', title: 'Công việc kỹ thuật của tôi', scope: 'Grand Park A · Việc được giao', summary: 'Kiểm tra thiết bị và theo dõi các việc được phân công.', menu: [...common, 'technical'], primary: 'tasks', primaryLabel: 'Xem việc được giao', refund: 'none', mode: 'assigned', allowed: ['Xem Work Order được giao', 'Theo dõi thời hạn và vị trí thực hiện'], restricted: 'Không xem toàn bộ công việc của đội khác.' },
  { id: 'cleaning', label: 'Vệ sinh', icon: 'Sparkles', name: 'Đỗ Thanh Mai', initials: 'TM', title: 'Ca vệ sinh của tôi', scope: 'Grand Park A · Sảnh tầng 1', summary: 'Theo dõi tuyến, khu vực và chất lượng vệ sinh.', menu: [...common, 'cleaning'], primary: 'tasks', primaryLabel: 'Mở nhiệm vụ trong ca', refund: 'none', mode: 'assigned', allowed: ['Xem nhiệm vụ vệ sinh được giao', 'Đối chiếu khu vực và thời hạn'], restricted: 'Không truy cập hồ sơ tài chính cư dân.' },
  { id: 'security', label: 'An ninh', icon: 'ShieldCheck', name: 'Bùi Quốc Bảo', initials: 'QB', title: 'Ca trực an ninh của tôi', scope: 'Phân khu B · Chốt an ninh 3', summary: 'Theo dõi tuần tra, sự cố và bàn giao ca.', menu: [...common, 'security'], primary: 'security', primaryLabel: 'Mở nhật ký ca trực', refund: 'none', mode: 'assigned', allowed: ['Xem ca và khu vực phụ trách', 'Theo dõi hồ sơ bàn giao được giao'], restricted: 'Không truy cập hóa đơn hoặc hồ sơ thanh toán.' },
  { id: 'auditor', label: 'Kiểm toán', icon: 'FileSearch', name: 'Ngô Hải Yến', initials: 'HY', title: 'Không gian kiểm toán', scope: 'GreenCity Central · Chỉ đọc', summary: 'Đối chiếu báo cáo, chứng từ và dấu vết xử lý.', menu: [...common, 'refund-form', 'technical', 'cleaning', 'security', 'projects', 'residents', 'finance', 'reports'], primary: 'reports', primaryLabel: 'Xem báo cáo & dấu vết', refund: 'view', mode: 'readonly', allowed: ['Đọc báo cáo và chứng từ theo phạm vi', 'Kiểm tra người lập, người duyệt'], restricted: 'Không tạo, sửa, trình hoặc duyệt hồ sơ.' },
];

export const staffAccounts = staffRoles.map(role => ({ ...role, accountId: `demo-${role.id}`, email: `${role.id}@greencity.example`, site: 'GreenCity Central' }));
export const findStaffAccount = id => staffAccounts.find(account => account.accountId === id) || null;
export const getAllowedNav = account => navItems.filter(item => account?.menu.includes(item.id));
export const canViewTab = (account, tab) => Boolean(account?.menu.includes(tab));
export const canSubmitRefund = account => account?.refund === 'submit';
export const canApproveRefund = (account, creatorId = 'demo-accountant') => account?.refund === 'approve' && account.accountId !== creatorId;

const serviceRequests = [
  { id: 'YC-2609-021', title: 'Tiếp nhận phản ánh đèn hành lang', location: 'Grand Park A · Tầng 3', status: 'Mới tiếp nhận', statusColor: 'amber', deadline: 'Hôm nay, 09:30', deadlineOrder: 1, department: 'CSKH' },
  { id: 'YC-2609-020', title: 'Cập nhật tiến độ xử lý tiếng ồn', location: 'Grand Park A · Tầng 5', status: 'Đang xử lý', statusColor: 'blue', deadline: 'Hôm nay, 11:00', deadlineOrder: 2, department: 'CSKH' },
  { id: 'YC-2609-018', title: 'Theo dõi phản hồi sau vệ sinh sảnh', location: 'Grand Park A · Sảnh tầng 1', status: 'Chờ phản hồi', statusColor: 'amber', deadline: 'Hôm nay, 15:00', deadlineOrder: 3, department: 'CSKH' },
];
const assignments = { technical: ['KT-2608-118', 'KT-2608-088'], cleaning: ['VS-2608-042'], security: ['AN-2608-019'] };
export function getScopedTasks(account) {
  if (!account) return [];
  if (account.id === 'cskh') return serviceRequests;
  if (account.id === 'accountant') return tasks.filter(task => task.department === 'Tài chính');
  if (assignments[account.id]) return tasks.filter(task => assignments[account.id].includes(task.id));
  return ['admin', 'director', 'auditor'].includes(account.id) ? tasks : [];
}
export function getScopedNotifications(account) {
  const ids = new Set(getScopedTasks(account).map(task => task.id));
  const records = initialNotifications.filter(item => item.taskId ? ids.has(item.taskId) : ['admin', 'director', 'accountant', 'auditor'].includes(account?.id));
  if (records.length || !account) return records;
  return [{ id: 101, title: `Không gian ${account.label} đã sẵn sàng`, detail: `Đang hiển thị dữ liệu mẫu trong phạm vi: ${account.scope}.`, time: 'Thông báo mẫu', unread: true }];
}
export function loadStaffSession(storage) {
  try { return findStaffAccount(JSON.parse(storage.getItem(STAFF_SESSION_KEY))?.accountId); } catch { return null; }
}
