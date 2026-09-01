# ROADMAP SẢN PHẨM PHẦN MỀM QUẢN LÝ KHU ĐÔ THỊ

> **Phiên bản:** 1.7 - Product Baseline tinh gọn
>
> **Ngày:** 02/09/2026
>
> **Trạng thái:** `PROPOSED BASELINE` cho đồ án/phiên bản demo
>
> **Phạm vi:** Tính năng sản phẩm, quy tắc nghiệp vụ, release và nghiệm thu
>
> **Nguồn:** Chắt lọc từ `ROADMAP_QUAN_LY_KHU_DO_THI_v1.6.md`

## 0. Kiểm soát tài liệu

### 0.1. Mục đích

Đây là nguồn sự thật trung tâm để trả lời bốn câu hỏi: sản phẩm giải quyết vấn đề gì, ai sử dụng, tính năng nào thuộc release nào và bằng chứng nào chứng minh tính năng đã hoàn thành.

### 0.2. Quy tắc chống lặp

- `OUT-*`: kết quả sản phẩm cần đạt.
- `CAP-*`: năng lực/phạm vi phát hành.
- `UC-*`: use case người dùng.
- `BR-*`: quy tắc và bất biến nghiệp vụ.
- `ST-*`: vòng đời trạng thái.
- `EX-*`: ngoại lệ cần xử lý.
- `AC-*`/`NFR-*`: tiêu chí nghiệm thu.
- `DEC-*`: quyết định hoặc giả định đã chọn.

Mỗi yêu cầu chỉ được mô tả đầy đủ tại một nơi; các phần khác tham chiếu ID. Lịch sử tự chấm phiên bản cũ, ERD/API, design pattern, CI/CD, cấu hình nhà cung cấp và test case chi tiết không nằm trong roadmap trung tâm.

---

## 1. Tầm nhìn, kết quả và ranh giới sản phẩm

### 1.1. Tầm nhìn

Xây dựng hệ thống tập trung giúp Ban quản lý kiểm soát không gian, cư dân, yêu cầu dịch vụ, công việc kỹ thuật, công nợ, thanh toán, an ninh và thông tin vận hành. Mỗi công việc, số tiền và thay đổi quan trọng phải truy ngược được về chủ thể, chứng từ, người thao tác và thời điểm.

### 1.2. Kết quả đo được

| ID | Kết quả | Đích kiểm chứng theo release |
|---|---|---|
| **OUT-01** | Dữ liệu nền đáng tin cậy | Import đúng tối thiểu 95% dòng hợp lệ; 100% dòng lỗi có vị trí và lý do |
| **OUT-02** | Yêu cầu được xử lý khép kín | 100% Work Order có người phụ trách, SLA, lịch sử và kết quả nghiệm thu |
| **OUT-03** | Công nợ minh bạch | 0 khoản thu trùng; 100% số dư tái lập được từ sổ bút toán |
| **OUT-04** | Đúng người, đúng phạm vi | 0 dữ liệu chéo site/role trong bộ test quyền |
| **OUT-05** | Điều hành có căn cứ | KPI drill-down khớp dữ liệu nguồn và cùng phạm vi quyền |
| **OUT-06** | Hỗ trợ người dùng an toàn | AI-R0 chuẩn bị trong MVP; từ AI-R1, câu trả lời phải có nguồn, đúng quyền và không tự thực hiện nghiệp vụ rủi ro |

### 1.3. Baseline đồ án

- Nhóm giả định 3-5 người; Core MVP thực hiện tuần 1-14, tuần 15-16 là buffer hoặc Parcel MVP-S.
- Luồng demo chính dùng một site; bộ test isolation có thêm một site tổng hợp không xuất hiện trong demo. Mô hình dữ liệu luôn mang `tenant/site/building_scope`.
- Desktop cho nhân viên là MVP; cổng cư dân web/PWA thuộc V1.
- Lễ tân có thể ghi nhận nghiệm thu thay cư dân trong MVP và bắt buộc lưu lý do/bằng chứng.
- Kiến trúc đã chọn ở mức ràng buộc: Python desktop, backend API và Supabase; chi tiết triển khai nằm ở SAD/SDD.
- Quy định pháp lý, thuế, quỹ và biểu mẫu chỉ được vận hành thật sau khi chủ nghiệp vụ xác nhận.

### 1.4. Phạm vi hệ thống

| Trong Core MVP | MVP-S/V1 | V2 hoặc ngoài phạm vi |
|---|---|---|
| Nền tảng quyền và Data Scope | Bưu phẩm ở MVP-S | IoT, BIM, FaceID, ANPR, barrier |
| Không gian, Person, quan hệ căn | Cổng cư dân, tạm trú/tạm vắng | Kế toán doanh nghiệp và báo cáo thuế đầy đủ |
| Helpdesk, Work Order, SLA, chi phí | Tài sản, bảo trì, tiện ích, an ninh | Đồng bộ offline hai chiều |
| Biểu phí, công nợ, hóa đơn, thanh toán | VietQR, đối soát ngân hàng, quỹ riêng | Hóa đơn điện tử và tích hợp thiết bị thật |
| Dashboard, audit, import/export | Kho, mua sắm, truyền thông, cộng đồng | AI tự trị trong tài chính/quyền/an ninh |

### 1.5. Hệ thống bên ngoài

- Nhà cung cấp xác thực, Email/SMS/Push, ngân hàng/VietQR, hóa đơn điện tử, thiết bị kiểm soát và AI provider là tác nhân phụ.
- Lỗi hệ thống ngoài không được rollback giao dịch lõi; yêu cầu gửi lại/đối soát phải vào hàng đợi có trạng thái.
- API key, token và dữ liệu bí mật chỉ tồn tại ở backend; ứng dụng desktop không gọi trực tiếp nhà cung cấp AI hay database bằng quyền quản trị.

---

## 2. Tác nhân, phạm vi dữ liệu và thực thể neo

### 2.1. Tác nhân

| Tác nhân | Mục tiêu chính | Phạm vi mặc định |
|---|---|---|
| **Admin** | Tài khoản, vai trò, danh mục, audit | Tenant/site được ủy quyền |
| **Giám đốc BQL** | Phê duyệt, dashboard, ngoại lệ | Site phụ trách |
| **Lễ tân/CSKH** | Tra cứu 360°, phản ánh, cư dân, bưu phẩm | Tòa/quầy phụ trách |
| **Kế toán** | Kỳ phí, hóa đơn, thanh toán, công nợ | Site hoặc tập tòa được cấp |
| **Trưởng kỹ thuật** | Phân công, SLA, nghiệm thu kỹ thuật | Khu/tòa phụ trách |
| **Kỹ thuật viên** | Thực hiện checklist, vật tư, ảnh | Work Order được giao |
| **An ninh** | Khách, xe, tuần tra, sự cố, bàn giao ca | Ca và khu vực phụ trách |
| **Cư dân V1** | Phản ánh, hóa đơn, tiện ích, thông báo | Căn và quan hệ còn hiệu lực của mình |
| **Kiểm toán** | Đọc báo cáo, chứng từ và audit | Read-only theo phạm vi được cấp |

