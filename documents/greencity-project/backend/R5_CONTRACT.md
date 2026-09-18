# R5 Task 1 — Contract, Outbox và correlation

## Scope của lát cắt này

Revision `0011` biến `DomainEvent` sẵn có thành transactional outbox có trạng
thái giao nhận và thêm `notification_read_models` làm inbox projection. Đây là
lát cắt backend R5 cho `AC-22` và `NFR-05`; chưa là Dashboard/KPI hay nghiệm thu
toàn bộ R5/Gate C.

Một service nghiệp vụ muốn gửi notification gọi `enqueue_notification(...)`
trong **cùng SQL transaction** với thay đổi nguồn. Service ghi đồng thời:

- `DomainEvent` có `correlation_id`, event/resource và payload immutable chứa
  `recipient_account_id`, `template_code`, `template_snapshot`.
- Một `NotificationReadModel` unique theo `domain_event_id`, để inbox biết ngay
  người nhận/template nào đang chờ, retry hoặc dead-letter.

Không có HTTP command cho client tự tạo notification hay chọn recipient. Đây là
quyết định an toàn: recipient/template là quyết định của domain service, không
được tin từ payload trình duyệt.

## Outbox state và retry

`DomainEvent.delivery_status` dùng năm trạng thái:

```text
PENDING -> PROCESSING -> PUBLISHED
                    \-> RETRY_SCHEDULED -> PROCESSING
                    \-> DEAD_LETTER
```

Worker `OutboxDispatcher` claim một hàng bằng `FOR UPDATE SKIP LOCKED`, lưu
lease UUID/thời hạn trước khi gọi channel ngoài transaction. Mỗi delivery gửi
`DomainEvent.id` làm idempotency key cho downstream channel. Kết quả stale lease
không được ghi đè attempt mới. Lỗi channel chỉ lưu mã ổn định, không persist
exception text/provider response có thể chứa secret hay PII.

Mặc định có tối đa 3 attempt với exponential backoff (1, 2 giây, tối đa 300
giây); sau đó là `DEAD_LETTER`. Cùng lúc, read model chuyển
`RETRY_SCHEDULED`/`DEAD_LETTER` và giữ `last_error` để inbox không báo thành
công giả. `POST /outbox/events/{id}/retry` reset một dead-letter/retry có kiểm
soát về `PENDING`; gọi lại khi đã `PENDING` là idempotent, không nhân event.

R5 chỉ cung cấp channel port/worker contract, không cấu hình Email/SMS/Push
provider hoặc tự chạy process nền trong API. Vận hành phải inject channel đã
thực thi idempotency key, chạy worker trusted riêng và theo dõi dead-letter.

## OpenAPI và role/scope

Mọi route dưới `/api/v1`, error envelope chung và `X-Correlation-ID` được kế
thừa từ middleware hiện hữu.

| Route | Quyền backend thực | Scope/điều kiện |
|---|---|---|
| `GET /audit-events` | `admin`, `director`, `accountant` | Admin/director theo active site + building grant; accountant chỉ resource tài chính cùng scope. Filter: `correlation_id`, `resource_type`, `resource_id`, timezone-aware `as_of`, `limit`, `offset`. |
| `GET /notifications` | Người nhận đã đăng nhập | Chỉ đúng `tenant_id`, active site và `recipient_account_id` từ session; mặc định chỉ unread. |
| `POST /notifications/{id}/read` | Người nhận đã đăng nhập | Chỉ chính notification đó; idempotent; ghi audit `NotificationRead`. |
| `GET /outbox/events` | `admin` hoặc `director` có site-wide grant | Chỉ active tenant/site; chỉ metadata giao nhận, không expose payload snapshot. |
| `POST /outbox/events/{id}/retry` | Như trên | Retry thủ công idempotent, ghi audit `OutboxDeliveryRetryRequested`. |

Roster backend hiện hành là đúng tám role: `admin`, `director`, `cskh`,
`accountant`, `technical_lead`, `technician`, `cleaning`, `security`. Không có
role `auditor`; mock Auditor phía frontend không làm phát sinh grant, token hay
quyền audit API. Quyết định này cố ý hẹp hơn cột Kiểm toán trong roadmap cho đến
khi roster/migration/policy backend được duyệt riêng.

## Correlation và ranh giới evidence

Domain mutation, `AuditEvent` và `DomainEvent` phải lấy cùng request
`correlation_id`. Khi worker gửi event, nó chuyển cùng ID trong `OutboxMessage`;
audit explorer filter theo ID đó để truy vết source/timeline/actor/scope.

## Task 2 — CAP-BI read-only Dashboard và Audit Explorer

Task 2 không thêm bảng hay migration: đây là projection chỉ đọc trên các record
R2--R4 và AR ledger append-only đã có. Vì vậy schema head vẫn là `0011`; runner
migration vẫn kiểm `0010 -> 0011 -> 0010 -> 0011` trước regression.

