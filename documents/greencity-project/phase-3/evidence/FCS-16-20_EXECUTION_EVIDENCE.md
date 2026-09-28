# Evidence FCS-16 đến FCS-20 — payment replay, submission gate và final audit

- **Ngày kiểm tra:** 2026-09-27; **cập nhật local rehearsal:** 2026-09-28
- **Checkout:** `_pttkpm` working tree; chưa commit/push
- **Phạm vi:** kiểm chứng local trên candidate hiện tại. Raw
  `documents/greencity-project/excel-data` chỉ được đọc local và không được
  chép vào evidence, log, database dùng chung hoặc review context.
- **Final status:** `NOT READY FOR SUBMISSION`

## FCS-16 — Payment replay và đối soát AR

Implementation đã hoàn tất ở boundary domain dùng chung:

- `backend/app/services/billing.py` có `receive_payment_command` và
  `match_unmatched_payment_command`; API và loader dùng cùng command thay vì
  insert trực tiếp payment/ledger.
- `backend/app/services/submission_data_operational_replay.py` replay
  allocated, partially allocated, unmatched, overpayment credit và retry
  idempotent; kiểm tra invoice/outstanding/AR theo cùng scope.
- `backend/scripts/load_submission_data.py` gọi payment replay ở stage `replay`
  và `all`; `all` cũng gọi FCS-12 Service Request/Work Order replay.
- `backend/scripts/submission_data_reconcile.py` được gọi trước commit của
  `apply` và trong `verify`/retry; kiểm từng invoice/item, payment/allocation,
  unmatched/credit và AR theo business key/scope. Chỉ trả số đếm và hai cờ
  chênh lệch `invoice_delta_vnd=0`, `ar_delta_vnd=0` sau khi toàn bộ check pass.
- `backend/tests/test_submission_data_payment_replay.py` kiểm tra 4 trạng thái,
  credit và AR delta bằng `0 VND`; assertion được scope theo tenant để không
  lẫn dữ liệu của test module khác.
- `backend/tests/test_submission_data_reconcile.py` có 5 focused synthetic
  tests, gồm duplicate invoice oracle, thiếu Work Order FCS-12, cleaning status
  sai và AR drift; `5 passed` vào 2026-09-27.

Kết quả kiểm tra không chứa dữ liệu nguồn:

```text
Full isolated PostgreSQL regression sau sửa Security: 376 passed, 1 skipped, 2 warnings (90.14s)
Synthetic clean DB rehearsal: stage=all, 12 workbooks/101 rows, dry-run/apply/verify/retry PASS
Migration 0018 / empty DB / repeat, seed/repeat, schema drift, forced password rotation, PostgreSQL shutdown: PASS
Historical FCS-16 targeted run: 1 passed, 313 deselected, 2 warnings
```

Summary log được giữ cục bộ ngoài gói nộp tại
`.local/submission-data/isolated-full-post-security.log`. Warning thư viện chứa
đường dẫn máy, nên log không được đưa vào package.

Hai warning là deprecation warning của FastAPI/Starlette TestClient và AnyIO;
không làm fail test. Số `313 passed` trong log lịch sử là trước các thay đổi đối
soát/date-only; full regression working tree mới đã pass `376 passed, 1 skipped,
2 warnings` sau khi sửa phạm vi quyền Security. Synthetic pack 12 workbook/101
dòng đã PASS `stage=all` dry-run, apply, verify và retry trên PostgreSQL cô lập
qua `scripts.test_submission_pack_isolated`.
`invoice_delta_vnd=0`/`ar_delta_vnd=0` ở code là kết quả chỉ được xuất sau khi
kiểm tra pass. Finance API/browser readback sau restart đã đạt trên DB tổng hợp;
FCS-16 giữ `PARTIAL` đến khi xác nhận trên package candidate cuối. User chọn synthetic
pack cho demo local; raw onboarding vẫn bị chặn bởi 35 lỗi thời gian nguồn và
không được coi là đã nhập dữ liệu thật.

## FCS-17 — Gói demo synthetic và ranh giới dữ liệu thật

User/Owner chọn gói synthetic làm dữ liệu demo cho bài nộp. Candidate có 12
workbook/101 dòng, `synthetic_manifest.json` gắn nhãn `SYNTHETIC_TEST_ONLY`
và ảnh `synthetic_evidence/`; các file này được tạo độc lập với raw source.
Isolated PostgreSQL runner đã PASS dry-run/apply/verify/retry. Bốn test targeted
cho anonymizer PASS; chạy trên raw hiện trả `SOURCE_PREFLIGHT_BLOCKED` và không
tạo output. Package-content PII/secret scan trên candidate cuối còn chờ.

User/Owner đã duyệt DP-01..DP-05 ngày 2026-09-27 cho luồng dữ liệu thật sau
khi sửa nguồn. Raw preflight read-only lúc `2026-09-28T03:06:20Z` trên 12
workbook/101 dòng có checksum đúng, 0 orphan, nhưng 30
`FUTURE_HISTORICAL_EVENT` và 5 `FUTURE_TERMINAL_EVENT` (35 ERROR), cộng 47
`FUTURE_SCHEDULE` warning. Chưa có gói local validation suy ra từ raw. Công cụ
anonymizer chỉ được phép tạo `LOCAL_VALIDATION_ONLY` với
`distribution_allowed=false`; không đưa raw workbook, output đó hoặc reverse
mapping vào Git/gói nộp và không gọi synthetic là dữ liệu thật đã ẩn danh.

