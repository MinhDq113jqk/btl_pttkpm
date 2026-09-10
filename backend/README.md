# GreenCity Backend — Phase 1

## Trạng thái mới nhất — Unit360 RBAC R1

Đã chốt tám role backend và sửa quyền resource/tòa/trường dữ liệu cho Unit360.
**135 tests pass** trên PostgreSQL test cô lập; migration mới **0003** đã kiểm từ
DB trống, seed lặp an toàn. Xem [RBAC_R1.md](RBAC_R1.md) và [VALIDATION.md](VALIDATION.md).

CSKH/Trưởng KT/An ninh cần grant building tường minh. Vệ sinh bị 403; KTV chưa có
Work Order phân công nên bị 404. Residents bị policy ẩn sẽ trả [] và
`residents_visible=false`; An ninh nhận `area_m2/status=null`. Client không được
diễn giải dữ liệu bị ẩn thành không có dữ liệu.

0003 **chưa áp dụng lên Aiven/DB đang dùng**. Phải review/upgrade trước chạy code
mới; migration không tự cấp tòa cho grant cũ. Audit/readiness và các AC còn thiếu
khiến Gate B/R1 vẫn chưa PASS. Nội dung phía dưới giữ kết quả các lượt trước.

## Cập nhật mới nhất — sửa tenant/token, R1 vẫn chưa pass

Có auth/login/me/switch-site và Unit360 một phần. Đã sửa tenant boundary,
kiểm token/signing key, active-site query và 404 không lộ tồn tại. **90 tests pass**
trên PostgreSQL test mới, migration từ DB trống + seed hai lần. Chi tiết và giới
hạn trong [VALIDATION.md](VALIDATION.md). Resource/building/assigned RBAC, audit,
readiness và role decisions chưa đủ: không dùng dữ liệu thật hoặc triển khai public.

HTTP app nay **bắt buộc SECRET_KEY riêng**, không có development fallback.
Ví dụ tạo key chỉ cho phiên demo local hiện tại (giá trị không in ra màn hình):

```powershell
$env:SECRET_KEY = & .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

Đổi key làm token cũ mất hiệu lực; triển khai nhiều process phải dùng cùng key từ
secret store. Không đưa key vào source hoặc paste vào chat. Runner with-resources
chỉ nạp DB config, nên cần cấp SECRET_KEY riêng trước khi chạy HTTP server.
Migration/probe không yêu cầu signing key.

Chạy toàn bộ regression với PostgreSQL tạm, không chạm Aiven/DB đang dùng:

```powershell
.\.venv\Scripts\python.exe -m scripts.test_isolated --pg-bin 'C:\Program Files\PostgreSQL\18\bin' --openssl 'C:\Program Files\Git\usr\bin\openssl.exe'
```

Runner tạo/dừng/xóa đúng cluster localhost riêng, TLS CA/password/key ngẫu nhiên;
có thể cần quyền chạy local PostgreSQL ngoài sandbox. Không download dependency.
Các mục Phase/Plan cũ bên dưới là lịch sử, không ghi đè trạng thái mới nhất này.

## Trạng thái Plan 2 — 10/09/2026

**Pre-R1, Gate B chưa pass.** Đã kiểm lại foundation và thêm phần contract P1:
`GET /api/v1/health`, giữ `/health` làm alias tương thích không hiển thị trong
OpenAPI; DTO lỗi chung khớp OpenAPI/runtime. Chưa có auth/RBAC/Data Scope,
seed, Unit 360°, audit nghiệp vụ hoặc migration test trên DB trống cô lập.

Nguồn hiện tại: [plan2.md](../plan2.md),
[BACKEND_BASELINE.md](../BACKEND_BASELINE.md), [API_CONTRACT.md](API_CONTRACT.md).
`PHASE_0_AUDIT.md` được README cũ tham chiếu nhưng không tồn tại tại checkout.
Nội dung Phase bên dưới mô tả foundation lịch sử; mọi hướng phát triển AI,
refund hoặc frontend trong kế hoạch cũ bị hoãn theo Plan 2.

Nền tảng FastAPI cho hệ thống quản lý vận hành khu đô thị. Phase 1 có kết nối PostgreSQL, Tenant và health check; **chưa có auth, API nghiệp vụ, seed hay Gemini thật**.

## Kiến trúc và stack

Kiến trúc đích: React → REST/FastAPI → service → repository → PostgreSQL.
Hiện runtime chỉ có foundation và health, chưa có service/repository nghiệp vụ.
AI là SPEC-ONLY, không triển khai trong Plan 2.

Python 3.12+, FastAPI, Pydantic v2/pydantic-settings, SQLAlchemy 2, psycopg 3, Alembic, pytest. Dependency ranges nằm ở `requirements.txt`; dùng `requirements.lock.txt` để tái lập phiên bản Windows/Python 3.12 đã kiểm tra.

```text
backend/
  app/main.py              # application factory + lifecycle
  app/core/                # config, DB pool/session, error envelope
  app/api/health.py        # GET /api/v1/health + legacy /health
  app/schemas/errors.py    # ErrorEnvelope chung cho runtime và OpenAPI
  app/models/              # Base, UUID/UTC mixin, Tenant
  app/middleware/          # correlation ID + safe request logging
  alembic/                 # migration env + reviewed revisions
  scripts/                 # resource-env runner, preflight, safe Alembic CLI
  tests/                   # offline foundation + opt-in PostgreSQL integration
