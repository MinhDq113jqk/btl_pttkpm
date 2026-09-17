# R7 — Review kỹ thuật một lượt

## Cách hiểu và phạm vi

Kho mã hiện chưa có baseline/release ID chính thức tên `R7`. Vì vậy lượt này
được ghi nhận như một review kỹ thuật của V1 Parcel Task 5, dựa trên HEAD
`0015`, các API Parcel Desk, frontend Parcel Desk và bằng chứng PostgreSQL cô
lập. Đây không phải independent review, Gate C hay production sign-off.

## Kết quả review

| Hạng mục | Kết quả | Ghi chú kiểm tra |
|---|---|---|
| Tenant/site/building scope | PASS | `UserContext` server-derived; out-of-scope là `404 ERR-SCOPE-NOTFOUND`; role không đủ là `403` |
| State transition và retry | PASS | Row lock + `expected_version`; `Idempotency-Key` theo actor/site/operation; terminal exception không mở lại |
| Case source invariant | PASS sau sửa | Case chỉ mở ở `HANDED_OVER` hoặc `RETURNED/LOST/DAMAGED`; UI ẩn command khi parcel còn `RECEIVED/READY_FOR_PICKUP` |
| Incident linkage | PASS sau sửa | Unique theo parcel; link cập nhật `updated_by_id`, tăng `version`, ghi before/after audit |
| Snapshot lịch sử | PASS | Receive → handover giữ nguyên identity/carrier/contact/location/time snapshot |
| Evidence security | PASS | PNG/JPEG magic bytes + MIME + size; private path; signed token kiểm tra account/site/tenant/parcel/attachment; download `no-store` |
| Audit/correlation | PASS | Parcel/Case/Incident/Attachment cùng timeline; Golden Flow kiểm correlation ID cố định |
| Frontend API client | PASS sau sửa | Download signed link dùng closure-safe helper, không phụ thuộc binding `this`; object URL chỉ revoke qua lifecycle cleanup |
| Migration/schema | PASS local | `0014 -> 0015`, downgrade fail-closed khi còn dữ liệu liên kết, `alembic check` không drift |

## Findings đã xử lý trong lượt này

1. **Case mở quá sớm**: endpoint trước đây nhận parcel `RECEIVED`; đã thêm
   `assert_case_source()` và trạng thái UI tương ứng.
2. **Incident link không phản ánh optimistic version/actor**: đã cập nhật
   `updated_by_id`, tăng `version` và đưa version vào audit after-data.
3. **Frontend signed download phụ thuộc `this`**: đã tách helper lexical để
   lời gọi destructure vẫn an toàn.
4. **Preview evidence revoke URL hai lần**: đã giao cleanup cho React effect,
   tránh revoke trùng khi đổi parcel/đóng preview.

## Residual / không thuộc blocker code

- Evidence vẫn dùng private filesystem local; chưa có object storage ngoài,
  malware scanner hoặc provider notification.
- Chưa có load/concurrency benchmark cho 10 người; test hiện chứng minh khóa
  DB/idempotency ở mức integration.
- `R7` chưa được định nghĩa trong `roadmap_v2.md`; cần PO/giảng viên xác nhận
  tên release và AC nếu muốn gọi đây là một Gate độc lập.

## Verdict

**PASS về mặt code cho phạm vi V1 Parcel Task 5, sau kiểm chứng local.** Không
được suy diễn verdict này thành Gate C, production-ready, Aiven deployment hay
review độc lập. Evidence chính nằm tại
[V1_PARCEL_TASK5_EXIT_EVIDENCE.md](V1_PARCEL_TASK5_EXIT_EVIDENCE.md).
