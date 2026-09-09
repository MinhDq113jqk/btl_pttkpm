# KẾ HOẠCH PHÁT TRIỂN HỆ THỐNG QUẢN LÝ KHU ĐÔ THỊ GREENCITY
## PLAN 1: ĐÁNH GIÁ TÍNH KHẢ THI & DANH MỤC API CHUẨN BỊ

> **Dự án:** Hệ thống Quản lý Vận hành Khu đô thị (GreenCity)  
> **Tài liệu căn cứ:** `roadmap_v2.md` (Master Baseline v2.0 - 07/09/2026)  
> **Ngân sách:** 592 person-hour / 3 thành viên (16 tuần)  
> **Công nghệ dự kiến:**  
> - Frontend: React 18 + Vite + Tailwind CSS (`greencity-app/`)  
> - Backend: Python FastAPI + Pydantic v2  
> - Database: PostgreSQL (Aiven Cloud Managed Service)  

---

## PHẦN 1: ĐÁNH GIÁ TÍNH KHẢ THI (FEASIBILITY ASSESSMENT)

### 1.1. Khả năng đáp ứng yêu cầu môn học & bảo vệ đề tài
* **Đánh giá:** **Rất cao (9.5/10)**.
* **Lý do:**
  * Đề tài Phân tích & Thiết kế Phần mềm (PTTKPM) đòi hỏi sự rõ ràng về mô hình phân tầng, tách bạch trách nhiệm và đặc biệt là tài liệu hóa API.
  * **FastAPI** tự động sinh tài liệu chuẩn tương tác **Swagger UI (`/docs`)** và **ReDoc (`/redoc`)**. Điều này giúp việc báo cáo tiến độ, chạy demo và trả lời chất vấn của hội đồng diễn ra trực quan, chuyên nghiệp mà không mất công viết tài liệu API thủ công.
  * Hỗ trợ xác thực schema 2 chiều (Pydantic v2) giúp giảm thiểu tối đa lỗi sai định dạng dữ liệu giữa client và server.

### 1.2. Khả năng cưỡng chế các bất biến kiến trúc Master Baseline v2.0
* **Đánh giá:** **Tuyệt đối (10/10)**.
* **Lý do:**
  * **PostgreSQL** là hệ quản trị cơ sở dữ liệu quan hệ (RDBMS) chuẩn công nghiệp, cho phép hiện thực hóa đầy đủ các bất biến bắt buộc trong Section 6 của roadmap:
    * `IDF-02`: Ràng buộc duy nhất đa cột `UniqueConstraint("site_id", "code")` cho phép các căn hộ ở các khu đô thị khác nhau có cùng số phòng hiển thị (ví dụ căn `A1-101`) mà không bao giờ bị xung đột dữ liệu.
    * `ARC-07`: Lưu trữ số tiền dạng `INTEGER` (đồng VND), không dùng số thực `FLOAT`, loại bỏ triệt để sai số làm tròn khi tính phí và lập hóa đơn.
    * `ARC-08`: Lưu trữ diện tích thông thủy (`carpet_area`) và diện tích tim tường (`built_up_area`) dưới dạng `NUMERIC(10, 2)` cố định 2 chữ số thập phân kèm `CheckConstraint("carpet_area > 0")`.
    * `ARC-09` & `ARC-10`: Hỗ trợ kiểu thời gian chuẩn `TIMESTAMPTZ` (UTC) và khoảng nửa mở `[valid_from, valid_to)` cho hợp đồng/quan hệ cư dân.
    * `ARC-13`: Cột phiên bản `version` hỗ trợ khóa lạc quan (Optimistic Concurrency Control), chống ghi đè dữ liệu khi nhiều nhân viên cùng thao tác.

### 1.3. Đánh giá hạ tầng Cloud Aiven PostgreSQL
* **Đánh giá:** **Khả thi & Đáng tin cậy (8.5/10)**.
* **Ưu điểm:**
  * Aiven cung cấp cụm PostgreSQL trên hạ tầng đám mây (AWS/GCP), có sẵn sao lưu tự động, chứng chỉ SSL bảo mật (`sslmode=require`), dashboard theo dõi CPU/RAM và dung lượng trực quan.
  * Gói miễn phí (Free Tier) hoàn toàn đáp ứng tốt cho quy mô dữ liệu Mức A (2 Site, ~200 căn hộ, vài nghìn bản ghi công việc).
