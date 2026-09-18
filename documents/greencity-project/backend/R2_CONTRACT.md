# GreenCity Backend — R2 CSKH và kỹ thuật

## Phạm vi nghiệm thu

R2 triển khai lát dọc `CAP-SRV` và phần bắt buộc của `CAP-AST` theo
`roadmap_v2.md`. Tiêu chí thoát là `AC-06`, `AC-08`, `AC-09`, `AC-10`,
`AC-38` và `AC-39`.

- `AC-07` (pause/resume SLA theo reason) là `SPEC-ONLY`; R2 chỉ dùng SLA tuyệt
  đối từ thời điểm tiếp nhận và thời lượng của danh mục dịch vụ.
- `InvoiceItem` chỉ là posting anchor tối thiểu để kiểm tra reversal của
  `AC-10`; đây không phải phân hệ hóa đơn/thanh toán R4.
- Lát frontend CSKH chỉ gồm login/`/auth/me`, Bearer list phân trang và form tạo
  Service Request bằng lựa chọn server cấp; không bao gồm full KTV UI hay thao tác
  Work Order/Maintenance trên frontend.
- R2 không bao gồm worker publish outbox, AI, resident portal, vệ sinh, an ninh,
  billing run, payment, refund hoặc chargeback.

## Luồng và trạng thái

### Service Request và Work Order

```text
Service Request: NEW -> TRIAGED -> IN_PROGRESS -> RESOLVED -> CLOSED
Work Order:      DRAFT -> ASSIGNED -> IN_PROGRESS -> WAITING_ACCEPTANCE
                -> COMPLETED -> CLOSED
                              \-> CANCELLED
Terminal WO dịch vụ có thể reopen -> IN_PROGRESS.
```

- Một Request có nhiều WO và chỉ thành `RESOLVED` khi mọi WO liên kết đều ở
  trạng thái terminal (`COMPLETED`, `CLOSED` hoặc `CANCELLED`). Reopen một WO
  sẽ đưa Request về `IN_PROGRESS`.
- KTV chỉ đọc/cập nhật WO được giao cho chính mình. Trưởng kỹ thuật phân công;
  KTV hoàn thành checklist, thêm ảnh và gửi nghiệm thu.
- `TECHNICAL` acceptance yêu cầu Trưởng kỹ thuật đúng building. `PROXY`
  acceptance yêu cầu CSKH đúng building, reason và ảnh evidence thuộc chính WO.
  Người thực hiện không được tự nghiệm thu.

### Chi phí và charge

```text
Cost Line:       SUBMITTED -> CANCELLED
Pending Charge:  SUBMITTED -> APPROVED | REJECTED
                 APPROVED -> POSTED -> REVERSED
```

- VND là integer dương; bool, float và chuỗi số bị từ chối.
- Dòng `RESIDENT` bắt buộc có ảnh evidence và tạo một Pending Charge; dòng
  `MANAGEMENT` không tạo charge.
- Kế toán không được duyệt charge do chính mình submit. Lần từ chối này vẫn ghi
  audit `PermissionDenied` trước khi trả `ERR-SOD-SELF-APPROVE`.
- Cancel/reopen WO có charge đã posting tạo `ChargeReversal` và `Case`, giữ lại
  Cost Line, Pending Charge và InvoiceItem gốc.

### Bảo trì

```text
Occurrence: DUE -> WO_CREATED -> IN_PROGRESS -> COMPLETED
            DUE/WO_CREATED -> DEFERRED -> WO_CREATED (khi đến defer_until)
```

- Asset thuộc tenant/site/building hợp lệ; Maintenance Plan có checklist,
  chu kỳ và `next_due_at` timezone-aware.
- Scheduler dùng unique occurrence `(plan_id, due_at)` và unique WO theo
  occurrence. Chạy lặp không tạo occurrence/WO thứ hai.
- Nghiệm thu WO bảo trì cập nhật occurrence `COMPLETED`, tạo đúng một
  Maintenance History và đẩy `next_due_at` từ kỳ vừa hoàn tất.

## API `/api/v1`

