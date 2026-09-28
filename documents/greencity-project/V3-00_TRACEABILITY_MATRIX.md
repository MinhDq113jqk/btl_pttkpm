# V3-00 — Ma trận truy vết code và phạm vi demo

**Ngày kiểm kê:** 2026-09-25
**Nguồn kế hoạch:** [`roadmap_v3.md`](roadmap_v3.md)
**Checkout:** `_pttkpm`, nhánh `main`; working tree đang có nhiều thay đổi chưa commit.
**Loại bằng chứng:** đọc tĩnh mã nguồn, cấu hình package và tên test hiện có. Không chạy test, không gọi dịch vụ ngoài, không sửa code sản phẩm.

## Kết quả V3-00

Đã xác định các bề mặt đang được role menu cấp, đối chiếu page/client/API/model/test cho tám Golden Flow, phân loại các mục prototype hoặc chưa có đường UI, và lập thứ tự bàn giao V3-01. Kết quả này là snapshot của working tree tại ngày ghi trên; cần cập nhật nếu code thay đổi trước khi triển khai V3-01.

### Quy ước quyết định

- **Giữ:** có bề mặt UI đang dùng và đường gọi dữ liệu thật; vẫn cần kiểm tra acceptance của Golden Flow.
- **Hoàn thiện:** backend hoặc UI một phần đã tồn tại nhưng thiếu liên kết/luồng để đáp ứng mục tiêu đồ án.
- **Ẩn:** không thuộc luồng đồ án đã chọn hoặc chưa có implementation thật; không xuất hiện như tính năng đang hoạt động.

## Task 1 — Phạm vi và mẫu truy vết

### Phạm vi đề xuất đã khóa cho lượt kiểm kê

Giữ tám luồng GF-01..08 làm luồng bảo vệ đồ án. Dashboard điều hành đặt ở **Tổng quan**; không cần tab Reports độc lập nếu điều hướng được từ KPI tới drill-down và audit. “Khách hàng & Cư dân” hiện là Unit 360° cho nhân viên; Resident Portal là bề mặt riêng được mount theo role resident. Import/export là khả năng ngoài tám Golden Flow nhưng đã có backend, vì vậy đánh dấu **Hoàn thiện** theo V3-04 trước khi giới thiệu như một mục menu.

### Mẫu dòng ma trận

`ID / vai trò → menu / route → React page → client method → API route → service / model / table → test → trạng thái → việc còn thiếu`

Không coi API hoặc test riêng lẻ là bằng chứng UI hoàn tất. Danh sách test dưới đây chỉ xác nhận có test được khai báo trong checkout; kết quả chạy hiện tại chưa được kiểm tra.

## Task 2 — Menu và quyền theo vai trò

`createAuthenticatedAccount()` trong `greencity-app/src/data/authSession.js` tạo menu staff từ `roles` do `/auth/me` trả về. `getAllowedNav()` lọc danh sách `navItems` theo menu này. Backend router được mount trong `backend/app/main.py`; quyền cuối cùng vẫn do backend enforce.

| Role từ server | Bề mặt chính trong menu staff | Ghi chú truy vết |
|---|---|---|
| `admin`, `director` | Tổng quan, Công việc & Yêu cầu, Vệ sinh, An ninh, Bưu phẩm, Tài chính, Khách hàng & Cư dân, Thông báo | Có dashboard điều hành và quyền quản lý được thể hiện trong policy frontend; vẫn phải kiểm thử quyền API. |
| `accountant` | Tổng quan, Công việc & Yêu cầu, Khách hàng & Cư dân, Tài chính, Thông báo | Executive KPI và quản trị outbox không nằm trong nhóm role policy tương ứng. |
| `cskh` | Tổng quan, Công việc & Yêu cầu, Bưu phẩm, Khách hàng & Cư dân, Thông báo | Có quyền tạo yêu cầu; thao tác Work Order chưa đủ trên UI tác vụ. |
| `technical_lead` | Tổng quan, Công việc & Yêu cầu, Khách hàng & Cư dân, Thông báo | Chưa có mục Technical/Maintenance trên menu. |
| `technician` | Tổng quan, Công việc & Yêu cầu, Thông báo | Danh sách có scope theo việc được giao; chi tiết UI hiện read-only. |
| `cleaning` | Tổng quan, Vệ sinh, Thông báo | Cleaning page gọi client API; quyền API vẫn là nguồn quyết định. |
| `security` | Tổng quan, An ninh, Bưu phẩm, Khách hàng & Cư dân, Thông báo | Bao gồm luồng vận hành security và parcel theo policy hiện tại. |
| `resident` | Resident Portal riêng; nhánh render tách khỏi staff shell | `App.jsx` trả `ResidentPortalView` trước khi render sidebar staff. Không dùng tab `residents` của staff làm Resident Portal. |
| Role không khớp policy | Tổng quan, Thông báo | Không được cấp thêm menu chỉ bằng frontend. |

