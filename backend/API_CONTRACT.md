# Plan 2 — Foundation API contract (P1, partial)

## Delta V1 Parcel Task 5 — Golden Flow, Case, Incident và private evidence

V1 Parcel Task 1–5 mở rộng Parcel Desk từ intake/handover sang hồ sơ xử lý liên
tục. Parcel được liên kết với `CaseRecord`, `SecurityIncident`, `Attachment` và
`AuditEvent` hiện có; không tạo một store song song. Migration `0014` tạo parcel,
còn `0015` thêm `source_parcel_id`, `parcel_id` và parent-union invariant.

### Bề mặt OpenAPI được duyệt

| Method | Path | Quy tắc chính |
|---|---|---|
| GET, POST | `/api/v1/parcels/{parcel_id}/case` | Một Case trực tiếp/parcel; POST cần `Idempotency-Key` |
| GET | `/api/v1/parcels/{parcel_id}/incident` | Incident đang liên kết trong cùng building |
| POST | `/api/v1/parcels/{parcel_id}/incident-link` | Link Incident cùng building; chỉ role security/admin/director |
| GET, POST | `/api/v1/parcels/{parcel_id}/evidence` | Metadata private; upload PNG/JPEG, checksum/quarantine, key |
| GET | `/api/v1/parcels/{parcel_id}/evidence/{attachment_id}/signed-link` | Signed link ngắn hạn, ràng actor/site/parcel/attachment |
| GET | `/api/v1/parcels/{parcel_id}/evidence/{attachment_id}/content` | Bearer + signed token, `Cache-Control: private, no-store` |
| GET | `/api/v1/parcels/{parcel_id}/timeline` | Audit timeline của Parcel và Case/Incident/Attachment liên kết |

Scope tenant/site/building luôn được dựng từ `UserContext`; client không được
gửi scope để nâng quyền. Case/evidence retry cùng fingerprint replay cùng
resource; payload khác trả conflict. File private không trả storage key và file
quarantine không được download. Một parcel chỉ có một Case trực tiếp, một
Incident chỉ link một parcel và Attachment chỉ có đúng một parent.
Case chỉ mở ở `HANDED_OVER` hoặc `RETURNED/LOST/DAMAGED`; Incident link tăng
version/actor và audit before/after.

### Bằng chứng local và giới hạn

Ngày 17/09/2026, runner PostgreSQL/TLS cô lập đạt **253 passed, 2 warnings**;
empty DB, repeat migration/seed, `alembic check`, migration tới `0015` và
shutdown đều PASS. Frontend đạt `npm test` **68/68**, Vite build PASS và Parcel
UX `npm run test:parcel` **13/13 checks**. Test chi tiết gồm
`test_v1_parcel_foundation.py`, `test_v1_parcel_workflow_integration.py`,
`test_migration_0015.py` và frontend API contract. Browser UX dùng transport
intercept nên không phải evidence browser-to-PostgreSQL.

Đây là **Implemented & Verified Local** cho V1 Parcel Task 1–5; không phải Gate C,
production/Aiven hay independent-review sign-off. Contract chi tiết ở
[V1_PARCEL_CONTRACT.md](V1_PARCEL_CONTRACT.md),
[V1_PARCEL_WORKFLOW_CONTRACT.md](V1_PARCEL_WORKFLOW_CONTRACT.md) và
[V1_PARCEL_CASE_EVIDENCE_CONTRACT.md](V1_PARCEL_CASE_EVIDENCE_CONTRACT.md).

## Delta R6 — Resident Self-Service

R6 là lát self-service read/write có giới hạn cho role `resident`. Danh tính
được xác minh từ `Account.person_id` và `UnitPersonRelationship` đang hiệu lực;
tenant, site đang hoạt động, building và unit đều được suy ra ở server. Client
không được gửi hoặc tin cậy `tenant_id`, `site_id`, `building_id`, `role` hay
`person_id` để mở rộng scope. Account cư dân không có quan hệ hiệu lực trả
`404 ERR-SCOPE-NOTFOUND`; role khác trả `403 ERR-FORBIDDEN`.

