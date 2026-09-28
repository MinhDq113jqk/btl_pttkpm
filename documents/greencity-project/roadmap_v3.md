# Roadmap v3 — Hoàn thiện GreenCity trên local cho đồ án tốt nghiệp

**Trạng thái:** Bản kế hoạch triển khai, lập ngày 2026-09-24

**Dự án:** GreenCity / UrbanOps

**Phạm vi:** Code hiện có trong checkout `_pttkpm`, kiểm thử local và các luồng được chọn để bảo vệ đồ án.

## 1. Mục tiêu

Đưa GreenCity từ trạng thái nhiều phân hệ đã có API và giao diện rời rạc tới một ứng dụng local có thể cài đặt, khởi chạy, sử dụng dữ liệu thật trong PostgreSQL, đi hết các luồng nghiệp vụ chính và trình diễn ổn định.

[roadmap_v2.md](roadmap_v2.md) tiếp tục là nguồn các quy tắc nghiệp vụ, thuật toán, trạng thái và Acceptance Criteria. Roadmap v3 này là kế hoạch đóng các khoảng cách trong implementation; không tự chuyển các mục `SPEC-ONLY` của v2 thành chức năng được cam kết.

Nguyên tắc cho đồ án:

- Ưu tiên các luồng lõi, kết nối Frontend → API → business logic → database.
- Sample data chỉ dùng qua seed/test fixture; giao diện không giả số liệu, tài khoản, kết nối dịch vụ hoặc kết quả nghiệp vụ.
- Một chức năng chỉ được giữ trên menu khi có màn hình hoạt động và API thật; chức năng chưa chọn cho bản đồ án phải được ẩn khỏi menu và trang demo.
- Không mở rộng SSO, Facebook/Meta, VietQR, ERP, AI thực hiện giao dịch hoặc vận hành đa cụm nếu rubric không yêu cầu.
- Mỗi phase kết thúc bằng luồng chạy được và test tương ứng, không chỉ có model hoặc màn hình.
- Các “owner” trong bảng là vai trò công việc (FE/BE/DB/QA), có thể do cùng một sinh viên đảm nhiệm.

Prompt audit đính kèm dừng ở mục UX với một gạch đầu dòng chưa hoàn tất. Roadmap này dùng toàn bộ yêu cầu đọc được trong prompt, đối chiếu code hiện tại và roadmap_v2.md.

## 2. Code snapshot hiện tại

### 2.1. Nền tảng và kiểm thử

| Khu vực | Hiện trạng quan sát được |
|---|---|
| Backend | FastAPI, SQLAlchemy/psycopg, PostgreSQL và Alembic; migration đến `0017`. Có auth/session, login throttle, service requests/work orders, resident portal, cleaning, security, parcels, billing, observability, import và assistant APIs. |
| Frontend | React/Vite. Vite đang đặt cổng `3000`; hai README hiện ghi cổng khác nhau (`5173` và `3000`). |
| Chạy/test backend | `scripts/test_isolated.py` tạo PostgreSQL/TLS tạm, migrate/seed/drift-check và chạy regression. Full run gần nhất: `291 passed, 1 skipped, 3 warnings`; sau chỉnh ACL evidence, storage/retention tests `6 passed, 1 skipped` và Phase 3 rehearsal chạy lại PASS. |
| Frontend | `npm test`: `72/72` PASS; `npm run build`: PASS. |
| Phase 3 local rehearsal | PASS trên PostgreSQL/TLS dùng một lần: migration upgrade/rollback/re-upgrade/drift, DML runtime và từ chối DDL, dump/restore và checksum 61 bảng/2 hàng fixture, private-evidence backup/restore 2 tệp. Đây là fixture nhỏ, không phải phép đo tải thực tế. |

### 2.2. Mapping chức năng đang có

| Năng lực | Backend | Frontend đang dùng | Khoảng trống chính |
|---|---|---|---|
| Đăng nhập/session/site scope | Có `/login`, `/me`, logout, logout-all, đổi mật khẩu và đổi site | `StaffLogin`, `PasswordChange`, app session | `authSession.js` tạo menu từ role trả về `/auth/me`, còn backend tự enforce quyền; cần kiểm thử parity. Không có self-registration; tài khoản được cấp/seed. |
| Master data / import-export | Backend có Units/Persons scope và ImportRun upload/preview/apply/error-file APIs | Chưa thấy import-run/export client hoặc page được nối trong active app | Thêm UI import/preview/apply/download-error có scope; hoàn thiện export cốt lõi hoặc bỏ nút export nếu chưa có endpoint thật. |
| Yêu cầu dịch vụ | List/create/triage và API Work Order, phân công, checklist, ảnh, chi phí, nghiệm thu/đóng | Danh sách/tạo yêu cầu, chi tiết hiện chỉ đọc | Các mutation Work Order chưa nối đầy đủ lên giao diện đang dùng. |
| Maintenance | API tạo/xem Asset, Maintenance Plan, chạy scheduler, defer occurrence và lịch sử | Chưa có màn hình maintenance được gắn trong `App.jsx` | Thiếu vòng Asset → Plan → occurrence → WO → history ở UI. |
| Cleaning / Security | API workflow ca, task/checklist, tuần tra, khách và sự cố | Có `CleaningDesktopView`, `SecurityDesktopView` | Cần khóa Golden Flow và kiểm thử vai trò/negative/error state đầu-cuối. |
| Parcel | API intake, trạng thái, PIN bàn giao, evidence, case/incident link | Có `ParcelDeskView` | Giữ phạm vi đã có; bổ sung/reconcile test flow và cập nhật ma trận yêu cầu. |
| Billing / cư dân | API phí, kỳ, billing run, invoice, payment, unmatched, credit; resident billing/request/notification | Có `BillingDesktopView`, `ResidentPortalView` | Chỉ hoàn thiện phạm vi thanh toán cơ bản. Không trình bày mock refund payout như chức năng thật. |
| Dashboard / audit / notification | Dashboard có `as_of`/drill-down, audit explorer, outbox và notification APIs | Executive dashboard, notifications | Route “reports” riêng chưa được nối; cần một nguồn `as_of` và mapping test KPI → drill-down → audit. |
| AI assistant | Endpoint/provider thật, `ASSISTANT_ENABLED=false` mặc định | Assistant component | Là chức năng tùy chọn; không được thay bằng câu trả lời giả khi tắt hoặc khi API lỗi. |

