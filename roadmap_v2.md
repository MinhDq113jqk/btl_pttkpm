# ROADMAP SẢN PHẨM PHẦN MỀM QUẢN LÝ KHU ĐÔ THỊ

> **Phiên bản:** 2.0 - Master Baseline (Phiên bản Hoàn thiện Toàn diện)
>
> **Ngày:** 07/09/2026
>
> **Trạng thái:** `APPROVED MASTER BASELINE` cho đồ án môn học & phát triển hệ thống
>
> **Phạm vi:** Tính năng sản phẩm, quy tắc nghiệp vụ, kiến trúc thi hành, phạm vi thi công, release và nghiệm thu
>
> **Nguồn:** Hoàn thiện và đóng gói chính thức từ v1.9 sau khi khắc phục triệt để 3 điểm sai quan trọng (thuế GTGT, deadlock trạng thái PendingCharge và thống nhất Overpayment Credit)
>
> **Tài liệu đi kèm:** `PROJECT_MANAGEMENT_PLAN.md` và `DANH_GIA_VA_SUA_LOI_ROADMAP_v1.9.md`

## 0. Kiểm soát tài liệu

### 0.1. Mục đích

Đây là nguồn sự thật trung tâm để trả lời năm câu hỏi: sản phẩm giải quyết vấn đề gì, ai sử dụng, tính năng nào thuộc release nào, hệ thống được cấu trúc thế nào để tính năng đó đứng được, và bằng chứng nào chứng minh tính năng đã hoàn thành.

v1.9 giữ các quyết định kiến trúc có khả năng thay đổi phạm vi tính năng, làm sai lệch số tiền hoặc nhân đôi khối lượng thi hành nếu chốt muộn. Thiết kế chi tiết còn lại (ERD đầy đủ, API contract từng endpoint, design pattern, CI/CD, cấu hình nhà cung cấp, test case chi tiết) vẫn thuộc SAD/SDD/Test Plan.

Roadmap phân biệt hai nhãn thi công:

- `BUILD`: bắt buộc có code và bằng chứng nghiệm thu trong học kỳ.
- `SPEC-ONLY`: được phân tích để giữ tầm nhìn sản phẩm nhưng không được trình bày như đã thi công.

Bốn mảng của đề tài — dịch vụ khách hàng, vận hành kỹ thuật, vệ sinh môi trường, an ninh và an toàn — đều phải có ít nhất một lát dọc `BUILD`; không được cắt bỏ trọn một mảng để cứu tiến độ.

### 0.2. Quy tắc chống lặp

| Tiền tố | Nội dung |
|---|---|
| `OUT-*` | Kết quả sản phẩm cần đạt |
| `CAP-*` | Năng lực/phạm vi phát hành |
| `UC-*` | Use case người dùng |
| `BR-*` | Quy tắc và bất biến nghiệp vụ |
| `ST-*` / `TRN-*` | Vòng đời trạng thái và bảng chuyển trạng thái |
| `EX-*` | Ngoại lệ cần xử lý |
| `AC-*` / `NFR-*` | Tiêu chí nghiệm thu |
| `DEC-*` | Quyết định hoặc giả định đã chọn |
| `ARC-*` | Quyết định kiến trúc thi hành |
| `ALG-*` | Thuật toán nghiệp vụ chuẩn hóa |
| `EVT-*` | Domain event |
| `PRM-*` | Quyền theo vai trò |
| `ERR-*` | Mã lỗi nghiệp vụ |
| `IDF-*` | Quy tắc định danh và mã nghiệp vụ |

Mỗi yêu cầu chỉ được mô tả đầy đủ tại một nơi; các phần khác tham chiếu ID. Lịch sử tự chấm phiên bản cũ không nằm trong tài liệu này.

### 0.3. Bổ sung của v1.9 so với v1.7/1.8

| Mục mới/điều chỉnh | Nội dung | Lý do bắt buộc có |
|---|---|---|
| 4 | Kiến trúc thi hành `ARC-01..20` | Các quyết định này thay đổi phạm vi tính năng và độ chính xác số tiền, không phải chi tiết cài đặt |
| 5 | Thuật toán nghiệp vụ `ALG-01..12` | `BR-FEE-01` yêu cầu "thứ tự làm tròn" và `BR-PAY-02` yêu cầu "thứ tự phân bổ" nhưng v1.7 không định nghĩa công thức |
| 6 | Mô hình dữ liệu neo và bất biến schema | v1.7 chỉ nêu tên 14 thực thể, không nêu khóa, quan hệ và ràng buộc bắt buộc |
| 7 | Domain event `EVT-01..24` | `BR-NOT-01` và audit yêu cầu event nhưng v1.7 không có danh mục |
| 8 | Bảng chuyển trạng thái `TRN-*` | `ST-*` chỉ nêu vòng đời; guard và hành động kèm theo chưa tường minh |
| 9 | Permission matrix `PRM-*` | `AC-01` và `NFR-03` không kiểm được nếu không có ma trận nguồn |
| 10 | Mã lỗi nghiệp vụ `ERR-*` | `NFR-11` yêu cầu "mọi lỗi nghiệp vụ quan trọng có mã" nhưng danh mục mã chưa tồn tại |
| 11 | Quy tắc định danh `IDF-*` | Mã nghiệp vụ hiển thị cho người dùng phải duy nhất theo scope và chống lộ thông tin |
| 11.5 | Thứ tự thi hành theo vertical slice | Chuỗi phụ thuộc `CAP-*` của v1.7 chưa nói thi hành theo chiều dọc hay chiều ngang, dẫn tới rủi ro không có gì demo được cho tới cuối |
| 11.6 | Phạm vi `BUILD`/`SPEC-ONLY` và ngân sách giờ | Bản 1.8 không phản ánh nhóm 3 người và không chứng minh phạm vi thi công vừa năng lực |
| 2, 3, 11-16 | Bổ sung lát dọc kỹ thuật, vệ sinh, an ninh | Hai bản trước đưa ba mảng bắt buộc ra khỏi Core MVP, trái phạm vi đề tài |
| Toàn tài liệu | Bỏ tuyên bố tự chấm 10/10 | Chỉ Product Gate và bằng chứng test mới chứng minh mức hoàn thiện |

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
| **OUT-06** | Hỗ trợ người dùng an toàn | `SPEC-ONLY` trong học kỳ; từ AI-R1, câu trả lời phải có nguồn, đúng quyền và không tự thực hiện nghiệp vụ rủi ro |
| **OUT-07** | Hệ thống tự bảo vệ tính đúng đắn | Mọi bất biến tài chính và phạm vi dữ liệu được cưỡng chế ở tầng dữ liệu/dịch vụ, không phụ thuộc kỷ luật người dùng |
| **OUT-08** | Kỹ thuật được bảo trì chủ động | 100% lịch đến hạn trong dữ liệu demo sinh nhiệm vụ; kết quả có checklist và bằng chứng |
| **OUT-09** | Vệ sinh được kiểm soát theo khu vực | 100% ca/tuyến demo có người phụ trách, checklist và kết quả đạt/không đạt |
| **OUT-10** | Sự kiện an ninh và an toàn truy vết được | 100% lượt tuần tra và sự cố demo có thời gian, khu vực, người ghi nhận và trạng thái xử lý |

`OUT-07` giữ bổ sung kiến trúc của v1.8. `OUT-08..10` sửa khoảng trống phạm vi: kỹ thuật, vệ sinh và an ninh là mảng bắt buộc của đề tài chứ không chỉ là backlog V1.

### 1.3. Baseline sản phẩm

- Nhóm có 3 thành viên. Ngân sách bền vững cho 16 tuần là 672 person-hour; v1.9 chỉ lập kế hoạch khoảng 590 person-hour và giữ phần còn lại làm dự phòng.
- Core MVP thực hiện trong tuần 1-14; tuần 15-16 chỉ dùng cho kiểm thử, sửa lỗi, hoàn thiện hồ sơ và diễn tập bảo vệ, không nhận thêm capability mới.
- Luồng demo chính dùng một site; bộ test isolation có thêm một site tổng hợp không xuất hiện trong demo. Mô hình dữ liệu luôn mang `tenant/site/building_scope`.
- Desktop cho nhân viên là MVP; cổng cư dân web/PWA thuộc V1.
- Lễ tân có thể ghi nhận nghiệm thu thay cư dân trong MVP và bắt buộc lưu lý do/bằng chứng.
- Kiến trúc thi hành được chốt tại mục 4; SAD/SDD chỉ chi tiết hóa, không được đảo quyết định đã ghi `ARC-*`.
- Quy định pháp lý, thuế, quỹ và biểu mẫu chỉ được vận hành thật sau khi chủ nghiệp vụ xác nhận.

### 1.4. Phạm vi hệ thống

| `BUILD` trong Core MVP | `SPEC-ONLY`/V1 | V2 hoặc ngoài phạm vi |
|---|---|---|
| Nền tảng quyền, Data Scope, audit | Bưu phẩm, cổng cư dân | IoT, BIM, FaceID, ANPR, barrier |
| Không gian, Person, quan hệ căn | Cổng cư dân, tạm trú/tạm vắng | Kế toán doanh nghiệp và báo cáo thuế đầy đủ |
| CSKH: tiếp nhận yêu cầu, Work Order, SLA cơ bản | Portal tự phục vụ, CSAT nâng cao | Đồng bộ offline hai chiều |
| Kỹ thuật: tài sản tối thiểu, lịch bảo trì, checklist | Đồng hồ, bảo hành, kiểm định | Telemetry và bảo trì dự đoán |
| Vệ sinh: ca/tuyến, nhiệm vụ, checklist, ghi nhận không đạt | Rác thải, cảnh quan, cây xanh | Cảm biến môi trường |
| An ninh/an toàn: bàn giao ca, tuần tra, khách và sự cố/PCCC | Bưu phẩm, bãi xe, thẻ ra vào | Tích hợp thiết bị kiểm soát thật |
| Biểu phí cơ bản, hóa đơn, thanh toán thủ công, công nợ | Proration phức tạp, refund/chargeback, VietQR và đối soát tự động | Hóa đơn điện tử và kế toán ngoài |
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
| **Nhân viên vệ sinh** | Thực hiện ca/tuyến và checklist vệ sinh | Nhiệm vụ và khu vực được giao |
| **An ninh** | Khách, xe, tuần tra, sự cố, bàn giao ca | Ca và khu vực phụ trách |
| **Cư dân V1** | Phản ánh, hóa đơn, tiện ích, thông báo | Căn và quan hệ còn hiệu lực của mình |
| **Kiểm toán** | Đọc báo cáo, chứng từ và audit | Read-only theo phạm vi được cấp |
| **System/Scheduler** | Chạy job định kỳ, outbox, escalation SLA, auto-relock kỳ | Toàn tenant, không có UI, mọi hành động vẫn ghi audit với actor kỹ thuật |

`System/Scheduler` là bổ sung của v1.8. Lý do: `BR-AR-02` yêu cầu auto-relock, `BR-NOT-01` yêu cầu outbox retry độc lập và `BR-SRV-02` yêu cầu escalation. Ba hành vi này không có tác nhân người nào chịu trách nhiệm, nên nếu không khai báo thì audit trail sẽ có bản ghi không có actor, vi phạm `NFR-05`.

### 2.2. Data Scope bắt buộc

- Mọi entity nghiệp vụ, tìm kiếm, dashboard, export, mã duy nhất và tệp đều mang hoặc suy ra được `tenant_id`, `site_id`, `building_id` phù hợp.
- UI, API, báo cáo, file, cache, notification và AI đều áp dụng cùng phạm vi; không chỉ ẩn nút ở giao diện.
- Phạm vi tác nhân lấy từ phiên đăng nhập và chính sách backend, không tin ID/role do client hoặc model tự truyền.
- Chuyển site phải làm mới dữ liệu, bộ lọc, cache và quyền truy cập tệp.
- Điểm cưỡng chế duy nhất và cách kiểm chứng được quy định tại `ARC-03`.

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
| **Fee Policy/Version** | Chính sách phí có phiên bản và khoảng hiệu lực; là đối tượng được snapshot vào Invoice Item |
| **Accounting Period** | Kỳ kế toán theo site; kiểm soát cửa sổ posting của toàn bộ bút toán |
| **Billing Run** | Một lần chạy sinh hóa đơn theo site/kỳ/loại phí; là đối tượng idempotent |
| **Idempotency Record** | Bản ghi khóa chống lặp dùng chung cho import, billing, posting và payment |
| **Audit Event** | Bản ghi bất biến của thao tác nhạy cảm, gắn correlation ID |
| **Attachment** | Tệp private có checksum, phân loại và chính sách truy cập |
| **Asset/Maintenance Plan** | Tài sản kỹ thuật, chu kỳ bảo trì và lần đến hạn kế tiếp |
| **Cleaning Shift/Task** | Ca, tuyến/khu vực, checklist và kết quả kiểm tra vệ sinh |
| **Patrol/Security Incident** | Lượt tuần tra, bàn giao ca, khách và sự cố an ninh/PCCC |

Bốn thực thể cuối cùng và `Fee Policy/Version`, `Accounting Period`, `Billing Run` là bổ sung của v1.8. Lý do: chúng đã được `BR-FEE-01`, `BR-AR-02`, `BR-AR-03`, `EX-02`, `NFR-05`, `NFR-09` của v1.7 sử dụng như thực thể có thật nhưng không nằm trong danh sách neo, dẫn tới Class Diagram vẽ theo v1.7 sẽ thiếu lớp.

---

## 3. Chuỗi giá trị và Use Case trọng yếu

### 3.1. Chuỗi giá trị

