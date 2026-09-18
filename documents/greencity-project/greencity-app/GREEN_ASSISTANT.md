# Green Assistant — Giao diện trợ lý desktop

Linh vật mầm xanh ở góc ứng dụng mở khung chat hỗ trợ, không mở cửa sổ ngoài hệ điều hành. Triển khai tại `C:\Users\LEGION\btl\greencity-app`; không sửa bản trong `_pttkpm`.

## Phạm vi 10 yêu cầu

| Yêu cầu | Cách hoạt động |
| --- | --- |
| Phân biệt người dùng và chatbot | Người dùng bên phải, nền xanh đậm; trợ lý bên trái, nền nhạt. Có tên người nói và giờ gửi. |
| Cuộn tới tin mới nhất | Tự cuộn khi gửi/nhận và khi mở lại. Nếu đang đọc đoạn cũ, giữ vị trí và hiện nút “Tin nhắn mới nhất”. |
| Hiệu ứng đang trả lời | Dòng “Green Assistant đang trả lời...” và ba chấm động. |
| Loading | `aria-busy`, spinner, chặn gửi trùng; vẫn soạn được câu hỏi tiếp theo trong lúc chờ. |
| Lỗi rõ ràng | Lỗi phản hồi, timeout, sao chép, nhập quá dài và lưu trữ đều có thông báo phù hợp. |
| Enter / Shift+Enter | Enter gửi; Shift+Enter xuống dòng; không gửi nhầm khi bộ gõ đang composition. |
| Giữ lịch sử | Lưu tin nhắn, nháp và danh sách cuộc trò chuyện bằng localStorage. Khôi phục khi tải lại. |
| Tạo trò chuyện mới | Nút dấu cộng mở cuộc mới, không xóa tin hoặc nháp của cuộc cũ; nút đồng hồ mở lịch sử. |
| Copy câu trả lời | Nút Sao chép dưới mỗi câu trả lời; báo đã sao chép hoặc hướng dẫn Ctrl+C nếu quyền clipboard bị chặn. |
| Gửi lại khi lỗi | Thử lại câu hỏi gốc trong chính khung lỗi, không nhân đôi câu hỏi; phản hồi gắn đúng cuộc trò chuyện kể cả khi đã chuyển cuộc. |

## Hành vi bổ sung

- Escape thu gọn khung chat và trả focus về linh vật. Khung chat không khóa các phần khác của ứng dụng; tự thu gọn nếu cần để không che một điều khiển nhận focus bằng bàn phím.
- Linh vật tránh các nút submit của biểu mẫu khi chúng xuất hiện trong vùng nhìn; khung chat nằm trên thanh hành động hoàn tiền.
- Nếu tải lại giữa lúc xử lý, trạng thái đang chờ trở thành lỗi “bị gián đoạn”, có nút gửi lại; không giữ spinner vô hạn.
- Nếu lịch sử hỏng, không ghi đè dữ liệu cũ. Nếu cửa sổ khác sửa lịch sử, tạm dừng ghi ở cửa sổ hiện tại và báo rõ, tránh ghi đè im lặng. Chưa có tính năng hợp nhất nhiều cửa sổ.
- Không dùng animation khi hệ thống bật reduced motion. Linh vật là SVG do dự án tự vẽ, không sử dụng tài sản Codex hoặc tài nguyên mạng.

## Giới hạn quan trọng

Đây là **giao diện với bộ trả lời mô phỏng**, chưa có mô hình AI hoặc backend. Không có yêu cầu mạng, API key, gửi dữ liệu ra ngoài, tự đọc hồ sơ cư dân hoặc tự thực hiện nghiệp vụ. Nội dung hướng dẫn và số liệu công việc chỉ đến từ dữ liệu mẫu hiện có.

Nhập **“thử lỗi”** để xem lỗi mô phỏng, rồi bấm **Gửi lại câu hỏi** để thử luồng phục hồi. Chi tiết này cũng có trong phần thông tin ở cuối khung chat. Timeout mặc định là 15 giây.

Lịch sử chỉ thuộc trình duyệt và origin hiện tại: `localhost` khác `127.0.0.1`, cổng `3000` khác `4173`. Không đồng bộ tài khoản, máy hoặc trình duyệt khác. Xóa dữ liệu trình duyệt sẽ xóa lịch sử. LocalStorage không phải kho bí mật: không nhập mật khẩu, OTP, token hoặc dữ liệu cư dân/tài chính thật vào bản mẫu.

## Điểm nối backend sau này

- `src/services/greenAssistant.js`: bộ trả lời mô phỏng. Component nhận prop `requestReply` với đầu vào `{ question, messages, attempt, signal }`, trả về `Promise<string>`.
- `src/data/assistantStore.js`: reducer, kiểm tra dữ liệu lịch sử, xử lý khôi phục và phím gửi.
- `src/components/assistant/GreenAssistant.jsx`: luồng chat, lưu lịch sử, copy, loading/error/retry.
- `src/components/assistant/GreenPet.jsx` và `green-assistant.css`: linh vật và kiểu hiển thị.
- Không đặt khóa API của nhà cung cấp trong frontend. Việc chọn nhà cung cấp, xác thực, dữ liệu được phép gửi và chính sách lưu giữ cần quyết định riêng trước khi nối AI thật.

## Kiểm thử

Lượt kiểm chứng ngày 08/09/2026: **32 kiểm thử logic, 53 kiểm tra UI Green Assistant và 83 kiểm tra hồi quy desktop đều đạt**. Hai bộ UI cũng chạy lại trên bản build preview; không ghi nhận lỗi JavaScript runtime trong các luồng kiểm thử. `npm run build` thành công.

```powershell
Set-Location 'C:\Users\LEGION\btl\greencity-app'
npm test
npm run build
```

Kiểm thử UI dùng Playwright và Edge có sẵn tại máy này, không thêm dependency cho sản phẩm:

```powershell
$env:NODE_PATH='C:\Users\LEGION\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
$env:UX_BASE_URL='http://127.0.0.1:4173/'
npm run test:assistant
npm run test:ux
```

Cần chạy `npm run preview -- --host 127.0.0.1 --port 4173` trước khi kiểm thử bản build. Đường dẫn runtime trên chỉ áp dụng cho máy hiện tại.

Kết quả và ảnh kiểm chứng: `artifacts/assistant/test-results.json`, `artifacts/assistant/GreenAssistant.png`; kiểm tra hồi quy ứng dụng ở `artifacts/ux/test-results.json`. Các kịch bản clipboard, timeout, hỏng/quá dung lượng bộ nhớ dùng trình duyệt kiểm thử riêng; không thay đổi clipboard hay lịch sử thật của người dùng.

Thiết kế dùng hướng dẫn ui-ux-pro-max và frontend-design, giữ nhận diện xanh và font desktop hiện có. Tham chiếu kỹ thuật: [MDN — Composition của bàn phím](https://developer.mozilla.org/en-US/docs/Web/API/KeyboardEvent/isComposing), [MDN — Clipboard.writeText](https://developer.mozilla.org/en-US/docs/Web/API/Clipboard/writeText), [MDN — LocalStorage](https://developer.mozilla.org/en-US/docs/Web/API/Window/localStorage). Chưa kiểm thử trình đọc màn hình thật hoặc tích hợp native Windows.