### Migration và seed

- `0012_r6_resident_identity_scope.py` thêm `accounts.person_id`, composite FK
  cùng tenant và unique `(tenant_id, person_id)`. Downgrade bị từ chối khi còn
  liên kết identity.
- `0013_r6_resident_service_request_evidence.py` cho phép Attachment có parent
  là Work Order **hoặc** Resident Service Request (đúng một parent), FK/index
  và downgrade fail-closed khi còn evidence cư dân.
- Seed lặp tạo `resident_west` và liên kết Person/Unit West; không tạo dữ liệu
  invoice/payment/ledger lịch sử.

### Bề mặt OpenAPI được duyệt

| Method | Path | Quy tắc chính |
|---|---|---|
| GET | `/api/v1/resident/service-request-options` | Options building/unit/category trong scope cư dân |
| GET, POST | `/api/v1/resident/service-requests` | Danh sách phân trang; POST bắt buộc `Idempotency-Key` |
| GET, PATCH | `/api/v1/resident/service-requests/{request_id}` | PATCH chỉ `NEW`/`WAITING_INFO`, bắt buộc `expected_version` + key |
| GET | `/api/v1/resident/service-requests/{request_id}/timeline` | Audit timeline của request đó |
| GET, POST | `/api/v1/resident/service-requests/{request_id}/evidence` | Private metadata; POST raw PNG/JPEG, checksum/quarantine, key |
| GET | `/api/v1/resident/service-requests/{request_id}/evidence/{attachment_id}/signed-link` | Signed link ngắn hạn, ràng actor/site/request/attachment |
| GET | `/api/v1/resident/service-requests/{request_id}/evidence/{attachment_id}/content` | Bearer cư dân + signed token; `no-store` |
| GET | `/api/v1/resident/billing/summary` | Bắt buộc `as_of` RFC3339 có múi giờ; AR ledger read-only |
| GET | `/api/v1/resident/billing/invoices` | Invoice phát hành trước cutoff, item snapshot read-only |
| GET | `/api/v1/resident/billing/payments` | Payment của các billing account trong scope trước cutoff |
| GET | `/api/v1/resident/notifications` | Inbox account/site; `include_read`, phân trang |
| POST | `/api/v1/resident/notifications/{notification_id}/read` | Acknowledge idempotent; ghi audit lần đọc đầu |

Tất cả route dùng ErrorEnvelope và `X-Correlation-ID` chung. `as_of` naive bị
`422 ERR-AS-OF-TIMEZONE`; billing summary tính `SUM(debit_vnd-credit_vnd)` với
`effective_at <= as_of` và luôn trả số nguyên VND. Portal không có endpoint ghi
payment, allocation, invoice hoặc AR ledger.

### Bất biến và retry

- Cùng actor/operation/idempotency key và cùng fingerprint được replay cùng
  resource; payload khác trả `409 ERR-CONFLICT`. Advisory lock và unique DB
  chống race giữa request đồng thời.
- PATCH khóa bản ghi, so sánh `expected_version` nguyên tử và tăng version;
  phiên bản cũ trả `409`.
- Evidence lưu private dưới root cấu hình, kiểm magic bytes/MIME/kích thước,
  SHA-256 và path traversal; file bị quarantine không được download.
- Audit/timeline và outbox được ghi cùng transaction nghiệp vụ. Notification
  chỉ join được event cùng tenant/site và recipient account; correlation nguồn
  được trả nhưng không lộ payload/event nội bộ không cần thiết.

### Bằng chứng local và giới hạn

Ngày 16/09/2026, runner PostgreSQL/TLS cô lập đạt **238 passed, 2 warnings**,
migration tới `0013`, DB trống/seed lặp/drift/shutdown PASS; frontend đạt
`npm test` **63/63**, Vite build PASS và Resident UX **17/17 checks**. Test chi
tiết: `test_r6_resident_service_requests_integration.py`,
`test_r6_resident_billing_integration.py`,
`test_r6_resident_notifications_integration.py`,
`test_r6_hardening_integration.py` và `test_contract.py`.

