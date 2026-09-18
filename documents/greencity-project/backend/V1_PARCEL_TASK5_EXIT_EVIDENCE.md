# V1 Parcel Task 5 — Golden Flow và Exit Evidence

## Phạm vi

Task 5 đóng gói lát V1 Parcel hiện có thành một đường kiểm chứng end-to-end.
Các thao tác nghiệp vụ trong flow đều đi qua HTTP API (màn hình Parcel Desk
dùng chính các API này); SQL chỉ được dùng làm oracle đọc sau cùng. Không có
script nghiệp vụ nào sửa dữ liệu bằng SQL.

`0014` là nền parcel/state machine, `0015` là Case/Incident/evidence. Task 5
không mở thêm migration.

## Golden Flow A — nhận và bàn giao

```text
POST /parcels
  -> POST /parcels/{id}/ready
  -> POST /parcels/{id}/handover
  -> GET  /parcels/{id}
```

Bài kiểm thử giữ snapshot tenant/site/building/unit, recipient, carrier,
contact, vị trí và thời điểm nhận trước khi chuyển trạng thái. Sau handover,
mọi snapshot giữ nguyên; chỉ status, version, thời điểm và actor bàn giao đổi.
Retry cùng `Idempotency-Key` trả cùng resource, còn `expected_version` chặn
request cũ.

## Golden Flow B — ngoại lệ đến hồ sơ kiểm toán

```text
POST /parcels
  -> POST /parcels/{id}/exception (LOST/RETURNED/DAMAGED)
  -> POST /parcels/{id}/case
  -> POST /security/shifts                 (fixture point qua API)
  -> POST /security/incidents
  -> POST /parcels/{id}/incident-link
  -> POST /parcels/{id}/evidence            (PNG/JPEG private)
  -> GET  /parcels/{id}/evidence/{attachment}/signed-link
  -> GET  /parcels/{id}/evidence/{attachment}/content
  -> GET  /parcels/{id}/timeline
```

Case chỉ được mở cho parcel đã bàn giao hoặc đã có ngoại lệ terminal. Incident
link là duy nhất theo parcel; evidence trả metadata, không trả storage key.
Signed token được kiểm tra lại tenant/site/account/parcel/attachment và file
được phục vụ với `Cache-Control: private, no-store`.

## Ma trận kiểm chứng

| Bằng chứng | Mục tiêu | Test/artefact |
|---|---|---|
| Receive → ready → handover | state transition, PIN, snapshot bất biến | `test_parcel_task5_golden_flows_run_through_api_and_preserve_exit_evidence` |
| Exception → Case | terminal reason, one Case, retry | cùng test; `test_parcel_case_incident_evidence_and_timeline_are_scoped_and_idempotent` |
| Incident linkage | tạo Incident qua API, building scope, one-to-one | cùng test; `test_parcel_case_incident_evidence_and_timeline_are_scoped_and_idempotent` |
| Evidence → signed download | magic bytes, private storage, Bearer + token, no-store | cùng test; frontend `parcel-ux.cjs` |
| Audit timeline | Parcel/Case/Incident/Attachment và correlation ID | cùng test; `GET /parcels/{id}/timeline` |
| Duplicate/retry/concurrency guards | idempotency records và optimistic version | workflow integration tests + SQL count oracle |
| Migration/seed/drift | DB trống, repeat, downgrade fail-closed | `scripts.test_migration_0014`, `scripts.test_migration_0015`, `scripts.test_isolated` |

## Lệnh kiểm chứng authoritative

```powershell
cd C:\Users\LEGION\btl\_pttkpm\backend
.\.venv\Scripts\python.exe -m scripts.test_isolated `
  --pg-bin "C:\Program Files\PostgreSQL\18\bin" `
  --openssl "C:\Program Files\Git\usr\bin\openssl.exe"

cd ..\greencity-app
npm test
npm run build
# Terminal riêng: npm run dev -- --host 127.0.0.1
node tests\parcel-ux.cjs
```

`parcel-ux.cjs` dùng Edge headless và mặc định truy cập
`http://127.0.0.1:3000/`; giữ Vite dev server chạy trong terminal riêng khi
chạy bước này.

## Kết quả ghi nhận ngày 17/09/2026

- Isolated PostgreSQL: **246 passed, 2 warnings** trong 48.50s; migration,
  empty DB, seed repeat, drift và shutdown đều PASS.
- Frontend Node tests: **66/66 PASS**; Vite build PASS.
- Parcel UX: **13/13 checks PASS**; không lỗi page, không overflow mobile và
  không render plaintext PIN.
- `git diff --check`: PASS. Hai warning backend là deprecation của
  Starlette/TestClient và AnyIO.

Kết quả cần ghi cùng commit/evidence pack: migration tới `0015`, DB trống và
seed lặp, schema drift PASS, PostgreSQL shutdown PASS, toàn bộ pytest/frontend
PASS, Parcel UX không overflow ở mobile và không render plaintext PIN.

## Giới hạn của evidence

- Đây là **Implemented & Verified Local** trên PostgreSQL cô lập; không phải
  Gate C, production/Aiven, tải 10 người hay independent review.
- Chưa có provider email/SMS, object storage ngoài local private path, hoặc
  Incident/Patrol master-data admin UI; test tạo PatrolPoint fixture trước khi
  gọi các API ca trực/sự cố.
- `PIN_MAX_ATTEMPTS = 5` là ngưỡng khóa tạm thời; DB giữ counter tối đa `10`
  để giới hạn tổng số lần thử qua nhiều chu kỳ khóa. Đây là hai invariants
  khác nhau, không phải hai ngưỡng khóa cạnh tranh.