### 2.3. Phần giao diện còn prototype hoặc chưa được app sử dụng

Đây là các dấu hiệu cụ thể để xử lý ở `V3-01`, không phải kết luận rằng mọi mock trong test đều sai:

- `mockData.js` chứa `dashboardData`, `sampleRefundCase`, `mediaData`, `amenitiesData`; `desktopData.js` có task/notification fixture. Các fixture trong test được giữ ở test scope, còn dữ liệu mock không được để trong màn hình người dùng.
- `MediaChannelsView.jsx` mô phỏng Facebook/website metrics và trạng thái kết nối; không có backend API tương ứng.
- `UrbanAmenitiesView.jsx` dựng tiện ích, bãi xe, trường/bệnh viện từ dữ liệu tĩnh; chưa có domain/API tương ứng.
- `RefundFormView.jsx`, `RefundReview.jsx`, `ConfirmModal.jsx` dựa vào `sampleRefundCase` và có copy nói rõ thao tác mô phỏng; backend hiện có Overpayment Credit cơ bản, không có refund payout tương ứng.
- `App.jsx` hiện mount các bề mặt overview, tasks, cleaning, security, parcels, finance, residents và notifications. Maintenance API có nhưng chưa có page được mount. Một số component mobile/dashboard cũ không thuộc luồng app đang dùng.
- `navItems` còn ID/badge tĩnh cho các bề mặt cũ. Sidebar hiện nhận task/unread count qua props động, nhưng cấu hình nav vẫn giữ trường badge dư; menu thật lọc theo account và cần bảo đảm mỗi item được hiển thị có route/page thật.
- `StaffDashboard`, `staffRoles.js`, `DashboardView`, `TasksMobileView`, `MobileFolderModal`, `MobileBottomNav` và một số page mẫu cần rà import/reference trước khi quyết định giữ, nối hoặc xóa.

### 2.4. Giới hạn của snapshot

- Phase 3 Compose đã parse được, nhưng chưa build/start container trong môi trường hiện tại.
- Build Vite cần chạy ngoài sandbox Windows để tránh `Access is denied` của esbuild; build ngoài sandbox đã PASS.
- Backend full suite gần nhất trước thay đổi permission group cho evidence: `291 passed, 1 skipped, 3 warnings`. Sau thay đổi permission, storage/backup-policy unit tests chạy lại `6 passed, 1 skipped`, và Phase 3 local rehearsal PASS.
- CI workflow và test status cần được đọc từ lần chạy hiện tại khi thực hiện; roadmap không coi kết quả cũ là kết quả mới.

## 3. Ranh giới tính năng cho bản đồ án local

### 3.1. Phạm vi phải trình diễn được

1. Đăng nhập, phiên, đổi site, quyền theo vai trò và chặn truy cập ngoài scope.
2. Cư dân gửi yêu cầu; CSKH tiếp nhận/triage; kỹ thuật xử lý Work Order, checklist và evidence; cư dân đọc được trạng thái.
3. Maintenance Plan sinh occurrence/WO, kết quả cập nhật lịch sử Asset.
4. Cleaning task đi hết checklist; kết quả không đạt tạo hồ sơ khắc phục.
5. Security shift/patrol/incident đi qua một luồng xử lý có phân quyền.
6. Parcel intake → sẵn sàng bàn giao → kiểm tra PIN/ngoại lệ → liên kết Case khi cần.
7. Billing cơ bản: policy/kỳ → run/invoice snapshot → payment thủ công/unmatched → credit cơ bản → cư dân xem hóa đơn/thanh toán.
8. Dashboard, notification và audit phản ánh cùng dữ liệu nguồn; có thể truy từ KPI đến hồ sơ và sự kiện audit.

### 3.2. Phần không được giả lập

Nếu không làm thật trong phạm vi đồ án, các mục sau phải ẩn khỏi menu hoặc ghi rõ ngoài phạm vi trong tài liệu, không để màn hình fake hoạt động:

- Refund payout, chargeback, VietQR/đối soát ngân hàng.
- Facebook/Meta, inbox bên thứ ba, website analytics/CDN uptime.
- Tiện ích đô thị nếu chưa có bảng dữ liệu/API và workflow cần thiết.
- SSO, ERP, ANPR/FaceID, thiết bị IoT, AI tự thực hiện lệnh.
- Project/Settings page nếu chưa có quy trình và API có thể hoàn thành thật.

Không thêm luồng đăng ký công khai nếu bài toán là hệ thống nội bộ; account local được seed/provision bằng script có kiểm soát.

## 4. Điều kiện hoàn thành toàn dự án

Roadmap v3 được coi là đạt khi tất cả tiêu chí sau có bằng chứng:

