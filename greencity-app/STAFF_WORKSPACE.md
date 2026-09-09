# GreenCity — Giao diện nhân viên & Ban quản lý

Ngày: 09/09/2026. Bản thiết kế tương tác tại `C:\Users\LEGION\btl\greencity-app`; không sửa tài liệu trong `_pttkpm` hoặc hai bản chuẩn bị publish trước đó.

## Cách xem

Chạy `npm run dev`, mở ứng dụng và chọn **Tài khoản nhân viên mẫu**, sau đó bấm **Vào không gian mẫu**. Dùng **Đổi tài khoản / Đăng xuất** ở cuối sidebar để xem một vai trò khác. Không cần và không nhập mật khẩu thật.

## Một khung, tám góc nhìn

| Vai trò | Dashboard ưu tiên | Phạm vi / điểm khác biệt |
| --- | --- | --- |
| Admin | Tài khoản, vai trò và danh mục | Có màn ma trận tài khoản/quyền; chỉ xem phiếu hoàn tiền, không duyệt |
| Giám đốc | Tổng quan điều hành, hồ sơ cần chú ý | Xem toàn site mẫu; kiểm tra và thử phê duyệt phiếu do Kế toán lập, không sửa thông tin gốc tại bước duyệt |
| CSKH | Hàng đợi tiếp nhận, tiến độ phản hồi | Ba yêu cầu mẫu tại quầy tòa A; không truy cập phiếu hoàn tiền |
| Kế toán | Phiếu tài chính và số dư đề nghị hoàn | Có biểu mẫu lập/lưu nháp/trình; không có quyền phê duyệt |
| Kỹ thuật | Công việc kỹ thuật của tôi | Chỉ hai Work Order mẫu được giao; không thấy việc đội khác |
| Vệ sinh | Ca vệ sinh của tôi | Chỉ nhiệm vụ mẫu ở sảnh tầng 1 được giao |
| An ninh | Ca trực và bàn giao | Chỉ hồ sơ mẫu tại chốt an ninh 3 thuộc phân khu B |
| Kiểm toán | Hồ sơ đối chiếu, báo cáo và dấu vết | Xem chứng từ/báo cáo; không có trường sửa, nút lưu nháp, trình hoặc duyệt nghiệp vụ |

Chung logo, sidebar, header, tìm kiếm, thông báo, trạng thái phạm vi và Green Assistant. Mỗi vai trò có nội dung dashboard, số đếm, lối tắt và menu tương ứng; không chỉ đổi tên người dùng.

## Căn cứ và giả định

- Đối chiếu tài liệu hiện có `_pttkpm/roadmap_v2.md`, mục 2.1, 2.2 và 9: phạm vi từ phiên, chỉ việc được giao, Kế toán lập/trình, Giám đốc duyệt, Kiểm toán chỉ đọc.
- “Kỹ thuật” trong yêu cầu được hiểu là **kỹ thuật viên**. Chưa bổ sung tài khoản Trưởng kỹ thuật; quyền phân công/nghiệm thu của trưởng nhóm không được gộp ngầm vào kỹ thuật viên.
- Demo chỉ một site GreenCity Central. Dữ liệu CSKH và phân công nhân viên là fixture mới, có nhãn mẫu, không phải số liệu vận hành thật.
- Phân hệ truyền thông/tiện ích hiện có tiếp tục dùng ở tài khoản Admin và CSKH để xem thử giao diện; đây là **đề xuất menu cho bản mẫu**, cần xác nhận quyền create/update/publish riêng trước khi làm backend vì ma trận hiện tại chưa định nghĩa đầy đủ các tài nguyên này.
- Không thêm cổng cư dân, backend, nhà cung cấp xác thực, giao dịch ngân hàng hoặc bộ cài Windows trong lượt này.

## Ranh giới dữ liệu trong giao diện

- Menu, dashboard, danh sách công việc, tìm kiếm, thông báo và câu trả lời mẫu của Green Assistant dùng cùng phạm vi tài khoản.
- Truy cập trực tiếp một URL không được cấp hiển thị “Không có quyền xem phân hệ này”, không mount màn nghiệp vụ đó.
- Đổi tài khoản remount không gian làm việc để bỏ state, bộ lọc, modal và dữ liệu đang hiển thị của tài khoản trước.
- Nháp hoàn tiền và lịch sử trợ lý có khóa lưu trữ riêng cho từng tài khoản mẫu. Khóa lịch sử/nháp cũ trước khi có đăng nhập **không bị xóa và không tự chia sẻ** cho tất cả vai trò mới.
- Đăng xuất có xác nhận; nhắc riêng khi phiếu hoàn tiền còn thay đổi chưa lưu. Nháp truyền thông/gian hàng chỉ tồn tại trong bộ nhớ phiên và có thể mất khi đăng xuất.

## Không nhầm với bảo mật production

Đây là **mô phỏng phía frontend**. Bộ chọn tài khoản và sessionStorage không xác thực danh tính. Dữ liệu mẫu vẫn nằm trong bundle JavaScript, vì vậy ẩn menu/guard URL không bảo vệ dữ liệu thật khỏi người có quyền truy cập trình duyệt.

Khi nối backend, server phải xác thực và kiểm quyền trên từng yêu cầu, áp dụng scope và maker-checker độc lập với dữ liệu client; không gửi dữ liệu ngoài quyền xuống frontend. Tham chiếu: [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).

Các trang dự án, cư dân và tài chính tổng hợp vẫn ghi “Chưa triển khai”. Màn tài khoản/quyền và báo cáo là giao diện xem dữ liệu mẫu, chưa có quản trị người dùng, audit thật hoặc quyền xuất dữ liệu. Thao tác trình/phê duyệt hoàn tiền chỉ mô phỏng phản hồi, không cập nhật quy trình backend.

## Tệp chính và kiểm thử

Lượt kiểm chứng 09/09/2026: build thành công; **40 kiểm thử logic, 74 kiểm tra giao diện vai trò, 83 kiểm tra hồi quy desktop và 53 kiểm tra Green Assistant đều đạt**. Ba bộ UI đã chạy lại trên bản build preview, không ghi nhận lỗi JavaScript runtime trong các luồng được kiểm thử. Kiểm tra này không phải nghiệm thu phân quyền/backend thật.

- `src/data/staffRoles.js`: tám tài khoản mẫu, cấu hình menu/quyền, lọc dữ liệu.
- `src/components/staff/`: đăng nhập chung, dashboard, bảng tài khoản/quyền, báo cáo và chứng từ chỉ đọc.
- `src/App.jsx`: phiên mẫu, điều hướng và kiểm tra trước khi render/thao tác.
- `npm test`: kiểm thử logic, gồm phiên lỗi, scope, maker-checker, tách lịch sử.
- `npm run test:staff`: kiểm tra đăng nhập, tám dashboard/menu, deep link, tìm kiếm, đọc-only, đổi tài khoản, nháp/lịch sử và cửa sổ desktop.
- `npm run test:ux`, `npm run test:assistant`: kiểm thử hồi quy đã cập nhật để đăng nhập bằng tài khoản có quyền phù hợp; không bỏ qua guard mới.
- Ảnh và kết quả: `artifacts/staff/`. Thư mục này không đưa vào Git.

Thiết kế áp dụng ui-ux-pro-max và frontend-design: giữ nhận diện xanh, font hệ thống desktop, nội dung theo vai trò, focus/bàn phím và trạng thái ngoài quyền. Không áp dụng gợi ý landing page hoặc palette khác của kết quả tìm kiếm cho sản phẩm hiện có.
