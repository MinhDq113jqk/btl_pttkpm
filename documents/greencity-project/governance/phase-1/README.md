# Phase 1 — Baseline và release governance

Gói này triển khai các artefact của Phase 1 theo
`C:\Users\LEGION\btl\documents\greencity-project\5phase.md`.

| Hạng mục | Artefact | Trạng thái tại 2026-09-22 |
| --- | --- | --- |
| OR-01 | [Đối chiếu baseline](BASELINE_RECONCILIATION.md) | Chờ PO + Tech Lead phê duyệt bốn quyết định |
| OR-02 | [Inventory, data flow, third-party register, RACI](SYSTEM_AND_DATA_INVENTORY.md) | Có bản dự thảo; owner theo vai trò cần xác nhận |
| OR-03 | [Threat model và risk register](THREAT_MODEL_AND_RISK_REGISTER.md) | Có năm finding; chưa finding nào được chấp nhận rủi ro |
| OR-03 | [Dự thảo policy](SECURITY_POLICY_DRAFT.md) | Chờ PO + Security phê duyệt trước khi công bố `SECURITY.md` ở gốc repo |
| OR-04 | `.github/workflows/quality-security.yml` | Đã cấu hình; cần một run GitHub từ clean clone |
| OR-05 | [Change control](RELEASE_CHANGE_CONTROL.md) và `.github/workflows/release-evidence.yml` | Đã cấu hình; không tạo tag/release tự động |

Xem [evidence pack](PHASE_1_EVIDENCE_PACK.md) để biết phần nào đã được chạy
cục bộ và phần nào còn cần phê duyệt hoặc xác nhận trên CI.

**Exit Phase 1 hiện là `NOT PASS`.** Tài liệu không thay thế phê duyệt của PO,
Security, Release Owner hoặc một run CI từ clean clone.
