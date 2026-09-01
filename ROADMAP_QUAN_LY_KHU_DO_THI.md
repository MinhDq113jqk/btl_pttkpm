# ROADMAP PHẦN MỀM QUẢN LÝ KHU ĐÔ THỊ

> Phiên bản: 1.0
> Ngày lập: 01/09/2026
> Nền tảng đề xuất: Python, PySide6, FastAPI và Supabase
> Đối tượng sử dụng: Ban quản lý khu đô thị, nhân viên vận hành, cư dân và nhà thầu

## 1. Tóm tắt quyết định

Hệ thống được định hướng thành một nền tảng quản lý vận hành khu đô thị tập trung, bao phủ bất động sản, cư dân, công việc, kỹ thuật, tài chính, an ninh, vệ sinh, tiện ích, kho, truyền thông và báo cáo.

Kiến trúc khuyến nghị:

- Ứng dụng desktop cho nhân viên: **PySide6**.
- Backend nghiệp vụ: **FastAPI**.
- Database, Authentication, Storage và Realtime: **Supabase**.
- Cổng cư dân: web/PWA responsive ở giai đoạn sau. Chỉ dùng desktop sẽ không đáp ứng tốt đăng ký khách, đặt tiện ích, nhận thông báo và gửi phản ánh của cư dân.
- Tích hợp ngân hàng, hóa đơn điện tử, SMS, email, IoT và kiểm soát ra vào phải đi qua backend, không gọi trực tiếp từ ứng dụng desktop.

Không nên triển khai toàn bộ 11 phân hệ cùng lúc. Bản MVP tập trung vào chuỗi nghiệp vụ cốt lõi:

**Không gian → Căn hộ → Cư dân → Yêu cầu → Phiếu công việc → Chi phí/Hóa đơn → Báo cáo.**

## 2. Phạm vi và giả định

- Hệ thống ban đầu quản lý một khu đô thị nhưng mô hình dữ liệu có trường `site_id` để mở rộng nhiều khu sau này.
- Dữ liệu dùng múi giờ nghiệp vụ `Asia/Ho_Chi_Minh`; thời gian trong database lưu theo UTC.
- Tiền tệ mặc định là VND và dùng kiểu số chính xác, không dùng số thực dấu phẩy động.
- Bản bài tập lớn sử dụng dữ liệu mẫu và mô phỏng tích hợp bên ngoài.
- Bản production phải xác nhận quy mô căn hộ, người dùng đồng thời, nhà cung cấp tích hợp, SLA và yêu cầu pháp lý trước khi khóa thiết kế.
- Thông tin định danh, hợp đồng, dữ liệu ra vào và dữ liệu tài chính là dữ liệu nhạy cảm, cần phân quyền, che dữ liệu và chính sách lưu giữ riêng.

## 3. Đánh giá tài liệu yêu cầu ban đầu

### 3.1. Điểm mạnh

- Bao phủ rộng và đúng các mảng vận hành chính của một khu đô thị.
- Mỗi phân hệ có mục tiêu nghiệp vụ rõ ràng.
- Đã mô tả một số luồng quan trọng như Work Order, bàn giao, bảo trì, hóa đơn, khách ra vào và đặt tiện ích.
- Có tư duy về SLA, CSAT, MTTR, RBAC, audit log, IoT và tự động hóa.
- Các phân hệ có khả năng liên kết thành chuỗi nghiệp vụ xuyên suốt.

### 3.2. Khoảng trống cần sửa

- Chưa phân biệt MVP, phiên bản 1 và tính năng nâng cao.
- Chưa thể hiện thứ tự phụ thuộc giữa các phân hệ.
- Chưa có kiến trúc frontend/backend và ranh giới bảo mật.
- Chưa có mô hình dữ liệu, quy tắc toàn vẹn và lịch sử thay đổi.
- Chưa có tiêu chí nghiệm thu, chiến lược kiểm thử và Definition of Done.
- Chưa xử lý đầy đủ ngoại lệ tài chính như thanh toán một phần, hoàn tiền, điều chỉnh và webhook trùng.
- Chưa có quản lý thời hạn giấy tờ, hợp đồng, chấp thuận sử dụng dữ liệu và chính sách lưu giữ.
- Chưa có kế hoạch triển khai, giám sát, sao lưu, phục hồi và xử lý sự cố.
- Chưa tách giao diện nhân viên với kênh tự phục vụ của cư dân.
- Phạm vi hiện tại quá lớn nếu thực hiện như một bài tập lớn trong một học kỳ.

### 3.3. Chấm điểm

| Đối tượng đánh giá | Điểm | Nhận xét |
|---|---:|---|
| Danh sách tính năng ban đầu | **8,2/10** | Phủ nghiệp vụ tốt nhưng thiếu ngoại lệ và yêu cầu phi chức năng |
| Tài liệu ban đầu nếu xem là roadmap triển khai | **4,8/10** | Chưa có ưu tiên, kiến trúc, mốc bàn giao, kiểm thử và tiêu chí hoàn thành |
| Roadmap mới trong tài liệu này | **9,2/10** | Có phạm vi, kiến trúc, phụ thuộc, checklist, rủi ro và nghiệm thu; chưa thể đạt 10 vì chưa có quy mô thực tế, nhà cung cấp tích hợp và xác nhận pháp lý |

### 3.4. Rubric chấm roadmap mới