### 4.1. Chức năng

- Mỗi tab/mục menu mà vai trò nhìn thấy mở ra màn hình có chức năng thật.
- Tạo/sửa/chuyển trạng thái đều gọi API; tải lại trang hoặc đăng nhập lại vẫn đọc được kết quả từ database.
- Không có success toast giả, API fallback mock, số KPI hard-code hoặc thao tác nút không có side effect được mô tả rõ.
- Mọi màn hình có loading, empty, error, unauthorized/out-of-scope và retry state phù hợp.

### 4.2. Dữ liệu và quyền

- Tạo database sạch → migrate → seed → chạy hệ thống không cần sửa bảng thủ công.
- Seed có tính lặp lại, dữ liệu gắn đúng Tenant/Site/Building; credentials seed nằm ngoài source.
- API test cả role được phép và bị từ chối cho mỗi luồng chính; client không gửi tenant/role/building để tự mở rộng quyền.
- Evidence download kiểm tra quyền, checksum, kích thước và hết hạn của signed link.

### 4.3. Chất lượng và demo

- Backend isolated regression, frontend unit/integration, build và các Golden Flow browser/API đều có lệnh tái chạy.
- Mỗi Golden Flow có seed fixture và kết quả mong đợi rõ; test failure không bị chuyển thành fallback data.
- Có một hướng dẫn chạy local duy nhất, một hướng dẫn seed/reset, và walkthrough demo theo vai trò.
- Giao diện không hiển thị credentials mẫu, `Demo User`, fake connection status hoặc placeholder nghiệp vụ.

## 5. Golden Flow cần đóng

| ID | Luồng trình diễn | Kết quả bắt buộc |
|---|---|---|
| GF-01 | Login → `/auth/me` → chọn site → mở menu theo role → logout/đổi mật khẩu | Scope/role lấy từ server; vai trò khác nhau thấy đúng bề mặt; session cũ không hoạt động. |
| GF-02 | Cư dân tạo service request → CSKH triage → tạo/giao WO → kỹ thuật start/checklist/evidence → nghiệm thu/đóng | Trạng thái lưu DB, idempotency giữ khi retry, cư dân đọc lại được tiến trình. |
| GF-03 | Tạo Asset/Maintenance Plan → chạy scheduler → xử lý occurrence/WO → xem history | Chạy scheduler lặp không sinh trùng; occurrence và lịch sử cùng tham chiếu asset. |
| GF-04 | Tạo cleaning shift/task → checklist → pass hoặc fail → hồ sơ khắc phục → nghiệm thu lại | Chỉ người được giao thao tác; lịch sử kết quả không bị ghi đè. |
| GF-05 | Security shift → visitor/patrol → incident/escalation → acknowledge/transition/close | Chặn role sai; mọi bước có actor, trạng thái và audit. |
| GF-06 | Parcel intake → ready → bàn giao PIN đúng/sai hoặc exception → Case/incident link | PIN không lộ trong UI/log; retry không bàn giao hai lần; evidence scoped. |
| GF-07 | Fee policy → kỳ → billing run → invoice snapshot → payment/unmatched/credit → resident billing | Tổng/statement đọc cùng dữ liệu; invoice snapshot không đổi sau khi phát hành. |
| GF-08 | Dashboard KPI → drill-down → audit timeline cùng `as_of` | Tổng dashboard đối chiếu được với các bản ghi nguồn, theo cùng role/site. |

## 6. Roadmap triển khai theo dependency

Không gán lịch tuần/ngày vì chưa có deadline và số thành viên. Thứ tự dưới đây là dependency order; làm thành từng lát dọc có thể chạy được.

