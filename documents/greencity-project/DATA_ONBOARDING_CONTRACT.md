# DATA ONBOARDING CONTRACT — GreenCity

> Contract FCS-03 cho 12 workbook dữ liệu thật dùng trong phạm vi local onboarding.
> Tài liệu này là hợp đồng schema và preflight; không tự ghi dữ liệu nghiệp vụ vào database.

## 1. Trạng thái và phạm vi

| Trường | Giá trị |
|---|---|
| Contract version | `fcs05-r3` (schema contract FCS-03, resolved mapping và incident enum) |
| Machine contract status | `LOCAL_PREFLIGHT_PASS_AND_DB_COUNT_RECORDED` |
| Trạng thái thực thi FCS-03 | DONE — 12 schema, disposition và tài liệu được kiểm cùng `WORKBOOK_CONTRACTS` |
| Machine-readable source | [backend/app/services/submission_data_contract.py](../../backend/app/services/submission_data_contract.py) |
| Source of truth | documents/greencity-project/excel-data |
| Phân loại | RESTRICTED_REAL_LOCAL_ONLY |
| Data sheet | `Dữ liệu` |
| Guide sheet | `Hướng dẫn` |
| Dòng dữ liệu theo manifest | 101 trên 12 workbook |
| Timezone đã duyệt | Asia/Ho_Chi_Minh → lưu timestamp ở UTC |
| Contract fingerprint | `4d749f7377335c49a6b3159e0d1e12bfb5480cd95f158bca2fe7f52a5ce16147` |

User/Owner đã phê duyệt FCS-01 ngày 2026-09-27; `open_decisions=0` trong contract.
Tại cutoff `2026-10-01T16:59:59Z`, raw source preflight PASS với 0
`FUTURE_TERMINAL_EVENT`; 36 `FUTURE_SCHEDULE` warning là lịch dự kiến không chặn.
Không đưa raw cell value, PII, credential, PIN hoặc checksum đầy đủ vào tài liệu này.

### Đối chiếu database cục bộ — Task 1

Truy vấn `READ ONLY` ngày 2026-10-01 trên `green_city` ghi nhận 61 base table
(không tính `alembic_version`), 38 table có dữ liệu và 272 bản ghi tổng cộng.
Đây là metadata aggregate không chứa PII; không chứng minh nguồn của từng bản
ghi, không thay thế apply/verify trên database sạch và không là Final Submission
Gate.

## 2. Quy ước chung

- Mỗi workbook phải có đúng hai sheet: Dữ liệu và Hướng dẫn; header của Dữ liệu phải đúng thứ tự source_name bên dưới.
- Mỗi cột có đúng một disposition: Persist, Derive, Validate hoặc Ignore-with-reason.
- Persist ghi qua service/domain command sau khi scope và constraint pass; Derive chỉ resolve từ khóa định danh đã khóa; Validate là oracle/metadata không được ghi như nguồn sự thật; Ignore-with-reason phải có lý do bắt đầu bằng IGNORE:.
- Không join bằng tên người, email, số điện thoại hoặc số tiền. Dùng external key và natural key trong contract; match nhiều kết quả hoặc không có kết quả đều tạo lỗi preflight.
- Text giữ dạng string; mã và số căn hộ giữ leading zero; integer phải parse được; tiền, diện tích và quantity dùng Decimal; VND phải non-negative và được quantize ở service boundary.
- Datetime nguồn là local time theo timezone site được duyệt, chuyển sang UTC khi lưu. Datetime tương lai phải được phân loại trước replay và không được tạo terminal event đã xảy ra.
- Enum được normalize theo rule của từng field và phải nằm trong enum khai báo; trạng thái terminal chỉ được tạo qua state-machine command.
- Raw staff contact và free-text notes không được xuất vào evidence; PIN bưu phẩm không bao giờ nhập hoặc log dưới dạng plaintext.

## 3. Tóm tắt 12 workbook

Bảng tóm tắt và ma trận bên dưới được sinh từ `WORKBOOK_CONTRACTS` bằng `python -m scripts.render_submission_contract --write`. Dùng `--check` để phát hiện tài liệu lệch contract trước khi đóng gói.

| Workbook | Version | Sheet | Dòng | Natural key | Target entities | Canonical input còn thiếu |
|---|---|---|---:|---|---|---|
| `01_cong_viec.xlsx` | `fcs05-r3` | `Dữ liệu` + `Hướng dẫn` | 9 | `work_code` | `ServiceRequest`, `WorkOrder`, `CostLine` | — |
| `02_danh_sach_nhan_vien.xlsx` | `fcs05-r3` | `Dữ liệu` + `Hướng dẫn` | 18 | `employee_code` | `Account`, `AccountRole`, `ImportExternalReference` | — |
| `03_toa_nha_can_ho.xlsx` | `fcs05-r3` | `Dữ liệu` + `Hướng dẫn` | 12 | `site_code`, `building_code`, `unit_number` | `Tenant`, `Site`, `Building`, `Unit`, `BillingAccount` | — |
| `04_cu_dan.xlsx` | `fcs05-r3` | `Dữ liệu` + `Hướng dẫn` | 11 | `resident_code`, `unit_number`, `relationship_type` | `Person`, `UnitPersonRelationship`, `ImportExternalReference` | — |
| `05_tai_san_bao_tri.xlsx` | `fcs05-r3` | `Dữ liệu` + `Hướng dẫn` | 6 | `site_code`, `asset_code` | `Asset`, `MaintenancePlan`, `ImportExternalReference` | — |
| `06_ve_sinh.xlsx` | `fcs05-r3` | `Dữ liệu` + `Hướng dẫn` | 6 | `site_code`, `shift_code` | `CleaningRoute`, `CleaningArea`, `CleaningShift`, `CleaningTask`, `CleaningChecklistResult` | — |
| `07_an_ninh_tuan_tra.xlsx` | `fcs05-r3` | `Dữ liệu` + `Hướng dẫn` | 6 | `building_code`, `shift_code`, `patrol_point_code`, `window_start` | `SecurityShift`, `PatrolPoint`, `PatrolWindow`, `PatrolLog`, `SecurityShiftHandoff` | — |
| `08_su_co_an_ninh.xlsx` | `fcs05-r3` | `Dữ liệu` + `Hướng dẫn` | 6 | `site_code`, `incident_code` | `SecurityIncident`, `IncidentEscalation`, `SecurityIncidentEvidence` | — |
| `09_chinh_sach_phi.xlsx` | `fcs05-r3` | `Dữ liệu` + `Hướng dẫn` | 5 | `building_code`, `fee_policy_code`, `version_number` | `FeePolicy`, `FeePolicyVersion`, `AccountingPeriod` | — |
| `10_hoa_don.xlsx` | `fcs05-r3` | `Dữ liệu` + `Hướng dẫn` | 8 | `site_code`, `invoice_number`, `line_code` | `BillingRun`, `BillingInvoice`, `BillingInvoiceItem` | `fee_policy_code` |
| `11_thanh_toan.xlsx` | `fcs05-r3` | `Dữ liệu` + `Hướng dẫn` | 8 | `site_code`, `source_reference`, `receipt_number` | `Payment`, `PaymentAllocation`, `UnmatchedPayment`, `OverpaymentCredit` | `period_key` |
| `12_buu_pham.xlsx` | `fcs05-r3` | `Dữ liệu` + `Hướng dẫn` | 6 | `site_code`, `parcel_code` | `Parcel`, `CaseRecord`, `ImportExternalReference` | — |