| Tiêu chí | Điểm tối đa | Điểm đạt | Căn cứ |
|---|---:|---:|---|
| Bao phủ nghiệp vụ | 1,00 | 1,00 | Giữ đủ 11 phân hệ và bổ sung nền tảng dùng chung |
| Ưu tiên và thứ tự triển khai | 1,00 | 1,00 | Có MVP, V1, V2 và hai lộ trình theo quy mô |
| Kiến trúc và ranh giới trách nhiệm | 1,00 | 0,95 | Đã tách desktop, API, Supabase, worker và adapter |
| Mô hình và quy tắc dữ liệu | 1,00 | 0,90 | Có nhóm bảng và quy tắc chung; ERD chi tiết chưa được vẽ |
| Bảo mật và riêng tư | 1,00 | 0,95 | Có RBAC, RLS, masking, audit và quản lý secret |
| Kiểm thử và nghiệm thu | 1,00 | 0,95 | Có test strategy, acceptance gate và Definition of Done |
| Triển khai và vận hành | 1,00 | 0,85 | Có CI/CD, logging, backup/restore; hạ tầng thực tế chưa chốt |
| Phụ thuộc và rủi ro | 1,00 | 0,90 | Đã nhận diện phạm vi, tài chính, tích hợp, IoT và dữ liệu |
| Tính khả thi về nguồn lực | 1,00 | 0,75 | Có khung thời gian nhưng chưa biết số người và năng lực nhóm |
| Tính rõ ràng của tài liệu | 1,00 | 0,95 | Có cấu trúc, checklist và kịch bản demo xuyên suốt |
| **Tổng** | **10,00** | **9,20** | Chấm tại thời điểm lập roadmap |

## 4. Các phương án kiến trúc

| Phương án | Mô hình | Ưu điểm | Hạn chế | Điểm phù hợp |
|---|---|---|---|---:|
| A. Desktop kết nối Supabase trực tiếp | PySide6 → Supabase | Nhanh, ít thành phần | Logic dễ phân tán, khó bảo vệ tích hợp và nghiệp vụ tài chính | 6,5/10 |
| **B. Ba tầng, khuyến nghị** | PySide6 → FastAPI → Supabase | Tách nghiệp vụ, dễ kiểm thử, bảo mật và mở rộng | Phải triển khai thêm API | **9,2/10** |
| C. Web-first | React/Next.js → FastAPI → Supabase | Phù hợp nhiều thiết bị, triển khai tập trung | Không còn là ứng dụng thuần Python desktop | 9,0/10 |

### 4.1. Kiến trúc mục tiêu

```text
[PySide6 Desktop cho nhân viên]       [Web/PWA cho cư dân - giai đoạn sau]
                 \                         /
                  +---- HTTPS / REST -----+
                              |
                       [FastAPI Backend]
                  /          |           \
          [Supabase]   [Background Jobs]  [Integration Adapters]
      Postgres/Auth/    nhắc hạn, hóa đơn   ngân hàng, HĐĐT,
      Storage/Realtime  bảo trì, thông báo  SMS, email, IoT
```

### 4.2. Nguyên tắc bảo mật kiến trúc

- Desktop chỉ chứa Supabase URL và `anon key`, tuyệt đối không chứa `service_role key`.
- Desktop dùng Supabase Auth để đăng nhập, sau đó gửi access token cho FastAPI.
- FastAPI xác thực token và kiểm tra quyền trước mỗi nghiệp vụ.
- Truy vấn thông thường nên giữ ngữ cảnh người dùng để Supabase RLS tiếp tục áp dụng.
- `service_role key` chỉ tồn tại trong biến môi trường của backend và chỉ dùng cho tác vụ đặc quyền hoặc chạy nền.
- Mọi webhook thanh toán phải kiểm tra chữ ký, chống gửi lại và có khóa idempotency.

## 5. Công nghệ đề xuất

| Lớp | Công nghệ | Trách nhiệm |
|---|---|---|
| Desktop UI | PySide6, Qt Designer | Giao diện nghiệp vụ cho nhân viên |
| State và validation | Pydantic, Qt Model/View | Kiểm tra dữ liệu và quản lý trạng thái màn hình |
| Backend API | FastAPI | Nghiệp vụ, phân quyền, tích hợp, OpenAPI |
| Database | Supabase PostgreSQL | Dữ liệu giao dịch và báo cáo |
| Authentication | Supabase Auth | Đăng nhập, phiên làm việc, đặt lại mật khẩu |
| File | Supabase Storage | Ảnh hiện trường, hợp đồng, biên bản, tài liệu |
| Realtime | Supabase Realtime | Cập nhật phiếu việc và thông báo khi cần |
| Tác vụ nền | Worker Python; bổ sung Redis/queue khi tải tăng | Nhắc hạn, chốt phí, gửi thông báo, retry tích hợp |
| Test | pytest, pytest-qt | Unit, API, tích hợp và UI smoke test |
| Chất lượng code | Ruff, type checking | Chuẩn hóa và phát hiện lỗi sớm |
| Đóng gói | PyInstaller | Tạo bộ cài Windows |
| CI/CD | GitHub Actions hoặc nền tảng tương đương | Kiểm tra và phát hành tự động |

Phiên bản cụ thể của từng thư viện phải được khóa trong giai đoạn khởi tạo sau khi kiểm tra tương thích.

## 6. Vai trò người dùng

| Vai trò | Phạm vi chính |
|---|---|
| Quản trị hệ thống | Người dùng, vai trò, danh mục, cấu hình, tích hợp |
| Giám đốc Ban quản lý | Dashboard tổng hợp, duyệt và báo cáo |
| Lễ tân/CSKH | Cư dân, khách, phản ánh, bàn giao, thông báo |
| Kế toán | Biểu phí, hóa đơn, thanh toán, công nợ, đối soát |
| Trưởng bộ phận kỹ thuật | Tài sản, kế hoạch bảo trì, phân công, nghiệm thu |
| Kỹ thuật viên | Nhận việc, checklist, vật tư, ảnh trước và sau |
| An ninh | Khách, phương tiện, ra vào, tuần tra, sự cố |
| Vệ sinh/Cảnh quan | Ca trực, tuyến công việc, checklist chất lượng |
| Cư dân/Chủ hộ/Khách thuê | Phản ánh, hóa đơn, khách mời, tiện ích, thông báo |
| Nhà thầu | Công việc được giao, nhân sự, giấy phép và nghiệm thu |
| Kiểm toán viên | Chỉ đọc báo cáo, chứng từ và audit log được cấp quyền |