| Route | Quyền backend thực | Contract |
|---|---|---|
| `GET /dashboard?as_of=<RFC3339 timezone-aware>` | `admin`, `director` | Một snapshot cùng tenant, active site và building grant do server suy ra. `as_of` bắt buộc; naive/missing trả `422 ERR-VALIDATION`. |
| `GET /dashboard/drill-down/{metric}?as_of=...` | Như dashboard | `metric` allowlist: `sla_overdue`, `maintenance_due`, `cleaning_rework`, `open_incidents`, `ar_debt`; trả source rows cùng cutoff, không có command. |
| `GET /audit-events?correlation_id=<UUID>` hoặc `?resource_type=...&resource_id=<UUID>&as_of=...` | `admin`, `director`, `accountant` | Audit Explorer hiện hữu. Timeline từ dòng drill-down giữ đúng resource và cutoff; accountant chỉ xem resource tài chính trong scope, không có dashboard vận hành tổng hợp. |

Dashboard trả đúng năm KPI từ **một** `as_of`: số Service Request quá SLA,
Maintenance Occurrence đến hạn chưa hoàn thành tại cutoff, Cleaning Task có
`REWORK_REQUIRED`, Security Incident mở và tổng công nợ VND. `ar_debt_vnd` và
drill-down công nợ được tính bằng `SUM(debit_vnd - credit_vnd)` trên
`ArLedgerEntry.effective_at <= as_of`; không đọc `BillingInvoice.outstanding_vnd`
hay một balance cache. Đây là `INV-01`.

Các cutoff dùng timestamp lifecycle, không diễn dịch status hiện tại thành lịch
sử: SLA xét deadline và `resolved_at`/`closed_at`; maintenance xét `due_at` và
`completed_at`; incident xét thời điểm tạo và đóng/giải quyết; cleaning chỉ xét
`REWORK_REQUIRED` terminal với `submitted_at`. Định nghĩa này không bao gồm
SLA history của một request đã resolve rồi reopen ở R2, vì lifecycle cũ không có
status-event đầy đủ cho trường hợp đó; bổ sung status history là thay đổi schema
riêng, không được giả lập bằng status hiện tại.

`test_r5_dashboard_integration.py` dùng oracle cố định: một record đóng sau
cutoff được tính, record đóng trước cutoff bị loại; năm drill-down reconcile với
KPI và AR drill-down cộng lại đúng `ar_debt_vnd`. Test cũng chặn CSKH, director
chỉ có grant một building, `as_of` missing/naive và kiểm Audit Explorer theo
correlation ID. PostgreSQL disposable kiểm `0010 -> 0011 -> 0010 -> 0011`, DB
trống/seed lặp/drift và regression **222 passed, 2 warnings in 36.82s**. Đây là
evidence local cho `AC-25`, phần backend `AC-45` và `INV-01`, không phải bằng
chứng frontend, Gate C, deployment hay independent review.

`0011` fail-closed khi downgrade nếu còn notification projection hoặc delivery
state không còn biểu diễn được ở `0010`. Không sửa event/audit lịch sử để đi
ngược migration.

Kiểm thử PostgreSQL cô lập trong `test_r5_outbox_integration.py` kiểm:

- `AC-22`: channel timeout không rollback source; retry dùng đúng event ID,
  sau publish không delivery lại; retry vượt giới hạn thành dead-letter và
  manual reset không nhân event.
- `NFR-05`: cùng correlation ID hiện ở source audit và outbox event; audit API
  giữ role/scope hiện hành, không có Auditor backend.

R5 hiện vẫn không tuyên bố real channel provider, scheduler daemon, frontend
Dashboard/Audit Explorer, independent review/Gate hay production readiness.

## Task 5 — Five Golden Flows và maintenance history read model

`GET /assets/{asset_id}/maintenance-history` là route read-only cho
`admin`/`director`/`cskh`/`technical_lead` có grant đúng building. Nó chỉ trả
history asset thuộc tenant, active site và scope server-derived; ngoài scope trả
`404 ERR-SCOPE-NOTFOUND`. Không có API sửa/xóa history.

`test_r5_golden_flows_integration.py` dùng seed lặp làm tiền đề, sau đó thực
hiện bốn mutation flow qua HTTP API: CSKH-to-cash, maintenance-to-history,
cleaning-to-case và patrol-to-incident. Sau đó Control-and-audit flow chỉ đọc
một `as_of`, reconcile đủ năm KPI/drill-down/AR và tra Audit Explorer theo bốn
correlation ID. Test kiểm replay idempotent, scope negative, snapshot invoice
và `INV-01..02`; SQL chỉ được đọc làm oracle. Evidence, demo boundary và ma
trận AC nằm tại [R5_EXIT_EVIDENCE.md](R5_EXIT_EVIDENCE.md).