`navItems` trong `greencity-app/src/data/mockData.js` còn các ID `refund-form`, `projects`, `amenities`, `technical`, `media`, `reports`, `settings`; các ID này không được đưa vào `account.menu`, vì vậy menu được cấp hiện không hiển thị chúng. Tuy nhiên nguồn nav vẫn đặt chung với mock business data và còn count/badge tĩnh. Hash tới một ID chưa được cấp sẽ đi vào nhánh “Không có quyền xem phân hệ này”; V3-01 nên chuẩn hóa điều hướng để thông báo đúng nghĩa “chưa hỗ trợ/không tìm thấy” thay vì biểu đạt như lỗi phân quyền.

## Task 3 — Ma trận menu → page → client → API → database

| ID / luồng | Menu / page đang hoạt động | Client → API và persistence | Test có trong checkout | Quyết định và khoảng trống |
|---|---|---|---|---|
| GF-01 Auth/session/site | Đăng nhập; staff shell; `PasswordChange` | `authenticate`, `switchSite`, `logoutCurrentSession`, `changePassword` → `/auth/login`, `/auth/me`, `/auth/switch-site`, `/auth/logout`, `/auth/change-password`; `Account`, `AccountRole`, `AuthSession`, `LoginThrottle` | `backend/tests/test_login_credentials.py`, `test_rbac_boundary.py`, `test_security_boundary.py`; frontend `runtime-config.test.js`, `frontend-integration.test.js`, `staff-ux.cjs` | **Giữ + xác minh parity.** Đối chiếu mọi role/menu với quyền API và kiểm tra đổi site/logout/password trong GF-01. |
| GF-02 Request → Work Order | `tasks` → `TasksDesktopView`; form tạo request; chi tiết hiện chỉ đọc | `listServiceRequests`, `createServiceRequest` → `/service-requests`, `/service-request-form-options`; backend còn `/triage`, `/work-orders`, assign/start/checklist/evidence/cost/submit/accept/reopen/close. Lưu trong `ServiceRequest`, `WorkOrder`, checklist, cost/charge và audit models | `backend/tests/test_r2_integration.py`, `test_r6_resident_service_requests_integration.py`; frontend `staff-ux.cjs`, `resident-ux.cjs` | **Hoàn thiện (P1/V3-05).** `App.jsx` còn hiển thị “Hồ sơ chỉ đọc”; nối đủ mutation, refresh/readback và negative role path để đóng GF-02. |
| GF-03 Maintenance | Không có mục/page Technical được mount trong staff app | Backend `maintenance.py`: tạo/xem asset, plan, chạy scheduler, defer occurrence, history; model `Asset`, `MaintenancePlan`, `MaintenanceOccurrence`, `MaintenanceHistory`. Không tìm thấy method maintenance tương ứng trong `apiClient.js` | `backend/tests/test_r2_integration.py` có scheduler/completion/defer; `test_contract.py` kiểm tra route | **Hoàn thiện (P1/V3-06).** Cần page + client + list/filter theo nhu cầu; hiện chưa có đường UI tới GF-03. |
| GF-04 Cleaning | `cleaning` → `CleaningDesktopView` | Client `listCleaningRoutes`, `listCleaningTasks`, `createCleaningShift`, assign/start/checklist/submit/accept → `/cleaning/...`; model `CleaningRoute`, `CleaningShift`, `CleaningTask`, checklist results và liên kết remediation | `backend/tests/test_r3_cleaning_integration.py`; frontend `cleaning-ux.cjs` | **Giữ + khóa GF.** Test browser pass/fail, role âm và rework; không kết luận hoàn tất chỉ từ tồn tại page/API. |
| GF-05 Security | `security` → `SecurityDesktopView` | Client cho shift, handoff, visitor, patrol, incident, evidence, escalation/ack/transition → `/security/...`; model security trong `operations.py` | `backend/tests/test_r3_security_integration.py`; frontend `security-ux.cjs` | **Giữ + khóa GF.** Cần bao phủ audit từng bước và điều kiện không đóng incident mức cao khi thiếu điều kiện. |
| GF-06 Parcel | `parcels` → `ParcelDeskView` | Client intake, ready, handover, exception, Case/incident, evidence/timeline → `/parcels/...`; model `Parcel`, attachment/Case/incident liên quan | `backend/tests/test_v1_parcel_workflow_integration.py`; frontend `parcel-ux.cjs` | **Giữ + khóa GF.** Xác minh PIN không lộ, retry/idempotency và scope file trong luồng UI. |
| GF-07 Billing/resident | `finance` → `BillingDesktopView`; resident route riêng → `ResidentPortalView` | Finance client policy/period/run/invoice/payment/unmatched/credit → `/billing/...`; resident client billing → `/resident/billing/...`; model trong `billing.py` và resident read APIs | `backend/tests/test_r4_billing_integration.py`, `test_r4_billing_issue_integration.py`, `test_r4_payment_allocation_integration.py`, `test_r6_resident_billing_integration.py`; frontend `billing-ux.cjs`, `payment-ux.cjs`, `resident-ux.cjs` | **Giữ trong local scope.** Chỉ credit cơ bản; không trình bày refund payout. Chưa thấy resident API trả payment initiation thật, cần giới hạn copy vào xem hóa đơn/thanh toán theo endpoint hiện có. |
| GF-08 Dashboard/audit | Dashboard nằm trong `overview` theo role; tab `reports` riêng không được cấp | `getDashboard`, `getDashboardDrillDown`, `listAuditEvents` → `/dashboard`, `/dashboard/drill-down/{metric}`, `/audit-events`; `as_of` được gửi ở dashboard/drill-down/audit; audit lưu `AuditEvent` | `backend/tests/test_r5_dashboard_integration.py`, `test_r5_golden_flows_integration.py`; frontend `dashboard-ux.cjs` | **Giữ dashboard, ẩn tab Reports riêng.** Test hiện có kiểm tra oracle/scope/timezone; cần xác nhận cùng cutoff xuyên suốt drill-down và audit, kể cả role/site đang chọn. |
| Notifications | `notifications` → `NotificationsDesktopView` | Client `listNotifications`, `markNotificationRead`, outbox methods → `/notifications`, `/notifications/{id}/read`, `/outbox/events...`; `NotificationReadModel`, domain/outbox/audit models | `backend/tests/test_r5_outbox_integration.py`, `test_r6_resident_notifications_integration.py`; frontend `notification-ux.cjs` | **Giữ.** Staff notifications và resident notifications là API/bề mặt riêng; phân biệt rõ khi kiểm tra role. |
| Unit 360 / master data | `residents` cho staff → `Unit360View`; không phải import page | `getUnit360` → `/units/{unit_id}/360`; backend có persons/units/import endpoints; `Unit`, `Person`, relationship và `ImportRun`/rows | `backend/tests/test_unit_import_postgres.py`, `test_import_runs_postgres.py`; frontend coverage cần xác định cụ thể cho Unit360 | **Giữ Unit 360; Hoàn thiện import.** Không thấy ImportRun methods trong `apiClient.js`, cũng không có page upload/preview/apply/error download. Chưa tìm thấy export route tương ứng. |

