# Hệ thống quản lý vận hành khu đô thị

Đồ án môn Phân tích và thiết kế phần mềm.

## Phạm vi nghiệp vụ

- Quản lý vận hành kỹ thuật
- Vệ sinh môi trường
- An ninh và an toàn
- Dịch vụ khách hàng

## Luồng nghiệp vụ cốt lõi

Phát sinh yêu cầu hoặc lịch định kỳ → tạo phiếu công việc → phân công nhân viên → xử lý → kiểm tra/nghiệm thu → lưu lịch sử và báo cáo.

## Tài liệu kiến trúc & Roadmap

- [`roadmap_v2.md`](roadmap_v2.md): **Master Baseline v2.0** — Nguồn sự thật trung tâm của đề tài (chuẩn hóa 20 quyết định kiến trúc, 18 use cases, ma trận phân quyền và quy tắc Data Scope).

## Ứng dụng giao diện BQL

Giao diện Desktop Workspace dành cho Ban quản lý và nhân viên vận hành 8 vai trò:
- Hướng dẫn trải nghiệm 8 vai trò: xem [`greencity-app/STAFF_WORKSPACE.md`](greencity-app/STAFF_WORKSPACE.md).
- Trợ lý thông minh Green Assistant: xem [`greencity-app/GREEN_ASSISTANT.md`](greencity-app/GREEN_ASSISTANT.md).
- Cải tiến trải nghiệm Desktop: xem [`greencity-app/UX_DESKTOP_REVIEW.md`](greencity-app/UX_DESKTOP_REVIEW.md).

### Khởi chạy giao diện:
```bash
cd greencity-app
npm install
npm run dev
```

## Backend FastAPI — R1–R6 local evidence

Backend hiện có lát R2 CSKH/kỹ thuật/bảo trì, closeout R1 cho Person--Unit và
CSV ImportRun/file safety; R3 có vệ sinh/an ninh; R4 có billing, công nợ và
thanh toán thủ công cơ bản. Runner PostgreSQL/TLS cô lập ngày 14/09/2026 đã
kiểm `0008 -> 0009 -> 0010 -> 0009 -> 0010`, DB trống đến head `0010`,
migration/seed lặp, `alembic check` và **218 test pass** (2 warning
deprecation). R4 gồm receipt/source idempotent, hàng đợi payment thiếu mã,
match đúng building, allocation oldest-debt-first và Overpayment Credit tách
riêng; không có refund, automatic credit application hoặc maker-checker.

R5 Task 1--5 bổ sung transactional outbox/inbox, Audit Explorer theo
correlation ID và CAP-BI Dashboard backend read-only tại một `as_of`: SLA,
maintenance đến hạn, vệ sinh cần làm lại, incident mở và AR debt từ ledger.
Quyền/scope lấy từ server; dashboard chỉ `admin`/`director`, Audit Explorer
của accountant chỉ tài chính. Task 5 thêm API acceptance cho 4 Golden Flows
nghiệp vụ cùng Control-and-audit Flow thứ năm và route read-only Maintenance
History; runner PostgreSQL local đã kiểm migration
đến `0011`, DB trống, seed repeat, drift và **223 tests pass** (2 warnings).
Đây mới là evidence backend local; Gate B/C, Aiven/production và review độc lập
chưa có.

R6 bổ sung lát **Resident Self-Service**: danh tính cư dân được liên kết với
`Person` và quan hệ `Unit` hiệu lực; cư dân có thể tạo/cập nhật yêu cầu dịch vụ,
theo dõi timeline và tải bằng chứng, xem công nợ/hóa đơn/payment read-only theo
một `as_of`, cùng hộp thư thông báo cá nhân. Migration `0012`/`0013` đã được
kiểm từ DB trống; runner ngày 16/09/2026 đạt **238 tests pass, 2 warnings**.
OpenAPI, scope, idempotency, optimistic locking, private evidence và giới hạn
được ghi tại [backend/R6_CONTRACT.md](backend/R6_CONTRACT.md) và
[backend/R6_RELEASE_EVIDENCE.md](backend/R6_RELEASE_EVIDENCE.md).

