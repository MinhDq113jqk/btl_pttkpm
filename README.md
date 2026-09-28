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
npm ci
npm run dev
```

Mở `http://localhost:3000`.

## Chạy backend local

Yêu cầu Python 3.12+, PostgreSQL đang chạy và một database development trống đã tạo.
Tạo database local bằng pgAdmin hoặc `createdb` một lần, rồi trỏ `DATABASE_URL`
trong `backend/.env` tới database đó. Từ thư mục project:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
Copy-Item .env.example .env
# Điền DATABASE_URL, SECRET_KEY và GEMINI_API_KEY riêng trong .env; không commit file này.
.\.venv\Scripts\python.exe -m scripts.migrate upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --reload --host 127.0.0.1 --port 8000
```

Seed chỉ dành cho database development/test tách biệt, bị tắt mặc định và bị
từ chối ở production. Tạo file credential ngẫu nhiên, chỉ tài khoản Windows
hiện tại đọc được, ở ngoài repository:

```powershell
cd backend
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
```

Credential gồm mười tài khoản `admin_demo`, `director_west`, `cskh_west`,
`cskh_east`, `accountant_west`, `techlead_west`, `technician_west`,
`cleaning_west`, `security_west` và `resident_west`. Giữ file bên ngoài Git;
không in credential ra log hoặc chép vào tài liệu. Seed lặp an toàn và không
đổi mật khẩu của tài khoản đã tồn tại, vì vậy hãy giữ file ban đầu cho cùng
database. Tài khoản demo mới yêu cầu đổi mật khẩu ở lần đăng nhập đầu.

Backend Swagger: `http://127.0.0.1:8000/docs`.

### Gói dữ liệu demo synthetic đi kèm

Gói nộp có `backend/tests/fixtures/submission_data/synthetic/` (12 workbook,
101 dòng), `synthetic_manifest.json` và `synthetic_evidence/`. Manifest gắn nhãn
`SYNTHETIC_TEST_ONLY`: dữ liệu này được tạo độc lập để kiểm thử code, không
phải bản ẩn danh chuyển từ `excel-data` và không chứng minh luồng raw import.
Full PostgreSQL isolated runner tự tạo database disposable, migrate, preflight,
dry-run, apply, verify và retry gói này. Chạy lệnh `scripts/test_isolated.py`
trong mục **Kiểm thử** để kiểm lại toàn bộ chuỗi mà không cần credential thật.

Khi muốn xem giao diện tương tác, dùng demo seed ở mục **Chạy backend local**;
chạy Golden Flow browser từ mục **Kiểm thử**. Hai đường demo này dùng dữ liệu
synthetic và phải được ghi đúng nguồn trong báo cáo nộp bài.

Để kiểm browser trên backend thật với PostgreSQL dùng một lần, chạy từ thư mục
gốc sau khi đã cài backend/frontend:

```powershell
$env:PHASE3_REAL_BROWSER = '1'
try {
  & .\backend\.venv\Scripts\python.exe .\backend\scripts\phase3_real_backend_browser.py `
    --pg-bin "C:\Program Files\PostgreSQL\18\bin" `
    --openssl "C:\Program Files\Git\usr\bin\openssl.exe" `
    --python ".\backend\.venv\Scripts\python.exe" `
    --node "C:\Program Files\nodejs\node.exe" `
    --evidence-dir ".\.local\submission-data\real-browser"
  if ($LASTEXITCODE -ne 0) { throw 'Real-backend browser rehearsal failed.' }
} finally {
  Remove-Item Env:PHASE3_REAL_BROWSER -ErrorAction SilentlyContinue
}
```

Runner import pack synthetic vào database disposable, restart backend rồi kiểm
readback. Riêng GF-07, runner gắn bảy liên kết cư dân từ
`backend/tests/fixtures/submission_data/synthetic_resident_links.json` vào
database test bằng thao tác lặp an toàn để portal đọc hóa đơn/thanh toán. Fixture
này chỉ phục vụ demo synthetic; không phải ánh xạ cư dân của `excel-data`.

### Kiểm chứng nguồn thật (ngoài phạm vi gói demo)

Raw `excel-data` là nguồn tham chiếu cho phần tích hợp dữ liệu thật, nhưng
không thuộc gói nộp. User/Owner đã chọn gói synthetic làm dữ liệu demo có thể
phân phối. Bộ anonymizer, kể cả khi nguồn tự khai synthetic, chỉ tạo
`LOCAL_VALIDATION_ONLY` với `distribution_allowed=false`; không
đưa `local_validation_pack`, manifest hoặc ánh xạ ngược vào Git/gói nộp.
Gói synthetic không chứng minh raw onboarding.

Sau khi User/Owner sửa các timestamp nguồn bị preflight chặn, kiểm nguồn
trước khi chạy bất kỳ bước local validation nào. Từ thư mục `backend`:

```powershell
$source = '../documents/greencity-project/excel-data'
$manifest = '../documents/greencity-project/DATA_SOURCE_MANIFEST.json'
& .\.venv\Scripts\python.exe -m scripts.submission_data_preflight `
  --source $source --report-dir '.local/submission-data/reports'
if ($LASTEXITCODE -ne 0) { throw 'Raw preflight still blocks packaging.' }
& .\.venv\Scripts\python.exe -m scripts.refresh_submission_source_manifest `
  --source $source --manifest $manifest --write
