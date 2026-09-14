import { navItems } from './mockData.js';

const SERVICE_REQUEST_ROLES = new Set([
  'admin', 'director', 'accountant', 'cskh', 'technical_lead', 'technician',
]);

const UNIT_360_ROLES = new Set([
  'admin', 'director', 'accountant', 'cskh', 'technical_lead', 'security',
]);

const CLEANING_ROLES = new Set(['admin', 'director', 'cleaning']);
const CLEANING_MANAGER_ROLES = new Set(['admin', 'director']);
const SECURITY_ROLES = new Set(['admin', 'director', 'security']);
const SECURITY_MANAGER_ROLES = new Set(['admin', 'director']);
const BILLING_ROLES = new Set(['admin', 'director', 'accountant']);

const ROLE_POLICIES = {
  admin: { label: 'Admin', title: 'Tổng quan yêu cầu dịch vụ', summary: 'Theo dõi yêu cầu trong site đang hoạt động.' },
  director: { label: 'Giám đốc', title: 'Tổng quan điều hành', summary: 'Theo dõi yêu cầu trong phạm vi điều hành hiện tại.' },
  accountant: { label: 'Kế toán', title: 'Yêu cầu dịch vụ trong site', summary: 'Đọc danh sách yêu cầu thuộc site đang hoạt động.' },
  cskh: { label: 'CSKH', title: 'Tiếp nhận & chăm sóc cư dân', summary: 'Theo dõi yêu cầu tại các tòa nhà được phân quyền.' },
  technical_lead: { label: 'Trưởng kỹ thuật', title: 'Điều phối yêu cầu kỹ thuật', summary: 'Theo dõi yêu cầu tại các tòa nhà được phân quyền.' },
  technician: { label: 'Kỹ thuật viên', title: 'Yêu cầu liên quan công việc của tôi', summary: 'Chỉ đọc yêu cầu có công việc được giao cho bạn.' },
  cleaning: { label: 'Vệ sinh', title: 'Ca vệ sinh của tôi', summary: 'Thực hiện checklist cho các khu vực được máy chủ phân công.' },
  security: { label: 'An ninh', title: 'Ca trực và tuần tra của tôi', summary: 'Ghi nhận tuần tra, khách và sự cố trong ca do máy chủ phân công.' },
};

const initialsFor = name => String(name || '').trim().split(/\s+/).filter(Boolean).slice(-2).map(part => part[0]).join('').toUpperCase() || 'GC';

export const canAccessServiceRequests = value => (value?.roles || []).some(role => SERVICE_REQUEST_ROLES.has(role));
export const canAccessUnit360 = value => (value?.roles || []).some(role => UNIT_360_ROLES.has(role));
export const canAccessCleaning = value => (value?.roles || []).some(role => CLEANING_ROLES.has(role));
export const canManageCleaning = value => (value?.roles || []).some(role => CLEANING_MANAGER_ROLES.has(role));
export const canAccessSecurity = value => (value?.roles || []).some(role => SECURITY_ROLES.has(role));
export const canManageSecurity = value => (value?.roles || []).some(role => SECURITY_MANAGER_ROLES.has(role));
export const canAccessBilling = value => (value?.roles || []).some(role => BILLING_ROLES.has(role));
export const canCreateServiceRequests = value => (value?.roles || []).includes('cskh');
export const getWorkspaceKey = account => `${account?.accountId || 'anonymous'}:${account?.activeSiteId || 'no-site'}`;