Preview package đã scan 409 file: 0 đường dẫn cấm, 0 `.env`, 0 Windows user
path, 0 private/API/JWT/Bearer/PIN literal. Email thuộc miền reserved `.test`;
số điện thoại literal chỉ ở test anonymizer; DSN là ví dụ hoặc code động.
Exporter loại file `.log`, `.result` và `.txt` historical evidence khỏi package,
giữ source evidence tại checkout. Đây là kết quả preview trước digest cuối.

Trạng thái: **`PARTIAL`** — đường demo synthetic kiểm thử được; còn scan gói
cuối sau khi tài liệu được cập nhật. Luồng raw-derived vẫn bị chặn ở nguồn.

## FCS-18 — Clean import và GF-01..08

Các suite Golden Flow frontend đã chạy pass với deterministic API fixtures:

```text
GF-01..GF-08: all browser suites PASS
```

Isolated PostgreSQL runner đã migrate một DB mới và PASS synthetic `stage=all`
dry-run/apply/verify/retry với 12 workbook/101 dòng. Real-backend browser
harness nạp bộ tổng hợp vào DB disposable, restart backend, verify lại và đạt
GF-01/02 **13/13** kiểm tra cùng GF-03..08 **85/85** kiểm tra. Các luồng sau
restart có thao tác pass/rework, incident ACK/close, PIN đúng/sai/exception,
payment/credit/unmatched và cư dân đọc lại cùng invoice/payment. Năm nhóm KPI
đối chiếu drill-down/audit với cùng `as_of`; browser không có JavaScript error.
JSON evidence báo `findings: []`.

Liên kết 7 tài khoản cư dân trong demo dùng sidecar
`synthetic_resident_links.json` khai báo tường minh, chỉ chạy trên PostgreSQL
loopback disposable với `APP_ENV=test`; chạy lặp không tạo liên kết trùng.
Sidecar không suy đoán liên kết người dùng trong raw `excel-data`.

Trạng thái: **`PARTIAL`** — local synthetic rehearsal sau restart đã đạt;
chưa chạy lại cùng package candidate digest cuối.

## FCS-19 — README, package và clean-clone rehearsal

Đã xác nhận trên working tree và các candidate rehearsal trung gian:

```text
Frontend unit/API/link-checker fixture tests: 58 passed, 0 failed (preview)
Production build: PASS (1,625 modules transformed) trên preview mới
FS-05 Markdown: PASS (51 files, 163 targets, marked 17.0.5) trên working tree
Python lockfile install + pip check: PASS trên candidate mới
Backend pytest: 194 passed, 158 skipped, 0 warnings trên candidate mới
Frontend npm ci: PASS (141 packages) trên candidate mới
Assistant source/bundle secret scan: PASS (13 source, 9 bundle files)
Golden Flow fixture runner: PASS (GF-01..GF-08)
git diff --check: PASS
```

README, lockfile và các command setup/preflight/load/verify/reset đã có trong
candidate. Candidate đầu bị loại vì thư mục tạm pytest và link screenshot
local lọt package; `.gitignore`, exporter và tài liệu đã sửa. Preview tiếp theo
có 410 file, 0 forbidden path, synthetic 12/101, sidecar resident và manifest.
Đã xác nhận `npm ci --offline` 141 package/0 vulnerability, `npm test` 58/58,
build 1.625 module trên preview. 47 email đều ở miền `.test`, 3 số điện thoại
nằm trong targeted anonymizer test; 9 DSN là ví dụ/code động. Full isolated
regression và browser/restart gate trên candidate digest cuối còn chờ;
`dist`, `node_modules`, raw data và credential local không thuộc gói nộp.

Exporter loại historical `.log`/`.result`/`.txt` khỏi gói nhưng Git HEAD vẫn
track chúng. Vì chưa stage/commit/push, chỉ gói xuất bằng exporter có ranh giới
privacy này; không dùng `git clone` của HEAD làm gói nộp. Local review còn đang
kiểm fail-closed đối với file untracked mới trước khi chốt digest.

Trạng thái: **`PARTIAL`** — package rehearsal pass nhiều bước, nhưng chưa đạt
DoD clean-clone và các gate cùng synthetic candidate cuối.

## FCS-20 — Review độc lập, final audit và verdict

Code audit local và security/source scans hiện có. Yêu cầu review Antigravity
với diff/context code đã lọc bị cơ chế auto-review từ chối trước khi gửi, vì
chưa có ủy quyền rõ cho việc truyền mã nguồn nội bộ tới dịch vụ bên ngoài.
Không retry hoặc gửi vòng qua kênh khác. Local review đang xử lý thêm finding
Security và exporter; không thay thế review độc lập. Chưa có owner sign-off hoặc
Final Submission Gate pass. Do đó không ghi `STATUS: PASS` và không chuyển toàn
bộ FCS-01..20 sang `DONE`.

Trạng thái: **`BLOCKED`** — phụ thuộc FCS-17, FCS-18, FCS-19 và reviewer /
User/Owner approval.

## Kết luận

FCS-16 đã đạt implementation/local verification. FCS-17 và FCS-18 đã có
đường demo synthetic và GF-01..08 sau restart trên working tree; package digest
cuối và privacy scan còn chờ. Raw-derived onboarding vẫn chờ sửa nguồn. FCS-19
mới đạt một phần; FCS-20 chưa thể kết luận.
Final status giữ nguyên `NOT READY FOR SUBMISSION`.