Quyền phải được cấp theo phạm vi `site`, `zone`, `building` hoặc `department`, không chỉ theo tên vai trò.

## 7. Thiết kế frontend

### 7.1. Cấu trúc giao diện desktop

- Thanh điều hướng bên trái thay đổi theo vai trò.
- Thanh lệnh trên cùng gồm tìm kiếm toàn cục, thông báo và tài khoản.
- Nội dung ưu tiên bảng dữ liệu, bộ lọc, form và lịch; hạn chế dashboard nhiều thẻ trang trí.
- Breadcrumb cho cây không gian: Khu → Phân khu → Tòa → Tầng → Căn.
- Bảng dữ liệu hỗ trợ tìm kiếm, lọc, sắp xếp, phân trang và xuất file theo quyền.
- Form có validation tại trường, cảnh báo khi rời trang chưa lưu và xác nhận cho thao tác rủi ro.
- Trạng thái chuẩn: đang tải, không có dữ liệu, lỗi mạng, hết phiên và không đủ quyền.
- Hỗ trợ bàn phím, độ tương phản rõ, co giãn 125-150% và màn hình laptop phổ biến.

### 7.2. Danh sách màn hình chính

- Đăng nhập, quên mật khẩu và đổi mật khẩu.
- Dashboard theo vai trò.
- Cây không gian và hồ sơ 360 độ của căn hộ.
- Hồ sơ 360 độ của cư dân, hợp đồng, phương tiện và lịch sử cư trú.
- Helpdesk, danh sách/Kanban Work Order và lịch phân công.
- Danh mục tài sản, lịch bảo trì và chỉ số đồng hồ.
- Kỳ phí, hóa đơn, thanh toán, công nợ và đối soát.
- Khách mời, thẻ ra vào, phương tiện, tuần tra và PCCC.
- Ca vệ sinh, kiểm tra chất lượng và cảnh quan.
- Tiện ích, lịch trống, booking và check-in.
- Kho, vật tư, phiếu nhập/xuất và nhà thầu.
- Thông báo, khảo sát, tài liệu và lịch sử gửi.
- Báo cáo, người dùng, vai trò, cấu hình và audit log.

### 7.3. Cổng cư dân giai đoạn sau

- Gửi và theo dõi phản ánh.
- Xem hóa đơn, công nợ và trạng thái thanh toán.
- Đăng ký khách, phương tiện, chuyển đồ và thi công.
- Đặt tiện ích và nhận mã check-in.
- Nhận thông báo, tham gia khảo sát và biểu quyết.
- Quản lý hồ sơ cá nhân và tùy chọn nhận thông báo.

## 8. Thiết kế backend

### 8.1. Các module FastAPI

```text
app/
  api/             # Router /api/v1
  auth/            # Token, RBAC, phạm vi dữ liệu
  properties/      # Không gian và bất động sản
  residents/       # Cư dân, cư trú, hợp đồng
  work_orders/     # Helpdesk, SLA, phân công
  facilities/      # Tài sản, bảo trì, đồng hồ
  billing/         # Phí, hóa đơn, thanh toán
  security/        # Ra vào, khách, xe, tuần tra
  operations/      # Vệ sinh và cảnh quan
  amenities/       # Tiện ích và đặt chỗ
  inventory/       # Kho, mua sắm, nhà thầu
  communications/  # Thông báo, khảo sát
  reports/         # KPI và xuất báo cáo
  integrations/    # Bank, HĐĐT, SMS, email, IoT
  audit/            # Nhật ký bất biến
```

### 8.2. Quy tắc backend bắt buộc

- API có version, mã lỗi thống nhất và request ID.
- Nghiệp vụ thay đổi nhiều bảng phải chạy trong transaction.
- Không hard-delete hóa đơn, thanh toán, cư trú, phiếu việc và audit log.
- Dùng optimistic locking hoặc trường phiên bản cho dữ liệu dễ bị sửa đồng thời.
- Tác vụ nền có retry giới hạn, dead-letter và cảnh báo khi thất bại.
- Mỗi tích hợp bên ngoài có adapter riêng, timeout, retry và nhật ký đối soát.
- File upload phải kiểm tra loại, kích thước, tên và quyền truy cập.

## 9. Danh mục tính năng đã chỉnh sửa và bổ sung

Ký hiệu ưu tiên:

- **MVP:** bắt buộc cho bản bài tập lớn có thể demo trọn luồng.
- **V1:** phiên bản vận hành chuẩn sau MVP.
- **V2:** nâng cao hoặc phụ thuộc thiết bị/nhà cung cấp bên ngoài.

### 9.0. Nền tảng dùng chung

- **MVP:** Đăng nhập, hồ sơ người dùng, RBAC, phạm vi dữ liệu và quản lý phiên.
- **MVP:** Danh mục dùng chung, mã tự sinh, file đính kèm, ghi chú và audit log.
- **MVP:** Tìm kiếm, lọc, phân trang, xuất CSV/Excel theo quyền.
- **V1:** Notification outbox, mẫu thông báo, email/SMS/push và lịch gửi.
- **V1:** Quy trình duyệt cấu hình được và ủy quyền tạm thời khi người duyệt vắng mặt.
- **V1:** Chính sách lưu giữ dữ liệu, che dữ liệu nhạy cảm và xử lý yêu cầu chỉnh sửa hồ sơ.
- **V2:** Đăng nhập đa yếu tố cho vai trò đặc quyền và đăng nhập một lần nếu tổ chức yêu cầu.

