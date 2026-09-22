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

Repository `btl_pttkpm` công bố bundle tài liệu dưới
`documents/greencity-project`, gồm cả governance Phase 1. Repository
`greencity` chỉ nhận mã nguồn, không nhận bundle này. `.env`, `.venv`,
`node_modules` và `dist` không đưa lên GitHub.

## Danh mục tài liệu đặc tả & quản trị

- **`BAO_CAO_DAC_TA_HE_THONG_GREENCITY_HOAN_CHINH.docx`**: Báo cáo tổng hợp đặc tả yêu cầu hệ thống và kiến trúc toàn diện GreenCity (SRS, danh mục Use Case phân cấp động từ chuẩn UML, kiến trúc module, kế hoạch định hướng sản phẩm và ma trận truy vết RTM) đã hoàn thiện qua 5 vòng phản biện học thuật.
- **`greencity-use-case-srs.html`**: Giao diện trực quan tra cứu chi tiết kịch bản tương tác Use Case.
- **`greencity-use-case.html`**: Sơ đồ Use Case theo từng phân hệ chức năng.
- **`greencity-database-schema.html`**: Thiết kế cơ sở dữ liệu vật lý và lược đồ quan hệ thực thể.
- **`roadmap_v2.md`**: Bản đồ lộ trình phát triển qua các Tranche R1-R7 & V1.
- **`governance/phase-1/`**: Bộ tài liệu thẩm định bảo mật, kiểm soát thay đổi và bằng chứng vận hành Phase 1.