### Menu item và prototype chưa chọn

| ID / bề mặt | Trạng thái hiện tại | Quyết định |
|---|---|---|
| `technical` | Có trong `navItems`; chưa có page mount trong `App.jsx`; backend maintenance tồn tại | **Hoàn thiện** cho GF-03, không mở rộng sang kho/IoT. |
| `reports` | Có trong `navItems`; không nằm trong role menu; dashboard/audit nằm ở Overview | **Ẩn tab riêng** hoặc điều hướng rõ tới phần dashboard thật trong Overview. |
| `refund-form` | Nav cũ; component refund dùng case mẫu; không có payout API tương ứng | **Ẩn** refund payout; finance giữ Overpayment Credit thật. |
| `media` | `MediaChannelsView` dùng dữ liệu metrics/connection giả, chưa có API | **Ẩn** trong demo và menu. |
| `amenities` | `UrbanAmenitiesView` dùng dữ liệu tĩnh, chưa có domain/API persistence | **Ẩn** trong demo và menu. |
| `projects`, `settings` | Có ID trong nav cũ nhưng không có page/API đang mount tương ứng | **Ẩn** trong menu demo. |
| `StaffDashboard`, mobile shell cũ và helper prototype | Còn component/test/helper trong source; chưa xác định hết import graph trong lượt này | **Chưa xóa.** Để V3-12 rà import graph trước khi dọn. |

