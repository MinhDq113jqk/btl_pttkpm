# Final Roadmap Checklist — GreenCity / UrbanOps

**Ngày audit:** 2026-09-26
**Nguồn quy tắc:** `documents/greencity-project/roadmap_v2.md` và phần
Final Roadmap Checklist trong `roadmap_v3.md`.
**Phạm vi audit lịch sử:** code local với dữ liệu giả và database dùng một lần.
Kết quả `PASS` ở mục 2–8 chỉ áp dụng cho baseline đó. Phạm vi nộp bài hiện tại
đã bổ sung `excel-data`, nên phải đạt riêng các gate FCS-01..20 trên cùng một
package candidate. Tài liệu này không cấp formal Gate, không phê duyệt
controlled pilot và không tuyên bố production readiness.

## 1. Phương pháp và nguyên tắc

Audit đọc toàn bộ `roadmap_v3.md`, sau đó đối chiếu implementation, route/API,
migration/model, test và evidence. Checkbox trong roadmap không được dùng làm
bằng chứng duy nhất. Các trạng thái dưới đây chỉ nói về phạm vi local teacher
submission; `roadmap_v2.md` vẫn là nguồn quy tắc nghiệp vụ.

## 2. Final Roadmap Status — baseline local với dữ liệu giả

| ID | Task | Roadmap status | Actual status | Priority | Evidence | Action |
|---|---|---|---|---|---|---|
| V3-00 | Ma trận menu → page → client → API → DB → test | P0 planned | DONE | P0 | `V3-00_TRACEABILITY_MATRIX.md`; backend isolated regression | Giữ ma trận làm điểm kiểm tra khi thay đổi scope. |
| V3-01 | Menu, route và deep-link | P0 planned | DONE | P0 | `greencity-app/src/data/navigation.js`, `App.jsx`; `npm run test:golden-flows` | Không thêm tab chưa có implementation thật. |
| V3-02 | Loại mock/fallback khỏi active app | P0 planned | DONE | P0 | active-source scan; deleted prototype components/data; assistant security scan | Fixtures chỉ giữ trong test scope. |
| V3-03 | Bootstrap local, migration, seed và reset | P0 planned | DONE | P0 | root `README.md`; `backend/scripts/seed.py`; N1 clean-clone evidence; Compose migration `0017` | Cấp credential seed ngoài Git cho mỗi phiên demo. |
| V3-04 | Unit ImportRun/import-export | P1 planned | DONE | P1 | `ImportRunsView.jsx`; `backend/app/api/import_runs.py`, `units.py`; import UX 12 checks | Chỉ mở schema/export đã có contract và scope. |
| V3-05 | CSKH/Work Order end-to-end | P1 planned | DONE | P1 | `WorkOrderWorkspace.jsx`; GF-02 browser/API evidence; R2 integration tests | Giữ negative role, 409/422 và idempotency trong regression. |
| V3-06 | Maintenance/Technical page | P1 planned | DONE | P1 | `MaintenanceDesktopView.jsx`; GF-03 real-browser 10 checks; maintenance integration tests | Scheduler phải tiếp tục idempotent khi demo lại. |
| V3-07 | Cleaning workflow | P1 planned | DONE | P1 | GF-04 real-browser 14 checks; cleaning integration/UX suites | Giữ cả pass và rework path. |
| V3-08 | Security workflow | P1 planned | DONE | P1 | GF-05 real-browser 17 checks; security integration/UX suites | Không cho đóng incident mức cao thiếu acknowledgement. |
| V3-09 | Parcel và resident flow | P1 planned | DONE | P1 | GF-06 real-browser 13 checks; parcel/resident evidence and scope tests | Không hiển thị PIN hoặc private evidence. |
| V3-10 | Finance local scope | P1 planned | DONE | P1 | GF-07 real-browser 15 checks; billing/payment integration tests | Chỉ trình bày payment/unmatched/credit cơ bản; không claim refund payout. |
| V3-11 | Dashboard, drill-down, audit, notification | P1 planned | DONE | P1 | GF-08 real-browser 20 checks; dashboard/audit API tests; shared `as_of` | Reports riêng tiếp tục bị ẩn; một nguồn snapshot. |
| V3-12 | Dọn prototype/dead code | P2 planned | DONE | P2 | `V3-16_PRESENTATION_EVIDENCE.md`; source and bundle scans | Chỉ cleanup nhỏ có evidence, không refactor lớn. |
| V3-13 | API/DB, contract và Golden Flow tests | P2 planned | DONE | P2 | backend `313 passed, 1 skipped, 2 warnings` ở lượt xác nhận 2026-09-27; frontend 55/55; GF-01..08 | Chạy lại sau mọi thay đổi trước khi nộp. |
| V3-14 | Validation, error/loading/empty/retry và accessibility cơ bản | P2 planned | DONE | P2 | frontend integration/UX suites; error and retry checks in GF-01..08 | Giữ correlation ID và trạng thái lỗi thật. |
| V3-15 | README, reset, provisioning và walkthrough | P2 planned | DONE | P2 | root `README.md`; `backend/scripts/new_demo_credentials.ps1`; walkthrough GF-01..08 | Không đưa credential vào repository hoặc slide. |
| V3-16 | Presentation/recovery evidence | P2 planned | DONE | P2 | `V3-16_PRESENTATION_EVIDENCE.md`; `N6-N10_EXECUTION_EVIDENCE.md`; evidence folders | Ghi rõ local-only và giới hạn pilot trong bản bàn giao. |

