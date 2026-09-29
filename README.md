# GreenCity – Hệ thống quản lý vận hành khu đô thị

## Giới thiệu sản phẩm

GreenCity là ứng dụng web hỗ trợ vận hành khu đô thị, gồm giao diện React/Vite
và API FastAPI/PostgreSQL. Hệ thống tập trung vào các tác vụ hằng ngày của ban
quản lý, nhân viên vận hành và cư dân, với quyền truy cập được giới hạn theo
phiên đăng nhập và phạm vi được máy chủ xác định.

Các phân hệ hiện có trong mã nguồn:

- Đăng nhập, đổi mật khẩu, phân quyền và quản lý phạm vi site/tòa nhà.
- Yêu cầu dịch vụ, Work Order, bảo trì, vệ sinh và an ninh.
- Bưu phẩm, cư dân, hóa đơn/công nợ, thanh toán và thông báo.
- Nhập dữ liệu, dashboard điều hành, nhật ký kiểm toán và inbox/outbox.
- Green Assistant là tính năng tùy chọn; mặc định đang tắt và khóa nhà cung
  cấp chỉ được đặt phía backend.

Dự án được thiết kế và kiểm chứng cho môi trường local với dữ liệu demo hoặc
synthetic. Điều đó không tương đương với xác nhận triển khai production hay
pilot chính thức.

## Hướng dẫn cài đặt

### 1. Lấy mã nguồn

Bỏ qua bước này nếu bạn đã có checkout:

~~~powershell
git clone https://github.com/MinhDq113jqk/btl_pttkpm.git
Set-Location .\btl_pttkpm
~~~

### 2. Yêu cầu

- Windows PowerShell.
- Python 3.12 (các lệnh dưới đây dùng `py -3.12`).
- Node.js 22 LTS (Docker build của dự án dùng Node 22.23.3).
- Một PostgreSQL database development trống, có cấu hình TLS phù hợp.

### 3. Tạo cấu hình backend

Từ thư mục gốc repository, tạo file cấu hình local nếu chưa có:

~~~powershell
if (-not (Test-Path .\backend\.env)) {
  Copy-Item .\backend\.env.example .\backend\.env
}
~~~

Trước khi tiếp tục, tạo một database development và user riêng bằng công cụ
PostgreSQL của bạn. Mở `backend\.env` và thay các giá trị mẫu tối thiểu.
`DATABASE_URL` phải là URI PostgreSQL hợp lệ với `sslmode=require`,
`verify-ca` hoặc `verify-full`; `SECRET_KEY` phải là giá trị riêng có ít nhất
32 byte. Nếu tên đăng nhập hoặc mật khẩu có ký tự đặc biệt, mã hóa chúng theo
URL trước khi đặt vào URI. Không commit file này.

~~~text
DATABASE_URL=postgresql+psycopg://<user>:<password>@<host>:5432/<database>?sslmode=require
SECRET_KEY=<mot-gia-tri-ngau-nhien-rieng-tu-32-byte-tro-len>
APP_ENV=development
CORS_ORIGINS=["http://localhost:3000"]
ASSISTANT_ENABLED=false
~~~

Giữ Green Assistant ở trạng thái tắt nếu chưa có phê duyệt quota, ngân sách và
retention. Khi bật, chỉ đặt `GEMINI_API_KEY` trong `backend\.env`; không đặt
khóa hoặc biến `VITE_*` ở frontend.

### 4. Cài và chạy backend

~~~powershell
Set-Location .\backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m scripts.migrate upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --reload --host 127.0.0.1 --port 8000
~~~

Kiểm tra API tại `http://127.0.0.1:8000/api/v1/health` và Swagger tại
`http://127.0.0.1:8000/docs`.

### 5. Cài và chạy frontend

Mở PowerShell thứ hai từ thư mục gốc repository:

~~~powershell
Set-Location .\greencity-app
npm ci
npm run dev
~~~

Mở `http://localhost:3000`. Khi backend chạy cùng máy, frontend mặc định proxy
`/api/v1` tới `http://127.0.0.1:8000`, nên không cần file frontend `.env`.
Chỉ tạo `greencity-app\.env` từ `.env.pilot.example` khi cần đổi địa chỉ API.

### 6. Tạo dữ liệu demo (tùy chọn)

Chỉ chạy bước này trên database development/test tách biệt. Script tạo mười
credential ngẫu nhiên ở file riêng ngoài repository và không in mật khẩu ra
terminal:

~~~powershell
Set-Location .\backend
.\scripts\new_demo_credentials.ps1
$credentialFile = Join-Path $env:LOCALAPPDATA 'GreenCity\demo-credentials.json'
$env:DEMO_SEED_ENABLED = 'true'
$env:DEMO_SEED_CREDENTIALS_JSON = [IO.File]::ReadAllText($credentialFile)
try {
  & .\.venv\Scripts\python.exe -m scripts.seed
  if ($LASTEXITCODE -ne 0) { throw 'Demo seed failed.' }
} finally {
  Remove-Item Env:DEMO_SEED_ENABLED, Env:DEMO_SEED_CREDENTIALS_JSON -ErrorAction SilentlyContinue
}
~~~

Dữ liệu demo bị tắt mặc định; chỉ seed vào database development/test tách biệt,
không dùng database chung hoặc dữ liệu vận hành thật. Tài liệu chi tiết về
walkthrough, kiểm thử và provenance dữ liệu nằm trong
[`documents/greencity-project/`](documents/greencity-project/).