## Task 4 — Test mapping và giới hạn bằng chứng

Các test liên quan được tìm thấy theo luồng ở ma trận trên. `greencity-app/package.json` tách `npm test` cho unit/integration frontend với các script UX riêng như `test:staff`, `test:cleaning`, `test:security`, `test:parcel`, `test:billing`, `test:payments`, `test:notifications`, `test:dashboard`, `test:resident`. Vì vậy `npm test` không đồng nghĩa toàn bộ browser/UX suites đã chạy.

Backend có các API/DB integration tests riêng theo R2–R6, `test_contract.py`, `test_import_runs_postgres.py` và parcel workflow suite. Tên test được liệt kê ở đây dựa trên file và hàm có trong working tree; chưa đọc kết quả CI hiện tại, chưa chạy test và chưa đánh giá coverage từng mutation một cách đầy đủ. Task V3-13 vẫn cần bổ sung/ghép browser Golden Flow GF-01..08 trên DB cô lập và xác nhận persisted state sau reload.

## Task 5 — Rà soát chéo và bàn giao V3-01

### Danh sách việc V3-01 theo mức ưu tiên

1. Giữ menu theo danh sách role đã truy vết; xóa các ID unsupported khỏi cấu hình nav active, bỏ badge/count tĩnh và giữ kiểm tra role server-side.
2. Giữ Dashboard/Audit tại `overview`; bỏ tab `reports` độc lập hoặc cho nó điều hướng tới dashboard hiện có. Đảm bảo route/hash trực tiếp tới module không hỗ trợ có thông báo rõ, không giả là lỗi quyền.
3. Thêm route/điểm vào Technical tối thiểu cho Maintenance để tạo điều kiện cho V3-06; nếu chưa triển khai cùng lát dọc, ẩn khỏi menu cho tới khi page thật sẵn sàng.
4. Kiểm tra nhánh `resident` và các menu staff riêng biệt; bảo đảm các test role xác nhận resident vào Resident Portal còn staff vào Unit 360°.
5. Không đưa import/export, refund payout, media, amenities, project hoặc settings vào menu như tính năng hoạt động khi chưa có UI/API thật.

### Tiêu chí chấp nhận cho bàn giao

- Mỗi role trong bảng quyền chỉ thấy các mục đã định; backend vẫn từ chối request sai role/site.
- Mỗi menu item đang hiển thị mở đúng page thật; tab cố định không có implementation không xuất hiện.
- Overview chứa đường truy cập rõ tới KPI, drill-down và audit; không tạo nguồn KPI thứ hai.
- Resident Portal và Unit 360° không bị nhập nhằng theo nhãn “Cư dân”.
- V3-01 kết thúc bằng test menu/route cho từng role và bằng chứng test được chạy; không dùng kết quả cũ của roadmap làm trạng thái hiện tại.

