# R7 Task 1 — Pilot Runtime Hardening

Tài liệu này mô tả cách chạy bản **Implemented & Verified Local** cho pilot
nội bộ khoảng 10 người dùng. Đây không phải Gate C, production sign-off hoặc
cam kết triển khai public. Dữ liệu demo phải là dữ liệu giả.

## Phạm vi

- Backend FastAPI chạy với schema Alembic `0015` và PostgreSQL.
- Preflight kiểm tra cấu hình hiệu lực, chạy migration explicit, seed tùy chọn,
  rồi kiểm tra kết nối/TLS/schema head mà không in credential.
- Frontend Vite chạy ở terminal riêng; API mặc định đi qua `/api/v1` proxy.
- Có thể đổi API origin bằng `VITE_API_BASE_URL` hoặc proxy target bằng
  `VITE_DEV_API_PROXY_TARGET`.

Không nằm trong task này: payment gateway thật, đăng ký public, dữ liệu cư dân
thật, object storage, autoscaling, backup/restore rehearsal hoặc Gate C.

## Chuẩn bị một lần

Từ thư mục `backend/`, sao chép template vào file local bị Git bỏ qua và điền
giá trị chỉ trên máy chạy:

```powershell
Copy-Item .env.pilot.example .env
notepad .env
```

`DATABASE_URL` phải là PostgreSQL hợp lệ. `SECRET_KEY` phải là khóa ngẫu nhiên
ít nhất 32 byte; có thể tạo trong process hiện tại mà không ghi vào repository:

```powershell
$env:SECRET_KEY = & .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

Nếu dùng file `.env`, thay placeholder trong file local thay vì chép secret vào
chat, issue hoặc log. Với pilot local, `APP_ENV=development` và CORS chỉ nên
chứa origin frontend nội bộ đã biết. Production sẽ yêu cầu PostgreSQL
`sslmode=verify-full` và origin HTTPS.

## Chạy backend

Mở terminal 1 tại `backend/`:

```powershell
.\scripts\start-pilot-backend.ps1 -SeedDemo
```

Lệnh này lần lượt chạy `runtime_check`, `alembic upgrade head`, seed tùy chọn,
và `db_probe --expected-revision 0015` trước khi mở Uvicorn tại
`http://127.0.0.1:8000`. Nếu đã chạy preflight riêng, có thể dùng
`-SkipPreflight`; script vẫn kiểm tra cấu hình nhưng không tự migrate lại.

Kiểm tra readiness trong terminal khác:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
Invoke-RestMethod http://127.0.0.1:8000/api/v1/readiness
```

Readiness phải trả `status=ready`, `database=connected` và
`schema_revision=0015`.

## Chạy frontend

Mở terminal 2 tại `greencity-app/`:

```powershell
.\scripts\start-pilot-frontend.ps1
```

Mặc định Vite chạy tại `http://127.0.0.1:3000` và proxy `/api/v1` tới backend
local. Khi backend ở origin khác, truyền rõ cấu hình cho process frontend:

```powershell
.\scripts\start-pilot-frontend.ps1 `
  -ApiBaseUrl 'http://127.0.0.1:8000/api/v1' `
  -ProxyTarget 'http://127.0.0.1:8000'
```

Không truyền `tenant_id`, role, site hoặc building từ frontend để mở rộng scope;
backend vẫn là lớp quyết định quyền cuối cùng.

## Kiểm chứng trước demo

```powershell
Set-Location ..\backend
.\.venv\Scripts\python.exe -m pytest -q tests/test_runtime_config.py tests/test_contract.py tests/test_security_boundary.py

Set-Location ..\greencity-app
npm test
npm run build
```

Các lệnh trên chứng minh cấu hình/contract local và build; chúng không phải
benchmark 10 người, Gate C, production readiness hay independent review.
