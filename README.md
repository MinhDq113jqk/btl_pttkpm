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

## Backend FastAPI — R1/R2 local evidence

Backend hiện có lát R2 CSKH/kỹ thuật/bảo trì và closeout R1 cho Person--Unit,
CSV ImportRun/file safety. Lần runner PostgreSQL/TLS cô lập ngày 13/09/2026
đạt head `0006`, migration `0005 -> 0006 -> 0005`, migration/seed lặp,
`alembic check` và **184 test pass** (2 warning deprecation). Xem phạm vi,
endpoint, state machine, role/scope và giới hạn tại
[backend/R2_CONTRACT.md](backend/R2_CONTRACT.md) và
[backend/R1_IMPORT_CONTRACT.md](backend/R1_IMPORT_CONTRACT.md).

Desktop frontend đã nối read-only cho login → `/auth/me` → danh sách Service
Request → Unit 360° bằng session thật; các phân hệ ngoài lát này vẫn là demo hoặc
chưa mở sprint. `0006` chưa được tuyên bố đã apply lên Aiven/production. Bằng
chứng local không tự động chứng minh mọi AC tiền đề R1, Gate C hoặc R3--R5 đã
pass; trạng thái review/traceability hiện tại nằm tại checklist/VALIDATION.

- [Baseline hiện tại, role matrix, bằng chứng và OPEN_DECISIONS](BACKEND_BASELINE.md).
- [Contract foundation Plan 2 và các phần chưa hoàn thành](backend/API_CONTRACT.md).
- [Contract CSV ImportRun và file safety R1](backend/R1_IMPORT_CONTRACT.md).
- [Contract và bằng chứng R2](backend/R2_CONTRACT.md).
- [Cài đặt, environment, Aiven, migration, chạy server/Swagger, frontend, seed và testing](backend/README.md).

## Bảo vệ dữ liệu cục bộ

Thư mục `documents/` chỉ chứa tài liệu tham khảo và danh sách thành viên, được giữ cục bộ và không đưa lên GitHub (`.gitignore`). Không thêm mật khẩu, token hoặc dữ liệu cá nhân vào repository.