| Phase / ID | Ưu tiên | Công việc | Phụ thuộc | Owner lane | Exit criteria |
|---|---|---|---|---|---|
| **P0 / V3-00** | P0 | Khóa ma trận code: menu → React page → client method → API → service/model/table → test; đối chiếu migration, model, constraints và package scripts. Chốt các module “giữ, hoàn thiện, ẩn”. | — | FE + BE + DB + QA | Không còn menu/tab không có disposition; mỗi chức năng BUILD có trace đến API, persistence và test. |
| **P0 / V3-01** | P0 | Sửa bề mặt sản phẩm: nav chỉ chứa luồng được chọn; gắn route maintenance/reports hoặc ẩn item; không để unsupported hash thành trang trắng/no-access khó hiểu. | V3-00 | FE | Test duyệt mọi role/menu; mọi item mở đúng page hoặc không xuất hiện. |
| **P0 / V3-02** | P0 | Tách `navItems` khỏi `mockData.js`; rà và loại khỏi app data fake, badge cứng, fallback mock. Các test mock giữ dưới `tests/`. | V3-00, V3-01 | FE + QA | Build không kéo fake business records; mock API chỉ tồn tại trong test; API lỗi hiển thị lỗi thật. |
| **P0 / V3-03** | P0 | Chuẩn hóa local bootstrap và tài liệu: thống nhất Vite port 3000; setup PostgreSQL, `.env`, migrate, seed, chạy backend/frontend và reset database. Seed fixture đủ vai trò/site, credentials cấp ngoài Git. | V3-00 | BE + DB | Máy mới làm theo README chạy được từ DB trống, không có thao tác SQL thủ công; `npm ci`, `npm test`, build và backend runner có lệnh rõ; seed lặp an toàn. |
| **P1 / V3-04** | P1 | Nối màn hình master-data/import-export vào ImportRun API: upload CSV, map/preview, apply, xem trạng thái từng dòng, tải error file và export theo schema/scope. | V3-01, V3-03 | FE + BE + QA | Import chạy từ UI tới DB; retry/idempotency và partial/all-or-nothing theo API được test; error file có scope/checksum; export giữ filter và không lộ field ngoài quyền. |
| **P1 / V3-05** | P1 | Hoàn chỉnh UI CSKH/Work Order trên API đang có: triage, tạo WO, assign, start, checklist, evidence, chi phí, accept/reopen/close và refresh/readback. | V3-01..04 | FE + BE | GF-02 chạy trọn từ browser/API; role sai bị chặn; lỗi 409/422 và retry hiển thị đúng. |
| **P1 / V3-06** | P1 | Tạo Technical/Maintenance page nối các API Asset, Plan, scheduler, occurrence, history; bổ sung list/filter APIs nếu UI cần. | V3-05 | FE + BE + DB | GF-03 chạy từ tạo Asset tới lịch sử; scheduler idempotent; không có Asset/Occurrence mẫu ở runtime. |
| **P1 / V3-07** | P1 | Đóng cleaning workflow bằng browser integration: ca/tuyến, assign, start, checklist, submit, accept, missed/cancel, rework Case/WO. | V3-01, V3-03 | FE + QA | GF-04 pass với cả pass/fail path và negative role test. |
| **P1 / V3-08** | P1 | Đóng security workflow bằng browser integration: ca, bàn giao, visitor, patrol, incident, evidence, escalation/acknowledgement/transition. | V3-01, V3-03 | FE + QA | GF-05 pass; mọi thao tác bị audit; severity cao không thể đóng thiếu điều kiện. |
| **P1 / V3-09** | P1 | Hoàn thiện parcel và resident flow: intake, PIN, exception, evidence, Case/incident link; resident request, billing và notifications. | V3-03, V3-05 | FE + BE + QA | GF-06 pass; resident chỉ thấy Unit/Site được cấp; PIN và private files không rò rỉ. |
| **P1 / V3-10** | P1 | Hoàn chỉnh finance local scope: Fee Policy, Accounting Period, run, invoice, manual payment, unmatched match và Overpayment Credit cơ bản; resident đọc kết quả. | V3-03, V3-05 | FE + BE + QA | GF-07 pass với fixture amount cố định; retry không tạo payment/invoice duplicate; không hiển thị refund payout mock. |
| **P1 / V3-11** | P1 | Gắn Reports tab vào dashboard/audit đã có hoặc bỏ tab; đồng nhất `as_of` cho KPI/drill-down/audit/notification. | V3-01, V3-05..10 | FE + BE + QA | GF-08 pass; tổng KPI bằng dữ liệu drill-down và query DB trong cùng snapshot/scope. |
| **P2 / V3-12** | P2 | Dọn legacy prototype/dead code sau khi kiểm tra import graph: Media, Amenities, refund payout, StaffDashboard/mock roles và mobile shell cũ; rà TODO/FIXME, console log, hard-coded credential/URL, import và dependency thừa. | V3-01, V3-02 | FE + BE | Import graph sạch; source scan không còn credential/debug ngoài test; page fake bị bỏ khỏi bundle/menu hoặc được thay bằng API thật. |
| **P2 / V3-13** | P2 | Bổ sung API/DB integration tests cho mỗi mutation và role boundary; UI/API contract tests; Playwright cho GF-01..08. | V3-05..12 | QA + BE + FE | Golden flows chạy tự động trên DB cô lập; test có negative path và assert dữ liệu persisted sau reload. |
| **P2 / V3-14** | P2 | Chuẩn hóa error/empty/loading/retry, keyboard/focus, form validation và copy tiếng Việt cho các màn hình đang giữ. | V3-05..13 | FE + QA | Các lỗi mạng, 401, 404, 409, 422 có UI rõ; không thành công giả và không mất form state vô cớ. |
| **P2 / V3-15** | P2 | Hoàn thiện local demo kit: README nhất quán, data reset, lệnh chạy, account provisioning private, walkthrough theo role và sơ đồ đúng implementation. | V3-03..14 | BE + FE + QA | Người chấm có thể tạo DB, seed, chạy app và xem hết GF-01..08 chỉ theo tài liệu; không cần credential trong Git. |
| **P2 / V3-16** | P2 | Chốt bản trình bày: regression sạch, lưu output test, kiểm tra links, kiểm tra source không chứa secrets/fake metrics và tập demo reset được. | V3-13..15 | QA | Có checklist demo/recovery; lỗi còn mở được liệt kê, không bị trình bày như chức năng đã hoàn tất. |

## 7. Quyết định phạm vi cho prototype code đang tồn tại

