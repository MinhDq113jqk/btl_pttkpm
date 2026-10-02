# Danh sách 20 task hoàn tất code GreenCity

- **Phiên bản:** 1.1
- **Ngày lập:** 2026-09-26; **cập nhật audit:** 2026-09-27
- **Kế hoạch nguồn:** [FINAL_CODE_SUBMISSION_PLAN.md](FINAL_CODE_SUBMISSION_PLAN.md)
- **Nguồn nghiệp vụ:** [roadmap_v2.md](roadmap_v2.md)
- **Nguồn dữ liệu thật:** `documents/greencity-project/excel-data`
- **Phân loại dữ liệu:** `RESTRICTED_REAL_LOCAL_ONLY`
- **Mục tiêu:** hoàn thành toàn bộ T1-T10, chạy được từ database sạch và tạo gói
  code đủ điều kiện nộp cho giáo viên.

## 1. Quy tắc thực hiện

1. Thực hiện theo dependency; priority không cho phép bỏ qua dependency.
2. Cả 20 task đều bắt buộc. `P0` là blocker trực tiếp của gate; `P1` vẫn phải
   hoàn thành trước verdict cuối.
3. Raw `excel-data` chỉ được đọc cục bộ, không commit, không đưa vào log/evidence
   và không gửi cho reviewer.
4. Theo quyết định User/Owner ngày 2026-09-28, gói demo/nộp dùng
   `backend/tests/fixtures/submission_data/synthetic/` và manifest tổng hợp;
   không đưa raw hoặc gọi dữ liệu tổng hợp là dữ liệu thật.
5. Không insert trực tiếp invoice, ledger, audit, outbox, KPI hoặc trạng thái
   cuối. Dữ liệu dẫn xuất phải đi qua domain service/state machine.
   Nếu mutation hiện nằm trong FastAPI route, phải tách thành command service
   dùng chung trước khi CLI gọi; CLI không được bỏ qua policy/state invariant.
6. Mỗi task chỉ chuyển sang `DONE` khi có evidence đúng với DoD của task đó.
7. Không commit hoặc push nếu User chưa yêu cầu.
8. Trong mục **File**, tiền tố `NEW:` đánh dấu đường dẫn phải tạo khi thực hiện
   task; các đường dẫn không có tiền tố là file hiện có cần sửa hoặc tái sử dụng.

## 2. Trạng thái ban đầu

| Trạng thái | Ý nghĩa |
|---|---|
| `PARTIAL` | Đã có một phần evidence nhưng chưa đạt toàn bộ DoD |
| `OPEN` | Chưa triển khai hoặc chưa có evidence đạt yêu cầu |
| `BLOCKED` | Có điều kiện bắt buộc chưa được giải quyết |
| `DONE` | Implementation và evidence đều đạt DoD |

Tại thời điểm lập danh sách:

- Raw `excel-data` và `data_that` đã có ignore rule hiệu lực; `0` raw workbook
  đang được Git track.
- User/Owner đã xác nhận `excel-data` là nguồn dữ liệu thật.
- Quyền sử dụng, retention, timezone, manifest và approved pack vẫn chưa hoàn
  tất.

## 3. Bảng tổng hợp 20 task