## 4. Field-level schema matrix

Header là tên cột và thứ tự canonical. Required là bắt buộc ở preflight; Reference là khóa resolve/oracle; Decision liên kết quyết định FCS-01/FCS-04/FCS-05.

### `01_cong_viec.xlsx`

- Schema version: `fcs05-r3`
- Sheets: `Dữ liệu` (data), `Hướng dẫn` (guidance)
- Expected data rows: `9`
- Natural key: `work_code`
- Target entities: `ServiceRequest`, `WorkOrder`, `CostLine`
- Canonical inputs missing: —
- Canonical header order: `work_code`, `request_type`, `title`, `description`, `priority`, `status`, `tenant_code`, `site_code`, `building_code`, `unit_number`, `reported_by_username`, `assignee_username`, `created_at`, `sla_due_at`, `completed_at`, `cost_vnd`, `notes`

| Header | Type | Required | Disposition | Target | Reference | Rule | Decision |
|---|---|---|---|---|---|---|---|
| `work_code` | `string` | yes | `Persist` | ServiceRequest.code | site_code + work_code | Preserve the source code; reject blank or duplicate code. | `—` |
| `request_type` | `string` | yes | `Validate` | ServiceCategory.code | site_code + request_type | Normalize for comparison; resolve category and SLA before apply. | `FCS-05:CATEGORY_SLA` |
| `title` | `string` | yes | `Persist` | ServiceRequest.title | — | Trim and enforce the target length. | `—` |
| `description` | `string` | yes | `Persist` | ServiceRequest.description | — | Trim; retain only in the local approved scope. | `—` |
| `priority` | `string` | yes | `Validate` | ServiceRequest.priority | — | Normalize to uppercase and validate the service priority enum. Enum: LOW, MEDIUM, HIGH, URGENT. | `—` |
| `status` | `string` | yes | `Validate` | ServiceRequest/WorkOrder.status | — | Map through state-machine commands; never write a terminal state directly. Enum: NEW, TRIAGED, IN_PROGRESS, WAITING_INFO, RESOLVED, CLOSED, CANCELLED, DRAFT, ASSIGNED, IN_PROGRESS, ON_HOLD, WAITING_ACCEPTANCE, COMPLETED, CLOSED, CANCELLED. | `—` |
| `tenant_code` | `string` | yes | `Derive` | tenant_id | Tenant.code | Resolve exactly one tenant; fail on zero or multiple matches. | `—` |
| `site_code` | `string` | yes | `Derive` | site_id | Site.tenant_id + Site.code | Resolve within the tenant scope. | `—` |
| `building_code` | `string` | yes | `Derive` | building_id | Building.site_id + Building.code | Resolve within the site scope. | `—` |
| `unit_number` | `string` | no | `Derive` | unit_id | Unit.building_id + Unit.unit_number | Blank means a building-scoped request; otherwise resolve one unit. | `—` |
| `reported_by_username` | `string` | yes | `Derive` | created_by_id | Account.tenant_id + Account.username | Resolve an existing account; do not join by full name. | `—` |
| `assignee_username` | `string` | yes | `Derive` | owner_account_id/assigned_to_id | Account.tenant_id + Account.username | Resolve an existing in-scope account. | `—` |
| `created_at` | `datetime` | yes | `Derive` | ServiceRequest.sla_started_at | — | Interpret in the approved site timezone, convert to UTC, and reject an invalid timestamp. | `FCS-01:TIMEZONE` |
| `sla_due_at` | `datetime` | yes | `Validate` | ServiceRequest SLA oracle | — | Recompute from category SLA and compare; do not persist as an independent authority. | `FCS-05:CATEGORY_SLA` |
| `completed_at` | `datetime` | no | `Derive` | WorkOrder.completed_at | — | Use only through a legal state transition; future timestamps cannot close work. | `—` |
| `cost_vnd` | `decimal` | yes | `Persist` | CostLine.amount_vnd | — | Parse Decimal, quantize to VND, and require the approved cost bearer before apply. | `FCS-05:COST_BEARER` |
| `notes` | `string` | no | `Ignore-with-reason` | — | — | IGNORE: free text is not imported or emitted in evidence; retain only row/error counts. | `—` |

### `02_danh_sach_nhan_vien.xlsx`

- Schema version: `fcs05-r3`
- Sheets: `Dữ liệu` (data), `Hướng dẫn` (guidance)
- Expected data rows: `18`
- Natural key: `employee_code`
- Target entities: `Account`, `AccountRole`, `ImportExternalReference`
- Canonical inputs missing: —
- Canonical header order: `employee_code`, `full_name`, `username`, `email`, `phone`, `role`, `department`, `tenant_code`, `site_code`, `building_code`, `status`, `start_date`, `notes`

| Header | Type | Required | Disposition | Target | Reference | Rule | Decision |
|---|---|---|---|---|---|---|---|
| `employee_code` | `string` | yes | `Persist` | ImportExternalReference.source_key | source=employee; entity=Account | Use as the non-PII external key; reject duplicates. | `—` |
| `full_name` | `string` | yes | `Persist` | Account.full_name | — | Trim and enforce the target length. | `—` |
| `username` | `string` | yes | `Persist` | Account.username | Account.tenant_id + Account.username | Use as the account natural lookup; reject duplicate usernames in a tenant. | `—` |
| `email` | `string` | yes | `Ignore-with-reason` | — | — | IGNORE: raw staff contact is not stored by the current account model or emitted in approved evidence. | `—` |
| `phone` | `string` | yes | `Ignore-with-reason` | — | — | IGNORE: raw staff contact is not stored by the current account model or emitted in approved evidence. | `—` |
| `role` | `string` | yes | `Persist` | AccountRole.role | AccountRole.account_id + scope | Normalize to lowercase and validate the backend role enum. Enum: admin, director, cskh, accountant, technical_lead, technician, cleaning, security, resident. | `—` |
| `department` | `string` | yes | `Ignore-with-reason` | — | — | IGNORE: no department field exists in the current account model; preserve as a contract validation field. | `—` |
| `tenant_code` | `string` | yes | `Derive` | tenant_id | Tenant.code | Resolve exactly one tenant. | `—` |
| `site_code` | `string` | no | `Derive` | site_id | Site.tenant_id + Site.code | Resolve when supplied; a tenant-level staff row may omit site. | `—` |
| `building_code` | `string` | no | `Derive` | building_id | Building.site_id + Building.code | Resolve when supplied; a site-level staff row may omit building. | `—` |
| `status` | `string` | yes | `Persist` | Account.is_active | — | Normalize the source status to a boolean active flag; reject unknown values. | `—` |
| `start_date` | `date` | yes | `Validate` | Account employment oracle | — | Validate an ISO date; no employment-date column exists in the current model. | `—` |
| `notes` | `string` | no | `Ignore-with-reason` | — | — | IGNORE: free text is not imported or emitted in evidence. | `—` |

