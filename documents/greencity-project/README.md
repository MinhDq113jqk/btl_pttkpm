# Hệ thống quản lý vận hành khu đô thị

Hướng dẫn cài đặt, cấu hình database local, seed/reset, khởi chạy và kiểm thử
được duy trì tại [README gốc của repository](../../README.md). Dùng tài liệu đó
làm nguồn thao tác duy nhất để tránh lệch port hoặc hướng dẫn seed. Demo seed
bị tắt mặc định; credential phải được cấp ngoài repository.

## Quy ước repository

Repository `btl_pttkpm` công bố bundle tài liệu dưới
`documents/greencity-project`, gồm cả governance Phase 1. Repository
`greencity` chỉ nhận mã nguồn, không nhận bundle này. `.env`, `.venv`,
`node_modules` và `dist` không đưa lên GitHub.

## Danh mục tài liệu đặc tả & quản trị

- **`BAO_CAO_DAC_TA_HE_THONG_GREENCITY_HOAN_CHINH.docx`**: Báo cáo tổng hợp đặc tả yêu cầu hệ thống và kiến trúc toàn diện GreenCity (SRS, danh mục Use Case phân cấp động từ chuẩn UML, kiến trúc module, kế hoạch định hướng sản phẩm và ma trận truy vết RTM) đã hoàn thiện qua 5 vòng phản biện học thuật.
- **`roadmap_v2.md`**: Nguồn yêu cầu và phạm vi chức năng qua các Tranche R1-R7 & V1.
- **`roadmap_v3.md`**: Roadmap triển khai bổ sung cho luồng demo và hoàn thiện
  local; không thay thế roadmap v2.
- **`FINAL_CODE_SUBMISSION_PLAN.md`**: Kế hoạch cuối để tích hợp `excel-data` và
  hoàn tất code nộp giáo viên.
- **`FINAL_CODE_SUBMISSION_20_TASKS.md`**: Checklist thực thi `FCS-01..FCS-20`
  kèm dependency, DoD và evidence.
- **`DATA_PROVENANCE.md`**: Hồ sơ nguồn `excel-data`, phân loại local-only và
  năm quyết định User/Owner còn chờ phê duyệt trước khi tích hợp dữ liệu thật.
- **`DATA_SOURCE_MANIFEST.json`**: Inventory metadata-only của 12 workbook,
  gồm hash, cấu trúc sheet và số dòng; không chứa giá trị ô hoặc header gốc.
- **`FINAL_SUBMISSION_CHECKLIST.md`**: Danh sách test và Final Submission Gate
  phải chạy trên cùng package candidate trước khi nộp.
- **`V3-00_TRACEABILITY_MATRIX.md`**: Ma trận menu → UI → API → database → test và bằng chứng triển khai local.
- **`diagrams/diagram_0_overview.png`**: Sơ đồ tổng quan các luồng nghiệp vụ hiện có.
- **`governance/phase-1/`**: Bộ tài liệu thẩm định bảo mật, kiểm soát thay đổi và bằng chứng vận hành Phase 1.
- **`phase-3/PHASE_3_IMPLEMENTATION.md`**: Bằng chứng diễn tập triển khai local; chưa phải phê duyệt production hoặc Go/No-Go.
- **`phase-3/V3-16_PRESENTATION_EVIDENCE.md`**: Checklist trình bày, recovery và
  output kiểm chứng V3-12..V3-16.