### 2.2. Data Scope bắt buộc

- Mọi entity nghiệp vụ, tìm kiếm, dashboard, export, mã duy nhất và tệp đều mang hoặc suy ra được `tenant_id`, `site_id`, `building_id` phù hợp.
- UI, API, báo cáo, file, cache, notification và AI đều áp dụng cùng phạm vi; không chỉ ẩn nút ở giao diện.
- Phạm vi tác nhân lấy từ phiên đăng nhập và chính sách backend, không tin ID/role do client hoặc model tự truyền.
- Chuyển site phải làm mới dữ liệu, bộ lọc, cache và quyền truy cập tệp.

### 2.3. Thực thể neo của nghiệp vụ

| Thực thể | Ý nghĩa trung tâm |
|---|---|
| **Space/Unit** | Site → khu → tòa → tầng → căn/không gian; lưu riêng diện tích thông thủy và tim tường |
| **Person** | Hồ sơ con người; có thể tồn tại mà không có tài khoản đăng nhập |
| **Unit Relationship** | Quan hệ Person–Unit theo vai trò, tỷ lệ và khoảng hiệu lực; một người có thể liên quan nhiều căn |
| **Billing Account** | Tài khoản nhận phí/công nợ của một căn hoặc chủ thể thanh toán |
| **Liability Episode** | Khoảng thời gian một chủ thể chịu trách nhiệm tài chính; là căn cứ chia kỳ và chuyển giao công nợ |
| **Service Request** | Nhu cầu/sự cố do người dùng tiếp nhận; có thể sinh một hoặc nhiều Work Order |
| **Work Order/Cost Line** | Công việc thực hiện và từng dòng chi phí với đúng một bên chịu phí |
| **Pending Charge** | Khoản cư dân phải trả đang chờ kiểm tra trước khi ghi vào hóa đơn |
| **AR Entry** | Bút toán công nợ bất biến; nguồn sự thật của dư nợ và số dư |
| **Invoice/Invoice Item** | Chứng từ phát hành và snapshot chính sách phí tại thời điểm chốt |
| **Payment/Allocation** | Tiền nhận được và cách phân bổ nhiều-nhiều với hóa đơn |
| **Credit/Deposit/Restricted Fund** | Tiền đóng thừa, tiền cọc và quỹ hạn chế sử dụng; ba loại không được trộn |
| **Case/Incident** | Hồ sơ sự vụ dùng chung, liên kết Unit/Person/WO/Invoice/Parcel/Security |
| **Notification Outbox** | Thông báo cần gửi, recipient snapshot, trạng thái kênh, retry và bằng chứng giao nhận |

---

## 3. Chuỗi giá trị và Use Case trọng yếu

### 3.1. Chuỗi giá trị

```text
Nhánh phí định kỳ: Không gian → Person/Quan hệ căn → Billing Account/Liability Episode
                  → Fee Policy → Accounting Period/Billing Run

Nhánh phí phát sinh: Service Request → Work Order → Cost Line → Pending Charge

Hai nhánh → Invoice → Payment/Allocation → Credit/Refund/Reconciliation
          → Dashboard/Audit
```

Parcel, sự cố và thông báo dùng chung tái sử dụng Person, Space, Case, tệp và audit; không tạo hệ thống song song.

### 3.2. Use Case Catalog

| ID | Tên hành động | Tác nhân chính | Kết quả |
|---|---|---|---|
| **UC-01** | Đăng nhập và chọn phạm vi | Mọi nhân viên | Phiên có role/scope hợp lệ |
| **UC-02** | Nhập dữ liệu nền hàng loạt | Admin/CSKH | Dữ liệu hợp lệ được nhập, lỗi có báo cáo |
| **UC-03** | Quản lý người, căn và trách nhiệm tài chính | CSKH/Kế toán | Quan hệ và Liability Episode không chồng sai |
| **UC-04** | Tiếp nhận và phân loại yêu cầu | Lễ tân/CSKH | Service Request có SLA, owner và liên kết |
| **UC-05** | Lập và thực hiện Work Order | Trưởng/KTV | Công việc, checklist, bằng chứng và cost line đầy đủ |
| **UC-06** | Kiểm tra khoản cư dân trả | Kế toán | Pending Charge được duyệt/từ chối đúng quyền |
| **UC-07** | Chốt kỳ và phát hành hóa đơn | Kế toán/Giám đốc | Billing Run idempotent, invoice có snapshot |
| **UC-08** | Ghi nhận và phân bổ thanh toán | Kế toán | Tiền settled được match/allocation hoặc đưa unmatched |
| **UC-09** | Xử lý điều chỉnh, tranh chấp và hoàn tiền | Kế toán/Giám đốc | Bút toán đảo/điều chỉnh có phê duyệt và lý do |
| **UC-10** | Tiếp nhận và bàn giao bưu phẩm | Lễ tân/An ninh | Parcel có vị trí, người nhận và bằng chứng |
| **UC-11** | Theo dõi KPI và xuất báo cáo | Quản lý/Kiểm toán | Số tổng hợp khớp drill-down và đúng quyền |
| **UC-12** | Hỏi trợ lý nghiệp vụ | Nhân viên/Cư dân V1 | Câu trả lời đúng scope, có nguồn hoặc chuyển người thật |

Phạm vi Gate: UC-01..09 và UC-11 thuộc Core; UC-10 thuộc Parcel MVP-S; UC-12 thuộc AI. Các capability V1/V2 chỉ là epic, phải có UC/BR/AC riêng tại Gate D trước khi build.

### 3.3. Đặc tả tóm tắt các Use Case trọng yếu

