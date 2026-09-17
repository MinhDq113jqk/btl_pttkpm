# R6 — Resident Self-Service & release evidence (local)

## Kết luận và ranh giới

R6 Resident Self-Service được **Implemented & Verified Local** khi chạy runner
PostgreSQL/TLS cô lập ở dưới. Evidence này chỉ xác nhận code, migration và
regression trong checkout hiện tại. Nó không là phê duyệt Gate, release
sign-off, deployment Aiven/production, backup/restore rehearsal, hay
independent review.

Không chạy các lệnh rehearsal hoặc downgrade trên database vận hành.

## Lệnh tái lập authoritative

Chạy từ thư mục `backend` trên Windows. Runner tạo credential, TLS certificate
và PostgreSQL cluster localhost mới; không kế thừa `PG*`, `DATABASE_*` hoặc
`RUN_DB_*`.

```powershell
.\.venv\Scripts\python.exe -m scripts.test_isolated --pg-bin 'C:\Program Files\PostgreSQL\18\bin' --openssl 'C:\Program Files\Git\usr\bin\openssl.exe'
```

Pass chỉ hợp lệ khi runner đồng thời báo `Isolated PostgreSQL regression: PASS`
và `Test PostgreSQL shutdown: PASS`. Nếu bị ngắt, chạy lại toàn bộ trên cluster
mới; không dùng output một phần làm evidence.

## Snapshot đã xác thực

Ngày 16/09/2026, runner trên PostgreSQL 18/TLS disposable đã PASS: migration
path `0005`, `0007`–`0013`, DB trống, migration/seed lặp, Alembic drift,
regression **238 passed, 2 warnings in 45.50s**, và shutdown. Hai warning là
deprecation từ Starlette `TestClient`/AnyIO; không có test R6 nào bị skip trong
runner.

Frontend cùng ngày đạt `npm test` **63/63**, `npm run build` PASS và
`npm run test:resident` **17/17 checks**. Resident UX chạy qua dev server
localhost với API transport giả lập; đây là evidence UI riêng, không phải
browser-to-PostgreSQL evidence.

## Ma trận hardening R6

| Hạng mục | Evidence local | Điều được kiểm chứng |
|---|---|---|
| Migration & drift | `scripts/test_isolated.py`; path `0005`, `0007`–`0013`; empty DB, repeat migration/seed, `alembic check` | Head `0013` tạo được từ DB rỗng, upgrade/seed lặp và models không sinh drift tự động. Migration `0012`/`0013` downgrade fail-closed khi còn resident data/evidence. |
| Scope regression | `test_r6_resident_service_requests_integration.py`, `test_r6_resident_billing_integration.py`, `test_r6_resident_notifications_integration.py` | Tenant/site/building/unit được suy ra ở server; token forged, người cùng nhà, site/tenant khác và quan hệ cư dân đã thu hồi không đọc/ghi được. |
| Duplicate & optimistic locking | `test_r6_resident_service_requests_integration.py` | Create/evidence replay cùng idempotency key trả cùng resource; payload khác bị conflict; PATCH cần `expected_version` và bản stale trả `409 ERR-CONFLICT`. |
| Outbox concurrency | `test_r6_hardening_integration.py` | Hai dispatcher với hai database session cùng claim một event đến hạn chỉ có một delivery; event kết thúc `PUBLISHED`, `attempt_count=1`, lease được xóa. |
| Ledger/audit bất biến | `test_r6_resident_billing_integration.py`, `test_r6_resident_service_requests_integration.py` | Billing summary lấy số dư từ AR ledger tại cùng `as_of`, không dùng snapshot invoice; mutation trực tiếp audit event bị PostgreSQL từ chối. |
| Observability | `test_r6_resident_notifications_integration.py`, `test_contract.py` | `ResidentNotificationRead` ghi audit với request correlation và source notification correlation; lỗi API dùng `ErrorEnvelope`/`X-Correlation-ID` mà không echo marker nhạy cảm. |
| OpenAPI least surface | `test_contract.py::test_r6_resident_openapi_surface_has_only_intended_methods` | 12 path Resident Service Request/Billing/Notification chỉ công bố phương thức đã duyệt: billing chỉ-read; notification chỉ có acknowledgement `POST`; request chỉ có create/update/evidence mutation cần thiết. |
| Performance baseline | `test_r6_hardening_integration.py` | Cluster sau migration có các index vật lý: `ix_ar_ledger_entries_account_effective`, `ix_notification_read_models_recipient`, `ix_domain_events_dispatch_due`. Đây là baseline tồn tại index, không phải claim latency/throughput. |

## Release checklist còn lại ngoài evidence local

1. Owner review diff/migration, quyền database runtime và OpenAPI trước khi
   phê duyệt môi trường khác.
2. Có kế hoạch backup/restore riêng, UAT dữ liệu giả và Go/No-Go được ký nhận.
3. Thực hiện independent review theo quy trình dự án nếu release cần điều đó.
4. Không suy diễn kết quả disposable localhost thành Aiven/production readiness.

## Artifacts liên quan

- `alembic/versions/0012_r6_resident_identity_scope.py` và
  `0013_r6_resident_service_request_evidence.py`: migration resident R6.
- `tests/test_r6_resident_service_requests_integration.py`,
  `tests/test_r6_resident_billing_integration.py`,
  `tests/test_r6_resident_notifications_integration.py`: HTTP acceptance và
  scope/audit/idempotency/locking R6.
- `tests/test_r6_hardening_integration.py`: race outbox và index baseline.
- `tests/test_contract.py`: OpenAPI resident methods và global correlation/error
  contract.
- `R6_CONTRACT.md`: schema/migration, endpoint, invariant và ma trận acceptance
  được chốt cho R6.
