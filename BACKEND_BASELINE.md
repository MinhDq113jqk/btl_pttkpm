# GREENCity Backend Current State

> Trạng thái mới nhất 10/09/2026: OD-ROLE đã được người dùng chốt cho tám role
> backend (chưa Kiểm toán). Unit360 đã có resource/building/field policy, migration
> 0003 và **135 tests pass** trên PostgreSQL cô lập. KTV chưa WO bị deny-by-default.
> Audit/readiness và các AC còn thiếu: **Partial-R1; Gate B/R1 NOT PASS**.
> Xem `backend/RBAC_R1.md` và mục mới nhất `backend/VALIDATION.md`; phần dưới là lịch sử.

> Cập nhật 10/09/2026 sau baseline: source hiện **Partial-R1**, đã sửa tenant/token
> và có **90 tests pass** trên PostgreSQL cô lập, migration từ trống/seed repeat.
> **Gate B/R1 vẫn NOT PASS**: RBAC building/assigned/resource và audit còn thiếu.
> Xem `backend/VALIDATION.md` mục mới nhất. Các bảng dưới đây là snapshot P0 trước
> thay đổi, không phải trạng thái runtime mới nhất.

Ngày kiểm tra: 2026-09-10. Nguồn chính: `plan2.md`; đối chiếu `roadmap_v2.md`.
Baseline trước thay đổi: commit `3cb1497`, working tree sạch.
Kết luận: **Pre-R1; Gate B NOT PASS; R1 NOT PASS**. Có foundation chạy test
offline, chưa có một vertical slice nghiệp vụ đủ điều kiện DONE.

## 1. Repository Overview / Environment

- Repository root: `C:/Users/LEGION/btl/_pttkpm`; thư mục cha `btl` không phải Git repo.
- Backend: `backend/`. Không sửa frontend trong hay ngoài checkout này.
- Đã đọc `plan2.md`, backend README/VALIDATION, toàn bộ Python application,
  migration, scripts và hai file test; đối chiếu roadmap, plan1 và role switch.
- **MISSING:** `backend/PHASE_0_AUDIT.md`. README root/backend liên kết đến file
  không tồn tại. Không tái dựng nội dung audit cũ bằng suy đoán.
- Không tìm thấy `AGENTS.md` được track; áp dụng chỉ dẫn người dùng trong phiên.
- Windows, Python `.venv` 3.12.14; `pip check` PASS.
- Phiên bản cài thực tế: FastAPI 0.141.1, Pydantic 2.13.5, pydantic-settings
  2.15.0, SQLAlchemy 2.0.52, psycopg 3.3.5, Alembic 1.19.2, pytest 9.1.1.
- Có requirements ranges và lockfile; không có pyproject. Không thêm dependency.
- PostgreSQL local 18.4, service running, `127.0.0.1:5432` accepting connections.
  Đây chỉ là kiểm tra availability, **không phải** authenticated connection/TLS.
- Docker CLI có, daemon không kết nối được cả sau kiểm tra ngoài sandbox.
- Không có `backend/.env`. Không đọc hoặc đưa credential từ tài liệu tài nguyên
  vào output; không dùng Aiven để chạy mutation trong lượt này.

## 2. Architecture Found / Existing Architecture

`create_app` (FastAPI factory/lifespan) → health router → Database (SQLAlchemy
sync engine/session, psycopg) → PostgreSQL schema `greencity`.

- `app/core/config.py`: env, SecretStr, TLS mode allowlist; production verify-full.
- `app/core/database.py`: pool 5/overflow 10, timeout, UTC, dependency get_session.
- `app/models/base.py`, `tenant.py`: UUID, TIMESTAMPTZ, Tenant name check.
- `app/core/exceptions.py`: error envelope; middleware: UUID correlation và log an toàn.
- Không có service/repository nghiệp vụ, auth dependency, policy hay schemas package
  tại baseline. DTO duy nhất là HealthResponse ngay trong router.