if ($LASTEXITCODE -ne 0) { throw 'Source manifest refresh failed.' }
& .\.venv\Scripts\python.exe -m scripts.refresh_submission_source_manifest `
  --source $source --manifest $manifest --check
if ($LASTEXITCODE -ne 0) { throw 'Source manifest check failed.' }
```

`--write` từ chối cập nhật manifest khi preflight còn lỗi; hiện không chạy bước
này. Snapshot read-only lúc `2026-09-28T03:06:20Z` trên 12 workbook/101 dòng
có checksum đúng, 0 orphan, nhưng 35 lỗi thời gian (30 historical event,
5 terminal event) và 47 cảnh báo future schedule. Chỉ User/Owner sửa nguồn
theo sự kiện thật rồi mới chạy lại chuỗi trên.

### Đặt lại database demo local

Tạo một database development/test **mới, trống** trong PostgreSQL, đổi
`DATABASE_URL` trong `backend/.env` sang database mới đó, rồi chạy:

```powershell
cd backend
.\.venv\Scripts\python.exe -m scripts.migrate upgrade head
```

Chạy demo seed hoặc synthetic import trên database test tương ứng sau migration. Một số
downgrade cố ý từ chối khi database còn dữ liệu, vì vậy việc tạo database mới
là cách reset cho walkthrough.

Chạy backend trước frontend để proxy local hoạt động. Endpoint assistant là
`POST /api/v1/assistant/chat`; endpoint yêu cầu Bearer session và backend tự
suy ra tenant/site/building/role từ phiên đăng nhập. Frontend chỉ gửi nội dung
câu hỏi.

## Kiểm thử

Để kiểm gói nộp theo đúng file của working tree hiện tại, từ thư mục gốc chạy:

```powershell
$candidate = Join-Path '.local' ('fcs19-' + [guid]::NewGuid().ToString('N'))
python backend/scripts/export_submission_candidate.py --destination $candidate
```

Script lấy file
tracked và untracked không bị ignore, từ chối đường dẫn dữ liệu gốc, `.env`,
cache và symlink, rồi in số file cùng SHA-256 của candidate. Chạy các lệnh cài
dependency, test và `npm run check:links` trong bản sao đó; xuất lại candidate
khi bất kỳ file nguồn nào thay đổi. Candidate demo chỉ chứa pack synthetic;
raw-derived local validation output bị loại trừ.