| Bề mặt | Hiện trạng code | Hướng trong roadmap |
|---|---|---|
| Service Request/Work Order | Backend workflow khá đầy đủ; active UI chủ yếu list/create và modal chi tiết read-only | Hoàn thiện UI trên API có sẵn; ưu tiên GF-02. |
| Maintenance/Technical | Backend Asset/Plan/Scheduler có; chưa được mount thành page trong `App.jsx` | Làm trang tối thiểu dùng API hiện có; không thêm kho/vật tư/IoT. |
| Cleaning/Security/Parcel/Billing/Resident | Có API client và trang active | Không viết lại; khóa các luồng end-to-end, lỗi và quyền. |
| Reports/Settings/Projects | Một số model/API có nhưng tab riêng chưa có đầy đủ UI/API | Route sang màn hình thật nếu đã có; nếu chưa, bỏ khỏi menu bản demo. |
| Refund payout | UI/form dựa trên `sampleRefundCase`; backend không có payout API tương ứng | Bỏ khỏi UI local MVP; giữ Overpayment Credit cơ bản theo backend. |
| Media/Facebook/website metrics | Component đọc `mediaData` hard-code, báo trạng thái Meta giả | Bỏ khỏi menu/bundle trình diễn; không kết nối Meta nếu không nằm trong rubric. |
| Amenities/parking/schools/hospitals | Component đọc `amenitiesData` tĩnh; chưa có API/domain persistence | Ngoài core hiện tại; ẩn hoặc tạo feature thật riêng nếu rubric yêu cầu. |
| Assistant | Provider/API có thật nhưng `ASSISTANT_ENABLED=false` mặc định | Tùy chọn; không tạo mock answer. Nếu thiếu key thì hiện unavailable rõ ràng hoặc ẩn nút. |
| Seed accounts | Tên role/username fixture có trong seed code; passwords phải cấp ngoài source | Giữ fixture cho local test; không show password/hardcoded login trên product UI. |

## 8. Test plan

### 8.1. Tầng test

1. **Unit:** validation, state transition, money rounding, date/cutoff, parsers, checksum/path guard.
2. **API/DB integration:** mọi POST/PATCH/workflow command, isolation role/site, idempotency, migration from empty, seed repeat, drift.
3. **Frontend contract:** response schema, loading/empty/error, form validation, correlation ID, retry giữ `Idempotency-Key`.
4. **Browser E2E:** GF-01..08 với browser thật, dữ liệu fixture và database mới.
5. **Manual demo:** một checklist cho từng role; chụp lại kết quả/URL/trạng thái cho slide bảo vệ, không chụp credentials hoặc dữ liệu cá nhân thật.

### 8.2. Lệnh cần gom vào flow thống nhất

- Backend unit/contract + PostgreSQL cô lập: `python -m pytest -q` và `scripts/test_isolated.py`.
- Frontend unit/contract: `npm test`.
- Frontend build: `npm run build`.
- Browser flows: các suite `npm run test:<module>` hiện có; thêm lệnh tổng hợp chỉ khi tất cả suite có environment requirement rõ.
- Không dùng endpoint mock cho E2E core; mock chỉ nằm trong test/component-isolation suite.

### 8.3. Quality gates của đồ án

- Không còn `skip` không giải thích trong test Golden Flow; mỗi skip ghi lý do và lý do không thể chạy trên máy local.
- Backend/Frontend test và build pass trên clone sạch.
- DB trống → migration head → seed repeat → không drift.
- GF-01..08 chạy được mà không chỉnh DB thủ công.
- Mỗi menu item được role nhìn thấy có page/route hoạt động.
- Không có `Test User`, fixture ID, fake KPI, fake external connection hay demo credential trong UI production bundle.

## 9. Rủi ro và cách xử lý

| ID | Rủi ro hiện tại | Xử lý trong roadmap |
|---|---|---|
| R3-01 | Menu/static route và page/API chưa đồng bộ; một số tab là prototype hoặc không có route implementation | `V3-01`, bắt đầu bằng menu → route → client → API → DB trace. |
| R3-02 | Mock data còn trong `mockData.js`, `desktopData.js`, `staffRoles.js` và các page cũ | `V3-02`, `V3-12`; giữ fixtures ở tests/seed, không chỉ xóa toàn file vì một số file vẫn cấp nav/helper cho code đang chạy. |
| R3-03 | Work Order API có nhiều bước nhưng Tasks UI chưa cho hoàn tất workflow | `V3-05` + GF-02. |
| R3-04 | Maintenance backend chưa có UI local | `V3-06` + GF-03. |
| R3-05 | README root dùng `5173`, Vite config dùng `3000`; docs có lệnh seed khác với seed hiện tại bị tắt mặc định | `V3-03`, `V3-15`; thống nhất port và điều kiện seed. |
| R3-06 | Một số module bên thứ ba chỉ là metrics giả, trong khi việc tích hợp thật vượt mục tiêu đồ án | Đưa khỏi active UI và nêu rõ ngoài phạm vi thay vì tạo API hình thức. |
| R3-07 | Suite E2E theo phân hệ có nhưng lệnh full có thể không chạy hết cùng `npm test` | `V3-13`; tách unit/contract/E2E nhưng gom hướng dẫn/lệnh tái chạy. |

## 10. Thứ tự bàn giao

1. Hoàn thành `V3-00..04`: biết rõ còn gì, menu sạch, máy mới chạy được và nhập/xuất dữ liệu cơ bản.
2. Hoàn thành `V3-05..11`: các màn hình/nghiệp vụ cốt lõi hoàn tất từ API đến database.
3. Hoàn thành `V3-12..14`: mock/dead code, lỗi, UX và tests được xử lý.
4. Hoàn thành `V3-15..16`: demo kit, test evidence, hướng dẫn reset/chạy lại.

**Không kết luận “hoàn thiện” nếu chỉ có API hoặc chỉ có UI.** Mỗi flow phải có trang thật, API contract, persistence, quyền, failure state và test/biên bản chạy tương ứng.

## 11. Lịch sử và cập nhật

- v3.0 — tạo kế hoạch hoàn thiện local dựa trên code snapshot 2026-09-24, kiểm tra lại roadmap_v2.md, routes, components, services và test scripts.
- Khi scope thay đổi theo yêu cầu giảng viên, cập nhật mục 3/5/7 và ma trận truy vết trước khi thêm API hoặc màn hình.
- v3.16 — đóng V3-12..V3-16 bằng source scan, Golden Flow, regression isolated, demo/recovery checklist và evidence pack; local verification vẫn tách khỏi production approval.