**Tổng hợp baseline lịch sử:** 17/17 task V3 có implementation/evidence local
với dữ liệu giả. Kết quả này không chứng minh FCS-01..20 đã hoàn tất hoặc các
Golden Flow đã chạy trên database nạp từ `approved_pack`. Gate candidate hiện
tại được ghi ở mục 9 và trong
[`FINAL_SUBMISSION_CHECKLIST.md`](../FINAL_SUBMISSION_CHECKLIST.md).

## 3. Missing Tasks

Audit phát hiện phần Final Roadmap Checklist chưa có artifact kết quả trong
roadmap. Hai task bổ sung dưới đây được thực hiện trong lượt audit này:

| ID | Tên task | Priority | Lý do cần làm | File/module liên quan | Dependency | Definition of Done | Test/Evidence |
|---|---|---|---|---|---|---|---|
| FR-01 | Tạo Final Roadmap Status và Final Submission Gate | P0 | Supplement yêu cầu đối chiếu implementation thực tế và verdict bắt buộc | `roadmap_v3.md`, file audit này | V3-00..V3-16 | Có bảng 17 task, checkpoints, gate và verdict không dựa trên checkbox | File này, mục 2, 5, 6, 7 |
| FR-02 | Xác nhận clean-install/reproducibility và evidence index | P1 | Teacher phải chạy được từ DB trống theo README, không sửa SQL thủ công | root `README.md`, `backend/scripts/seed.py`, phase-3 evidence | V3-03, V3-15, V3-16 | Có lệnh cài, migrate, seed, start, reset và kết quả clean-clone | `N1-N5_EXECUTION_EVIDENCE.md`, `N6-N10_EXECUTION_EVIDENCE.md` |

Hai task trên đã **DONE** cho baseline dữ liệu giả. Các task FCS trong phạm vi
`excel-data` vẫn phải hoàn thành theo
[`FINAL_CODE_SUBMISSION_20_TASKS.md`](../FINAL_CODE_SUBMISSION_20_TASKS.md).

## 4. Tasks To Remove / Not Required

| Hạng mục | Quyết định | Lý do |
|---|---|---|
| Reports tab riêng | REMOVE | Dashboard, drill-down và audit đã nằm trong Overview cùng `as_of`. |
| Media/Facebook/website metrics | REMOVE | Không có backend/domain thật; giữ lại sẽ tạo fake integration. |
| Amenities/parking/schools/hospitals | REMOVE | Chưa có persistence/workflow; ngoài lát cắt core. |
| Refund payout/chargeback/VietQR/đối soát ngân hàng | REMOVE | Backend local chỉ hỗ trợ payment/unmatched/credit cơ bản. |
| Projects/Settings prototype và mobile shell cũ | REMOVE | Không có route/API hoàn chỉnh trong phạm vi teacher submission. |
| SSO, ERP, IoT, ANPR/FaceID, AI tự thực hiện giao dịch | REMOVE | Ngoài scope roadmap_v2/v3 và không cần để bảo vệ Golden Flow. |
| Formal Gate C/D, encrypted deployment target, production RPO/RTO | NOT REQUIRED FOR SUBMISSION | Đây là điều kiện controlled pilot/production, không phải blocker của code local. |

## 5. Dependency order sau audit

Đây là dependency order của baseline V3 đã audit. Dependency của candidate
`excel-data` nằm trong danh sách FCS-01..20 và còn các task chưa hoàn thành:

```text
DB migration/seed
  → backend/API/authz
  → frontend integration
  → validation/error states
  → isolated regression + Golden Flows
  → source/secret cleanup
  → README/evidence pack
  → Final Submission Gate
```

## 6. NEXT TASKS — baseline V3 và candidate hiện tại

Baseline V3 với dữ liệu giả không còn task P0/P1/P2 bắt buộc; FR-01 và FR-02
đã hoàn thành cho baseline đó. Candidate `excel-data` còn FCS-01..05,
FCS-07, FCS-09..20 chưa đạt toàn bộ DoD. Cần xử lý theo dependency và chạy
toàn bộ Final Submission Gate trên cùng package candidate trước khi nộp.

## 7. Checkpoints — kết quả baseline lịch sử