- README mô tả service/repository và Phase 8 Gemini là kế hoạch cũ, không phải code.
- `ARC-04` yêu cầu module theo capability; code foundation hiện chia theo tầng.
  Chưa cần rewrite foundation; domain mới phải có biên module rõ khi tới gate.

## 3. Implemented Capabilities / Existing Modules

`Có` không đồng nghĩa đạt DoD. `N/A` = không cần ở lớp hạ tầng đó.

| Capability | Có code | Có migration | Có API | Có policy | Có test | Có bằng chứng chạy | Trạng thái |
|---|---|---|---|---|---|---|---|
| Config/pool/TLS | Có | N/A | Gián tiếp health | Cấu hình TLS | Offline + PG opt-in | Offline pass; TLS thật chưa chạy lại | PARTIAL |
| Tenant | Có | 0001 | Không | Không | DDL + PG rollback | DDL offline pass; PG chưa chạy lại | PARTIAL |
| Health | Có | N/A | GET /health | Public, không dữ liệu domain | Mock + PG | Mock HTTP pass | PARTIAL (DB live chưa xác minh) |
| Error/correlation | Có | N/A | Middleware/handler | Không thay thế auth | Offline | Pass, chưa có audit domain | PARTIAL |
| Versioned contract | Không tại baseline | N/A | Không /api/v1 | N/A | Chưa | Chưa | MISSING |
| Auth/login/me/switch-site | Không | Không | Không | Không | Không | Không | MISSING |
| RBAC/scope/RLS | Không | Không | Không | Không | Không | Không | MISSING |
| Site/Building/Unit/Person/Relationship | Không | Không | Không | Không | Không | Không | MISSING |
| Seed idempotent hai site | Không | Không | N/A | Không | Không | Không | MISSING |
| Readiness kiểm revision/schema | Không | N/A | Không | Public dự kiến | Không | Không | MISSING |
| Audit nghiệp vụ | Chỉ request log | Không | Không | Không | Không actor/scope test | Không | MISSING |
| CSKH/kỹ thuật/vệ sinh/an ninh | Không | Không | Không | Không | Không | Không | MISSING |
| Tài chính cơ bản/KPI drill-down | Không | Không | Không | Không | Không | Không | MISSING |
| AI/portal/online payment/refund | Không backend | Không | Không | N/A | N/A | Không | SPEC-ONLY |

Không có capability nghiệp vụ nào được đánh dấu DONE.

## 4. Missing Capabilities / Authentication Status

Không có Account, role enum/table/seed, password hash, identity provider adapter,
JWT/session verification, login/me, active scope persisted ở server, logout/revoke.
`SECRET_KEY` đang reserved; có biến này không chứng minh có authentication.

Thiếu toàn bộ R1 Unit 360°, seed, policy, audit persist, optimistic locking,
idempotency và isolated PostgreSQL migration/seed harness. Không có state/business
tests cho R2–R5; không có Golden Flow hay demo login → Unit 360°.

## 5. Security / Scope Risks

### Authorization Status / Data Scope

Không có tầng `Authentication → Role → Tenant → Site → Building → Assigned → Resource`.
Tenant là tenant root; chưa có entity con, membership hoặc scoped query.
Không có RLS migration như lưới an toàn thứ hai của `ARC-03`.
Không có API nghiệp vụ để chứng minh IDOR hoặc cross-site exploit, cũng không thể
tuyên bố isolation pass chỉ vì chưa có dữ liệu để truy cập.

### Security Gaps