### `03_toa_nha_can_ho.xlsx`

- Schema version: `fcs05-r3`
- Sheets: `Dữ liệu` (data), `Hướng dẫn` (guidance)
- Expected data rows: `12`
- Natural key: `site_code`, `building_code`, `unit_number`
- Target entities: `Tenant`, `Site`, `Building`, `Unit`, `BillingAccount`
- Canonical inputs missing: —
- Canonical header order: `tenant_code`, `site_code`, `site_name`, `building_code`, `building_name`, `floors_count`, `unit_number`, `floor`, `area_m2`, `unit_status`, `billing_account_number`, `billing_status`, `resident_code`

| Header | Type | Required | Disposition | Target | Reference | Rule | Decision |
|---|---|---|---|---|---|---|---|
| `tenant_code` | `string` | yes | `Derive` | tenant_id | Tenant.code | Resolve exactly one tenant. | `—` |
| `site_code` | `string` | yes | `Persist` | Site.code | Site.tenant_id + Site.code | Create or match only the explicitly approved site; reject conflict. | `—` |
| `site_name` | `string` | yes | `Persist` | Site.name | Site.tenant_id + Site.code | Use the source name only after site-code identity matches. | `—` |
| `building_code` | `string` | yes | `Persist` | Building.code | Building.site_id + Building.code | Create or match within the resolved site. | `—` |
| `building_name` | `string` | yes | `Persist` | Building.name | Building.site_id + Building.code | Update only on an explicit conflict policy; otherwise reject mismatch. | `—` |
| `floors_count` | `integer` | yes | `Persist` | Building.floors_count | — | Require a positive integer. | `—` |
| `unit_number` | `string` | yes | `Persist` | Unit.unit_number | Unit.building_id + Unit.unit_number | Preserve as text, including leading zeroes. | `—` |
| `floor` | `integer` | yes | `Persist` | Unit.floor | — | Require an integer within the building floor range. | `—` |
| `area_m2` | `decimal` | yes | `Persist` | Unit.area_m2 | — | Parse Decimal and apply the approved quantization before the current Float column is written. | `FCS-04:AREA_PRECISION` |
| `unit_status` | `string` | yes | `Persist` | Unit.status | — | Normalize to lowercase and validate the unit status enum. Enum: occupied, vacant, reserved. | `—` |
| `billing_account_number` | `string` | yes | `Persist` | BillingAccount.account_number | BillingAccount.site_id + BillingAccount.account_number | Read as text to preserve identity and resolve exactly one unit account. | `—` |
| `billing_status` | `string` | yes | `Persist` | BillingAccount.status | — | Normalize/validate the billing account status enum. Enum: ACTIVE, SUSPENDED, CLOSED. | `—` |
| `resident_code` | `string` | no | `Derive` | UnitPersonRelationship.person_id | ImportExternalReference.source_key=resident_code | Resolve the resident mapping only when supplied; do not join by name. | `—` |

### `04_cu_dan.xlsx`

- Schema version: `fcs05-r3`
- Sheets: `Dữ liệu` (data), `Hướng dẫn` (guidance)
- Expected data rows: `11`
- Natural key: `resident_code`, `unit_number`, `relationship_type`
- Target entities: `Person`, `UnitPersonRelationship`, `ImportExternalReference`
- Canonical inputs missing: —
- Canonical header order: `resident_code`, `full_name`, `phone_masked`, `email_masked`, `relationship_type`, `ownership_ratio`, `tenant_code`, `site_code`, `building_code`, `unit_number`, `valid_from`, `valid_to`, `status`

| Header | Type | Required | Disposition | Target | Reference | Rule | Decision |
|---|---|---|---|---|---|---|---|
| `resident_code` | `string` | yes | `Persist` | ImportExternalReference.source_key | source=resident; entity=Person | Use as a non-PII external key; reject duplicate source identity. | `—` |
| `full_name` | `string` | yes | `Persist` | Person.full_name | — | Trim and enforce the target length. | `—` |
| `phone_masked` | `string` | yes | `Persist` | Person.phone_masked | — | Accept only the masked representation; reject an unmasked pack. | `—` |
| `email_masked` | `string` | yes | `Persist` | Person.email_masked | — | Accept only the masked representation; reject an unmasked pack. | `—` |
| `relationship_type` | `string` | yes | `Persist` | UnitPersonRelationship.relationship_type | — | Normalize to lowercase and validate the relationship enum. Enum: owner, tenant, family_member. | `—` |
| `ownership_ratio` | `decimal` | yes | `Persist` | UnitPersonRelationship.ownership_ratio | — | Parse Decimal; canonicalize zero for non-owner rows to NULL. | `FCS-04:OWNERSHIP_ZERO` |
| `tenant_code` | `string` | yes | `Derive` | tenant_id | Tenant.code | Resolve exactly one tenant. | `—` |
| `site_code` | `string` | yes | `Derive` | site_id | Site.tenant_id + Site.code | Resolve within the tenant. | `—` |
| `building_code` | `string` | yes | `Derive` | building_id | Building.site_id + Building.code | Resolve within the site. | `—` |
| `unit_number` | `string` | yes | `Derive` | unit_id | Unit.building_id + Unit.unit_number | Resolve exactly one unit. | `—` |
| `valid_from` | `date` | yes | `Persist` | UnitPersonRelationship.valid_from | — | Require an ISO date. | `—` |
| `valid_to` | `date` | no | `Persist` | UnitPersonRelationship.valid_to | — | Optional ISO date; must not precede valid_from. | `—` |
| `status` | `string` | yes | `Validate` | relationship validity oracle | — | Validate active/inactive semantics against the valid date range. | `—` |

### `05_tai_san_bao_tri.xlsx`

- Schema version: `fcs05-r3`
- Sheets: `Dữ liệu` (data), `Hướng dẫn` (guidance)
- Expected data rows: `6`
- Natural key: `site_code`, `asset_code`
- Target entities: `Asset`, `MaintenancePlan`, `ImportExternalReference`
- Canonical inputs missing: —
- Canonical header order: `asset_code`, `asset_name`, `asset_type`, `tenant_code`, `site_code`, `building_code`, `location`, `status`, `installed_on`, `maintenance_plan_code`, `interval_days`, `next_due_date`, `vendor_name`, `responsible_username`, `notes`