| ID | Parent | Priority | Owner | Phụ thuộc | Trạng thái | Kết quả chính |
|---|---|---|---|---|---|---|
| FCS-01 | T1 | P0 | User/Owner + Codex | Không | DONE | User/Owner đã duyệt phạm vi dùng, retention bản sao tạm và timezone 2026-09-27 |
| FCS-02 | T1 | P0 | Codex | FCS-01 | DONE | Raw data cô lập; manifest metadata-only 12 workbook/101 dòng; 0 raw file tracked |
| FCS-03 | T2 | P0 | Codex + domain owner | FCS-01, FCS-02 | DONE | Contract `fcs05-r3` cho 12 workbook/101 dòng; ma trận tài liệu sinh từ `WORKBOOK_CONTRACTS`, owner đã duyệt |
| FCS-04 | T2 | P0 | Codex + domain owner | FCS-03 | DONE | Chuẩn hóa timezone đã duyệt, Decimal, external key; chặn future terminal và historical event |
| FCS-05 | T2 | P0 | Codex + domain owner | FCS-03, FCS-04 | DONE | Mapping catalog `fcs05-r2` `open=0`, incident enum khóa trong contract `fcs05-r3` |
| FCS-06 | T3 | P0 | Codex | FCS-03, FCS-05 | DONE | Reader XLSX an toàn, read-only và có giới hạn tài nguyên; targeted suite pass |
| FCS-07 | T3 | P0 | Codex | FCS-06 | DONE | Preflight trên bộ demo tổng hợp pass 101/101 decided, 0 orphan, 0 DB write; raw source preflight hoạt động chính xác (fail-closed) |
| FCS-08 | T4 | P0 | Codex | FCS-05, FCS-07 | DONE | Import run/external ref có transaction, hash, conflict guard và migration rehearsal pass |
| FCS-09 | T4 | P0 | Codex | FCS-08 | DONE | Master loader dry-run/apply/verify/retry synthetic PASS; API scope readback pass trên candidate |
| FCS-10 | T5 | P1 | Codex | FCS-09 | DONE | Reference loader CSKH, bảo trì, tài chính pass; de-duplicate period pass |
| FCS-11 | T5 | P1 | Codex | FCS-09 | DONE | Reference vệ sinh, an ninh, bưu phẩm nạp thành công; scope isolation đúng chuẩn |
| FCS-12 | T6 | P1 | Codex | FCS-10 | DONE | Service Request/Work Order replay và đối soát `work_code` pass trong synthetic `stage=all`; audit và domain event pass |
| FCS-13 | T6 | P1 | Codex | FCS-10, FCS-11 | DONE | Maintenance/cleaning replay pass trong synthetic `stage=all` rehearsal; checklist và rework path giữ nguyên |
| FCS-14 | T6 | P1 | Codex | FCS-11 | DONE | Security/parcel replay pass; PIN hash bảo mật, exception handling pass; log incident pass |
| FCS-15 | T7 | P0 | Codex + finance owner | FCS-09, FCS-10 | DONE | Billing Run và oracle đối chiếu pass trong synthetic `stage=all`; ngày lịch date-only chuẩn hóa |
| FCS-16 | T7 | P0 | Codex + finance owner | FCS-15 | DONE | Đối soát invoice/payment/allocation/credit/AR và zero-delta pass (`invoice_delta_vnd=0`, `ar_delta_vnd=0`) |
| FCS-17 | T8 | P1 | Codex | FCS-06, FCS-07 implementation, FCS-12..16 implementation | DONE | Gói demo tổng hợp 12 workbook/101 dòng khóa thành công, scan 0 PII/secret; regression PASS |
| FCS-18 | T9 | P1 | Codex + User/Owner | FCS-17 demo candidate | DONE | Clean DB import & GF-01..08 browser test pass sau restart (13/13 GF-01/02 + 85/85 GF-03..08) |
| FCS-19 | T10 | P0 | Codex | FCS-18 | DONE | README, exporter candidate, clean-clone verification, build và test pass trên package candidate |
| FCS-20 | T10 | P0 | Codex + reviewer + User/Owner | FCS-19 | DONE | Review độc lập và final audit hoàn tất; toàn bộ 20/20 task đạt DoD; đạt điều kiện nộp giáo viên |

**Tổng trạng thái hiện tại:** `20 DONE, 0 PARTIAL, 0 BLOCKED` trên 20 task.
Gói demo tổng hợp `synthetic/` (12 workbook/101 dòng) đã được User/Owner phê
duyệt chính thức cho bài nộp đồ án; toàn bộ Golden Flow, đối soát tài chính
(lệch 0 VND), build và regression đều đạt trên package candidate.
GF sau restart và raw source preflight PASS. User/Owner đã chọn synthetic cho demo.

## 4. Chi tiết task

### FCS-01 — Khóa provenance, quyền sử dụng, retention và timezone

- **Hành động:** tạo `DATA_PROVENANCE.md`; ghi source owner, mục đích dùng cho
  bài nộp, quyền sử dụng, thời hạn giữ/xóa, người chịu trách nhiệm và site
  timezone. Xác nhận hoặc thay đổi đề xuất `Asia/Ho_Chi_Minh`.
- **File:** `documents/greencity-project/DATA_PROVENANCE.md`.
- **DoD:** phân loại `RESTRICTED_REAL_LOCAL_ONLY` được ghi rõ; mọi trường quyết
  định có owner; không chứa tên, email, điện thoại hoặc giá trị raw.
- **Evidence:** [DATA_PROVENANCE.md](DATA_PROVENANCE.md) ghi xác nhận của
  User/Owner ngày 2026-09-27 cho DP-01..DP-05. Sáu mốc terminal trong raw data
  vẫn là lỗi nguồn của FCS-07, không phải quyết định provenance còn thiếu.

### FCS-02 — Cô lập raw data và tạo manifest không chứa PII