| Severity | Bằng chứng và giới hạn | Ưu tiên |
|---|---|---|
| HIGH (blocker trước domain API) | Auth/RBAC/scope chưa tồn tại; không phải một exploit đã tái hiện trên endpoint domain | Khóa policy trước mở dữ liệu |
| HIGH (rủi ro lịch sử, chưa xác minh lại) | VALIDATION 09/09 ghi runtime DB role có create_role/create_db/bypass_rls; chưa có cấu hình tách runtime/migrator trong repo | Tách role và test deny-by-default trước R1 nghiệm thu |
| HIGH (rủi ro lịch sử) | VALIDATION ghi credential AI từng lộ một phần; trạng thái rotation không biết | Chủ sở hữu xác minh rotation ngoài source; không gọi AI |
| MEDIUM | Development dùng require, không bảo đảm xác minh hostname/CA; production config ép verify-full | Kiểm TLS live đúng môi trường |
| MEDIUM | Test PG opt-in lấy DATABASE_URL chung và dùng DB đã migrate; không cô lập bằng harness | DB test riêng, không dùng tài nguyên Aiven mặc định |
| MEDIUM | Không audit durable actor/tenant/site; request log không thay audit | Migration + transactional audit trước R1 |
| LOW | OpenAPI tại baseline không mô tả error envelope dùng chung; FastAPI có thể tự sinh HTTPValidationError cho DTO mới | Nhóm contract P1 nhỏ |

Handler/middleware hiện che body, query, arbitrary path và DB exception trong test.
`.gitignore` che `.env`, tài liệu tài nguyên, CA/key; chỉ mẫu `.env.example` được track.
Đây không phải chứng nhận toàn bộ Git history sạch secret hay security scan toàn repo.
Frontend role switch/sessionStorage là mô phỏng, không có giá trị chứng minh server security.

## 6. Migration Status / Database

- Một revision `0001_initial_foundation.py`: chỉ CREATE `greencity.tenants`,
  check name không trắng, UUID PK, created/updated TIMESTAMPTZ. Không có version column.
- Alembic env tạo namespace trước version table; không `create_all`/auto-migrate runtime.
- `scripts.migrate heads`: **0001 (head)**; chỉ chứng minh revision trong source.
- `scripts.migrate upgrade head --sql`: **PASS** tạo SQL offline có namespace và tenants.
  **Không phải** chạy migration trên PostgreSQL trống.
- `VALIDATION.md` 09/09 ghi Aiven upgrade/current/check pass: bằng chứng lịch sử,
  không xác minh current revision hoặc schema drift trong lượt 10/09.
- `tests/test_postgres.py` chỉ assert revision có giá trị, không đối chiếu đúng head.
- Seed/migration-from-empty/constraint-negative/concurrency test: **MISSING**.
- Không áp dụng upgrade/downgrade hoặc sửa dữ liệu trên PostgreSQL local/Aiven.

## 7. Test Status / API Status

Baseline chạy lại: **25 passed, 3 integration deselected**, 2 deprecation warnings
Starlette/httpx/AnyIO. `pip check` PASS. Không sửa dependency để giấu warning.

- Offline: config/TLS validation, pool, DDL compile, HTTP mock health/error/CORS/logging.
- PG opt-in: TLS/schema/timezone, Tenant flush rollback, health dùng DB thật.
- Unit/domain tests: chưa có domain để kiểm. API tests hiện trộn trong foundation,
  không có auth/policy acceptance tests. PG integration có marker riêng.
- HTTP 200 trong test client không chứng minh DB reachable vì dependency bị mock.
- Tại baseline: `/health`, `/docs`, `/redoc`, `/openapi.json`; không `/api/v1`.
- Chưa có pagination/filter DTO, money VND DTO, version/conflict contract thực thi.
- UUID/UTC chỉ có ở model; chưa có datetime response contract nghiệp vụ.
- `/health` chỉ SELECT 1; không thay readiness/schema-version check.

## 8. Role Matrix Status

Quyền dưới đây là **spec/UI**, không phải quyền đã thực thi. Tất cả role đều không
có DB role enum/table, seed hoặc route permission và không có backend role test.
Nguồn S = roadmap §2.1/§9; F = `greencity-app/src/data/staffRoles.js`.