Backend unit/contract tests:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q --basetemp=".pytest-temp-$PID"
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
npm run test:cleaning
npm run test:security
npm run test:imports
npm run test:work-orders
npm run test:maintenance
npm run test:golden-flows
npm run build
```

`test:assistant:security` build frontend rồi quét source và bundle để bảo đảm
không có tên biến key Gemini, URL upstream Gemini hoặc header API key trong
artifact trình duyệt.

Các smoke suite theo phân hệ có sẵn dưới dạng `npm run test:<module>` trong
`package.json` (ví dụ `test:parcel`, `test:resident`, `test:billing`).
`npm run test:golden-flows` gom browser suites theo GF-01..08; các browser
suite dùng API fixture để kiểm tra giao diện, role visibility và request
contract. Persistence, audit, scope, idempotency và state transition được xác
minh riêng bởi PostgreSQL integration suite ở lệnh `scripts\test_isolated.py`.
Hai lớp bằng chứng này không phải browser chạy trực tiếp trên database.

### Walkthrough demo theo vai trò

1. **GF-01 — Phiên:** đăng nhập, kiểm tra menu lấy từ `/auth/me`, đổi site khi
   được cấp, đổi mật khẩu lần đầu và đăng xuất.
2. **GF-02 — Yêu cầu đến Work Order:** `resident_west` tạo yêu cầu;
   `cskh_west` phân loại; `techlead_west` giao việc;
   `technician_west` checklist/tệp bằng chứng/nộp nghiệm thu; `director_west`
   kiểm tra và đóng theo trạng thái cho phép.
3. **GF-03 — Bảo trì:** `techlead_west` tạo Asset/Plan, chạy scheduler và xem
   occurrence/history; `technician_west` xử lý Work Order được giao.
4. **GF-04 — Vệ sinh:** `director_west` tạo ca/giao tuyến; `cleaning_west` gửi
   checklist đạt và checklist cần khắc phục; quản lý kiểm tra kết quả.
5. **GF-05 — An ninh:** `director_west` tạo ca; `security_west` bàn giao,
   ghi visitor/patrol/incident; incident mức cao chỉ đóng sau khi đủ evidence
   và acknowledgement.
6. **GF-06 — Bưu phẩm:** `cskh_west` hoặc `security_west` tiếp nhận, đánh dấu
   sẵn sàng, bàn giao/ghi exception và liên kết hồ sơ; PIN không ghi vào log.
7. **GF-07 — Tài chính:** `accountant_west` cấu hình kỳ phí, chạy billing,
   xử lý payment/unmatched/credit; `resident_west` đọc invoice và payment.
   Demo chỉ dùng dữ liệu giả, không dùng cổng thanh toán thật.
8. **GF-08 — Điều hành:** `admin_demo` hoặc `director_west` mở KPI, drill-down,
   audit và inbox/outbox; đối chiếu theo cùng `as_of`.

Chỉ dùng dữ liệu giả trên database disposable. Tạo lại database sạch theo mục
“Đặt lại database demo local” rồi seed lại khi cần chạy walkthrough từ đầu.
Các username trong walkthrough là của demo seed. Synthetic import runner tự tạo
credential tạm cho database disposable; không dùng các tài khoản này với raw
source hoặc một database dùng chung.

## Quy ước repository

Bundle tài liệu dự án được publish trong `documents/greencity-project` trên
repository `btl_pttkpm`. Repository `greencity` chỉ nhận mã nguồn, không nhận
bundle tài liệu này. `.env`, `.venv`, `node_modules` và `dist` không đưa lên
GitHub.

Tài liệu báo cáo đặc tả hệ thống hoàn chỉnh:
- [Báo cáo đặc tả hệ thống GreenCity (.docx)](documents/greencity-project/BAO_CAO_DAC_TA_HE_THONG_GREENCITY_HOAN_CHINH.docx)
- [Ma trận truy vết V3](documents/greencity-project/V3-00_TRACEABILITY_MATRIX.md)
- [Lộ trình phát triển hệ thống](documents/greencity-project/roadmap_v2.md)
- [Phần bổ sung Roadmap V3](documents/greencity-project/roadmap_v3.md)
- [Hồ sơ provenance dữ liệu](documents/greencity-project/DATA_PROVENANCE.md)
- [Manifest nguồn dữ liệu đã redact](documents/greencity-project/DATA_SOURCE_MANIFEST.json)
- [Data onboarding contract FCS-03](documents/greencity-project/DATA_ONBOARDING_CONTRACT.md)
- [Machine-readable submission data contract](backend/app/services/submission_data_contract.py)
- [Submission normalization rules FCS-04](backend/app/services/submission_data_normalization.py)
- [Sơ đồ tổng quan luồng](documents/greencity-project/diagrams/diagram_0_overview.png)
- [Evidence pack V3-16](documents/greencity-project/phase-3/V3-16_PRESENTATION_EVIDENCE.md)