| Header | Type | Required | Disposition | Target | Reference | Rule | Decision |
|---|---|---|---|---|---|---|---|
| `asset_code` | `string` | yes | `Persist` | Asset.code | Asset.site_id + Asset.code | Reject blank or duplicate asset code. | `—` |
| `asset_name` | `string` | yes | `Persist` | Asset.name | — | Trim and enforce the target length. | `—` |
| `asset_type` | `string` | yes | `Validate` | Asset type metadata | — | Validate against the approved maintenance category mapping; do not silently drop it. | `FCS-05:MAINTENANCE_CATEGORY` |
| `tenant_code` | `string` | yes | `Derive` | tenant_id | Tenant.code | Resolve exactly one tenant. | `—` |
| `site_code` | `string` | yes | `Derive` | site_id | Site.tenant_id + Site.code | Resolve within the tenant. | `—` |
| `building_code` | `string` | yes | `Derive` | building_id | Building.site_id + Building.code | Resolve within the site. | `—` |
| `location` | `string` | yes | `Validate` | Asset location metadata | — | Validate against the approved location mapping; no implicit free-text join. | `FCS-05:MAINTENANCE_LOCATION` |
| `status` | `string` | yes | `Persist` | Asset.status | — | Normalize/validate ACTIVE, INACTIVE or RETIRED. Enum: ACTIVE, INACTIVE, RETIRED. | `—` |
| `installed_on` | `date` | yes | `Validate` | Asset installation-date oracle | — | Validate an ISO date; current Asset has no installation-date column. | `—` |
| `maintenance_plan_code` | `string` | yes | `Persist` | MaintenancePlan.code | MaintenancePlan.asset_id + MaintenancePlan.code | Resolve repeated codes only after the duplicate-plan decision is recorded. | `FCS-05:MAINTENANCE_PLAN_CODE` |
| `interval_days` | `integer` | yes | `Persist` | MaintenancePlan.interval_days | — | Require 1..3650 days. | `—` |
| `next_due_date` | `date` | yes | `Derive` | MaintenancePlan.next_due_at | — | Attach approved site timezone, store UTC, and derive from the plan schedule. | `—` |
| `vendor_name` | `string` | yes | `Validate` | Maintenance vendor metadata | — | Keep as a validation field until a target representation is approved. | `FCS-05:MAINTENANCE_VENDOR` |
| `responsible_username` | `string` | yes | `Validate` | Maintenance responsibility metadata | Account.tenant_id + Account.username | Resolve the account but do not invent an owner column in MaintenancePlan. | `FCS-05:MAINTENANCE_OWNER` |
| `notes` | `string` | no | `Ignore-with-reason` | — | — | IGNORE: free text is not imported or emitted in evidence. | `—` |

### `06_ve_sinh.xlsx`

- Schema version: `fcs05-r3`
- Sheets: `Dữ liệu` (data), `Hướng dẫn` (guidance)
- Expected data rows: `6`
- Natural key: `site_code`, `shift_code`
- Target entities: `CleaningRoute`, `CleaningArea`, `CleaningShift`, `CleaningTask`, `CleaningChecklistResult`
- Canonical inputs missing: —
- Canonical header order: `shift_code`, `route_code`, `area_code`, `site_code`, `building_code`, `scheduled_start`, `scheduled_end`, `assignee_username`, `status`, `checklist_floor`, `checklist_bins`, `quality_result`, `rework_required`, `notes`

| Header | Type | Required | Disposition | Target | Reference | Rule | Decision |
|---|---|---|---|---|---|---|---|
| `shift_code` | `string` | yes | `Persist` | ImportExternalReference.source_key | source=cleaning; entity=CleaningShift | Use as the non-PII shift key; reject duplicate shift identity. | `—` |
| `route_code` | `string` | yes | `Persist` | CleaningRoute.code | CleaningRoute.site_id + CleaningRoute.code | Resolve exactly one route. | `—` |
| `area_code` | `string` | yes | `Persist` | CleaningArea.code | CleaningArea.site_id + CleaningArea.code | Resolve exactly one area. | `—` |
| `site_code` | `string` | yes | `Derive` | site_id | Site.code | Resolve within the tenant. | `—` |
| `building_code` | `string` | yes | `Derive` | building_id | Building.site_id + Building.code | Resolve within the site. | `—` |
| `scheduled_start` | `datetime` | yes | `Persist` | CleaningShift.scheduled_start_at | — | Attach the approved site timezone and store UTC. | `FCS-01:TIMEZONE` |
| `scheduled_end` | `datetime` | yes | `Persist` | CleaningShift.scheduled_end_at | — | Require end after start; attach site timezone and store UTC. | `FCS-01:TIMEZONE` |
| `assignee_username` | `string` | yes | `Derive` | CleaningTask.assigned_to_id | Account.tenant_id + Account.username | Resolve an in-scope cleaning account. | `—` |
| `status` | `string` | yes | `Persist` | CleaningShift.status | — | Normalize/validate the cleaning state machine. Enum: PLANNED, IN_PROGRESS, COMPLETED, CANCELLED. | `—` |
| `checklist_floor` | `string` | yes | `Derive` | CleaningChecklistResult.result | — | Normalize the floor checklist result. Enum: PENDING, PASS, FAIL, NOT_APPLICABLE, REWORK. | `FCS-05:CLEANING_MASTER` |
| `checklist_bins` | `string` | yes | `Derive` | CleaningChecklistResult.result | — | Normalize the bin checklist result. Enum: PENDING, PASS, FAIL, NOT_APPLICABLE, REWORK. | `FCS-05:CLEANING_MASTER` |
| `quality_result` | `string` | yes | `Derive` | CleaningChecklistResult.result | — | Normalize and apply PASS/FAIL/rework state transitions. Enum: PENDING, PASS, FAIL, NOT_APPLICABLE, REWORK. | `FCS-05:CLEANING_MASTER` |
| `rework_required` | `boolean` | yes | `Derive` | CleaningTask.status | — | Translate true to FAIL -> REWORK_REQUIRED while retaining prior history. | `—` |
| `notes` | `string` | no | `Ignore-with-reason` | — | — | IGNORE: free text is not imported or emitted in evidence. | `—` |

### `07_an_ninh_tuan_tra.xlsx`

- Schema version: `fcs05-r3`
- Sheets: `Dữ liệu` (data), `Hướng dẫn` (guidance)
- Expected data rows: `6`
- Natural key: `building_code`, `shift_code`, `patrol_point_code`, `window_start`
- Target entities: `SecurityShift`, `PatrolPoint`, `PatrolWindow`, `PatrolLog`, `SecurityShiftHandoff`
- Canonical inputs missing: —
- Canonical header order: `shift_code`, `site_code`, `building_code`, `guard_username`, `scheduled_start`, `scheduled_end`, `patrol_point_code`, `window_start`, `window_end`, `patrol_status`, `event_type`, `incident_code`, `handoff_summary`, `notes`

