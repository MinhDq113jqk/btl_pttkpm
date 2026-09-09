# KẾ HOẠCH PHÁT TRIỂN GREENCITY — PLAN 2

## 1. Mục tiêu và ranh giới

**Điểm xuất phát:** phần backend đã được triển khai. Lần làm tiếp theo ưu tiên biến backend thành một lát dọc có thể nghiệm thu, thay vì làm thêm màn hình hoặc thay mock data của `greencity-app/`.

**Không làm trong Plan 2:** hoàn thiện frontend, portal cư dân, Green Assistant/AI, thanh toán online, refund/chargeback, hoặc các capability `SPEC-ONLY` khác.

> “Đã triển khai backend” chưa đồng nghĩa “đã sẵn sàng tích hợp/bảo vệ”. Chỉ được coi là hoàn thành khi migration, test, phân quyền/scope, API contract và Golden Flow tương ứng đều có bằng chứng chạy được.

## 2. Sửa các giả định cần làm rõ từ Plan 1

1. **Refund không thuộc Core MVP.** `plan1.md` liệt kê API `/refunds`, nhưng roadmap v2 đánh dấu refund/chargeback là `SPEC-ONLY`. Không tiếp tục xây hoặc demo nhóm API này trong Plan 2; giữ nó ở backlog V1.
2. **Không tin quyền hay `site_id` do client gửi.** JWT/session chỉ là đầu vào xác thực; backend phải tự suy ra role và Data Scope ở mỗi request, trả `404` cho bản ghi ngoài scope để không lộ sự tồn tại.
3. **8 role demo chưa tự khớp với 10 tác nhân con người.** Trước khi viết policy/seed, chốt bảng ánh xạ chính thức (ví dụ gộp Trưởng kỹ thuật/KTV thế nào; cư dân và kiểm toán có thuộc Core MVP hay không). Không để frontend role switch trở thành nguồn sự thật.
4. **Aiven không được giả định là môi trường test duy nhất.** Test tự động cần chạy lặp lại được với database cô lập; migration/integration test PostgreSQL cần tách rõ với test unit. Không ghi URI, mật khẩu, token hoặc dữ liệu cá nhân vào repo/log.

## 3. Trình tự lần làm tiếp theo

### P0 — Chụp baseline và xác nhận phạm vi (không thêm tính năng)

- Xác nhận checkout chuẩn là `_pttkpm/`; kiểm tra Git status, phiên bản dependency và các migration đã có.
- Đọc `backend/PHASE_0_AUDIT.md`, `backend/README.md`, `backend/VALIDATION.md`, schema, route, migration và test hiện hữu; lập bảng “đã có / có test / chưa có bằng chứng”.
- Khóa Core MVP theo roadmap: giữ 4 lát dọc BUILD (CSKH, kỹ thuật, vệ sinh, an ninh/an toàn) và tài chính cơ bản hỗ trợ; ghi rõ các phần bị hoãn là `SPEC-ONLY`.
- Chốt role matrix 8-role demo, owner nghiệp vụ, một site demo và site thứ hai chỉ để test isolation.

**Đầu ra:** `BACKEND_BASELINE.md` ngắn gọn, kèm danh sách lệnh kiểm chứng và các khoảng trống P0/P1. Không sửa frontend ở bước này.

### P1 — Gate B: contract và policy trước khi mở rộng endpoint

- Định nghĩa contract versioned `/api/v1`: DTO Pydantic, mã lỗi tiếng Việt, pagination/filter, UTC datetime, VND integer, `version` cho optimistic locking và correlation ID.
- Viết policy/server dependency cho authentication, role, tenant/site/building/assigned-only scope; mọi truy vấn phải đi qua policy này.
- Chốt lifecycle/state + owner + ngoại lệ + acceptance criteria cho các UC BUILD đầu tiên: UC-04, UC-16, UC-17, UC-18.
- Viết seed Mức A không có PII thật: tenant, 2 site, building/unit, account/role và dữ liệu nghiệp vụ tối thiểu.

**Điều kiện qua Gate B:** không còn mâu thuẫn giữa route, schema, role matrix, Data Scope, migration và AC; các `SPEC-ONLY` không nằm trong sprint.

### P2 — Hoàn tất lát dọc R1: nền tảng và tra cứu căn hộ 360°

