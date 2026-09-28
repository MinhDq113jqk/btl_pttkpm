# Hồ sơ nguồn dữ liệu — GreenCity

- **Phiên bản:** 1.0
- **Trạng thái:** `OWNER_APPROVED_WITH_SOURCE_CORRECTION_PENDING`
- **Phạm vi:** chuẩn bị và kiểm chứng cục bộ cho bài nộp mã nguồn GreenCity.
- **Vai trò quyết định:** `User/Owner`.
- **Vai trò quản lý tài liệu:** `Codex`.
- **Mã tham chiếu phê duyệt:** `OWNER-CHAT-2026-09-27` (xác nhận trong cuộc trao đổi hiện tại).
- **Lần xem xét gần nhất:** `2026-09-27`.

## 1. Nhận diện và phân loại nguồn

| Trường | Giá trị | Trạng thái |
|---|---|---|
| Định danh nguồn | `documents/greencity-project/excel-data` | Đã ghi nhận |
| Bản chất nguồn | Dữ liệu vận hành thật do User/Owner cung cấp | Đã xác nhận ngày 2026-09-26 |
| Chủ sở hữu nguồn | `User/Owner` cung cấp dữ liệu và quyết định phạm vi dùng cho bài nộp | Đã xác nhận trong chat ngày 2026-09-27 |
| Source of truth | Nguồn chuẩn cho phạm vi tích hợp dữ liệu của bài nộp cuối | Đã xác nhận |
| Nguồn cũ | `data_that` chỉ là dữ liệu demo cũ, không là source of truth | Đã ghi nhận |
| Phân loại | `RESTRICTED_REAL_LOCAL_ONLY` | Đã xác nhận |
| Độ nhạy cảm | Có thể chứa dữ liệu nhận diện hoặc liên hệ trực tiếp; tài liệu này không ghi bất kỳ giá trị nào | Đã ghi nhận |

## 2. Mục đích được phép và ranh giới đóng gói

| Quyết định | Giá trị hiện tại | Trạng thái | Cần owner phê duyệt |
|---|---|---|---|
| Mục đích dùng raw data | Chỉ dùng cục bộ để preflight, kiểm chứng import có kiểm soát và tạo gói ẩn danh cho bài nộp | Đã duyệt 2026-09-27 | Đã xác nhận |
| Phân phối raw data | Không đưa vào Git, gói nộp, log, evidence, ngữ cảnh review hoặc chia sẻ ra ngoài | Đã duyệt 2026-09-27 | Đã xác nhận |
| Gói nộp cho giáo viên | User/Owner đã cho phép có điều kiện với dữ liệu thật đã ẩn danh; lựa chọn demo hiện tại là pack tổng hợp `SYNTHETIC_TEST_ONLY` | Đã chọn pack tổng hợp 2026-09-28 | Đã xác nhận |
| Ánh xạ ngược | Không đưa vào Git hoặc gói nộp | Đã duyệt 2026-09-27 | Đã xác nhận |

Quyền dùng dữ liệu thật có điều kiện đã được duyệt, nhưng công cụ hiện tại giữ
nguyên số tiền/số lượng và chỉ dịch ngày theo quy tắc cố định. Vì vậy output
tạo từ raw được gắn `LOCAL_VALIDATION_ONLY`, không được đưa vào gói
nộp hoặc chia sẻ. Regex scan và preflight không chứng minh đã khử khả năng tái
nhận diện. Gói demo duy nhất là bộ tổng hợp. Preflight ngày 2026-09-28 phát hiện
30 `FUTURE_HISTORICAL_EVENT` và 5 `FUTURE_TERMINAL_EVENT` trong raw; User/Owner
sẽ sửa các mốc theo sự kiện thật.

## 3. Retention và hủy dữ liệu

| Trường | Giá trị hiện tại | Owner quyết định |
|---|---|---|
| Mốc bắt đầu retention | Khi tạo bản sao tạm phục vụ kiểm thử/bài nộp | `User/Owner` đã xác nhận |
| Ngày hoặc sự kiện kết thúc retention | Sau khi giáo viên chấm xong | `User/Owner` đã xác nhận |
| Xử lý bản sao lưu | Không tạo bản sao raw cho gói nộp; bản sao tạm phục vụ pipeline được xóa cùng thời điểm trên | `User/Owner` đã xác nhận phạm vi local |
| Phương thức hủy | Xóa bản sao tạm local; raw gốc do User/Owner quản lý trên máy | `User/Owner` đã xác nhận |
| Bằng chứng hủy | Ghi nhận checklist sau khi việc chấm bài kết thúc; chưa thể tuyên bố đã hủy trước sự kiện đó | `User/Owner` chịu trách nhiệm |
| Vai trò chịu trách nhiệm thực hiện | `User/Owner` | Đã xác nhận |

Gói ẩn danh đã nộp cho giáo viên không thuộc nhóm "bản sao tạm local"; raw gốc
chỉ ở máy User/Owner và không đi vào Git/package.

## 4. Quyết định timezone

| Trường | Giá trị hiện tại | Trạng thái |
|---|---|---|
| Timezone site | `Asia/Ho_Chi_Minh` | User/Owner xác nhận 2026-09-27 |
| Quy tắc lưu trữ | Diễn giải thời gian nguồn theo timezone site đã duyệt, sau đó lưu timestamp ở UTC | Đã duyệt |
| Timestamp tương lai | 35 mốc sự kiện lịch sử/kết thúc còn chặn import tại lần kiểm 2026-09-28; User/Owner sẽ sửa theo sự kiện thật | Đang chờ sửa nguồn |

## 5. Bản ghi phê duyệt bắt buộc

| ID | Quyết định | Vai trò phê duyệt | Mã tham chiếu | Thời điểm duyệt | Ngày xem xét hoặc hết hạn |
|---|---|---|---|---|---|
| DP-01 | Quyền dùng dữ liệu thật trong phạm vi bài nộp này | `User/Owner` | `OWNER-CHAT-2026-09-27` | `2026-09-27` | Sau khi chấm bài |
| DP-02 | Mục đích dùng và đối tượng được nhận | `User/Owner` | `OWNER-CHAT-2026-09-27` | `2026-09-27` | Sau khi chấm bài |
| DP-03 | Điều kiện đưa approved pack vào gói nộp | `User/Owner` | `OWNER-CHAT-2026-09-27` | `2026-09-27` | Trước khi đóng gói |
| DP-04 | Retention, backup và hủy dữ liệu tạm local | `User/Owner` | `OWNER-CHAT-2026-09-27` | `2026-09-27` | Sau khi chấm bài |
| DP-05 | Timezone site cuối cùng | `User/Owner` | `OWNER-CHAT-2026-09-27` | `2026-09-27` | Trước lần import cuối |

FCS-01 đã có quyết định của User/Owner cho DP-01..DP-05. Bản dữ liệu thật chỉ
được replay sau khi User/Owner sửa các timestamp sự kiện sai và preflight PASS;
quyết định phê duyệt không thay thế kiểm tra kỹ thuật này.

## 6. Cam kết không chứa dữ liệu nhạy cảm

Tài liệu này không chứa giá trị ô thô, tên, email, số điện thoại, thông tin đăng
nhập, secret, PIN, nội dung workbook, checksum, tên từng workbook, số dòng, số
sheet hoặc ánh xạ ngược. Metadata mức tệp chỉ được lập ở FCS-02 trong manifest đã
redact.
