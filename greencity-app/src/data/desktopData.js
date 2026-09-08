import { dashboardData } from './mockData.js';

// Fixtures only. Keep badges and filters derived from this one list.
export const tasks = [
  ...dashboardData.urgentTasks,
  { id: 'VS-2608-042', title: 'Kiểm tra vệ sinh sảnh chính tòa A', location: 'Grand Park A · Tầng 1', status: 'Đang xử lý', statusColor: 'blue', deadline: 'Hôm nay, 17:30' },
  { id: 'AN-2608-019', title: 'Bàn giao nhật ký tuần tra ca chiều', location: 'Phân khu B · Chốt an ninh 3', status: 'Chờ duyệt', statusColor: 'amber', deadline: 'Hôm nay, 18:00' },
  { id: 'KT-2608-088', title: 'Bảo dưỡng máy bơm tăng áp tầng hầm', location: 'Grand Park A · Phòng kỹ thuật B2', status: 'Đang xử lý', statusColor: 'blue', deadline: 'Ngày mai, 11:00' },
].map((task, index) => ({
  ...task,
  department: task.id.startsWith('VS') ? 'Vệ sinh' : task.id.startsWith('AN') ? 'An ninh' : task.id.startsWith('TC') ? 'Tài chính' : 'Kỹ thuật',
  deadlineOrder: [2, 6, 0, 3, 4, 5, 7][index],
}));

export const initialNotifications = [
  { id: 1, title: 'Cần phê duyệt hoàn tiền căn A101', detail: 'Hồ sơ hoàn phí thừa 3.000.000 đ kỳ 08/2026 đang chờ kiểm tra.', time: '10 phút trước', unread: true, taskId: 'TC-2608-016' },
  { id: 2, title: 'Cảnh báo quá hạn kiểm tra hệ thống điện', detail: 'Công việc KT-2608-097 tại Grand Park B trễ hạn 1 ngày.', time: '45 phút trước', unread: true, taskId: 'KT-2608-097' },
  { id: 3, title: 'Nhật ký ca trực an ninh chờ duyệt', detail: 'Tổ an ninh phân khu B đã nộp nhật ký tuần tra.', time: '2 giờ trước', unread: false, taskId: 'AN-2608-019' },
  { id: 4, title: 'Dữ liệu minh họa công nợ tháng 09/2026', detail: 'Thông báo mẫu để kiểm tra giao diện; chưa có kết nối hệ thống kế toán.', time: 'Hôm qua', unread: false },
];

export const normalizeSearch = value => String(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/g, 'd').replace(/Đ/g, 'D').toLowerCase().trim();
export const filterTasks = (items, query, status, department) => items.filter(task =>
  (status === 'all' || task.status === status) &&
  (department === 'all' || task.department === department) &&
  normalizeSearch(`${task.id} ${task.title} ${task.location}`).includes(normalizeSearch(query))
);
