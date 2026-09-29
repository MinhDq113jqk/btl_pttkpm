# GreenCity — Walkthrough demo theo vai trò

Tài liệu này dùng cho bản đồ án local và gói nộp. Demo phải chạy trên database
development/test hoặc PostgreSQL disposable, với dữ liệu synthetic được commit tại
`backend/tests/fixtures/submission_data/synthetic/`. Không dùng raw `excel-data`,
không dùng database chia sẻ và không ghi credential vào slide, log hoặc Git.

## 1. Chuẩn bị

1. Làm theo `README.md` ở repository root để cài backend/frontend từ checkout sạch.
2. Tạo credential demo bằng `backend/scripts/new_demo_credentials.ps1`; giữ file
   credential ngoài repository.
3. Nếu cần kiểm chứng đầy đủ thay vì demo thủ công, chạy
   `backend/scripts/phase3_real_backend_browser.py` với `PHASE3_REAL_BROWSER=1`.
4. Trước khi bắt đầu demo, mở health endpoint backend và frontend, sau đó đăng nhập
   bằng credential được provision riêng cho buổi demo.

Không cần sửa bảng PostgreSQL bằng tay. Nếu cần quay về trạng thái sạch, tạo lại
cluster/database disposable rồi migrate/seed/import lại.

## 2. Thứ tự demo khuyến nghị

### GF-01 — Auth, session và quyền

- Đăng nhập bằng một tài khoản staff đã được provision.
- Nếu là lần đăng nhập đầu, hoàn tất đổi mật khẩu bắt buộc.
- Xác nhận menu được sinh từ role/scope server trả về.
- Nếu tài khoản có nhiều site, đổi site và kiểm tra menu/dữ liệu thay đổi theo scope.
- Đăng xuất và xác nhận phiên cũ không còn sử dụng được.

Kết quả cần thấy: không có credential mẫu trên UI; role khác nhau không tự mở rộng
quyền bằng dữ liệu phía client.

### GF-02 — Resident request → CSKH → Work Order

Vai trò: resident → CSKH → technical lead/technician.

- Resident tạo yêu cầu dịch vụ.
- CSKH xem yêu cầu, triage và mở Work Order.
- Technical lead phân công kỹ thuật viên.
- Kỹ thuật viên start, hoàn tất checklist/evidence và submit.
- Người có quyền nghiệm thu/đóng; resident reload và đọc lại trạng thái đã lưu.

Kết quả cần thấy: trạng thái vẫn tồn tại sau reload; retry không tạo bản ghi trùng;
role sai bị từ chối.

### GF-03 — Maintenance

Vai trò: technical lead/technician.

- Mở Asset/Maintenance.
- Tạo hoặc chọn Asset và Maintenance Plan.
- Chạy scheduler/occurrence theo dữ liệu được cấp.
- Xử lý Work Order phát sinh.
- Mở Asset history và xác nhận occurrence/Work Order/history tham chiếu cùng Asset.

Kết quả cần thấy: chạy scheduler lặp không sinh occurrence/Work Order trùng.

### GF-04 — Cleaning

Vai trò: director/cleaning.

- Tạo ca/tuyến và task.
- Assign, start, hoàn thành checklist rồi submit.
- Trình diễn một nhánh PASS và một nhánh checklist FAIL.
- Với FAIL, xác nhận hệ thống tạo rework Work Order/Case và có thể đọc lại sau reload.

### GF-05 — Security

Vai trò: director/security.

- Tạo/đọc ca an ninh, patrol point và thực hiện check-in.
- Tạo incident mức cao.
- Ghi evidence, transition, acknowledgement đúng vai trò rồi close.
- Kiểm audit timeline và thử truy cập bằng một role không có quyền.

Kết quả cần thấy: role không phù hợp nhận từ chối; actor/state/audit được lưu.

### GF-06 — Parcel

Vai trò: CSKH/security theo scope được cấp.

- Intake parcel trên building/unit được phép.
- Chuyển trạng thái ready.
- Thử PIN sai để thấy bị từ chối mà không bàn giao.
- Thực hiện PIN đúng hoặc exception path.
- Mở Case/timeline/evidence liên quan.

Kết quả cần thấy: PIN/plaintext hash không xuất hiện trong UI/log/API response; retry
không bàn giao hai lần.

### GF-07 — Billing và resident billing

Vai trò: accountant → resident.

- Mở Fee Policy/Accounting Period/Billing Run/Invoice.
- Ghi nhận manual payment; nếu thiếu account/code, kiểm unmatched queue và match.
- Allocate payment; nếu thừa, kiểm Overpayment Credit.
- Đăng nhập resident tương ứng để xem invoice/payment/summary.

Kết quả cần thấy: invoice snapshot không đổi sau phát hành; payment retry không sinh
bản ghi trùng; không có refund payout giả.

### GF-08 — Dashboard → drill-down → audit

Vai trò: director/admin.

- Mở dashboard điều hành.
- Chọn từng KPI và drill-down.
- Từ source row mở audit timeline.
- Xác nhận dashboard, drill-down và audit dùng cùng `as_of`/scope.

Kết quả cần thấy: KPI reconcile được với source rows; không có fake KPI/fallback mock.

## 3. Lệnh kiểm chứng trước khi bảo vệ

Từ `greencity-app/`:

```powershell
npm ci
npm run check:links
npm run check:source
npm test
npm run build
npm run test:golden-flows
```

Backend/PostgreSQL và browser thật dùng các runner trong README. Marker cuối của
real-backend rehearsal phải là:

```text
REAL_BACKEND_BROWSER_REHEARSAL: PASS
```

## 4. Những nội dung không trình bày như chức năng thật

- Refund payout/chargeback/VietQR hoặc đối soát ngân hàng ngoài phạm vi.
- Facebook/Meta, website analytics hoặc connection status giả.
- Amenities/parking/school/hospital nếu không có domain/API persistence.
- SSO, ERP, IoT, ANPR/FaceID hoặc AI tự thực hiện giao dịch.

Nếu giáo viên hỏi, trình bày các mục trên là ngoài phạm vi bản đồ án hiện tại thay
vì mở màn hình prototype hoặc dùng dữ liệu giả.