Đây là **Implemented & Verified Local** cho R6 Resident Self-Service; không
phải Gate C, production/Aiven, payment gateway thật, refund/chargeback, AI,
đăng ký cư dân công khai hay independent-review sign-off. Xem ma trận phát hành
tại [R6_RELEASE_EVIDENCE.md](R6_RELEASE_EVIDENCE.md).

## Delta R5 Task 1 — Outbox, notification inbox và audit correlation

[R5_CONTRACT.md](R5_CONTRACT.md) khóa revision `0011`: `DomainEvent` là
transactional outbox có retry/dead-letter/lease, notification read model, audit
explorer scoped và manual retry cho operator site-wide. Backend roster vẫn chỉ
có tám role; mock Auditor frontend không tạo quyền API. Lát này không bao gồm
Dashboard/KPI hay provider Email/SMS/Push thực; Dashboard được bổ sung riêng ở
R5 Task 2 ngay bên dưới.

## Delta R4 — Billing, AR ledger và Payment foundation

Contract đầy đủ tại [R4_CONTRACT.md](R4_CONTRACT.md). Revision `0010` kế thừa
`0008`/`0009` và thêm
Billing Account, Fee Policy/version, Accounting Period, Billing Run,
Billing Invoice/Item, Payment/Allocation/Unmatched/Overpayment Credit và AR
ledger theo tenant/site/building. Tên `billing_invoice_items` cố ý tách khỏi
`invoice_items` R2 (posting anchor chi phí kỹ thuật).

OpenAPI publish policy/version, period, run/retry và invoice list/detail/void
bên cạnh `GET /billing/accounts`, receive/list payment, unmatched queue/match,
allocation và Overpayment Credit list. Scope luôn từ session/server. Run là
all-or-nothing và database unique chặn trùng; Invoice Item snapshot là immutable;
void thêm reversal thay vì sửa lịch sử. Task 4 thêm Golden Flow oracle,
idempotent recovery sau response mất và regression financial; refund và
maker-checker vẫn không được suy diễn từ schema hay route.

Pending Charge đã `APPROVED` trước cutoff được Billing Run snapshot vào
`billing_invoice_items`; cùng transaction tạo đúng một `invoice_items` R2
posting anchor trước khi chuyển charge thành `POSTED`. Do đó một luồng
CSKH-to-cash có thể đối soát từ Cost Line qua snapshot/anchor đến AR ledger và
payment allocation mà không cần ghi tay vào database.

## Delta R1 — AC-03 Person--Unit read contract

`GET /api/v1/persons/{person_id}/units?as_of=YYYY-MM-DD` là đọc hai chiều
cho quan hệ Person--Unit. Chỉ `admin`, `director`, `cskh`, `accountant` được
gọi; database tự suy ra tenant, active site và building grant từ phiên hiện
hành. Client không gửi hoặc mở rộng `tenant_id`, role, site hay building scope.

- Kết quả chỉ chứa relationship đang hiệu lực theo khoảng nửa mở
  `valid_from <= as_of < valid_to` (hoặc `valid_to` rỗng).
- Mỗi item gồm Unit/tòa/site, `relationship_type`, `ownership_ratio` và
  `valid_from`/`valid_to`; contact vẫn là dữ liệu masked.
- Person không tồn tại, ngoài site/tòa hoặc chỉ có relationship không nằm trong
  scope đều cùng trả `404 ERR-SCOPE-NOTFOUND`; thiếu role trả `403 ERR-FORBIDDEN`.
- Migration `0005` bắt buộc ratio owner trong `(0, 1]`, tổng ratio owner hiệu lực
  không vượt 1, không chồng episode cùng Person--Unit--type, và cấm thay tenant
  của Person/Site hoặc di chuyển Unit/Building qua tenant khi đã có relationship.
  Đây là bảo toàn tính đúng đắn DB, không phải claim Gate/release. Trạng thái
  closeout là **Implemented & Verified Local**; xem [R1_CLOSEOUT.md](R1_CLOSEOUT.md).

## Delta R1 — Unit CSV ImportRun (AC-02 / AC-24)