export function createAuthenticatedAccount(user) {
  const roles = [...new Set((user?.roles || []).filter(role => typeof role === 'string'))];
  const policies = roles.map(role => ROLE_POLICIES[role]).filter(Boolean);
  const primary = policies[0] || { label: 'Nhân viên', title: 'Không gian làm việc', summary: 'Quyền hiển thị được lấy từ hồ sơ máy chủ.' };
  const activeSite = (user?.allowed_sites || []).find(site => site.id === user.active_site_id) || null;
  const allowedSites = (user?.allowed_sites || []).map(site => ({ id: site.id, code: site.code, name: site.name }));
  const canListRequests = roles.some(role => SERVICE_REQUEST_ROLES.has(role));
  const canViewUnits = roles.some(role => UNIT_360_ROLES.has(role));
  const canViewCleaning = roles.some(role => CLEANING_ROLES.has(role));
  const canManageCleaningTasks = roles.some(role => CLEANING_MANAGER_ROLES.has(role));
  const canViewSecurity = roles.some(role => SECURITY_ROLES.has(role));
  const canManageSecurityShifts = roles.some(role => SECURITY_MANAGER_ROLES.has(role));
  const canViewBilling = roles.some(role => BILLING_ROLES.has(role));
  const canCreateRequests = roles.includes('cskh');
  const menu = ['overview'];
  if (canListRequests) menu.push('tasks');
  if (canViewCleaning) menu.push('cleaning');
  if (canViewSecurity) menu.push('security');
  if (canViewBilling) menu.push('finance');
  if (canViewUnits) menu.push('residents');
  menu.push('notifications');
  const roleLabel = policies.length ? policies.map(policy => policy.label).join(' · ') : primary.label;

  const account = {
    accountId: user.account_id,
    activeSiteId: user.active_site_id,
    allowedSites,
    id: roles[0] || 'staff',
    username: user.username,
    name: user.full_name,
    initials: initialsFor(user.full_name),
    roles,
    label: roleLabel,
    title: primary.title,
    summary: primary.summary,
    site: activeSite?.name || 'Chưa có site đang hoạt động',
    scope: activeSite ? `${activeSite.name} · Phạm vi do máy chủ cấp` : 'Chưa có site đang hoạt động',
    menu,
    primary: canListRequests ? 'tasks' : canViewCleaning ? 'cleaning' : canViewSecurity ? 'security' : canViewUnits ? 'residents' : 'notifications',
    primaryLabel: canListRequests ? 'Mở danh sách yêu cầu' : canViewCleaning ? 'Mở ca vệ sinh' : canViewSecurity ? 'Mở ca trực an ninh' : canViewUnits ? 'Tra cứu căn hộ 360°' : 'Xem thông báo phiên',
    canViewServiceRequests: canListRequests,
    canCreateServiceRequests: canCreateRequests,
    canViewUnit360: canViewUnits,
    canViewCleaning,
    canManageCleaning: canManageCleaningTasks,
    canViewSecurity,
    canManageSecurity: canManageSecurityShifts,
    canViewBilling,
    allowed: canListRequests
      ? ['Đọc yêu cầu trong phạm vi máy chủ cho phép', ...(canViewUnits ? ['Tra cứu căn hộ theo Unit ID trong phạm vi phiên'] : []), ...(canViewCleaning ? ['Xem ca vệ sinh theo API của phiên'] : []), ...(canViewBilling ? ['Cấu hình phí và xem hóa đơn theo API kế toán'] : []), 'Lọc trạng thái và phân trang trên API']
      : canViewCleaning
        ? ['Xem và thực hiện ca vệ sinh theo phân công của máy chủ']
        : canViewSecurity
          ? ['Xem và thực hiện ca trực, tuần tra theo phân công của máy chủ']
        : canViewUnits
          ? ['Tra cứu căn hộ theo Unit ID trong phạm vi phiên']
          : ['Xem thông tin phiên và vai trò được máy chủ trả về'],
    restricted: 'Giao diện không gửi tenant, role hoặc phạm vi tòa nhà để mở rộng quyền.',
  };
  return { ...account, workspaceKey: getWorkspaceKey(account) };
}

export const getAllowedNav = account => navItems.filter(item => account?.menu?.includes(item.id));
export const canViewTab = (account, tab) => Boolean(account?.menu?.includes(tab));

export const getSessionNotifications = account => [{
  id: 'authenticated-session',
  title: 'Phiên đăng nhập đã được xác minh',
  detail: `Menu hiện tại được tạo từ vai trò do /auth/me trả về cho ${account.name}.`,
  time: 'Phiên hiện tại',
  unread: true,
}];