* **Rủi ro kỹ thuật & Biện pháp kiểm soát:**
  1. *Độ trễ mạng (Network Latency):* Do đặt server tại Singapore/quốc tế, ping trung bình 40–80ms. Nếu gọi cloud trong quá trình chạy automated unit test trên máy cá nhân sẽ gây chậm trễ.
     * **Giải pháp:** Thiết kế cấu hình linh hoạt: Chạy Unit Test dùng SQLite in-memory cực nhanh trên máy local; khi chạy server demo, kiểm thử tích hợp (E2E) hoặc báo cáo thì trỏ vào PostgreSQL Aiven thật qua biến môi trường `DATABASE_URL`.
  2. *Giới hạn số lượng kết nối (Connection Pool Limit):*
     * **Giải pháp:** Cấu hình SQLAlchemy Connection Pool gọn gàng: `pool_size=5`, `max_overflow=10`, `pool_pre_ping=True` để tự động tái kết nối khi mạng chập chờn.

### 1.4. Đánh giá khối lượng công việc cho nhóm 3 thành viên
* **Đánh giá:** **Cân đối & Khả thi trong 592 giờ**.
* **Phân công đề xuất:**
  * **Thành viên 1 (Data & Infrastructure):** Thiết kế Schema CSDL, quản trị PostgreSQL Aiven, viết migration, nạp dữ liệu mẫu (Seed Data Mức A) và viết test bất biến `INV-01`, `INV-02`.
  * **Thành viên 2 (Backend Services & API):** Xây dựng các router FastAPI, cài đặt Middleware Data Scope (`ARC-03`), Correlation ID (`ARC-19`), Idempotency (`ARC-06`) và xử lý nghiệp vụ.
  * **Thành viên 3 (Frontend Integration):** Kết nối giao diện React `greencity-app` với các API thật (thay thế mock data), xử lý hiển thị lỗi nghiệp vụ (`ERR-*`) và trải nghiệm người dùng.

---

## PHẦN 2: DANH MỤC API CHI TIẾT CẦN CHUẨN BỊ (API CATALOG)

Dựa trên các màn hình, chức năng và 8 vai trò nhân viên đã có sẵn trong `greencity-app`, dưới đây là 5 nhóm API cần chuẩn bị:

### 2.1. Nhóm 1: Xác thực & Ngữ cảnh phân quyền (`CAP-PLT` - Auth & Scope)
*Phục vụ: Màn hình chuyển đổi 8 vai trò nhân viên và thanh chọn Site trên Header.*

| Method | Endpoint | Request Payload / Params | Response Structure | Ý nghĩa nghiệp vụ |
|---|---|---|---|---|
| `POST` | `/api/v1/auth/login` | `{"username": "...", "password": "..."}` | `{"access_token": "...", "user": {"id", "name", "role", "site_id"}}` | Đăng nhập tài khoản BQL, trả về JWT Token mang `role_code` và phạm vi `site_id`. |
| `GET` | `/api/v1/auth/me` | *Header: Bearer Token* | `{"id", "username", "full_name", "role_code", "current_site", "available_sites": [...]}` | Lấy thông tin phiên làm việc hiện tại của nhân viên. |
| `POST` | `/api/v1/auth/switch-site` | `{"new_site_id": "..."}` | `{"active_site_id": "...", "access_token": "..."}` | Chuyển đổi khu đô thị làm việc (áp dụng cho Giám đốc/Admin có quyền nhiều site - `ARC-05`). |

---

### 2.2. Nhóm 2: Không gian & Tra cứu Căn hộ 360° (`CAP-SPC` & `CAP-CRM` - Trọng tâm Release R1)
*Phục vụ: Menu "Dự án & Mặt bằng", "Khách hàng & Cư dân", Lát dọc tra cứu 360°.*