| UC | Tiền điều kiện | Luồng chính | Luồng thay thế/ngoại lệ | Hậu điều kiện |
|---|---|---|---|---|
| **UC-02** | Có mẫu và quyền import | Upload → map → preview → validate → xác nhận → kết quả | Partial/all-or-nothing; file trùng; lỗi tham chiếu | Không tạo trùng; có import run và file lỗi |
| **UC-03** | Unit/Person tồn tại | Tìm người → tạo quan hệ → tạo Billing Account/Liability Episode → xác nhận | Nghi trùng; gap/overlap; chuyển giao giữa kỳ | Item được tách theo episode; nợ cũ giữ đúng Billing Account |
| **UC-04** | Có danh mục loại việc/SLA | Tiếp nhận → phân loại → ưu tiên → owner → tạo WO | Trùng yêu cầu; thiếu thông tin; nhiều WO; chuyển site | Đồng hồ SLA và timeline bắt đầu đúng |
| **UC-05** | Request hợp lệ | Phân công → thực hiện → checklist/ảnh → cost line → nghiệm thu | On-hold; đổi người; hủy; reopen; cư dân không phản hồi | Kết quả kỹ thuật và chi phí nguồn được khóa phiên bản |
| **UC-06** | Cost line `RESIDENT` đã submit | Kế toán kiểm tra bằng chứng → duyệt hoặc từ chối | Submit lặp; thiếu chứng từ; WO bị hủy | Mỗi cost line sinh tối đa một Pending Charge hợp lệ |
| **UC-07** | Kỳ OPEN, dữ liệu hợp lệ | Preview → xử lý cảnh báo → CLOSING → run → issue → CLOSED | Hai người cùng chạy; lỗi giữa chừng; charge sau cutoff | Không trùng/thiếu hóa đơn; snapshot tái tính được |
| **UC-08** | Payment có khóa nguồn duy nhất | Ghi nhận → settled → match → preview allocation → post | Thiếu mã; nghi trùng; trả thiếu/thừa; returned/chargeback | AR cân bằng; unmatched/credit đúng; không xóa lịch sử |
| **UC-09** | Có chứng từ gốc | Tạo yêu cầu → reason/evidence → phê duyệt → posting/reversal | Tự duyệt; kỳ LOCKED; thiếu số dư; yêu cầu trùng | Chứng từ gốc không bị sửa; số dư và audit cập nhật đúng |
| **UC-10** | Person/Unit hoặc người nhận xác định được | Nhận → lưu vị trí → báo nhận → xác minh → bàn giao | Không liên hệ được; sai PIN; mất/hỏng; trả lại | Timeline, recipient snapshot và bằng chứng đầy đủ |
| **UC-12** | AI release đã qua gate | Xác thực → retrieval/tool → kiểm quyền → trả lời/citation | Không nguồn; injection; provider lỗi; ngoài quyền | AI-R1..R3 không ghi; AI-R4 chỉ tạo draft/proposal, không tự gửi/thực thi |

---

## 4. Năng lực sản phẩm và lộ trình phát hành

### 4.1. Capability × Release Matrix

| ID | Năng lực | Core MVP | MVP-S | V1 | V2 |
|---|---|---|---|---|---|
| **CAP-PLT** | Nền tảng | Auth, RBAC, Data Scope, audit, search, import/export, tệp, approval | Không | Notification center, delegation | SSO/liên thông mở rộng |
| **CAP-SPC** | Không gian | Site/khu/tòa/tầng/căn, hai loại diện tích, bàn giao | Không | Khu vực chung, lịch sử thay đổi | Floorplan/BIM |
| **CAP-CRM** | Cư dân/CRM | Person, merge có duyệt, nhiều căn, hợp đồng, Liability Episode | Không | Tạm trú/tạm vắng, move-in/out, fit-out | OCR có xác minh |
| **CAP-SRV** | Helpdesk/WO | Request, nhiều WO, SLA, checklist, ảnh, cost line, CSAT | Không | Ca/kỹ năng/gợi ý phân công | Tự động hóa nâng cao |
| **CAP-AST** | Tài sản/đồng hồ | Không | Không | Chỉ số, tài sản, bảo hành, bảo trì, kiểm định | Telemetry/dự đoán |
| **CAP-FIN** | Tài chính | Fee policy, kỳ, AR, invoice, payment, credit, dispute/refund ledger; payout thủ công | Không | VietQR, đối soát tự động, quỹ bảo trì | E-invoice/kế toán ngoài |
| **CAP-SEC** | An ninh/lễ tân | Không | Parcel nếu được chọn | Khách, xe, tuần tra, PCCC | ANPR/FaceID/barrier |
| **CAP-ENV** | Môi trường/cảnh quan | Không | Không | Ca/tuyến/checklist/rác/cây xanh/case | Cảm biến môi trường |
| **CAP-AMN** | Tiện ích | Không | Không | Lịch, sức chứa, quota, cọc, waitlist, no-show | Thiết bị check-in |
| **CAP-SCM** | Kho/mua sắm | Không | Không | Nhiều kho, chứng từ, mua hàng, nhà thầu | Tích hợp ERP |
| **CAP-COM** | Truyền thông | Notification Outbox cho sự kiện lõi | Parcel notification nếu chọn | Thông báo, khảo sát, biểu quyết, cẩm nang | Đa kênh nâng cao |
| **CAP-BI** | Báo cáo | Công nợ, thu phí, SLA, CSAT, audit, drill-down/export | Báo cáo Parcel nếu chọn | Báo cáo vận hành mở rộng | Kho dữ liệu/BI ngoài |
| **CAP-AI** | Trợ lý AI | Chỉ AI-R0 chuẩn bị | Không | AI-R1, AI-R2 staff; AI-R3 resident pilot | AI-R4 Action Proposal |

### 4.2. Kế hoạch Core MVP

| Release | Tuần | Sản phẩm bàn giao | Exit criteria |
|---|---:|---|---|
| **R0 - Product Gate** | 1-2 | Actor/scope, UC, BR, state, wireflow, dữ liệu mẫu | DEC P0 có owner; Gate A/B Pass |
| **R1 - Trusted Master Data** | 3-5 | CAP-PLT, CAP-SPC, CAP-CRM lõi | AC-01..05 và AC-24 Pass |
| **R2 - Request to Resolution** | 6-8 | CAP-SRV và notification lõi | AC-06..10 và AC-22 Pass |
| **R3 - Charge to Cash** | 9-12 | CAP-FIN lõi | AC-11..21 và AC-30 Pass |
| **R4 - Control & Demo** | 13-14 | CAP-BI, audit, Golden Flow, hardening | Core AC-01..22, AC-24..25, AC-30 và NFR-01..11 Pass |
| **Buffer/MVP-S** | 15-16 | Sửa lỗi; Parcel nếu còn năng lực | Parcel cần AC-23; không làm giảm chất lượng Core |

### 4.3. Phụ thuộc bắt buộc

`CAP-PLT → CAP-SPC → CAP-CRM → CAP-SRV → CAP-FIN → CAP-BI`.

- CAP-FIN không build trước Billing Account, Liability Episode và approval matrix.
- Portal cư dân, parcel và tiện ích dùng lại Person, Notification, Case và Payment; không nhân bản.
- AI-R1 chỉ bắt đầu sau Core MVP Gate C; AI-R0 có thể chuẩn bị song song mà không chiếm nguồn lực luồng lõi.

### 4.4. Product Gates

- **Gate A - Ready for Design:** owner, scope, dữ liệu mẫu, UC và DEC P0 đã rõ.
- **Gate B - Ready for Build:** wireflow, state, quyền, BR, ngoại lệ và AC không mâu thuẫn.
- **Gate C - Core MVP Complete:** Golden Flow và mọi AC/NFR MVP Pass, không sửa database thủ công.
- **Gate D - Ready for V1:** phản hồi demo đã phân loại, scope V1 được ưu tiên lại và có chủ sở hữu.

---

## 5. P0 Control Registry

### 5.1. Quy tắc nghiệp vụ