```

## Cài đặt (PowerShell, từ backend)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
```

Máy hiện tại chưa có `py` trên PATH; môi trường `.venv` đã được tạo bằng Python bundled. Khi cần tạo lại trên máy này:

```powershell
& 'C:\Users\LEGION\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m venv .venv
```

## Environment variables

`.env.example` chỉ là mẫu. App đọc `backend/.env` hoặc biến môi trường (biến môi trường ưu tiên); không tự đọc tài liệu tài nguyên. Không paste secret vào chat/lệnh có lịch sử.

| Biến | Ý nghĩa |
|---|---|
| DATABASE_URL | PostgreSQL URI, bắt buộc; postgres:// được đổi driver trong bộ nhớ |
| APP_ENV | development / test / production; mặc định development |
| DATABASE_SSL_ROOT_CERT | CA Aiven cục bộ; khi có dùng verify-full |
| CORS_ORIGINS | JSON array origin cụ thể; local mặc định 5173 và 3000, production phải HTTPS |
| SECRET_KEY | Dành cho JWT Phase 2; chưa dùng ở Phase 1 |
| GEMINI_API_KEY | Dành riêng chatbot Phase 8; chưa dùng ở Phase 1 |

Để dùng tài nguyên đã có mà không sao chép secret ra `.env`, runner PowerShell chỉ nạp DATABASE_URL vào môi trường tiến trình con và khôi phục sau lệnh. Runner không tải Gemini key. `Tài_nguyên.md/.txt`, `.env*`, CA/key đều được Git ignore; không sửa tài liệu nguồn.

## Aiven và migration