### 9.1. Bất động sản và không gian

- **MVP:** Cây phân cấp Site → Zone → Building/Block → Floor → Unit/Space.
- **MVP:** Hồ sơ căn hộ/mặt bằng, diện tích, mục đích sử dụng và trạng thái vận hành.
- **MVP:** Khu vực công cộng và liên kết tài sản kỹ thuật theo vị trí.
- **MVP:** Mã đồng hồ điện/nước, vị trí tủ điện và tài liệu kỹ thuật.
- **V1:** Lịch sử thay đổi chủ sở hữu, hiện trạng bàn giao và tình trạng cho thuê.
- **V1:** Quản lý bản vẽ mặt bằng, phiên bản tài liệu và tọa độ vị trí.
- **V1:** Khóa/đánh dấu căn hộ đang tranh chấp hoặc hạn chế giao dịch nghiệp vụ.
- **V2:** Sơ đồ 2D tương tác, GIS/GeoJSON và liên kết mô hình BIM nếu có nguồn dữ liệu chuẩn.

### 9.2. Cư dân, khách thuê và CRM

- **MVP:** Hồ sơ cá nhân, hộ gia đình, quan hệ với căn hộ và thời gian cư trú.
- **MVP:** Chủ sở hữu, chủ hộ, người thân, khách thuê và người được ủy quyền.
- **MVP:** Hợp đồng thuê/mua, ngày hiệu lực, ngày hết hạn và cảnh báo sắp hết hạn.
- **MVP:** Luồng bàn giao căn hộ, checklist lỗi, ảnh và biên bản.
- **V1:** Move-in/move-out, đăng ký xe tải, khung giờ và phê duyệt liên phòng ban.
- **V1:** Thi công nội thất, hồ sơ bản vẽ, đặt cọc, nhân sự nhà thầu, vi phạm và hoàn cọc.
- **V1:** Theo dõi thời hạn CCCD/hộ chiếu/tạm trú theo chính sách được phê duyệt.
- **V1:** Consent và tùy chọn kênh liên lạc của cư dân.
- **V2:** OCR giấy tờ với bước xác nhận thủ công; không tự động coi dữ liệu OCR là chính xác.

### 9.3. Helpdesk và Work Order

- **MVP:** Tiếp nhận yêu cầu từ lễ tân hoặc cư dân, phân loại và gắn vị trí.
- **MVP:** Mức ưu tiên, SLA phản hồi, SLA xử lý và cảnh báo sắp vi phạm.
- **MVP:** Luồng `NEW → ASSIGNED → IN_PROGRESS → WAITING_ACCEPTANCE → COMPLETED → CLOSED`.
- **MVP:** Trạng thái bổ sung `ON_HOLD`, `CANCELLED`, `REOPENED` kèm lý do bắt buộc.
- **MVP:** Phân công, bình luận, checklist, ảnh trước/sau và lịch sử trạng thái.
- **MVP:** Nghiệm thu, CSAT 1-5 sao và mở lại phiếu có kiểm soát.
- **V1:** Lịch ca trực, kỹ năng nhân viên và gợi ý phân công phù hợp.
- **V1:** Liên kết Work Order với tài sản, vật tư, nhà thầu và chi phí.
- **V1:** Chống tạo phiếu trùng và liên kết sự cố diện rộng với nhiều căn hộ.
- **V2:** Omnichannel hotline, email, chatbot và sự kiện IoT.

### 9.4. Vận hành kỹ thuật và bảo trì tài sản

- **V1:** Danh mục tài sản, mã tài sản, vị trí, thông số, bảo hành và trạng thái.
- **V1:** Kế hoạch bảo trì theo chu kỳ, checklist và tự sinh công việc đến hạn.
- **V1:** Lịch sử sửa chữa, phụ tùng, chi phí và thời gian dừng thiết bị.
- **V1:** Bảo trì theo số giờ chạy/chỉ số, không chỉ theo lịch.
- **V1:** Hiệu chuẩn, kiểm định, giấy phép và cảnh báo hết hạn.
- **V1:** Chỉ số điện/nước đầu nguồn và theo khu vực; cảnh báo sai lệch bất thường.
- **V1:** Phân tích MTBF, MTTR, chi phí vòng đời và đề xuất thay thế.
- **V2:** Telemetry IoT, cảnh báo ngưỡng và bảo trì dự đoán sau khi đủ dữ liệu.

### 9.5. Tài chính, tính phí và hóa đơn

- **MVP:** Danh mục phí, chu kỳ thu, đơn giá theo diện tích và phí xe định kỳ.
- **MVP:** Nhập chỉ số đồng hồ, kiểm tra chỉ số giảm/bất thường và tính phí theo bậc.
- **MVP:** Chốt kỳ, lập hóa đơn, chi tiết khoản phí và theo dõi công nợ.
- **MVP:** Ghi nhận thanh toán thủ công và phân bổ thanh toán vào hóa đơn.
- **MVP:** Trạng thái `DRAFT → ISSUED → PARTIALLY_PAID → PAID/OVERDUE`.
- **V1:** Điều chỉnh, miễn giảm, bù trừ, hoàn tiền và phê duyệt theo hạn mức.
- **V1:** VietQR động, webhook ngân hàng, idempotency và màn hình đối soát ngoại lệ.
- **V1:** Nhắc nợ theo kịch bản và quản lý cam kết thanh toán.
- **V1:** Khóa kỳ có kiểm soát; sửa sai bằng bút toán điều chỉnh thay vì sửa lịch sử.
- **V2:** Hóa đơn điện tử qua adapter VNPT/Viettel/MISA sau khi chốt nhà cung cấp.
- **V2:** Tích hợp phần mềm kế toán và báo cáo thu chi vận hành.