| ID | Quy tắc bắt buộc | Owner xác nhận |
|---|---|---|
| **BR-SCP-01** | Mọi truy cập dữ liệu/tệp/report/cache áp dụng Data Scope tại backend | Admin/PO |
| **BR-SCP-02** | Export giữ bộ lọc, cột được phép, masking và recipient scope | Admin/PO |
| **BR-ID-01** | Person có 0 hoặc 1 tài khoản chủ động; SĐT/email chỉ là tín hiệu nghi trùng | CSKH |
| **BR-ID-02** | Quan hệ Person–Unit kết thúc hiệu lực thay vì xóa; tổng tỷ lệ sở hữu được kiểm tra theo thời gian | CSKH |
| **BR-LIA-01** | Mỗi Charge/Invoice Item trỏ Liability Episode hợp lệ cho service interval; Invoice trỏ đúng một Billing Account | Kế toán |
| **BR-LIA-02** | Chuyển giao giữa kỳ dùng chính sách proration; sửa hồi tố tạo adjustment, không sửa invoice đã phát hành | Kế toán/PO |
| **BR-LIA-03** | Mỗi service interval được Liability Episode phủ đúng 100%; gap/overlap bị chặn, nhiều episode phải tách item theo Billing Account | Kế toán/PO |
| **BR-SRV-01** | Một Service Request có thể sinh nhiều WO; merge/split/duplicate đều lưu liên kết và lý do | Vận hành |
| **BR-SRV-02** | SLA pause/resume chỉ theo reason code được cấu hình; escalation vẫn được audit | Vận hành |
| **BR-SRV-03** | Mỗi cost line có đúng một cost bearer; chỉ `RESIDENT` sinh Pending Charge | Kỹ thuật/Kế toán |
| **BR-SRV-04** | Request chỉ RESOLVED khi mọi WO đã terminal hợp lệ; nghiệm thu dùng resident/proxy, còn deemed acceptance mặc định tắt | Vận hành/PO |
| **BR-FEE-01** | Fee policy có phiên bản, hiệu lực, cơ sở tính, thuế, min/max, proration và thứ tự làm tròn | Kế toán |
| **BR-FEE-02** | Invoice lưu snapshot đầu vào/công thức; thay policy không đổi kỳ đã chốt | Kế toán |
| **BR-FEE-03** | Pending Charge sau cutoff chuyển kỳ sau; một charge chỉ posting một lần | Kế toán |
| **BR-AR-01** | AR subledger bất biến; sửa sai bằng bút toán đảo/điều chỉnh liên kết chứng từ gốc | Kế toán |
| **BR-AR-02** | Kỳ đi qua OPEN/CLOSING/CLOSED/LOCKED; reopen chỉ ở REOPENED_LIMITED có phạm vi, `expires_at`, delta report và auto-relock | Kế toán/Giám đốc |
| **BR-AR-03** | Billing Run idempotent theo site/kỳ/loại phí; retry không tạo trùng/thiếu | Kế toán |
| **BR-AR-04** | Overpayment Credit, Security Deposit và Restricted Fund là ledger/account riêng; không tự cấn trừ chéo | Kế toán |
| **BR-AR-05** | Sự kiện đến muộn của kỳ LOCKED được posting vào kỳ OPEN hiện tại và trỏ `original_period/entry`; không sửa kỳ gốc | Kế toán |
| **BR-PAY-01** | Payment chỉ phân bổ sau khi settled; tổng allocation không vượt tiền khả dụng | Kế toán |
| **BR-PAY-02** | Mặc định phân bổ nợ cũ trước trong cùng Billing Account; không tự trả nợ chủ cũ/tài khoản khác | Kế toán |
| **BR-PAY-03** | Payment không xác định đi vào Unmatched; không đoán căn/hóa đơn | Kế toán |
| **BR-PAY-04** | Returned payment/chargeback đảo allocation và mở lại dư nợ bằng bút toán | Kế toán |
| **BR-PAY-05** | Adjustment, waiver, write-off, dispute, refund có reason, evidence, maker-checker và vòng đời riêng | Kế toán/Giám đốc |
| **BR-PAY-06** | Payment có khóa nguồn duy nhất `(site, channel, provider_transaction_id/receipt_no)`; nghi trùng phải review | Kế toán |
| **BR-PAY-07** | Refund giữ beneficiary snapshot, payout reference duy nhất và evidence; retry/returned payout dùng transition, không tạo refund mới | Kế toán |
| **BR-APR-01** | Người tạo không tự duyệt giao dịch nhạy cảm; delegation có phạm vi và ngày hết hạn | Giám đốc |
| **BR-NOT-01** | Giao dịch lõi commit trước; Notification Outbox retry độc lập và giữ recipient/template snapshot | PO |
| **BR-PII-01** | PII có phân loại, masking, retention, legal hold và audit quyền xem/tải | Admin/PO |
| **BR-PII-02** | Tệp private có checksum, loại/kích thước cho phép, quét mã độc và signed access hết hạn | Admin |
| **BR-AI-01** | Backend/domain service là nguồn sự thật; AI không trực tiếp truy cập DB | PO |
| **BR-AI-02** | Retrieval/tool/citation tự kiểm quyền; chỉ tài liệu PUBLISHED đúng scope/hiệu lực được dùng | PO/Admin |
| **BR-AI-03** | AI-R1..R3 chỉ đọc; AI-R4 chỉ tạo draft/proposal trong allowlist; cấm tự duyệt phí, phát hành hóa đơn, hoàn tiền, đổi quyền, tự gửi hoặc bàn giao | PO |
| **BR-AI-04** | Không đủ nguồn hoặc provider lỗi phải từ chối đoán và chuyển sang hỗ trợ an toàn | PO |

### 5.2. Approval Matrix và phân tách nhiệm vụ

| Nghiệp vụ | Người tạo | Người duyệt | Điều kiện demo |
|---|---|---|---|
| Pending Charge | KTV/Trưởng kỹ thuật | Kế toán | Không cùng người; đủ evidence |
| Chốt kỳ/phát hành batch | Kế toán | Kế toán trưởng/Giám đốc | Preview sạch lỗi chặn |
| Adjustment/waiver/write-off | Kế toán | Giám đốc | Mọi số tiền đều cần duyệt trong demo |
| Refund/transfer credit | Kế toán | Giám đốc | Kiểm tra số dư khả dụng trước và ngay khi posting |
| Reopen kỳ LOCKED | Kế toán trưởng | Giám đốc | Lý do, phạm vi, thời hạn mở lại |
| Merge Person | CSKH | Admin/CSKH trưởng | Hiển thị ảnh hưởng quan hệ và công nợ |
| Delegation | Admin/Giám đốc | Người có thẩm quyền cao hơn | Có scope, hiệu lực và thu hồi |

### 5.3. Bất biến tài chính