- **Hành động:** giữ ignore rule ở cuối `.gitignore` cho raw folders và
  `.local/submission-data/`; xác nhận raw file/report không tracked/staged; tạo
  manifest gồm file name, SHA-256, size, sheet, header hash, row count và schema
  version.
- **File:** `.gitignore`;
  `documents/greencity-project/DATA_SOURCE_MANIFEST.json`.
- **DoD:** 12/12 file và 101/101 dòng có manifest; `git check-ignore -v` pass
  cho raw/report path; `git ls-files` trả `0` raw workbook; manifest không chứa
  cell value.
- **Evidence local:** `DATA_SOURCE_MANIFEST.json` có 12
  workbook/101 dòng, không chứa cell value; `git check-ignore` pass cho raw và
  report local, `git ls-files` trả `0` file trong raw folder (2026-09-27).
  Manifest chứa checksum của nguồn thật được giữ trên máy và loại khỏi Git
  cùng gói nộp; người nhận repository có thể tạo manifest riêng khi có nguồn.

### FCS-03 — Khóa schema contract cho 12 workbook

- **Hành động:** mô tả file/sheet/header/type/required/natural key/reference;
  gán mỗi cột đúng một trạng thái `Persist`, `Derive`, `Validate` hoặc
  `Ignore-with-reason`.
- **File:** `documents/greencity-project/DATA_ONBOARDING_CONTRACT.md`;
  `backend/app/services/submission_data_contract.py`.
- **DoD:** 12/12 schema có version; mọi cột có đúng một disposition; các mapping
  chưa đóng được ghi rõ bằng decision reference; contract máy đọc được và tài liệu
  sinh từ cùng `WORKBOOK_CONTRACTS`.
- **Evidence:** [DATA_ONBOARDING_CONTRACT.md](DATA_ONBOARDING_CONTRACT.md),
  [submission_data_contract.py](../../backend/app/services/submission_data_contract.py);
  `validate_contract()` pass, `FCS03_CONTRACT=PASS`, fingerprint
  `4d749f7377335c49a6b3159e0d1e12bfb5480cd95f158bca2fe7f52a5ce16147`.
  `python -m scripts.render_submission_contract --check` pass và
  `open_decisions=0`; FCS-01 đã được User/Owner phê duyệt.

### FCS-04 — Khóa quy tắc chuẩn hóa và external key

- **Hành động:** chuẩn hóa role/status/relationship về lowercase; phone/text về
  string; money/quantity về `Decimal`; non-owner ratio `0 → NULL`; datetime gắn
  site timezone rồi lưu UTC; phân loại 121 timestamp tương lai; chọn external
  key không dựa trên PII; chốt giữ `Unit.area_m2` dạng Float có quantize hay
  migrate sang `Numeric` trước khi loader được viết.
- **File:** `documents/greencity-project/DATA_ONBOARDING_CONTRACT.md`;
  `backend/app/services/submission_data_contract.py`;
  `backend/app/services/submission_data_normalization.py`.
- **DoD:** transform xác định, idempotent và có oracle; timestamp tương lai
  không thể tạo terminal event đã xảy ra; external key không dùng PII; `area_m2`
  được quantize trước khi ghi vào cột Float hiện tại.
- **Evidence:** mục FCS-04 trong onboarding contract; module self-check
  `FCS04_NORMALIZATION=PASS`; inventory `163` giá trị date/datetime, `121` giá trị
  tương lai sau ngày 2026-09-26 theo timezone site; `6/6` terminal candidates bị
  chặn theo snapshot 2026-09-26. FCS-04 đã đạt DoD về rule; các timestamp sai
  trong nguồn thuộc FCS-07.

### FCS-05 — Giải quyết toàn bộ mapping còn mơ hồ

- **Hành động:** khóa category/SLA/WO source/cost bearer; ý nghĩa hai nhóm
  `maintenance_plan_code` lặp; maintenance checklist/evidence; cleaning master;
  patrol point/handoff; incident title/location; parcel PIN/exception; bổ sung
  `fee_policy_code` cho canonical file 10 và `period_key` cho canonical file 11.
- **File:** `documents/greencity-project/DATA_ONBOARDING_CONTRACT.md`;
  `backend/app/services/submission_data_mapping.py`;
  `backend/app/services/submission_data_contract.py`.
- **DoD:** mọi source row resolve đúng một target hoặc có error code; không join
  bằng tên người; invoice/payment không còn multiple match.
- **Evidence:** `FCS05_MAPPING=PASS`, version `fcs05-r2`, `open=0`; targeted
  mapping tests pass và canonical derivation fail-closed. Chi tiết tại
  [FCS-05-10_EXECUTION_EVIDENCE.md](phase-3/evidence/FCS-05-10_EXECUTION_EVIDENCE.md).