Traceability closeout tại [R1_CLOSEOUT.md](R1_CLOSEOUT.md). Các route thực thi
dưới `/api/v1/import-runs` là `GET /template`, `POST /` (CSV body,
`building_code`, `mode`, `Idempotency-Key`), `POST /{run_id}/preview`,
`POST /{run_id}/apply`, `GET /{run_id}`, `GET /{run_id}/rows`, và signed
error-file link/download. Request không nhận `tenant_id`, `site_id`,
`building_id` hay role; backend suy toàn bộ scope từ session và database.

- Chỉ `admin`/`cskh` có grant thật trong active site/building được dùng flow.
  Ngoài scope trả `404 ERR-SCOPE-NOTFOUND`; role không hợp lệ trả 403.
- ImportRun lưu source private, checksum, phiên bản, mapping, row result và
  audit/outbox. Source không hợp lệ bị quarantine; checksum source/error sai
  trả `ERR-FILE-INTEGRITY`.
- Signed error-file token có `purpose=import-error-download`, ràng actor,
  tenant/site/building/run và expiry; nó không thể dùng làm Bearer session.
- `POST /api/v1/units/import` JSON cũ chỉ còn compatibility slice lịch sử,
  không phải contract/evidence hiện hành để đóng AC-02.

Head local là `0007`. PostgreSQL local đã kiểm migration `0006 -> 0007 -> 0006 -> 0007`
và **191 test pass**. `AC-02`/`AC-24` là **Implemented & Verified Local** theo
ma trận closeout, không phải Gate/release claim; không có review Antigravity lần 3.

## Delta R5 — CAP-BI Dashboard và Audit Explorer (backend)

`GET /api/v1/dashboard?as_of=<timezone-aware RFC3339>` và
`GET /api/v1/dashboard/drill-down/{metric}?as_of=...` là projection chỉ đọc cho
`admin`/`director`. Không nhận tenant/site/building/role từ client: context server
quyết active tenant/site và building grant. `as_of` là bắt buộc, không nhận
datetime naive. Dashboard chỉ có năm KPI `sla_overdue`, `maintenance_due`,
`cleaning_rework`, `open_incidents`, `ar_debt`; drill-down chỉ nhận đúng allowlist
đó. Công nợ dùng AR ledger `SUM(debit_vnd-credit_vnd)` tại `effective_at <= as_of`
và không dùng invoice balance cache (`INV-01`).

Audit Explorer nhận `correlation_id` hoặc cặp `resource_type`/`resource_id`, kèm
`as_of` timezone-aware tùy chọn: admin/director nhận event trong server scope,
accountant chỉ audit resource tài chính. Roster backend không có `auditor`;
frontend mock không cấp quyền API. Xem
[R5_CONTRACT.md](R5_CONTRACT.md) để biết cutoff semantics/evidence và giới hạn.

## Delta R3 — data foundation vệ sinh và an ninh

Contract R3 tại [R3_CONTRACT.md](R3_CONTRACT.md): schema scoped cho ca/tuyến,
checklist, patrol, incident/PCCC, escalation/acknowledgement và visitor log;
`WorkOrder` có thêm nguồn `cleaning_task_id`. Task 2 publish cleaning API/evidence
AC-40..41; Task 3 publish security API/evidence AC-42..43 với scope server-side,
timeline append-only, patrol missed reason và điều kiện đóng incident.

## Delta R2 — Service Request, Work Order và Maintenance (12/09/2026)

Contract R2 thực thi, state transition, role/scope, endpoint, idempotency và
mapping `AC-06`, `AC-08..10`, `AC-38..39` được khóa tại
[R2_CONTRACT.md](R2_CONTRACT.md). OpenAPI hiện publish toàn bộ route R2 dưới
`/api/v1`; mọi response lỗi dùng envelope chung và khai báo cả HTTP 400 cho
idempotency key/input command không hợp lệ.