- Tổng debit - credit của từng Billing Account tái lập đúng dư nợ tại mọi thời điểm.
- Mỗi allocation không vượt `min(payment_available, invoice_open_balance)`; phần tiền còn lại tạo bút toán Credit riêng, không gắn vào invoice.
- Mọi Invoice Item nguồn từ Pending Charge có khóa duy nhất; không tồn tại posting mồ côi.
- Invoice đã `ISSUED` không sửa số tiền; adjustment/reversal phải liên kết invoice/item gốc.
- Kỳ `LOCKED` không nhận posting mới; reopen tạo audit và báo cáo chênh lệch trước/sau.
- Tiền cọc/quỹ hạn chế không được dùng thanh toán phí vận hành nếu không có nghiệp vụ chuyển được phê duyệt.

---

## 6. State và Exception Registry

### 6.1. Vòng đời trọng yếu

| ID | Thực thể | Vòng đời chính | Guard quan trọng |
|---|---|---|---|
| **ST-SRV-01** | Service Request | `NEW → TRIAGED → IN_PROGRESS → RESOLVED → CLOSED` | Có `WAITING_INFO/CANCELLED`; reopen quay lại IN_PROGRESS và lưu event |
| **ST-WO-01** | Work Order | `DRAFT → ASSIGNED → IN_PROGRESS → WAITING_ACCEPTANCE → COMPLETED → CLOSED` | `ON_HOLD/CANCELLED`; đóng cần checklist và kết quả nghiệm thu |
| **ST-CHG-01** | Pending Charge | `DRAFT → SUBMITTED → APPROVED → POSTED` | `REJECTED/CANCELLED/REVERSED`; POSTED phải có Invoice Item |
| **ST-PER-01** | Accounting Period | `OPEN → CLOSING → CLOSED → LOCKED`; `LOCKED → REOPENED_LIMITED → LOCKED` | Reopen chỉ cho posting được duyệt, có expiry, auto-relock và delta report |
| **ST-INV-01** | Invoice | `DRAFT → ISSUED → VOIDED` | VOIDED chỉ khi chưa allocation và kỳ OPEN; còn lại dùng Credit Note/reversal |
| **ST-PAY-01** | Payment | `PENDING → SETTLED`; `PENDING → FAILED`; `SETTLED → RETURNED/CHARGEBACK` | Matching `UNMATCHED/PARTIAL/MATCHED` là vòng đời trực giao |
| **ST-DSP-01** | Dispute | `OPEN → UNDER_REVIEW → RESOLVED → CLOSED` | Resolution chọn giữ nguyên, adjustment, waiver hoặc write-off |
| **ST-ADJ-01** | Adjustment/Credit Note | `DRAFT → SUBMITTED → APPROVED → POSTED` | Có `REJECTED/CANCELLED`; liên kết chứng từ gốc |
| **ST-WRV-01** | Waiver/Write-off | `DRAFT → SUBMITTED → APPROVED → POSTED` | Không xóa nợ gốc; maker không là approver |
| **ST-RFD-01** | Refund | `DRAFT → SUBMITTED → APPROVED → PROCESSING → PAID`; `PROCESSING → FAILED → PROCESSING`; `PAID → RETURNED/REVERSED` | Cùng payout key; mỗi attempt có ID/reason/evidence, giới hạn retry; kiểm tra lại số dư |
| **ST-PAR-01** | Parcel | `RECEIVED → READY_FOR_PICKUP → HANDED_OVER` | `RETURNED/LOST/DAMAGED`; notification là event độc lập |
| **ST-CAS-01** | Case/Incident | `NEW → TRIAGED → IN_PROGRESS → RESOLVED → CLOSED` | Reopen quay lại IN_PROGRESS; severity quyết định SLA/escalation |
| **ST-AIP-01** | AI Action Proposal | `DRAFT → PRESENTED → CONFIRMED → EXECUTED` | `REJECTED/EXPIRED`; chống sửa, replay và TOCTOU |

Mỗi transition phải có event, actor, guard, timestamp, reason/evidence khi cần và transition cấm. Không dùng event như `REOPENED`, `ADJUSTED`, `UNMATCHED` thay cho state chính nếu chúng là thuộc tính/vòng đời trực giao.

### 6.2. Ngoại lệ liên phân hệ

| ID | Tình huống | Hành vi bắt buộc |
|---|---|---|
| **EX-01** | Import lỗi một phần | Cho chọn partial/all-or-nothing; trả đúng dòng/cột/lý do |
| **EX-02** | Chạy lại import/request/billing/payment | Idempotency key trả kết quả trước hoặc tiếp tục an toàn; không tạo trùng |
| **EX-03** | Person nghi trùng | Cho so sánh/liên kết/merge theo quyền; không tự gộp |
| **EX-04** | Quan hệ/Liability chồng thời gian | Chặn lỗi tài chính; trường hợp cảnh báo cần evidence và phê duyệt |
| **EX-05** | Hai người cùng sửa | Optimistic conflict; người lưu sau xem bản mới trước khi thử lại |
| **EX-06** | SLA bị tạm dừng | Chỉ pause theo reason; deadline mới và lịch sử phải tính lại được |
| **EX-07** | WO hủy sau khi có posting | Hủy khoản chưa duyệt; tạo reversal cho khoản đã posting |
| **EX-08** | Billing Run lỗi giữa chừng | Trạng thái FAILED; retry không sinh trùng/thiếu và có báo cáo bước lỗi |
| **EX-09** | Charge đến sau cutoff | Chuyển kỳ sau; không chen vào snapshot đã khóa |
| **EX-10** | Tiền thiếu mã | Đưa Unmatched queue; đối soát thủ công có maker-checker |
| **EX-11** | Returned payment/chargeback của kỳ đã LOCKED | Posting reversal vào kỳ OPEN hiện tại, mở công nợ và trỏ giao dịch/kỳ gốc |
| **EX-12** | Refund thiếu số dư hoặc kỳ hiện tại chưa OPEN | Từ chối posting; không chỉ cảnh báo ở UI |
| **EX-13** | Email/SMS/Push lỗi | Retry/fallback; giao dịch nguồn vẫn thành công và inbox hiển thị lỗi |
| **EX-14** | Parcel sai PIN/mất/hỏng | Khóa PIN hoặc tạo Case/biên bản; chặn bàn giao thông thường |
| **EX-15** | Tệp sai loại/có mã độc | Cách ly, chặn tải/xem và ghi sự kiện; không gắn vào hồ sơ chính thức |
| **EX-16** | AI thiếu nguồn, ngoài quyền hoặc bị injection | Không xác nhận dữ liệu tồn tại, không gọi tool ngoài allowlist, chuyển người thật |

---

## 7. Trợ lý AI nghiệp vụ

### 7.1. Giá trị và release

| Mốc | Năng lực | Exit gate |
|---|---|---|
| **AI-R0** | Data inventory, câu hỏi thật, threat model, Golden Questions, PoC provider | ACL/RLS, retention, owner nguồn và rubric được duyệt |
| **AI-R1** | Staff RAG hướng dẫn phần mềm/SOP, có citation | Grounding, injection, lifecycle tài liệu và fallback Pass |
| **AI-R2** | Tool chỉ đọc cho invoice/WO/credit/parcel | Permission matrix và số tiền 0 VND sai lệch Pass |
| **AI-R3** | Pilot cư dân tại một tòa | Staff pilot đạt gate; privacy/permission leak bằng 0 |
| **AI-R4** | Soạn nháp và Action Proposal có xác nhận | Approval matrix, anti-replay/expiry/TOCTOU Pass |

