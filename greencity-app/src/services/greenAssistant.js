import { normalizeSearch, tasks } from '../data/desktopData.js';

// UI-only adapter. No API key, network request, external model or business mutation.
// A future server adapter must keep this Promise<string> + AbortSignal contract.
export function requestDemoReply({ question, attempt = 1, signal }) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) { reject(new DOMException('Aborted', 'AbortError')); return; }
    const abort = () => { clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')); };
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', abort);
      if (normalizeSearch(question) === 'thu loi' && attempt === 1) {
        reject(new Error('Đây là lỗi mô phỏng để kiểm tra giao diện. Câu hỏi vẫn được giữ nguyên; chọn Gửi lại để thử lần nữa.'));
      } else {
        resolve(demoAnswer(question));
      }
    }, 1100);
    signal?.addEventListener('abort', abort, { once: true });
  });
}

export function demoAnswer(question) {
  const query = normalizeSearch(question);
  if (query === 'thu loi') return 'Đã gửi lại thành công trong bản mô phỏng. Câu hỏi được giữ nguyên, không tạo thêm tin nhắn trùng lặp.\n\nKhi có API AI, khu vực này sẽ hiển thị câu trả lời từ hệ thống thật.';
  if (query.includes('hoan tien') || query.includes('hoa don')) return 'Bạn có thể kiểm tra phiếu hoàn tiền theo các bước:\n\n1. Mở “Phiếu hoàn tiền & Hoá đơn” ở thanh bên.\n2. Đối chiếu cư dân, số tiền, ngày và phương thức chi trả.\n3. Kiểm tra chứng từ, rồi chọn “Kiểm tra & xác nhận”.\n\nDùng “Lưu bản nháp” nếu cần làm tiếp sau. Đây là hướng dẫn cho giao diện mẫu; xác nhận hiện không chuyển tiền hoặc tạo bút toán thật.';
  if (query.includes('qua han') || query.includes('cong viec')) {
    const overdue = tasks.filter(task => task.status === 'Quá hạn');
    return `Trong bộ dữ liệu mẫu có ${tasks.length} công việc, ${overdue.length} việc quá hạn:\n\n${overdue.map(task => `• ${task.id}: ${task.title}\n  ${task.location} · ${task.deadline}`).join('\n')}\n\nĐể xem chi tiết, mở “Công việc & Yêu cầu”, chọn bộ lọc “Quá hạn”, rồi mở công việc cần kiểm tra.\n\nĐây không phải dữ liệu vận hành trực tiếp.`;
  }
  if (query.includes('thong bao')) return 'Mở “Thông báo” ở thanh bên hoặc biểu tượng chuông trên đầu ứng dụng.\n\n• Chọn “Chưa đọc” để xem các mục cần chú ý.\n• Chọn “Mở hồ sơ liên quan” để đối chiếu thông tin.\n• Dùng “Đánh dấu đã đọc” khi đã xem xong.\n\nCác trạng thái này hiện thuộc bản dữ liệu mẫu.';
  if (query.includes('lich su') || query.includes('tro chuyen')) return 'Lịch sử Green Assistant được lưu trong trình duyệt trên máy này. Bạn có thể đóng khung chat, tải lại ứng dụng rồi mở lại để tiếp tục.\n\nNút đồng hồ mở danh sách các cuộc trò chuyện. Nút dấu cộng tạo cuộc trò chuyện mới nhưng không xóa các cuộc cũ.\n\nLịch sử chưa đồng bộ tài khoản hoặc thiết bị. Không nhập mật khẩu, OTP hay dữ liệu cư dân thật.';
  return 'Mình là Green Assistant — trợ lý hướng dẫn sử dụng GreenCity. Bản hiện tại trả lời theo kịch bản mẫu, chưa kết nối mô hình AI.\n\nBạn có thể hỏi về:\n• Cách theo dõi công việc quá hạn.\n• Cách kiểm tra phiếu hoàn tiền.\n• Cách xem thông báo hoặc tìm lại cuộc trò chuyện.\n\nVới câu hỏi ngoài các nội dung này, mình chưa có dữ liệu để trả lời chính xác.';
}