| Header | Type | Required | Disposition | Target | Reference | Rule | Decision |
|---|---|---|---|---|---|---|---|
| `shift_code` | `string` | yes | `Persist` | ImportExternalReference.source_key | source=security; entity=SecurityShift | Use as the non-PII shift key. | `—` |
| `site_code` | `string` | yes | `Derive` | site_id | Site.code | Resolve within the tenant. | `—` |
| `building_code` | `string` | yes | `Derive` | building_id | Building.site_id + Building.code | Resolve within the site. | `—` |
| `guard_username` | `string` | yes | `Derive` | SecurityShift.assigned_to_id | Account.tenant_id + Account.username | Resolve an in-scope security account. | `—` |
| `scheduled_start` | `datetime` | yes | `Persist` | SecurityShift.scheduled_start_at | — | Attach the approved site timezone and store UTC. | `FCS-01:TIMEZONE` |
| `scheduled_end` | `datetime` | yes | `Persist` | SecurityShift.scheduled_end_at | — | Require end after start; attach site timezone and store UTC. | `FCS-01:TIMEZONE` |
| `patrol_point_code` | `string` | yes | `Persist` | PatrolPoint.code | PatrolPoint.building_id + PatrolPoint.code | Resolve exactly one patrol point. | `—` |
| `window_start` | `datetime` | yes | `Persist` | PatrolWindow.window_start_at | — | Attach site timezone and store UTC. | `FCS-01:TIMEZONE` |
| `window_end` | `datetime` | yes | `Persist` | PatrolWindow.window_end_at | — | Require end after start; attach site timezone and store UTC. | `FCS-01:TIMEZONE` |
| `patrol_status` | `string` | yes | `Persist` | PatrolWindow.status | — | Normalize/validate scheduled, completed, missed or cancelled. Enum: SCHEDULED, COMPLETED, MISSED, CANCELLED. | `—` |
| `event_type` | `string` | no | `Persist` | PatrolLog.event_type | — | Validate against the approved patrol event mapping when a patrol event exists. | `—` |
| `incident_code` | `string` | no | `Derive` | SecurityIncident.code | site_code + incident_code | Resolve only when supplied; never create an incident from a blank code. | `—` |
| `handoff_summary` | `string` | no | `Persist` | SecurityShiftHandoff.summary | — | Persist through a handoff command only when the source contains a handoff summary. | `FCS-05:PATROL_HANDOFF` |
| `notes` | `string` | no | `Ignore-with-reason` | — | — | IGNORE: free text is not imported or emitted in evidence. | `—` |

### `08_su_co_an_ninh.xlsx`

- Schema version: `fcs05-r3`
- Sheets: `Dữ liệu` (data), `Hướng dẫn` (guidance)
- Expected data rows: `6`
- Natural key: `site_code`, `incident_code`
- Target entities: `SecurityIncident`, `IncidentEscalation`, `SecurityIncidentEvidence`
- Canonical inputs missing: —
- Canonical header order: `incident_code`, `incident_type`, `severity`, `status`, `tenant_code`, `site_code`, `building_code`, `location`, `reported_at`, `reported_by_username`, `owner_username`, `resolved_at`, `description`, `notes`

| Header | Type | Required | Disposition | Target | Reference | Rule | Decision |
|---|---|---|---|---|---|---|---|
| `incident_code` | `string` | yes | `Persist` | SecurityIncident.code | SecurityIncident.site_id + SecurityIncident.code | Reject blank or duplicate incident code. | `—` |
| `incident_type` | `string` | yes | `Persist` | SecurityIncident.incident_type | — | Require the domain incident type enum before apply. Enum: SECURITY, FIRE. | `FCS-05:INCIDENT_TYPE` |
| `severity` | `string` | yes | `Persist` | SecurityIncident.severity | — | Normalize/validate the severity enum. Enum: LOW, MEDIUM, HIGH, CRITICAL. | `—` |
| `status` | `string` | yes | `Persist` | SecurityIncident.status | — | Apply only legal incident transitions; high severity requires closure checks. Enum: NEW, TRIAGED, IN_PROGRESS, RESOLVED, CLOSED. | `—` |
| `tenant_code` | `string` | yes | `Derive` | tenant_id | Tenant.code | Resolve exactly one tenant. | `—` |
| `site_code` | `string` | yes | `Derive` | site_id | Site.tenant_id + Site.code | Resolve within the tenant. | `—` |
| `building_code` | `string` | yes | `Derive` | building_id | Building.site_id + Building.code | Resolve within the site. | `—` |
| `location` | `string` | yes | `Persist` | SecurityIncident.title/location metadata | — | Keep a structured location only after the incident mapping decision. | `FCS-05:INCIDENT_LOCATION` |
| `reported_at` | `datetime` | yes | `Persist` | SecurityIncident.occurred_at | — | Attach approved site timezone and store UTC. | `FCS-01:TIMEZONE` |
| `reported_by_username` | `string` | yes | `Derive` | SecurityIncident.reported_by_id | Account.tenant_id + Account.username | Resolve an in-scope account. | `—` |
| `owner_username` | `string` | no | `Derive` | Incident owner/assignee | Account.tenant_id + Account.username | Resolve when supplied; a NEW incident may have no owner yet. | `FCS-05:INCIDENT_OWNER` |
| `resolved_at` | `datetime` | no | `Derive` | SecurityIncident.resolved_at | — | Use only through a legal transition; future timestamps cannot resolve an incident. | `FCS-04:FUTURE_TIME` |
| `description` | `string` | yes | `Persist` | SecurityIncident.description | — | Trim and enforce the target length. | `—` |
| `notes` | `string` | no | `Ignore-with-reason` | — | — | IGNORE: free text is not imported or emitted in evidence. | `—` |

### `09_chinh_sach_phi.xlsx`

- Schema version: `fcs05-r3`
- Sheets: `Dữ liệu` (data), `Hướng dẫn` (guidance)
- Expected data rows: `5`
- Natural key: `building_code`, `fee_policy_code`, `version_number`
- Target entities: `FeePolicy`, `FeePolicyVersion`, `AccountingPeriod`
- Canonical inputs missing: —
- Canonical header order: `fee_policy_code`, `fee_policy_name`, `tenant_code`, `site_code`, `building_code`, `version_number`, `effective_from`, `effective_to`, `unit_rate_vnd`, `basis`, `rounding_unit_vnd`, `period_key`, `period_start`, `period_end`, `cutoff_at`, `period_status`, `policy_status`

| Header | Type | Required | Disposition | Target | Reference | Rule | Decision |
|---|---|---|---|---|---|---|---|
| `fee_policy_code` | `string` | yes | `Persist` | FeePolicy.code | FeePolicy.building_id + FeePolicy.code | Reject blank or duplicate policy code. | `—` |
| `fee_policy_name` | `string` | yes | `Persist` | FeePolicy.name | — | Trim and enforce the target length. | `—` |
| `tenant_code` | `string` | yes | `Derive` | tenant_id | Tenant.code | Resolve exactly one tenant. | `—` |
| `site_code` | `string` | yes | `Derive` | site_id | Site.tenant_id + Site.code | Resolve within the tenant. | `—` |
| `building_code` | `string` | yes | `Derive` | building_id | Building.site_id + Building.code | Resolve within the site. | `—` |
| `version_number` | `integer` | yes | `Persist` | FeePolicyVersion.version_number | fee_policy_id + version_number | Require a positive integer and one version per policy. | `—` |
| `effective_from` | `date` | yes | `Persist` | FeePolicyVersion.effective_from | — | Require a valid date. | `—` |
| `effective_to` | `date` | no | `Persist` | FeePolicyVersion.effective_to | — | Optional date; must not precede effective_from. | `—` |
| `unit_rate_vnd` | `decimal` | yes | `Persist` | FeePolicyVersion.unit_rate_vnd | — | Parse Decimal, require non-negative VND, and quantize at the service boundary. | `—` |
| `basis` | `string` | yes | `Persist` | FeePolicyVersion.basis | — | Normalize/validate the billing basis. Enum: UNIT_AREA_M2. | `—` |
| `rounding_unit_vnd` | `decimal` | yes | `Persist` | FeePolicyVersion.rounding_unit_vnd | — | Parse Decimal and require a positive rounding unit. | `—` |
| `period_key` | `string` | yes | `Persist` | AccountingPeriod.period_key | Building.accounting_periods.period_key | Validate YYYY-MM and de-duplicate within a building. | `—` |
| `period_start` | `date` | yes | `Persist` | AccountingPeriod.period_start | — | Require period_end >= period_start. | `—` |
| `period_end` | `date` | yes | `Persist` | AccountingPeriod.period_end | — | Require period_end >= period_start. | `—` |
| `cutoff_at` | `datetime` | yes | `Persist` | AccountingPeriod.cutoff_at | — | Attach approved site timezone and store UTC. | `FCS-01:TIMEZONE` |
| `period_status` | `string` | yes | `Persist` | AccountingPeriod.status | — | Normalize/validate the accounting-period state. Enum: OPEN, CLOSING, CLOSED, LOCKED. | `—` |
| `policy_status` | `string` | yes | `Persist` | FeePolicy.is_active | — | Normalize the policy active flag and reject unknown values. | `—` |