| Role | Nguồn | Scope theo spec | Quyền hiện tại | Test | Vấn đề |
|---|---|---|---|---|---|
| Admin | S + F admin | Tenant/site được cấp | UI danh mục/audit; backend chưa có | Backend không | Không mặc định superuser xuyên tenant |
| Giám đốc BQL | S + F director | Site phụ trách | UI xem/duyệt; backend chưa có | Backend không | Refund UI ngoài Plan 2 |
| Lễ tân/CSKH | S + F cskh | Tòa/quầy | UI tiếp nhận/tra cứu; backend chưa có | Backend không | Cần field masking và building membership |
| Kế toán | S + F accountant | Site/tập tòa | UI tài chính; backend chưa có | Backend không | Refund UI không thành sprint backend |
| Trưởng kỹ thuật | S, không F | Khu/tòa | Spec assign/accept; backend chưa có | Không | Không có tài khoản demo tương ứng |
| Kỹ thuật viên | S + F technical | WO được giao | UI assigned-only; backend chưa có | Backend không | F xác nhận không gộp quyền trưởng nhóm |
| Nhân viên vệ sinh | S + F cleaning | Nhiệm vụ/khu vực | UI assigned-only; backend chưa có | Backend không | Người lập/giao ca chưa rõ trong matrix |
| An ninh | S + F security | Ca/khu vực | UI tuần tra; backend chưa có | Backend không | Trưởng an ninh được BR nhắc nhưng chưa có role row |
| Cư dân | S | Quan hệ căn còn hiệu lực | Không backend | Không | V1, không đưa vào Core seed |
| Kiểm toán | S + F auditor | Read-only scope được cấp | UI đọc; backend chưa có | Backend không | Cần owner chốt danh sách role Core chính thức |
| System/Scheduler | S | Tenant/job được cấp | Không implementation | Không | Actor kỹ thuật, không tính thành human demo role |

## 9. Current R-Level

**Pre-R1**, không Partial-R2..R5 dù frontend có màn tương ứng. Model Tenant +
migration + 25 offline tests chỉ là foundation trước lát dọc R1. Không login/me,
Unit 360°, authorization, site isolation hoặc acceptance demo để gọi Partial-R1
theo luồng đã chạy. P0 inventory hoàn thành; các khả năng chưa kiểm giữ UNVERIFIED.

## 10. Gap To Next Gate / P0 Issues / P1 Issues

P0: thiếu audit file được link; DB test cô lập chưa xác minh; ghi nhận role conflict.
P1/Gate B: versioned route + DTO/error contract; policy trung tâm và membership;
role matrix được owner chốt; lifecycle/owner/exception/AC UC-04/16/17/18;
migration + seed hai site; đồng bộ release/AC và DEC-24. **Gate B chưa pass**.

### Open Decisions / OPEN_DECISIONS

1. **OD-ROLE / CONFLICT:** Plan 2 yêu cầu chốt tám role, nhưng S cần Trưởng KT
   riêng và F giữ Kiểm toán trong tám role, technical chỉ là KTV. PO/Admin/Vận hành
   chọn roster demo chính thức và cách demo người phân công/nghiệm thu. Không tự
   gộp Trưởng KT/KTV hoặc bỏ Kiểm toán để đạt con số tám.
2. **OD-OWNER / CONFLICT:** UC-17 nói Quản lý/NV vệ sinh; matrix cho Giám đốc
   accept nhưng không chỉ rõ ai create/assign Cleaning Shift. BR-SEC-03 nhắc
   Trưởng an ninh mà §2.1 không có role tương ứng. PO/Vận hành chốt quyền giao ca
   và acknowledgement/escalation, không trao quyền ngầm cho nhân viên thực thi.
3. **OD-RELEASE / CONFLICT:** roadmap R1 đòi AC-02 import, AC-24 private file và
   AC-35 đổi site/cache/file, trong khi lát R1 tối thiểu Plan 2 ưu tiên login/360°.
   Thực hiện Plan 2 trước, nhưng không tuyên bố PASS toàn bộ release R1 roadmap
   bằng subset đó. PO/QA phải phê duyệt mapping nghiệm thu trước khi đóng gate.