`GET /api/v1/assets/{asset_id}/maintenance-history` là projection chỉ đọc của
Maintenance History. Nó chỉ trả history của asset trong tenant/site/building do
server suy từ phiên; không có route ghi/sửa/xóa history. `admin`, `director`,
`cskh` và `technical_lead` có grant đúng building mới đọc được; asset ngoài
scope trả `404 ERR-SCOPE-NOTFOUND`.

Snapshot P1/R1 phía dưới là lịch sử hình thành contract, không còn là danh sách
endpoint hiện tại. `AC-07` vẫn `SPEC-ONLY`; frontend list/search, outbox worker và
billing R4 không nằm trong delta R2.

## Delta mới nhất — resource/building/field policy

Contract Unit360 hiện tuân theo [RBAC_R1.md](RBAC_R1.md). Roster Core tám role
đã được người dùng xác nhận, không có Kiểm toán. Role không có Unit read: 403;
scope tòa sai/thiếu hoặc KTV chưa có assignment: 404 ERR-SCOPE-NOTFOUND.

Response bổ sung `residents_visible: boolean`; false => residents=[] do policy.
`area_m2: number|null`, `status: string|null`: null khi projection An ninh chỉ
cho phép định danh/vị trí. Role có quyền đầy đủ vẫn nhận dữ liệu kiểu cũ.
Trưởng KT/An ninh không nhận Person ID/contact/relationship metadata qua endpoint
này, kể cả khi có role CSKH nhưng role đó chỉ được cấp tại tòa khác.
Role/building/scope trong payload, query, header hay JWT không phải nguồn quyền.

Đây là contract R1 đang triển khai, không phải tuyên bố hoàn tất WO assigned-only,
audit hoặc Gate B. Các delta cũ phía dưới là lịch sử.

## Delta sau bản sửa Group 1 (10/09/2026)

- Có `/api/v1/auth/login`, `/auth/me`, `/auth/switch-site` (cùng prefix `/api/v1`)
  và `/api/v1/units/{unit_id}/360`; DTO tại schemas/auth.py và schemas/unit.py.
- HTTP app yêu cầu SECRET_KEY tường minh; login trả token HS256, role/tenant và
  membership được đọc lại từ DB. Role trong me là role áp dụng active site.
- Unit360 luôn giới hạn tenant + allowed sites + active site. Admin cũng phải
  switch-site trước khi đọc site khác; không có wildcard tenant. Missing Unit và
  ngoài scope đều 404 ERR-SCOPE-NOTFOUND với message `Không tìm thấy dữ liệu.`.
- Unit/Person sai tenant không được trả về. Chưa có complete resource/field/
  building/assigned policy: **không phải full RBAC hoặc R1 PASS**.
- Username đang trùng nhiều tenant bị 401 chung, chưa lựa chọn tenant thay người dùng.
- Audit/readiness và session-wide invalidation sau switch chưa có; xem VALIDATION.

Phần bên dưới giữ snapshot contract foundation trước khi có các API R1.

Trạng thái: chỉ contract foundation trong lượt 10/09/2026. **Không phải Gate B
PASS**, không có auth/policy/Unit 360° và không đóng băng contract domain chưa build.
Nguồn: `../plan2.md`, roadmap `ARC-03/07/09/13/19`, baseline tại repo root.

## Contract thực thi trong nhóm này

- API namespace chính `/api/v1`; hiện chỉ `GET /api/v1/health`.
- Giữ `GET /health` làm alias tương thích cùng handler/DTO, không publish alias
  trong OpenAPI. `/docs`, `/redoc`, `/openapi.json` là infrastructure routes.
- Health là public, read-only, không actor/owner nghiệp vụ hay state transition.
  Không nhận role/site từ client, không truy vấn domain record. Không có thay đổi
  schema hoặc seed; không thể dùng health thay acceptance demo nghiệp vụ.
- Thành công: `200 {"status":"ok","database":"connected"}` từ HealthResponse.
  Kiểm SELECT 1; không cam kết schema/revision readiness.
- Lỗi ứng dụng: `{ "error": { "code": "ERR-...", "message": "Thông báo tiếng Việt",
  "correlation_id": "UUID" } }`, DTO ErrorEnvelope/ErrorDetail dùng chung runtime
  và OpenAPI. Không echo body, query, arbitrary path, exception hoặc secret.
