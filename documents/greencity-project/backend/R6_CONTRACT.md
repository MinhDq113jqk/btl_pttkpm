# R6 — Resident Self-Service contract

**Ngày chốt local:** 16/09/2026
**Trạng thái:** `Implemented & Verified Local`
**Phạm vi:** một lát self-service cho cư dân đã xác minh; không phải Gate C,
production readiness hay approval nghiệp vụ.

## 1. Phạm vi và nguyên tắc

R6 cho phép cư dân:

1. tạo, xem, chỉnh sửa yêu cầu dịch vụ đang tiếp nhận;
2. xem timeline/audit của yêu cầu và upload bằng chứng private;
3. xem công nợ, invoice snapshot và payment đã ghi nhận tại một mốc `as_of`;
4. đọc và acknowledge thông báo của chính account.

Danh tính bắt đầu từ `Account.person_id` và quan hệ `Person--Unit` còn hiệu lực.
Mỗi request lại suy ra tenant, site hiện hành, building và unit ở server qua
`UserContext`; frontend không phải nguồn quyền. Quan hệ bị thu hồi hoặc site
không hợp lệ trả cùng `404 ERR-SCOPE-NOTFOUND`, không lộ tài nguyên.

## 2. Schema/migration

| Revision | Thay đổi | Rollback guard |
|---|---|---|
| `0012` | `accounts.person_id`, composite FK cùng tenant, unique `(tenant_id, person_id)` và index | Từ chối downgrade nếu còn account link |
| `0013` | `attachments.service_request_id`, FK tới `service_requests`, index lookup và check đúng một parent (`work_order_id` hoặc `service_request_id`) | Từ chối downgrade nếu còn resident evidence |

Seed lặp tạo account `resident_west`, Person/Unit West và role `resident` có
building grant tương ứng. Seed không tạo invoice, payment, allocation, credit,
unmatched payment hoặc AR history.

## 3. API contract

Base path là `/api/v1`; mọi route yêu cầu Bearer session do `/auth/login` cấp.

| Method | Path | Request/response chính |
|---|---|---|
| `GET` | `/resident/service-request-options` | `buildings[]`, `units[]`, `categories[]` đã lọc scope |
| `GET` | `/resident/service-requests?page=&page_size=` | `items[]`, `page`, `page_size`, `total` |
| `POST` | `/resident/service-requests` | Body `unit_id`, `category_id`, `title`, `description`, `priority`; bắt buộc `Idempotency-Key` |
| `GET` | `/resident/service-requests/{request_id}` | Request view, SLA timestamps và `version` |
| `PATCH` | `/resident/service-requests/{request_id}` | `expected_version` + ít nhất một trường sửa; bắt buộc `Idempotency-Key` |
| `GET` | `/resident/service-requests/{request_id}/timeline` | Audit timeline đã rút gọn cho cư dân |
| `GET` | `/resident/service-requests/{request_id}/evidence` | Metadata evidence không chứa storage path |
| `POST` | `/resident/service-requests/{request_id}/evidence` | Raw PNG/JPEG, `X-File-Name`, `Idempotency-Key`; trả attachment hoặc quarantine |
| `GET` | `/resident/service-requests/{request_id}/evidence/{attachment_id}/signed-link` | URL content có expiry, ràng account/site/request/attachment |
| `GET` | `/resident/service-requests/{request_id}/evidence/{attachment_id}/content?signed_token=` | Bearer + signed token; file `private, no-store` |
| `GET` | `/resident/billing/summary?as_of=` | AR ledger balance integer VND tại cutoff |
| `GET` | `/resident/billing/invoices?as_of=` | Invoice đã phát hành và item snapshot trước cutoff |
| `GET` | `/resident/billing/payments?as_of=` | Payment của billing account trong scope trước cutoff |
| `GET` | `/resident/notifications?include_read=&page=&page_size=` | Inbox account/site, `unread_count` |
| `POST` | `/resident/notifications/{notification_id}/read` | Acknowledge read; replay an toàn |