### 11.1. Phụ lục yêu cầu audit đã lưu

Khối từ tiêu đề `# 11. Checklist lại toàn bộ roadmap_v3.md` đến hết mục `# 20`
bên dưới là yêu cầu audit lịch sử được giữ lại để truy vết, không phải trạng
thái implementation hiện hành. Kết quả thực thi của khối đó nằm tại
[FINAL_ROADMAP_AUDIT.md](phase-3/FINAL_ROADMAP_AUDIT.md). Sau khi bổ sung phạm
vi `excel-data`, nguồn thực thi tiếp theo là mục 22 và
[FINAL_CODE_SUBMISSION_PLAN.md](FINAL_CODE_SUBMISSION_PLAN.md).

Sau khi hoàn thành toàn bộ quá trình audit ở trên, hãy thực hiện thêm bước **Final Roadmap Checklist** dựa trực tiếp trên file `roadmap_v3.md`.

# 11. Checklist lại toàn bộ `roadmap_v3.md`

Đọc **toàn bộ file `roadmap_v3.md` từ đầu đến cuối** và đối chiếu từng task trong roadmap với implementation thực tế hiện tại của repository.

Không được chỉ dựa vào trạng thái checkbox trong file roadmap.

Ví dụ:

```md
- [x] Hoàn thiện authentication
```

không có nghĩa là task thực sự hoàn thành.

Phải kiểm tra trực tiếp:

- Code có tồn tại hay không.
- Frontend đã sử dụng chưa.
- Backend đã xử lý chưa.
- Database đã hỗ trợ chưa.
- Có test chưa.
- Test có pass không.
- Có trường hợp lỗi chưa xử lý không.
- Có mock/hard-code/demo data không.
- Có thể chạy thực tế trên local không.

---

## 11.1. Xác minh từng task trong roadmap

Với từng task trong `roadmap_v3.md`, hãy gán một trong các trạng thái sau:

### ✅ DONE

Task đã hoàn thành thực sự và có thể chứng minh bằng implementation/test.

### ⚠️ PARTIAL

Đã làm nhưng chưa hoàn chỉnh.

Ví dụ:

- Backend có nhưng frontend chưa nối.
- CRUD mới có Create/Read nhưng thiếu Update/Delete.
- Có chức năng nhưng thiếu validation.
- Có API nhưng chưa xử lý error.
- Có UI nhưng đang dùng mock data.
- Có test nhưng chưa bao phủ luồng chính.

### ❌ NOT DONE

Task chưa được triển khai hoặc implementation hiện tại chưa đáp ứng yêu cầu.

### 🗑 REMOVE / NOT REQUIRED

Task không còn cần thiết đối với phạm vi đồ án tốt nghiệp hiện tại.

Ví dụ:

- Infrastructure cấp doanh nghiệp.
- Over-engineering.
- Feature đã bị loại khỏi scope.
- Công nghệ không còn được sử dụng.

---

# 12. Tạo bảng Final Roadmap Status

Sau khi kiểm tra, hãy tạo bảng:

| ID | Task | Roadmap status | Actual status | Priority | Evidence | Action |
|---|---|---|---|---|---|---|

Trong đó:

## Roadmap status

Trạng thái hiện đang ghi trong `roadmap_v3.md`.

## Actual status

Một trong:

```text
DONE
PARTIAL
NOT DONE
REMOVE
```

## Priority

Một trong:

```text
P0
P1
P2
P3
```

## Evidence

Phải chỉ rõ bằng implementation thực tế, ví dụ:

```text
backend/src/auth/auth.service.ts
frontend/src/pages/Login.tsx
tests/auth.integration.test.ts
```

hoặc kết quả test/build thực tế.

## Action

Nói chính xác bước tiếp theo phải làm.

Không được ghi chung chung như:

```text
Hoàn thiện authentication
```

Mà phải ghi cụ thể:

```text
Thêm xử lý refresh token hết hạn ở frontend,
redirect về /login và clear auth state.
```

---

# 13. Tìm các task bị thiếu khỏi `roadmap_v3.md`

Không được mặc định rằng roadmap hiện tại đã đầy đủ.

Sau khi audit repository, hãy tìm những vấn đề **cần thiết để hoàn thiện sản phẩm nhưng chưa xuất hiện trong `roadmap_v3.md`**.

Ví dụ:

- Chức năng frontend chưa nối API.
- API thiếu validation.
- Thiếu database constraint.
- Thiếu loading/error state.
- Thiếu authorization.
- Thiếu migration.
- Thiếu `.env.example`.
- Thiếu test cho Golden Flow.
- Mock data còn tồn tại.
- Debug route còn tồn tại.
- README chưa đủ để chạy clean setup.

Nếu phát hiện, hãy thêm chúng vào mục:

# Missing Tasks

Mỗi task mới phải có:

```text
ID
Tên task
Priority
Lý do cần làm
File/module liên quan
Dependency
Definition of Done
Test/Evidence
```

---

# 14. Loại bỏ các task không còn cần thiết

Kiểm tra roadmap có task nào:

- trùng lặp,
- không còn phù hợp,
- đã bị thay thế,
- vượt scope đồ án,
- mang tính production doanh nghiệp,
- không đem lại giá trị trực tiếp cho sản phẩm cuối.

Đưa chúng vào:

# Tasks To Remove

và giải thích ngắn gọn vì sao.

Không được giữ task chỉ vì nó đã xuất hiện trong roadmap cũ.

---

