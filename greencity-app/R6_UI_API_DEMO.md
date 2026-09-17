# R6 UI/API demo — Resident Self-Service

Kịch bản này dùng cho demo **local** với dữ liệu giả. Nó không phải Gate C,
production/Aiven, payment gateway thật hoặc bằng chứng browser-to-PostgreSQL.
Không ghi password, JWT, connection string hay PII vào slide/log/repository.

## Chuẩn bị

1. Từ `backend/`, chạy runner PostgreSQL cô lập trong
   [R6_RELEASE_EVIDENCE.md](../backend/R6_RELEASE_EVIDENCE.md), sau đó khởi động
   FastAPI với `SECRET_KEY` chỉ nằm trong environment của process.
2. Đặt `VITE_API_BASE_URL` tới API local (ví dụ
   `http://127.0.0.1:8000/api/v1`) và chạy Vite ở port `3000`.
3. Dùng account seed `resident_west`; người trình diễn tự nhập mật khẩu demo,
   không lưu thông tin xác thực vào tài liệu này.

## Luồng demo 5–7 phút

1. Đăng nhập và xác nhận `/auth/me` trả role `resident`, site hiện hành và
   `resident_unit_ids`; Portal được chọn từ role server, không từ menu tự khai.
2. Tab **Yêu cầu dịch vụ**: mở form, chọn unit/category do
   `/resident/service-request-options` trả về, tạo một yêu cầu. Có thể mô phỏng
   mất response rồi bấm lại; hai request phải giữ cùng `Idempotency-Key` và chỉ
   xuất hiện một yêu cầu sau khi API thành công.
3. Mở chi tiết: kiểm tra status/SLA/version, timeline audit và upload ảnh
   PNG/JPEG. File sai loại hoặc quá giới hạn phải báo lỗi/quarantine; không có
   storage path trong response.
4. Tab **Công nợ & hóa đơn**: ghi lại một `as_of` UTC; summary, invoices và
   payments phải gửi cùng mốc. Xác nhận số tiền hiển thị integer VND, invoice
   item là read-only và không có thao tác ghi payment/ledger.
5. Tab **Thông báo**: xác nhận inbox chỉ của account hiện tại, xem correlation
   ID và đánh dấu đã đọc. Refresh phải giữ trạng thái đã đọc; lỗi mạng phải hiện
   correlation/error, không tự đổ mock data.
6. Thu hồi quan hệ Person--Unit hoặc đổi site trong môi trường test, gọi lại API
   và xác nhận request bị chặn `404 ERR-SCOPE-NOTFOUND`. Không sửa DB tay trong
   luồng demo; mọi setup phải đi qua seed/migration/API hợp lệ.

## Bằng chứng

```powershell
Set-Location ..\backend
.\.venv\Scripts\python.exe -m scripts.test_isolated --pg-bin 'C:\Program Files\PostgreSQL\18\bin' --openssl 'C:\Program Files\Git\usr\bin\openssl.exe'

Set-Location ..\greencity-app
npm test
npm run build
npm run test:resident
```

Snapshot ngày 16/09/2026: backend **238 passed, 2 warnings**, frontend
**63/63**, Resident UX **17/17**, build PASS. Browser UX intercept API transport
để kiểm state/request shape; không thay thế acceptance HTTP trên PostgreSQL
disposable. Evidence chi tiết ở [../backend/R6_CONTRACT.md](../backend/R6_CONTRACT.md)
và [../backend/R6_RELEASE_EVIDENCE.md](../backend/R6_RELEASE_EVIDENCE.md).
