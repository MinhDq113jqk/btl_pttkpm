# BÁO CÁO ĐÁNH GIÁ TIẾN ĐỘ DỰ ÁN GREENCITY — REVIEW 3

> **Addendum 13/09/2026 — snapshot lịch sử:** Các số liệu/nhận định bên dưới
> phản ánh Review 3 ngày 12/09 và không phải trạng thái source hiện tại. Runner
> mới nhất đã đạt head `0006`, migration `0005 -> 0006 -> 0005`, migration/seed
> repeat, schema drift và 184 test PostgreSQL local. Import JSON cũ đã được thay
> bằng CSV ImportRun trong contract hiện hành. AC-03 Review #1 timeout; AC-02/24
> Review #1 và #2 `NEEDS_REVISION`, sau đó code được test lại nhưng không có
> review vòng 3; xem `backend/VALIDATION.md` và `checklist.md` để theo dõi trạng
> thái `[-]`. Không dùng addendum này để tuyên bố Gate/release/production.

* **Thời điểm đánh giá:** 12/09/2026
* **Tài liệu đối chiếu:** [`roadmap_v2.md`](file:///C:/Users/LEGION/btl/_pttkpm/roadmap_v2.md) (Master Baseline v2.0), [`R2_CONTRACT.md`](file:///C:/Users/LEGION/btl/_pttkpm/backend/R2_CONTRACT.md), [`RBAC_R1.md`](file:///C:/Users/LEGION/btl/_pttkpm/backend/RBAC_R1.md), [`STAFF_WORKSPACE.md`](file:///C:/Users/LEGION/btl/_pttkpm/greencity-app/STAFF_WORKSPACE.md), [`backend/VALIDATION.md`](file:///C:/Users/LEGION/btl/_pttkpm/backend/VALIDATION.md)
* **Phương pháp kiểm chứng khách quan:**
  * **Backend:** Kiểm thử tự động trên cụm PostgreSQL 18.4 cô lập thông qua [`scripts/test_isolated.py`](file:///C:/Users/LEGION/btl/_pttkpm/backend/scripts/test_isolated.py) với **173/173 tests PASS**, head `0005`, migration/seed repeat và không schema drift ở lần chạy gần nhất.
  * **Frontend:** Kiểm thử Node native (`npm test`) với **50/50 tests PASS**; smoke UI staff **27 checks PASS** với API response được kiểm soát.
  * **Frontend Production Build:** Vite build thành công trong **23.34s**, không lỗi cú pháp hoặc import.
  * **Antigravity:** Unit 360° và AC-24 đã kết thúc đúng two-pass với `STATUS: PASS`. Review #1 của AC-02, AC-03 và AC-35 timeout với trạng thái remote không xác định; không tự retry, các lát này vẫn `[-]` và chưa stage.

---

## 1. Tóm tắt kết quả đã kiểm chứng local

Trong phiên làm việc vừa qua, dự án đã nối được lát cắt backend/frontend đọc-only và kiểm chứng trên môi trường local:

1. **Khép kín Lát cắt Đọc danh sách Service Request trên Backend (`GET /api/v1/service-requests`):**
   - Đã hiện thực hóa endpoint [`GET /api/v1/service-requests`](file:///C:/Users/LEGION/btl/_pttkpm/backend/app/api/service_requests.py) theo đúng cam kết hợp đồng.
   - **Cưỡng chế phân quyền đa tầng tại tầng truy vấn SQL:**
     - CSKH & Trưởng kỹ thuật: Chỉ xem được các yêu cầu thuộc các tòa nhà mà tài khoản được cấp quyền quản lý trong active site (`building_id IN (:user_building_ids)`).
     - Kỹ thuật viên (KTV): Triệt để áp dụng chính sách **`assigned-only`** thông qua câu truy vấn con `EXISTS (SELECT 1 FROM work_orders WHERE work_order.service_request_id = service_requests.id AND work_order.assigned_to_id = :account_id)`. KTV hoàn toàn không thấy các yêu cầu mà mình không được giao việc.
     - Ban Giám đốc & Quản trị viên: Xem toàn bộ yêu cầu trong active site.
     - Các vai trò ngoài ma trận (`cleaning`, `security`, `accountant`): Trả về danh sách rỗng (`total: 0, items: []`) hoặc bị chặn theo ma trận quyền.
   - **Bảo mật phạm vi dữ liệu (`SEC-01`, `ARC-03`):** Tuyệt đối không cho phép client gửi hoặc quyết định `tenant_id`, `role`, hay `building_id` qua query parameters. Mọi tham số mạo danh đều bị phớt lờ.
   - **Làm giàu dữ liệu hiển thị (Enrichment):** Sử dụng `JOIN Building` và `LEFT JOIN Unit` để trả kèm mã hiển thị thân thiện (`building_code`, `building_name`, `unit_number`) mà không phát sinh thêm câu truy vấn N+1.
   - **Phân trang & Lọc an toàn:** Hỗ trợ `page`, `page_size` (chặn trần tối đa 100 để bảo vệ DB), và lọc theo `status` nằm trong danh mục cho phép.

2. **Nối Giao diện Desktop thật (`greencity-app`) — Xóa bỏ Mock Data cho Luồng Đăng nhập & CSKH:**
   - **Xác thực phiên thật (Real Authentication):** Màn hình [`StaffLogin.jsx`](file:///C:/Users/LEGION/btl/_pttkpm/greencity-app/src/components/staff/StaffLogin.jsx) gửi thông tin đăng nhập trực tiếp tới `POST /api/v1/auth/login`. Có thông điệp cam kết: *"Mọi quyền hiển thị lấy từ `/auth/me`, người dùng không thể tự chọn vai trò trên giao diện"*.
   - **Token truy cập trong bộ nhớ (In-Memory Access Token):** Token được giữ trong closure của API Client ([`apiClient.js`](file:///C:/Users/LEGION/btl/_pttkpm/greencity-app/src/services/apiClient.js)), không persist vào `localStorage`, `sessionStorage` hay mock/source. Điều này giảm bề mặt lưu trữ lâu dài nhưng không loại bỏ rủi ro XSS trong renderer đang chạy. Đăng xuất hoặc reload làm mất phiên.
   - **Khởi tạo không gian làm việc từ hồ sơ máy chủ ([`authSession.js`](file:///C:/Users/LEGION/btl/_pttkpm/greencity-app/src/data/authSession.js)):** Sau login, hệ thống luôn gọi `GET /api/v1/auth/me`; role/site từ response này được ánh xạ qua policy menu cố định phía frontend. Client không cho người dùng tự chọn role hoặc scope.
   - **Bảng danh sách CSKH kết nối API thật ([`TasksDesktopView.jsx`](file:///C:/Users/LEGION/btl/_pttkpm/greencity-app/src/components/TasksDesktopView.jsx)):** Hiển thị danh sách yêu cầu dịch vụ đọc từ máy chủ, hỗ trợ thanh lọc trạng thái (Tất cả, Mới, Đang xử lý, Chờ thông tin...), bộ đếm tổng số, tính toán hạn SLA và cảnh báo nổi bật các yêu cầu đã quá hạn. Hỗ trợ thanh chuyển trang chuẩn mực.
   - **Xử lý toàn diện các trạng thái biên (UI Edge States):**
     - **Loading state:** Hiển thị spinner và thuộc tính `aria-busy` khi đang tải.
     - **Empty state:** Thông báo ngữ cảnh riêng biệt cho trường hợp "Chưa có yêu cầu trong phạm vi" vs "Không tìm thấy yêu cầu sau khi lọc".
     - **401 Unauthorized:** Tự động xóa sạch token trong bộ nhớ, đưa người dùng về màn hình đăng nhập kèm thông báo phiên hết hạn.
     - **`ERR-SCOPE-NOTFOUND` (404):** Hiển thị banner cảnh báo riêng khi người dùng cố truy cập ngoài phạm vi dữ liệu được cấp.
     - **`ERR-NETWORK`:** Xử lý mất kết nối máy chủ và cung cấp nút "Thử lại" (Retry).
     - **Mã đối chiếu (`X-Correlation-ID`):** Mọi cuộc gọi API đều mang correlation ID và hiển thị trong khung thông báo lỗi để tiện đối chiếu log hệ thống.
   - **Màn hình Tổng quan Phiên ([`SessionDashboard.jsx`](file:///C:/Users/LEGION/btl/_pttkpm/greencity-app/src/components/staff/SessionDashboard.jsx)):** Cung cấp các thẻ đo lường (metrics) tổng số yêu cầu, số lượng đang xử lý, chờ thông tin, quá hạn SLA, danh sách ưu tiên cần xử lý gấp, và ghi chú rõ ràng về phạm vi phiên.
    - **Tra cứu Căn hộ 360° ([`Unit360View.jsx`](file:///C:/Users/LEGION/btl/_pttkpm/greencity-app/src/components/Unit360View.jsx)):** Gọi đúng `GET /api/v1/units/{unit_id}/360`, chỉ truyền Unit ID; hiển thị unit/building/site, dữ liệu cư dân đã masking, `residents_visible`, trạng thái idle/loading/network-retry/401 và `ERR-SCOPE-NOTFOUND`.
    - **Switch-site an toàn:** Frontend chỉ gửi `{site_id}`, cài token mới rồi luôn gọi lại `/auth/me`; session revision loại response/401 của site cũ. Workspace key gồm account + active site làm remount để reset bộ lọc, trang, selection, search và Unit 360.

3. **Gia tăng quy mô kiểm thử tự động toàn diện:**
   - **Backend:** Toàn bộ **173 bài test PASS** tại mốc gần nhất, gồm AC-02 JSON 1.000 dòng, AC-03 Person–Unit và AC-24 quarantine/signed link.
   - **Frontend:** Bộ test tích hợp có ca switch-site và stale 401, đưa toàn bộ test suite lên **50/50 tests PASS**; smoke staff đạt **27 checks**.

---

## 2. Bảng so sánh tiến độ chi tiết qua 3 mốc Review

> ⚠️ **Lưu ý căn cứ chuẩn theo [`backend/VALIDATION.md:18`](file:///C:/Users/LEGION/btl/_pttkpm/backend/VALIDATION.md#L18):
> Các kết quả kiểm thử trên PostgreSQL 18.4 cô lập là **bằng chứng candidate trên môi trường kiểm thử local**, **chưa phải tuyên bố hoàn tất Gate C hay release production-ready**. Các tiêu chí tiền đề R1 còn thiếu bằng chứng độc lập (như import 1.000 dòng `AC-02`) cần được theo dõi riêng biệt; không được dùng test count R2 để mặc nhiên coi R1 là PASS toàn diện.

| Release / Phân hệ | Ngân sách | Mục tiêu & Phạm vi theo Roadmap | Đánh giá Review 1 (11/09) | Đánh giá Review 2 (12/09 Sáng) | Đánh giá Review 3 (12/09 Chiều) | Đánh giá thay đổi |
|---|:---:|---|:---:|:---:|:---:|---|
| **R0: Product Gate & Baseline** | 64 h | Khóa scope Core MVP vs `SPEC-ONLY`, wireflow UI, ERD neo, ma trận 8 vai trò, test runner cô lập. | Chưa chuẩn hóa bằng chứng | Candidate | **Candidate** | Có baseline local; chưa dùng bảng này để tuyên bố Gate A/B pass. |
| **R1: Nền tảng & Căn hộ 360°** | 80 h | CAP-PLT, CAP-SPC, CAP-CRM: Auth, Data Scope, RBAC theo tòa, Tra cứu căn hộ 360° (`/360`), chặn cross-site. | Chưa chuẩn hóa bằng chứng | Lát cắt candidate | **Lát cắt candidate** | `AC-24` pass local + review; `AC-02`, `AC-03`, `AC-35` có test local nhưng verdict/traceability chưa khép kín. |
| **R2: CSKH & Vận hành Kỹ thuật** | 112 h | CAP-SRV, CAP-AST: Service Request, Work Order, SLA, Checklist, Ảnh, Maker/Checker, Quản lý tài sản & Scheduler bảo trì. | 15% | Lát cắt candidate | **Lát cắt candidate** | Đã bổ sung `GET /service-requests`, nối hoàn chỉnh màn hình Đăng nhập và Danh sách CSKH đọc-only trên app desktop. |
| **R3: Vệ sinh & An ninh** | 112 h | CAP-ENV, CAP-SEC: Ca/tuyến vệ sinh, checklist đạt/không đạt, sổ bàn giao ca, tuần tra an ninh, sự cố/PCCC. | Chưa chuẩn hóa bằng chứng | Chưa mở sprint | **Chưa mở sprint** | Có mock UI; chưa có migration hoặc backend R3. |
| **R4: Phí & Hóa đơn cơ bản** | 80 h | CAP-FIN (BUILD): Biểu phí cơ bản, kỳ đóng/mở, hóa đơn snapshot, thanh toán thủ công, Overpayment Credit. | Chưa chuẩn hóa bằng chứng | Chưa mở sprint | **Chưa mở sprint** | Có baseline kiến trúc; chưa thi công release. |
| **R5: Điều hành & 4 Golden Flows** | 64 h | CAP-BI: Dashboard tổng hợp 4 mảng, drill-down số liệu, chạy liên hoàn 4 Golden Flows không sửa DB tay. | Chưa chuẩn hóa bằng chứng | Chưa mở sprint | **Chưa mở sprint** | Chưa chạy bốn Golden Flow liên hoàn. |
| **Hardening & Kiểm thử hồi quy** | 80 h | Kiểm thử tự động hồi quy, kiểm tra tải, tài liệu SAD/SDD, diễn tập kịch bản bảo vệ đề tài. | Chưa chuẩn hóa bằng chứng | Đang thực hiện | **Đang thực hiện** | Backend 173 tests; frontend 50 Node tests + 27 staff smoke checks pass local. |

---

## 3. Đánh giá tính tuân thủ Kiến trúc & Tiêu chuẩn Kỹ thuật

```
[Máy trạm Desktop]
   │
   ├── 1. POST /api/v1/auth/login ──────────> Trả về Bearer JWT (Lưu trong RAM, không lưu Storage)
   │
   ├── 2. GET /api/v1/auth/me ──────────────> Trả về account_id, roles, allowed_sites
   │                                          (UI tự dựng Menu & Phân quyền, cấm sửa scope)
   │
   ├── 3. GET /api/v1/service-requests ────> SQL scope từ phiên
   │      (?status=&page=&page_size=)
   │
   ├── 4. GET /api/v1/units/{unit_id}/360 ─> Unit ID trên path; projection từ backend
   │
   └── 5. POST /api/v1/auth/switch-site ───> Chỉ site_id; token mới → GET /auth/me
```

### 3.1. Các bất biến kiến trúc đã được chứng minh (Proven Invariants)
1. **`ARC-01..03` (Multi-tenant & Data Scope Invariants):**
   - Không có bất kỳ tham số phạm vi nào (`tenant_id`, `site_id`, `building_id`, `role`) được gửi từ Frontend lên Backend trong query danh sách.
   - Backend đọc account/site từ phiên đã xác thực, sau đó đọc lại role/grant từ DB và dựng scope truy vấn; không tin role/tenant do frontend gửi.
2. **`SEC-01` (Không tin cậy Client & IDOR Prevention):**
   - Khi client cố ý gửi các query param như `tenant_id` hay `building_id` mạo danh, backend hoàn toàn bỏ qua và chỉ áp dụng phạm vi của phiên hiện hành.
3. **`SEC-02` & `PRM-05..06` (RBAC & KTV Assigned-only):**
   - Kỹ thuật viên không thể nhìn thấy bất kỳ yêu cầu nào nếu yêu cầu đó không có Work Order phân công cho họ.
   - CSKH không thể nhìn thấy yêu cầu của tòa nhà khác ngoài danh sách tòa được phân quyền.
   - Vai trò `cleaning` và `security` được frontend chủ động khóa không cho gọi nhầm API Service Request, đồng thời backend cũng chặn quyền nếu gọi trái phép.
4. **An toàn bộ nhớ Token (In-Memory Token Safety):**
   - Token không được persist trong `localStorage` hay `sessionStorage`; reload yêu cầu đăng nhập lại. Token vẫn có thể bị ảnh hưởng nếu renderer đang chạy bị XSS, vì vậy đây là giảm thiểu rủi ro lưu trữ chứ không phải bảo đảm chống XSS tuyệt đối.
5. **Khả năng quan sát & Giám sát lỗi (Observability):**
   - Mọi cuộc gọi API đều được gắn header `X-Correlation-ID`. Mã đối chiếu này xuất hiện trực tiếp trên giao diện khi phát sinh lỗi để người dùng có thể gửi ngay cho đội ngũ kỹ thuật điều tra log mà không làm lộ dữ liệu nhạy cảm.

---

## 4. Bằng chứng Kiểm thử Thực tế

### 4.1. Backend Isolated PostgreSQL Test Suite
Lệnh thực thi:
```powershell
.\.venv\Scripts\python.exe -m scripts.test_isolated --pg-bin "C:\Program Files\PostgreSQL\18\bin" --openssl "C:\Program Files\Git\usr\bin\openssl.exe"
```
Kết quả ghi nhận:
```text
Fresh cluster init: PASS
Test TLS certificate: PASS
Test PostgreSQL startup: PASS
Empty DB migration: PASS (0001 -> 0002 -> 0003 -> 0004 -> 0005)
Migration repeat: PASS (Idempotency kiểm tra lại)
Demo seed: PASS (Nạp dữ liệu 2 site không PII)
Seed repeat: PASS (Idempotency dữ liệu mẫu)
Alembic schema drift: PASS (No new upgrade operations detected)
Isolated PostgreSQL regression: 173 passed, 2 warnings
Test PostgreSQL shutdown: PASS
```

### 4.2. Frontend Integration & Unit Test Suite
Lệnh thực thi:
```powershell
npm test
```
Kết quả ghi nhận:
```text
> greencity-app@1.0.0 test
> node --test tests/logic.test.js tests/assistant.test.js tests/staff.test.js tests/frontend-integration.test.js

ℹ tests 50
ℹ suites 0
ℹ pass 50
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ duration_ms 2314.3295
```

### 4.3. Frontend Production Build
Lệnh thực thi:
```powershell
npm run build
```
Kết quả:
```text
✓ 1610 modules transformed.
dist/index.html                   0.77 kB │ gzip:  0.52 kB
dist/assets/index-BQGa9e0H.css   80.14 kB │ gzip: 15.87 kB
dist/assets/index-Sy_IpNR4.js   244.95 kB │ gzip: 75.03 kB
✓ built in 23.34s
```

---

## 5. Tổng hợp bằng chứng hiện tại

Không quy đổi thành phần trăm hoàn thành release khi chưa có bảng đối chiếu đầy đủ từng exit criterion và chữ ký nghiệm thu. Trạng thái hiện tại được ghi nhận theo bằng chứng có thể chạy lại:

| Phạm vi | Bằng chứng local | Giới hạn kết luận |
|---|---|---|
| Backend R1/R2 candidate | 173 tests PostgreSQL cô lập ở lần chạy gần nhất, migration/seed repeat và schema drift pass | Không tự suy ra Gate A/B/C hoặc production-ready |
| Frontend auth + Service Request + Unit 360° + switch-site | 50 Node tests, 27 staff smoke checks và Vite build pass; AC-35 review timeout nên vẫn `[-]` | Browser test dùng API response được kiểm soát; không phải E2E browser-to-live-PostgreSQL |
| Toàn dự án R0–R5 | R3–R5 chưa mở sprint hoặc chưa có Golden Flow hoàn chỉnh | Không còn duy trì con số 62% thiếu traceability |

---

## 6. Các hành động tiếp theo được khuyến nghị

1. Giữ `AC-02`, `AC-03`, `AC-35` ở `[-]` và chưa stage code cho tới khi trạng thái review/traceability được giải quyết; không tự retry các request Antigravity đã timeout.
2. Stage tường minh lát AC-24 đã có `STATUS: PASS`, kiểm `git diff --cached --check`; không trộn việc xóa `plan1.md`/`plan2.md`.
3. Chỉ đánh giá mở R3 sau khi staged diff sạch và các AC tiền đề có traceability rõ. Migration R3 dự kiến bắt đầu từ `0006`, không ghi đè migration AC-03 `0005`.