| Method | Endpoint | Request Payload / Params | Response Structure | Ý nghĩa nghiệp vụ |
|---|---|---|---|---|
| `GET` | `/api/v1/sites` | *Header: Bearer Token* | `[{"id", "code", "name", "address"}]` | Danh sách khu đô thị thuộc quyền xem của tài khoản. |
| `GET` | `/api/v1/buildings` | `?site_id=...` | `[{"id", "code", "name", "total_floors"}]` | Danh sách tòa nhà thuộc khu đô thị. |
| `GET` | `/api/v1/units` | `?building_id=&floor=&status=` | `[{"id", "code", "floor", "carpet_area", "built_up_area", "handover_status"}]` | Danh sách căn hộ (bắt buộc lọc tự động theo `site_id` của phiên - `ARC-03`). |
| `GET` | `/api/v1/units/{unit_id}/360` | `unit_id` trên đường dẫn | `{"unit": {...}, "building": {...}, "residents": [{"name", "phone", "relationship_type", "is_financial_sponsor"}]}` | **Lát dọc R1:** Tra cứu hồ sơ 360° căn hộ. Server từ chối 404 `ERR-SCOPE-NOTFOUND` nếu gọi sang căn hộ của Site khác (`AC-01`). |
| `POST` | `/api/v1/units/import` | `multipart/form-data` (file Excel) | `{"total_rows": 100, "success_count": 98, "errors": [{"row": 5, "reason": "Trùng mã căn"}]}` | Import danh sách căn hộ theo lô (`AC-02`). |

---

### 2.3. Nhóm 3: Công việc, Phản ánh & Hàng đợi tiếp nhận (`CAP-SRV`, `CAP-AST`, `CAP-ENV`, `CAP-SEC`)
*Phục vụ: Menu "Công việc & Yêu cầu", các tab chuyên môn Kỹ thuật / Vệ sinh / An ninh của 8 vai trò.*

| Method | Endpoint | Request Payload / Params | Response Structure | Ý nghĩa nghiệp vụ |
|---|---|---|---|---|
| `GET` | `/api/v1/tasks` | `?department=&status=&priority=` | `[{"id", "title", "location", "status", "deadline", "department", "assigned_to"}]` | Lấy danh sách công việc theo phân quyền vai trò (khớp với `getScopedTasks` trong `staffRoles.js`). |
| `GET` | `/api/v1/tasks/{task_id}` | `task_id` trên đường dẫn | `{"id", "title", "description", "checklist": [...], "history": [...], "attachments": [...]}` | Xem chi tiết công việc, thời hạn SLA và danh sách checklist kiểm tra. |
| `PATCH` | `/api/v1/tasks/{task_id}/status` | `{"status": "COMPLETED", "note": "...", "evidence_urls": [...]}` | `{"task_id", "new_status", "updated_at"}` | Cập nhật tiến độ xử lý công việc (Kỹ thuật viên hoàn thành bảo trì, Vệ sinh xác nhận ca). |
| `POST` | `/api/v1/requests` | `{"title", "unit_id", "content", "category"}` | `{"request_id", "code", "created_at"}` | Lễ tân / CSKH tiếp nhận và tạo yêu cầu phản ánh mới từ cư dân. |

---

### 2.4. Nhóm 4: Phiếu hoàn tiền & Hóa đơn (`CAP-FIN` - Đã có sẵn Form trên UI `greencity-app`)
*Phục vụ: Menu "Phiếu hoàn tiền & Hoá đơn" (Quy trình Maker/Checker giữa Kế toán và Giám đốc).*

| Method | Endpoint | Request Payload / Params | Response Structure | Ý nghĩa nghiệp vụ |
|---|---|---|---|---|
| `GET` | `/api/v1/refunds` | `?status=PENDING_APPROVAL` | `[{"id", "code", "unit_code", "amount", "reason", "creator", "status", "created_at"}]` | Danh sách phiếu hoàn tiền trong khu đô thị. |
| `POST` | `/api/v1/refunds/draft` | `{"unit_id", "amount", "reason", "bank_info"}` | `{"draft_id", "status": "DRAFT"}` | Kế toán lưu nháp thông tin hoàn tiền (`canSubmitRefund`). |
| `POST` | `/api/v1/refunds` | `{"unit_id", "amount", "reason", "payment_method", "bank_account", "evidence_file"}` | `{"refund_id", "code", "status": "PENDING"}` | Kế toán nộp phiếu chính thức trình duyệt Giám đốc. |
| `POST` | `/api/v1/refunds/{id}/approve` | `{"note": "Đồng ý chi trả"}` | `{"refund_id", "status": "APPROVED", "approver_id"}` | Giám đốc BQL phê duyệt phiếu (Cưỡng chế SoD: cấm tự duyệt phiếu do mình tạo - `AC-09`). |
| `POST` | `/api/v1/refunds/{id}/reject` | `{"rejection_reason": "Thiếu chứng từ gốc"}` | `{"refund_id", "status": "REJECTED"}` | Giám đốc BQL từ chối duyệt phiếu. |