`as_of` phải là RFC3339 timezone-aware; server chuẩn hóa UTC. Billing summary
dùng `SUM(debit_vnd - credit_vnd)` với `effective_at <= as_of`, không dùng cache
dư nợ trên invoice. Portal không có route ghi payment/allocation/invoice/ledger.

Các path trên là toàn bộ Resident surface được kiểm OpenAPI; không tự thêm
method ghi khác.

## 4. Bất biến nghiệp vụ và bảo mật

- **Scope:** chỉ role `resident` có identity/person/unit hiệu lực; không tin
  claim role/tenant/site/unit hoặc hidden field từ client.
- **Request:** chỉ `NEW` và `WAITING_INFO` được sửa; `PATCH` dùng row lock,
  compare-and-update `version`; stale version trả `409 ERR-CONFLICT`.
- **Idempotency:** cùng actor + operation + key + fingerprint replay đúng
  resource; key cùng intent khác payload trả conflict; advisory lock và unique
  record chống double-submit/concurrency.
- **Evidence:** giới hạn kích thước theo `MAX_EVIDENCE_BYTES`, kiểm magic bytes
  và MIME, SHA-256, tên/path traversal; file lỗi vào quarantine và không được
  signed/download.
- **Audit/correlation:** create/update/evidence/read/download ghi audit; outbox
  event nằm trong transaction nguồn. Response lỗi dùng `ErrorEnvelope` và
  `X-Correlation-ID`, không echo secret hoặc arbitrary payload.
- **Privacy:** notification join đúng `recipient_account_id` và source event
  cùng tenant/site; timeline chỉ trả resource của cư dân.

## 5. Frontend surface

`ResidentPortalView.jsx` được chọn khi `/auth/me` trả duy nhất role `resident`.
Portal có ba tab: Yêu cầu dịch vụ, Công nợ & hóa đơn, Thông báo; tự giữ một
`as_of` cho ba API billing, chỉ gửi identifier do server trả về và hiển thị lỗi
network/correlation thay vì fallback mock. Session resident giữ token trong RAM.

## 6. Acceptance/evidence map

| Mục | Test/evidence | Kết quả |
|---|---|---|
| Migration empty DB, repeat seed, drift, downgrade guard | `scripts.test_isolated`, `scripts.test_migration_0012`, `scripts.test_migration_0013` | PASS, head `0013` |
| Scope/identity/revocation, create/update/replay, timeline/evidence | `tests/test_r6_resident_service_requests_integration.py` | PASS |
| Ledger cutoff, invoice snapshot, read-only/authorization | `tests/test_r6_resident_billing_integration.py` | PASS |
| Inbox recipient scope, unread/read audit/correlation | `tests/test_r6_resident_notifications_integration.py` | PASS |
| Outbox race and hot-path indexes | `tests/test_r6_hardening_integration.py` | PASS |
| OpenAPI method allowlist and error/correlation contract | `tests/test_contract.py` | PASS |
| Full backend regression | PostgreSQL 18/TLS disposable | **238 passed, 2 warnings** |
| Frontend regression/build | `npm test`; `npm run build` | **63/63; PASS** |
| Resident browser UX | `npm run test:resident` | **17/17 checks; PASS** |

## 7. Giới hạn release

Evidence trên chỉ áp dụng checkout local và PostgreSQL disposable. Chưa bao
gồm Aiven/production deployment, backup/restore rehearsal, payment gateway
thật, đăng ký cư dân công khai, refund/chargeback, AI, hay chữ ký Gate B/C.
Không chạy downgrade hoặc seed runner trên database vận hành.

Lệnh tái lập authoritative (từ `backend/`):

```powershell
.\.venv\Scripts\python.exe -m scripts.test_isolated --pg-bin 'C:\Program Files\PostgreSQL\18\bin' --openssl 'C:\Program Files\Git\usr\bin\openssl.exe'
```
