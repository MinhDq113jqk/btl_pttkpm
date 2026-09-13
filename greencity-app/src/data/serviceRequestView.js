export const SERVICE_REQUEST_STATUSES = [
  { value: 'all', label: 'Tất cả' },
  { value: 'NEW', label: 'Mới tiếp nhận' },
  { value: 'TRIAGED', label: 'Đã phân loại' },
  { value: 'IN_PROGRESS', label: 'Đang xử lý' },
  { value: 'WAITING_INFO', label: 'Chờ thông tin' },
  { value: 'RESOLVED', label: 'Đã xử lý' },
  { value: 'CLOSED', label: 'Đã đóng' },
  { value: 'CANCELLED', label: 'Đã hủy' },
];

const STATUS_PRESENTATION = {
  NEW: ['Mới tiếp nhận', 'amber'],
  TRIAGED: ['Đã phân loại', 'blue'],
  IN_PROGRESS: ['Đang xử lý', 'blue'],
  WAITING_INFO: ['Chờ thông tin', 'amber'],
  RESOLVED: ['Đã xử lý', 'emerald'],
  CLOSED: ['Đã đóng', 'emerald'],
  CANCELLED: ['Đã hủy', 'rose'],
};

const PRIORITY_LABELS = { LOW: 'Thấp', MEDIUM: 'Trung bình', HIGH: 'Cao', URGENT: 'Khẩn cấp' };
const ACTIVE_STATUSES = new Set(['NEW', 'TRIAGED', 'IN_PROGRESS', 'WAITING_INFO']);

export function formatRequestDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Không xác định';
  return new Intl.DateTimeFormat('vi-VN', {
    dateStyle: 'short', timeStyle: 'short', timeZone: 'Asia/Ho_Chi_Minh',
  }).format(date);
}

export function mapServiceRequest(item, now = new Date()) {
  const deadlineOrder = new Date(item.sla_deadline).getTime();
  const createdAtOrder = new Date(item.created_at).getTime();
  const [status, statusColor] = STATUS_PRESENTATION[item.status] || [item.status || 'Không xác định', 'amber'];
  const isOverdue = ACTIVE_STATUSES.has(item.status) && Number.isFinite(deadlineOrder) && deadlineOrder < now.getTime();
  const unit = item.unit_number ? `Căn ${item.unit_number}` : 'Khu vực chung';
  const building = item.building_name || item.building_code || 'Tòa nhà chưa xác định';
  return {
    id: item.code || item.id,
    recordId: item.id,
    title: item.title,
    location: `${building} · ${unit}`,
    building,
    unit,
    apiStatus: item.status,
    status,
    statusColor,
    priority: item.priority,
    priorityLabel: PRIORITY_LABELS[item.priority] || item.priority || 'Không xác định',
    deadline: formatRequestDate(item.sla_deadline),
    deadlineOrder: Number.isFinite(deadlineOrder) ? deadlineOrder : Number.MAX_SAFE_INTEGER,
    createdAt: formatRequestDate(item.created_at),
    createdAtOrder: Number.isFinite(createdAtOrder) ? createdAtOrder : 0,
    isOverdue,
  };
}