V1 Parcel Task 1–5 bổ sung migration `0014`/`0015`, Parcel Desk intake → ready →
handover/exception, Case/Incident linkage, private evidence và audit timeline.
Task 5 ghép Golden Flow receive → handover và exception → Case → Incident →
evidence → audit qua HTTP API, giữ snapshot bất biến và kiểm retry/duplicate;
Task 4 dùng lại `CaseRecord`, `SecurityIncident`, `Attachment` hiện có; scope,
idempotency, quarantine, signed-link và OpenAPI được khóa tại
[backend/V1_PARCEL_CASE_EVIDENCE_CONTRACT.md](backend/V1_PARCEL_CASE_EVIDENCE_CONTRACT.md).
Exit evidence và lượt review kỹ thuật được ghi tại
[backend/V1_PARCEL_TASK5_EXIT_EVIDENCE.md](backend/V1_PARCEL_TASK5_EXIT_EVIDENCE.md)
và [backend/R7_REVIEW.md](backend/R7_REVIEW.md).
Runner PostgreSQL/TLS ngày 17/09/2026 đạt **253 tests pass, 2 warnings**,
empty DB/seed repeat/drift/shutdown PASS; frontend `npm test` **68/68**, Vite
build PASS và Parcel UX **13/13 checks**. Đây là lát **Implemented & Verified
Local**; không suy ra Gate/production.

Đây là **Implemented & Verified Local** cho các lát cắt đã nêu, không phải
thông báo Gate B/C, rollout Aiven/production hay verdict review độc lập.
Closeout R1 được truy vết tại [backend/R1_CLOSEOUT.md](backend/R1_CLOSEOUT.md).
Xem phạm vi, endpoint, state machine, role/scope và giới hạn theo từng release
tại [backend/R2_CONTRACT.md](backend/R2_CONTRACT.md),
[backend/R3_CONTRACT.md](backend/R3_CONTRACT.md) và
[backend/R4_CONTRACT.md](backend/R4_CONTRACT.md),
[backend/R5_CONTRACT.md](backend/R5_CONTRACT.md) và
[backend/R5_EXIT_EVIDENCE.md](backend/R5_EXIT_EVIDENCE.md),
[backend/R6_CONTRACT.md](backend/R6_CONTRACT.md) và
[backend/R6_RELEASE_EVIDENCE.md](backend/R6_RELEASE_EVIDENCE.md).

Desktop frontend đã nối login/session, Service Request, Unit 360°, vệ sinh,
an ninh/PCCC, tab kế toán tối thiểu và Resident Portal. Regression frontend có
**68/68 checks**, Vite build PASS; Resident UX có **17/17 checks** và Parcel UX
có **13/13 checks**. Billing
Golden Flow có 10 và payment Golden Flow có 14 UX checks; payment/resident retry
sau response bị mất giữ cùng Idempotency-Key. `0015` chưa được tuyên bố đã apply
lên Aiven/production; bằng chứng local không thay thế verdict review độc lập.

- [Baseline hiện tại, role matrix, bằng chứng và OPEN_DECISIONS](BACKEND_BASELINE.md).
- [Contract foundation Plan 2 và các phần chưa hoàn thành](backend/API_CONTRACT.md).
- [Closeout AC/evidence R1](backend/R1_CLOSEOUT.md).
- [Contract và bằng chứng R2](backend/R2_CONTRACT.md).
- [Contract data foundation R3](backend/R3_CONTRACT.md).
- [Contract billing/payment R4](backend/R4_CONTRACT.md).
- [Contract Resident Self-Service R6](backend/R6_CONTRACT.md) và
  [kịch bản demo R6 UI/API](greencity-app/R6_UI_API_DEMO.md).
- [Cài đặt, environment, Aiven, migration, chạy server/Swagger, frontend, seed và testing](backend/README.md).

## Bảo vệ dữ liệu cục bộ

Thư mục `documents/` chỉ chứa tài liệu tham khảo và danh sách thành viên, được giữ cục bộ và không đưa lên GitHub (`.gitignore`). Không thêm mật khẩu, token hoặc dữ liệu cá nhân vào repository.