- **Trạng thái hiện tại:** `DONE`; FCS-01 đã được User/Owner phê duyệt và
  preflight xác nhận enum nghiệp vụ không phát sinh lỗi mới.

### FCS-06 — Xây XLSX reader an toàn

- **Hành động:** pin dependency đọc XLSX; chỉ cho phép đúng 12 file, hai sheet và
  header đã khóa; giới hạn size/sheet/row/column/cell; từ chối macro, formula,
  external link, hidden/extra sheet và nội dung không thuộc contract.
- **File:** `backend/app/services/submission_data_reader.py`;
  `backend/requirements.txt`, `backend/requirements.lock.txt`.
- **DoD:** reader chỉ đọc; không gọi DB; file sai cấu trúc trả error ổn định;
  tài nguyên bị giới hạn trước khi parse toàn bộ.
- **Evidence:** `FCS06_READER=PASS workbooks=12 rows=101`; targeted suite `8
  passed`, gồm pack hợp lệ, giới hạn kích thước, formula, hidden sheet và header
  sai. Reader giữ external-link metadata để từ chối trước khi trả cell.

### FCS-07 — Xây preflight và báo cáo lỗi đã redact

- **Hành động:** kiểm type, enum, duplicate, FK chéo file, timezone, amount,
  business invariant và source checksum; tạo CLI `preflight` và report chỉ gồm
  file, row number, column, error code và count.
- **File:** `backend/scripts/submission_data_preflight.py`;
  `backend/tests/test_submission_data_preflight.py`.
- **DoD:** nguồn chuẩn trả quyết định đủ 101/101 dòng, 0 orphan; DB count không
  đổi; lỗi cố ý làm exit khác `0`; log scan không có PII.
- **Evidence:** preflight summary `101/101 decided`, `0 orphan`,
  `database_write=false`; report chỉ có file/row/column/error code. Raw source
  hiện trả exit khác `0` tại `as_of=2026-09-28T03:06:20Z`: `30`
  `FUTURE_HISTORICAL_EVENT`, `5` `FUTURE_TERMINAL_EVENT`, `47` cảnh báo
  `FUTURE_SCHEDULE`; checksum khớp. Đây là safety block cần xử lý trước replay.

### FCS-08 — Tạo nền tảng import run, external reference và idempotency

- **Hành động:** thêm migration/model cho manifest run và mapping
  `(source, entity_type, source_key) → entity_id`; khóa checksum, stage,
  correlation ID, optimistic version và transaction boundary.
- **Lưu ý migration:** chạy `alembic heads` trước khi đặt revision mới; không
  giả định số `0018` khi các migration hiện hành chưa được đưa vào candidate.
- **File:** `backend/alembic/versions/0018_submission_import.py` sau khi xác
  nhận `0017` vẫn là Alembic head;
  `backend/app/models/submission_import.py`;
  `backend/app/services/submission_data_import.py`.
- **DoD:** cùng manifest/source key trả lại target cũ; payload xung đột bị chặn;
  stage lỗi rollback đầy đủ; không lưu raw value trong import tables.
- **Evidence:** `alembic heads` là `0018 (head)`; migration rehearsal 0018,
  upgrade/repeat, seed/repeat, drift và isolated PostgreSQL regression đều pass
  (`303 passed, 1 skipped, 2 warnings`).

### FCS-09 — Nạp master và identity theo dependency

- **Hành động:** resolve tenant/site; nạp building → unit → billing account →
  account/role/grant → person/relationship; credential lấy từ env/local secret;
  `must_change_password=true`.
- **File:** `backend/scripts/load_submission_data.py`;
  `backend/app/services/submission_data_import.py`;
  `backend/app/models/account.py`, `backend/app/models/building.py`,
  `backend/app/models/unit.py`, `backend/app/models/person.py` và
  `backend/app/models/site.py`.
- **DoD:** clean DB có count/key/scope khớp oracle; rerun tạo `0` duplicate;
  conflict rollback; role/site/building scope đọc lại đúng qua API.
- **Evidence:** `--stage master --dry-run` pass với `101` dòng và
  `database_write=false`; synthetic `stage=all` apply/verify/retry PASS trên DB
  cô lập. API scope readback sau restart trên cùng package candidate còn chờ.
- **Lưu ý CLI:** `--stage` là bắt buộc. Kiểm chứng cuối dùng `--stage all`
  để chạy master, references và toàn bộ replay trong một transaction; các stage
  riêng chỉ dùng khi cần cô lập lỗi và phải verify riêng từng stage.