---

### 2.5. Nhóm 5: Tổng quan điều hành & Thông báo (`CAP-BI` & `CAP-COM`)
*Phục vụ: Màn hình "Tổng quan" (Dashboard) và "Thông báo" trên Header.*

| Method | Endpoint | Request Payload / Params | Response Structure | Ý nghĩa nghiệp vụ |
|---|---|---|---|---|
| `GET` | `/api/v1/dashboard/kpis` | *Header: Scope* | `{"in_progress": 38, "pending_approval": 12, "completed_month": 146, "active_staff": 42}` | Trả về 4 chỉ số KPI điều hành khớp với dashboard của Giám đốc/BQL. |
| `GET` | `/api/v1/notifications` | `?unread_only=true` | `[{"id", "title", "detail", "time", "is_read", "task_id"}]` | Danh sách thông báo theo đúng phạm vi công việc của nhân viên đang đăng nhập. |

---

## PHẦN 3: LỘ TRÌNH TRIỂN KHAI THEO LÁT DỌC (VERTICAL SLICE)

Thay vì làm toàn bộ backend rồi mới nối frontend, nhóm nên triển khai lần lượt từng lát cắt dọc:

```mermaid
graph TD
    subgraph R1 ["Release R1: Nền tảng & Căn hộ 360° (Tuần 3-4)"]
        A1["Tạo bảng Tenant, Site, Building, Unit, Account"] --> A2["API Login & Tra cứu Căn hộ 360°"]
        A2 --> A3["Chặn chéo Data Scope Site A/B (AC-01)"]
    end

    subgraph R2 ["Release R2: CSKH & Kỹ thuật (Tuần 5-7)"]
        B1["Tạo bảng Request, WorkOrder, Asset"] --> B2["API Hàng đợi công việc & Checklist"]
        B2 --> B3["Kỹ thuật viên cập nhật tiến độ thật"]
    end

    subgraph R3 ["Release R3: Vệ sinh & An ninh (Tuần 8-10)"]
        C1["Tạo bảng CleaningTask, Patrol, Incident"] --> C2["API Ca vệ sinh & Tuần tra"]
        C2 --> C3["Xử lý sự cố và báo cáo điểm vi phạm"]
    end

    subgraph R4 ["Release R4: Phiếu hoàn tiền & Tài chính (Tuần 11-12)"]
        D1["Tạo bảng Refund, BillingAccount, Invoice"] --> D2["API Nộp & Phê duyệt Hoàn tiền"]
        D2 --> D3["Cưỡng chế SoD Maker/Checker (AC-09)"]
    end

    subgraph R5 ["Release R5: Dashboard Điều hành & Golden Flows (Tuần 13-14)"]
        E1["API KPI Dashboard Drill-down"] --> E2["4 Golden Flows hoàn chỉnh không sửa DB tay"]
    end

    R1 --> R2 --> R3 --> R4 --> R5
```

---

## PHẦN 4: CHECKLIST CHUẨN BỊ CHO BẠN VÀ NHÓM

Trước khi bắt tay vào viết code, các thành viên cần chuẩn bị sẵn:
- [ ] **Tạo dịch vụ PostgreSQL Aiven:**
  - Đăng ký tài khoản tại [Aiven.io](https://aiven.io).
  - Khởi tạo 1 dịch vụ PostgreSQL miễn phí (khu vực Singapore).
  - Lưu lại chuỗi kết nối URI có dạng: `postgres://avnadmin:PASSWORD@HOST.aivencloud.com:PORT/defaultdb?sslmode=require`.
- [ ] **Thống nhất Data Contract (Request/Response):**
  - Chốt tên các trường dữ liệu ở Phần 2 với thành viên làm frontend để tránh lệch tên trường (ví dụ `carpet_area` thay vì `dientich`).
- [ ] **Phân chia trách nhiệm trong nhóm:**
  - Bạn 1: CSDL & Cloud Aiven.
  - Bạn 2: Backend FastAPI theo hợp đồng API trên.
  - Bạn 3: Frontend React kết nối API.