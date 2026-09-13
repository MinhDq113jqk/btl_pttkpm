# GreenCity — Frontend Integration R2

Ngày cập nhật: 12/09/2026. Thư mục chuẩn để tiếp tục phát triển là
`C:\Users\LEGION\btl\_pttkpm\greencity-app`.

## Phạm vi đã nối

Luồng phiên hiện tại là:

1. `POST /api/v1/auth/login` với duy nhất `username`, `password`.
2. Lưu access token trong bộ nhớ của API client, không ghi vào source,
   `localStorage`, `sessionStorage` hay dữ liệu mock.
3. Luôn gọi `GET /api/v1/auth/me`; menu, nhãn vai trò và site hoạt động chỉ được
   tạo từ response này. Trường `user` trong response login không phải nguồn quyền.
4. Với role được backend cho phép, gọi
   `GET /api/v1/service-requests?status=&page=&page_size=` và hiển thị danh sách
   đọc-only.
5. Với role Unit 360° được backend hỗ trợ, gọi
   `GET /api/v1/units/{unit_id}/360`; chỉ Unit ID nằm trên path, không có query
   scope từ frontend.

Frontend không gửi `tenant_id`, role hay building scope. Ngoại lệ có chủ đích là
`POST /auth/switch-site`: client chỉ gửi `{site_id}` đã có trong danh sách
allowed sites từ `/auth/me`; backend xác minh lại membership/scope và cấp token
mới, rồi client bắt buộc gọi lại `/auth/me`. API client chỉ cho phép ba query
parameter `status`, `page`, `page_size` cho danh sách request. Backend vẫn là
lớp cưỡng chế quyền cuối cùng.

## Ranh giới có chủ đích

- Token mất khi reload hoặc đóng renderer; người dùng phải đăng nhập lại. Chưa có
  contract refresh token hoặc kho credential an toàn của Electron.
- Phiên thật chỉ mở Tổng quan, Công việc & Yêu cầu, Tra cứu Căn hộ 360° và Thông
  báo tùy role từ `/auth/me`. Các màn mô phỏng tài chính/phân quyền cũ không được
  mount từ menu hoặc deep link của phiên thật.
- Role `cleaning` và `security` không gọi nhầm Service Request vì endpoint hiện
  không cấp quyền cho hai role này.
- Unit 360° là lát cắt đọc-only: CSKH/Admin/Giám đốc/Kế toán/Trưởng kỹ thuật/An
  ninh có thể thấy menu theo role; KTV chưa thấy menu vì backend chưa cấp Unit
  scope dựa trên Work Order assignment cho endpoint này.

## Trạng thái UI và lỗi

Danh sách yêu cầu và Unit 360° có loading, empty, lỗi mạng và nút thử lại.
`401` xóa token trong bộ nhớ và đưa về đăng nhập. `ERR-SCOPE-NOTFOUND` có thông
báo riêng. Correlation ID được gửi bằng `X-Correlation-ID` và hiển thị trong lỗi
để đối chiếu log; không hiển thị token hay nội dung nhạy cảm.

## Chạy cục bộ

Trong chế độ development, Vite chuyển tiếp `/api/v1` tới backend cục bộ tại
`http://127.0.0.1:8000`, nên chỉ cần chạy:

```powershell
npm run dev -- --host 127.0.0.1
```

Nếu backend ở địa chỉ khác, đặt `VITE_API_BASE_URL` trước khi build/chạy. Khi
không đặt, client dùng `/api/v1` trên cùng origin — phù hợp với Vite proxy,
reverse proxy hoặc Electron host có định tuyến tương đương.

## Kiểm thử

```powershell
npm test
npm run build
npm run test:staff
npm run test:ux
npm run test:assistant
```

- `npm test`: thứ tự login → me, Bearer header, query allow-list, Unit ID path,
  contract Unit 360°, 401, scope, network, role/menu mapping và adapter Service Request.
- `npm run test:staff`: smoke UI headless với API được kiểm soát, bao gồm các trạng
  thái Unit 360° idle/loading/success/network-retry/scope/401, projection cư dân
  và kiểm tra token không vào browser storage.
- `npm run test:ux`, `npm run test:assistant`: hồi quy bố cục desktop, deep link
  read-only, tìm kiếm, trợ lý trong phiên xác thực và việc reload làm mất token.
- Smoke PostgreSQL tách biệt dùng cluster TLS dùng một lần và credential ngẫu
  nhiên; không dùng database chia sẻ hay in connection secret.

Lần kiểm chứng local ngày 13/09/2026: `npm test` **50/50**, `npm run test:staff`
**28/28**, và `npm run build` pass. Đây là evidence UI/client local, không thay
thế review/Gate hoặc E2E với PostgreSQL live.

## Traceability AC-35

Sau switch-site, session revision loại response/401 của site cũ; workspace key
remount để reset page, filter, search, selection và Unit 360 state trước khi dữ
liệu site mới được hiển thị. Đây là bằng chứng local của AC-35; trạng thái Gate
và review không được suy diễn chỉ từ test frontend.