- Chứng minh config environment, TLS PostgreSQL, Alembic upgrade từ database trống, health/readiness và seed có thể chạy lại an toàn.
- Hoàn tất session/login và `/auth/me`; backend tự lấy active scope. Nếu thật sự có chuyển site, kiểm tra quyền nhiều-site ở server và audit sự kiện chuyển scope.
- Cài `Site` → `Building` → `Unit` → `Person/Unit relationship` tối thiểu, cùng endpoint tra cứu Unit 360°.
- Thêm test API: cùng scope thấy dữ liệu đúng; khác site nhận `ERR-SCOPE-NOTFOUND`/404; input sai trả lỗi ổn định; audit/correlation ID hiện diện.

**Bằng chứng bắt buộc:** migration sạch, test tự động pass, truy vấn cross-site bị chặn, và một demo script/cURL không chứa secret.

### P3 — Mở rộng theo từng Golden Flow BUILD, không làm ngang toàn bộ module

Thứ tự triển khai sau khi R1 pass:

1. **R2 CSKH → kỹ thuật:** tiếp nhận Service Request, SLA cơ bản, sinh Work Order, checklist/ảnh, cập nhật trạng thái và lịch sử Asset/Maintenance.
2. **R3 Vệ sinh và an ninh:** ca/tuyến, checklist, Case/WO khắc phục; bàn giao ca, patrol/incident severity cao, escalation, chặn đóng khi thiếu kết luận/bằng chứng.
3. **R4 Tài chính cơ bản:** policy/snapshot, cost line được duyệt, invoice, ghi nhận thanh toán thủ công, overpayment credit cơ bản. Không đưa refund/proration/deposit vào R4.
4. **R5 Điều hành/audit:** KPI có drill-down về bản ghi nguồn, timeline, actor, scope và correlation ID.

Với mỗi lát dọc, chỉ mở sprint khi có: state diagram, policy, migration, seed, endpoint contract, test lỗi/scope/idempotency và một acceptance demo. Không “xong model” nếu luồng chưa chạy xuyên suốt.

## 4. Chiến lược kiểm thử và nghiệm thu

| Lớp | Cần chứng minh | Mốc áp dụng |
|---|---|---|
| Unit/domain | State transition, money VND, rounding, SLA, không tự duyệt | Mỗi module |
| API/policy | Auth, RBAC, tenant/site/assigned scope, 404 không lộ tồn tại | Từ R1 |
| Migration/seed | DB trống nâng cấp được; seed lặp lại an toàn | Từ R1 |
| Integration PostgreSQL | Constraint, transaction, optimistic locking, audit/outbox khi có | Từ R1/R2 |
| Golden Flow | 5 flow BUILD trong roadmap chạy không sửa DB thủ công | Gate C |
| Regression | Toàn bộ AC/NFR BUILD và `INV-01..02` không sai lệch | Hardening |

## 5. Khi nào mới quay lại frontend

Chỉ bắt đầu tích hợp frontend sau khi R1 có contract được khóa và test pass. Khi đó làm theo một lát dọc nhỏ: **login → `/auth/me` → tra cứu Unit 360°**, giữ UI desktop hiện hữu, thay đúng mock của lát đó, hiển thị lỗi API, và kiểm tra role/scope bằng backend. Không hoàn thiện giao diện hay nối toàn bộ API một lần.

## 6. Tiêu chí dừng của Plan 2

- Có baseline bằng chứng về backend hiện tại và quyết định role/release rõ ràng.
- Gate B và R1 pass với migration, seed, API/policy và test cross-site.
- Backlog R2–R5 được sắp theo Golden Flow BUILD; mọi `SPEC-ONLY` tách riêng.
- Frontend vẫn chưa bị mở rộng ngoài lát tích hợp được phê duyệt.

## 7. Câu hỏi cần chốt đầu buổi làm tiếp

1. Backend hiện đã bao phủ đến R1, hay đã có một phần R2–R5? Quyết định này phải dựa trên test/migration hiện có, không chỉ theo tên thư mục.
2. Tám role demo chính thức là những role nào và mỗi role có scope nào?
3. Nhóm dùng PostgreSQL local/container hay Aiven cho integration test; ai giữ quyền migration và ai xác nhận backup/restore?
4. UC/AC BUILD nào sẽ là acceptance demo đầu tiên sau R1?