| Nhóm | Method và path | Vai trò chính |
|---|---|---|
| Request form | `GET /service-request-form-options[?building_id=]` | Chỉ CSKH; lựa chọn theo active site + building grant |
| Request | `POST /service-requests` | CSKH đúng building |
| Request | `GET /service-requests?status=&page=&page_size=` | Điều hành theo scope; CSKH/Trưởng KT đúng building; KTV assigned-only |
| Request | `GET /service-requests/{id}` | CSKH/Trưởng KT/điều hành; KTV assigned-only |
| Request | `POST /service-requests/{id}/triage` | CSKH |
| Request | `POST /service-requests/{id}/work-orders` | CSKH hoặc Trưởng KT |
| Request | `POST /service-requests/{id}/close` | CSKH |
| SLA | `POST /service-requests/sla/run` | Admin hoặc Giám đốc |
| WO | `GET /work-orders/{id}` | Theo building; KTV assigned-only |
| WO | `POST /work-orders/{id}/assign` | Trưởng KT |
| WO | `POST /work-orders/{id}/start` | KTV được giao |
| WO | `PATCH /work-orders/{id}/checklist/{item_id}` | KTV được giao |
| WO | `POST /work-orders/{id}/evidence` | KTV được giao |
| File | `GET /attachments/{id}/content` | Người có quyền xem WO |
| WO | `POST /work-orders/{id}/cost-lines` | KTV được giao hoặc Trưởng KT |
| Charge | `POST /pending-charges/{id}/decision` | Kế toán, có SoD |
| Charge | `POST /pending-charges/{id}/post` | Kế toán |
| WO | `POST /work-orders/{id}/submit` | KTV được giao |
| WO | `POST /work-orders/{id}/accept` | Trưởng KT hoặc CSKH proxy |
| WO | `POST /work-orders/{id}/cancel` | Trưởng KT |
| WO | `POST /work-orders/{id}/reopen` | Trưởng KT |
| WO | `POST /work-orders/{id}/close` | Trưởng KT hoặc CSKH |
| Asset | `POST/GET /assets[/{id}]` | Trưởng KT tạo; role được phép đọc |
| Plan | `POST/GET /maintenance-plans[/{id}]` | Trưởng KT tạo; role được phép đọc |
| Scheduler | `POST /maintenance/scheduler/run` | Admin hoặc Trưởng KT |
| Occurrence | `POST /maintenance-occurrences/{id}/defer` | Trưởng KT |

### Contract danh sách Service Request

`GET /service-requests` nhận duy nhất ba query parameter: `status` tùy chọn,
`page` mặc định `1` và `page_size` mặc định `20`, tối đa `100`. `status` chỉ
nhận `NEW`, `TRIAGED`, `IN_PROGRESS`, `WAITING_INFO`, `RESOLVED`, `CLOSED`
hoặc `CANCELLED`.

### Contract lựa chọn tạo Service Request

`GET /service-request-form-options` không nhận tenant, site hoặc role từ
client. Không truyền `building_id` thì response chỉ có `buildings` mà CSKH đã
được cấp trong active site; `categories` và `units` là mảng rỗng. Khi truyền
`building_id`, backend vẫn kiểm tra lại đúng grant CSKH trước khi trả category
active toàn site hoặc của tòa đó, và unit đúng tòa. Ngoài scope trả
`404 ERR-SCOPE-NOTFOUND`; vai trò khác trả `403 ERR-FORBIDDEN`.
Grant CSKH với `building_id = null` không phải quyền site-wide: response rỗng
và mọi building selection vẫn trả `404 ERR-SCOPE-NOTFOUND`.

```json
{
  "buildings": [{"id": "UUID", "code": "B1", "name": "Tòa B1"}],
  "categories": [{"id": "UUID", "code": "TECHNICAL", "name": "Kỹ thuật", "building_id": null}],
  "units": [{"id": "UUID", "unit_number": "B1-0101", "building_id": "UUID"}]
}
```

Response có dạng:

```json
{
  "items": [{
    "id": "uuid",
    "code": "SR-...",
    "title": "...",
    "unit_id": "uuid-or-null",
    "unit_number": "A-1201-or-null",
    "building_id": "uuid",
    "building_code": "A",
    "building_name": "Tòa A",
    "status": "NEW",
    "priority": "HIGH",
    "sla_deadline": "2026-09-12T10:00:00Z",
    "created_at": "2026-09-12T06:00:00Z"
  }],
  "page": 1,
  "page_size": 20,
  "total": 1
}
```

`total` được tính sau scope và `status`, trước phân trang. Kết quả sắp xếp ổn
định theo `created_at DESC, id DESC`. Scope không có query parameter: backend
đọc tenant, active site, role và building grant từ phiên/DB. Admin, Giám đốc và
Kế toán đọc theo site hoặc building grant hiện hành; CSKH và Trưởng kỹ thuật
bắt buộc có building grant khớp; KTV chỉ thấy Request có Work Order giao cho
chính tài khoản đó. Role ngoài ma trận bị từ chối `403`; role hợp lệ nhưng không
có dữ liệu trong scope nhận danh sách rỗng.

Mọi endpoint nghiệp vụ yêu cầu JWT; tenant, site, role và building scope được
đọc lại từ database. ID ngoài scope trả `404 ERR-SCOPE-NOTFOUND`. Các command
thay đổi trạng thái dùng `expected_version`; stale version trả `409
ERR-CONFLICT`.

