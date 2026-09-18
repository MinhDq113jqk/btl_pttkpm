# GreenCity — Cải thiện UX desktop

Ngày kiểm tra: 08/09/2026. Phạm vi: giao diện React 18 / Vite hiện có, không triển khai backend hoặc đóng gói Windows.

## Thư mục bàn giao

- Bản đã sửa: `C:\Users\LEGION\btl\greencity-app`.
- Bản Git `C:\Users\LEGION\btl\_pttkpm\greencity-app` được giữ nguyên. Hai thư mục `src` giống nhau trước khi sửa; bản Git vẫn sạch sau lượt làm việc này.
- Không commit, push hoặc đồng bộ hai bản. Muốn đưa thay đổi lên Git cần chọn bản làm việc chính trước.

## Phát hiện và thay đổi

| Bằng chứng ban đầu | Ảnh hưởng | Đã sửa |
| --- | --- | --- |
| Desktop dùng `TasksMobileView`, có công tắc mô phỏng điện thoại | Mật độ thông tin và điều hướng không phù hợp công việc desktop | Khung desktop với sidebar, vùng nội dung cuộn độc lập, bảng công việc và thanh trạng thái |
| Ô tìm kiếm và Ctrl+K không có xử lý; “Xem tất cả” mở phiếu hoàn tiền | Người dùng không tìm hoặc đi đúng luồng | Tìm kiếm không dấu, tìm mã/tên/vị trí và phân hệ; điều hướng đúng; lịch sử Back/Forward |
| Công việc hiển thị số đếm 12/6 nhưng có 7 bản ghi | Không tin cậy trạng thái vận hành | KPI, sidebar, bộ lọc và bảng dùng cùng nguồn dữ liệu; có trạng thái rỗng và xóa lọc |
| Nút thông báo không hoạt động, “Đọc tất cả” chưa cập nhật trạng thái | Không biết còn việc chưa đọc | Hộp thông báo desktop, đánh dấu đã đọc, badge đồng bộ và mở hồ sơ liên quan |
| Ngày `2026/09/04` khiến input date trống | Không thể đối chiếu ngày rõ ràng | Chuẩn hóa giá trị ISO; xác nhận hiển thị ngày/tháng/năm |
| Số tiền âm bị bỏ dấu; chỉ kiểm tra số tiền, chưa kiểm tra trường liên quan | Có thể xác nhận khác ý định người nhập | Giữ giá trị nhập; kiểm tra số nguyên, số dư, ngày, chứng từ và trường ngân hàng theo phương thức |
| Lưu nháp chỉ hiện toast; rời phiếu mất thay đổi | Mất dữ liệu nhập và thông báo thành công sai | Nháp hoàn tiền lưu vào sessionStorage của tab, phục hồi khi tải lại; cảnh báo rời phiếu; lỗi lưu trữ có hướng phục hồi |
| Xác nhận luôn hiển thị tài khoản ngân hàng, kể cả chọn tiền mặt | Dễ xác nhận sai phương thức | Nội dung xác nhận thay đổi theo ngân hàng / tiền mặt / khấu trừ; không tự nhận đã xác minh danh tính |
| Modal chưa giữ focus, Escape và khôi phục focus | Khó sử dụng bằng bàn phím | Dialog native, vòng Tab/Shift+Tab, Escape, trả focus, focus lỗi và reduced motion |
| Thanh nút form phủ toàn cửa sổ | Che sidebar/nội dung | Thanh hành động nằm trong vùng nội dung, kiểm tra không bị che ở các kích thước desktop |
| Tiện ích sử dụng `Sparkles` chưa import | Lỗi runtime làm trắng màn hình dù build có thể vẫn thành công | Bổ sung import và kiểm thử các tab con |
| Nút xem bài / hồ sơ chỉ hiện toast hoặc chưa làm gì | Luồng bị ngắt | Xem chi tiết thật từ bản ghi trong bộ nhớ; nháp bài viết/gian hàng có lưu và khôi phục trong phiên |
| Ảnh mạng có thể trống hoặc lỗi | Chất lượng giao diện không ổn định | Giữ kích thước và hiển thị hình thay thế có nhãn khi tải ảnh thất bại |
| Nhãn Live, đồng bộ và giao dịch thành công dù không có backend | Gây hiểu nhầm về mức hoàn thiện sản phẩm | Ghi rõ dữ liệu mẫu, trạng thái chưa kết nối và thao tác mô phỏng |

## Định hướng thiết kế