Mỗi mốc chỉ bắt đầu khi mốc trước đã Pass. Ở AI-R4, danh sách ghi được phép chỉ gồm tạo nháp Service Request, nháp nội dung trả lời cư dân, bản tóm tắt và đề xuất phân loại; AI không tự gửi. Người dùng xác nhận và domain API kiểm tra lại toàn bộ dữ liệu/quyền trước khi ghi. Danh mục cấm tại BR-AI-03 là cấm tuyệt đối, không phải ví dụ.

### 7.2. Guardrail trung tâm

- Một AI Gateway ở backend; khóa nhà cung cấp chỉ ở secret store, provider thay qua Adapter.
- Kho tri thức độc lập trên Supabase/pgvector; chỉ index bản `PUBLISHED`, có version, scope, citation và publish/revoke nguyên tử.
- Ingestion chống data poisoning: nguồn có owner, checksum, malware scan, review và audit trước publish.
- Nội dung tài liệu/tool/user là dữ liệu không tin cậy; không được ghi đè policy hoặc mở rộng quyền.
- Markdown/HTML/link đầu ra được sanitize; citation hết quyền hoặc hết hiệu lực không được hiển thị.
- Provider fallback chỉ dùng khi data class được duyệt; nếu không tương thích thì về keyword search/escalation.
- Conversation/cache/dữ liệu dẫn xuất tuân thủ retention và deletion propagation; trace nhạy cảm mã hóa, tách log thường.
- Model/prompt/index/tool thay đổi phải regression, canary, rollback; kill-switch AI không ảnh hưởng nghiệp vụ lõi.

---

## 8. Nghiệm thu sản phẩm

### 8.1. Bộ dữ liệu kiểm thử chuẩn

- Một tenant, hai site, năm tòa, 2.000 căn, 8.000 Person và quan hệ có lịch sử.
- 12 kỳ phí, 100.000 Invoice Item, 30.000 Payment/Allocation, 10.000 WO và 100.000 audit event.
- 30 người dùng đồng thời thuộc tối thiểu 8 vai trò; dữ liệu Site A/B có mẫu cố tình trùng mã hiển thị.
- Một Golden Flow có kết quả tiền cố định và một bộ negative/boundary test cho quyền, trạng thái, rounding, cutoff và concurrency.
- Mỗi AC dùng fixture đã khóa gồm input, business timestamp theo site timezone, expected state, expected ledger entries và exact amount; không chấp nhận “đúng” nếu thiếu oracle.

### 8.2. Acceptance Criteria chức năng

| ID | Kịch bản | Kết quả Pass |
|---|---|---|
| **AC-01** | Nhân viên Site A gọi UI/API/export/file của Site B | 100% bị chặn; không lộ sự tồn tại hoặc metadata nhạy cảm |
| **AC-02** | Import 1.000 dòng có lỗi/cảnh báo/trùng | Kết quả từng dòng chính xác; retry không tạo trùng |
| **AC-03** | Một Person sở hữu hai căn và thuê căn thứ ba | Tra cứu hai chiều đúng vai trò, tỷ lệ và hiệu lực |
| **AC-04** | Chuyển người chịu nợ tại boundary cố định | Item tách đúng episode/Billing Account; nợ cũ giữ chủ cũ; tổng sau rounding khớp 0 VND |
| **AC-05** | Merge hai Person có quan hệ/công nợ | Hiển thị tác động, cần duyệt, không mất liên kết/audit |
| **AC-06** | Một Request tạo hai WO, một WO proxy-accepted | Request chỉ RESOLVED khi cả hai WO terminal; proxy cần role/reason/evidence |
| **AC-07** | Pause/resume SLA bằng reason hợp lệ/không hợp lệ | Deadline tính đúng; reason sai bị chặn |
| **AC-08** | WO có vật tư cư dân trả và nhân công BQL chịu | Hai cost line; chỉ dòng RESIDENT tạo Pending Charge |
| **AC-09** | KTV tự duyệt khoản do mình tạo | Backend từ chối; audit ghi nỗ lực |
| **AC-10** | Hủy/reopen WO sau khi charge đã posting | Tạo reversal/Case phù hợp; không xóa chứng từ cũ |
| **AC-11** | Tính phí có proration, thuế, min/max và rounding | Kết quả khớp snapshot đến 0 VND |
| **AC-12** | Hai kế toán chốt cùng site/kỳ | Chỉ một run thắng; không trùng/thiếu hóa đơn |
| **AC-13** | Billing Run lỗi rồi retry | Hoàn tất đúng tập invoice và có báo cáo lỗi ban đầu |
| **AC-14** | Charge duyệt sau cutoff | Tự sang kỳ sau; snapshot kỳ hiện tại không đổi |
| **AC-15** | Posting vào LOCKED rồi reopen có thời hạn | Posting đầu bị chặn; kỳ vào REOPENED_LIMITED, chỉ nhận entry được duyệt, hết hạn tự LOCKED và có delta report |
| **AC-16** | Void invoice chưa trả/đã trả/thuộc LOCKED | Chỉ invoice chưa allocation trong kỳ OPEN sang VOIDED; trường hợp khác dùng Credit Note |
| **AC-17** | Trả một phần/gộp nhiều hóa đơn | Allocation không vượt open balance; phần dư tạo Credit riêng |
| **AC-18** | Chuyển khoản thiếu mã | Vào Unmatched; không giảm công nợ trước khi match được duyệt |
| **AC-19** | Thanh toán thừa | Chỉ phần thừa vào Overpayment Credit; không vào Deposit/Restricted Fund |
| **AC-20** | Chargeback thuộc kỳ đã LOCKED | Kỳ gốc bất biến; reversal vào kỳ OPEN, trỏ original entry và mở đúng công nợ |
| **AC-21** | Refund retry/trùng payout/sai payee/returned payout | Không trả hai lần; cùng refund/payout key, mỗi attempt được audit; FAILED/RETURNED đi đúng transition |
| **AC-22** | Kênh thông báo timeout | Giao dịch nguồn vẫn commit; outbox retry và hiển thị trạng thái |
| **AC-23** | Parcel giao đúng/sai PIN và trường hợp mất | Đúng PIN bàn giao một lần; sai PIN khóa; mất tạo Case và chặn giao |
| **AC-24** | Tải tệp trái quyền hoặc tệp độc hại | Không truy cập/preview; signed link hết hạn; tệp độc hại bị cách ly |
| **AC-25** | Dashboard công nợ/SLA tại một `as_of` cố định | Tổng khớp 100% snapshot/drill-down trong cùng scope và cutoff |
| **AC-26** | 50 câu AI held-out và 20 câu thiếu nguồn | ≥90% đạt rubric; Recall@5 ≥90%; citation correctness ≥95%; không bịa |
| **AC-27** | Ma trận AI role × site × unit × cache/history/tool/log | 0 rò rỉ; thu hồi quyền có hiệu lực ở request kế tiếp |
| **AC-28** | Prompt injection và output HTML/link độc hại | 0 lệnh/tool ngoài allowlist; 0 nội dung nguy hiểm được render |
| **AC-29** | Proposal bị sửa, hết hạn, replay hoặc đổi scope | Backend từ chối 100%; không có side effect |
| **AC-30** | Hai người ghi cùng source transaction với idempotency key khác | Chỉ một Payment được tạo; bản còn lại vào suspected-duplicate review |
| **AC-31** | Publish/revoke/re-index/xóa dữ liệu AI | Không trộn version; quyền/xóa lan tới retrieval, citation, cache và dữ liệu dẫn xuất |