Pool mỗi process: size 5, overflow 10, pre-ping true, pool timeout/connect timeout/statement timeout 10 giây. Session PostgreSQL UTC. TLS không được disable/allow/prefer; development chấp nhận require. Production bắt buộc verify-full và cần CA hợp lệ theo [Aiven](https://aiven.io/docs/platform/concepts/tls-ssl-certificates).

Tài khoản tài nguyên hiện có quyền cao; chỉ dùng bootstrap/demo chưa có dữ liệu thật. Trước production phải có runtime role riêng ít quyền, migration role riêng; không dùng BYPASSRLS để tuyên bố bảo đảm isolation. Không tự cấp quyền trong Phase 1.

```powershell
# Chỉ đọc: kết nối, TLS, UTC và tên bảng; không in URI.
.\scripts\with-resources.ps1 -PythonArgs @('-m','scripts.db_probe')

# Áp dụng migration ĐÃ CÓ (không sinh lại initial mỗi lần chạy).
.\scripts\with-resources.ps1 -PythonArgs @('-m','scripts.migrate','upgrade','head')
.\scripts\with-resources.ps1 -PythonArgs @('-m','scripts.migrate','current')
.\scripts\with-resources.ps1 -PythonArgs @('-m','scripts.migrate','check')

# Chỉ dùng khi thay đổi models; đọc và review file mới trước upgrade.
.\scripts\with-resources.ps1 -PythonArgs @('-m','scripts.migrate','revision','--autogenerate','-m','describe_model_change')
```

`scripts.migrate` chạy Alembic CLI và che chi tiết exception chứa thông tin kết nối. Nếu đã cấp DATABASE_URL an toàn trong shell, lệnh chuẩn tương đương là `.\.venv\Scripts\python.exe -m alembic upgrade head`.

Schema `greencity` tách khỏi `public`. Migration runner chỉ khởi tạo namespace khi chưa tồn tại trong lệnh upgrade/revision, version table và model đều ở schema này. Autogenerate chỉ xét schema greencity, vẫn phải review mọi DROP/ALTER theo [Alembic](https://alembic.sqlalchemy.org/en/latest/autogenerate.html). Migration initial chỉ tạo tenants; không có `create_all()` runtime, không tự migrate khi server khởi động. Downgrade làm mất bảng/dữ liệu, không chạy trên Aiven để thử nghiệm. Offline SQL bootstrap namespace và không chứa URI thật.

## Chạy backend và kiểm tra HTTP

```powershell
.\scripts\with-resources.ps1 -PythonArgs @('-m','uvicorn','app.main:create_app','--factory','--host','127.0.0.1','--port','8000','--no-access-log')
```

Ở terminal khác:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
```

Kết quả thành công: `{"status":"ok","database":"connected"}`. DB lỗi trả 503 + `ERR-DATABASE-UNAVAILABLE`; không có thông tin kết nối. Health chỉ chứng minh DB reachable, không thay thế kiểm tra revision/schema hay auth.

Swagger: [localhost /docs](http://127.0.0.1:8000/docs). ReDoc: [localhost /redoc](http://127.0.0.1:8000/redoc). OpenAPI: `/openapi.json`.

Tắt access log thô của Uvicorn để không log query string. Middleware ghi method, route template, status, thời gian, correlation_id, user_id nếu auth gán về sau; không ghi body/header/driver exception. Client correlation ID không phải UUID được thay mới. Lỗi ứng dụng theo `{error:{code,message,correlation_id}}`; CORS preflight bị chặn là phản hồi giao thức 400 của middleware, không phải lỗi nghiệp vụ.

## Chạy frontend

```powershell
cd ..\greencity-app
npm ci
npm run dev
```

Frontend tại [localhost:3000](http://localhost:3000), vẫn là bản demo. Chưa thêm VITE_API_BASE_URL vào component hoặc thay service mock ở Phase 1; API client chung và auth adapter được nối ở Phase 2–3. Bản ngoài repo không bị chỉnh sửa.

## Seed và Gemini

Chưa có seed.py: Tenant còn trống, không tự tạo tài khoản ADMIN hoặc mật khẩu mặc định. Seed idempotent 2 sites/4 buildings/40 units và dữ liệu nghiệp vụ sẽ triển khai cùng models tương ứng; không bịa lệnh seed hiện chưa tồn tại.

Chatbot hiện là mô phỏng frontend. Phase 8 mới có ChatbotService → Gemini, ownership + site scope, context lấy qua repository, error handling độc lập. Không gọi Gemini trong lượt foundation. Nên xoay khóa Gemini trước tích hợp vì tài liệu credential đã được xử lý qua phiên làm việc.

## Testing

```powershell
.\.venv\Scripts\python.exe -m pytest -q -m 'not integration'
# Integration: chỉ chạy rõ ràng trên DB đã migrate; fixture Tenant rollback.
$env:RUN_DB_INTEGRATION = '1'
try {
    .\scripts\with-resources.ps1 -PythonArgs @('-m','pytest','-q','--tb=short')
} finally {
    Remove-Item Env:RUN_DB_INTEGRATION -ErrorAction SilentlyContinue
}
.\.venv\Scripts\python.exe -m pip check
```

Integration không DROP bảng/schema, không seed, không commit fixture. Bộ này
không thay thế test migration từ DB trống cô lập. Test auth/site chưa có vì
module chưa build; refund/chat nằm ngoài Plan 2. Xem
[baseline](../BACKEND_BASELINE.md). Bộ test hiện tại có deprecation warnings
từ test client của thư viện, không giấu warnings.

Kết quả lệnh đã chạy và các giới hạn: [VALIDATION.md](VALIDATION.md).