### Open items còn cần xác nhận trước khi coi các luồng đóng

- Dashboard KPI → drill-down → audit có browser checks mock và PostgreSQL API tests; chưa có một browser run nối trực tiếp vào backend thật.
- Resident/cleaning/security/parcel/payment UX suites vẫn dùng mock API; persistence và role boundary được chứng minh riêng ở backend integration tests.
- Import/export hiện hỗ trợ schema Unit; export Person là ngoài schema ImportRun hiện tại và cần task riêng nếu rubric yêu cầu.
- Xem xét working-tree diff trước triển khai để tránh ghi đè hoặc đưa các thay đổi chưa liên quan vào scope V3-01.

## V3-01 — Kết quả triển khai (2026-09-25)

| Task | Kết quả |
|---|---|
| Ma trận menu theo role | Đã thêm test unit cho 9 role; menu chỉ nhận các ID staff page có implementation. Menu vẫn bắt nguồn từ role `/auth/me`, backend tiếp tục enforce authorization. |
| Ẩn prototype | Sidebar chỉ nhóm các trang đang hoạt động; các ID refund, project, amenities, media, reports và settings không thể lọt vào menu hoặc `canViewTab`, kể cả khi session cũ chứa các ID đó. Maintenance được thêm sau khi V3-06 có page thật và chỉ dành cho technical_lead/technician. |
| Hash/deep-link | Hash ngoài allow-list quay về `#/overview` và được chuẩn hóa khi tải trang, đổi fragment hoặc dùng history navigation. Hash tới trang hợp lệ nhưng thiếu quyền vẫn hiện trạng thái không có quyền. |
| Dashboard/Reports | Executive Dashboard và Audit Explorer tiếp tục ở Overview; Reports riêng không hiện trên menu. Dashboard UX suite xác nhận KPI → drill-down → audit và role CSKH không thấy Executive KPI. |
| Kiểm thử role/điều hướng | Unit xác nhận 9 role và stale menu; browser suite xác nhận menu CSKH, deep-link Maintenance/refund, Resident Portal, dashboard và các nhóm Sidebar. |

### Bằng chứng kiểm tra local

- `npm test`: **73 passed**.
- Frontend UX suites: **156 checks passed** — staff 38, resident 17, dashboard 24, cleaning 6, security 7, parcel 13, billing 10, payments 14, notifications 17, desktop 10.
- `npm run build`: **PASS**, 1,618 modules bundled.
- Browser UX suites dùng API mock để kiểm tra UI/điều hướng; chúng không thay thế bằng chứng backend authorization hoặc persistence.
- Ghi chú V3-01 ở trên là historical snapshot; V3-12 đã rà active import graph và dọn prototype, xem phần V3-12..16 ở cuối tài liệu.

## V3-02..06 — Kết quả triển khai (2026-09-25)

| Task | Kết quả |
|---|---|
| V3-02 — Mock và nav | `navItems` đã chuyển sang `greencity-app/src/data/navigation.js`; `normalizeSearch` ở helper riêng; SearchDialog nhận menu/task thật qua props và không tự nạp fixture. Mock store và prototype component không còn trên active import path. |
| V3-03 — Local bootstrap | README gốc là hướng dẫn chạy/reset/test duy nhất; frontend dùng port 3000. Seed bị tắt mặc định, chỉ chạy development/test với 10 credential riêng ngoài repo; reset schema chỉ hướng dẫn cho DB disposable. CORS mẫu đã bỏ port 5173. |
| V3-04 — Unit ImportRun | Thêm menu admin/CSKH, upload → map → preview → apply, xem/trang dòng lỗi, tải error CSV qua signed link và mở lại run theo ID. Thêm Unit CSV export schema cố định, giới hạn building qua grant hiện hành, chống formula injection và audit sự kiện export. |
| V3-05 — Work Order | Chi tiết request tải lại state từ API; có triage, tạo WO/checklist, assign, start, checklist result, private evidence, cost line, submit, accept/proxy, reopen/cancel/close và đọc lại state. Bổ sung API list WOs, assignees, evidence, cost lines theo scope. Assignment giữ contract hiện hữu: technician site-granted được chọn bởi technical lead; technician chỉ đọc Work Order đã giao cho chính mình. |
| V3-06 — Maintenance | Technical Lead tạo Asset/Plan, chạy scheduler, đọc occurrence/WO/history và hoãn lịch. Technician thấy riêng các maintenance WO được giao và xử lý checklist/evidence/submit; Technical Lead nghiệm thu và ghi history. Các list/options mới lọc theo active site, building grant hoặc account được giao. |