Phân loại Gate: Core R1 dùng AC-01..05 và AC-24; R2 dùng AC-06..10 và AC-22; R3 dùng AC-11..21 và AC-30; R4 chạy lại toàn bộ Core. AC-23 chỉ bắt buộc nếu chọn Parcel MVP-S. AC-26..29 và AC-31 thuộc các gate AI tương ứng.

### 8.3. NFR đo được

| ID | Yêu cầu | Cách xác minh |
|---|---|---|
| **NFR-01** | P95 list/detail ≤2 giây, search ≤3 giây, dashboard ≤5 giây trên bộ dữ liệu chuẩn | Load test 30 user đồng thời |
| **NFR-02** | Import 10.000 dòng preview ≤60 giây; tiến trình lớn không khóa UI | Test file chuẩn và khả năng hủy/retry |
| **NFR-03** | 0 lỗi phân quyền/Data Scope ở UI, API, export, file và cache của capability Core đã phát hành | Permission matrix tự động + kiểm thử thủ công |
| **NFR-04** | Idempotency cho import, billing, posting và payment | Retry/concurrency test |
| **NFR-05** | Audit bất biến có actor, scope, before/after hợp lệ, reason và correlation ID | Truy vết Golden Flow end-to-end |
| **NFR-06** | Pilot có RPO ≤24 giờ, RTO ≤4 giờ; restore được diễn tập | Restore sang môi trường kiểm thử |
| **NFR-07** | 100% luồng MVP thao tác được bằng bàn phím; UI dùng được ở Windows scaling 125/150/200% | Accessibility và visual test |
| **NFR-08** | Form có loading/empty/error/permission/session/conflict; không báo thành công giả khi mất mạng | Fault-injection và UX checklist |
| **NFR-09** | Tệp private, checksum đúng, signed access hết hạn và malware validation | Upload/download negative test |
| **NFR-10** | Dữ liệu nhạy cảm được masking; log thường không chứa secret/CCCD đầy đủ/token | Log scan và privacy review |
| **NFR-11** | Mọi lỗi nghiệp vụ quan trọng có mã, correlation ID và thông tin xử lý được | Observability checklist |
| **NFR-12** | AI permission leak = 0; provider lỗi không làm gián đoạn Core | Security test và kill-switch drill |

### 8.4. Golden Flows

1. **Onboarding-to-billing:** import Space/Person → tạo Unit Relationship/Liability Episode → áp fee policy → preview/chốt kỳ → kiểm tra invoice snapshot.
2. **Request-to-cash:** tạo Request → hai WO/cost bearer → duyệt charge → invoice → partial payment → overpayment → returned payment/refund → dashboard/audit.
3. **Parcel-to-case - MVP-S:** nhận parcel → notification lỗi/retry → sai PIN → mất/hỏng → tạo Case → xử lý/đóng → báo cáo.
4. **Ask-to-escalate - AI:** hỏi AI về invoice/SOP → citation đúng scope → câu thiếu nguồn → chuyển CSKH; injection/tool vượt quyền bị chặn.

---

## 9. Ma trận truy vết yêu cầu

| Outcome | Capability/UC | Rule/State/Exception | AC/NFR | Release |
|---|---|---|---|---|
| OUT-01, OUT-04 | CAP-PLT, CAP-SPC, CAP-CRM; UC-01..03 | BR-SCP-01, BR-SCP-02, BR-ID-01, BR-ID-02, BR-LIA-01..03; EX-01..05, EX-15 | AC-01..05, AC-24; NFR-02..05, NFR-07..11 | R1, R4 |
| OUT-02 | CAP-SRV; UC-04..06 | BR-SRV-01..04, BR-NOT-01, BR-APR-01; ST-SRV-01, ST-WO-01, ST-CHG-01, ST-CAS-01; EX-06, EX-07, EX-13 | AC-06..10, AC-22; NFR-05, NFR-08, NFR-11 | R2 |
| OUT-03 | CAP-FIN; UC-07..09 | BR-FEE-01..03, BR-AR-01..05, BR-PAY-01..07, BR-APR-01; ST-PER-01, ST-INV-01, ST-PAY-01, ST-DSP-01, ST-ADJ-01, ST-WRV-01, ST-RFD-01; EX-02, EX-04, EX-08..12 | AC-11..21, AC-30; NFR-04..06 | R3 |
| OUT-05 | CAP-BI; UC-11 | BR-SCP-02, BR-AR-01 | AC-25; NFR-01, NFR-05, NFR-11 | R4 |
| OUT-02, OUT-04 | CAP-SEC, CAP-COM; UC-10 | BR-SCP-01, BR-NOT-01, BR-PII-01, BR-PII-02; ST-PAR-01, ST-CAS-01; EX-13..15 | AC-23, AC-24 | MVP-S Parcel |
| OUT-06 | CAP-AI; UC-12 | BR-AI-01..04; ST-AIP-01; EX-16 | AC-26..29, AC-31; NFR-12 | AI-R0..R4 |
| OUT-02, OUT-05 | CAP-AST, CAP-ENV, CAP-AMN, CAP-SCM và phần V1 của CAP-COM, CAP-SEC | Chưa baseline; phải tạo UC/BR/ST/EX tại Gate D | Phải tạo AC/NFR trước khi build | V1 backlog |

Quy tắc kiểm tra RTM: không có UC/BR/ST/EX/AC/NFR đã baseline mà không truy về Outcome, release và test. Epic V1/V2 không được build cho đến khi có traceability tương đương. Thay đổi rule phải chỉ ra AC, fixture và Golden Flow bị ảnh hưởng.

---

## 10. Risk Register sản phẩm