### 9.6. An ninh, kiểm soát ra vào và bãi xe

- **V1:** Hồ sơ phương tiện, thẻ ra vào, thời hạn và liên kết căn hộ.
- **V1:** Đăng ký khách, mã QR, thời gian hiệu lực, người bảo lãnh và nhật ký check-in/out.
- **V1:** Nhật ký mở cổng thủ công với người thực hiện và lý do.
- **V1:** Vé xe cư dân/khách, hạn mức, biểu phí và sự kiện vào/ra.
- **V1:** Tuyến tuần tra, checkpoint, ca trực, bỏ lượt và báo cáo bất thường.
- **V1:** Danh mục thiết bị PCCC, lịch kiểm định và diễn tập khẩn cấp.
- **V1:** Danh sách cần chú ý có thời hạn, lý do và quy trình phê duyệt để tránh lạm dụng.
- **V2:** ANPR, RFID, FaceID, barrier và thang máy qua adapter của nhà cung cấp.
- **V2:** Trung tâm sự cố khẩn cấp, xác nhận đã nhận cảnh báo và nhật ký chỉ huy.

### 9.7. Vệ sinh, môi trường và cảnh quan

- **V1:** Kế hoạch ca, tuyến công việc, khu vực và định mức nhân sự.
- **V1:** Checklist nghiệm thu, ảnh lỗi, yêu cầu làm lại và điểm chất lượng.
- **V1:** Lịch gom rác, rác nguy hại, chứng từ bàn giao và nhà cung cấp xử lý.
- **V1:** Lịch cắt tỉa, tưới, phun thuốc, diệt côn trùng và bảo dưỡng cảnh quan.
- **V1:** Liên kết phản ánh cư dân với ca vệ sinh hoặc nhà thầu chịu trách nhiệm.
- **V2:** Cảm biến thùng rác/môi trường và tối ưu tuyến sau khi có thiết bị thực tế.

### 9.8. Đặt lịch tiện ích

- **V1:** Danh mục tiện ích, lịch mở cửa, sức chứa, giá, cọc và nội quy.
- **V1:** Slot, giới hạn lượt theo căn hộ, chống trùng và danh sách chờ.
- **V1:** Quy trình `PENDING → CONFIRMED → CHECKED_IN → COMPLETED`.
- **V1:** Hủy, hoàn tiền/cọc, no-show và khóa đặt tạm thời theo chính sách.
- **V1:** Đóng tiện ích để bảo trì và tự thông báo cho booking bị ảnh hưởng.
- **V2:** QR check-in, cổng tự động và thanh toán trực tuyến.

### 9.9. Kho, mua sắm và nhà thầu

- **V1:** Nhiều kho, danh mục vật tư, đơn vị tính, lô và mức tồn tối thiểu.
- **V1:** Nhập, xuất, chuyển kho, kiểm kê và điều chỉnh có phê duyệt.
- **V1:** Xuất vật tư theo Work Order và hoàn trả phần chưa sử dụng.
- **V1:** Yêu cầu mua → duyệt → đơn mua → nhận hàng → đối chiếu.
- **V1:** Hồ sơ nhà cung cấp, hợp đồng, bảo hiểm, chứng chỉ và ngày hết hạn.
- **V1:** SLA nhà thầu, đánh giá định kỳ, vi phạm và lịch sử thực hiện.
- **V2:** Mã vạch/QR, máy quét cầm tay và dự báo nhu cầu vật tư.

### 9.10. Truyền thông và cộng đồng

- **V1:** Thông báo theo toàn khu, tòa, nhóm vai trò hoặc căn hộ.
- **V1:** Mức độ, lịch đăng, tệp đính kèm và xác nhận đã đọc với thông báo bắt buộc.
- **V1:** Mẫu email/SMS/push, tùy chọn kênh và lịch sử gửi/thất bại.
- **V1:** Khảo sát, câu hỏi, thời gian mở/đóng và báo cáo kết quả.
- **V1:** Biểu quyết với điều kiện hợp lệ, snapshot quyền biểu quyết và audit log.
- **V1:** Cẩm nang, phiên bản tài liệu, ngày hiệu lực và xác nhận nội quy.
- **V2:** Lịch sự kiện cộng đồng và đăng ký tham gia.

### 9.11. BI, Analytics và quản trị hệ thống

- **MVP:** Dashboard công nợ, SLA Work Order, CSAT và người dùng hoạt động.
- **MVP:** Người dùng, vai trò, quyền hành động và phạm vi dữ liệu.
- **MVP:** Audit log cho thay đổi tài chính, quyền và dữ liệu cư dân.
- **V1:** Báo cáo MTTR, MTBF, tỷ lệ đúng hạn, chi phí bảo trì và tiêu hao năng lượng.
- **V1:** Mở rộng audit log cho thao tác an ninh, kho, nhà thầu và tích hợp.
- **V1:** Bộ lọc theo thời gian/khu/tòa và xuất báo cáo theo quyền.
- **V1:** Theo dõi sức khỏe tích hợp, hàng đợi lỗi và tác vụ nền.
- **V1:** Cấu hình SLA, biểu phí, mẫu thông báo và danh mục mà không sửa code.
- **V2:** Kho dữ liệu/BI riêng khi truy vấn phân tích ảnh hưởng hệ thống giao dịch.

## 10. Mô hình dữ liệu mức cao

### 10.1. Nhóm tổ chức và không gian

- `sites`, `zones`, `buildings`, `floors`, `units`, `common_spaces`.
- `space_documents`, `space_status_history`, `utility_meters`.