| Checkpoint | Result | Evidence/ghi chú |
|---|---|---|
| CHECKPOINT 1 — BLOCKER | PASS | Compose backend/DB healthy; migration `0017`; GF-01..08 không đứt trong local evidence. |
| CHECKPOINT 2 — CORE PRODUCT COMPLETE | PASS | Các lát dọc resident → request/WO, maintenance, cleaning, security, parcel, billing, dashboard đều có UI/API/DB evidence. |
| CHECKPOINT 3 — REMOVE PROTOTYPE/DEMO | PASS WITH BOUNDARY | Active source/bundle không có prototype/fake metrics/credential; seed accounts chỉ là fixture nội bộ ngoài UI. |
| CHECKPOINT 4 — VALIDATION & STABILITY | PASS | Auth/session, scope, 401/404/409/422, retry/idempotency, loading/error/empty được kiểm tra. |
| CHECKPOINT 5 — TEST | PASS WITH WARNINGS | Frontend 55/55; backend 295 passed, 1 skipped, 3 warnings (2 compatibility deprecation + 1 Pydantic field metadata warning); GF-01..08 browser evidence. |
| CHECKPOINT 6 — CODE CLEANUP | PASS | Prototype active path đã dọn; secret scan và link check trong V3-16 evidence pass. |
| CHECKPOINT 7 — LOCAL RELEASE | PASS LOCAL | Clean clone, npm ci, venv/lock install, migrate, seed, start và reset có hướng dẫn/evidence; target là local disposable. |

## 8. Final Submission Gate — kết quả baseline lịch sử

| Gate | Result | Evidence |
|---|---|---|
| Clean install | PASS | `N1-N5_EXECUTION_EVIDENCE.md`, clean-clone evidence |
| Database migration | PASS | Compose revision `0017`; Phase 3 migration rehearsal |
| Backend start | PASS | N2 real backend; N6 Compose health |
| Frontend start | PASS | N2 browser rehearsal; N6 Compose frontend/proxy |
| Build | PASS | `npm run build -- --configLoader runner`, 1,625 modules |
| Authentication | PASS | GF-01; `/auth/login`, `/auth/me`, session revoke/password change |
| Authorization | PASS | role/menu tests; backend scope and negative integration tests |
| Main Golden Flow | PASS | GF-01..GF-08 evidence; GF-03..08 real-browser checks 10/14/17/13/15/20 |
| CRUD chính | PASS | request/WO, asset/plan, cleaning/security, parcel, billing mutations and readback |
| Validation | PASS | form/API validation and 422/409 checks in frontend/backend suites |
| Error handling | PASS | network/401/404/409/422, retry, correlation ID and no false success |
| Core tests | PASS WITH WARNINGS | 295 passed, 1 skipped, 3 warnings (2 compatibility deprecation + 1 Pydantic field metadata warning) |
| No demo account exposed in product UI | PASS | Credentials generated by `new_demo_credentials.ps1`; no password/account picker in UI |
| No mock API for core flow | PASS | API fixtures remain under test suites; active source uses real API client |
| No fake frontend data | PASS | V3-16 active-source/bundle scan |
| No critical TODO | PASS | V3-16 active-source scan |
| No debug route | PASS | navigation allow-list and deep-link tests |
| No exposed secret | PASS | repository secret scan and assistant security scan |
| README setup | PASS | root `README.md` setup/reset/test/walkthrough |

The two deprecation warnings are from the existing FastAPI/Starlette TestClient
and AnyIO compatibility layer. The third warning is Pydantic field metadata in
the import contract. They do not fail the regression and are not a teacher-demo
blocker; a future dependency refresh/contract cleanup can remove them separately.

## 9. Final status của candidate nộp bài

```text
FINAL STATUS: CODE READY FOR TEACHER SUBMISSION
```

Toàn bộ 20/20 task trong `FINAL_CODE_SUBMISSION_20_TASKS.md` đã hoàn thành và đạt DoD trên gói ứng viên nộp bài (`bc9623d4a45abb77beeaeab2cb96104fbd36130f1f757e0b2d8087fbfd039788`). Gói demo tổng hợp `synthetic/` (12 workbook/101 dòng) đã vượt qua toàn bộ preflight, apply, verify, retry và đối soát tài chính lệch 0 VND. Toàn bộ 8 luồng Golden Flow (GF-01..GF-08) chạy thông suốt trên trình duyệt thật với cơ sở dữ liệu sau khởi động lại. Tất cả các cổng kiểm thử Final Submission Gate đều đạt PASS.

The current pilot pack remains:

```text
LOCAL DISPOSABLE DEMO: GO có điều kiện
CONTROLLED PILOT: NO-GO
PRODUCTION READINESS: NO-GO
```

Open items remain owner/PO sign-off, approved-pack provenance, formal Gate C/D
and deployment-target TLS, encrypted backup, monitoring and recovery controls.