### `10_hoa_don.xlsx`

- Schema version: `fcs05-r3`
- Sheets: `Dữ liệu` (data), `Hướng dẫn` (guidance)
- Expected data rows: `8`
- Natural key: `site_code`, `invoice_number`, `line_code`
- Target entities: `BillingRun`, `BillingInvoice`, `BillingInvoiceItem`
- Canonical inputs missing: `fee_policy_code`
- Canonical header order: `invoice_number`, `billing_account_number`, `tenant_code`, `site_code`, `building_code`, `unit_number`, `period_key`, `billing_run_key`, `policy_version`, `invoice_status`, `issued_on`, `due_on`, `total_vnd`, `outstanding_vnd`, `line_code`, `line_description`, `basis_quantity`, `unit_rate_vnd_snapshot`, `rounding_unit_vnd_snapshot`, `amount_vnd`, `notes`

| Header | Type | Required | Disposition | Target | Reference | Rule | Decision |
|---|---|---|---|---|---|---|---|
| `invoice_number` | `string` | yes | `Validate` | BillingInvoice.invoice_number | site_code + invoice_number | Use the file as an oracle; invoices are generated by Billing Run, never inserted from this file. | `—` |
| `billing_account_number` | `string` | yes | `Derive` | BillingInvoice.billing_account_id | BillingAccount.site_id + BillingAccount.account_number | Resolve exactly one billing account. | `—` |
| `tenant_code` | `string` | yes | `Derive` | tenant_id | Tenant.code | Resolve exactly one tenant. | `—` |
| `site_code` | `string` | yes | `Derive` | site_id | Site.tenant_id + Site.code | Resolve within the tenant. | `—` |
| `building_code` | `string` | yes | `Derive` | building_id | Building.site_id + Building.code | Resolve within the site. | `—` |
| `unit_number` | `string` | yes | `Derive` | unit_id | Unit.building_id + Unit.unit_number | Resolve exactly one unit. | `—` |
| `period_key` | `string` | yes | `Derive` | AccountingPeriod.id | Building.accounting_periods.period_key | Resolve one accounting period. | `—` |
| `billing_run_key` | `string` | yes | `Derive` | BillingRun.run_key | BillingRun.site_id + BillingRun.run_key | Resolve the generated Billing Run; never create a duplicate run from the oracle. | `—` |
| `policy_version` | `integer` | yes | `Derive` | FeePolicyVersion.id | fee_policy + version_number | Resolve the version used by Billing Run. | `—` |
| `invoice_status` | `string` | yes | `Validate` | BillingInvoice.status | — | Compare generated state; do not write status directly. Enum: DRAFT, ISSUED, PARTIALLY_PAID, PAID, VOID. | `—` |
| `issued_on` | `date` | yes | `Validate` | BillingInvoice.issued_on | — | Compare generated invoice date. | `—` |
| `due_on` | `date` | yes | `Validate` | BillingInvoice.due_on | — | Compare generated due date. | `—` |
| `total_vnd` | `decimal` | yes | `Validate` | BillingInvoice.total_vnd | — | Compare generated total; require sum(items) == total. | `—` |
| `outstanding_vnd` | `decimal` | yes | `Validate` | BillingInvoice.outstanding_vnd | — | Compare generated outstanding balance. | `—` |
| `line_code` | `string` | yes | `Validate` | BillingInvoiceItem.line_number/source reference | — | Compare generated line identity; no direct item insert. | `—` |
| `line_description` | `string` | yes | `Validate` | BillingInvoiceItem.description | — | Compare generated description. | `—` |
| `basis_quantity` | `decimal` | yes | `Validate` | BillingInvoiceItem.basis_quantity | — | Compare generated Decimal quantity. | `—` |
| `unit_rate_vnd_snapshot` | `decimal` | yes | `Validate` | BillingInvoiceItem.unit_rate_vnd_snapshot | — | Compare generated VND snapshot. | `—` |
| `rounding_unit_vnd_snapshot` | `decimal` | yes | `Validate` | BillingInvoiceItem.rounding_unit_vnd_snapshot | — | Compare generated rounding unit. | `—` |
| `amount_vnd` | `decimal` | yes | `Validate` | BillingInvoiceItem.amount_vnd | — | Compare generated amount and sum reconciliation. | `—` |
| `notes` | `string` | no | `Ignore-with-reason` | — | — | IGNORE: free text is not imported or emitted in evidence. | `—` |

### `11_thanh_toan.xlsx`

- Schema version: `fcs05-r3`
- Sheets: `Dữ liệu` (data), `Hướng dẫn` (guidance)
- Expected data rows: `8`
- Natural key: `site_code`, `source_reference`, `receipt_number`
- Target entities: `Payment`, `PaymentAllocation`, `UnmatchedPayment`, `OverpaymentCredit`
- Canonical inputs missing: `period_key`
- Canonical header order: `source_reference`, `receipt_number`, `payment_source`, `tenant_code`, `site_code`, `building_code`, `billing_account_number`, `received_at`, `amount_vnd`, `status`, `matched_invoice_number`, `allocated_vnd`, `unmatched_reason`, `overpayment_vnd`, `received_by_username`, `notes`

