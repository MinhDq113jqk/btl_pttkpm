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