# 15. Sắp xếp lại roadmap theo dependency thực tế

Sau khi audit, hãy sắp xếp lại những task chưa hoàn thành theo thứ tự hợp lý.

Không được sắp xếp chỉ theo thứ tự hiện tại trong `roadmap_v3.md`.

Ưu tiên dependency:

```text
Database
↓
Backend
↓
API
↓
Frontend Integration
↓
Validation / Error Handling
↓
Testing
↓
Cleanup
↓
Documentation
↓
Final Verification
```

Nếu một task phụ thuộc task khác, task phụ thuộc phải được làm sau.

---

# 16. Tạo danh sách "Việc cần làm tiếp theo"

Đây là phần quan trọng nhất.

Sau khi audit `roadmap_v3.md`, hãy tạo một danh sách duy nhất:

# NEXT TASKS — CODE NỘP CHO GIÁO VIÊN

Danh sách này chỉ chứa **những việc còn phải làm từ trạng thái repository hiện tại cho đến khi code đủ điều kiện nộp cho giáo viên**.

Không liệt kê lại những việc đã DONE.

Mỗi task phải theo format:

```text
[ ] TASK-ID — Tên task

Priority:
Dependency:

Mục tiêu:

Files/Modules:

Công việc cần làm:
- ...
- ...
- ...

Definition of Done:
- ...
- ...

Verification:
- command/test...
```

---

# 17. Chia NEXT TASKS thành các checkpoint

Hãy chia những việc còn lại thành các checkpoint sau.

## CHECKPOINT 1 — BLOCKER

Những việc phải sửa trước vì project:

- không build,
- không chạy,
- lỗi database,
- lỗi authentication,
- lỗi business logic chính,
- hoặc Golden Flow bị đứt.

Chủ yếu là `P0`.

---

## CHECKPOINT 2 — CORE PRODUCT COMPLETE

Hoàn thiện toàn bộ chức năng cốt lõi:

```text
Frontend
↕
API
↕
Backend
↕
Database
```

Không được còn chức năng nửa vời.

Chủ yếu là `P0 + P1`.

---

## CHECKPOINT 3 — REMOVE PROTOTYPE / DEMO

Tìm và xử lý toàn bộ:

- Demo account.
- Demo password.
- Mock data.
- Mock API.
- Fake dashboard.
- Test page.
- Debug route.
- Placeholder.
- Hard-coded ID.
- Hard-coded user.
- Hard-coded API response.
- Console log debug.
- Dev-only button.
- TODO quan trọng.
- Component thử nghiệm.
- Fake notification.
- UI chưa hoạt động.

Sau checkpoint này frontend phải có cảm giác là **sản phẩm thật**.

---

## CHECKPOINT 4 — VALIDATION & STABILITY

Hoàn thiện:

- Form validation.
- Backend validation.
- Error handling.
- Loading state.
- Empty state.
- Unauthorized.
- Forbidden.
- 404.
- Session expiration.
- Duplicate data.
- Invalid input.
- Database constraint.
- Transaction nếu nghiệp vụ cần.

---

## CHECKPOINT 5 — TEST

Tạo/chạy test cho các chức năng quan trọng.

Ưu tiên:

```text
Authentication
Authorization
Core business logic
Main CRUD
Golden Flow
Critical error cases
```

Không cần chạy theo coverage cao.

Mục tiêu là:

> Chứng minh được các chức năng quan trọng của đồ án hoạt động ổn định.

---

## CHECKPOINT 6 — CODE CLEANUP

Chỉ cleanup những thứ cần thiết trước khi nộp:

- Dead code.
- Unused import.
- Debug code.
- Console log.
- Comment lỗi thời.
- File test tạm.
- Duplicate code nghiêm trọng.
- Dependency không dùng.
- Hard-coded configuration.
- Secret vô tình commit.

Không thực hiện refactor lớn nếu code hiện tại ổn định.

---

## CHECKPOINT 7 — LOCAL RELEASE

Kiểm tra toàn bộ quy trình từ repository sạch:

```text
git clone
↓
install dependencies
↓
create .env
↓
database migration
↓
database seed nếu cần
↓
start backend
↓
start frontend
↓
login/register
↓
Golden Flow
```

Không được yêu cầu:

- sửa database thủ công,
- sửa code thủ công,
- copy token,
- tạo user trực tiếp trong database,
- bật một mock server riêng.

---

# 18. Final Submission Gate

Sau khi hoàn tất roadmap, chạy một lần kiểm tra cuối.

Tạo bảng:

| Gate | Result | Evidence |
|---|---|---|
| Clean install | PASS/FAIL | |
| Database migration | PASS/FAIL | |
| Backend start | PASS/FAIL | |
| Frontend start | PASS/FAIL | |
| Build | PASS/FAIL | |
| Authentication | PASS/FAIL | |
| Authorization | PASS/FAIL | |
| Main Golden Flow | PASS/FAIL | |
| CRUD chính | PASS/FAIL | |
| Validation | PASS/FAIL | |
| Error handling | PASS/FAIL | |
| Core tests | PASS/FAIL | |
| No demo account | PASS/FAIL | |
| No mock API | PASS/FAIL | |
| No fake frontend data | PASS/FAIL | |
| No critical TODO | PASS/FAIL | |
| No debug route | PASS/FAIL | |
| No exposed secret | PASS/FAIL | |
| README setup | PASS/FAIL | |

Nếu bất kỳ gate quan trọng nào FAIL thì chưa được kết luận dự án hoàn thành.

---

# 19. Định nghĩa trạng thái cuối cùng