### Bằng chứng kiểm tra V3-02..06

- `npm test`: **74 passed**.
- Browser UX suites: **182 checks passed** — staff 38, resident 17, dashboard 24, desktop 10, cleaning 6, security 7, parcel 13, billing 10, payments 14, notifications 17, imports 12, work-orders 7, maintenance 7.
- `npm run build`: production bundle pass sau khi tách Import, Maintenance và Work Order thành lazy chunks.
- `scripts/test_isolated.py`: **294 passed, 1 skipped, 2 warnings** trên PostgreSQL/TLS dùng một lần; migration, seed repeat và drift checks pass; PostgreSQL shutdown pass.
- Browser suites dùng API mock để kiểm tra UI và API request shape; persistence, scope, export audit, assignment, scheduler và history được kiểm tra riêng trong PostgreSQL integration suite.
- Review độc lập Antigravity chưa có kết quả. Auto-review trước đó chặn việc gửi code riêng tư và logic phân quyền ra dịch vụ ngoài; không thử gửi lại khi chưa có chấp thuận cụ thể.

## V3-07..11 — Kết quả triển khai (2026-09-25)

| Task | Kết quả |
|---|---|
| V3-07 — Cleaning | UI có tạo ca, phân công, checklist, nộp/duyệt, ghi nhận bỏ lỡ/hủy với lý do; khi checklist fail hiển thị ID Work Order/Case remediation. Browser checks chạy cả path đạt và không đạt. |
| V3-08 — Security | Browser flow bao phủ tạo ca, bàn giao, visitor, check-in/hoàn tất tuần tra, tạo sự cố mức cao, evidence, acknowledgement của Security/Director; thử đóng sớm bị chặn cho tới khi đủ acknowledgement. |
| V3-09 — Parcel/Resident | Các trang hiện có được xác nhận qua parcel/resident UX suites và backend scope/evidence integration tests; PIN và file riêng tư giữ đúng ranh giới server. |
| V3-10 — Finance | Billing/payment UI và backend Golden Flow hiện có được chạy lại; giữ manual payment, unmatched và credit trong local scope, không giới thiệu refund payout. |
| V3-11 — Dashboard/Reports | Reports riêng tiếp tục được bỏ; KPI, drill-down, audit, notification inbox/outbox nhận chung một `as_of` khi mở từ executive workspace. Notification cutoff lọc theo thời điểm tạo; trạng thái đọc/giao nhận vẫn là trạng thái hiện tại. |

### Bằng chứng kiểm tra cuối V3-02..11

- `npm test`: **74 passed**.
- Browser UX suites: **200 checks passed** — staff 38, resident 17, dashboard 25, desktop 10, cleaning 16, security 14, parcel 13, billing 10, payments 14, notifications 17, imports 12, work-orders 7, maintenance 7.
- `npm run test:assistant:security`: build pass và quét 17 source/9 bundle files; production main bundle khoảng 484 KB, ba màn lớn tách thành lazy chunks.
- `scripts/test_isolated.py`: **295 passed, 1 skipped, 2 dependency warnings** trên PostgreSQL/TLS dùng một lần; migration/seed-repeat/drift và shutdown pass.
- Mocked browser suites xác nhận giao diện, role visibility và request shape; PostgreSQL integration suite xác nhận persistence, scope, audit, idempotency và state transitions.

## File tham chiếu đã kiểm tra