### 10.2. Nhóm cư dân

- `profiles`, `persons`, `households`, `unit_relationships`.
- `ownerships`, `leases`, `identity_documents`, `vehicles`.
- `handovers`, `handover_items`, `move_requests`, `fitout_permits`.

### 10.3. Nhóm vận hành

- `service_requests`, `work_orders`, `work_order_assignments`, `work_order_events`.
- `sla_policies`, `checklists`, `checklist_results`, `feedback`.
- `assets`, `maintenance_plans`, `maintenance_tasks`, `meter_readings`.

### 10.4. Nhóm tài chính

- `fee_types`, `fee_rules`, `billing_cycles`, `invoices`, `invoice_items`.
- `payments`, `payment_allocations`, `adjustments`, `debt_reminders`.
- Mọi bảng tiền tệ lưu cả số tiền, loại tiền, kỳ và nguồn phát sinh.

### 10.5. Nhóm dịch vụ và quản trị

- `visitor_passes`, `access_credentials`, `access_events`, `patrol_routes`, `patrol_visits`.
- `amenities`, `amenity_slots`, `bookings`, `booking_events`.
- `warehouses`, `items`, `stock_movements`, `vendors`, `contracts`, `purchase_orders`.
- `announcements`, `audience_targets`, `polls`, `votes`, `documents`.
- `roles`, `permissions`, `role_assignments`, `audit_logs`, `notification_outbox`, `integration_events`.

### 10.6. Quy tắc dữ liệu chung

- Khóa chính UUID; khóa ngoại và unique constraint được khai báo rõ.
- Các bảng nghiệp vụ có `site_id`, `created_at`, `updated_at`, `created_by` khi phù hợp.
- Dữ liệu lịch sử dùng hiệu lực `valid_from`, `valid_to` hoặc bảng event, không ghi đè mất dấu vết.
- File trong Storage dùng đường dẫn theo `site/module/entity`, không dùng URL công khai cho hồ sơ nhạy cảm.
- RLS mặc định từ chối; chỉ mở quyền bằng policy đã kiểm thử.
- Tìm kiếm CCCD, số điện thoại và biển số phải che dữ liệu trên giao diện nếu vai trò không cần xem đầy đủ.

## 11. State machine quan trọng

| Nghiệp vụ | Luồng chính |
|---|---|
| Cư trú | `DRAFT → PENDING_APPROVAL → ACTIVE → EXPIRED/TERMINATED` |
| Work Order | `NEW → ASSIGNED → IN_PROGRESS → WAITING_ACCEPTANCE → COMPLETED → CLOSED` |
| Hóa đơn | `DRAFT → ISSUED → PARTIALLY_PAID → PAID/OVERDUE` |
| Booking | `PENDING → CONFIRMED → CHECKED_IN → COMPLETED` |
| Mua sắm | `DRAFT → SUBMITTED → APPROVED → ORDERED → RECEIVED → CLOSED` |
| Fit-out | `SUBMITTED → REVIEWING → APPROVED → IN_PROGRESS → INSPECTION → CLOSED` |

Mỗi chuyển trạng thái phải quy định vai trò được phép, điều kiện đầu vào, dữ liệu bắt buộc, hành động sau chuyển và nội dung audit log.

## 12. Roadmap triển khai

### 12.1. Lộ trình A: Bài tập lớn/MVP trong 12-16 tuần

#### Giai đoạn 0 - Chốt phạm vi và thiết kế, tuần 1-2

- [ ] Chốt actor, 10-15 use case quan trọng và ma trận quyền.
- [ ] Chốt 4 phân hệ nghiệp vụ lõi: không gian, cư dân, Work Order và hóa đơn đơn giản; nền tảng và báo cáo là phần dùng chung bắt buộc.
- [ ] Vẽ use case, activity/state diagram, ERD và kiến trúc triển khai.
- [ ] Tạo wireframe cho các luồng demo chính.
- [ ] Viết acceptance criteria và dữ liệu mẫu.

**Điều kiện hoàn thành:** phạm vi không còn tính năng chưa có mức ưu tiên; ERD và luồng demo được duyệt.

#### Giai đoạn 1 - Nền tảng kỹ thuật, tuần 3-4

- [ ] Khởi tạo repository, cấu trúc desktop, API và test.
- [ ] Tạo Supabase development project, migration và seed data.
- [ ] Cấu hình Auth, RLS, Storage bucket riêng tư và biến môi trường.
- [ ] Xây login, layout, điều hướng theo vai trò và error handling chung.
- [ ] Thiết lập lint, test và build kiểm tra trong CI.

**Điều kiện hoàn thành:** đăng nhập được; quyền sai bị từ chối cả UI, API và database.

#### Giai đoạn 2 - Không gian và cư dân, tuần 5-7

- [ ] CRUD cây không gian, căn hộ và khu vực chung.
- [ ] Hồ sơ căn hộ, trạng thái và đồng hồ dịch vụ.
- [ ] Hồ sơ cư dân, hộ gia đình và quan hệ với căn hộ.
- [ ] Hợp đồng, thời hạn, bàn giao và file đính kèm.
- [ ] Tìm kiếm, lọc, phân trang và audit log.

**Điều kiện hoàn thành:** truy vết được ai đang ở căn nào tại một thời điểm và lịch sử thay đổi.

#### Giai đoạn 3 - Helpdesk và Work Order, tuần 8-10

- [ ] Tạo phản ánh, phân loại, ưu tiên và SLA.
- [ ] Phân công, chuyển trạng thái, checklist và ảnh trước/sau.
- [ ] Nghiệm thu, CSAT, mở lại và lịch sử thao tác.
- [ ] Dashboard SLA, công việc quá hạn và tải công việc theo nhân viên.