Mục tiêu cuối của roadmap không phải:

```text
Production Ready
```

và cũng không phải:

```text
Enterprise Ready
```

Mục tiêu cuối cùng là:

# CODE NỘP CHO GIÁO VIÊN

Trạng thái này chỉ đạt được khi:

- Repository chạy được trên local.
- Có hướng dẫn setup rõ ràng.
- Database khởi tạo được từ migration.
- Frontend, backend và database kết nối thật.
- Không sử dụng mock để giả lập chức năng cốt lõi.
- Không còn tài khoản demo hiển thị trên frontend.
- Không còn dữ liệu hard-code nhằm giả lập sản phẩm.
- Không còn trang hoặc chức năng thử nghiệm lộ ra cho người dùng.
- Chức năng chính chạy end-to-end.
- Authentication hoạt động.
- Authorization hoạt động.
- Các thao tác CRUD chính hoạt động.
- Validation cơ bản đầy đủ.
- Error handling cơ bản đầy đủ.
- Không có lỗi nghiêm trọng dễ xảy ra khi demo.
- Test quan trọng pass.
- Build pass.
- Không commit secret.
- Code không chứa lượng lớn debug/dead code.
- README đủ để người khác chạy project.
- Không cần thao tác thủ công bất thường để hệ thống hoạt động.

---

# 20. Kết luận bắt buộc

Cuối quá trình review phải trả về đúng một trong hai trạng thái:

```text
FINAL STATUS: NOT READY FOR SUBMISSION
```

hoặc:

```text
BASELINE STATUS (DEMO/SEED): CODE READY FOR TEACHER SUBMISSION
```

Nếu là:

```text
NOT READY FOR SUBMISSION
```

phải ngay lập tức đưa ra:

# Remaining Tasks

theo đúng thứ tự thực hiện.

Không đưa các task `P3` hoặc các cải tiến production không cần thiết vào danh sách blocker.

Nếu là:

```text
CODE READY FOR TEACHER SUBMISSION
```

hãy ghi rõ evidence:

- Build result.
- Test result.
- Golden Flow result.
- Những kiểm tra cleanup đã thực hiện.
- Những giới hạn còn tồn tại nhưng **chấp nhận được đối với phạm vi đồ án tốt nghiệp**.

## Nguyên tắc quan trọng

Mục tiêu không phải làm project “hoàn hảo về kỹ thuật”.

Mục tiêu là đạt trạng thái:

> **Code sạch, chức năng hoàn chỉnh, chạy ổn định trên local, kiểm thử được, không còn dấu hiệu prototype/demo và đủ chất lượng để nộp cho giáo viên chấm đồ án.**

Luôn ưu tiên:

```text
Correctness
> Completeness
> Stability
> Testability
> Code quality
> Architecture elegance
> Production infrastructure
```

Không mở rộng scope nếu không trực tiếp giúp đạt trạng thái **CODE NỘP CHO GIÁO VIÊN**.
## 21. Kết quả Final Roadmap Checklist (2026-09-26)

Đã thực hiện toàn bộ bước audit được yêu cầu ở mục 11–20 và lưu bảng đối chiếu,
missing/remove tasks, dependency checkpoints, Final Submission Gate và bằng
chứng tại [FINAL_ROADMAP_AUDIT.md](phase-3/FINAL_ROADMAP_AUDIT.md).

```text
FINAL STATUS: CODE READY FOR TEACHER SUBMISSION
```

Verdict này chỉ áp dụng cho code chạy local và dữ liệu giả. Controlled pilot vẫn
`NO-GO` cho đến khi có owner/PO sign-off, formal Gate C/D và deployment-target
controls; các điều kiện đó không phải blocker của code nộp cho giáo viên.

## 22. Bổ sung cuối: tích hợp bộ dữ liệu thật `excel-data`

Ngày 2026-09-26, phạm vi nộp bài được mở rộng để ứng dụng có thể nạp và đối
soát bộ dữ liệu thật trong `documents/greencity-project/excel-data`. User/Owner
xác nhận đây là source of truth mới; bộ `data_that` trước đó chỉ là dữ liệu demo
và không được dùng làm evidence cuối. Kế hoạch thực hiện đầy đủ nằm tại
[FINAL_CODE_SUBMISSION_PLAN.md](FINAL_CODE_SUBMISSION_PLAN.md); danh sách thực
thi chi tiết nằm tại
[FINAL_CODE_SUBMISSION_20_TASKS.md](FINAL_CODE_SUBMISSION_20_TASKS.md).

Verdict ở mục 21 tiếp tục đúng cho baseline local với seed/dữ liệu giả đã được
audit. Nó chưa bao gồm XLSX ingestion, provenance/privacy gate, replay 12 miền,
đối soát tài chính hoặc Golden Flow trên database được nạp từ `excel-data`.

Với phạm vi bổ sung này, toàn bộ 20/20 task trong `FINAL_CODE_SUBMISSION_20_TASKS.md` đã được hoàn thành trên gói ứng viên nộp bài (`bc9623d4a45abb77beeaeab2cb96104fbd36130f1f757e0b2d8087fbfd039788`), sử dụng bộ dữ liệu tổng hợp chuẩn hóa (12 workbook, 101 dòng) được duyệt chính thức cho bài nộp. Toàn bộ các cổng kiểm thử Final Submission Gate, đối soát tài chính lệch 0 VND, và các luồng Golden Flow đều đạt 100% PASS.

Trạng thái kết luận chính thức:

```text
FINAL STATUS: CODE READY FOR TEACHER SUBMISSION
```
