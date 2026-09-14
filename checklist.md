# BẢNG THEO DÕI TIẾN ĐỘ DỰ ÁN GREENCITY (CHECKLIST)

> **Tài liệu tham chiếu:** [`roadmap_v2.md`](file:///C:/Users/LEGION/btl/_pttkpm/roadmap_v2.md) (Master Baseline v2.0) & [`review3.md`](file:///C:/Users/LEGION/btl/_pttkpm/review3.md)
> **Cập nhật lần cuối:** 13/09/2026
> **Quy ước ký hiệu:**
> - `[x]` : **Đã hoàn thành & Đã kiểm chứng ở tier được ghi rõ** (ví dụ: `Implemented & Verified Local`; không tự là Gate/release)
> - `[-]` : **Đang thi công / Đang kiểm thử (In Progress)**
> - `[ ]` : **Chưa bắt đầu (Pending / Backlog)**
> - `[~]` : **`SPEC-ONLY`** (Đặc tả thiết kế, không bắt buộc code trong Core MVP)

---

## 📊 1. Bảng điều khiển tiến độ tổng hợp (Progress Dashboard)

> ⚠️ **Lưu ý chuẩn cứ kiểm chứng ([`backend/VALIDATION.md`](file:///C:/Users/LEGION/btl/_pttkpm/backend/VALIDATION.md)):
> Các kết quả hiện tại là **bằng chứng local** trên cụm PostgreSQL cô lập cho từng lát cắt, **chưa phải tuyên bố Gate B/C, release hoàn tất hay production-ready**. Không dùng số lượng test để suy diễn coverage ngoài ma trận AC được ghi rõ.

| Release / Phân hệ | Ngân sách | Đánh giá hiện trạng | Trạng thái kỹ thuật thực tế | Bằng chứng kiểm chứng |
|---|:---:|:---:|---|---|
| **R0: Product Gate & Baseline** | 64 h | **Candidate** | Khóa scope `BUILD` vs `SPEC-ONLY`, ERD neo, ma trận 8 role | Đã chạy kiểm thử cô lập |
| **R1: Nền tảng & Căn hộ 360°** | 80 h | **Implemented & Verified Local** | Auth, Data Scope, RBAC theo tòa, Unit 360° (`/360`) read-only, Person--Unit và CSV ImportRun | `AC-01`, `AC-02`, `AC-03`, `AC-24`, `AC-35`: ma trận local tại `backend/R1_CLOSEOUT.md`; không phải Gate B/C |
| **R2: CSKH & Vận hành Kỹ thuật** | 112 h | **Implemented & Verified Local** | Backend 17 bảng, API SR/WO/Scheduler/Audit đã kiểm chứng; UI Đăng nhập, Form tạo SR & DS CSKH đã nối | `AC-06`, `AC-08..10`, `AC-38..39` Pass local; `AC-07` là `SPEC-ONLY` |
| **R3: Vệ sinh & An ninh** | 112 h | **Implemented & Verified Local** | Migration `0007` (9 bảng); Ca/tuyến vệ sinh, checklist đạt/không đạt, sổ giao ca, tuần tra, sự cố PCCC & escalation | `AC-40..43` Pass local; `greencity-app/artifacts/security-ux` |
| **R4: Phí & Hóa đơn cơ bản** | 80 h | **Implemented & Verified Local** | Migrations `0008..0010`; Biểu phí, Billing Run, Hóa đơn snapshot, Thu tiền, Đối soát Unmatched, Phân bổ ALG-05, Overpayment Credit ALG-07 | `AC-11..14`, `AC-16..19`, `AC-30`, `AC-44` Pass local; `R4_CONTRACT.md` |
| **R5: Điều hành & 4 Golden Flows** | 64 h | **Chưa mở sprint** | Dashboard layout & Correlation ID sẵn sàng | Chuẩn bị triển khai sau khi đóng gói R4 |
| **Hardening & Kiểm thử hồi quy** | 80 h | **Đang thực hiện** | Backend 218 pass; frontend 53/53 + Playwright smoke pass; 0 schema drift ở lần chạy backend gần nhất | Bằng chứng kiểm thử tự động local PostgreSQL 18.4 cô lập |

* **Tổng ngân sách kế hoạch:** 592 person-hour (Dự phòng 80h trong hạn mức 672h).
* **Tiến độ tổng thể dự án:** Hoàn tất toàn bộ nền tảng R1, R2, R3, R4 trên môi trường kiểm thử local. Sẵn sàng mở R5.
* **Hạ tầng kiểm thử tự động:**
  * **Backend PostgreSQL 18.4 cô lập:** **218/218 tests PASS** (3 warning deprecation, 0 schema drift; kiểm tra lặp `0005 ↔ 0007 ↔ 0008 ↔ 0009 ↔ 0010`).
  * **Frontend Node Test Runner:** **53/53 tests PASS**; Vite build pass (1.94s); smoke UI staff, cleaning, security, billing, payment pass.
  * **Alembic Head local:** `0010_r4_payment_reconciliation.py`.

---

## 🎯 2. Tiêu điểm Sprint hiện tại (Active Sprint Focus)

> **Mục tiêu ưu tiên:** Đã hoàn tất nghiệm thu local toàn bộ R1, R2, R3, R4 (`218/218 tests backend`, `53/53 tests frontend`). Chuẩn bị kích hoạt **Sprint R5: Điều hành & 4 Golden Flows**.

- [x] Backend: Thêm endpoint `GET /api/v1/service-requests` phân trang, lọc status, bảo vệ building scope và chính sách `assigned-only` cho KTV.
- [x] Backend: Bổ sung 2 bài test PostgreSQL kiểm chứng phân quyền danh sách và KTV (165 tests pass).
- [x] Frontend: Xây dựng `apiClient.js` với cơ chế lưu token trong RAM (In-Memory JWT), không ghi vào storage.
- [x] Frontend: Nối form `StaffLogin.jsx` thật $\rightarrow$ `/auth/me` $\rightarrow$ Tự sinh menu và nhãn vai trò từ server.
- [x] Frontend: Nối bảng `TasksDesktopView.jsx` với `GET /api/v1/service-requests`, xử lý loading, empty, 401, error retry.
- [x] Frontend: Nối màn hình tra cứu **Căn hộ 360° (Unit 360° Read-Only)** gọi `GET /api/v1/units/{unit_id}/360`; chỉ gửi Unit ID và hiển thị projection do server trả về.
- [x] Test: API client/UI state Unit 360° và switch-site pass local (`npm test` 51/51; smoke staff 30 checks; build pass).
- [x] Review Unit 360°: Antigravity #1 `STATUS: NEEDS_REVISION`; Codex sửa lỗi 401/stale request hợp lý; Review #2 cuối `STATUS: PASS`. Không có lượt 3.
- [x] Git: closeout stage chỉ gồm source/test/docs R1 được nêu rõ; không `git add .`, không stage `plan1.md`/`plan2.md`, R2/frontend ngoài scope và không migration mới.
- [x] Đánh giá mở Sprint R3: **Chưa mở**; closeout local R1 không là điều kiện tự động để mở R3.
- [x] AC-01: bề mặt R1 cross-site UI/API/export/file trả scope-safe 404, traceability tại `backend/R1_CLOSEOUT.md`.
- [x] AC-02: ImportRun CSV 1.000 dòng mixed, replay và concurrency PASS local; 950 Unit hợp lệ được ghi, 50 warning, 25 skip, 25 lỗi.
- [x] AC-03: Person sở hữu 2 Unit và thuê Unit thứ 3, ratio/hiệu lực/migration path PASS local.
- [x] AC-24: quarantine, checksum source/error, `AttachmentQuarantined`/EVT-23, signed link actor/scope/expiry PASS local.
- [x] AC-35: switch-site chỉ gửi `site_id`, refresh `/auth/me`, loại stale response/401 và reset workspace PASS local.

---

## 📋 3. Chi tiết tiến độ từng Release

---

### 🔹 R0: Product Gate & Architecture Baseline (Đã kiểm chứng local)

- [x] **Đặc tả & Ranh giới sản phẩm:**
  - [x] Phân định rõ ràng phạm vi `BUILD` vs `SPEC-ONLY` ([`roadmap_v2.md`](file:///C:/Users/LEGION/btl/_pttkpm/roadmap_v2.md) §11.6).
  - [x] Khóa bộ 8 vai trò Core MVP (Admin, Giám đốc, Kế toán, CSKH, Trưởng KT, Kỹ thuật viên, Vệ sinh, An ninh).
  - [x] Wireflow giao diện desktop cho nhân viên & BQL.
- [x] **Hạ tầng kiểm thử & Kiến trúc:**
  - [x] Script test cô lập [`scripts/test_isolated.py`](file:///C:/Users/LEGION/btl/_pttkpm/backend/scripts/test_isolated.py) (Cluster PostgreSQL 18 dùng một lần, TLS `verify-full`, SCRAM).
  - [x] Cưỡng chế chuẩn tiền tệ VND integer `ARC-07` và chuẩn thời gian UTC `ARC-09`.
  - [x] Tiêu chuẩn hóa mã định danh `IDF-*` và danh mục lỗi nghiệp vụ `ERR-*`.
  - [x] **Trạng thái:** Hoàn tất bộ baseline candidate R0 trên local.

---

### 🔹 R1: Nền tảng, Dữ liệu nền & Căn hộ 360° (Lát cắt candidate)

#### 1. Database & Schema
- [x] Migration `0001_initial_foundation.py`: Bảng `tenants`, `sites`, `accounts`, `account_roles`.
- [x] Migration `0002_r1_foundation.py`: Bảng `buildings`, `floors`, `units`, `persons`, `unit_relationships`.
- [x] Migration `0003_role_building_scope.py`: Phân quyền `building_id` cho từng vai trò theo tòa.
- [x] Bảng `audit_events` trong Migration 0004 (SEC-04: Lưu vết giao dịch bền vững append-only).
- [x] Migration `0005_r1_person_unit_relationship.py`: tỷ lệ sở hữu, khoảng hiệu lực nửa mở và chặn cross-tenant/overflow đã kiểm chứng local; không tạo migration mới trong closeout.
- [x] Migration `0006_r1_import_runs.py`: ImportRun/row, checksum/quarantine và scope database đã kiểm chứng local; không tạo migration mới trong closeout.

#### 2. Backend API & Nghiệp vụ
- [x] `POST /api/v1/auth/login`: Xác thực tài khoản, cấp JWT token (SECRET_KEY $\ge$ 32 bytes).
- [x] `GET /api/v1/auth/me`: Trả về thông tin phiên, active site, vai trò và danh sách tòa được phân quyền.
- [x] `GET /api/v1/readiness`: Kiểm tra kết nối DB và tính tương thích phiên bản schema (`EXPECTED_SCHEMA_REVISION = "0006"` trên lát local hiện tại).
- [x] `GET /api/v1/units/{unit_id}/360`: Tra cứu căn hộ 360°, chặn cross-site, projection phân quyền (Trưởng KT/An ninh: `residents_visible=false`, `residents=[]`), masking số điện thoại (`phone_masked`) và email (`email_masked`).
- [x] Bảo mật phạm vi dữ liệu: Cưỡng chế `tenant_id`, `site_id`, `building_id` ở tầng truy vấn SQL; trả `404 ERR-SCOPE-NOTFOUND` thống nhất khi truy cập ngoài quyền.

#### 3. Frontend UI & Tích hợp
- [x] Màn hình đăng nhập thật [`StaffLogin.jsx`](file:///C:/Users/LEGION/btl/_pttkpm/greencity-app/src/components/staff/StaffLogin.jsx) nối `POST /auth/login`.
- [x] Quản lý phiên in-memory trong [`apiClient.js`](file:///C:/Users/LEGION/btl/_pttkpm/greencity-app/src/services/apiClient.js) (không lưu `localStorage`).
- [x] Dựng menu và nhãn vai trò tự động từ `GET /auth/me` trong [`authSession.js`](file:///C:/Users/LEGION/btl/_pttkpm/greencity-app/src/data/authSession.js).
- [x] Màn hình Tra cứu Căn hộ 360° đọc-only nối `GET /api/v1/units/{unit_id}/360`; có idle/loading/network retry/401/`ERR-SCOPE-NOTFOUND` và projection cư dân.

#### 4. Tiêu chí thoát & Bằng chứng kiểm chứng
- [x] `AC-01`: bề mặt R1 cross-site UI/API/export/file đã có ma trận function/test/contract local tại `backend/R1_CLOSEOUT.md`.
- [x] `AC-02`: CSV ImportRun 1.000 dòng mixed, durable row result, retry và concurrency PASS local.
- [x] `AC-03`: fixture Person sở hữu 2 căn và thuê căn thứ 3, truy vấn hai chiều, tỷ lệ/hiệu lực và constraint PostgreSQL PASS local.
- [x] `AC-24`: quarantine, checksum file, audit/outbox `AttachmentQuarantined`/EVT-23, retry idempotent và signed link actor/scope/expiry PASS local.
- [x] `AC-35`: switch-site reset workspace/cache/filter, loại response/401 cũ và refresh `/auth/me` bằng token mới PASS local.

---

### 🔹 R2: CSKH & Vận hành Kỹ thuật (Lát cắt candidate đã kiểm chứng local)

#### 1. Database & Schema
- [x] Migration `0004_r2_service_maintenance.py`: 17 bảng mới bao gồm:
  - `service_categories`, `service_requests`, `work_orders`, `work_order_checklist_items`, `cost_lines`, `pending_charges`, `charge_reversals`, `case_records`.
  - `assets`, `maintenance_plans`, `maintenance_occurrences`, `maintenance_history`.
  - `attachments`, `idempotency_records`, `domain_events`, `audit_events`.
- [x] Khóa ngoại ghép `(site_id, tenant_id)` và `(building_id, site_id)` cưỡng chế toàn vẹn cách ly dữ liệu ở cấp độ database.

#### 2. Backend API & Nghiệp vụ
- [x] `POST /api/v1/service-requests`: Tạo yêu cầu dịch vụ, tính hạn chót SLA tuyệt đối, idempotent.
- [x] `GET /api/v1/service-requests`: Danh sách yêu cầu phân trang, lọc status, cưỡng chế scope tòa cho CSKH và `assigned-only` cho KTV.
- [x] `GET /api/v1/service-requests/{id}`: Xem chi tiết yêu cầu đúng thẩm quyền.
- [x] `POST /api/v1/service-requests/{id}/triage`: Phân loại yêu cầu, chỉ định mức độ ưu tiên và người phụ trách.
- [x] `POST /api/v1/service-requests/{id}/work-orders`: Tạo Work Order kèm checklist công việc.
- [x] `POST /api/v1/work-orders/{id}/assign`: Trưởng kỹ thuật phân công KTV (`AccountRole.role == "technician"`).
- [x] `POST /api/v1/work-orders/{id}/start`: KTV bắt đầu xử lý công việc được giao.
- [x] `PATCH /api/v1/work-orders/{id}/checklist/{item_id}`: KTV tích hoàn thành từng mục checklist.
- [x] `POST /api/v1/work-orders/{id}/evidence`: Tải ảnh bằng chứng (PNG/JPEG magic bytes, $\le 10$ MB, lưu private storage).
- [x] `POST /api/v1/work-orders/{id}/cost-lines`: Thêm chi phí BQL/Cư dân kèm ảnh hóa đơn chứng từ.
- [x] `POST /api/v1/pending-charges/{id}/decision`: Kế toán duyệt/từ chối chi phí, cưỡng chế SoD (cấm người tạo tự duyệt).
- [x] `POST /api/v1/work-orders/{id}/submit`: KTV nộp báo cáo hoàn thành công việc.
- [x] `POST /api/v1/work-orders/{id}/accept`: Nghiệm thu kỹ thuật (Trưởng KT) hoặc Nghiệm thu ủy quyền (CSKH có lý do/ảnh). Cưỡng chế SoD `ERR-SOD-SELF-APPROVE`.
- [x] `POST /api/v1/work-orders/{id}/reopen` & `cancel`: Tự động sinh `ChargeReversal` và `CaseRecord` khi hủy WO đã duyệt chi phí.
- [x] `POST /api/v1/maintenance/scheduler/run`: Quét tài sản/kế hoạch đến hạn, sinh Work Order idempotent.
- [x] `POST /api/v1/maintenance-occurrences/{id}/defer`: Hoãn lịch bảo trì có lý do.

#### 3. Frontend UI & Tích hợp
- [x] [`SessionDashboard.jsx`](file:///C:/Users/LEGION/btl/_pttkpm/greencity-app/src/components/staff/SessionDashboard.jsx): Thẻ đo lường SLA, yêu cầu đang xử lý, chờ thông tin, cảnh báo quá hạn.
- [x] [`TasksDesktopView.jsx`](file:///C:/Users/LEGION/btl/_pttkpm/greencity-app/src/components/TasksDesktopView.jsx): Bảng danh sách CSKH kết nối API thật, lọc trạng thái, phân trang, hiển thị vị trí căn hộ/tòa nhà.
- [x] Xử lý trạng thái biên UI: Loading spinner, Empty states, lỗi 401 tự logout, lỗi Scope 404, lỗi Network retry, Correlation ID.
- [x] Modal xem nhanh chi tiết Service Request.
- [ ] Form CSKH tạo yêu cầu mới (`POST /service-requests`) từ UI.
- [ ] Form Trưởng KT phân công và KTV cập nhật checklist từ UI.

#### 4. Tiêu chí thoát & Kiểm chứng
- [x] `AC-06`: Service Request chỉ chuyển sang `RESOLVED` khi tất cả Work Order liên kết đều ở trạng thái kết thúc.
- [~] `AC-07`: *[SPEC-ONLY]* Pause/resume SLA nhiều lịch làm việc phức tạp.
- [x] `AC-08`: Work Order có chi phí BQL và Cư dân; chỉ dòng Cư dân sinh `PendingCharge`.
- [x] `AC-09`: KTV hoặc Kế toán tự duyệt khoản do mình tạo $\rightarrow$ Bị chặn `ERR-SOD-SELF-APPROVE`.
- [x] `AC-10`: Hủy/reopen Work Order sau khi chi phí đã duyệt $\rightarrow$ Tự động sinh reversal và case record.
- [x] `AC-38`: Scheduler bảo trì chạy 2 lần cho cùng kế hoạch $\rightarrow$ Chỉ sinh 1 lần (Idempotent).
- [x] `AC-39`: Nghiệm thu bảo trì ghi nhận lịch sử `MaintenanceHistory` và tính `next_due_at` chuẩn UTC.

---

### 🔹 R3: Vệ sinh & An ninh (Implemented & Verified Local)

#### 1. Database & Schema
- [x] Migration `0007_r3_operations.py`: 9 bảng nghiệp vụ vận hành:
  - Phân hệ Vệ sinh: `cleaning_shifts`, `cleaning_routes`, `cleaning_tasks`, `cleaning_checklists`.
  - Phân hệ An ninh: `security_shifts`, `shift_handover_logs`, `patrol_routes`, `patrol_logs`, `security_incidents`.
- [x] Ràng buộc toàn vẹn: Composite Foreign Keys `(site_id, tenant_id)`, `(building_id, site_id)`. Trigger database cưỡng chế append-only cho lịch sử tuần tra và bàn giao ca.

#### 2. Backend API & Nghiệp vụ
- [x] Phân hệ Vệ sinh (`CAP-ENV`):
  - [x] `GET/POST /api/v1/cleaning/tasks`: Quản lý nhiệm vụ vệ sinh theo ca/tuyến, lọc theo scope tòa/khu vực.
  - [x] `POST /api/v1/cleaning/tasks/{id}/checklist`: Ghi nhận kết quả đạt/không đạt.
  - [x] Tự động sinh Case/Work Order khi có điểm vệ sinh không đạt (`REWORK_REQUIRED`).
- [x] Phân hệ An ninh (`CAP-SEC`):
  - [x] `POST /api/v1/security/shifts/handover`: Bàn giao ca trực, kiểm đếm quân số/công cụ hỗ trợ.
  - [x] `POST /api/v1/security/patrols`: Ghi nhận nhật ký tuần tra theo mốc thời gian/khu vực.
  - [x] `POST /api/v1/security/incidents`: Ghi nhận sự cố an ninh/PCCC, phân cấp mức độ (Severity) và điều hướng xử lý (Escalation).

#### 3. Frontend UI & Tích hợp
- [x] Giao diện Ca/Tuyến vệ sinh cho nhân viên Vệ sinh (`CleaningDesktopView.jsx`).
- [x] Giao diện Sổ bàn giao ca, Tuần tra và Sự cố cho nhân viên An ninh (`SecurityDesktopView.jsx`).

#### 4. Tiêu chí thoát & Kiểm chứng
- [x] `AC-40`: Nhân viên vệ sinh thực hiện ca nhiều khu vực $\rightarrow$ Chỉ thấy nhiệm vụ được giao; mỗi điểm có checklist.
- [x] `AC-41`: Điểm vệ sinh đánh giá không đạt $\rightarrow$ Chuyển `REWORK_REQUIRED`, tự động sinh Case/WO liên kết.
- [x] `AC-42`: Lượt tuần tra an ninh bị bỏ qua cửa sổ thời gian $\rightarrow$ Không tự đánh dấu hoàn thành, yêu cầu giải trình.
- [x] `AC-43`: Ghi nhận sự cố an ninh/PCCC mức độ nghiêm trọng $\rightarrow$ Escalation đúng vai trò, có người tiếp nhận.

---

### 🔹 R4: Phí & Hóa đơn cơ bản (Implemented & Verified Local)

#### 1. Database & Schema
- [x] Migrations `0008_r4_billing_foundation.py`, `0009_r4_billing_issue.py`, `0010_r4_payment_reconciliation.py`:
  - `billing_accounts`, `billing_fee_policies`, `billing_fee_policy_versions`, `accounting_periods`, `billing_runs`, `billing_invoices`, `billing_invoice_items`.
  - `payments`, `payment_allocations`, `unmatched_payments`, `overpayment_credits`, `ar_ledger_entries`.
- [x] Ràng buộc bất biến: Tiền tệ kiểu số nguyên VND `BIGINT` (`ARC-07`), số dư nợ tính từ sổ cái bút toán (`ARC-08`), trigger `trg_ar_ledger_entries_append_only`, trigger `trg_payment_allocations_cap`, trigger `trg_billing_invoice_items_immutable`.

#### 2. Backend API & Nghiệp vụ
- [x] `POST /api/v1/billing/runs`: Chốt kỳ và tính toán phát hành Billing Run nguyên tử (`ALG-01`), retry cùng run key khi lỗi basis.
- [x] Chốt hóa đơn bất biến (Invoice Snapshot: diện tích `m²`, đơn giá VND, tổng tiền, items snapshot cấm sửa xóa).
- [x] `POST /api/v1/billing/payments`: Ghi nhận thanh toán thủ công (phiếu thu tiền mặt / chuyển khoản ủy nhiệm chi), chống nhận trùng `AC-30`.
- [x] Phân bổ thanh toán theo thuật toán `ALG-05` (ưu tiên nợ cũ trước `due_on ASC`, khóa biến động `with_for_update()`).
- [x] Xử lý khoản thanh toán chưa khớp (Unmatched Payment `AC-18`) và Tiền thừa cấn trừ tự động (Overpayment Credit `ALG-07`, `AC-19`).
- [x] `POST /api/v1/billing/invoices/{id}/void`: Ràng buộc void hóa đơn an toàn (`AC-16`: chỉ invoice `ISSUED`, chưa allocation, trong kỳ `OPEN`).
- [~] *[SPEC-ONLY]* Các tính năng nâng cao: Hoàn tiền (Refund Payout), Chargeback, Miễn giảm (Waiver), Quỹ bảo trì 2%, Đối soát VietQR tự động.

#### 3. Frontend UI & Tích hợp
- [x] Giao diện Kế toán (`BillingDesktopView.jsx`): Cấu hình biểu phí, mở kỳ kế toán, phát hành billing run, tra cứu hóa đơn snapshot, tiếp nhận payment thủ công, hàng đợi đối soát unmatched, phân bổ nợ và bảng overpayment credits.
- [x] Smoke UI Playwright e2e (`tests/billing-ux.cjs`, `tests/payment-ux.cjs`).

#### 4. Tiêu chí thoát & Kiểm chứng
- [x] `AC-11`: Tính phí cơ bản theo cơ sở tính $\times$ đơn giá và làm tròn $\rightarrow$ Khớp snapshot đến 0 VND sai lệch.
- [x] `AC-12`: Hai kế toán chốt cùng kỳ/site $\rightarrow$ Chỉ 1 run thắng, không trùng lặp hóa đơn.
- [x] `AC-13`: Billing Run lỗi rồi retry $\rightarrow$ Hoàn tất đúng tập invoice, báo cáo lỗi ban đầu.
- [x] `AC-14`: Charge duyệt sau ngày cutoff $\rightarrow$ Tự động chuyển sang kỳ sau, snapshot kỳ hiện tại bất biến.
- [x] `AC-16`: Void hóa đơn $\rightarrow$ Chỉ cho phép hóa đơn chưa allocation trong kỳ `OPEN`.
- [x] `AC-17`: Trả một phần hoặc gộp nhiều hóa đơn $\rightarrow$ Thứ tự phân bổ khớp thuật toán.
- [x] `AC-18`: Chuyển khoản thiếu mã căn $\rightarrow$ Đưa vào hàng chờ Unmatched, không giảm nợ trước khi khớp.
- [x] `AC-19`: Thanh toán thừa $\rightarrow$ Chỉ phần thừa ghi nhận vào Overpayment Credit.
- [x] `AC-30`: Ghi nhận thanh toán đồng thời cùng mã giao dịch $\rightarrow$ Idempotency chỉ cho phép 1 Payment thành công.
- [x] `AC-44`: Phát hành hóa đơn rồi ghi nhận thanh toán thủ công $\rightarrow$ Snapshot không đổi, số dư tái lập chính xác.

---

### 🔹 R5: Điều hành, Tích hợp 4 Golden Flows & Báo cáo (Chưa mở sprint)

#### 1. Backend & Dữ liệu
- [ ] Endpoint KPI Dashboard tổng hợp cho Ban Giám đốc (`director`):
  - Tỷ lệ hoàn thành SLA CSKH.
  - Tỷ lệ kế hoạch bảo trì kỹ thuật đúng hạn.
  - Điểm vệ sinh đạt chuẩn theo khu vực.
  - Tình hình an ninh, số vụ sự cố mở.
  - Tỷ lệ thu phí và tổng công nợ quá hạn.
- [ ] Báo cáo Drill-down: Bấm từ số liệu KPI xem chi tiết từng bản ghi gốc đúng quyền.

#### 2. Kịch bản tích hợp 4 Golden Flows (Khép kín không sửa DB tay)
- [ ] **Golden Flow 1 (CSKH & Kỹ thuật):** Cư dân phản ánh $\rightarrow$ CSKH tiếp nhận $\rightarrow$ Trưởng KT tạo WO $\rightarrow$ KTV thực hiện & upload ảnh $\rightarrow$ Trưởng KT nghiệm thu $\rightarrow$ CSKH đóng yêu cầu.
- [ ] **Golden Flow 2 (Bảo trì định kỳ):** Scheduler tự quét đến hạn $\rightarrow$ Sinh WO kiểm tra máy phát $\rightarrow$ KTV hoàn tất checklist $\rightarrow$ Tự cập nhật hạn bảo trì kỳ kế tiếp.
- [ ] **Golden Flow 3 (Vệ sinh & An ninh):** Nhân viên vệ sinh báo lỗi khu vực sảnh $\rightarrow$ Tự sinh Case $\rightarrow$ Đội an ninh phát hiện sự cố PCCC $\rightarrow$ Escalation và lập biên bản.
- [ ] **Golden Flow 4 (Phí & Thanh toán):** Chốt kỳ phí tháng $\rightarrow$ Sinh hóa đơn dịch vụ $\rightarrow$ Cư dân nộp tiền mặt tại quầy $\rightarrow$ Kế toán phát hành phiếu thu $\rightarrow$ Công nợ về 0.

#### 3. Tiêu chí thoát & Kiểm chứng
- [ ] `AC-22`: Kênh thông báo timeout $\rightarrow$ Giao dịch gốc vẫn commit, Outbox retry hiển thị trạng thái đúng.
- [ ] `AC-25`: Dashboard công nợ và SLA tại một mốc `as_of` $\rightarrow$ Khớp 100% dữ liệu chi tiết nguồn.
- [ ] `AC-36`: Cắt kết nối mạng lúc lưu rồi thử lại $\rightarrow$ Idempotency key bảo vệ không trùng lặp bản ghi.
- [ ] `AC-45`: Bốn Golden Flow chạy liên hoàn không lỗi, không can thiệp thủ công vào cơ sở dữ liệu.

---

### 🔹 Hardening, Kiểm thử Hồi quy & Chuẩn bị Bảo vệ (Đang thực hiện)

- [x] **Hạ tầng kiểm thử:**
  - [x] Chạy tự động trọn gói kiểm thử trên PostgreSQL 18 cô lập.
  - [x] Kiểm tra di chuyển schema lặp (head `0006`; có path `0005 -> 0006 -> 0005`).
  - [x] Kiểm tra nạp dữ liệu mẫu lặp (Seed repeat test idempotent).
  - [x] Kiểm tra không có Schema Drift (`alembic check` Pass).
  - [x] Bộ test Frontend tự động với Node.js (`npm test`: 51 tests pass; smoke staff: 30 checks pass; Vite build pass).
- [ ] **Tài liệu đồ án môn học:**
  - [ ] Báo cáo Kiến trúc & Thiết kế phần mềm (SAD/SDD).
  - [ ] Báo cáo Kế hoạch & Kết quả kiểm thử (Test Plan & Report).
  - [ ] Slide thuyết trình bảo vệ đồ án kèm video kịch bản demo 4 Golden Flows.
- [ ] **Diễn tập bảo vệ (Defense Dry-run):**
  - [ ] Diễn tập kịch bản demo trên môi trường sạch, đo thời gian trình bày.
  - [ ] Chuẩn bị bộ câu hỏi phản biện về SoD, Multi-tenant Data Scope, và Bất biến tài chính.

---

## 🛠️ 4. Quy ước duy trì & Cập nhật Checklist

1. **Khi hoàn thành một mục:**
   - Đổi `[ ]` thành `[x]`.
   - Nếu đang làm dở dang hoặc đang kiểm thử, dùng `[-]`.
   - Nếu là tính năng phức tạp thuộc tầm nhìn xa được hoãn lại theo Roadmap, dùng `[~]` (*SPEC-ONLY*).
2. **Khi thêm migration mới:**
   - Bổ sung tên file migration vào danh sách tương ứng.
   - Cập nhật số bảng và phiên bản revision mong đợi trong phần tổng quan.
3. **Khi bổ sung test case:**
   - Cập nhật số lượng bài test trong Bảng điều khiển (Mục 1) sau khi chạy lệnh runner kiểm chứng thực tế.
4. **Cập nhật "Tiêu điểm Sprint hiện tại" (Mục 2):**
   - Giữ từ 3 - 5 đầu việc trọng tâm của tuần/sprint hiện tại để định hướng rõ ràng cho phiên làm việc tiếp theo.