**Điều kiện hoàn thành:** demo trọn luồng từ phản ánh đến đóng phiếu và đánh giá.

#### Giai đoạn 4 - Hóa đơn đơn giản và báo cáo, tuần 11-13

- [ ] Cấu hình phí quản lý và phí xe.
- [ ] Tạo kỳ phí, hóa đơn, công nợ và ghi nhận thanh toán thủ công.
- [ ] Dashboard doanh thu/công nợ và xuất báo cáo.
- [ ] Audit thay đổi hóa đơn và kiểm thử tính tiền.

**Điều kiện hoàn thành:** cùng một dữ liệu đầu vào luôn tạo đúng số tiền mong đợi và không thể sửa lịch sử trái quyền.

#### Giai đoạn 5 - Hoàn thiện và bàn giao, tuần 14-16

- [ ] Chạy unit, API, RLS, UI smoke test và UAT.
- [ ] Kiểm tra lỗi mạng, hết phiên, dữ liệu rỗng và nhập sai.
- [ ] Đóng gói `.exe` và cài thử trên máy sạch.
- [ ] Hoàn thiện README, hướng dẫn cài đặt, tài khoản demo và video/kịch bản trình bày.
- [ ] Chốt báo cáo thiết kế, test case và hạn chế của MVP.

**Điều kiện hoàn thành:** bộ cài chạy được trên máy khác và toàn bộ kịch bản demo vượt qua.

### 12.2. Lộ trình B: Bản production đầy đủ trong 9-15 tháng

| Mốc | Thời gian tham khảo | Phạm vi |
|---|---:|---|
| P0. Discovery và kiến trúc | 3-5 tuần | Quy mô, quy trình, dữ liệu, pháp lý, nhà cung cấp |
| P1. Platform và master data | 4-6 tuần | Auth, RBAC/RLS, audit, không gian, cư dân |
| P2. Core operations | 6-8 tuần | Helpdesk, Work Order, tài sản, bảo trì |
| P3. Finance | 6-10 tuần | Biểu phí, hóa đơn, thanh toán, đối soát |
| P4. Field operations | 6-8 tuần | An ninh, vệ sinh, kho, nhà thầu, tiện ích |
| P5. Resident channel | 5-8 tuần | Web/PWA cư dân, thông báo, khảo sát |
| P6. Integrations | 6-12 tuần | Ngân hàng, HĐĐT, SMS, email, IoT, barrier |
| P7. Hardening và rollout | 4-8 tuần | Hiệu năng, bảo mật, DR, pilot, đào tạo, go-live |

Ước lượng này dành cho nhóm khoảng 6-10 người. Cần lập lại ước lượng sau discovery; không dùng trực tiếp làm cam kết hợp đồng.

## 13. Kiểm thử và tiêu chí chất lượng

### 13.1. Test bắt buộc

- [ ] Unit test cho tính phí, SLA, chuyển trạng thái và phân quyền nghiệp vụ.
- [ ] API integration test cho luồng chính và lỗi dữ liệu.
- [ ] RLS test chứng minh người dùng không xem/sửa dữ liệu ngoài phạm vi.
- [ ] Migration test trên database trống và database có dữ liệu.
- [ ] UI smoke test cho login, CRUD chính và luồng Work Order.
- [ ] Test transaction khi một bước giữa quy trình thất bại.
- [ ] Test webhook trùng, sai chữ ký, đến sai thứ tự và retry.
- [ ] Test file độc hại/sai định dạng/quá dung lượng ở mức phù hợp.
- [ ] UAT theo vai trò với kịch bản nghiệp vụ thực tế.
- [ ] Backup/restore drill trước production.

### 13.2. Mục tiêu phi chức năng ban đầu

- API phổ biến có P95 dưới 1 giây trong điều kiện tải đã thống nhất, không tính thời gian nhà cung cấp ngoài.
- Tìm kiếm danh sách phải phân trang phía server; không tải toàn bộ bảng về desktop.
- Tác vụ chốt phí phải có báo cáo thành công/thất bại và có thể chạy lại an toàn.
- Mọi thay đổi tài chính, quyền và ra vào phải có audit log.
- Production mục tiêu sẵn sàng ban đầu 99,5%; RPO/RTO phải chốt theo gói hạ tầng và yêu cầu vận hành.
- Không ghi access token, giấy tờ định danh hoặc dữ liệu thanh toán đầy đủ vào log.

## 14. Definition of Done cho mỗi tính năng

- [ ] Có mô tả nghiệp vụ và acceptance criteria được duyệt.
- [ ] Có migration, constraint, index và RLS policy khi liên quan dữ liệu.
- [ ] API kiểm tra quyền, validation và trả mã lỗi thống nhất.
- [ ] UI có loading, empty, error, success và permission state.
- [ ] Có audit log cho hành động nhạy cảm.
- [ ] Unit/integration test vượt qua.
- [ ] Không có lỗi lint/type check thuộc phạm vi thay đổi.
- [ ] Tài liệu sử dụng và thay đổi API/database được cập nhật.
- [ ] Đã kiểm tra trên vai trò được phép và vai trò bị cấm.
- [ ] Product owner/người phụ trách nghiệp vụ nghiệm thu.

## 15. Bảo mật, riêng tư và vận hành

