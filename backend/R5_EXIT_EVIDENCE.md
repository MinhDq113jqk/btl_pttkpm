# R5 Task 5 — Five Golden Flows & Exit Evidence (local)

## Kết luận phạm vi

**Implemented & Verified Local** cho năm Golden Flow qua HTTP API, migration
regression và UI contract regression. Đây không phải Gate B/C, deployment
Aiven/production, provider notification thật, hay independent review.

Mọi mutation trong `test_r5_golden_flows_integration.py` đi qua route công khai
với JWT, server-derived scope, `Idempotency-Key` và `X-Correlation-ID`. Seed
lặp là tiền đề duy nhất; không có insert/update/delete SQL trong flow. Các
truy vấn SQL oracle chỉ đọc để kiểm invariant không có endpoint ghi tương ứng.

## Ma trận AC và invariant

| Mã | Bằng chứng local | Kết quả |
|---|---|---|
| AC-22 | `test_r5_outbox_integration.py`, notification UX | Timeout không rollback nguồn; retry/dead-letter và idempotency đúng. |
| AC-25 | `test_r5_dashboard_integration.py`, dashboard UX | 5 KPI và drill-down cùng `as_of`, scope server-side. |
| AC-36 | R4 retry/concurrency regression, notification UX | Replay dùng cùng key, không tạo bản ghi/hiển thị thành công giả. |
| AC-45 | `test_r5_golden_flows_integration.py` | 4 flow nghiệp vụ + Control-and-audit flow: 5 KPI drill-down, AR reconcile, audit correlation và scope negative. |
| INV-01 | Dashboard/drill-down AR và Flow 4 | Invoice/payment đưa dư nợ của Billing Account về 0 từ AR ledger, không dựa cache invoice. |
| INV-02 | Flow 1 + read-only query | Pending Charge `POSTED` có đúng posting anchor; không Invoice Item mồ côi. |

## Five Golden Flows

1. CSKH tạo/triage Service Request, Technical Lead tạo và phân công Work
   Order, Technician upload evidence/checklist, Accountant duyệt Pending
   Charge, Billing Run snapshot charge thành invoice item/posting anchor, nhận
   CASH và allocation tất toán; Lead nghiệm thu/đóng, CSKH đóng yêu cầu.
2. Lead tạo Asset/Plan, scheduler chạy lại an toàn, Technician hoàn tất WO,
   Lead nghiệm thu; `GET /assets/{id}/maintenance-history` trả history và
   `next_due_at` tăng đúng một kỳ. Asset ngoài site trả `404 ERR-SCOPE-NOTFOUND`.
3. Director tạo/assign Cleaning Shift, Cleaner nộp checklist FAIL tạo đúng
   rework Case/WO.
4. Security tạo incident FIRE mức HIGH từ patrol, evidence, acknowledgement
   hai role và đóng incident theo transition hợp lệ.
5. Director dùng cùng một `as_of` để xem dashboard, drill-down cả năm KPI,
   reconcile tổng AR từ ledger rồi mở Audit Explorer theo bốn correlation ID.

Mỗi flow nghiệp vụ dùng correlation ID riêng và Audit Explorer của Director truy
vết các event nguồn. Flow thứ năm chỉ đọc một `as_of`, đối chiếu cả năm KPI với
drill-down/AR và truy vết lại bốn correlation ID. Các API read có correlation
mới không làm thay đổi correlation của mutation đã ghi.

## Migration và regression

Lệnh authoritative, chạy từ `backend`:

```powershell
.\.venv\Scripts\python.exe -m scripts.test_isolated --pg-bin "C:\Program Files\PostgreSQL\18\bin" --openssl "C:\Program Files\Git\usr\bin\openssl.exe"
```

Kết quả 15/09/2026: PostgreSQL 18/TLS disposable kiểm migration `0005`,
`0007`, `0008`, `0009`, `0010`, `0011`; DB trống, upgrade repeat, seed repeat,
`alembic check`, regression và shutdown đều PASS: **223 passed, 2 warnings in
82.83s**. Warnings là deprecation của Starlette TestClient, không có test skip
trong runner.

## Frontend và ownership

| Owner | File/phạm vi độc lập |
|---|---|
| Backend | `app/api/maintenance.py`, `schemas/r2.py`, `services/billing.py`, `tests/test_r5_golden_flows_integration.py`, API/evidence docs. |
| Frontend | Các UI hiện có `CreateServiceRequestForm`, Cleaning, Security, Billing, Dashboard/Notification và test UX tương ứng. Không có frontend file bị backend sửa. |

Kết quả frontend local: `npm test` **62/62**, `npm run build` PASS; Playwright
smoke qua Vite: cleaning **6**, security **7**, billing **10**, payment **14**,
dashboard **24**, notification **17** checks PASS.

Các script UX hiện intercept/mock transport để kiểm UX, permission visibility,
retry và không fallback mock ngầm. Chúng **không** là bằng chứng browser-to-live
PostgreSQL; bằng chứng mutation end-to-end là acceptance test HTTP ở backend
trên DB disposable nêu trên.

## Hướng dẫn demo không sửa DB tay

1. Chạy migration/seed/test bằng runner cô lập ở trên; dùng lại seed chỉ qua
   login UI/API, không lấy/sửa ID trực tiếp trong database.
2. Đăng nhập lần lượt các role seed đã được cấp quyền; tạo Service Request,
   Cleaning Shift, Security Shift và Billing flow từ các màn hình tương ứng.
3. Với thao tác chưa có màn hình điều phối riêng (WO/maintenance scheduler),
   gọi route đã ghi trong OpenAPI `/docs` bằng token của đúng role. Luôn truyền
   `Idempotency-Key`, lưu `X-Correlation-ID`, rồi tra `/api/v1/audit-events`.
4. Kết thúc tại Dashboard Director với `as_of` timezone-aware; mở drill-down
   và Audit Explorer để đối soát. Không paste mật khẩu, token hay connection
   string vào slide/log/evidence.

## Ngoài phạm vi

- UI điều phối Work Order/maintenance đầy đủ là backlog riêng; không giả vờ nó
  đã được thêm trong Task 5.
- Không có refund/chargeback, automatic credit application, real notification
  provider, production deploy hoặc release sign-off.
