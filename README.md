# Hệ thống quản lý vận hành khu đô thị

## Cấu hình

Backend đọc cấu hình từ `backend/.env`. Tạo file local từ template rồi điền
giá trị riêng, không commit file `.env`:

```powershell
cd backend
Copy-Item .env.example .env
```

Điền tối thiểu `DATABASE_URL` và `SECRET_KEY` (khóa ngẫu nhiên tối thiểu 32
bytes). Để dùng Green Assistant, điền `GEMINI_API_KEY` trong chính
`backend/.env`. Backend đọc key này trực tiếp từ file server-side; không đặt
key trong `greencity-app/.env`, không dùng biến `VITE_GEMINI_API_KEY` và không
đưa key vào mã nguồn hoặc request của trình duyệt.

Frontend không cần key Gemini. Có thể tạo cấu hình proxy local tùy chọn:

```powershell
cd greencity-app
Copy-Item .env.pilot.example .env
```

Giữ `VITE_API_BASE_URL` trống để dùng proxy same-origin `/api/v1`. Nếu backend
chạy ở địa chỉ khác, đặt `VITE_DEV_API_PROXY_TARGET` thành một URL `http(s)`
hợp lệ. `VITE_API_BASE_URL` chỉ là địa chỉ API public, không phải nơi chứa
secret.

## Chạy nhanh frontend

```powershell
cd greencity-app
npm install
npm run dev
```

Mở `http://localhost:3000`. Với checkout sạch, dùng `npm ci` thay cho
`npm install` để cài đúng `package-lock.json`.

## Chạy backend local

Yêu cầu Python 3.12+ và PostgreSQL đã chạy. Từ thư mục project:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
Copy-Item .env.example .env
# Điền DATABASE_URL, SECRET_KEY và GEMINI_API_KEY riêng trong .env; không commit file này.
.\.venv\Scripts\python.exe -m scripts.migrate upgrade head
.\.venv\Scripts\python.exe -m scripts.seed
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --reload --host 127.0.0.1 --port 8000
```

Backend Swagger: `http://127.0.0.1:8000/docs`.

Chạy backend trước frontend để proxy local hoạt động. Endpoint assistant là
`POST /api/v1/assistant/chat`; endpoint yêu cầu Bearer session và backend tự
suy ra tenant/site/building/role từ phiên đăng nhập. Frontend chỉ gửi nội dung
câu hỏi.

## Kiểm thử

Backend unit/contract tests:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

Test riêng cho Gemini client và assistant API:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_gemini_client.py tests\test_assistant_api.py -q
```

Full regression trên PostgreSQL cô lập (cần PostgreSQL và OpenSSL local):

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\test_isolated.py `
  --pg-bin "C:\Program Files\PostgreSQL\18\bin" `
  --openssl "C:\Program Files\Git\usr\bin\openssl.exe"
```

Frontend tests và production build:

```powershell
cd greencity-app
npm ci
npm test
npm run test:assistant
npm run test:assistant:security
npm run build
```

`test:assistant:security` build frontend rồi quét source và bundle để bảo đảm
không có tên biến key Gemini, URL upstream Gemini hoặc header API key trong
artifact trình duyệt.

Các smoke suite theo phân hệ có sẵn dưới dạng `npm run test:<module>` trong
`package.json` (ví dụ `test:parcel`, `test:resident`, `test:billing`).

## Quy ước repository

Bundle tài liệu dự án được publish trong `documents/greencity-project` trên
repository `btl_pttkpm`. Repository `greencity` chỉ nhận mã nguồn, không nhận
bundle tài liệu này. `.env`, `.venv`, `node_modules` và `dist` không đưa lên
GitHub.