4. **OD-PMP:** DEC-24 còn OPEN; không có PROJECT_MANAGEMENT_PLAN được track.
   PM/PO xác nhận owner và baseline WBS/RACI; không tự tạo quyết định kinh doanh.

Plan1 refund/AI và hướng dẫn Phase 8 cũ **CONFLICT** với Plan2 nhưng đã được Plan2
giải quyết rõ: SPEC-ONLY, không cần hỏi lại. Quy mô seed 40/200 căn trong docs khác
nhau: lượt đầu dùng tối thiểu đủ hai site theo Plan2, không nhận là performance fixture.
Chọn công cụ DB test là vấn đề kỹ thuật/môi trường, không đưa vào quyết định nghiệp vụ.

## 11. Files That Need Changes

Nhóm gần nhất (P0 + contract P1, không đổi DB):

- `BACKEND_BASELINE.md` (file này), README root/backend, backend VALIDATION.
- `backend/app/main.py`, `app/api/health.py`, `app/core/exceptions.py`.
- Thêm `backend/app/schemas/errors.py`, `backend/tests/test_contract.py`,
  `backend/API_CONTRACT.md` để document và kiểm response thật/OpenAPI.

Sau khi giải quyết gate: auth/session, central policy/scope, domain migrations,
seed, isolated PG fixtures và golden-flow script. Đây là backlog, không phải file
đã được tạo hoặc chức năng đã làm.

## 12. Recommended Implementation Order

1. P0 baseline có bằng chứng, sửa link docs lỗi; không bịa audit lịch sử.
2. P1 nhóm contract hẹp: namespace `/api/v1`, DTO lỗi chung, OpenAPI/runtime parity,
   giữ `/health` compatibility; test regression. Không tạo API nghiệp vụ mới.
3. Chốt OD-ROLE/OWNER; đặc tả lifecycle UC-04/16/17/18 theo ST/BR/EX/AC đã có;
   khóa policy deny-by-default, field masking và contract còn thiếu.
4. Isolated PostgreSQL migration/seed harness; mô hình tenant/site/building/account
   membership + reviewed migration + seed hai site; kiểm empty DB và rerun.
5. Chỉ khi Gate B pass: R1 login/me/server active scope → Unit 360° → audit →
   negative/scope/concurrency tests → demo không secret. Tách runtime/migrator.
6. R1 pass mới tới R2 CSKH→KT; R3 vệ sinh/an ninh; R4 tài chính cơ bản;
   R5 KPI→source→timeline. Không frontend hoặc SPEC-ONLY trong lượt này.

**NEXT ACTION:** Nhóm số 2, chỉ phần contract foundation không phụ thuộc quyết định
role. Hoàn tất nhóm này vẫn không có nghĩa Gate B hoặc R1 pass.

## Commands Used To Verify

Từ repo root trừ khi ghi backend. Không chứa URI/secret.

```powershell
Get-Location
git rev-parse --show-toplevel
git status --short
git log -1 --format='%h %s'
rg --files backend
git ls-files backend
git check-ignore 'Tài_nguyên.md' backend/.env backend/.env.example
# Từ backend:
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q -m 'not integration'
.\.venv\Scripts\python.exe -m scripts.migrate heads
.\.venv\Scripts\python.exe -m scripts.migrate upgrade head --sql
# Chỉ đọc trạng thái local; docker daemon chưa chạy:
docker info --format '{{.ServerVersion}}'
Get-Service -Name postgresql-x64-18
& 'C:\Program Files\PostgreSQL\18\bin\postgres.exe' --version
& 'C:\Program Files\PostgreSQL\18\bin\pg_isready.exe' -h 127.0.0.1 -p 5432
```

Kết quả sau nhóm NEXT ACTION được ghi riêng trong `backend/VALIDATION.md`,
không hồi tố thay baseline trước sửa thành bằng chứng hoàn thành R1.
