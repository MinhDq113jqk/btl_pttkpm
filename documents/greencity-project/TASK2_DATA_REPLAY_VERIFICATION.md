# Task 2 — Xác minh data-replay trên PostgreSQL disposable

- **Ngày chạy:** 2026-10-01
- **Phạm vi:** 7 file implementation/test và `DATA_SOURCE_MANIFEST.json` được
  liệt kê tại [TASK1_SCOPE_AND_DATA_RECONCILIATION.md](TASK1_SCOPE_AND_DATA_RECONCILIATION.md).
- **Trạng thái:** `LOCAL_VERIFIED_NOT_FROZEN`
- **Candidate ID:** chưa có; working tree còn các HOLD item của Task 3/4.

## 1. Ranh giới kiểm thử

Raw source chỉ được kiểm tra bằng dry-run read-only. Runner tạo PostgreSQL/TLS
disposable, credential ngẫu nhiên và synthetic pack; không dùng `green_city`.
Cluster đã shutdown; không còn process PostgreSQL disposable từ Task 2. Log và
thư mục tạm của runner không thuộc evidence package và đã được dọn sau khi ghi
tóm tắt này.

## 2. Kết quả

| Kiểm tra | Kết quả chính xác | Ý nghĩa |
|---|---|---|
| Raw source + manifest | `FCS09_LOADER=PASS stage=all workbooks=12 rows=101 database_write=False` | Manifest khớp source hiện tại; lệnh chỉ đọc và không ghi database. |
| Focused slice | `16 passed, 3 skipped in 2.38s` | Gồm loader gate, security/parcel replay và service-request replay. Ba skip là các test integration khi không đặt `GREENCITY_ISOLATED_SECURITY_TESTS=1`; runner disposable bên dưới đặt biến này và bao phủ chúng. |
| Migration và schema | `0005`, `0007` đến `0018`, empty-DB migration/repeat, seed repeat và Alembic drift đều PASS | Xác minh schema/import path trên database sạch. |
| Synthetic rehearsal | `SUBMISSION_REHEARSAL=PASS stage=all workbooks=12 rows=101 dry_run=PASS apply=PASS verify=PASS retry=PASS` | Apply/verify/retry chỉ thực hiện với synthetic data trên database disposable. |
| Full regression | `379 passed, 1 skipped in 161.33s` | Chạy trên cùng disposable PostgreSQL sau rehearsal. Skip còn lại là test tạo symlink không khả dụng trong Windows test context; không có failed/error. |
| Shutdown | `Test PostgreSQL shutdown: PASS` | Cluster tạm đã dừng trước cleanup. |

Lượt focused đầu tiên dùng thư mục pytest dùng chung của Windows và có 4 setup
error `Access is denied`; đây là lỗi quyền thư mục tạm, không phải assertion
failure. Lượt rerun dùng `--basetemp` trong `backend/.test-runtime` đạt kết quả
ở bảng trên. Không sửa mã để che lỗi này.

Khi Task 5 rerun trên candidate cuối, evidence phải ghi lại từng skip/warning
và đánh giá tác động của chúng; các kết quả local tại đây không tự thỏa điều
kiện Final Submission Gate.

## 3. Kết luận và handoff

Task 2 xác nhận local cho tám file data-replay hiện tại. Nó không chứng minh
provenance từng row trong `green_city`, không freeze working tree, không thay
Final Submission Gate và không cho phép đưa raw Excel vào package.

Task 3 cần xử lý `greencity-app/tests/resident-ux.cjs` bằng frontend và
real-backend Golden-Flow evidence. Task 5 phải freeze một candidate rồi rerun
mọi gate trên đúng candidate đó.
