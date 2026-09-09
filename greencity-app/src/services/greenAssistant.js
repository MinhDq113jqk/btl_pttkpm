import { normalizeSearch, tasks } from '../data/desktopData.js';

// UI-only adapter. No API key, network request, external model or business mutation.
// A future server adapter must keep this Promise<string> + AbortSignal contract.
export function requestDemoReply({ question, attempt = 1, signal, visibleTasks = tasks, allowedTabs, roleLabel }) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) { reject(new DOMException('Aborted', 'AbortError')); return; }
    const abort = () => { clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')); };
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', abort);
      if (normalizeSearch(question) === 'thu loi' && attempt === 1) {
        const error = new Error('Đây là lỗi mô phỏng để kiểm tra giao diện. Câu hỏi vẫn được giữ nguyên; chọn Gửi lại để thử lần nữa.');
        error.name = 'DemoAssistantError';
        reject(error);
      } else {
        resolve(demoAnswer(question, { visibleTasks, allowedTabs, roleLabel }));
      }
    }, 1100);
    signal?.addEventListener('abort', abort, { once: true });
  });
}

export function demoAnswer(question, { visibleTasks = tasks, allowedTabs, roleLabel } = {}) {
  const query = normalizeSearch(question);
  if ((query.includes('hoan tien') || query.includes('hoa don')) && allowedTabs && !allowedTabs.includes('refund-form')) return `Vai trò ${roleLabel} không có quyền truy cập phiếu hoàn tiền trong bản giao diện. Bạn có thể liên hệ Kế toán hoặc CSKH để được hướng dẫn; mình không hiển thị chứng từ ngoài phạm vi.`;
  if ((query.includes('hoan tien') || query.includes('hoa don')) && ['Giám đốc', 'Admin', 'Kiểm toán'].includes(roleLabel)) return roleLabel === 'Giám đốc' ? 'Mở “Phiếu hoàn tiền & Hoá đơn” để đối chiếu hồ sơ do Kế toán lập. Bạn có thể xem thông tin gốc và thử bước phê duyệt, không sửa số tiền hoặc tài khoản thụ hưởng tại bước này. Đây là mô phỏng, không tạo giao dịch thật.' : `Vai trò ${roleLabel} chỉ xem chứng từ hoàn tiền, không sửa, trình hoặc phê duyệt. Bạn có thể mở “Phiếu hoàn tiền & Hoá đơn” và “Báo cáo điều hành” để đối chiếu dữ liệu mẫu.`;
  if (query === 'thu loi') return 'Đã gửi lại thành công trong bản mô phỏng. Câu hỏi được giữ nguyên, không tạo thêm tin nhắn trùng lặp.\n\nKhi có API AI, khu vực này sẽ hiển thị câu trả lời từ hệ thống thật.';
  if (query.includes('hoan tien') || query.includes('hoa don')) return 'Bạn có thể kiểm tra phiếu hoàn tiền theo các bước:\n\n1. Mở “Phiếu hoàn tiền & Hoá đơn” ở thanh bên.\n2. Đối chiếu cư dân, số tiền, ngày và phương thức chi trả.\n3. Kiểm tra chứng từ, rồi chọn “Kiểm tra & xác nhận”.\n\nDùng “Lưu bản nháp” nếu cần làm tiếp sau. Đây là hướng dẫn cho giao diện mẫu; xác nhận hiện không chuyển tiền hoặc tạo bút toán thật.';
  if (query.includes('qua han') || query.includes('cong viec')) {
    const overdue = visibleTasks.filter(task => task.status === 'Quá hạn');
    return `Trong bộ dữ liệu mẫu${roleLabel ? ` thuộc phạm vi ${roleLabel}` : ''} có ${visibleTasks.length} công việc, ${overdue.length} việc quá hạn:\n\n${overdue.length ? overdue.map(task => `• ${task.id}: ${task.title}\n  ${task.location} · ${task.deadline}`).join('\n') : 'Không có công việc quá hạn trong phạm vi hiện tại.'}\n\nĐể xem chi tiết, mở “Công việc & Yêu cầu”, chọn bộ lọc “Quá hạn”, rồi mở công việc cần kiểm tra.\n\nĐây không phải dữ liệu vận hành trực tiếp.`;
  }
  if (query.includes('thong bao')) return 'Mở “Thông báo” ở thanh bên hoặc biểu tượng chuông trên đầu ứng dụng.\n\n• Chọn “Chưa đọc” để xem các mục cần chú ý.\n• Chọn “Mở hồ sơ liên quan” để đối chiếu thông tin.\n• Dùng “Đánh dấu đã đọc” khi đã xem xong.\n\nCác trạng thái này hiện thuộc bản dữ liệu mẫu.';
  if (query.includes('lich su') || query.includes('tro chuyen')) return 'Lịch sử Green Assistant được lưu trong trình duyệt trên máy này. Bạn có thể đóng khung chat, tải lại ứng dụng rồi mở lại để tiếp tục.\n\nNút đồng hồ mở danh sách các cuộc trò chuyện. Nút dấu cộng tạo cuộc trò chuyện mới nhưng không xóa các cuộc cũ.\n\nLịch sử chưa đồng bộ tài khoản hoặc thiết bị. Không nhập mật khẩu, OTP hay dữ liệu cư dân thật.';
  return 'Mình là Green Assistant — trợ lý hướng dẫn sử dụng GreenCity. Bản hiện tại trả lời theo kịch bản mẫu, chưa kết nối mô hình AI.\n\nBạn có thể hỏi về:\n• Cách theo dõi công việc quá hạn.\n• Cách kiểm tra phiếu hoàn tiền.\n• Cách xem thông báo hoặc tìm lại cuộc trò chuyện.\n\nVới câu hỏi ngoài các nội dung này, mình chưa có dữ liệu để trả lời chính xác.';
}