| Header | Type | Required | Disposition | Target | Reference | Rule | Decision |
|---|---|---|---|---|---|---|---|
| `source_reference` | `string` | yes | `Persist` | Payment.source_reference | tenant/site/payment_source/source_reference | Use as a non-PII idempotency key; reject conflict. | `—` |
| `receipt_number` | `string` | yes | `Persist` | Payment.receipt_number | tenant/site/receipt_number | Reject duplicate receipt number. | `—` |
| `payment_source` | `string` | yes | `Persist` | Payment.payment_source | — | Normalize/validate the payment source enum. Enum: CASH, BANK_TRANSFER, GATEWAY. | `—` |
| `tenant_code` | `string` | yes | `Derive` | tenant_id | Tenant.code | Resolve exactly one tenant. | `—` |
| `site_code` | `string` | yes | `Derive` | site_id | Site.tenant_id + Site.code | Resolve within the tenant. | `—` |
| `building_code` | `string` | yes | `Derive` | building_id | Building.site_id + Building.code | Resolve within the site. | `—` |
| `billing_account_number` | `string` | no | `Derive` | Payment.billing_account_id | BillingAccount.site_id + BillingAccount.account_number | Resolve when supplied; unmatched payments remain explicit. | `—` |
| `received_at` | `datetime` | yes | `Persist` | Payment.received_at | — | Attach approved site timezone and store UTC. | `FCS-01:TIMEZONE` |
| `amount_vnd` | `decimal` | yes | `Persist` | Payment.amount_vnd | — | Parse Decimal and require a positive VND amount. | `—` |
| `status` | `string` | yes | `Validate` | Payment.status | — | Replay through payment transitions and compare final status. Enum: RECEIVED, ALLOCATING, PARTIALLY_ALLOCATED, ALLOCATED, UNMATCHED, OVERPAID, REVERSED. | `—` |
| `matched_invoice_number` | `string` | no | `Derive` | PaymentAllocation.billing_invoice_id | BillingInvoice.site_id + BillingInvoice.invoice_number | Resolve exactly one invoice when supplied; never match by amount alone. | `—` |
| `allocated_vnd` | `decimal` | no | `Validate` | PaymentAllocation.amount_vnd | — | Compare allocation produced by the command service. | `—` |
| `unmatched_reason` | `string` | no | `Derive` | UnmatchedPayment.reason | — | Create only through the unmatched-payment state path. | `—` |
| `overpayment_vnd` | `decimal` | no | `Derive` | OverpaymentCredit.remaining_vnd | — | Create only through the overpayment-credit state path. | `—` |
| `received_by_username` | `string` | yes | `Derive` | Payment.received_by_id | Account.tenant_id + Account.username | Resolve an in-scope account. | `—` |
| `notes` | `string` | no | `Ignore-with-reason` | — | — | IGNORE: free text is not imported or emitted in evidence. | `—` |

### `12_buu_pham.xlsx`

- Schema version: `fcs05-r3`
- Sheets: `Dữ liệu` (data), `Hướng dẫn` (guidance)
- Expected data rows: `6`
- Natural key: `site_code`, `parcel_code`
- Target entities: `Parcel`, `CaseRecord`, `ImportExternalReference`
- Canonical inputs missing: —
- Canonical header order: `parcel_code`, `site_code`, `building_code`, `unit_number`, `recipient_name_snapshot`, `recipient_contact_masked`, `received_at`, `status`, `storage_location`, `ready_at`, `handed_over_at`, `pin_attempt_count`, `case_required`, `notes`

| Header | Type | Required | Disposition | Target | Reference | Rule | Decision |
|---|---|---|---|---|---|---|---|
| `parcel_code` | `string` | yes | `Persist` | Parcel.parcel_code | Parcel.site_id + Parcel.parcel_code | Reject blank or duplicate parcel code. | `—` |
| `site_code` | `string` | yes | `Derive` | site_id | Site.code | Resolve within the tenant. | `—` |
| `building_code` | `string` | yes | `Derive` | building_id | Building.site_id + Building.code | Resolve within the site. | `—` |
| `unit_number` | `string` | yes | `Derive` | unit_id | Unit.building_id + Unit.unit_number | Resolve exactly one unit. | `—` |
| `recipient_name_snapshot` | `string` | yes | `Persist` | Parcel.recipient_name_snapshot | — | Persist only within the approved local scope; do not use as a join key. | `—` |
| `recipient_contact_masked` | `string` | yes | `Persist` | Parcel.recipient_contact_snapshot | — | Accept only the masked representation. | `—` |
| `received_at` | `datetime` | yes | `Persist` | Parcel.received_at | — | Attach approved site timezone and store UTC. | `FCS-01:TIMEZONE` |
| `status` | `string` | yes | `Validate` | Parcel.status | — | Replay legal parcel transitions; never write a terminal status directly. Enum: RECEIVED, READY_FOR_PICKUP, HANDED_OVER, RETURNED, LOST, DAMAGED. | `—` |
| `storage_location` | `string` | yes | `Persist` | Parcel.storage_location | — | Trim and enforce the target length. | `—` |
| `ready_at` | `datetime` | no | `Derive` | Parcel.ready_for_pickup_at | — | Use only when the state machine allows READY_FOR_PICKUP. | `FCS-04:FUTURE_TIME` |
| `handed_over_at` | `datetime` | no | `Derive` | Parcel.handed_over_at | — | Use only through handover command and never without PIN verification. | `FCS-05:PARCEL_PIN` |
| `pin_attempt_count` | `integer` | yes | `Validate` | Parcel.pin_attempt_count | — | Validate state metadata; never import or emit a plaintext PIN. | `—` |
| `case_required` | `boolean` | yes | `Derive` | CaseRecord | — | Create a case only through the parcel exception/case command. | `FCS-05:PARCEL_EXCEPTION` |
| `notes` | `string` | no | `Ignore-with-reason` | — | — | IGNORE: free text is not imported or emitted in evidence. | `—` |

## 5. Trạng thái quyết định owner và cổng nguồn

| Mã/nhóm | Nội dung | Tác động | Trạng thái/điều kiện |
|---|---|---|---|
| FCS-01:TIMEZONE | Timezone site và provenance | Tất cả datetime | DONE — User/Owner duyệt `Asia/Ho_Chi_Minh` ngày 2026-09-27 |
| FCS-04:AREA_PRECISION | Unit.area_m2 đi vào cột Float | Sai số diện tích/billing | DONE — quantize `0.01` trước storage boundary |
| FCS-04:OWNERSHIP_ZERO | Ratio 0 của non-owner | Tính quyền sở hữu | DONE — chuẩn hóa `0 → NULL` và kiểm relationship |
| FCS-04:FUTURE_TIME | Timestamp tương lai | Replay state machine | Rule DONE; current source preflight có 0 terminal candidate, còn lịch dự kiến được cảnh báo riêng |
| FCS-05 (13 quyết định) | Category/SLA, WO source, maintenance, cleaning, patrol, incident, parcel và finance canonical keys | Mapping/preflight/replay | DONE — mapping `fcs05-r2`, `open=0`; incident enum nằm trong contract `fcs05-r3` |
| FCS-10 reference representation | Metadata reference/replay | Reference/replay | Domain command đã triển khai; DB readback vẫn cần approved pack |
| Canonical input | File 10 `fee_policy_code` và file 11 `period_key` | Invoice/payment mapping | DONE — derive fail-closed; không join theo tên hoặc số tiền |

## 6. Kiểm tra tính nhất quán

Validator chạy độc lập với database:

```powershell
$python = "backend\.venv\Scripts\python.exe"
& $python "backend\app\services\submission_data_contract.py"
& $python -m py_compile "backend\app\services\submission_data_contract.py"
```

Kết quả hiện tại: FCS03_CONTRACT=PASS, đủ 12/12 workbook contract; fingerprint
`4d749f7377335c49a6b3159e0d1e12bfb5480cd95f158bca2fe7f52a5ce16147`. FCS-05
mapping catalog đã chuyển sang `RESOLVED` với fingerprint riêng trong evidence
pack. Reader/preflight FCS-06/FCS-07 đối chiếu header thực tế, row count, sheet
set và disposition trước bất kỳ database write nào.