Các lệnh tạo Request, WO, evidence, Cost Line, Asset, Plan, scheduler run và
posting nhận `Idempotency-Key`. Cùng actor/scope/operation/key và payload trả lại
kết quả cũ; cùng key với payload khác trả conflict. Unique constraint trong
PostgreSQL bảo vệ dữ liệu nền. Xử lý hai request đồng thời cùng key và outbox
publisher/retry thuộc hardening/R5, không được suy diễn từ contract R2 này.

## Ảnh, audit và sự kiện

- Evidence chỉ nhận PNG/JPEG khớp magic/footer, tối đa 10 MiB, lưu checksum
  SHA-256 và tên file đã làm sạch trong private storage; download trả
  `Cache-Control: private, no-store` và kiểm lại quyền WO.
- File không khớp allowlist magic/MIME được giữ trong namespace quarantine, có
  audit/outbox và không được dùng làm evidence. Retry cùng idempotency key không
  tạo bản quarantine thứ hai. File hợp lệ chỉ tải qua signed link TTL ngắn, ràng
  buộc actor/tenant/active-site/building/attachment và vẫn kiểm lại quyền WO.
- Lát local không tích hợp antivirus engine ngoài allowlist nội dung hiện có.
- Mọi transition chính ghi audit có actor, scope, correlation ID và before/after
  phù hợp. Trigger PostgreSQL chặn UPDATE/DELETE trên `audit_events`.
- Domain event được ghi cùng transaction để làm outbox anchor. Worker publish,
  retry và quan sát trạng thái là phạm vi R5 (`AC-22`).

## Ánh xạ acceptance

| AC | Bằng chứng tự động chính |
|---|---|
| `AC-06` | `test_ac06_two_work_orders_resolve_only_after_both_terminal` |
| `AC-08`, `AC-09`, `AC-10` | `test_ac08_ac09_ac10_charge_sod_audit_and_reversal` |
| `AC-38`, `AC-39` | `test_ac38_ac39_scheduler_and_maintenance_completion` |
| `AC-24` | R2 attachment test ở `tests/test_r2_integration.py`; ImportRun CSV/file evidence R1 ở `tests/test_import_runs_postgres.py` |
| Scope/idempotency/link/triage | `test_r2_request_idempotency_and_scope_are_enforced` và các test liên quan trong `tests/test_r2_integration.py` |
| Form CSKH theo scope | `test_service_request_form_options_are_cskh_scoped`; `frontend-integration.test.js` và `staff-ux.cjs` kiểm payload/browser slice |
| SLA, image, text, VND | `tests/test_r2_domain.py` |

Lần kiểm chứng R2 ban đầu ngày 12/09/2026 trên PostgreSQL 18.4/TLS cô lập:

- DB trống nâng đến Alembic `0005`; upgrade và seed chạy lặp: PASS.
- `alembic check`: không có schema drift.
- Toàn bộ regression: **173 passed**, không skip, 2 warning deprecation từ
  Starlette/httpx/AnyIO.
- Offline Alembic SQL đi từ `BEGIN` đến `COMMIT`; `pip check`, compileall và
  `git diff --check`: PASS.

Lần runner toàn repo mới nhất ngày 13/09/2026 đã nâng local head tới `0006`,
kiểm `0005 -> 0006 -> 0005`, migration/seed repeat, schema drift và **184 test
pass**. Nó bao gồm regression R2 nhưng cũng bao gồm closeout R1; xem
`VALIDATION.md`/`R1_IMPORT_CONTRACT.md` để biết trạng thái verdict review của
AC-02/AC-24.

Lần kiểm chứng lại ngày 13/09/2026 cho lát form/list/create CSKH: runner
PostgreSQL 18.4/TLS cô lập thực hiện empty-DB migration, migration/seed repeat,
`alembic check` và regression hiện tại: **185 passed, 3 warnings in 44.79s**.
`npm test` đạt **51 passed**, Vite build PASS; `staff-ux.cjs` đạt **31 checks**
trên browser với API transport được mock có chủ đích. Browser slice kiểm
`login -> /auth/me -> Bearer`, list phân trang, form options, create có
`Idempotency-Key`, loading/empty/retry, 401 và `ERR-SCOPE-NOTFOUND`; nó không
thay thế một demo frontend gọi backend đã triển khai ngoài máy local.

Không tạo migration trong lát này. Kết quả local không tự động chứng minh
R1/Gate B đã đủ mọi AC tiền đề, không chứng minh migration đã được áp dụng lên
Aiven/production và không thay thế review độc lập.