Áp dụng skill `ui-ux-pro-max`: ưu tiên bàn phím, focus, trạng thái lỗi, điều hướng, mật độ dữ liệu desktop. Kết quả thiết kế thiên về landing page bất động sản không được áp dụng. Giữ màu xanh GreenCity, dùng font hệ thống Windows, tăng tương phản, bỏ phụ thuộc Google Fonts. Không áp dụng thanh điều hướng dưới, khung điện thoại hay quy tắc safe-area mobile cho desktop.

Phối hợp hướng dẫn frontend-design và karpathy-guidelines để giữ thay đổi tập trung vào luồng hiện có, không thêm thư viện giao diện hoặc thay đổi kiến trúc ngoài phạm vi.

Tham chiếu kỹ thuật: [W3C — Dialog keyboard interaction](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/), [MDN — Giá trị input date](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/input/date). Đây là cơ sở cho một số thay đổi; không phải chứng nhận toàn ứng dụng đạt WCAG.

## Kiểm chứng

- `npm test`: 17 kiểm thử logic.
- `npm run build`: thành công, không thêm dependency.
- `npm run test:ux`: lượt cuối trên bản build preview đạt 83 kiểm tra, 0 lỗi JavaScript runtime. Dùng Playwright/Edge headless; các lượt trước cũng chạy trên dev. Từng kết quả ở `artifacts/ux/test-results.json`.
- Các cỡ cửa sổ chính: 1920×1080, 1440×900, 1366×768, 1280×720, 1024×768, 800×600; thêm viewport CSS 720×450 tương đương không gian nội dung khi phóng to 200% từ 1440×900. Đây không phải kiểm tra trực tiếp DPI Windows hay zoom native.
- Có kiểm tra trạng thái tải ban đầu và ổn định, lọc/tìm không dấu, sorting, Tab/Escape, trả focus, reduced motion, lưu/khôi phục/bỏ nháp, lỗi lưu trữ, tệp không hợp lệ, phương thức tiền mặt, bộ đếm thông báo, các tab con.
- Kiểm tra lỗi ảnh bằng chặn yêu cầu ảnh từ Unsplash trong trình duyệt kiểm thử; ảnh chụp màn phụ vì vậy có thể hiển thị hình thay thế.
- Ảnh trước/sau và kết quả kiểm thử nằm trong `artifacts/ux/`, được loại khỏi Git bằng `.gitignore`.

## Chạy tại máy này

```powershell
Set-Location 'C:\Users\LEGION\btl\greencity-app'
npm run dev
```

Mở `http://127.0.0.1:3000/`. Bản build: `npm run build`, rồi `npm run preview -- --host 127.0.0.1 --port 4173`.

Chạy kiểm thử UI bằng Playwright đã có sẵn trong runtime của máy, không cài thêm vào dependency của sản phẩm:

```powershell
$env:NODE_PATH='C:\Users\LEGION\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
$env:UX_BASE_URL='http://127.0.0.1:4173/'
npm run test:ux
```

`npm test` không cần Playwright. Đường dẫn runtime ở trên chỉ áp dụng cho máy hiện tại; máy khác cần Node.js và Playwright/Edge phù hợp.

## Giới hạn cần biết

1. Đây vẫn là frontend ưu tiên desktop chạy bằng web runtime, chưa có Electron/Tauri, bộ cài `.exe`, kiểm tra đa cửa sổ, tích hợp hệ thống hay tự cập nhật.
2. Phân công/đổi trạng thái công việc, backend, xác thực, phân quyền, sổ cái, ngân hàng, Messenger và đăng bài thật chưa có. Các phân hệ chưa triển khai vẫn được giữ và ghi nhãn, không giả lập là đã hoàn tất nghiệp vụ.
3. Nháp hoàn tiền chỉ lưu nội dung trong tab; tệp người dùng chọn thêm không được lưu nội dung và phải chọn lại sau tải lại. Nháp truyền thông/gian hàng chỉ tồn tại trong bộ nhớ phiên, mất khi tải lại; hiện không có đồng bộ nhiều máy.
4. Chứng từ đính kèm chỉ kiểm tra định dạng/kích thước phía giao diện, không phải quét an toàn hoặc xác minh chứng từ. Không dùng thông tin tài chính, cư dân hay tài khoản thật để thử bản mẫu.
5. Chưa nghiệm thu nghiệp vụ tài chính, kiểm thử người dùng thật, trình đọc màn hình thực tế, dark mode, offline toàn phần hoặc toàn bộ tổ hợp thao tác. Các kiểm tra ở trên không đồng nghĩa sản phẩm sẵn sàng triển khai chính thức.
