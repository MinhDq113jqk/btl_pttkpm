# Hệ thống quản lý vận hành khu đô thị

## Chạy nhanh frontend

```powershell
cd greencity-app
npm install
npm run dev
```

Mở `http://localhost:5173`. Với checkout sạch, dùng `npm ci` thay cho
`npm install` để cài đúng `package-lock.json`.

## Chạy backend local

Yêu cầu Python 3.12+ và PostgreSQL đã chạy. Từ thư mục project:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
Copy-Item .env.example .env
# Điền DATABASE_URL và SECRET_KEY riêng trong .env; không commit file này.
.\.venv\Scripts\python.exe -m scripts.migrate upgrade head
.\.venv\Scripts\python.exe -m scripts.seed
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --reload --host 127.0.0.1 --port 8000
```

Backend Swagger: `http://127.0.0.1:8000/docs`.

## Kiểm thử

Backend unit/contract tests:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
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
npm run build
```

Các smoke suite theo phân hệ có sẵn dưới dạng `npm run test:<module>` trong
`package.json` (ví dụ `test:parcel`, `test:resident`, `test:billing`).

## Quy ước repository

README là tài liệu duy nhất được giữ trong repository. Các tài liệu Markdown
khác được lưu ngoài project tại `..\documents\greencity-project`; `.env`,
`.venv`, `node_modules` và `dist` không đưa lên GitHub.