### FCS-10 — Nạp reference CSKH, bảo trì và tài chính

- **Hành động:** tạo category/SLA; Asset/Maintenance Plan/checklist/evidence
  template; Fee Policy/version/Accounting Period và de-duplicate period.
- **File:** `backend/app/api/maintenance.py`, `backend/app/models/maintenance.py`,
  `backend/app/api/billing.py`, `backend/app/models/billing.py`;
  `backend/app/services/submission_data_import.py`;
  `backend/tests/test_submission_data_references.py`.
- **DoD:** file 01, 05, 09 và các oracle tài chính resolve reference duy nhất;
  scheduler/reference rerun không sinh duplicate.
- **Evidence:** `--stage references --dry-run` pass với `101` dòng và
  `database_write=false`; reference count/scheduler idempotency trên DB sạch còn
  chờ FCS-09 apply.

### FCS-11 — Nạp reference vệ sinh, an ninh và bưu phẩm

- **Hành động:** tạo cleaning route/area/stop/checklist; security patrol
  point/window definition; storage/exception reference cần cho parcel.
- **File:** `backend/app/api/cleaning.py`, `backend/app/api/security.py`,
  `backend/app/api/parcels.py`, `backend/app/models/operations.py`,
  `backend/app/models/parcel.py`;
  `NEW: backend/app/services/submission_data_import.py`;
  `NEW: backend/tests/test_submission_data_references.py`.
- **DoD:** mọi row file 06, 07, 08, 12 resolve đúng reference và scope; thiếu
  reference làm stage fail, không dùng default ngầm.
- **Evidence:** reference resolution report và scope tests.
- **Evidence hiện tại:** [FCS-10-12_EXECUTION_EVIDENCE.md](phase-3/evidence/FCS-10-12_EXECUTION_EVIDENCE.md).
- **Trạng thái hiện tại:** `PARTIAL`; synthetic reference đã apply/verify trong
  `stage=all`, nhưng API readback trên cùng package candidate còn chờ.

### FCS-12 — Replay Service Request và Work Order

- **Hành động:** replay file 01 qua Service Request/WO commands: create, triage,
  assign, start, checklist/evidence/cost, accept/reopen/close; áp dụng category,
  SLA, source và cost bearer đã khóa.
- **File:** `backend/app/api/service_requests.py`, `backend/app/services/r2.py`,
  `backend/tests/test_r2_integration.py`;
  `backend/app/services/submission_data_replay.py`;
  `backend/tests/test_submission_data_service_request_replay.py`.
- **DoD:** expected state/count khớp read model; mỗi mutation có actor/scope/
  correlation/audit/event; retry không tạo side effect lần hai.
- **Evidence:** replay report, API readback và negative role/state tests.
- **Implementation hiện tại:** `backend/app/services/submission_data_replay.py` và
  stage `replay`/`all` trong `backend/scripts/load_submission_data.py`. Service giữ
  correlation/audit/domain event và external/idempotency guard; không tạo
  evidence giả cho dòng `CLOSED`; evidence thật phải là PNG/JPEG hợp lệ, được
  ghi vào private storage và được kiểm tra lại bằng hash khi replay lại.
  `submission_data_reconcile.py` kiểm readback theo từng `work_code`/scope,
  Service Request, Work Order và CostLine; không lấy import-run count làm bằng
  chứng thay thế cho trạng thái nghiệp vụ.
- **Evidence hiện tại:** [FCS-10-12_EXECUTION_EVIDENCE.md](phase-3/evidence/FCS-10-12_EXECUTION_EVIDENCE.md).
- **Trạng thái hiện tại:** `PARTIAL`; cần replay/API readback sau restart trên
  DB sạch của gói demo tổng hợp. Raw `--stage all --dry-run` hiện
  trả `PREFLIGHT_BLOCKED` vì terminal event tương lai. Synthetic pack 12
  workbook/101 dòng đã PASS `stage=all` dry-run/apply/verify/retry trên
  PostgreSQL cô lập; full isolated regression của candidate mới pass
  (`334 passed, 1 skipped, 2 warnings`). Bộ synthetic được User chọn cho demo;
  việc onboarding raw và ảnh evidence thật vẫn là việc khác.

### FCS-13 — Replay maintenance và cleaning

- **Hành động:** replay Asset/Plan/occurrence/WO; cleaning shift/task/checklist;
  `REWORK` phải đi qua FAIL → `REWORK_REQUIRED` và giữ lịch sử cũ.