| ID | Rủi ro | Xác suất/Tác động | Owner | Giảm thiểu | Trigger và phương án dự phòng |
|---|---|---|---|---|---|
| **RSK-01** | Scope vượt năng lực nhóm | Cao/Cao | PO | Khóa vertical slice Core; Parcel chỉ làm sau Gate C | Trễ R1 >20%: chuyển merge/hợp đồng sang V1; trễ R3 >20%: chuyển dispute/waiver/write-off/refund sang V1, giữ invoice/manual payment/credit |
| **RSK-02** | Quy tắc phí/pháp lý chưa xác nhận | TB/Cao | Kế toán/PO | Policy version + DEC giả định rõ | Chưa duyệt Gate B: chỉ demo, không production |
| **RSK-03** | Dữ liệu import kém chất lượng | Cao/TB | Admin/CSKH | Preview, validation, dedupe, rollback logic | Lỗi >5%: làm sạch/mapping trước import |
| **RSK-04** | Rò dữ liệu chéo site/role | TB/Rất cao | Admin/Tech lead | Backend scope, private file, permission matrix | Bất kỳ leak: dừng release, revoke, điều tra audit |
| **RSK-05** | Sai sổ công nợ/đối soát | TB/Rất cao | Kế toán | Immutable ledger, invariants, maker-checker | Chênh lệch ≠0: khóa posting, reconcile từ ledger |
| **RSK-06** | AI trả sai/vượt quyền | Cao/Cao | PO/AI owner | RAG citation, read-only, eval, kill-switch | Critical incident: tắt AI, Core vẫn chạy |
| **RSK-07** | Phụ thuộc dịch vụ ngoài | TB/TB | Tech lead | Outbox, timeout, fallback được duyệt | Provider lỗi: queue/manual/keyword mode |

---

## 11. Decision Register

| ID | Quyết định baseline | Trạng thái | Owner cần xác nhận |
|---|---|---|---|
| **DEC-01** | Core MVP tuần 1-14; tuần 15-16 chỉ buffer hoặc Parcel MVP-S | `BASELINE-BTL` | PO/Nhóm |
| **DEC-02** | Desktop nhân viên ở MVP; portal cư dân ở V1 | `BASELINE-BTL` | PO |
| **DEC-03** | Demo một site; mọi dữ liệu vẫn thiết kế theo tenant/site/building scope | `BASELINE-BTL` | PO/Admin |
| **DEC-04** | Một Service Request có thể sinh nhiều Work Order | `BASELINE-BTL` | Vận hành |
| **DEC-05** | Diện tích tính phí lấy từ fee policy; dữ liệu demo dùng thông thủy, không hardcode | `BASELINE-BTL` | Kế toán |
| **DEC-06** | Episode dùng khoảng `[start_at,end_at)` theo site timezone; phí cho phép prorate tách item/account; nợ cũ ở lại chủ cũ, chuyển nợ cần phê duyệt riêng | `BASELINE-BTL` | Kế toán/PO |
| **DEC-07** | Charge sau cutoff sang kỳ sau; late event của kỳ LOCKED posting kỳ OPEN và trỏ kỳ gốc | `BASELINE-BTL` | Kế toán |
| **DEC-08** | Payment trả nợ cũ trước trong cùng Billing Account; override/transfer có preview, quyền và lý do | `BASELINE-BTL` | Kế toán |
| **DEC-09** | MVP hỗ trợ match/đối soát thủ công; tự động ngân hàng thuộc V1 | `BASELINE-BTL` | Kế toán |
| **DEC-10** | Refund do kế toán tạo và Giám đốc duyệt; demo không dùng ngưỡng bỏ duyệt | `BASELINE-BTL` | Giám đốc |
| **DEC-11** | Overpayment, deposit và restricted fund không dùng chung ledger/account | `BASELINE-BTL` | Kế toán |
| **DEC-12** | AI-R0 có thể song song; AI-R1 sau Core Gate C; AI-R4 chỉ ghi draft/proposal rủi ro thấp qua domain API | `BASELINE-BTL` | PO |

`BASELINE-BTL` là giả định có hiệu lực để thiết kế và chấm đồ án, không thay thế phê duyệt pháp lý/nghiệp vụ khi triển khai thực tế. Mọi thay đổi DEC phải ghi lý do, người duyệt, ngày hiệu lực và các ID bị ảnh hưởng.

---

## 12. Checklist khóa roadmap và đánh giá

### 12.1. Checklist nội dung

- [x] Có tầm nhìn, outcome đo được, ranh giới in/out và baseline nguồn lực.
- [x] Có actor chính/phụ, Data Scope và thực thể neo.
- [x] Có Use Case Catalog và đặc tả tóm tắt luồng chính/ngoại lệ.
- [x] Có capability/release/dependency/Product Gate.
- [x] Có Billing Account, Liability Episode, AR subledger và period lock.
- [x] Có approval/SoD, adjustment/dispute/refund và payment reconciliation.
- [x] Có state, exception, notification, PII/tệp và Case dùng chung.
- [x] Có AC, NFR, Golden Flow, RTM, risk và decision register.
- [x] Phần AI ngắn gọn, có release, guardrail và acceptance; không lấn át Core MVP.
- [x] Không còn lịch sử tự chấm v1.4/v1.5/v1.6, nội dung kỹ thuật chi tiết hoặc chuỗi nghiệp vụ bị lặp nhiều lần.

### 12.2. Checklist trước khi bắt đầu code

- [ ] Owner thực tế ký xác nhận DEC-01..12; change request phải được giải quyết và cập nhật baseline, không được để mở.
- [ ] Wireflow/quyền UC-01..09 và UC-11 được duyệt cho Core; UC-10, UC-12 duyệt tại gate riêng.
- [ ] Mẫu dữ liệu, fee policy, rounding, cutoff và kết quả tiền Golden Flow được đóng băng.
- [ ] Transition matrix chi tiết có actor/guard/action cho từng ST được đưa vào SRS.
- [ ] Permission matrix role × scope × action × field/file được kiểm tra chéo.
- [ ] Test Plan ánh xạ hai chiều toàn bộ AC/NFR và có người chịu trách nhiệm.

### 12.3. Đánh giá chất lượng v1.7

| Tiêu chí | Điểm | Bằng chứng trong tài liệu |
|---|---:|---|
| Scope và boundary | 1,00/1,00 | Mục 1 |
| Actor và system context | 0,75/0,75 | Mục 2 |
| Use case | 1,50/1,50 | Mục 3 |
| State model | 0,75/0,75 | Mục 6 |
| Business rules | 1,00/1,00 | Mục 5 |
| Acceptance/Golden Flow | 1,25/1,25 | Mục 8 |
| Traceability | 1,00/1,00 | Mục 9 |
| NFR đo được | 1,00/1,00 | Mục 8.3 |
| Risks | 0,75/0,75 | Mục 10 |
| Decisions và nhất quán | 1,00/1,00 | Mục 0, 11, 12 |
| **Tổng độ hoàn chỉnh roadmap** | **10,00/10,00** | **Đủ baseline để chuyển sang SRS/wireflow** |

Điểm 10/10 phản ánh độ hoàn chỉnh và khả năng truy vết của roadmap với các giả định `BASELINE-BTL`. Trạng thái sẵn sàng Production chỉ đạt khi checklist 12.2, thẩm định pháp lý/nghiệp vụ và toàn bộ Product Gate tương ứng được xác nhận bằng bằng chứng.