```text
Nhánh phí định kỳ: Không gian → Person/Quan hệ căn → Billing Account/Liability Episode
                  → Fee Policy Version → Accounting Period/Billing Run

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
| **UC-13** | Cấu hình biểu phí và phiên bản chính sách | Kế toán/Admin | Fee Policy Version có hiệu lực, không đổi kỳ đã chốt |
| **UC-14** | Quản trị kỳ kế toán | Kế toán trưởng/Giám đốc | Kỳ chuyển trạng thái đúng, reopen có thời hạn và delta report |
| **UC-15** | Vận hành job hệ thống và hàng đợi | System/Admin | Outbox, escalation, auto-relock chạy đúng và quan sát được |
| **UC-16** | Lập và thực hiện bảo trì kỹ thuật | Trưởng kỹ thuật/KTV | Lịch đến hạn sinh nhiệm vụ, có checklist và kết quả |
| **UC-17** | Lập ca và kiểm tra vệ sinh | Quản lý/Nhân viên vệ sinh | Khu vực được làm đúng ca, lỗi chất lượng được ghi nhận |
| **UC-18** | Ghi nhận tuần tra và xử lý sự cố an ninh | An ninh/Giám đốc | Nhật ký ca, lượt tuần tra và sự cố/PCCC có timeline khép kín |

Phạm vi Gate: UC-01..08, UC-11, UC-13, UC-15..18 thuộc `BUILD`; UC-09, UC-10, UC-12, UC-14 và các nhánh tài chính nâng cao thuộc `SPEC-ONLY`. Các capability V1/V2 chỉ là epic, phải có UC/BR/AC riêng tại Gate D trước khi build.

UC-13..15 là bổ sung của v1.8. Lý do: `BR-FEE-01`, `BR-AR-02`, `BR-NOT-01` của v1.7 đặt ra hành vi cần có nhưng không có use case nào tạo và quản trị các đối tượng đó, nên Use Case Diagram sẽ có lỗ hổng logic — hóa đơn dùng fee policy mà không ai tạo fee policy, kỳ bị lock mà không ai lock.

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
| **UC-13** | Có quyền cấu hình phí | Tạo version → nhập cơ sở tính/thuế/min-max/rounding → đặt hiệu lực → publish | Sửa version đang dùng; hiệu lực chồng nhau; publish vào kỳ đã CLOSED | Version mới chỉ áp cho kỳ chưa chốt; version cũ giữ nguyên vĩnh viễn |
| **UC-14** | Kỳ tồn tại và có quyền | Xem trạng thái → chuyển CLOSING/CLOSED/LOCKED → hoặc mở REOPENED_LIMITED có phạm vi/thời hạn | Reopen không có lý do; hết hạn còn posting dở; hai người cùng chuyển | Mỗi transition có delta report và audit; auto-relock đúng hạn |
| **UC-15** | Job được cấu hình | Scheduler kích hoạt → xử lý batch → ghi kết quả từng item → báo cáo | Item lỗi lặp; vượt giới hạn retry; job chạy chồng | Item lỗi vào dead-letter có thể xử lý tay; job không chạy chồng |
| **UC-16** | Asset và Maintenance Plan hợp lệ | Xem lịch đến hạn → sinh WO → giao KTV → checklist/ảnh → nghiệm thu | Lịch bị tắt; sinh trùng; thiếu phụ tùng; hoãn có lý do | Một kỳ đến hạn chỉ sinh tối đa một WO; lịch sử bảo trì cập nhật |
| **UC-17** | Có ca, khu vực và checklist | Lập ca/tuyến → giao việc → thực hiện checklist → kiểm tra → đạt/không đạt | Vắng ca; bỏ sót điểm; không đạt; phát sinh sự cố | Kết quả gắn đúng ca/khu vực/người thực hiện; lỗi tạo Case/WO |
| **UC-18** | Có ca và khu vực tuần tra | Bàn giao ca → ghi khách/lượt tuần tra → ghi sự cố → phân loại → xử lý/đóng | Bỏ lượt; sự cố nghiêm trọng; mất mạng; thiếu bằng chứng | Timeline không sửa xóa, sự cố nghiêm trọng được escalation |

---

## 4. Kiến trúc thi hành (Execution Architecture)

Mục này là bổ sung lớn nhất của v1.8. v1.7 ghi "kiến trúc đã chọn ở mức ràng buộc, chi tiết triển khai nằm ở SAD/SDD". Vấn đề: một phần quyết định trong nhóm này không phải chi tiết cài đặt mà là **điều kiện tồn tại của tính năng**. Nếu chốt sai hoặc chốt muộn, hoặc tính năng không thể đạt AC, hoặc khối lượng thi hành bị nhân đôi. Ví dụ cụ thể: nếu không quyết định điểm cưỡng chế Data Scope ngay, nhóm sẽ viết kiểm tra quyền ở cả tầng UI, tầng service và RLS, ba nơi lệch nhau và `AC-01` không bao giờ Pass ổn định.

### 4.1. Kiến trúc tổng thể và biên giới tin cậy

| ID | Quyết định | Nội dung bắt buộc | Hệ quả nếu làm khác |
|---|---|---|---|
| **ARC-01** | Ba tầng có biên tin cậy rõ | Desktop client (không tin cậy) → Backend API (tin cậy, chứa toàn bộ nghiệp vụ) → Database. Client không giữ secret, không gọi DB bằng quyền quản trị, không tự quyết quyền | Nghiệp vụ nằm ở client thì mọi `BR-*` bị vô hiệu bằng cách sửa client hoặc gọi API trực tiếp |
| **ARC-02** | Backend là nguồn sự thật duy nhất cho quyền và tính toán tiền | Mọi phép tính tiền, kiểm tra quyền, chuyển trạng thái đều thực hiện ở backend; client chỉ hiển thị và gửi ý định | Tính tiền ở client thì hai máy khác nhau cho hai kết quả khác nhau, `AC-11` không kiểm chứng được |
| **ARC-03** | Data Scope cưỡng chế tại **một** điểm | Chọn tầng service của backend làm điểm cưỡng chế duy nhất: mọi truy vấn đi qua một hàm/lớp dựng scope filter từ session, không truy vấn nào được viết tay bỏ qua lớp này. RLS của database là **lưới an toàn thứ hai** ở chế độ deny-by-default, không phải nơi chứa logic phân quyền | Cưỡng chế ở nhiều nơi với logic khác nhau thì chi phí gấp đôi và chắc chắn lệch; chỉ cưỡng chế ở UI thì `AC-01` fail |
| **ARC-04** | Kiến trúc module theo capability, không theo tầng kỹ thuật | Mã nguồn chia theo `CAP-*` (platform, space, crm, service, asset, environment, security, finance, bi), mỗi module có API vào rõ ràng; module tài chính không được import trực tiếp bảng của module khác mà đi qua API nội bộ | Chia theo tầng (tất cả model một chỗ, tất cả service một chỗ) thì phụ thuộc mục 11.3 không kiểm soát được, logic nghiệp vụ rò rỉ vào mọi nơi |
| **ARC-05** | Desktop không giữ trạng thái nghiệp vụ lâu dài | Client chỉ cache dữ liệu đọc trong phiên và phải xóa khi đổi site/đăng xuất; không có DB cục bộ đồng bộ hai chiều | Cache tồn tại qua lần đổi site sẽ vi phạm mục 2.2 và `AC-01` |
| **ARC-06** | Mọi API ghi đều nhận `Idempotency-Key` | Client sinh key cho mỗi ý định ghi; backend lưu vào `Idempotency Record` và trả lại kết quả cũ khi gặp key trùng | Không có key thì mất mạng lúc bấm lưu sẽ tạo bản ghi trùng, `EX-02` và `NFR-04` fail |

### 4.2. Mô hình tiền, thời gian và định lượng

Nhóm quyết định này ảnh hưởng trực tiếp tới `AC-04`, `AC-11`, `AC-14`, `AC-17`, `AC-19` — tất cả đều yêu cầu khớp đến 0 VND.

| ID | Quyết định | Nội dung bắt buộc | Hệ quả nếu làm khác |
|---|---|---|---|
| **ARC-07** | Tiền lưu bằng số nguyên VND | Mọi số tiền là integer đơn vị đồng, không dùng float ở bất kỳ đâu. Đơn giá cho phép có phần thập phân thì lưu riêng dưới dạng decimal có scale khai báo, còn **kết quả tiền luôn là integer sau khi áp `ALG-01`** | Float có thể làm lệch số tiền và khiến AC-11 không tái lập được |
| **ARC-08** | Diện tích và chỉ số lưu decimal có scale cố định | Diện tích scale 2, chỉ số đồng hồ scale 3, tỷ lệ sở hữu scale 4. Không suy diễn scale từ dữ liệu nhập | Scale không thống nhất làm import, tính phí và báo cáo cho kết quả khác nhau |
| **ARC-09** | Thời điểm lưu UTC, ranh giới nghiệp vụ tính theo site timezone | Cột thời gian dùng kiểu có timezone và lưu UTC. Mọi ranh giới nghiệp vụ (đầu/cuối kỳ, cutoff, deadline SLA, `[start_at, end_at)` của episode) tính bằng timezone của site rồi mới quy đổi | Đây là chi tiết hóa `DEC-06`, vốn chỉ nói "theo site timezone" mà không nói lưu thế nào |
| **ARC-10** | Khoảng thời gian dùng nửa mở `[start, end)` cho mọi thực thể | Áp dụng thống nhất cho Liability Episode, Fee Policy Version, Unit Relationship, kỳ kế toán. Không thực thể nào dùng `[start, end]` đóng hai đầu | Trộn hai quy ước là nguyên nhân phổ biến nhất của lỗi tính trùng một ngày |
| **ARC-11** | Tỷ lệ và hệ số không được nhân trực tiếp vào tổng tiền | Áp tỷ lệ theo `ALG-02` với thứ tự tường minh, không viết `total * ratio` rải rác trong mã | Làm tròn rải rác gây thất thoát hoặc dư tiền khi cộng các phần |

### 4.3. Đồng thời, khóa và bất biến

Nhóm này phục vụ `AC-09`, `AC-12`, `AC-13`, `AC-15`, `AC-30` và `EX-05`.

| ID | Quyết định | Nội dung bắt buộc | Hệ quả nếu làm khác |
|---|---|---|---|
| **ARC-12** | Chống chạy trùng bằng ràng buộc dữ liệu, không bằng khóa ứng dụng | `Billing Run` có ràng buộc duy nhất trên `(site_id, period_id, fee_type)`. Người thứ hai bấm chốt kỳ nhận lỗi từ database chứ không phụ thuộc một biến khóa trong bộ nhớ tiến trình | Khóa trong tiến trình không hiệu lực khi có hai tiến trình backend; ràng buộc dữ liệu thì luôn đúng |
| **ARC-13** | Sửa dữ liệu đồng thời dùng optimistic concurrency | Mọi bảng nghiệp vụ có cột phiên bản; lệnh cập nhật kèm phiên bản đã đọc, không khớp thì trả `ERR-CONFLICT` và buộc người dùng xem bản mới | Thiếu version làm thay đổi của người lưu trước bị ghi đè âm thầm |
| **ARC-14** | Bút toán chỉ thêm, không sửa không xóa | `AR Entry` và mọi ledger là append-only ở mức quyền dữ liệu: không cấp quyền UPDATE/DELETE cho tài khoản ứng dụng trên các bảng này. Sửa sai chỉ bằng bút toán mới liên kết bút toán gốc | Nếu chỉ dựa vào "lập trình viên không viết câu UPDATE" thì `BR-AR-01` là lời hứa, không phải bất biến |
| **ARC-15** | Số dư luôn được tính, không được lưu | Dư nợ và số dư credit là kết quả tổng hợp từ ledger. Nếu cần tăng tốc thì dùng bảng tổng hợp có thể dựng lại hoàn toàn từ ledger và có kiểm tra đối chiếu định kỳ | Lưu số dư ghi đè được là nguyên nhân trực tiếp của sai sổ `RSK-05` |
| **ARC-16** | Cửa sổ posting kiểm tra ở tầng dữ liệu | Không cho phép ghi bút toán vào kỳ `CLOSED`/`LOCKED` bằng ràng buộc/trigger, không chỉ bằng câu lệnh `if` trong service | `AC-15` yêu cầu "posting đầu bị chặn"; chặn ở service thì một đường ghi khác quên kiểm tra là lọt |

### 4.4. Tệp, quan sát và vận hành

| ID | Quyết định | Nội dung bắt buộc |
|---|---|---|
| **ARC-17** | Tệp lưu ở storage private, truy cập bằng link có thời hạn | Không có tệp nghiệp vụ nào ở đường dẫn công khai. Backend cấp link ngắn hạn sau khi kiểm quyền; metadata gồm checksum, kích thước, MIME đã xác thực và phân loại PII |
| **ARC-18** | Kiểm tra tệp theo allowlist trước, quét mã độc là lớp sau | Bắt buộc: allowlist phần mở rộng và MIME thực (đọc nội dung, không tin phần mở rộng), giới hạn kích thước, checksum, tên tệp chuẩn hóa. Quét mã độc là lớp bổ sung có thể bật sau. Điều này sửa `AC-24` cho khả thi mà vẫn đo được |
| **ARC-19** | Correlation ID xuyên suốt một ý định người dùng | Mỗi request sinh hoặc nhận một correlation ID, gắn vào log, audit event, domain event và thông báo lỗi trả về người dùng. `NFR-11` chỉ kiểm được nếu ID này tồn tại từ đầu |
| **ARC-20** | Sao lưu và phục hồi ở mức chứng minh được | Bắt buộc: sao lưu logic toàn bộ schema và dữ liệu theo chu kỳ ngày, lưu ngoài môi trường chạy, và **một lần diễn tập phục hồi có biên bản** đo được thời gian. Đây là chi tiết hóa `NFR-06` để có thể nghiệm thu bằng bằng chứng thật |

### 4.5. Ràng buộc kiến trúc bắt buộc kiểm tra tại Gate B

- Không có đường ghi nào vào bảng ledger mà bỏ qua service tài chính.
- Không có truy vấn đọc dữ liệu nghiệp vụ nào bỏ qua lớp dựng scope của `ARC-03`.
- Không có phép tính tiền nào nằm ngoài mục 5.
- Không có tệp nghiệp vụ nào truy cập được bằng URL không hết hạn.
- Không có bảng nghiệp vụ nào thiếu cột phiên bản của `ARC-13` và cột scope của mục 2.2.

---

## 5. Thuật toán nghiệp vụ chuẩn hóa

v1.7 yêu cầu ở `BR-FEE-01` rằng fee policy có "cơ sở tính, thuế, min/max, proration và thứ tự làm tròn", và ở `AC-11` rằng "kết quả khớp snapshot đến 0 VND". Nhưng thứ tự đó chưa được viết ra ở đâu. Hai lập trình viên đọc cùng `BR-FEE-01` sẽ cho hai kết quả lệch nhau vài trăm đồng, và không ai chứng minh được ai đúng. Mục này khóa lại các công thức, mỗi công thức có ví dụ tính tay để làm oracle cho fixture của mục 12.1.

### 5.1. Tính tiền và làm tròn

**`ALG-01` Thứ tự tính một dòng phí và thuế.** Thực hiện đúng thứ tự sau, không đảo bước:

```text
1. base        = cơ sở tính (diện tích, số lượng, chỉ số tiêu thụ)
2. gross       = base × unit_price                     [giữ decimal, chưa làm tròn]
3. prorated    = gross × proration_factor (ALG-03)     [giữ decimal, chưa làm tròn]
4. capped      = clamp(prorated, min_amount, max_amount)
5. net         = round_vnd(capped, 1)                  [dòng chi tiết luôn làm tròn đến 1 VND]
6. tax         = round_vnd(net × tax_rate, 1)          [thuế GTGT luôn tính đến 1 VND theo luật thuế]
7. line_total  = net + tax                             [integer VND chính xác]
```

Quy tắc bắt buộc: **Mọi dòng chi tiết (`InvoiceItem`) và tiền thuế VAT bắt buộc tính và lưu trữ chính xác đến 1 VND (`rounding_unit = 1`)** để đảm bảo tuân thủ Luật Thuế GTGT và tránh lỗi tích lũy làm tròn (Cumulative Rounding Error). Quy tắc làm tròn đến 1.000 VND (nếu có) **chỉ áp dụng duy nhất một lần trên TỔNG SỐ TIỀN PHẢI THANH TOÁN CUỐI CÙNG CỦA HÓA ĐƠN**, và phần chênh lệch làm tròn được hạch toán minh bạch vào dòng điều chỉnh `ROUNDING_ADJUSTMENT`.

Ví dụ oracle dòng chi tiết: `base = 80,25 m²`, `unit_price = 12.000 VND/m²`, `proration_factor = 1`, `min = 0`, `max = null`, `tax_rate = 0,08 (8% VAT)`.
`gross = 963.000`; `net = 963.000 VND`; `tax = round_vnd(963.000 × 0,08, 1) = 77.040 VND`; `line_total = 1.040.040 VND`.

Ví dụ oracle làm tròn tổng hóa đơn: Nếu tổng các dòng `line_total = 1.040.040 VND`, khi áp dụng quy chế thu chẵn nghìn:
- Số tiền làm tròn thanh toán = `1.040.000 VND`.
- Dòng bút toán `ROUNDING_ADJUSTMENT` = `-40 VND`. Tổng hóa đơn vẫn cân đối tuyệt đối 100% theo `INV-01`.

**`ALG-02` Áp tỷ lệ nhiều bên.** Khi một khoản phải chia theo tỷ lệ (đồng sở hữu, nhiều episode trong kỳ): tính từng phần bằng `floor(total × ratio_i)` theo integer VND, sau đó **phần dư còn lại cộng vào phần tử có ratio lớn nhất**; nếu bằng nhau thì cộng vào phần tử có khóa nhỏ nhất để kết quả tất định. Tổng các phần luôn bằng đúng tổng gốc.

Ví dụ oracle: `total = 1.000.000`, ba bên tỷ lệ `1/3` mỗi bên. `floor` cho `333.333` mỗi bên, tổng `999.999`, dư `1` cộng vào bên có khóa nhỏ nhất → `333.334 / 333.333 / 333.333`. Tổng khớp `1.000.000`, thỏa `AC-04` và mục 5.3 của `BR` tài chính.

**`ALG-03` Hệ số proration.** `proration_factor = số ngày phục vụ trong kỳ / tổng số ngày của kỳ`, đếm ngày theo timezone site với khoảng nửa mở `[start, end)` của `ARC-10`. Giữ ở dạng decimal đủ scale, không làm tròn thành phần trăm.

Ví dụ oracle: kỳ tháng 9 có 30 ngày, chủ mới nhận trách nhiệm từ `2026-09-11T00:00+07`. Chủ cũ phủ `[09-01, 09-11)` là 10 ngày, hệ số `10/30`. Chủ mới phủ `[09-11, 10-01)` là 20 ngày, hệ số `20/30`. Tổng hai hệ số bằng đúng `1`, không có ngày nào bị đếm hai lần hoặc bỏ sót — đây chính là điều `AC-04` kiểm.

**`ALG-04` Tính tiền theo chỉ số tiêu thụ.** `consumption = (chỉ số cuối − chỉ số đầu) × hệ số nhân`. Nếu chỉ số cuối nhỏ hơn chỉ số đầu thì **không được tự suy diễn vòng lặp đồng hồ**: chặn lại và yêu cầu xác nhận, vì đây có thể là thay đồng hồ hoặc nhập sai. Sau khi có `consumption`, áp `ALG-01` với `base = consumption`. Biểu giá bậc thang tính từng bậc rồi cộng, mỗi bậc là một lần áp bước 2-3, chỉ làm tròn một lần trên tổng.

### 5.2. Phân bổ tiền và công nợ

**`ALG-05` Thứ tự phân bổ một khoản thanh toán.** Chi tiết hóa `BR-PAY-02` và `DEC-08`:

```text
1. Chỉ xét hóa đơn cùng Billing Account với khoản tiền
2. Sắp xếp theo: ngày đến hạn tăng dần → ngày phát hành tăng dần → mã hóa đơn tăng dần
3. Với từng hóa đơn: allocate = min(tiền còn lại, dư nợ mở của hóa đơn)
4. Lặp cho tới khi hết tiền hoặc hết hóa đơn
5. Tiền còn lại sau bước 4 tạo bút toán Overpayment Credit, KHÔNG gắn vào hóa đơn nào
```

Bước 2 phải tất định đến mức không còn chỗ cho ngẫu nhiên — nếu chỉ sắp theo ngày đến hạn thì hai hóa đơn cùng ngày sẽ cho hai kết quả khác nhau giữa hai lần chạy, và `AC-17` không tái lập được.

Ví dụ oracle: hóa đơn A đến hạn `09-05` dư nợ `500.000`, hóa đơn B đến hạn `10-05` dư nợ `700.000`, nhận `1.000.000`. Kết quả: A được `500.000` và đóng, B được `500.000` và còn dư nợ `200.000`, không sinh credit. Nhận `1.300.000` thì A `500.000`, B `700.000`, credit `100.000`.

**`ALG-06` Đảo phân bổ khi tiền bị trả lại.** Khi payment chuyển `RETURNED`/`CHARGEBACK`: sinh bút toán đảo cho **từng** allocation theo thứ tự ngược của lúc phân bổ, mở lại đúng số dư nợ từng hóa đơn, và nếu có credit đã sinh từ khoản tiền đó thì đảo credit trước khi đảo allocation. Bút toán đảo posting vào kỳ `OPEN` hiện tại và trỏ về bút toán gốc, theo `BR-AR-05`. Kỳ gốc không bị chạm.

Thứ tự "credit trước, allocation sau" là bắt buộc: nếu đảo allocation trước, số dư credit có thể đã bị dùng cho hóa đơn khác và hệ thống sẽ tính ra số dư âm không giải thích được.

**`ALG-07` Tính dư nợ tại một thời điểm.** `dư nợ (Billing Account, as_of) = Σ debit − Σ credit` của mọi bút toán có `posted_at ≤ as_of` thuộc account đó. Không lấy từ cột số dư, theo `ARC-15`. Dashboard và drill-down của `AC-25` phải dùng đúng hàm này với đúng một `as_of`, nếu không tổng và chi tiết sẽ lệch do thời điểm đọc khác nhau.

**`ALG-08` Chọn Liability Episode cho một khoảng phục vụ.** Với `[svc_start, svc_end)` cần tính phí: lấy mọi episode giao với khoảng đó, kiểm tra hợp của chúng phủ đúng 100% khoảng phục vụ (`BR-LIA-03`). Nếu có lỗ hổng hoặc chồng lấn thì chặn. Nếu có nhiều episode thì **tách thành nhiều invoice item**, mỗi item một Billing Account và một hệ số `ALG-03` riêng.

### 5.3. Thời gian nghiệp vụ

**`ALG-09` Đồng hồ SLA.** `deadline = start + duration + Σ thời gian tạm dừng hợp lệ`. Chỉ reason code được cấu hình mới tạo được khoảng tạm dừng (`BR-SRV-02`). Mỗi lần pause/resume lưu thành một cặp mốc, deadline luôn tính lại được từ đầu bằng cách phát lại các cặp mốc đó — không lưu deadline như một giá trị cố định bị ghi đè.

Ví dụ oracle: bắt đầu `09-01T08:00+07`, SLA 4 giờ, pause `09:00→11:00` bằng reason hợp lệ. Deadline `= 12:00 + 2 giờ = 14:00`, không phải `12:00`. Pause bằng reason không có trong cấu hình bị từ chối và deadline giữ `12:00` — đây là hai nửa của `AC-07`.

**`ALG-10` Xác định kỳ đích cho một khoản phát sinh.** Nếu `approved_at ≤ period.cutoff_at` thì vào kỳ hiện tại; ngược lại vào kỳ `OPEN` kế tiếp (`BR-FEE-03`, `AC-14`). So sánh thực hiện theo timezone site. Snapshot của kỳ hiện tại không được thay đổi trong cả hai trường hợp.

**`ALG-11` Xác định kỳ đích cho sự kiện đến muộn.** Nếu kỳ gốc của giao dịch đã `LOCKED` thì bút toán mới vào kỳ `OPEN` hiện tại và mang tham chiếu `original_period` cùng `original_entry` (`BR-AR-05`, `AC-20`). Nếu không tồn tại kỳ `OPEN` thì **từ chối posting kèm mã lỗi**, không được ghi tạm vào đâu (`EX-12`).

**`ALG-12` Phát hiện nghi trùng.** Ba mức riêng biệt, không trộn:

| Mức | Đối tượng | Hành vi |
|---|---|---|
| Khóa cứng | `Payment` theo `(site, channel, provider_transaction_id)` | Ràng buộc duy nhất ở dữ liệu, bản thứ hai bị chặn (`BR-PAY-06`, `AC-30`) |
| Khóa cứng | `Pending Charge` theo `cost_line_id` | Một cost line sinh tối đa một charge hợp lệ (`UC-06`) |
| Tín hiệu mềm | `Person` theo số điện thoại/email/giấy tờ | Chỉ cảnh báo và đưa vào hàng đợi review, tuyệt đối không tự gộp (`BR-ID-01`, `EX-03`) |

Phân biệt hai loại này là điểm dễ sai nhất: dùng khóa cứng cho Person sẽ chặn hai người thật cùng số điện thoại gia đình; dùng tín hiệu mềm cho Payment sẽ cho phép ghi trùng tiền.

---

## 6. Mô hình dữ liệu neo và bất biến schema

Mục này không thay ERD của SDD. Nó khóa những ràng buộc mà nếu thiếu thì `BR-*` trở thành lời hứa thay vì bất biến. Nguyên tắc chọn lọc: chỉ ghi ràng buộc nào có một `AC-*` tương ứng kiểm được.

### 6.1. Ràng buộc bắt buộc theo nhóm thực thể

| Nhóm | Ràng buộc bắt buộc ở mức dữ liệu | Bảo vệ điều gì |
|---|---|---|
| Mọi bảng nghiệp vụ | Có `tenant_id`, `site_id`, (`building_id` nếu áp dụng), cột phiên bản, `created_at/by`, `updated_at/by` | Mục 2.2, `ARC-13`, `NFR-05` |
| Space/Unit | Mã căn duy nhất theo `(site_id, code)`; `carpet_area` và `built_up_area` là hai cột độc lập, đều dương | `IDF-02`, phí chỉ tính trên diện tích do policy chỉ định (`DEC-05`) |
| Unit Relationship | Khoảng `[valid_from, valid_to)`; không xóa cứng; tổng tỷ lệ sở hữu tại mọi thời điểm không vượt 100% | `BR-ID-02`, `AC-03` |
| Liability Episode | Khoảng `[start_at, end_at)`; không chồng lấn trong cùng Unit; trỏ đúng một Billing Account | `BR-LIA-01`, `BR-LIA-03`, `AC-04` |
| Fee Policy Version | Không sửa được sau khi publish; khoảng hiệu lực không chồng nhau trong cùng loại phí và site | `BR-FEE-01`, `BR-FEE-02`, `UC-13` |
| Accounting Period | Duy nhất theo `(site_id, year, month)`; trạng thái theo `ST-PER-01`; có `cutoff_at` | `BR-AR-02`, `ALG-10` |
| Billing Run | **Duy nhất theo `(site_id, period_id, fee_type)`** | `BR-AR-03`, `AC-12`, `AC-13`, `ARC-12` |
| Invoice | Số hóa đơn duy nhất theo `(site_id, series, seq)`; không sửa số tiền khi đã `ISSUED` | `BR-AR-01`, `IDF-03`, mục 5.3 v1.7 |
| Invoice Item | Trỏ đúng một Liability Episode và đúng một Billing Account; nếu nguồn là Pending Charge thì khóa duy nhất theo charge đó | `BR-LIA-01`, `ALG-08`, chống posting mồ côi |
| Pending Charge | Duy nhất theo `cost_line_id`; chỉ cost line `RESIDENT` được tạo | `BR-SRV-03`, `ALG-12` |
| AR Entry | Append-only ở mức quyền; có `posted_at`, `period_id`, `billing_account_id`, `reference_entry_id` cho bút toán đảo | `BR-AR-01`, `ARC-14`, `AC-20` |
| Payment | Duy nhất theo `(site_id, channel, provider_transaction_id)` | `BR-PAY-06`, `AC-30` |
| Allocation | Tổng theo payment không vượt tiền khả dụng; tổng theo invoice không vượt dư nợ mở | `BR-PAY-01`, `AC-17` |
| Credit / Deposit / Restricted Fund | **Ba bảng/tài khoản riêng biệt**, không có đường cấn trừ trực tiếp giữa chúng | `BR-AR-04`, `DEC-11`, `AC-19` |
| Refund | Duy nhất theo payout key; mỗi attempt là một bản ghi con có reason/evidence | `BR-PAY-07`, `AC-21` |
| Idempotency Record | Duy nhất theo `(scope, key)`; lưu kết quả đã trả | `EX-02`, `NFR-04`, `ARC-06` |
| Attachment | Có checksum, MIME đã xác thực, kích thước, phân loại PII; không có đường truy cập công khai | `BR-PII-02`, `ARC-17`, `ARC-18`, `AC-24` |
| Audit Event | Append-only; có actor, scope, before/after, reason, correlation ID | `NFR-05`, `ARC-19` |
| Asset / Maintenance Plan | Asset thuộc đúng vị trí; occurrence duy nhất theo `(plan_id, due_at)`; WO sinh ra trỏ ngược occurrence | `BR-AST-01`, `AC-38` |
| Cleaning Shift / Task | Task thuộc đúng ca/khu vực/checklist; kết quả cũ không bị ghi đè khi rework | `BR-ENV-01..02`, `AC-40..41` |
| Patrol / Security Incident | Lượt tuần tra duy nhất theo ca/điểm/cửa sổ; incident severity cao có bản ghi escalation/acknowledgement | `BR-SEC-01..03`, `AC-42..43` |

### 6.2. Ba bất biến phải kiểm được bằng một truy vấn

Đây là điểm khác biệt so với v1.7: các bất biến ở mục 5.3 của v1.7 được phát biểu bằng lời nhưng không nói kiểm bằng cách nào. Ba bất biến sau phải viết được thành truy vấn kiểm tra và chạy trong bộ test hồi quy:

**`INV-01` Cân đối sổ.** Với mọi Billing Account: tổng debit trừ tổng credit trong ledger bằng đúng dư nợ mà hệ thống báo cáo. Sai lệch khác 0 là lỗi chặn release.

**`INV-02` Không có posting mồ côi.** Mọi Invoice Item có nguồn Pending Charge đều trỏ tới một charge tồn tại ở trạng thái `POSTED`, và mọi charge `POSTED` đều có đúng một Invoice Item. Hai chiều đều phải đúng.

**`INV-03` Phủ trách nhiệm tài chính.** Với mọi khoảng phục vụ đã sinh phí: hợp các Liability Episode liên quan phủ đúng 100%, không lỗ hổng, không chồng lấn.

### 6.3. Quy tắc định danh nghiệp vụ

| ID | Quy tắc |
|---|---|
| **IDF-01** | Khóa chính nội bộ dùng định danh không tuần tự, không mang thông tin nghiệp vụ; mã hiển thị cho người dùng là cột riêng |
| **IDF-02** | Mã hiển thị duy nhất trong phạm vi site, không nhất thiết duy nhất toàn tenant. Bộ test isolation cố tình cho hai site trùng mã hiển thị (mục 15.1) nên hệ thống không được giả định duy nhất toàn cục |
| **IDF-03** | Số hóa đơn liên tục theo `(site, series)` và không tái sử dụng; hóa đơn `VOIDED` vẫn giữ số |
| **IDF-04** | Mã nghiệp vụ không nhúng dữ liệu cá nhân, không nhúng số tiền |
| **IDF-05** | Mã PIN bưu phẩm và token truy cập tệp sinh bằng nguồn ngẫu nhiên an toàn, có thời hạn, và lưu dưới dạng băm nếu dùng để xác thực |

---

## 7. Domain event

v1.7 yêu cầu `BR-NOT-01` ("giao dịch lõi commit trước, outbox retry độc lập") và `NFR-05` (audit có correlation ID) nhưng không liệt kê event nào tồn tại. Không có danh mục thì mỗi module tự đặt tên, notification và audit không khớp nhau, và Sequence Diagram không vẽ được.

### 7.1. Danh mục event lõi

| ID | Event | Sinh ra khi | Hệ quả bắt buộc |
|---|---|---|---|
| **EVT-01** | `ImportRunCompleted` | Import kết thúc | Ghi audit, tạo tệp lỗi nếu có |
| **EVT-02** | `PersonMerged` | Merge Person được duyệt | Audit chi tiết ảnh hưởng quan hệ và công nợ |
| **EVT-03** | `UnitRelationshipEnded` | Quan hệ hết hiệu lực | Kiểm tra lại phủ episode (`INV-03`) |
| **EVT-04** | `LiabilityEpisodeChanged` | Tạo/sửa/kết thúc episode | Kiểm tra `BR-LIA-03` trước khi cho phép |
| **EVT-05** | `ServiceRequestCreated` | Tiếp nhận yêu cầu | Khởi động đồng hồ SLA (`ALG-09`), thông báo |
| **EVT-06** | `WorkOrderAssigned` | Phân công | Thông báo người nhận việc |
| **EVT-07** | `WorkOrderCompleted` | WO hoàn thành | Kiểm tra điều kiện `RESOLVED` của request (`BR-SRV-04`) |
| **EVT-08** | `SlaPaused` / `SlaResumed` | Tạm dừng/tiếp tục | Ghi cặp mốc cho `ALG-09` |
| **EVT-09** | `SlaBreached` | Vượt deadline | Escalation, ghi KPI |
| **EVT-10** | `CostLineSubmitted` | KTV gửi chi phí | Sinh Pending Charge nếu bên chịu phí là `RESIDENT` |
| **EVT-11** | `PendingChargeApproved` / `Rejected` | Kế toán quyết định | Xác định kỳ đích theo `ALG-10` |
| **EVT-12** | `FeePolicyVersionPublished` | Publish version | Vô hiệu cache biểu phí, không đổi kỳ đã chốt |
| **EVT-13** | `PeriodStateChanged` | Kỳ chuyển trạng thái | Delta report, mở/đóng cửa sổ posting (`ARC-16`) |
| **EVT-14** | `BillingRunStarted` / `Failed` / `Completed` | Chạy chốt kỳ | Báo cáo bước lỗi, cho phép retry an toàn |
| **EVT-15** | `InvoiceIssued` | Phát hành hóa đơn | Thông báo, khóa sửa số tiền |
| **EVT-16** | `PaymentSettled` | Tiền về chắc chắn | Cho phép phân bổ (`BR-PAY-01`) |
| **EVT-17** | `PaymentAllocated` | Phân bổ xong | Cập nhật dư nợ tính toán, ghi credit nếu dư |
| **EVT-18** | `PaymentReturned` | Tiền bị trả lại | Đảo theo `ALG-06` |
| **EVT-19** | `AdjustmentPosted` | Điều chỉnh/miễn giảm/xóa nợ posting | Audit kèm chứng từ gốc |
| **EVT-20** | `RefundStateChanged` | Refund đổi trạng thái | Ghi attempt, kiểm tra lại số dư khi posting |
| **EVT-21** | `CaseOpened` / `CaseClosed` | Mở/đóng sự vụ | Liên kết đối tượng nguồn |
| **EVT-22** | `NotificationQueued` / `Sent` / `Failed` | Vòng đời outbox | Retry độc lập, hiển thị trạng thái cho người dùng |
| **EVT-23** | `AttachmentQuarantined` | Tệp không đạt kiểm tra | Chặn xem/tải, ghi sự kiện (`AC-24`) |
| **EVT-24** | `PermissionDenied` | Truy cập bị chặn | Ghi nỗ lực truy cập, phục vụ `AC-09` và `AC-01` |
| **EVT-25** | `MaintenanceOccurrenceDue` | Lịch bảo trì đến hạn | Tạo hoặc trả lại WO đã có theo `BR-AST-01` |
| **EVT-26** | `MaintenanceCompleted` | WO bảo trì hoàn tất hợp lệ | Cập nhật lịch sử asset và lần đến hạn kế tiếp |
| **EVT-27** | `CleaningTaskAssigned` | Giao nhiệm vụ vệ sinh | Thông báo đúng nhân viên và khu vực |
| **EVT-28** | `CleaningInspectionFailed` | Nghiệm thu không đạt | Chuyển rework và tạo Case/WO liên kết |
| **EVT-29** | `CleaningTaskAccepted` | Nghiệm thu đạt | Khóa kết quả cũ, ghi KPI chất lượng |
| **EVT-30** | `SecurityShiftHandedOver` | Bàn giao ca | Chốt snapshot tồn đọng và người nhận ca |
| **EVT-31** | `PatrolMissed` | Quá cửa sổ mà chưa hoàn tất | Yêu cầu lý do, hiển thị cảnh báo |
| **EVT-32** | `SecurityIncidentOpened` | Ghi nhận sự cố | Khởi động timeline và SLA theo severity |
| **EVT-33** | `SecurityIncidentEscalated` | Sự cố severity cao | Thông báo người có thẩm quyền và theo dõi acknowledgement |

### 7.2. Quy tắc phát và tiêu thụ event

- Event chỉ được phát **sau khi** giao dịch nghiệp vụ commit thành công. Không có event nào phát trong cùng giao dịch mà việc gửi đi có thể làm rollback nghiệp vụ (`BR-NOT-01`).
- Event mang correlation ID của `ARC-19` và định danh phiên bản dữ liệu tại thời điểm phát.
- Bên tiêu thụ phải xử lý được event trùng (at-least-once), tức là mọi handler là idempotent.
- Event không phải nguồn sự thật: dựng lại trạng thái luôn từ bảng nghiệp vụ và ledger, không từ dòng event.

---

## 8. Vòng đời trạng thái và bảng chuyển trạng thái

### 8.1. Vòng đời trọng yếu

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
| **ST-RUN-01** | Billing Run | `QUEUED → RUNNING → COMPLETED`; `RUNNING → FAILED → RUNNING` | Retry dùng cùng run key; không tạo run mới; `FAILED` giữ báo cáo bước lỗi |
| **ST-NOT-01** | Notification Outbox | `QUEUED → SENDING → SENT`; `SENDING → FAILED → QUEUED`; `FAILED → DEAD_LETTER` | Giới hạn retry; `DEAD_LETTER` phải xử lý tay được; giao dịch nguồn không bị ảnh hưởng |
| **ST-IMP-01** | Import Run | `UPLOADED → VALIDATING → PREVIEWED → APPLIED`; `VALIDATING/APPLYING → FAILED` | Chế độ partial/all-or-nothing chọn trước khi APPLIED; retry theo idempotency key |
| **ST-MNT-01** | Maintenance Occurrence | `DUE → WO_CREATED → IN_PROGRESS → COMPLETED` | `DEFERRED/CANCELLED`; một occurrence chỉ có một WO hoạt động; defer cần lý do |
| **ST-CLN-01** | Cleaning Task | `PLANNED → ASSIGNED → IN_PROGRESS → SUBMITTED → ACCEPTED` | `MISSED/REWORK_REQUIRED/CANCELLED`; người thực hiện không tự nghiệm thu |
| **ST-INC-01** | Security Incident | `NEW → TRIAGED → IN_PROGRESS → RESOLVED → CLOSED` | Severity cao bắt buộc escalation; đóng cần kết luận và bằng chứng |

`ST-RUN-01`, `ST-NOT-01`, `ST-IMP-01` được giữ từ v1.8. `ST-MNT-01`, `ST-CLN-01`, `ST-INC-01` là bổ sung của v1.9 để ba mảng bắt buộc mới có state model và ca nghiệm thu tương ứng.

### 8.2. Bảng chuyển trạng thái mẫu bắt buộc

v1.7 nói "mỗi transition phải có event, actor, guard, timestamp, reason/evidence khi cần và transition cấm" nhưng để trống nội dung. Hai bảng dưới đây là khuôn mẫu bắt buộc; SRS phải hoàn thiện đủ cho mọi `ST-*` theo đúng dạng này.

**`TRN-CHG` Pending Charge**

| Từ | Đến | Actor được phép | Guard | Hành động kèm theo |
|---|---|---|---|---|
| `DRAFT` | `SUBMITTED` | KTV/Trưởng kỹ thuật | Có cost line `RESIDENT`, có evidence | Phát `EVT-10` |
| `SUBMITTED` | `APPROVED` | Kế toán, **khác người submit** | Đủ chứng từ; WO chưa bị hủy | Phát `EVT-11`; xác định kỳ đích bằng `ALG-10` |
| `SUBMITTED` | `REJECTED` | Kế toán | Có lý do bắt buộc | Phát `EVT-11`; WO cần điều chỉnh |
| `REJECTED` | `SUBMITTED` | KTV/Trưởng kỹ thuật | Đã cập nhật CostLine, bổ sung giải trình/chứng từ | Phát `EVT-10` (nộp lại sau chỉnh sửa) |
| `REJECTED` | `CANCELLED` | Kế toán trưởng/Giám đốc | Có lý do hủy thu hoặc chuyển BQL chịu chi phí | Đóng khoản thu, cập nhật CostLine |
| `APPROVED` | `POSTED` | System (billing run) | Kỳ đích ở trạng thái cho posting | Tạo đúng một Invoice Item (`INV-02`) |
| `POSTED` | `REVERSED` | Kế toán + duyệt | Có bút toán đảo hợp lệ | Không xóa bản ghi gốc |
| bất kỳ | `DRAFT` | — | **Cấm tuyệt đối** | Không có đường quay lại DRAFT |
| `POSTED` | `REJECTED` | — | **Cấm tuyệt đối** | Đã posting thì chỉ đảo, không từ chối |

**`TRN-PER` Accounting Period**

| Từ | Đến | Actor được phép | Guard | Hành động kèm theo |
|---|---|---|---|---|
| `OPEN` | `CLOSING` | Kế toán | Preview không còn lỗi chặn | Ngừng nhận charge mới vào kỳ |
| `CLOSING` | `CLOSED` | Kế toán | Mọi billing run `COMPLETED` | Phát `EVT-13`, sinh delta report |
| `CLOSED` | `LOCKED` | Kế toán trưởng | Đối chiếu `INV-01` bằng 0 | Đóng cửa sổ posting ở tầng dữ liệu (`ARC-16`) |
| `LOCKED` | `REOPENED_LIMITED` | Giám đốc duyệt | Có lý do, phạm vi và `expires_at` | Chỉ nhận entry trong phạm vi đã duyệt |
| `REOPENED_LIMITED` | `LOCKED` | System hoặc Kế toán trưởng | Hết hạn hoặc hoàn tất | **Auto-relock bắt buộc**; sinh delta report trước/sau |
| `LOCKED` | `OPEN` | — | **Cấm tuyệt đối** | Không có đường mở lại hoàn toàn |
| `CLOSING` | `OPEN` | Kế toán trưởng | Chưa có invoice nào `ISSUED` | Ghi audit lý do hủy chốt |

---

## 9. Permission matrix

`AC-01` và `NFR-03` yêu cầu "0 lỗi phân quyền ở UI, API, export, file và cache". Không thể kiểm nếu không có ma trận nguồn để sinh test. Mục này định nghĩa cấu trúc quyền và ma trận lõi.

### 9.1. Cấu trúc quyền

`PRM = (role, scope, resource, action, field_policy)`

- **`PRM-01` Deny by default:** tổ hợp không được khai báo thì bị từ chối ở backend.
- **`PRM-02` Scope from session:** role/scope lấy từ phiên, không nhận từ payload do client gửi.
- **`PRM-03` Assigned-only:** nhân viên thực thi chỉ cập nhật bản ghi được giao; quản lý xem theo khu vực được cấp.

- `role`: vai trò tại mục 2.1.
- `scope`: tenant / site / building / assigned-only (chỉ bản ghi được giao).
- `action`: `view`, `create`, `update`, `submit`, `approve`, `post`, `export`, `download`.
- `field_policy`: `full` / `masked` / `hidden` cho từng nhóm trường nhạy cảm.

Nguyên tắc: **deny by default**. Không có dòng nào trong ma trận thì không có quyền, kể cả khi UI hiển thị nút.

### 9.2. Ma trận lõi

| Resource | Admin | Giám đốc | Lễ tân/CSKH | Kế toán | Trưởng KT | KTV | An ninh | Kiểm toán |
|---|---|---|---|---|---|---|---|---|
| Person (thông tin cơ bản) | view/create/update | view | view/create/update | view | view | — | view (masked) | view |
| Person (giấy tờ, PII) | view (audit) | view (audit) | masked | masked | hidden | hidden | hidden | view (audit) |
| Unit / Space | full | view | view | view | view | view (assigned) | view (masked) | view |
| Unit Relationship | full | view | create/update | view | — | — | — | view |
| Liability Episode | view | approve | — | create/update | — | — | — | view |
| Service Request | view | view | create/update | view | view/update | view (assigned) | create | view |
| Work Order | view | view | create | view | create/update/assign | update (assigned) | — | view |
| Cost Line | view | view | — | view | create/submit | create/submit | — | view |
| Pending Charge | view | view | — | **approve/post** | submit | submit | — | view |
| Fee Policy Version | create/update | approve | — | create/submit | — | — | — | view |
| Accounting Period | view | **approve reopen** | — | create/close | — | — | — | view |
| Billing Run | view | approve | — | create/execute | — | — | — | view |
| Invoice | view | view | view | create/issue/void | — | — | — | view |
| Payment / Allocation | view | view | — | create/post | — | — | — | view |
| Adjustment / Waiver / Write-off | view | **approve** | — | create/submit | — | — | — | view |
| Refund | view | **approve** | — | create/submit | — | — | — | view |
| Attachment | download (audit) | download | download (scope) | download | download (WO) | download (assigned) | download (scope) | download (audit) |
| Audit Event | view | view | — | view (tài chính) | — | — | — | view |
| Export | full (audit) | scope | scope (masked) | scope | scope | — | scope (masked) | scope |

Ma trận bổ sung v1.9 cho ba mảng bắt buộc:

| Resource | Admin | Giám đốc | CSKH | Trưởng KT | KTV | Nhân viên vệ sinh | An ninh | Kiểm toán |
|---|---|---|---|---|---|---|---|---|
| Asset / Maintenance Plan | view | view | view | create/update/assign | update (assigned) | — | — | view |
| Maintenance Occurrence | view | view | view | create/update/accept | update (assigned) | — | — | view |
| Cleaning Shift / Task | view | view/accept | create Case/view | view WO liên kết | update WO được giao | update (assigned) | view theo khu vực | view |
| Patrol / Shift Handover | view | view | view khách | — | — | — | create/update (assigned) | view |
| Security Incident / PCCC | view | view/close | create/view | update WO liên kết | update WO được giao | create Case | create/update (assigned) | view |

### 9.3. Ràng buộc phân tách nhiệm vụ

Bốn quy tắc sau đứng **trên** ma trận và không được ghi đè bởi bất kỳ dòng nào:

- Người tạo không được là người duyệt cho cùng một bản ghi (`BR-APR-01`, `AC-09`), kể cả khi vai trò có cả hai quyền.
- Ủy quyền có phạm vi và ngày hết hạn; người nhận ủy quyền không được ủy quyền tiếp.
- Quyền `post` chỉ thuộc kế toán và System; không vai trò nào khác có quyền ghi vào ledger.
- Thu hồi quyền có hiệu lực ở request kế tiếp, không chờ hết phiên (`AC-27` áp dụng cho AI, nhưng quy tắc này áp cho toàn hệ thống).

### 9.4. Cách sinh test từ ma trận

Bộ test quyền sinh tự động theo tổ hợp: mỗi ô trong ma trận sinh một ca dương (được phép, phải thành công) và các ô trống sinh ca âm (không được phép, phải bị chặn ở backend, không chỉ ẩn ở UI). Ca âm phải kiểm cả bốn bề mặt: API, export, tệp và cache. Đây là cách duy nhất `NFR-03` có nghĩa "0 lỗi" thay vì "chưa thấy lỗi".

---

## 10. Mã lỗi nghiệp vụ

`NFR-11` yêu cầu "mọi lỗi nghiệp vụ quan trọng có mã, correlation ID và thông tin xử lý được", nhưng v1.7 không có danh mục mã. Không có mã thì thông báo lỗi sẽ là chuỗi tự do, không tra được và không test được.

### 10.1. Nguyên tắc

Mỗi lỗi có: mã ổn định, thông điệp cho người dùng bằng tiếng Việt nói rõ **làm gì tiếp**, correlation ID của `ARC-19`, và không lộ thông tin nằm ngoài phạm vi người dùng (`AC-01` yêu cầu "không lộ sự tồn tại"). Cụ thể: truy cập bản ghi ngoài scope trả về "không tìm thấy", không trả về "không có quyền" — vì câu thứ hai đã xác nhận bản ghi tồn tại.

### 10.2. Danh mục

| Mã | Tình huống | Thông điệp hướng người dùng | Liên quan |
|---|---|---|---|
| `ERR-SCOPE-NOTFOUND` | Truy cập ngoài phạm vi | "Không tìm thấy dữ liệu" | `AC-01`, mục 10.1 |
| `ERR-PERM-DENIED` | Trong scope nhưng thiếu quyền hành động | "Bạn không có quyền thực hiện. Liên hệ quản trị." | `AC-09`, `EVT-24` |
| `ERR-CONFLICT` | Xung đột phiên bản | "Dữ liệu đã được người khác cập nhật. Xem bản mới rồi thử lại." | `ARC-13`, `EX-05` |
| `ERR-DUPLICATE-KEY` | Vi phạm khóa duy nhất | "Bản ghi này đã tồn tại" kèm mã bản ghi cũ | `ALG-12`, `AC-30` |
| `ERR-IDEMPOTENT-REPLAY` | Gặp lại idempotency key | Trả kết quả lần trước, không phải lỗi hiển thị đỏ | `EX-02`, `ARC-06` |
| `ERR-IMPORT-ROW` | Lỗi từng dòng import | Nêu rõ số dòng, tên cột, lý do | `EX-01`, `AC-02` |
| `ERR-LIA-GAP` | Lỗ hổng phủ trách nhiệm | "Khoảng thời gian chưa có người chịu trách nhiệm tài chính" | `BR-LIA-03`, `INV-03` |
| `ERR-LIA-OVERLAP` | Chồng lấn episode | "Khoảng thời gian bị trùng với bản ghi khác" | `BR-LIA-03`, `EX-04` |
| `ERR-SLA-REASON` | Reason pause không hợp lệ | "Lý do tạm dừng không nằm trong danh mục" | `BR-SRV-02`, `AC-07` |
| `ERR-SOD-SELF-APPROVE` | Tự duyệt | "Người tạo không thể tự duyệt" | `BR-APR-01`, `AC-09` |
| `ERR-PERIOD-CLOSED` | Posting vào kỳ đã đóng | "Kỳ đã chốt. Khoản này sẽ vào kỳ tiếp theo." | `ALG-10`, `AC-14` |
| `ERR-PERIOD-LOCKED` | Posting vào kỳ LOCKED | "Kỳ đã khóa. Cần mở lại có phê duyệt." | `BR-AR-02`, `AC-15` |
| `ERR-NO-OPEN-PERIOD` | Không có kỳ OPEN để nhận bút toán muộn | "Chưa có kỳ mở. Không thể ghi nhận." | `ALG-11`, `EX-12` |
| `ERR-RUN-DUPLICATE` | Chốt kỳ trùng | "Kỳ này đang được chốt bởi phiên khác" | `ARC-12`, `AC-12` |
| `ERR-ALLOC-EXCEED` | Phân bổ vượt số | "Số phân bổ vượt dư nợ hoặc tiền khả dụng" | `BR-PAY-01`, `AC-17` |
| `ERR-PAY-NOT-SETTLED` | Phân bổ khi chưa settled | "Chỉ phân bổ sau khi tiền đã về chắc chắn" | `BR-PAY-01` |
| `ERR-FUND-MIX` | Cấn trừ chéo ba loại quỹ | "Không thể dùng loại quỹ này để thanh toán khoản đó" | `BR-AR-04`, `AC-19` |
| `ERR-REFUND-BALANCE` | Refund thiếu số dư | "Số dư khả dụng không đủ" | `EX-12`, `AC-21` |
| `ERR-INVOICE-IMMUTABLE` | Sửa hóa đơn đã phát hành | "Hóa đơn đã phát hành. Dùng điều chỉnh hoặc credit note." | `BR-AR-01`, `AC-16` |
| `ERR-FILE-REJECTED` | Tệp sai loại/kích thước | Nêu rõ loại và kích thước cho phép | `ARC-18`, `AC-24` |
| `ERR-FILE-QUARANTINED` | Tệp bị cách ly | "Tệp không an toàn và đã bị chặn" | `EVT-23`, `AC-24` |
| `ERR-FILE-INTEGRITY` | Tệp private mất hoặc checksum không khớp | "Không thể xác thực tệp. Hãy tải lại hoặc liên hệ quản trị." | `NFR-09`, `AC-24` |
| `ERR-LINK-EXPIRED` | Link tệp hết hạn | "Liên kết đã hết hạn. Tải lại trang." | `ARC-17`, `NFR-09` |
| `ERR-OFFLINE` | Mất kết nối khi lưu | "Chưa lưu được. Nội dung vẫn còn trên biểu mẫu; hãy kết nối lại và thử lại." **Không báo thành công giả, không hứa đồng bộ offline** | `ARC-05`, `NFR-08` |
| `ERR-MNT-DEFER` | Hoãn bảo trì không hợp lệ | "Cần nhập lý do và thời điểm xử lý mới hợp lệ." | `BR-AST-01`, `EX-23` |
| `ERR-CHECKLIST-INCOMPLETE` | Checklist kỹ thuật/vệ sinh chưa đủ | "Hãy hoàn thành các mục bắt buộc trước khi gửi nghiệm thu." | `BR-AST-02`, `BR-ENV-01` |
| `ERR-PATROL-MISSED` | Lượt tuần tra bị bỏ | "Lượt tuần tra chưa hoàn thành. Hãy nhập lý do." | `BR-SEC-02`, `EX-25` |
| `ERR-ESCALATION-REQUIRED` | Sự cố nghiêm trọng chưa được tiếp nhận | "Sự cố phải được người có thẩm quyền tiếp nhận trước khi đóng." | `BR-SEC-03`, `EX-26` |
| `ERR-AI-NO-SOURCE` | AI không đủ nguồn | "Chưa có căn cứ để trả lời. Chuyển CSKH?" | `BR-AI-04`, `AC-26` |
| `ERR-AI-OUT-OF-SCOPE` | AI bị hỏi ngoài quyền | Không xác nhận dữ liệu tồn tại | `EX-16`, `AC-27` |

---

## 11. Năng lực sản phẩm và lộ trình phát hành

### 11.1. Capability × Release Matrix

| ID | Năng lực | Core MVP | MVP-S | V1 | V2 |
|---|---|---|---|---|---|
| **CAP-PLT** | Nền tảng | Auth, RBAC, Data Scope, audit, search, import/export, tệp, approval, idempotency, outbox | Không | Notification center, delegation | SSO/liên thông mở rộng |
| **CAP-SPC** | Không gian | Site/khu/tòa/tầng/căn, hai loại diện tích, bàn giao | Không | Khu vực chung, lịch sử thay đổi | Floorplan/BIM |
| **CAP-CRM** | Cư dân/CRM | Person, nhiều căn, người đại diện tài chính; merge và Liability Episode là `SPEC-ONLY` | Không | Hợp đồng, tạm trú/tạm vắng, move-in/out, fit-out | OCR có xác minh |
| **CAP-SRV** | Helpdesk/WO | Request, nhiều WO, SLA, checklist, ảnh, cost line, CSAT | Không | Ca/kỹ năng/gợi ý phân công | Tự động hóa nâng cao |
| **CAP-AST** | Kỹ thuật/tài sản | Danh mục tài sản tối thiểu, lịch bảo trì, sinh WO, checklist và kết quả | Không | Đồng hồ, bảo hành, kiểm định, vật tư | Telemetry/dự đoán |
| **CAP-FIN** | Tài chính | Fee policy cơ bản, kỳ tới CLOSED, invoice snapshot, payment thủ công và dư nợ tính lại | Không | Liability Episode, proration, credit/refund/chargeback, VietQR, đối soát | E-invoice/kế toán ngoài |
| **CAP-SEC** | An ninh/an toàn | Bàn giao ca, khách, tuần tra, sự cố/PCCC và escalation | Không | Parcel, xe, thẻ ra vào, bãi xe | ANPR/FaceID/barrier |
| **CAP-ENV** | Vệ sinh/môi trường | Ca/tuyến, nhiệm vụ, checklist, kết quả đạt/không đạt và Case/WO | Không | Rác thải, cảnh quan, cây xanh | Cảm biến môi trường |
| **CAP-AMN** | Tiện ích | Không | Không | Lịch, sức chứa, quota, cọc, waitlist, no-show | Thiết bị check-in |
| **CAP-SCM** | Kho/mua sắm | Không | Không | Nhiều kho, chứng từ, mua hàng, nhà thầu | Tích hợp ERP |
| **CAP-COM** | Truyền thông | Notification Outbox/inbox cho sự kiện lõi | Không | Email/SMS/Push, thông báo Parcel, khảo sát, biểu quyết, cẩm nang | Đa kênh nâng cao |
| **CAP-BI** | Báo cáo | KPI năm nhóm `BUILD`, audit, drill-down/export | Không | Báo cáo Parcel và vận hành mở rộng | Kho dữ liệu/BI ngoài |
| **CAP-AI** | Trợ lý AI | `SPEC-ONLY` | Không | AI-R0..R3 sau Gate D | AI-R4 Action Proposal |

### 11.2. Kế hoạch Core MVP theo năng lực 3 người

| Release | Tuần | Sản phẩm bàn giao | Exit criteria |
|---|---:|---|---|
| **R0 - Product Gate** | 1-2 | Khóa scope, wireflow, UML bắt buộc, dữ liệu mẫu và quyết định P0 | Gate A/B Pass; khoảng 64 h |
| **R1 - Nền tảng và dữ liệu nền** | 3-4 | CAP-PLT, CAP-SPC, CAP-CRM phần `BUILD` | AC-01..03, AC-24, AC-35 Pass; khoảng 80 h |
| **R2 - CSKH và kỹ thuật** | 5-7 | CAP-SRV và lát dọc CAP-AST | AC-06, AC-08..10, AC-38..39 Pass; khoảng 112 h |
| **R3 - Vệ sinh và an ninh** | 8-10 | Lát dọc CAP-ENV và CAP-SEC | AC-40..43 Pass; khoảng 112 h |
| **R4 - Phí và thanh toán cơ bản** | 11-12 | CAP-FIN phần `BUILD`; nhánh phức tạp giữ `SPEC-ONLY` | AC-11..14, AC-16..18, AC-30, AC-44 Pass; khoảng 80 h |
| **R5 - Điều hành và tích hợp demo** | 13-14 | CAP-BI, audit và bốn Golden Flow | AC-22, AC-25, AC-36, AC-45 Pass; khoảng 64 h |
| **Hardening và bảo vệ** | 15-16 | Chạy hồi quy, sửa lỗi, hoàn thiện hồ sơ và diễn tập | Mọi AC/NFR `BUILD` Pass; khoảng 80 h |

Tổng kế hoạch khoảng **592 person-hour**, thấp hơn năng lực bền vững 672 giờ khoảng 80 giờ. Phần dự phòng này dành cho sai số học công nghệ và lỗi tích hợp; không được dùng để mở capability mới trước khi toàn bộ Gate C Pass.

### 11.3. Phụ thuộc bắt buộc

`CAP-PLT → CAP-SPC → CAP-CRM → CAP-SRV`; từ CAP-SRV tách ba nhánh `CAP-AST`, `CAP-ENV`, `CAP-SEC`; nhánh phí đi `CAP-CRM → CAP-FIN`; cuối cùng mọi nhánh hội tụ tại `CAP-BI`.

- CAP-FIN phần `BUILD` cần Billing Account và người đại diện tài chính; Liability Episode/proration là `SPEC-ONLY` và không chặn bản demo.
- Portal cư dân, parcel và tiện ích dùng lại Person, Notification, Case và Payment; không nhân bản.
- Toàn bộ CAP-AI là `SPEC-ONLY` trong học kỳ này; chỉ xem xét lại sau Gate C.
- Bổ sung của v1.8: `ARC-03` (điểm cưỡng chế scope), `ARC-06` (idempotency), `ARC-07`/`ARC-09` (tiền và thời gian) và `ARC-19` (correlation ID) là **hạ tầng chéo**, phải hoàn thành trong R1 vì mọi capability sau đều dựng trên chúng. Bổ sung sau khi đã có ba module là làm lại ba module.

### 11.4. Product Gates

- **Gate A - Ready for Design:** owner, scope, dữ liệu mẫu, UC và DEC P0 đã rõ.
- **Gate B - Ready for Build:** wireflow, state, quyền, BR, ngoại lệ và AC không mâu thuẫn; `ARC-*` đã chốt, `ALG-*` có oracle, ma trận mục 9 được duyệt, mục 4.5 được kiểm và phạm vi mục 11.6 đã đồng bộ sang Project Management Plan.
- **Gate C - Core MVP Complete:** năm Golden Flow và mọi AC/NFR `BUILD` Pass, `INV-01..02` bằng 0 sai lệch, không sửa database thủ công.
- **Gate D - Ready for V1:** phản hồi demo đã phân loại, scope V1 được ưu tiên lại và có chủ sở hữu.

### 11.5. Thứ tự thi hành theo vertical slice

Chuỗi phụ thuộc mục 11.3 là thứ tự **kiến trúc**, không phải lời khuyên làm xong hoàn toàn từng module rồi mới sang module sau. Nếu hiểu theo chiều ngang (làm đủ mọi tính năng của CAP-PLT trước) thì tới cuối R3 vẫn chưa có luồng nào chạy được từ đầu đến cuối, và mọi rủi ro tích hợp dồn vào R4.

Nguyên tắc thi hành: **mỗi release đóng một lát dọc chạy được**, kể cả khi lát đó hẹp.

| Release | Lát dọc phải chạy được cuối release |
|---|---|
| R1 | Đăng nhập → chọn site → import một tệp căn hộ và cư dân → tra cứu 360° một căn → thấy đúng scope và bị chặn khi vượt scope |
| R2 | Tiếp nhận yêu cầu → sinh WO → KTV cập nhật checklist/ảnh; lịch bảo trì đến hạn cũng sinh WO và cập nhật lịch sử tài sản |
| R3 | Ca vệ sinh đi hết checklist và điểm không đạt tạo Case/WO; ca an ninh ghi tuần tra/khách và xử lý một sự cố/PCCC |
| R4 | Phát hành hóa đơn có snapshot → ghi nhận thanh toán thủ công → dư nợ tính lại đúng; không dùng refund/chargeback/proration |
| R5 | Bốn Golden Flow liên tục không sửa database tay, kèm dashboard drill-down và audit bằng correlation ID |

Hệ quả với thứ tự công việc bên trong mỗi release: ưu tiên đường đi đúng (happy path) đủ để lát dọc chạy, sau đó mới bổ sung ngoại lệ `EX-*` theo mức độ mà AC của release đó yêu cầu. Ngoại lệ không được để dồn hết sang R4 vì phần lớn `EX-*` đòi thay đổi cấu trúc dữ liệu, không phải thêm một nhánh `if`.

### 11.6. Implementation Scope - Demo Slice

| Nhóm | `BUILD` - bắt buộc có code | `SPEC-ONLY` - giữ trong SRS/SDD hoặc backlog |
|---|---|---|
| Nền tảng | Đăng nhập, phiên, RBAC 8 vai trò demo, Data Scope, audit, import/export cơ bản, tệp private | Delegation phức tạp, SSO, masking theo từng trường mở rộng |
| Không gian/CRM | Site/tòa/tầng/căn, Person, Unit Relationship và người đại diện thanh toán | Merge Person, Liability Episode, proration chuyển chủ giữa kỳ, hợp đồng đầy đủ |
| CSKH/WO | Tiếp nhận yêu cầu, phân loại, SLA tuyệt đối, nhiều WO, checklist/ảnh, nghiệm thu proxy có lý do, cost line/Pending Charge | Gợi ý phân công, SLA pause/resume nhiều lịch làm việc, portal cư dân |
| Kỹ thuật | Asset tối thiểu, Maintenance Plan, lịch đến hạn sinh WO, checklist và lịch sử | Đồng hồ, bảo hành, kiểm định, vật tư/kho, bảo trì dự đoán |
| Vệ sinh | Ca/tuyến, Cleaning Task, checklist, đạt/không đạt và tạo Case/WO | Rác thải, cảnh quan, cây xanh và cảm biến |
| An ninh/an toàn | Bàn giao ca, khách, lượt tuần tra, sự cố/PCCC, severity và escalation | Xe/thẻ/bãi, bưu phẩm, ANPR/FaceID/barrier |
| Tài chính | Fee Policy cơ bản, kỳ OPEN/CLOSING/CLOSED, invoice snapshot, payment thủ công, unmatched payment, Overpayment Credit cơ bản (bút toán DEPOSIT tiền thừa và AUTO_DEDUCTION cấn trừ nợ kỳ sau), dư nợ tính từ entry | LOCKED/reopen, Liability Episode, refund payout, chargeback, waiver/write-off, Security Deposit, Quỹ bảo trì 2% (Restricted Fund), credit transfer liên căn, VietQR và đối soát tự động |
| Báo cáo | Dashboard theo đúng scope: SLA, bảo trì đến hạn, vệ sinh không đạt, sự cố mở, công nợ; drill-down và audit explorer | Kho dữ liệu, BI ngoài và báo cáo pháp lý |
| AI | — | Toàn bộ CAP-AI |

Các ID `SPEC-ONLY` trọng yếu: UC-09, UC-10, UC-12, UC-14; BR-LIA-02..03, BR-AR-02, BR-AR-05, BR-PAY-04..05, BR-PAY-07, BR-AI-01..04; ST-DSP-01, ST-ADJ-01, ST-WRV-01, ST-RFD-01, ST-PAR-01, ST-AIP-01; AC-04, AC-05, AC-07, AC-15, AC-20..21, AC-23, AC-26..29, AC-31..34, AC-37; NFR-12 (Riêng BR-AR-04 và AC-19: phần Overpayment Credit cơ bản thuộc `BUILD`, phần cấn trừ chéo Quỹ/Deposit và Refund là `SPEC-ONLY`). Các ID còn lại chỉ mang nhãn `BUILD` nếu nằm trong bảng trên.

Quy tắc cắt phạm vi: được giảm số trường, số báo cáo hoặc ngoại lệ P1 trong một lát dọc; không được chuyển toàn bộ CAP-AST, CAP-ENV hoặc CAP-SEC về `SPEC-ONLY`. Nếu một trong bốn mảng bắt buộc chưa có Golden Flow chạy được, Gate C phải Fail.

---

## 12. P0 Control Registry

### 12.1. Quy tắc nghiệp vụ

| ID | Quy tắc bắt buộc | Owner xác nhận |
|---|---|---|
| **BR-SCP-01** | Mọi truy cập dữ liệu/tệp/report/cache áp dụng Data Scope tại backend | Admin/PO |
| **BR-SCP-02** | Export giữ bộ lọc, cột được phép, masking và recipient scope | Admin/PO |
| **BR-ID-01** | Person có 0 hoặc 1 tài khoản chủ động; SĐT/email chỉ là tín hiệu nghi trùng | CSKH |
| **BR-ID-02** | Quan hệ Person–Unit kết thúc hiệu lực thay vì xóa; tổng tỷ lệ sở hữu được kiểm tra theo thời gian | CSKH |
| **BR-LIA-01** | Invoice luôn trỏ đúng một Billing Account; khi Liability Episode được mở ở V1, Invoice Item mới bắt buộc trỏ episode hợp lệ cho service interval | Kế toán |
| **BR-LIA-02** | Chuyển giao giữa kỳ dùng chính sách proration; sửa hồi tố tạo adjustment, không sửa invoice đã phát hành | Kế toán/PO |
| **BR-LIA-03** | Mỗi service interval được Liability Episode phủ đúng 100%; gap/overlap bị chặn, nhiều episode phải tách item theo Billing Account | Kế toán/PO |
| **BR-SRV-01** | Một Service Request có thể sinh nhiều WO; merge/split/duplicate đều lưu liên kết và lý do | Vận hành |
| **BR-SRV-02** | SLA pause/resume chỉ theo reason code được cấu hình; escalation vẫn được audit | Vận hành |
| **BR-SRV-03** | Mỗi cost line có đúng một cost bearer; chỉ `RESIDENT` sinh Pending Charge | Kỹ thuật/Kế toán |
| **BR-SRV-04** | Request chỉ RESOLVED khi mọi WO đã terminal hợp lệ; nghiệm thu dùng resident/proxy, còn deemed acceptance mặc định tắt | Vận hành/PO |
| **BR-AST-01** | Mỗi lần đến hạn của một Maintenance Plan chỉ sinh tối đa một WO; chạy lại scheduler không tạo trùng | Trưởng kỹ thuật |
| **BR-AST-02** | Chỉ hoàn tất bảo trì khi có checklist, kết quả, người thực hiện và bằng chứng; lần đến hạn kế tiếp chỉ cập nhật sau khi WO terminal hợp lệ | Trưởng kỹ thuật |
| **BR-ENV-01** | Cleaning Task phải gắn đúng ca, khu vực, checklist và người thực hiện; không được hoàn tất hộ nếu thiếu lý do/ủy quyền | Quản lý vệ sinh |
| **BR-ENV-02** | Điểm kiểm tra không đạt phải tạo Case hoặc WO liên kết; không được sửa kết quả cũ thành đạt để che lịch sử | Quản lý vệ sinh |
| **BR-SEC-01** | Bàn giao ca, lượt tuần tra và sự cố là timeline chỉ thêm; sửa sai bằng bản ghi đính chính có lý do | Trưởng an ninh |
| **BR-SEC-02** | Mỗi điểm tuần tra bắt buộc có cửa sổ thời gian; bỏ lượt phải ghi lý do và hiển thị trên dashboard | Trưởng an ninh |
| **BR-SEC-03** | Sự cố mức cao/PCCC phải escalation ngay, có người tiếp nhận và không được đóng nếu thiếu kết luận/bằng chứng | Giám đốc/Trưởng an ninh |
| **BR-FEE-01** | Fee policy có phiên bản, hiệu lực, cơ sở tính và thứ tự làm tròn theo `ALG-01`; thuế/min-max/proration nâng cao là `SPEC-ONLY` | Kế toán |
| **BR-FEE-02** | Invoice lưu snapshot đầu vào/công thức; thay policy không đổi kỳ đã chốt | Kế toán |
| **BR-FEE-03** | Pending Charge sau cutoff chuyển kỳ sau theo `ALG-10`; một charge chỉ posting một lần | Kế toán |
| **BR-AR-01** | AR subledger bất biến; sửa sai bằng bút toán đảo/điều chỉnh liên kết chứng từ gốc; cưỡng chế bằng `ARC-14` | Kế toán |
| **BR-AR-02** | Kỳ đi qua OPEN/CLOSING/CLOSED/LOCKED; reopen chỉ ở REOPENED_LIMITED có phạm vi, `expires_at`, delta report và auto-relock theo `TRN-PER` | Kế toán/Giám đốc |
| **BR-AR-03** | Billing Run idempotent theo site/kỳ/loại phí; cưỡng chế bằng ràng buộc duy nhất của `ARC-12` | Kế toán |
| **BR-AR-04** | Overpayment Credit, Security Deposit và Restricted Fund là ledger/account riêng; không tự cấn trừ chéo | Kế toán |
| **BR-AR-05** | Sự kiện đến muộn của kỳ LOCKED được posting vào kỳ OPEN hiện tại theo `ALG-11` và trỏ `original_period/entry` | Kế toán |
| **BR-PAY-01** | Payment chỉ phân bổ sau khi settled; tổng allocation không vượt tiền khả dụng | Kế toán |
| **BR-PAY-02** | Thứ tự phân bổ theo `ALG-05`, trong cùng Billing Account; không tự trả nợ chủ cũ/tài khoản khác | Kế toán |
| **BR-PAY-03** | Payment không xác định đi vào Unmatched; không đoán căn/hóa đơn | Kế toán |
| **BR-PAY-04** | Returned payment/chargeback đảo theo `ALG-06` và mở lại dư nợ bằng bút toán | Kế toán |
| **BR-PAY-05** | Adjustment, waiver, write-off, dispute, refund có reason, evidence, maker-checker và vòng đời riêng | Kế toán/Giám đốc |
| **BR-PAY-06** | Payment có khóa nguồn duy nhất `(site, channel, provider_transaction_id/receipt_no)`; nghi trùng phải review | Kế toán |
| **BR-PAY-07** | Refund giữ beneficiary snapshot, payout reference duy nhất và evidence; retry/returned payout dùng transition, không tạo refund mới | Kế toán |
| **BR-APR-01** | Người tạo không tự duyệt giao dịch nhạy cảm; delegation có phạm vi và ngày hết hạn | Giám đốc |
| **BR-NOT-01** | Giao dịch lõi commit trước; Notification Outbox retry độc lập theo `ST-NOT-01` và giữ recipient/template snapshot | PO |
| **BR-PII-01** | PII có phân loại, masking, retention, legal hold và audit quyền xem/tải | Admin/PO |
| **BR-PII-02** | Tệp private có checksum, loại/kích thước cho phép, kiểm tra theo `ARC-18` và signed access hết hạn | Admin |
| **BR-AI-01** | Backend/domain service là nguồn sự thật; AI không trực tiếp truy cập DB | PO |
| **BR-AI-02** | Retrieval/tool/citation tự kiểm quyền; chỉ tài liệu PUBLISHED đúng scope/hiệu lực được dùng | PO/Admin |
| **BR-AI-03** | AI-R1..R3 chỉ đọc; AI-R4 chỉ tạo draft/proposal trong allowlist; cấm tự duyệt phí, phát hành hóa đơn, hoàn tiền, đổi quyền, tự gửi hoặc bàn giao | PO |
| **BR-AI-04** | Không đủ nguồn hoặc provider lỗi phải từ chối đoán và chuyển sang hỗ trợ an toàn | PO |
| **BR-ARC-01** | Không có đường ghi nào vào ledger, và không có truy vấn đọc nào, bỏ qua điểm cưỡng chế của `ARC-03` và service tài chính | Tech lead |
| **BR-ARC-02** | Mọi phép tính tiền chỉ tồn tại tại mục 5; không có công thức tiền nào viết lặp trong tầng UI hoặc truy vấn báo cáo | Tech lead/Kế toán |

Hai `BR-ARC-*` là bổ sung của v1.8. Lý do: chúng là các quy tắc mà vi phạm sẽ làm vô hiệu hàng loạt `BR-*` khác mà không sinh ra lỗi nhìn thấy được — loại lỗi nguy hiểm nhất, vì hệ thống vẫn chạy và vẫn cho ra số, chỉ là số sai.

### 12.2. Approval Matrix và phân tách nhiệm vụ

| Nghiệp vụ | Người tạo | Người duyệt | Điều kiện demo |
|---|---|---|---|
| Pending Charge | KTV/Trưởng kỹ thuật | Kế toán | Không cùng người; đủ evidence |
| Chốt kỳ/phát hành batch | Kế toán | Kế toán trưởng/Giám đốc | Preview sạch lỗi chặn |
| Adjustment/waiver/write-off | Kế toán | Giám đốc | Mọi số tiền đều cần duyệt trong demo |
| Refund/transfer credit | Kế toán | Giám đốc | Kiểm tra số dư khả dụng trước và ngay khi posting |
| Reopen kỳ LOCKED | Kế toán trưởng | Giám đốc | Lý do, phạm vi, thời hạn mở lại |
| Merge Person | CSKH | Admin/CSKH trưởng | Hiển thị ảnh hưởng quan hệ và công nợ |
| Delegation | Admin/Giám đốc | Người có thẩm quyền cao hơn | Có scope, hiệu lực và thu hồi |
| Publish Fee Policy Version | Kế toán | Giám đốc | Hiển thị kỳ nào bị ảnh hưởng trước khi publish |

### 12.3. Bất biến tài chính

- Tổng debit trừ credit của từng Billing Account tái lập đúng dư nợ tại mọi thời điểm, kiểm bằng `INV-01`.
- Mỗi allocation không vượt `min(payment_available, invoice_open_balance)`; phần tiền còn lại tạo bút toán Credit riêng, không gắn vào invoice.
- Mọi Invoice Item nguồn từ Pending Charge có khóa duy nhất; không tồn tại posting mồ côi, kiểm bằng `INV-02`.
- Invoice đã `ISSUED` không sửa số tiền; adjustment/reversal phải liên kết invoice/item gốc.
- Kỳ `LOCKED` không nhận posting mới; reopen tạo audit và báo cáo chênh lệch trước/sau.
- Tiền cọc/quỹ hạn chế không được dùng thanh toán phí vận hành nếu không có nghiệp vụ chuyển được phê duyệt.
- Tổng các phần sau khi chia tỷ lệ bằng đúng tổng gốc, không thất thoát đồng nào do làm tròn (`ALG-02`).

---

## 13. Exception Registry

| ID | Tình huống | Hành vi bắt buộc | Mã lỗi |
|---|---|---|---|
| **EX-01** | Import lỗi một phần | Cho chọn partial/all-or-nothing; trả đúng dòng/cột/lý do | `ERR-IMPORT-ROW` |
| **EX-02** | Chạy lại import/request/billing/payment | Idempotency key trả kết quả trước hoặc tiếp tục an toàn; không tạo trùng | `ERR-IDEMPOTENT-REPLAY` |
| **EX-03** | Person nghi trùng | Cho so sánh/liên kết/merge theo quyền; không tự gộp | tín hiệu mềm `ALG-12` |
| **EX-04** | Quan hệ/Liability chồng thời gian | Chặn lỗi tài chính; trường hợp cảnh báo cần evidence và phê duyệt | `ERR-LIA-OVERLAP` |
| **EX-05** | Hai người cùng sửa | Optimistic conflict; người lưu sau xem bản mới trước khi thử lại | `ERR-CONFLICT` |
| **EX-06** | SLA bị tạm dừng | Chỉ pause theo reason; deadline mới và lịch sử phải tính lại được | `ERR-SLA-REASON` |
| **EX-07** | WO hủy sau khi có posting | Hủy khoản chưa duyệt; tạo reversal cho khoản đã posting | — |
| **EX-08** | Billing Run lỗi giữa chừng | Trạng thái FAILED theo `ST-RUN-01`; retry không sinh trùng/thiếu và có báo cáo bước lỗi | `ERR-RUN-DUPLICATE` |
| **EX-09** | Charge đến sau cutoff | Chuyển kỳ sau; không chen vào snapshot đã khóa | `ERR-PERIOD-CLOSED` |
| **EX-10** | Tiền thiếu mã | Đưa Unmatched queue; đối soát thủ công có maker-checker | — |
| **EX-11** | Returned payment/chargeback của kỳ đã LOCKED | Posting reversal vào kỳ OPEN hiện tại, mở công nợ và trỏ giao dịch/kỳ gốc | `ERR-PERIOD-LOCKED` |
| **EX-12** | Refund thiếu số dư hoặc kỳ hiện tại chưa OPEN | Từ chối posting; không chỉ cảnh báo ở UI | `ERR-REFUND-BALANCE`, `ERR-NO-OPEN-PERIOD` |
| **EX-13** | Email/SMS/Push lỗi | Retry/fallback theo `ST-NOT-01`; giao dịch nguồn vẫn thành công và inbox hiển thị lỗi | — |
| **EX-14** | Parcel sai PIN/mất/hỏng | Khóa PIN hoặc tạo Case/biên bản; chặn bàn giao thông thường | — |
| **EX-15** | Tệp sai loại/có mã độc | Cách ly, chặn tải/xem và ghi sự kiện; không gắn vào hồ sơ chính thức | `ERR-FILE-REJECTED`, `ERR-FILE-QUARANTINED` |
| **EX-16** | AI thiếu nguồn, ngoài quyền hoặc bị injection | Không xác nhận dữ liệu tồn tại, không gọi tool ngoài allowlist, chuyển người thật | `ERR-AI-NO-SOURCE`, `ERR-AI-OUT-OF-SCOPE` |
| **EX-17** | Chỉ số đồng hồ lùi hoặc nhảy bất thường | Chặn tính phí tự động, yêu cầu xác nhận có lý do; không tự suy diễn vòng lặp đồng hồ (`ALG-04`) | — |
| **EX-18** | Kỳ `REOPENED_LIMITED` hết hạn khi còn posting dở | Auto-relock vẫn thực hiện; posting chưa hoàn tất bị từ chối và phải xin mở lại | `ERR-PERIOD-LOCKED` |
| **EX-19** | Fee policy version được publish khi kỳ đang CLOSING | Chặn publish hoặc buộc chọn hiệu lực từ kỳ sau; không đổi snapshot kỳ đang chốt | — |
| **EX-20** | Notification vượt giới hạn retry | Chuyển `DEAD_LETTER`, hiển thị cho người vận hành xử lý tay; không âm thầm bỏ | — |
| **EX-21** | Mất kết nối khi người dùng đang lưu | Giữ dữ liệu tại form, báo rõ chưa lưu, cho thử lại bằng cùng idempotency key; không báo thành công giả | `ERR-OFFLINE` |
| **EX-22** | Scheduler bảo trì chạy lại cùng kỳ đến hạn | Trả occurrence/WO đã có; không tạo WO thứ hai | `ERR-IDEMPOTENT-REPLAY` |
| **EX-23** | Hoãn bảo trì nhưng thiếu lý do hoặc quá hạn cho phép | Từ chối hoãn; giữ trạng thái DUE và báo quản lý | `ERR-MNT-DEFER` |
| **EX-24** | Nhiệm vụ vệ sinh thiếu điểm kiểm tra hoặc bị đánh giá không đạt | Không cho ACCEPTED; chuyển REWORK_REQUIRED và tạo Case/WO nếu có sự cố | `ERR-CHECKLIST-INCOMPLETE` |
| **EX-25** | Bỏ lượt tuần tra | Ghi nhận ngoại lệ, lý do và cảnh báo trên dashboard; không tự đánh dấu đã tuần tra | `ERR-PATROL-MISSED` |
| **EX-26** | Sự cố an ninh/PCCC mức cao chưa có người tiếp nhận | Giữ mở, escalation tới Giám đốc/Trưởng an ninh và cấm đóng | `ERR-ESCALATION-REQUIRED` |

`EX-17..21` được giữ từ v1.8. `EX-22..26` bổ sung các đường lỗi bắt buộc của bảo trì, vệ sinh và an ninh; nếu thiếu chúng thì ba lát dọc mới chỉ mô tả happy path.

---

## 14. Trợ lý AI nghiệp vụ

Toàn bộ mục 14 mang nhãn `SPEC-ONLY` trong học kỳ này. Nội dung được giữ để bảo toàn tầm nhìn và ràng buộc an toàn, nhưng không nằm trong ngân sách 592 giờ và không phải điều kiện Gate C.

### 14.1. Giá trị và release

| Mốc | Năng lực | Exit gate |
|---|---|---|
| **AI-R0** | Data inventory, câu hỏi thật, threat model, Golden Questions, PoC provider | ACL/RLS, retention, owner nguồn và rubric được duyệt |
| **AI-R1** | Staff RAG hướng dẫn phần mềm/SOP, có citation | Grounding, injection, lifecycle tài liệu và fallback Pass |
| **AI-R2** | Tool chỉ đọc cho invoice/WO/credit/parcel | Permission matrix và số tiền 0 VND sai lệch Pass |
| **AI-R3** | Pilot cư dân tại một tòa | Staff pilot đạt gate; privacy/permission leak bằng 0 |
| **AI-R4** | Soạn nháp và Action Proposal có xác nhận | Approval matrix, anti-replay/expiry/TOCTOU Pass |

Mỗi mốc chỉ bắt đầu khi mốc trước đã Pass. Ở AI-R4, danh sách ghi được phép chỉ gồm tạo nháp Service Request, nháp nội dung trả lời cư dân, bản tóm tắt và đề xuất phân loại; AI không tự gửi. Người dùng xác nhận và domain API kiểm tra lại toàn bộ dữ liệu/quyền trước khi ghi. Danh mục cấm tại `BR-AI-03` là cấm tuyệt đối, không phải ví dụ.

### 14.2. Guardrail trung tâm

- Một AI Gateway ở backend; khóa nhà cung cấp chỉ ở secret store, provider thay qua Adapter.
- Kho tri thức độc lập, chỉ index bản `PUBLISHED`, có version, scope, citation và publish/revoke nguyên tử.
- Ingestion chống data poisoning: nguồn có owner, checksum, malware scan, review và audit trước publish.
- Nội dung tài liệu/tool/user là dữ liệu không tin cậy; không được ghi đè policy hoặc mở rộng quyền.
- Markdown/HTML/link đầu ra được sanitize; citation hết quyền hoặc hết hiệu lực không được hiển thị.
- Provider fallback chỉ dùng khi data class được duyệt; nếu không tương thích thì về keyword search/escalation.
- Conversation/cache/dữ liệu dẫn xuất tuân thủ retention và deletion propagation; trace nhạy cảm mã hóa, tách log thường.
- Model/prompt/index/tool thay đổi phải regression, canary, rollback; kill-switch AI không ảnh hưởng nghiệp vụ lõi.
- Bổ sung của v1.8: AI đọc dữ liệu nghiệp vụ **chỉ qua** cùng lớp cưỡng chế scope của `ARC-03`, dùng đúng phiên và scope của người đang hỏi. Không có đường đọc riêng cho AI, vì một đường đọc riêng là một điểm rò rỉ riêng và làm `AC-27` không kiểm được từ một nguồn ma trận duy nhất.

---

## 15. Nghiệm thu sản phẩm

### 15.1. Bộ dữ liệu kiểm thử chuẩn

- Một tenant, hai site, năm tòa, 2.000 căn, 8.000 Person và quan hệ có lịch sử.
- 12 kỳ phí, 100.000 Invoice Item, 30.000 Payment/Allocation, 10.000 WO và 100.000 audit event.
- 2.000 tài sản/lịch bảo trì, 10.000 Cleaning Task, 20.000 lượt tuần tra và 2.000 sự cố an ninh/PCCC ở Mức B; Mức A dùng tập nhỏ có đủ đường đúng và đường lỗi.
- 30 người dùng đồng thời thuộc tối thiểu 8 vai trò; dữ liệu Site A/B có mẫu cố tình trùng mã hiển thị để kiểm `IDF-02`.
- Một Golden Flow có kết quả tiền cố định và một bộ negative/boundary test cho quyền, trạng thái, rounding, cutoff và concurrency.
- Mỗi AC dùng fixture đã khóa gồm input, business timestamp theo site timezone, expected state, expected ledger entries và exact amount; không chấp nhận "đúng" nếu thiếu oracle.
- Bổ sung của v1.8: các ví dụ oracle tại mục 5 là fixture bắt buộc. Trước khi viết mã tính phí, ba con số `963.000`, `991.000` và bộ `333.334/333.333/333.333` phải tồn tại trong bộ test và fail — sau đó mã mới được viết để làm chúng pass. Nếu fixture viết sau mã thì fixture sẽ mô tả hành vi thực tế thay vì hành vi đúng, và `AC-11` mất ý nghĩa.

Bộ dữ liệu chuẩn có hai mức, để phân biệt kiểm đúng đắn và kiểm hiệu năng:

| Mức | Quy mô | Dùng cho |
|---|---|---|
| **Mức A - Đúng đắn** | 2 site, 200 căn, 2-3 kỳ, dữ liệu biên cố ý | Toàn bộ AC chức năng, `INV-01..03`, test quyền, chạy được ở mọi máy phát triển |
| **Mức B - Hiệu năng** | Quy mô đầy đủ như trên | `NFR-01`, `NFR-02`, kiểm hành vi khi dữ liệu lớn |

Tách hai mức là cần thiết vì bộ test đúng đắn phải chạy được sau mỗi thay đổi; nếu mỗi lần chạy đều cần 100.000 invoice item thì bộ test sẽ bị bỏ.

### 15.2. Acceptance Criteria chức năng

| ID | Kịch bản | Kết quả Pass |
|---|---|---|
| **AC-01** | Nhân viên Site A gọi UI/API/export/file của Site B | 100% bị chặn; trả `ERR-SCOPE-NOTFOUND`, không lộ sự tồn tại hoặc metadata nhạy cảm |
| **AC-02** | Import 1.000 dòng có lỗi/cảnh báo/trùng | Kết quả từng dòng chính xác; retry không tạo trùng |
| **AC-03** | Một Person sở hữu hai căn và thuê căn thứ ba | Tra cứu hai chiều đúng vai trò, tỷ lệ và hiệu lực |
| **AC-04** | Chuyển người chịu nợ tại boundary cố định | Item tách đúng episode/Billing Account theo `ALG-03`/`ALG-08`; nợ cũ giữ chủ cũ; tổng sau rounding khớp 0 VND |
| **AC-05** | Merge hai Person có quan hệ/công nợ | Hiển thị tác động, cần duyệt, không mất liên kết/audit |
| **AC-06** | Một Request tạo hai WO, một WO proxy-accepted | Request chỉ RESOLVED khi cả hai WO terminal; proxy cần role/reason/evidence |
| **AC-07** | Pause/resume SLA bằng reason hợp lệ/không hợp lệ | Deadline tính đúng theo `ALG-09`; reason sai bị chặn |
| **AC-08** | WO có vật tư cư dân trả và nhân công BQL chịu | Hai cost line; chỉ dòng RESIDENT tạo Pending Charge |
| **AC-09** | KTV tự duyệt khoản do mình tạo | Backend từ chối `ERR-SOD-SELF-APPROVE`; audit ghi nỗ lực qua `EVT-24` |
| **AC-10** | Hủy/reopen WO sau khi charge đã posting | Tạo reversal/Case phù hợp; không xóa chứng từ cũ |
| **AC-11** | Tính phí `BUILD` theo cơ sở tính × đơn giá và rounding | Kết quả khớp snapshot đến 0 VND và oracle cơ bản của `ALG-01`; proration/thuế/min-max nâng cao là `SPEC-ONLY` |
| **AC-12** | Hai kế toán chốt cùng site/kỳ | Chỉ một run thắng nhờ `ARC-12`; không trùng/thiếu hóa đơn |
| **AC-13** | Billing Run lỗi rồi retry | Hoàn tất đúng tập invoice và có báo cáo lỗi ban đầu |
| **AC-14** | Charge duyệt sau cutoff | Tự sang kỳ sau theo `ALG-10`; snapshot kỳ hiện tại không đổi |
| **AC-15** | Posting vào LOCKED rồi reopen có thời hạn | Posting đầu bị chặn ở tầng dữ liệu (`ARC-16`); kỳ vào REOPENED_LIMITED, chỉ nhận entry được duyệt, hết hạn tự LOCKED và có delta report |
| **AC-16** | Void invoice chưa trả/đã trả/thuộc LOCKED | Chỉ invoice chưa allocation trong kỳ OPEN sang VOIDED; trường hợp khác dùng Credit Note |
| **AC-17** | Trả một phần/gộp nhiều hóa đơn | Thứ tự phân bổ khớp `ALG-05` và tái lập được; allocation không vượt open balance; phần dư tạo Credit riêng |
| **AC-18** | Chuyển khoản thiếu mã | Vào Unmatched; không giảm công nợ trước khi match được duyệt |
| **AC-19** | Thanh toán thừa | Chỉ phần thừa vào Overpayment Credit; không vào Deposit/Restricted Fund |
| **AC-20** | Chargeback thuộc kỳ đã LOCKED | Kỳ gốc bất biến; reversal theo `ALG-06` vào kỳ OPEN, trỏ original entry và mở đúng công nợ |
| **AC-21** | Refund retry/trùng payout/sai payee/returned payout | Không trả hai lần; cùng refund/payout key, mỗi attempt được audit; FAILED/RETURNED đi đúng transition |
| **AC-22** | Kênh thông báo timeout | Giao dịch nguồn vẫn commit; outbox retry và hiển thị trạng thái |
| **AC-23** | Parcel giao đúng/sai PIN và trường hợp mất | Đúng PIN bàn giao một lần; sai PIN khóa; mất tạo Case và chặn giao |
| **AC-24** | Tải tệp trái quyền hoặc tệp không đạt kiểm tra | Không truy cập/preview; signed link hết hạn; tệp bị chặn theo allowlist của `ARC-18` và cách ly, phát `EVT-23` |
| **AC-25** | Dashboard công nợ/SLA tại một `as_of` cố định | Tổng khớp 100% snapshot/drill-down trong cùng scope và cutoff, cùng dùng `ALG-07` |
| **AC-26** | 50 câu AI held-out và 20 câu thiếu nguồn | ≥90% đạt rubric; Recall@5 ≥90%; citation correctness ≥95%; không bịa |
| **AC-27** | Ma trận AI role × site × unit × cache/history/tool/log | 0 rò rỉ; thu hồi quyền có hiệu lực ở request kế tiếp |
| **AC-28** | Prompt injection và output HTML/link độc hại | 0 lệnh/tool ngoài allowlist; 0 nội dung nguy hiểm được render |
| **AC-29** | Proposal bị sửa, hết hạn, replay hoặc đổi scope | Backend từ chối 100%; không có side effect |
| **AC-30** | Hai người ghi cùng source transaction với idempotency key khác | Chỉ một Payment được tạo; bản còn lại vào suspected-duplicate review |
| **AC-31** | Publish/revoke/re-index/xóa dữ liệu AI | Không trộn version; quyền/xóa lan tới retrieval, citation, cache và dữ liệu dẫn xuất |
| **AC-32** | Chia một khoản cho nhiều bên theo tỷ lệ không chia hết | Tổng các phần bằng đúng tổng gốc; phân bổ phần dư tất định theo `ALG-02`; chạy lại cho kết quả y hệt |
| **AC-33** | Chỉ số đồng hồ mới nhỏ hơn chỉ số cũ | Chặn tính phí tự động, yêu cầu xác nhận có lý do; không tự suy diễn (`EX-17`) |
| **AC-34** | Fee policy version mới publish giữa lúc kỳ đang CLOSING | Kỳ đang chốt giữ nguyên snapshot; version mới chỉ áp từ kỳ sau (`EX-19`) |
| **AC-35** | Đổi site trong cùng phiên rồi mở lại danh sách và tệp vừa xem | Dữ liệu, bộ lọc, cache và link tệp của site cũ không còn truy cập được (`ARC-05`) |
| **AC-36** | Cắt kết nối ngay lúc bấm lưu, sau đó thử lại | Không có bản ghi trùng nhờ cùng idempotency key; không có thông báo thành công giả (`ERR-OFFLINE`) |
| **AC-37** | Chạy truy vấn kiểm tra `INV-01..03` trên bộ dữ liệu Mức A sau Golden Flow | Cả ba trả về 0 dòng sai lệch |
| **AC-38** | Scheduler bảo trì chạy hai lần cho cùng Asset/kỳ đến hạn | Chỉ một Maintenance Occurrence và một WO hoạt động được tạo; lần hai trả kết quả cũ |
| **AC-39** | KTV hoàn tất bảo trì khi thiếu/đủ checklist và ảnh bắt buộc | Thiếu thì bị chặn; đủ thì occurrence COMPLETED, lịch sử tài sản và lần đến hạn kế tiếp cập nhật đúng |
| **AC-40** | Nhân viên vệ sinh thực hiện một ca có nhiều khu vực | Chỉ thấy nhiệm vụ được giao; mỗi nhiệm vụ lưu đủ checklist, thời gian và người thực hiện |
| **AC-41** | Một điểm vệ sinh bị đánh giá không đạt | Task vào REWORK_REQUIRED; Case/WO liên kết được tạo và lịch sử kết quả cũ không bị ghi đè |
| **AC-42** | Một lượt tuần tra bị bỏ qua cửa sổ thời gian | Không tự đánh dấu hoàn thành; yêu cầu lý do và dashboard hiển thị ngoại lệ đúng khu vực |
| **AC-43** | Ghi sự cố an ninh/PCCC severity cao | Escalation tới đúng vai trò, có người tiếp nhận; không thể đóng nếu thiếu kết luận/bằng chứng |
| **AC-44** | Phát hành hóa đơn cơ bản rồi ghi nhận thanh toán thủ công/thiếu mã | Snapshot không đổi; payment hợp lệ giảm đúng dư nợ, payment thiếu mã vào Unmatched và không giảm nợ |
| **AC-45** | Quản lý xem dashboard sau bốn Golden Flow | KPI CSKH, bảo trì, vệ sinh, an ninh và công nợ đều khớp drill-down tại cùng `as_of` và đúng Data Scope |

`AC-32..37` giữ các kiểm tra bổ sung của v1.8. `AC-38..45` là điều kiện bắt buộc để ba mảng bị thiếu và lát dọc tài chính tinh gọn có thể được nghiệm thu bằng bằng chứng.

Phân loại Gate theo v1.9 nằm tại mục 11.2 và 11.6. Mọi AC `SPEC-ONLY` không chặn Gate C, nhưng phải giữ trong Test Plan cho V1. AC-38..45 luôn là `BUILD`; không được bỏ toàn bộ một nhóm AC 38-39, 40-41 hoặc 42-43 để cứu tiến độ.

### 15.3. NFR đo được

| ID | Yêu cầu | Cách xác minh |
|---|---|---|
| **NFR-01** | P95 list/detail ≤2 giây, search ≤3 giây, dashboard ≤5 giây trên bộ dữ liệu Mức B | Load test 30 user đồng thời |
| **NFR-02** | Import 10.000 dòng preview ≤60 giây; tiến trình lớn không khóa UI | Test file chuẩn và khả năng hủy/retry |
| **NFR-03** | 0 lỗi phân quyền/Data Scope ở UI, API, export, file và cache của capability Core đã phát hành | Test sinh từ ma trận mục 9, cả ca dương và ca âm |
| **NFR-04** | Idempotency cho import, billing, posting và payment | Retry/concurrency test |
| **NFR-05** | Audit bất biến có actor, scope, before/after hợp lệ, reason và correlation ID | Truy vết Golden Flow end-to-end bằng một correlation ID |
| **NFR-06** | Sao lưu logic hằng ngày lưu ngoài môi trường chạy; có **một lần diễn tập phục hồi có biên bản** đo được thời gian đạt được | Restore sang môi trường kiểm thử theo `ARC-20` |
| **NFR-07** | 100% luồng MVP thao tác được bằng bàn phím; UI dùng được ở các mức phóng đại màn hình thông dụng | Accessibility và visual test |
| **NFR-08** | Form có loading/empty/error/permission/session/conflict; không báo thành công giả khi mất mạng | Fault-injection và UX checklist |
| **NFR-09** | Tệp private, checksum đúng, signed access hết hạn và kiểm tra theo allowlist | Upload/download negative test |
| **NFR-10** | Dữ liệu nhạy cảm được masking; log thường không chứa secret/giấy tờ đầy đủ/token | Log scan và privacy review |
| **NFR-11** | Mọi lỗi nghiệp vụ quan trọng có mã thuộc mục 10, correlation ID và thông tin xử lý được | Observability checklist đối chiếu danh mục `ERR-*` |
| **NFR-12** | AI permission leak = 0; provider lỗi không làm gián đoạn Core | Security test và kill-switch drill |
| **NFR-13** | Mọi phép tính tiền tái lập được: chạy lại cùng đầu vào và cùng fee policy version cho ra cùng kết quả đến 0 VND | Replay test trên fixture khóa của mục 15.1 |
| **NFR-14** | Bộ test đúng đắn trên dữ liệu Mức A hoàn tất trong ≤10 phút trên máy phát triển chuẩn của nhóm | Ghi cấu hình máy và thời gian chạy bộ test hồi quy trong CI hoặc biên bản test |

`NFR-06` được viết lại so với v1.7. Lý do: v1.7 yêu cầu RPO ≤24 giờ và RTO ≤4 giờ. RPO 24 giờ đạt được bằng sao lưu ngày, nhưng RTO 4 giờ là cam kết về tốc độ phục hồi mà chỉ chứng minh được nếu có hạ tầng dự phòng và quy trình đã diễn tập nhiều lần. Giữ nguyên con số sẽ dẫn tới đánh dấu Pass mà không có bằng chứng, tức là làm hỏng chính nguyên tắc "không chấp nhận đúng nếu thiếu oracle" của mục 15.1. Cách viết mới vẫn đo được và trung thực: có sao lưu, có diễn tập, có số đo thực tế.

`NFR-13` và `NFR-14` là bổ sung. `NFR-13` biến "khớp đến 0 VND" từ một lần kiểm thành thuộc tính bền vững. `NFR-14` bảo vệ chính bộ test: một bộ test đúng nhưng chạy quá lâu sẽ bị bỏ qua, và khi đó mọi bất biến ở trên mất hiệu lực trong thực tế.

### 15.4. Golden Flows

1. **CSKH-to-cash - BUILD:** import căn/người → tiếp nhận yêu cầu → tạo WO kỹ thuật → checklist/ảnh → duyệt cost line → phát hành hóa đơn cơ bản → ghi thanh toán thủ công → dashboard/audit.
2. **Maintenance-to-history - BUILD:** tạo Asset/Maintenance Plan → scheduler sinh đúng một WO → KTV thực hiện checklist/ảnh → nghiệm thu → cập nhật lịch sử và lần đến hạn kế tiếp.
3. **Cleaning-to-case - BUILD:** lập ca/tuyến → nhân viên thực hiện checklist → một điểm không đạt → tạo Case/WO khắc phục → nghiệm thu lại → dashboard chất lượng.
4. **Patrol-to-incident - BUILD:** bàn giao ca → ghi khách/lượt tuần tra → bỏ một lượt có lý do → ghi sự cố/PCCC severity cao → escalation → tiếp nhận/xử lý/đóng.
5. **Control-and-audit - BUILD:** từ một KPI bất kỳ drill-down tới bản ghi nguồn, timeline và người thao tác bằng cùng `as_of`, scope và correlation ID; kiểm tra chéo cả năm nhóm KPI tại `AC-45`.

Hai luồng **Parcel-to-case** và **Ask-to-escalate bằng AI** được giữ ở `SPEC-ONLY`; chúng không thay thế bất kỳ Golden Flow `BUILD` nào khi bảo vệ.

---

## 16. Ma trận truy vết yêu cầu

| Outcome | Capability/UC | Rule/State/Exception | Kiến trúc/Thuật toán | AC/NFR | Release |
|---|---|---|---|---|---|
| OUT-01, OUT-04 | CAP-PLT, CAP-SPC, CAP-CRM; UC-01..03 | BR-SCP-01..02, BR-ID-01..02; ST-IMP-01; EX-01..03, EX-05, EX-15 | ARC-01..06, ARC-08, ARC-10, ARC-17..19; ALG-12 | AC-01..03, AC-24, AC-35; NFR-02..05, NFR-07..11 | R1, R5 |
| OUT-02 | CAP-SRV; UC-04..06 | BR-SRV-01..04, BR-NOT-01, BR-APR-01; ST-SRV-01, ST-WO-01, ST-CHG-01, ST-CAS-01, ST-NOT-01; EX-07, EX-13, EX-20..21 | TRN-CHG; EVT-05..11, EVT-22 | AC-06, AC-08..10, AC-22, AC-36; NFR-05, NFR-08, NFR-11 | R2, R5 |
| OUT-03 | CAP-FIN; UC-07..08, UC-13 | BR-FEE-01..03, BR-AR-01, BR-AR-03, BR-PAY-01..03, BR-PAY-06, BR-APR-01; ST-INV-01, ST-PAY-01, ST-RUN-01; EX-02, EX-08..10 | ARC-07, ARC-09, ARC-12, ARC-14..15; ALG-01, ALG-05, ALG-07, ALG-10, ALG-12; INV-01..02 | AC-11..14, AC-16..18, AC-30, AC-36, AC-44; NFR-04..06, NFR-13 | R4, R5 |
| OUT-05 | CAP-BI; UC-11 | BR-SCP-02, BR-AR-01, BR-AST-02, BR-ENV-02, BR-SEC-02..03 | ARC-19; ALG-07 | AC-25, AC-45; NFR-01, NFR-05, NFR-11 | R5 |
| OUT-06 | CAP-AI; UC-12 | BR-AI-01..04; ST-AIP-01; EX-16 | ARC-03 dùng chung cho AI | AC-26..29, AC-31; NFR-12 | AI-R0..R4 |
| OUT-07 | Xuyên suốt mọi capability; UC-15 | BR-ARC-01..02; mục 12.3 | ARC-03, ARC-12, ARC-14..16; INV-01..02 | AC-01, AC-09, AC-12, AC-30; NFR-03..04, NFR-13..14 | R1, kiểm lại R4-R5 |
| OUT-08 | CAP-AST; UC-16 | BR-AST-01..02; ST-MNT-01; EX-22..23 | ARC-06, ARC-13, ARC-19; EVT-25..26 | AC-38..39; NFR-05, NFR-08, NFR-11 | R2 |
| OUT-09 | CAP-ENV; UC-17 | BR-ENV-01..02; ST-CLN-01, ST-CAS-01; EX-24 | ARC-03, ARC-13, ARC-19; PRM-01..03; EVT-27..29 | AC-40..41; NFR-03, NFR-05, NFR-08 | R3 |
| OUT-10 | CAP-SEC; UC-18 | BR-SEC-01..03; ST-INC-01; EX-25..26 | ARC-03, ARC-13, ARC-19; PRM-01..03; EVT-30..33 | AC-42..43; NFR-03, NFR-05, NFR-11 | R3 |
| OUT-02, OUT-04 | CAP-SEC, CAP-COM; UC-10 `SPEC-ONLY` | BR-SCP-01, BR-NOT-01, BR-PII-01..02; ST-PAR-01; EX-13..15 | IDF-05; EVT-21..23 | AC-23, AC-24 | V1 Parcel |
| OUT-02, OUT-05 | CAP-AMN, CAP-SCM và các phần V1 của mọi CAP | Phải tạo/duyệt UC/BR/ST/EX bổ sung tại Gate D | Kế thừa ARC-*, không tạo kiến trúc song song | Phải tạo AC/NFR trước khi build | V1 backlog |

Quy tắc kiểm tra RTM: không có UC/BR/ST/EX/AC/NFR/ARC/ALG đã baseline mà không truy về Outcome, release và test. Epic V1/V2 không được build cho đến khi có traceability tương đương. Thay đổi rule phải chỉ ra AC, fixture và Golden Flow bị ảnh hưởng.

Bổ sung cột "Kiến trúc/Thuật toán" là thay đổi cấu trúc của RTM so với v1.7. Lý do: v1.7 truy vết từ outcome đến test nhưng bỏ trống phần giữa — cái gì làm cho quy tắc đó thành sự thật trong hệ thống. Với cột mới, khi một `AC-*` fail thì tìm được ngay quyết định kiến trúc hoặc thuật toán chịu trách nhiệm, thay vì phải đọc lại toàn bộ mã.

---

## 17. Risk Register sản phẩm

| ID | Rủi ro | Xác suất/Tác động | Owner | Giảm thiểu | Trigger và phương án dự phòng |
|---|---|---|---|---|---|
| **RSK-01** | Scope vượt năng lực thi hành | Cao/Cao | PO | Khóa `BUILD` theo mục 11.6 và ngân sách 592 h | Trễ mốc >20%: cắt ngoại lệ/tính năng P1 trong từng lát dọc; không bỏ trọn một trong bốn mảng bắt buộc |
| **RSK-02** | Quy tắc phí/pháp lý chưa xác nhận | TB/Cao | Kế toán/PO | Policy version + DEC giả định rõ | Chưa duyệt Gate B: chỉ demo, không production |
| **RSK-03** | Dữ liệu import kém chất lượng | Cao/TB | Admin/CSKH | Preview, validation, dedupe, rollback logic | Lỗi >5%: làm sạch/mapping trước import |
| **RSK-04** | Rò dữ liệu chéo site/role | TB/Rất cao | Admin/Tech lead | `ARC-03` một điểm cưỡng chế, private file, test sinh từ ma trận mục 9 | Bất kỳ leak: dừng release, revoke, điều tra audit |
| **RSK-05** | Sai sổ công nợ/đối soát | TB/Rất cao | Kế toán | Immutable ledger `ARC-14`, số dư tính `ARC-15`, `INV-01..03`, maker-checker | Chênh lệch ≠0: khóa posting, reconcile từ ledger |
| **RSK-06** | AI trả sai/vượt quyền | Cao/Cao | PO/AI owner | RAG citation, read-only, eval, kill-switch | Critical incident: tắt AI, Core vẫn chạy |
| **RSK-07** | Phụ thuộc dịch vụ ngoài | TB/TB | Tech lead | Outbox, timeout, fallback được duyệt | Provider lỗi: queue/manual/keyword mode |
| **RSK-08** | Quyết định kiến trúc bị đảo giữa dự án | TB/Rất cao | Tech lead | `ARC-*` là baseline, đổi phải qua Decision Register và chỉ ra AC/fixture bị ảnh hưởng | Nếu buộc phải đổi `ARC-03`, `ARC-07`, `ARC-09` hoặc `ARC-14` sau R2: coi như làm lại module tài chính, phải giảm scope tương ứng |
| **RSK-09** | Logic tiền bị nhân bản nhiều nơi | Cao/Cao | Tech lead/Kế toán | `BR-ARC-02`; mọi công thức chỉ ở mục 5; review bắt buộc khi có thay đổi liên quan tiền | Phát hiện công thức trùng: gộp về một nơi ngay, không để tới R4 |
| **RSK-10** | Bộ test đúng đắn bị bỏ vì chạy chậm hoặc dữ liệu quá lớn | TB/Cao | Tech lead | Tách dữ liệu Mức A/Mức B (mục 15.1), `NFR-14` | Bộ test bị bỏ qua hai lần liên tiếp: dừng thêm tính năng, tối ưu bộ test trước |
| **RSK-11** | Tập trung quá mức vào tài chính làm thiếu ba mảng vận hành | Cao/Cao | PO/Nhóm | Mỗi mảng có outcome, UC, state, AC, Golden Flow và release riêng | Một nhóm AC 38-39, 40-41 hoặc 42-43 chưa Pass ở cuối R3: dừng mở rộng tài chính và hoàn tất mảng thiếu |

`RSK-08..10` được giữ từ v1.8. `RSK-11` là sửa đổi quan trọng nhất của v1.9 vì chính 1.7/1.8 đã biểu hiện rủi ro này khi đưa CAP-AST, CAP-ENV và CAP-SEC ra khỏi Core.

---

## 18. Decision Register

| ID | Quyết định baseline | Trạng thái | Owner cần xác nhận |
|---|---|---|---|
| **DEC-01** | Core MVP tuần 1-14; tuần 15-16 chỉ hardening, hồ sơ và diễn tập bảo vệ, không nhận capability mới | `BASELINE-BTL` | PO/Nhóm |
| **DEC-02** | Desktop nhân viên ở MVP; portal cư dân ở V1 | `BASELINE-BTL` | PO |
| **DEC-03** | Demo một site; mọi dữ liệu vẫn thiết kế theo tenant/site/building scope | `BASELINE-BTL` | PO/Admin |
| **DEC-04** | Một Service Request có thể sinh nhiều Work Order | `BASELINE-BTL` | Vận hành |
| **DEC-05** | Diện tích tính phí lấy từ fee policy; dữ liệu demo dùng thông thủy, không hardcode | `BASELINE-BTL` | Kế toán |
| **DEC-06** | Liability Episode/proration là `SPEC-ONLY`; bản `BUILD` đổi người đại diện tài chính tại đầu kỳ kế tiếp và giữ nợ cũ ở Billing Account cũ | `BASELINE-BTL` | Kế toán/PO |
| **DEC-07** | Charge sau cutoff sang kỳ sau; late event của kỳ LOCKED posting kỳ OPEN và trỏ kỳ gốc | `BASELINE-BTL` | Kế toán |
| **DEC-08** | Payment trả nợ cũ trước trong cùng Billing Account theo `ALG-05`; override/transfer có preview, quyền và lý do | `BASELINE-BTL` | Kế toán |
| **DEC-09** | MVP hỗ trợ match/đối soát thủ công; tự động ngân hàng thuộc V1 | `BASELINE-BTL` | Kế toán |
| **DEC-10** | Refund/chargeback là `SPEC-ONLY`; khi triển khai V1, kế toán tạo và Giám đốc duyệt | `BASELINE-BTL` | Giám đốc |
| **DEC-11** | Overpayment Credit cơ bản thuộc BUILD (để nhận tiền thừa theo ALG-05 và cấn trừ kỳ sau); Deposit và Restricted Fund là SPEC-ONLY; ba loại không dùng chung ledger/account | `BASELINE-BTL` | Kế toán |
| **DEC-12** | Toàn bộ CAP-AI là `SPEC-ONLY` trong học kỳ; chỉ xem xét sau khi Gate C Pass | `BASELINE-BTL` | PO |
| **DEC-13** | Data Scope cưỡng chế tại tầng service backend là điểm duy nhất; RLS là lưới an toàn deny-by-default, không chứa logic phân quyền | `BASELINE-BTL` | Tech lead/Admin |
| **DEC-14** | Tiền lưu integer VND; làm tròn nửa lên, chỉ một lần, đúng vị trí bước 5-6 của `ALG-01`; `rounding_unit` lấy từ fee policy | `BASELINE-BTL` | Kế toán |
| **DEC-15** | Thời điểm lưu UTC; mọi ranh giới nghiệp vụ tính theo timezone site; mọi khoảng thời gian nửa mở | `BASELINE-BTL` | Kế toán/Tech lead |
| **DEC-16** | Số dư và dư nợ luôn tính từ ledger, không lưu cột số dư ghi đè được | `BASELINE-BTL` | Kế toán |
| **DEC-17** | Chống chạy trùng và chống ghi trùng bằng ràng buộc dữ liệu, không bằng khóa trong tiến trình ứng dụng | `BASELINE-BTL` | Tech lead |
| **DEC-18** | Kiểm tra tệp bắt buộc là allowlist loại/kích thước/MIME thực cộng checksum; quét mã độc là lớp bổ sung có thể bật sau | `BASELINE-BTL` | Admin/PO |
| **DEC-19** | `NFR-06` đo bằng sao lưu ngày cộng một lần diễn tập phục hồi có biên bản, thay cho cam kết RTO chưa chứng minh được | `BASELINE-BTL` | PO/Tech lead |
| **DEC-20** | Bộ dữ liệu kiểm thử tách hai mức: Mức A cho đúng đắn, Mức B cho hiệu năng | `BASELINE-BTL` | PO/QA |
| **DEC-21** | Bốn mảng CSKH, kỹ thuật, vệ sinh, an ninh/an toàn đều có lát dọc `BUILD`; tài chính cơ bản là năng lực hỗ trợ CSKH | `BASELINE-BTL` | PO/Nhóm |
| **DEC-22** | Kế hoạch thi công là 592/672 person-hour; 80 giờ còn lại là dự phòng rủi ro, không phải ngân sách mở scope | `BASELINE-BTL` | PO/Nhóm |
| **DEC-23** | Khi chậm tiến độ chỉ cắt chiều sâu trong một lát dọc; không bỏ toàn bộ CAP-AST, CAP-ENV hoặc CAP-SEC | `BASELINE-BTL` | PO/Nhóm |
| **DEC-24** | `PROJECT_MANAGEMENT_PLAN.md` 1.0 tham chiếu 1.7.1 nên phải cập nhật WBS/UCP/Gantt/RACI theo UC-16..18 và R0..R5 trước Gate B | `OPEN` | PM/Nhóm |

`BASELINE-BTL` là giả định có hiệu lực để thiết kế và chấm đồ án, không thay thế phê duyệt pháp lý/nghiệp vụ khi triển khai thực tế. Mọi thay đổi DEC phải ghi lý do, người duyệt, ngày hiệu lực và các ID bị ảnh hưởng.

`DEC-13..20` giữ các quyết định kiến trúc của v1.8. `DEC-21..24` sửa phạm vi và tính khả thi; riêng `DEC-24` còn `OPEN`, vì vậy roadmap chưa được phép tự nhận là đã khóa hoàn toàn.

---

## 19. Checklist khóa roadmap

### 19.1. Checklist nội dung

- [x] Có tầm nhìn, outcome đo được, ranh giới in/out và baseline phạm vi.
- [x] Có actor chính/phụ (gồm tác nhân hệ thống), Data Scope và thực thể neo đầy đủ.
- [x] Có Use Case Catalog phủ cả cấu hình phí, quản trị kỳ và job hệ thống.
- [x] Có capability/release/dependency/Product Gate và thứ tự thi hành theo lát dọc.
- [x] Có Billing Account, Liability Episode, AR subledger và period lock.
- [x] Có approval/SoD, adjustment/dispute/refund và payment reconciliation.
- [x] Có state đầy đủ gồm billing run, outbox và import run; có bảng chuyển trạng thái mẫu.
- [x] Có kiến trúc thi hành `ARC-*` cho quyền, tiền, thời gian, đồng thời, tệp và quan sát.
- [x] Có thuật toán `ALG-*` với ví dụ oracle tính tay cho mọi phép tính tiền.
- [x] Có mô hình dữ liệu neo, ràng buộc bắt buộc và ba bất biến kiểm được bằng truy vấn.
- [x] Có domain event, permission matrix và danh mục mã lỗi.
- [x] Có AC, NFR, Golden Flow, RTM có cột kiến trúc, risk và decision register.
- [x] Phần AI ngắn gọn, có release, guardrail và acceptance; không lấn át Core MVP.
- [x] Có actor, outcome, UC, state, exception và AC cho kỹ thuật, vệ sinh và an ninh/an toàn.
- [x] Có ranh giới `BUILD`/`SPEC-ONLY`; bốn mảng bắt buộc đều có Golden Flow `BUILD`.
- [x] Kế hoạch 592 giờ nằm trong năng lực bền vững 672 giờ của nhóm 3 người.

### 19.2. Checklist trước khi bắt đầu code

- [ ] Owner thực tế xác nhận DEC-01..24; change request phải được giải quyết và cập nhật baseline.
- [ ] `ARC-01..20` được rà soát và không mâu thuẫn với nhau; mục 4.5 và phạm vi thi công 11.6 được kiểm bằng danh sách cụ thể.
- [ ] `ALG-01..12` có ví dụ oracle được kế toán xác nhận đúng, và đã tồn tại trong bộ test ở trạng thái fail.
- [ ] Wireflow/quyền các UC `BUILD` tại mục 11.6, đặc biệt UC-16..18, được duyệt; UC `SPEC-ONLY` duyệt tại Gate D.
- [ ] Mẫu dữ liệu, fee policy version, rounding unit, cutoff và kết quả tiền Golden Flow được đóng băng.
- [ ] Bảng chuyển trạng thái chi tiết theo khuôn `TRN-*` hoàn thiện cho mọi `ST-*` và đưa vào SRS.
- [ ] Permission matrix mục 9 được kiểm chéo và đã sinh được bộ test ca dương/ca âm.
- [ ] Danh mục `ERR-*` được rà soát để không có mã nào lộ thông tin ngoài scope.
- [ ] Hai truy vấn `INV-01..02` được viết trước module tài chính; `INV-03` theo Liability Episode là `SPEC-ONLY`.
- [ ] Test Plan ánh xạ hai chiều toàn bộ AC/NFR, ghi rõ nhãn thi công và người chịu trách nhiệm.
- [ ] `PROJECT_MANAGEMENT_PLAN.md` được cập nhật theo DEC-24; tổng WBS không vượt ngân sách 592 giờ nếu chưa có quyết định tăng năng lực.

### 19.3. Điều kiện coi là hoàn chỉnh

Roadmap này **đủ nội dung để bắt đầu** SRS, wireflow và SDD, nhưng chưa được coi là `APPROVED BASELINE` cho đến khi checklist 19.2 và `DEC-24` hoàn tất. Ba nhóm nội dung đã được tổ chức như sau:

Nhóm thứ nhất là **cái gì** — outcome, capability, use case, quy tắc nghiệp vụ, vòng đời và ngoại lệ. v1.9 bổ sung đầy đủ ba mảng bắt buộc từng bị đẩy sang V1.

Nhóm thứ hai là **bằng cách nào mà nó thành sự thật** — kiến trúc thi hành, thuật toán, ràng buộc dữ liệu, event, quyền và mã lỗi. Phần chi tiết vẫn phải được hoàn thiện trong SDD thay vì tiếp tục làm phình roadmap.

Nhóm thứ ba là **làm sao biết nó đúng** — AC có oracle, NFR đo được, bất biến kiểm bằng truy vấn, Golden Flow và RTM hai chiều.

Điều kiện chưa đạt: roadmap chưa được owner phê duyệt, Project Management Plan chưa đồng bộ và chưa có test trên hệ thống chạy thật. Vì vậy không tự chấm 10/10 và không dùng từ "hoàn hảo" hoặc "production-ready" trong trạng thái tài liệu.

---

## 20. Tóm tắt sửa đổi v1.9

| Nhóm sửa đổi | Nội dung chính | ID/bằng chứng |
|---|---|---|
| Khôi phục phạm vi đề tài | Đưa kỹ thuật tài sản, vệ sinh môi trường và an ninh/an toàn vào `BUILD` thay vì để toàn bộ ở V1 | OUT-08..10, UC-16..18, AC-38..43 |
| Khôi phục tính khả thi | Áp nhóm 3 người, 592/672 giờ, hai tuần cuối hardening và tách `BUILD/SPEC-ONLY` | Mục 1.3, 11.2, 11.6, DEC-22 |
| Giảm tải tài chính | Giữ hóa đơn/thanh toán/công nợ cơ bản; chuyển proration, refund, chargeback và các quỹ sang `SPEC-ONLY` | CAP-FIN, DEC-06, DEC-10 |
| Hoàn thiện truy vết ba mảng | Thêm actor, entity, rule, state, permission, exception, AC, Golden Flow và RTM | BR-AST/ENV/SEC, ST-MNT/CLN/INC, EX-22..26 |
| Sửa mâu thuẫn kỹ thuật | Thông báo offline không còn hứa lưu/đồng bộ cục bộ trái ARC-05; NFR-14 có ngưỡng đo | ERR-OFFLINE, NFR-14 |
| Trung thực trạng thái | Không tự chấm 10/10; ghi rõ roadmap chưa được owner duyệt và PMP chưa đồng bộ | DEC-24, checklist 19.2 |

v1.9 là bản nên dùng làm nguồn hợp nhất tiếp theo. Không xóa v1.7.1 hoặc v1.8 cho tới khi nhóm duyệt v1.9 và cập nhật mọi tài liệu đang tham chiếu ID cũ.