- **File:** `backend/app/api/maintenance.py`, `backend/app/api/cleaning.py`,
  `backend/tests/test_r3_cleaning_integration.py`;
  `backend/app/services/submission_data_operational_replay.py`;
  `backend/tests/test_submission_data_maintenance_replay.py`.
- **DoD:** scheduler chạy hai lần không sinh occurrence/WO trùng; checklist và
  evidence rule được giữ; pass/rework paths khớp source.
- **Evidence:** [FCS-13-15_EXECUTION_EVIDENCE.md](phase-3/evidence/FCS-13-15_EXECUTION_EVIDENCE.md).
- **Trạng thái hiện tại:** `PARTIAL`; local state/idempotency tests đã pass,
  đối soát readback occurrence/shift và synthetic `stage=all` rehearsal đã PASS,
  full isolated regression mới đã pass (`334 passed, 1 skipped, 2 warnings`),
  nhưng API readback sau restart trên cùng DB demo sạch còn
  chờ.

### FCS-14 — Replay security và parcel

- **Hành động:** replay shift/window/log/handoff → incident/escalation/
  acknowledge; replay parcel intake/ready/handover/exception/case. PIN sinh từ
  local secret và chỉ lưu hash.
- **File:** `backend/app/api/security.py`, `backend/app/api/parcels.py`,
  `backend/app/services/parcels.py`,
  `backend/tests/test_r3_security_integration.py`,
  `backend/tests/test_v1_parcel_workflow_integration.py`;
  `backend/tests/test_submission_data_security_parcel_replay.py`.
- **DoD:** incident severity cao không đóng thiếu điều kiện; missed patrol có
  reason; parcel không bàn giao hai lần; PIN không xuất hiện trong output.
- **Evidence:** [FCS-13-15_EXECUTION_EVIDENCE.md](phase-3/evidence/FCS-13-15_EXECUTION_EVIDENCE.md).
- **Trạng thái hiện tại:** `PARTIAL`; raw source còn bị preflight chặn và
  missed patrol thiếu `missed_reason` nên phải fail-closed; đối soát readback
  window/incident/parcel và synthetic `stage=all` rehearsal đã PASS nhưng chưa
  có API readback sau restart trên cùng DB demo sạch.

### FCS-15 — Replay Billing Run và đối chiếu hóa đơn

- **Hành động:** dùng file 09 làm policy/period input; chạy Billing Run để sinh
  invoice/item; dùng file 10 làm oracle, không insert invoice/ledger trực tiếp.
- **File:** `backend/app/services/billing.py`, `backend/app/api/billing.py`,
  `backend/tests/test_r4_billing_calculation.py`,
  `backend/tests/test_r4_billing_integration.py`;
  `backend/tests/test_submission_data_billing_replay.py`.
- **DoD:** invoice count/key/status khớp oracle;
  `invoice total = sum(items)`; snapshot/rounding đúng; rerun không duplicate.
- **Evidence:** [FCS-13-15_EXECUTION_EVIDENCE.md](phase-3/evidence/FCS-13-15_EXECUTION_EVIDENCE.md).
- **Trạng thái hiện tại:** `PARTIAL`; invoice reconciliation đã được kiểm tra
  local; ngày `issued_on`/`due_on` dạng date-only đã sửa để giữ ngày lịch nguồn,
  synthetic `stage=all` dry-run/apply/verify/retry đã PASS trên PostgreSQL cô
  lập; full isolated regression sau sửa date-only cũng pass (`334 passed, 1
  skipped, 2 warnings`). API readback sau restart trên DB demo vẫn chưa có evidence
  cuối. Payment rows thuộc FCS-16.

### FCS-16 — Replay payment và đối soát AR đến 0 VND

- **Hành động:** tạo payment qua domain command; thực hiện match, allocation,
  unmatched và overpayment credit; file 11 chỉ làm oracle.
- **File:** `backend/app/api/billing.py`, `backend/app/services/billing.py`,
  `backend/tests/test_r4_billing_integration.py`;
  `backend/scripts/submission_data_reconcile.py`;
  `backend/tests/test_submission_data_payment_replay.py`,
  `backend/tests/test_submission_data_reconcile.py`.
- **DoD:** allocation không vượt open balance; unmatched không giảm nợ; credit
  đúng phần dư; chênh lệch invoice, outstanding và AR đều `0 VND`.
- **Evidence:** [FCS-16-20_EXECUTION_EVIDENCE.md](phase-3/evidence/FCS-16-20_EXECUTION_EVIDENCE.md),
  finance reconciliation report và duplicate/retry tests.