## 7. Ranh giới ghi database

- FCS-03 chỉ định nghĩa contract, natural key, reference, normalization rule và oracle.
- Không có lệnh insert/update/migration trong contract module; raw workbook không bị chỉnh sửa.
- Import run, external reference, transaction và idempotency bắt đầu ở FCS-08/FCS-09 sau khi FCS-05 và preflight FCS-07 đạt.

## 8. Quy tắc FCS-04 đã khóa

Module thực thi là
[`submission_data_normalization.py`](../../backend/app/services/submission_data_normalization.py).
Module chỉ nhận giá trị đã đọc từ reader, trả về giá trị canonical hoặc lỗi có mã;
module không mở session và không ghi database.

| Nhóm | Quy tắc canonical | Bằng chứng/ghi chú |
|---|---|---|
| Token | Role, status và relationship được so sánh không phân biệt hoa thường và trả về semantic token lowercase; adapter persistence dùng `target_enum` khi schema đích yêu cầu chữ hoa. | Idempotent: chạy lại không đổi token đã chuẩn hóa. |
| Text/phone | Phone và text phải là string; phone dùng strict mode để không tự dựng lại số 0 đầu bị mất khi Excel đọc sai kiểu. | Không dùng tên/email/phone làm khóa. |
| Money/quantity | Parse bằng `Decimal(str(value))`; ROUND_HALF_UP; VND quantum `1`; quantity quantum `0.0001`; ownership quantum `0.0001`. | Không dùng float cho phép tính canonical. |
| Ownership | Owner phải có ratio `(0, 1]`; non-owner có ratio `0` được canonicalize thành `NULL`, ratio khác 0 bị từ chối. | Khớp constraint `ownership_ratio_semantics`. |
| Datetime/date | Gắn timezone site đã duyệt `Asia/Ho_Chi_Minh` cho giá trị naive, sau đó lưu UTC; giá trị có timezone được đổi sang cùng site timezone trước khi chuyển UTC. | User/Owner đã duyệt timezone ngày 2026-09-27. |
| Future time | Giá trị sau cutoff được phân loại `scheduled_future`; truyền `terminal_event=True` sẽ trả lỗi `FUTURE_TERMINAL_EVENT`. | Source preflight tại `2026-10-01T16:59:59Z`: `42` future, `0` terminal candidate, `36` `FUTURE_SCHEDULE` warning; checksum verified. |
| Area | Chính sách FCS-04: `Decimal` quantize `0.01`, rồi chuyển sang Float ở boundary hiện tại (`FLOAT_QUANTIZED_0_01`). | Nếu đổi schema sang Numeric, chỉ thay adapter storage; không đổi canonical rule. |
| External key | 12 spec định danh dùng scope code + source reference; payload version `ek1`, deterministic, không chứa field PII. | Bao phủ work, employee, unit, resident, asset, cleaning, patrol, incident, fee policy, invoice, payment, parcel. |

### Ví dụ chuẩn hóa tổng hợp (giá trị minh họa, không lấy từ raw workbook)

| Input | Canonical output |
|---|---|
| Role ` Technician ` | `technician` |
| Relationship `OWNER` | `owner` |
| Money `1000.4` | Decimal `1000` |
| Area `80.126` | Decimal `80.13`, storage adapter `80.13` |
| Non-owner ratio `0` | `NULL` |
| Naive local datetime | `site timezone → UTC` |

### Fingerprint và kiểm tra FCS-04

- Normalization version: `fcs04-r1`.
- Normalization fingerprint: `0951bb4d6d74aac68859259eaf66901f925a3a0924832f0bfa6d9bdd1ac52b9d`.
- Chạy self-check không cần database:

```powershell
$python = "backend\.venv\Scripts\python.exe"
& $python "backend\app\services\submission_data_normalization.py"
& $python -m py_compile "backend\app\services\submission_data_normalization.py"
```

Kết quả đã xác nhận: `FCS04_NORMALIZATION=PASS`; guard vẫn từ chối terminal event
tương lai. Source-specific preflight hiện PASS với 0 terminal candidate; kết quả
này cần chạy lại trên candidate cuối trước khi đóng Final Submission Gate.

## 9. Evidence FCS-05 đến FCS-12

Evidence chi tiết, đã redact và không chứa raw cell value, nằm tại
[FCS-05-10_EXECUTION_EVIDENCE.md](phase-3/evidence/FCS-05-10_EXECUTION_EVIDENCE.md) và
[FCS-10-12_EXECUTION_EVIDENCE.md](phase-3/evidence/FCS-10-12_EXECUTION_EVIDENCE.md).

Tóm tắt kiểm chứng hiện tại:

| Task | Kết quả |
|---|---|
| FCS-05 | `FCS05_MAPPING=PASS`, version `fcs05-r2`, `open=0`; 13 mapping decision và hai canonical derivation đã khóa fail-closed. |
| FCS-06 | `FCS06_READER=PASS`, 12 workbook/101 dòng; targeted suite `8 passed` với giới hạn kích thước, formula, hidden sheet và header tampering. Reader giữ external-link metadata để từ chối liên kết ngoài. |
| FCS-07 | Source preflight tại `2026-10-01T16:59:59Z`: `101/101 decided`, `0 orphan`, checksum verified, `42` future, `0` terminal candidate, `36` `FUTURE_SCHEDULE` warning; dry-run không ghi database. |
| FCS-08 | Alembic `0018 (head)`; snapshot lịch sử ngày 2026-09-27 có `307 passed, 1 skipped, 2 warnings`. Task 2 rerun trên PostgreSQL disposable ngày 2026-10-01: migration/repeat/drift, seed repeat, synthetic rehearsal, full regression `379 passed, 1 skipped` và shutdown đều PASS; chưa là candidate cuối. |
| FCS-09 | Master loader raw dry-run Task 2 PASS (`stage=all`, 12 workbook/101 dòng, `database_write=false`); synthetic clean-DB dry-run/apply/verify/retry PASS. Task 1 chỉ ghi DB local bằng READ ONLY: 38 table có dữ liệu/272 bản ghi. Các aggregate này không thay thế apply/verify/package evidence của candidate cuối. |
| FCS-10 | Reference loader mở rộng category/maintenance/finance và cleaning/security/parcel initial-state; dry-run pass, `database_write=false`; reference count/apply trên DB sạch chưa chạy. |
| FCS-11 | Contract và loader đã resolve scope/role/reference cho file 06, 07, 08, 12; terminal source state chỉ dành cho replay; chưa có DB readback. |
| FCS-12 | Replay service có state transition, actor/scope, correlation, audit/domain event và idempotency; source preflight hiện không bị terminal-time block, nhưng CLOSED vẫn cần evidence binary và replay phải được chứng minh trên candidate cuối. |

Các mục chưa có reference count/apply/DB readback ở FCS-10..12 áp dụng cho
approved raw pack và API readback sau restart. Chúng không phủ định synthetic
clean-DB rehearsal của Task 2, vốn chỉ là evidence local.

Raw `excel-data` vẫn chỉ đọc cục bộ. Không dùng kết quả dry-run hoặc migration
rehearsal để tuyên bố dữ liệu thật đã được nạp vào database.

