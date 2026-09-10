# Plan 2 — Foundation API contract (P1, partial)

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