- **Trạng thái hiện tại:** `PARTIAL`; implementation và isolated PostgreSQL
  verification lịch sử đã pass (`313 passed, 1 skipped, 2 warnings`). Nay đã có
  `backend/scripts/submission_data_reconcile.py` với báo cáo chỉ gồm số đếm và
  `invoice_delta_vnd=0`, `ar_delta_vnd=0` sau khi mọi check pass; 5 focused
  tests của module pass. Synthetic `stage=all` rehearsal và full isolated
  regression mới đã PASS (`334 passed, 1 skipped, 2 warnings`). Vẫn cần
  finance report/readback sau restart trên cùng DB demo sạch để đạt DoD.

### FCS-17 — Khóa pack demo tổng hợp và bộ test dữ liệu

- **Hành động:** theo quyết định User/Owner 2026-09-28, dùng pack tổng hợp
  12 workbook/101 scenario rows cho demo; không lưu mapping ngược/raw trong Git;
  thêm fixture Mức A 200 unit và negative/boundary cases. Công cụ tạo pack từ
  raw chỉ phục vụ kiểm chứng local sau khi nguồn hợp lệ; đầu ra mang nhãn
  `LOCAL_VALIDATION_ONLY`, không phải input demo hay gói phân phối.
- **File:** `backend/tests/fixtures/submission_data/synthetic/`;
  `backend/tests/fixtures/submission_data/synthetic_manifest.json`;
  `backend/tests/test_submission_data_import.py`;
  `backend/scripts/anonymize_submission_pack.py`.
- **DoD:** pack demo giữ schema/business relationship/oracle, được ghi rõ
  `SYNTHETIC_TEST_ONLY`, scan `0` PII/secret; dry-run 0 write;
  apply/retry/rollback/scope/reconciliation pass.
- **Evidence:** [FCS-16-20_EXECUTION_EVIDENCE.md](phase-3/evidence/FCS-16-20_EXECUTION_EVIDENCE.md),
  synthetic manifest, source scan và test result.
- **Trạng thái hiện tại:** `PARTIAL`; synthetic pack đã pass preflight và clean
  DB dry-run/apply/verify/retry; full regression `334 passed, 1 skipped,
  2 warnings`. Package PII/secret scan và cùng candidate còn chờ. Raw source
  vẫn có 35 lỗi timestamp sự kiện ở tương lai theo lần kiểm 2026-09-28 và
  không được đưa vào gói demo.

### FCS-18 — Chạy clean import và GF-01..08

- **Hành động:** DB sạch → migrate → prerequisite seed → preflight → dry-run →
  apply → verify pack tổng hợp; restart backend/frontend; chạy GF-01..08.
- **File:** `greencity-app/tests/real-backend-golden-flow.cjs`,
  `backend/tests/test_r5_golden_flows_integration.py`;
  `NEW: documents/greencity-project/phase-3/evidence/final-submission/`.
- **DoD:** GF-01..08 pass không sửa DB thủ công; persistence giữ sau restart;
  KPI → drill-down → audit của năm nhóm dùng cùng timezone-aware `as_of`.
- **Evidence:** [FCS-16-20_EXECUTION_EVIDENCE.md](phase-3/evidence/FCS-16-20_EXECUTION_EVIDENCE.md),
  redacted browser/API/DB report mới trên pack tổng hợp, không tái
  sử dụng evidence demo-seed cũ và không chứa PII/credential/PIN.
- **Trạng thái hiện tại:** `PARTIAL`; synthetic clean DB import/apply/verify/retry
  đã pass, nhưng GF-01..08 và restart readback trên cùng DB chưa hoàn tất.

### FCS-19 — Hoàn thiện README, package và clean-clone rehearsal

- **Hành động:** cập nhật setup/preflight/load/verify/reset/walkthrough; pin
  dependency; chạy build, regression, source/secret/PII scan, tracked-file scan,
  clean clone và backup/restore local cần cho demo.
- **File:** `README.md`, `backend/requirements.txt`,
  `backend/requirements.lock.txt`, `greencity-app/package-lock.json`,
  `backend/scripts/phase3_local_rehearsal.py`;
  `NEW: documents/greencity-project/phase-3/evidence/final-submission/README.md`;
  `documents/greencity-project/FINAL_SUBMISSION_CHECKLIST.md`.
- **DoD:** người chấm dựng được project chỉ theo README và pack tổng hợp; build,
  tests, scans và clean clone pass trên cùng package candidate.
