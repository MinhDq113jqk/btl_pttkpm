# R5 UI/API demo — Dashboard, Audit và Notifications

Tài liệu này là kịch bản trình diễn **local** cho Task 3. Nó không xác nhận
Gate B/C, Aiven/production, provider Email/SMS/Push thật, hay review độc lập.
Không đưa password, JWT, connection string hoặc correlation ID của môi trường
thật vào slide, log hay repo.

## Chuẩn bị an toàn

1. Dùng một PostgreSQL **cô lập** đã migrate/seed bằng quy trình test của dự án;
   không dùng Aiven hoặc DB vận hành cho demo.
2. Khởi động FastAPI local với `CORS_ORIGINS` chỉ chứa origin Vite local và
   `SECRET_KEY` chỉ nằm trong environment của tiến trình. Xác nhận `GET
   /api/v1/health` trả trạng thái tốt, không in cấu hình kết nối.
3. Trong terminal frontend, đặt `VITE_API_BASE_URL` tới API local (ví dụ
   `http://127.0.0.1:8000/api/v1`) cho **một** phiên terminal, rồi chạy Vite.
   Kiểm tra Network chỉ gọi endpoint `/api/v1/*`; token phải chỉ nằm trong RAM.
4. Chuẩn bị một tài khoản `director` trong seed local và ít nhất một event
   outbox/notification phù hợp. Người trình diễn tự nhập thông tin đăng nhập;
   kịch bản này không chứa thông tin xác thực.

## Kịch bản 6–8 phút

1. Đăng nhập `director`. Xác nhận site, role và menu là dữ liệu phiên do
   `/auth/me` cấp; không tự sửa scope bằng DevTools.
2. Tại Dashboard, ghi lại mốc UTC `as_of`. Đợi hết loading, sau đó xác nhận đủ
   5 KPI: SLA, maintenance, cleaning rework, incident mở và AR debt.
3. Chọn một KPI có bản ghi nguồn. Trong drill-down, kiểm tra mốc cutoff hiển
   thị giống Dashboard, danh sách source rows và trạng thái empty (nếu KPI là
   0). Mở `Audit` của một row: request phải mang `resource_type`, `resource_id`
   và cùng `as_of`.
4. Trong Audit Explorer, đối chiếu resource/timeline/actor; dùng Escape để
   đóng. Tiêu điểm phải trở lại control đã mở dialog.
5. Mở Thông báo: xác nhận Inbox tải từ API và thao tác “đã đọc” cập nhật UI.
   Với `director`, mở Outbox và kiểm tra trạng thái delivery. Chỉ retry một
   event thất bại đã chuẩn bị; trong Network, hai lần retry của cùng intent phải
   giữ nguyên `Idempotency-Key` nếu lần đầu mất response.
6. Tắt mạng của browser hoặc mô phỏng mất kết nối. Dashboard/Notifications phải
   báo offline hoặc lỗi có mã đối chiếu và không hiển thị dữ liệu mock như dữ
   liệu mới. Khôi phục kết nối, bấm “Kiểm tra lại”/“Thử lại”, rồi xác nhận UI
   phục hồi.

## Bằng chứng và giới hạn

- `npm run test:dashboard` và `npm run test:notifications` kiểm tra UX bằng
  transport Playwright intercept/mock; chúng chứng minh state, scope hiển thị,
  keyboard và request shape, **không** phải live backend end-to-end.
- Runner isolated PostgreSQL của backend kiểm chứng route/API, scope,
  idempotency và migration trên DB disposable. Chạy từ `backend`:

  ```powershell
  .\.venv\Scripts\python.exe -m scripts.test_isolated --pg-bin 'C:\Program Files\PostgreSQL\18\bin' --openssl 'C:\Program Files\Git\usr\bin\openssl.exe'
  ```

- Một lần demo live chỉ được ghi là “Implemented & Verified Local” khi API và
  Vite đều trỏ vào local disposable environment đã chuẩn bị, các bước trên có
  ảnh/video redacted, và không có console error. Không suy ra deployment hay
  Gate C từ kịch bản này.