- [ ] Áp dụng nguyên tắc ít quyền nhất ở UI, API và RLS.
- [ ] Tách môi trường development, staging và production.
- [ ] Quản lý secret bằng biến môi trường/kho secret; không commit vào Git.
- [ ] Mã hóa khi truyền bằng HTTPS và dùng Storage bucket riêng tư.
- [ ] Che CCCD, số điện thoại, biển số và dữ liệu tài chính theo vai trò.
- [ ] Quy định thời gian lưu giữ từng loại hồ sơ và cơ chế xóa/ẩn hợp lệ.
- [ ] Theo dõi đăng nhập bất thường, thay đổi quyền và thao tác đặc quyền.
- [ ] Rate limit API nhạy cảm và khóa tạm thời khi thử đăng nhập sai nhiều lần.
- [ ] Có cảnh báo lỗi, request ID, log cấu trúc và dashboard sức khỏe dịch vụ.
- [ ] Có runbook cho mất mạng, lỗi tích hợp, sai kỳ phí và khôi phục dữ liệu.

## 16. KPI vận hành

| Nhóm | KPI đề xuất |
|---|---|
| Helpdesk | Tỷ lệ đúng SLA, thời gian phản hồi, MTTR, tỷ lệ mở lại, CSAT |
| Tài chính | Tỷ lệ thu phí, nợ quá hạn, sai lệch đối soát, thời gian chốt kỳ |
| Tài sản | Tỷ lệ bảo trì đúng hạn, MTBF, downtime, chi phí vòng đời |
| An ninh | Sự cố theo khu vực, lượt tuần tra đúng giờ, ngoại lệ ra vào |
| Vệ sinh | Điểm checklist, tỷ lệ làm lại, phản ánh theo khu vực |
| Kho | Vòng quay tồn, hết hàng, chênh lệch kiểm kê, thời gian mua hàng |
| Tiện ích | Công suất sử dụng, no-show, doanh thu và khiếu nại |
| Hệ thống | Người dùng hoạt động, lỗi API, tác vụ nền thất bại, thời gian phục hồi |

## 17. Rủi ro và cách xử lý

| Rủi ro | Mức | Cách xử lý |
|---|---|---|
| Phạm vi 11 phân hệ vượt khả năng học kỳ | Rất cao | Chốt 4 phân hệ nghiệp vụ lõi cùng nền tảng/báo cáo; các phần còn lại dùng prototype/backlog |
| Sai công thức hoặc lịch sử tài chính | Rất cao | Decimal, test theo bảng mẫu, khóa kỳ và điều chỉnh có audit |
| Lộ dữ liệu cư dân | Rất cao | RBAC + RLS, masking, log tối thiểu, kiểm thử quyền |
| Tích hợp ngân hàng/HĐĐT chưa sẵn sàng | Cao | Adapter, mock sandbox và đối soát thủ công dự phòng |
| Thiết bị IoT/barrier khác giao thức | Cao | Chốt vendor trước, adapter riêng, không đưa vào MVP |
| Desktop mất mạng | Trung bình | Timeout rõ, retry an toàn, lưu draft cục bộ; offline sync là V2 |
| Dữ liệu gốc không sạch | Cao | Template nhập, validation, import preview và báo cáo lỗi |
| Người dùng khó chấp nhận quy trình mới | Trung bình | Pilot một tòa, đào tạo theo vai trò và thu feedback |
| Báo cáo làm chậm giao dịch | Trung bình | Index, query view/materialized view; tách BI khi cần |

## 18. Checklist quyết định trước khi bắt đầu code

- [ ] Chọn lộ trình BTL/MVP hay production.
- [ ] Xác định số khu, tòa, căn hộ và người dùng dự kiến.
- [ ] Chốt vai trò và phạm vi dữ liệu của từng vai trò.
- [ ] Chốt 4 phân hệ nghiệp vụ lõi, phần nền tảng/báo cáo và danh sách tính năng loại khỏi MVP.
- [ ] Chốt các công thức phí và bộ dữ liệu tính mẫu.
- [ ] Chốt quy trình Work Order và giá trị SLA thực tế.
- [ ] Chốt loại giấy tờ cần lưu và chính sách bảo vệ dữ liệu.
- [ ] Chốt tích hợp nào dùng thật, tích hợp nào chỉ mô phỏng.
- [ ] Chốt tiêu chí demo/nghiệm thu và thời hạn dự án.
- [ ] Chốt quy ước Git, môi trường, migration và dữ liệu seed.

## 19. Kịch bản demo MVP đề xuất

1. Admin đăng nhập, tạo tòa, tầng, căn hộ và tài khoản nhân viên.
2. Lễ tân tạo hồ sơ cư dân, gắn với căn hộ và tải biên bản bàn giao.
3. Cư dân/lễ tân tạo phản ánh rò rỉ nước tại căn hộ.
4. Trưởng kỹ thuật phân công; kỹ thuật viên cập nhật checklist và ảnh xử lý.
5. Cư dân nghiệm thu, đánh giá; dashboard ghi nhận SLA và CSAT.
6. Kế toán tạo kỳ phí quản lý, phát hành hóa đơn và ghi nhận thanh toán.
7. Giám đốc xem dashboard công nợ, SLA và audit log.

Kịch bản này chứng minh được tính liên kết của hệ thống mà không phụ thuộc ngân hàng, hóa đơn điện tử, IoT hoặc thiết bị kiểm soát ra vào thật.

## 20. Kết luận

Danh sách 11 phân hệ ban đầu phù hợp làm tầm nhìn sản phẩm, nhưng không nên dùng nguyên trạng làm kế hoạch triển khai. Roadmap mới giữ lại toàn bộ giá trị nghiệp vụ, bổ sung nền tảng dùng chung, ngoại lệ quan trọng, bảo mật, dữ liệu, kiểm thử và vận hành; đồng thời tách rõ MVP học kỳ với bản production.

Quyết định quan trọng nhất tiếp theo là khóa phạm vi MVP. Với một bài tập lớn, nên hoàn thiện thật tốt 4 phân hệ nghiệp vụ lõi cùng nền tảng/báo cáo và dùng prototype cho phần còn lại thay vì xây 11 phân hệ ở mức nửa hoàn chỉnh.