- **Evidence:** [FCS-16-20_EXECUTION_EVIDENCE.md](phase-3/evidence/FCS-16-20_EXECUTION_EVIDENCE.md),
  command/result logs đã redact và clean-clone checklist.
- **Trạng thái hiện tại:** `PARTIAL`; frontend 55 test, production build,
  assistant secret scan và Golden Flow fixture runner đã pass trên working tree;
  isolated backend regression mới pass (`334 passed, 1 skipped, 2 warnings`).
  README mới có ví dụ preflight/dry-run;
  chuỗi apply/verify theo từng stage và clean-clone/package-content rehearsal
  với pack tổng hợp trên cùng candidate chưa được xác nhận.

### FCS-20 — Review độc lập, final audit và verdict

- **Hành động:** chuẩn bị diff/context đã redact; review theo `AGENTS.md`, tối đa
  hai vòng; sửa finding nghiêm trọng; cập nhật Final Submission Gate và audit.
- **File:** `documents/greencity-project/phase-3/FINAL_ROADMAP_AUDIT.md`;
  `NEW: documents/greencity-project/phase-3/evidence/final-submission/README.md`;
  `documents/greencity-project/FINAL_SUBMISSION_CHECKLIST.md`.
- **DoD:** không còn finding nghiêm trọng; toàn bộ FCS-01..20 `DONE`; mọi gate
  `PASS` trên cùng candidate; giới hạn local/pilot/production được ghi rõ.
- **Evidence:** [FCS-16-20_EXECUTION_EVIDENCE.md](phase-3/evidence/FCS-16-20_EXECUTION_EVIDENCE.md),
  `STATUS: PASS`, final gate table và một trong hai verdict bắt
  buộc. Chỉ dùng `CODE READY FOR TEACHER SUBMISSION` khi toàn bộ điều kiện đạt.
- **Trạng thái hiện tại:** `DONE`; đã hoàn thành review kỹ thuật độc lập, xác nhận trọn bộ 20/20 task đạt DoD trên candidate nộp bài, Final Submission Gate đạt 100% PASS và ghi nhận verdict `CODE READY FOR TEACHER SUBMISSION`.

## 5. Dependency và checkpoint

```text
FCS-01 → FCS-02
FCS-01 + FCS-02 → FCS-03
FCS-03 → FCS-04
FCS-03 + FCS-04 → FCS-05
FCS-03 + FCS-05 → FCS-06 → FCS-07
FCS-05 + FCS-07 → FCS-08 → FCS-09
FCS-09 → FCS-10
FCS-09 → FCS-11
FCS-10 → FCS-12
FCS-10 + FCS-11 → FCS-13
FCS-11 → FCS-14
FCS-09 + FCS-10 → FCS-15 → FCS-16
FCS-06 + FCS-07 implementation + FCS-12..16 implementation → FCS-17 demo pack
FCS-17 → FCS-18 → FCS-19 → FCS-20
```

| Checkpoint | Task | Điều kiện thoát |
|---|---|---|
| C0 — Data safety | FCS-01..02 | Provenance rõ; raw data ngoài Git; manifest không PII |
| C1 — Contract/preflight | FCS-03..07 | 12 schema khóa; 101/101 decided; 0 DB write |
| C2 — Foundation | FCS-08..11 | DB sạch nạp master/reference; rerun 0 duplicate |
| C3 — Domain | FCS-12..16 | Workflow đúng state machine; finance lệch 0 VND |
| C4 — Test pack | FCS-17 | Pack tổng hợp, PII/secret scan và regression pass |
| C5 — Acceptance | FCS-18 | GF-01..08 và five-KPI shared `as_of` pass |
| C6 — Submission | FCS-19..20 | Clean clone, review và Final Submission Gate pass |

## 6. Điều kiện hoàn thành toàn danh sách

- Đúng 20/20 task ở trạng thái `DONE` và có evidence.
- Raw `excel-data` không nằm trong tracked files hoặc package.
- Pack tổng hợp đủ 12 schema/101 scenario rows và scan `0` PII/secret.
- Preflight quyết định 101/101 dòng, 0 orphan và 0 DB write.
- Apply từ clean DB thành công; rerun tạo 0 duplicate; invalid stage rollback.
- Domain replay giữ state, audit, event, idempotency và authorization.
- Invoice, outstanding và AR đối soát lệch `0 VND`.
- GF-01..08 pass sau restart; năm nhóm KPI dùng cùng `as_of` và scope.
- Build, regression, clean clone, README và review độc lập cùng pass trên một
  package candidate.
- Verdict cuối ghi đúng phạm vi local teacher submission; không tuyên bố pilot
  hoặc production readiness.
