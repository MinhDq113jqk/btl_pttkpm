# Plan 2 — Foundation API contract (P1, partial)

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