- `X-Correlation-ID`: giữ UUID hợp lệ, sinh mới nếu thiếu/sai. UUID header và body
  lỗi phải trùng nhau; lỗi không xử lý dùng ERR-INTERNAL và vẫn được che chi tiết.
- OpenAPI khai báo error envelope chung cho 401/403/404/405/409/422/500/503.
  Đây là định dạng lỗi tiêu chuẩn, **không phải** tuyên bố health cần đăng nhập hay
  các policy tương ứng đã tồn tại. Route mới không dùng default HTTPValidationError.
- Giữ protocol headers `WWW-Authenticate` (401), `Allow` (405).
- CORS preflight là phản hồi giao thức middleware, ngoài envelope nghiệp vụ.

| HTTP | Code hiện có / quy ước | Bằng chứng |
|---|---|---|
| 401 | ERR-UNAUTHORIZED | Handler test-only; chưa có login/auth |
| 403 | ERR-FORBIDDEN | Handler test-only; chưa có RBAC |
| 404 | ERR-NOTFOUND; ERR-SCOPE-NOTFOUND qua AppError | Test format; chưa có scope query |
| 405 | ERR-HTTP | POST health bị chặn, có Allow |
| 409 | ERR-CONFLICT cho domain tương lai | Chỉ envelope, chưa optimistic locking |
| 422 | ERR-VALIDATION | DTO probe sai, không echo input |
| 500 | ERR-INTERNAL | Mock unexpected exception được che |
| 503 | ERR-DATABASE-UNAVAILABLE | Mock DB failure; integration thật opt-in |

## Những phần chưa được triển khai hoặc nghiệm thu

| Contract | Yêu cầu cho nhóm P1/R1 sau | Trạng thái |
|---|---|---|
| Pagination/filter | DTO chung, limit có chặn, sort ổn định, filter allowlist sau scope; chọn shape trước list API đầu tiên | MISSING |
| UTC datetime | Input timezone-aware, chuẩn hóa output UTC; không suy đoán timezone của naive input | MISSING ở DTO domain; DB đã TIMESTAMPTZ/UTC |
| VND integer | Từ chối float/bool/coercion gây mất chính xác; quy tắc làm tròn domain có oracle | MISSING; không có finance API |
| version | Migration + atomic compare-and-update; stale trả 409 ERR-CONFLICT | MISSING |
| Idempotency-Key | Ghi theo ARC-06, scoped key/fingerprint/replay trong transaction | MISSING |
| Auth/me/switch-site | Danh tính được xác minh; role/membership/active scope từ server, đổi scope audit | MISSING |
| RBAC/scope/field policy | Deny-by-default, tenant/site/building/assigned/resource; 404 không dò tồn tại | MISSING |
| Audit | Persist actor/scope/time/correlation cùng transaction nghiệp vụ | MISSING |

Không tạo DTO/model placeholder cho các mục này rồi đánh dấu hoàn thành.

## Acceptance criteria nhóm contract / demo

1. GET versioned health và legacy alias dùng cùng DTO và database ping.
2. OpenAPI chỉ publish versioned health, có schema lỗi chung kể cả request validation.
3. 404/405/422/500/503 có envelope ổn định, UUID header/body trùng nhau.
4. 401 giữ challenge, 405 giữ Allow; các payload giả nhạy cảm không xuất hiện ở log/response.
5. Toàn bộ foundation tests cũ giữ nguyên và pass. Không phát sinh route nghiệp vụ.

Chạy từ backend (không credential, dùng injected mock DB):

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_contract.py
.\.venv\Scripts\python.exe -m pytest -q -m 'not integration'
```

Khi server đã có cấu hình DB an toàn, chỉ đọc:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
Invoke-RestMethod http://127.0.0.1:8000/openapi.json
```

Các lệnh HTTP trên không phải bằng chứng đã chạy live trong lượt này. Test probe
chỉ nằm trong test factory, không được đăng ký ở application production.