- `greencity-app/src/App.jsx`
- `greencity-app/src/data/authSession.js`
- `greencity-app/src/data/mockData.js`
- `greencity-app/src/data/navigation.js`, `greencity-app/src/data/searchUtils.js`
- `greencity-app/src/services/apiClient.js`
- `greencity-app/src/components/ImportRunsView.jsx`, `WorkOrderWorkspace.jsx`, `MaintenanceDesktopView.jsx`
- `greencity-app/package.json`
- `backend/app/main.py`, `backend/app/api/units.py`, `maintenance.py`, `service_requests.py`
- `backend/app/models/`, `backend/app/schemas/r2.py`
- `backend/tests/`, `greencity-app/tests/`
- `documents/greencity-project/roadmap_v3.md`
## V3-12..16 — Kết quả closeout (2026-09-25)

Các mục dưới đây cập nhật bằng chứng sau khi triển khai. Chúng thay thế các
ghi chú “chưa chạy” ở snapshot V3-00 cho phạm vi V3-12..V3-16; không thay đổi
kết luận lịch sử của V3-00..V3-01.

| Task | Kết quả và truy vết | Trạng thái |
|---|---|---|
| **V3-12 — Legacy/dead code** | Đã bỏ khỏi active frontend path các prototype Media, Amenities, refund payout, StaffDashboard/mock-role và mobile shell cũ; test fixtures không được coi là runtime data. Source scan active src không còn tên prototype, fake metric, debug log, TODO/FIXME hoặc provider key; assistant security scan kiểm tra source/bundle. | **Đạt local** |
| **V3-13 — Golden Flow/contract** | Thêm tests/golden-flows.cjs để chạy GF-01..08. Browser suites xác nhận menu, request shape, negative path và retry; backend isolated PostgreSQL xác nhận persistence/scope/audit/idempotency/state transition. Browser fixture không thay thế backend evidence. | **Đạt local** |
| **V3-14 — Error/UX** | SessionDashboard phân biệt loading/error/empty và giữ filter khi retry; ResidentPortalView có error summary, focus và liên kết field qua aria-describedby; browser flow bao phủ lỗi mạng, 401/404/409/422 và recovery. | **Đạt local** |
| **V3-15 — Demo kit** | README root là hướng dẫn chạy/reset/test; seed credential được cấp bằng backend/scripts/new_demo_credentials.ps1 ngoài checkout; walkthrough role và giới hạn finance/assistant/prototype được ghi rõ; sơ đồ/link tài liệu trỏ tới implementation hiện tại. | **Đạt local** |
| **V3-16 — Presentation/recovery** | Evidence pack tại phase-3/V3-16_PRESENTATION_EVIDENCE.md lưu lệnh và output. Kết quả cuối: frontend 55 unit pass; build 1,625 modules; assistant security 13 source/9 bundle; Golden Flow GF-01..08 pass; backend 295 pass/1 skip/2 warnings; Phase 3 disposable rehearsal pass. | **Đạt local, chưa phải production approval** |

### Bằng chứng và giới hạn V3-12..16

- [V3-16_PRESENTATION_EVIDENCE.md](phase-3/V3-16_PRESENTATION_EVIDENCE.md) chứa
  checklist demo/recovery, kết quả từng lệnh, screenshot đại diện, log và
  lỗi còn mở.
- Output lịch sử tại `phase-3/evidence/v3-16` được giữ trên máy local, không thuộc
  gói nộp vì log có thể chứa đường dẫn máy.
- Browser Golden Flow dùng API fixtures deterministic; persistence, scope,
  audit, idempotency và state transition lấy từ isolated PostgreSQL.
- Docker daemon không chạy trên máy kiểm tra nên compose startup/HTTPS smoke
  chưa được xác nhận. Hai deprecation warnings backend còn mở; không có formal
  Gate/production/independent-review claim.
- Outbox enqueue ghi một timestamp UTC cho DomainEvent và NotificationReadModel
  để snapshot as_of dùng cùng cutoff; isolated test đã pass sau thay đổi này.
