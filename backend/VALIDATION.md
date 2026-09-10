# Backend — bằng chứng kiểm chứng

## Mới nhất — SEC-02 Unit360 RBAC/building/field policy (10/09/2026)

**Outcome: fixed** cho truy cập Unit360 vượt resource/building/field policy trong
slice R1 hiện có. **Partial-R1; Gate B/R1 NOT PASS**: audit/readiness và các AC
còn lại chưa được hoàn tất. KTV chưa có WO phân công thật nên bị deny-by-default;
không ghi nhận happy path assigned-only của R2 là đã build.

### Completed

- Người dùng đã xác nhận roster Core tám role backend: Admin, Giám đốc, CSKH,
  Kế toán, Trưởng kỹ thuật, KTV, Vệ sinh, An ninh; chưa có Kiểm toán. OD-ROLE đóng
  cho roster này, không còn là blocker của Unit360. Xem [RBAC_R1.md](RBAC_R1.md).
- Policy giữ từng cặp role + building scope, lọc Unit trước truy vấn quan hệ và
  tính projection theo đúng grant khớp tòa đích. Không nhân chéo role × tòa.
- Cleaning/unknown/auditor không được đọc Unit360 (403). Unknown/auditor cũng
  không tạo quyền site metadata trong auth/me. KTV không có WO: 404.
- CSKH/Trưởng KT/An ninh bắt buộc grant tòa; Admin/Giám đốc/Kế toán có thể được
  cấp site hoặc tòa. Null building không mở toàn site cho role cần tòa.
- Trưởng KT/An ninh không tải Person hoặc Unit Relationship và trả residents=[]
  với residents_visible=false. An ninh nhận area_m2/status=null; server vẫn có
  thể đọc cột Unit để tạo projection, không tuyên bố mọi field ẩn đều không SELECT.
- Thu hồi grant hoặc quyền xem residents có hiệu lực với token hiện hữu ở
  request kế tiếp. Role/building giả trong token/header/query không tăng quyền.

### Files Changed

- `app/core/policy.py`, `app/api/units.py`, `app/schemas/unit.py`.
- `app/models/account.py`, `app/models/building.py` và revision mới
  `alembic/versions/0003_role_building_scope.py`.
- `scripts/seed.py`: cấp grant tòa tường minh cho các tài khoản demo được chỉ rõ,
  kể cả account đã có; không suy scope cho account bất kỳ hoặc xóa grant cũ.
- Thêm `tests/test_rbac_boundary.py`; mở rộng `tests/test_security_postgres.py`.
- Tài liệu RBAC_R1/VALIDATION/README/API_CONTRACT; root plan2/implementation_plan/
  BACKEND_BASELINE để ghi quyết định và kết quả hiện tại.
- Không sửa frontend, không thêm dependencies/module R2, không commit/push.

### Migration

- `0003` thêm AccountRole.building_id, index, check building cần site, FK ghép
  building/site và unique target. Xóa building CASCADE thu hồi grant, không SET
  NULL thành quyền site-wide. Không sửa revision 0001/0002.
- **Đã chạy từ DB trống đến 0003 và upgrade lại trên PostgreSQL test cô lập**.
- Seed hai lần giữ số lượng: 1 tenant, 2 sites/buildings/units/persons/relations,
  9 accounts, 9 role grants. Grant demo tòa có căn cứ rõ trong seed.
- **Chưa áp dụng 0003 lên Aiven/DB đang dùng.** Trước chạy bản app này với môi
  trường khác phải review/upgrade migration. Grant site-only cũ cho role cần tòa
  sẽ không match Unit: cần provision tòa tường minh, không migration ngầm cấp quyền.
- Không thử downgrade hoặc khẳng định Alembic drift toàn schema đã sạch.

### Tests Added / Tests Executed / Test Results

Thêm **45 ca** (parameterized): 4 offline + 41 PostgreSQL, gồm tất cả Core roles,
role ngoài roster, same-site khác tòa, mixed-grant cùng/khác tòa, field revocation,
SQL không tải household, forged claims, FK sai site/tenant và cascade thu hồi.

| Verification | Kết quả |
|---|---|
| RED `pytest -q tests/test_rbac_boundary.py --tb=short` trước sửa | 4 failed; cả 4 role không đủ quyền từng nhận 200 |
| `python -m compileall -q app tests scripts` | PASS |
| Offline regression trước 7 ca PG cuối | 75 passed, 53 deselected, 2 warnings |
| Offline regression cuối | 75 passed, 60 deselected, 2 warnings |
| PostgreSQL runner lượt đầu | 128 passed, 2 warnings |
| PostgreSQL runner lượt cuối | **135 passed, không skip, 2 warnings**, pytest 18.89 s |
| Empty DB migrate + upgrade repeat + seed repeat | PASS trên PostgreSQL 18.4/TLS verify-full |
| `python -m pip check`; `git diff --check` | PASS |

Lệnh từ backend, bằng `.venv/Scripts/python.exe`:

```powershell
.\.venv\Scripts\python.exe -m scripts.test_isolated --pg-bin 'C:\Program Files\PostgreSQL\18\bin' --openssl 'C:\Program Files\Git\usr\bin\openssl.exe'
```

### Security/Scope Verification

Đường lỗi: Account có site membership → Unit ID lookup → tải household không
kiểm role/tòa. Sau sửa, trigger role không hợp lệ bị 403 trước Unit SELECT;
scope/assignment thiếu nhận 404; mixed CSKH tòa A + An ninh/Trưởng KT tòa B không
trả hoặc query household tòa B. PostgreSQL tests xác minh hành vi, không chỉ mock.

Control hợp lệ vẫn pass: CSKH đúng tòa xem Unit/residents masked; Admin và các
role site-wide được cấp truy cập đúng site; nhiều grant cùng tòa có thể kết hợp
quyền hợp lệ. Giữ regression tenant/token từ bản sửa trước.

Theo fix-finding, đã có điều tra và candidate review độc lập read-only; reviewer
không thấy bypass cụ thể trong phạm vi. Karpathy-guidelines giữ thay đổi tại grant
và Unit read policy; hướng dẫn PostgreSQL được dùng cho FK ghép/index. Không thêm
bảng Unit assignment giả để thay thế Work Order chưa tồn tại.

### Remaining Issues / Next Recommended Step

1. Durable audit (actor/tenant/site/time/correlation) và readiness/schema version.
2. Contract/lifecycle/AC Gate B còn thiếu, DATA-01, RLS/runtime least-privilege,
   schema drift và mapping R1 tối thiểu với roadmap. OD-LOGIN/OWNER/PMP vẫn mở.
3. Khi tới R2, nối KTV với WO assignment thật; hiện chỉ có negative/fail-closed
   coverage. Đây không phải yêu cầu build WO trước R1, tránh phụ thuộc vòng.
4. An ninh mới có geographic/building read scope; authorization ca trực/tuần tra
   thuộc R3, chưa được nhận là hoàn tất.
5. Không có API quản trị grant; hiện provision qua seed/demo hoặc DB administration
   được ủy quyền. Không đưa code này thành sản phẩm production-ready chỉ từ test count.

Các cluster test của lượt này đã dừng và xóa đúng thư mục tạm; không có dữ liệu
người dùng bị xóa, không dùng credential Aiven hoặc thay đổi DB đang chạy sẵn.

## Xác minh mới nhất — Group 1 tenant/token + DB test cô lập (10/09/2026)

**Outcome:** `fixed` cho SEC-01 (tenant), SEC-03 (signing config/parser), SEC-05
(scoped 404), và phần scope của SEC-04. **Chưa hoàn tất toàn bộ Nhóm 1**:
SEC-02 resource/building/assigned authorization còn blocked bởi mô hình cấp quyền/
OD-ROLE; SEC-04 durable audit còn thiếu. **Partial-R1; Gate B/R1 NOT PASS.**
Mục “Gate B & Release R1 hoàn tất” phía dưới là tuyên bố lịch sử đã bị lần kiểm tra
này bác bỏ; 55 tests xanh không đủ chứng minh gate pass.

### Completed

- App bắt buộc SECRET_KEY tường minh >=32 bytes; loại bỏ mọi signing-key fallback.
  Migration/probe chỉ cần DB config, không bị buộc nạp key xác thực.
- JWT kiểm header HS256, JSON/object/claim types, UUID, expiration hữu hạn và
  `exp <= now`, signature, base64url canonical, duplicate keys; lỗi trả 401 an toàn.
- `context_for_account` tập trung giải scope từ Account/AccountRole/Site trong DB.
  Site luôn thuộc tenant; admin site-specific không thành tenant-wide; None/empty
  không là wildcard. Role phản ánh active site, không cộng quyền từ site khác.
- Unit query join Building→Site, lọc tenant + membership + active site trước tải
  relationships. Person sai tenant không được load/serialize dù FK quan hệ sai.
- Login/me/switch-site dùng chung resolution; switch kiểm site tồn tại và tenant,
  refresh membership trước ký token. Claim role/tenant không ghi đè DB identity.
- Missing/out-of-scope/inactive-site trả cùng 404 code/message, trừ correlation.
- Username trùng giữa tenants fail closed 401, không đoán tenant hay phát 500;
  giải pháp định danh cuối cùng vẫn cần OD-LOGIN.
- `scripts.test_isolated` tạo PostgreSQL cluster mới trên localhost với SCRAM,
  TLS verify-full và khóa/mật khẩu ngẫu nhiên, chạy migration/seed/tests rồi dọn.

### Files Changed (chỉ phần thực hiện trong lượt này)

- `app/core/config.py`, `security.py`, `policy.py`; `app/api/auth.py`, `units.py`;
  `app/main.py`.
- Thêm `tests/test_security_boundary.py`, `tests/test_security_postgres.py`,
  `scripts/test_isolated.py`; cập nhật fixture trong `test_foundation.py`,
  `test_contract.py`, `test_r1_integration.py`.
- `.env.example`, `README.md`, `VALIDATION.md`, `API_CONTRACT.md`;
  root `.gitignore`, `BACKEND_BASELINE.md`, `implementation_plan.md`.
- Không sửa models, revision 0001/0002, seed implementation, frontend, dependencies
  hoặc tài liệu credential. Giữ các thay đổi R1 đã có sẵn trong working tree.

### Migration / Tests Added / Tests Executed / Test Results

Không tạo revision mới. Đã dùng migration hiện có từ DB trống đến **0002**.
Thêm **35 ca**: 26 offline và 9 PostgreSQL (bao gồm parameterization).

| Verification gate / command (từ backend) | Kết quả |
|---|---|
| RED `python -m pytest -q tests/test_security_boundary.py --tb=no` trước sửa | 22 failed, 4 passed: tái hiện fallback/parser/expiry/None/Admin |
| Syntax/import `python -m compileall -q app tests scripts` | PASS |
| Focused/offline `python -m pytest -q -m 'not integration' --tb=short` | **71 passed, 19 deselected**, 2 warnings |
| Isolated runner, command đầy đủ bên dưới | **90 passed**, không skip, 2 warnings, pytest 5.55 s |
| Empty DB upgrade + repeat | PASS, head 0002 được assert trên DB thật |
| Seed + repeat | PASS; 1 tenant, 2 sites/buildings/units/persons/relationships, 9 accounts/roles |
| Live TLS | PASS; connection dùng verify-full với test CA và assert pg_stat_ssl |
| `python -m pip check`; `git diff --check` | PASS |

```powershell
.\.venv\Scripts\python.exe -m scripts.test_isolated --pg-bin 'C:\Program Files\PostgreSQL\18\bin' --openssl 'C:\Program Files\Git\usr\bin\openssl.exe'
```

Lượt đầu initdb bị sandbox chặn, chạy lại bằng quyền được duyệt. Trình runner ban
đầu mắc inherited-pipe của pg_ctl trên Windows; đã dừng đúng cluster test và đổi
infrastructure stdout/stderr sang DEVNULL. Lượt tiếp theo 87 pass/2 fail do test
offline kế thừa CA integration; đã giữ assertion TLS, đặt CA=None tường minh trong
fixture offline. Cache được chuyển vào thư mục của mỗi lượt test để tránh ACL
chéo tài khoản. Lượt cuối 90 pass; không filter/hide deprecation warnings.

### Security/Scope Verification

- Tái hiện trước sửa: Admin tenant A đọc Unit B trả 200 ở HTTP mock probe;
  sau sửa test HTTP với DB PostgreSQL thật trả **404**, kể cả cùng mã hiển thị.
- Person tenant B liên kết sai với Unit A không xuất hiện trong response.
- Cross-tenant AccountRole không lọt login/me; site giả/ngoài tenant switch trả 404.
- Grant bị thu hồi và account bị khóa được kiểm lại từ DB ở request sau.
- Control hợp lệ: same-site CSKH đọc thành công, tenant Admin switch site hợp lệ
  rồi đọc thành công. Test Admin cũ được sửa để switch rõ trước mỗi site theo
  active-scope requirement, không bỏ kiểm tenant hoặc nới assertion.
- Hai lượt agent read-only theo skill fix-finding: investigation trước patch và
  candidate review sau patch; reviewer không thấy bypass cụ thể còn lại **trong
  phạm vi tenant/token đã sửa**. Review tĩnh không thay runtime evidence.
- Skill PostgreSQL best practices giữ tenant filter tại query và tách môi trường
  kiểm thử. Test dùng migrator privilege; **không** chứng minh production DB role
  least-privilege hay RLS.

### Remaining Issues / Next Recommended Step

**SEC-02 còn HIGH:** Unit360 chưa gọi policy resource/field/building/assigned đầy
đủ; cleaning cùng site vẫn chưa được bảo đảm bị chặn. Không dùng dữ liệu thật
hoặc mở demo public. Không tuyên bố full RBAC, audit hay R1 pass từ 90 tests này.

- Chốt OD-ROLE và representation membership building/assignment/field policy,
  rồi viết test role không phù hợp, same-site khác building và assigned-only trước
  khi mở quyền. Không tự đổi roster tám role.
- Thêm durable audit + readiness; active site hiện là phạm vi trên token đã được
  server kiểm membership, chưa có session-wide revoke/invalidating old tokens sau switch.
- Alembic drift check, schema corrections DATA-01, FK tenant consistency, RLS,
  runtime least-privilege và concurrent seed/locking vẫn chưa được nghiệm thu.
- Seed repeat hiện chỉ kiểm tuần tự; không đồng nghĩa chịu được concurrent seed.
- Chưa có acceptance demo script cho operator, lifecycle UC-04/16/17/18 hoặc
  mapping toàn bộ AC R1 được owner phê duyệt. Chưa frontend/R2.
- Các cluster test phát sinh trong lượt này đã được dừng và xóa; không còn dữ
  liệu test cần khôi phục. Không sửa PostgreSQL đang chạy sẵn/Aiven, không commit/push.

## Lịch sử: tuyên bố Gate B & Release R1 hoàn tất — CHƯA ĐẠT sau kiểm tra lại

### Completed
- **Data Models R1**: Hoàn thành các entity `Site`, `Building`, `Unit`, `Person`, `UnitPersonRelationship`, `Account`, `AccountRole` cùng `RoleEnum` (8 roles), `UnitStatusEnum`, `RelationshipTypeEnum`.
- **Migration Alembic 0002**: Tạo `0002_r1_foundation.py` và áp dụng thành công lên PostgreSQL thật (`0002 (head)`).
- **Idempotent Seed 2 Sites**: Script `scripts/seed.py` nạp dữ liệu mẫu không PII cho 2 site (`GC-WEST` và `GC-EAST`), 8 tài khoản phân quyền tương ứng; kiểm tra chạy lại (idempotency) hoàn toàn an toàn.
- **Central Policy & Data Scope**: Cài đặt `app/core/policy.py` với `UserContext` và `get_current_user_context`. Bắt buộc kiểm tra quyền server-side; chặn truy vấn cross-site bằng mã lỗi `404 ERR-SCOPE-NOTFOUND` (deny-by-default, không lộ sự tồn tại của tài nguyên ngoài phạm vi).
- **Authentication & Tra cứu căn hộ 360° API**:
  - `POST /api/v1/auth/login`
  - `GET /api/v1/auth/me`
  - `POST /api/v1/auth/switch-site`
  - `GET /api/v1/units/{unit_id}/360`
- **Bộ kiểm thử tích hợp R1**: `tests/test_r1_integration.py` gồm 7 test cases kiểm tra login, me, cùng scope xem được, khác site nhận 404, admin xem đa site, switch site bảo vệ scope.

### Kết quả kiểm thử thực tế
- **Offline test suite**: 45 passed, 0 failed.
- **PostgreSQL live integration test**: 10 passed (3 tests hạ tầng + 7 tests R1 integration), 0 failed.
- **Tổng toàn bộ test suite**: **55 passed**, 0 failed, 3 warnings trong 23.53s.

## Plan 2 / P0 + P1 contract subset — 10/09/2026

### Completed

- Kiểm tra checkout `_pttkpm`, working tree sạch tại commit `3cb1497` trước sửa.
- Đọc source/config/models/routes/migration/scripts/tests và đối chiếu Plan 2,
  roadmap, role switch. Ghi đủ 12 mục, capability/role matrix, rủi ro và
  OPEN_DECISIONS trong `../BACKEND_BASELINE.md`.
- Phát hiện `PHASE_0_AUDIT.md` không tồn tại; sửa link README trỏ baseline mới,
  không dựng lại audit lịch sử.
- Thêm `/api/v1/health`, giữ legacy `/health` cùng handler, không publish alias.
- ErrorEnvelope/ErrorDetail dùng chung runtime và OpenAPI; giữ cấu trúc lỗi cũ,
  UUID correlation, redaction, 401 challenge và 405 Allow.
- Skill karpathy-guidelines giới hạn thay đổi vào contract foundation có test;
  không dựng model/policy placeholder hoặc tự chọn role đang mâu thuẫn.

### Files Changed

- `../BACKEND_BASELINE.md` (mới), `../README.md`.
- `README.md`, `VALIDATION.md`, `API_CONTRACT.md` (mới).
- `app/main.py`, `app/core/exceptions.py`.
- `app/schemas/__init__.py`, `app/schemas/errors.py` (mới).
- `tests/test_contract.py` (mới).

Không sửa frontend, dependencies, model, migration hoặc tài liệu tài nguyên.
Không commit/push, không thay đổi database.

### Migration

- Source head: `0001 (head)`; offline SQL upgrade generation pass.
- Không tạo migration mới: thay đổi này chỉ là HTTP contract, không đổi schema.
- **Chưa chạy upgrade từ DB trống hoặc Alembic check với DB thật trong lượt này.**
- PostgreSQL local 18.4 service running/port ready; chưa xác minh login/TLS/schema.
- Docker daemon không chạy; lần kiểm tra read-only ngoài sandbox cũng không kết nối được.

### Tests Added

20 test cases trong `tests/test_contract.py` (tính cả parameterization):
versioned/legacy health, production route inventory không có test probes,
OpenAPI error schema cho 8 HTTP status, validation/malformed JSON,
401/403/404 handler shape, 404 redaction, 405 Allow,
500/503 redaction và correlation. Các lỗi response được validate bằng ErrorEnvelope.

### Tests Executed / Test Results

Chạy từ `backend/` bằng `.venv/Scripts/python.exe`:

| Lệnh / bước | Kết quả thực tế |
|---|---|
| `--version` | Python 3.12.14 |
| `-m pip check` trước/sau | No broken requirements found |
| `-m pytest -q -m 'not integration'` trước sửa | 25 passed, 3 deselected |
| `-m pytest -q tests/test_contract.py --tb=short` RED, 18 ca ban đầu | 13 failed, 5 passed; thiếu route versioned/OpenAPI envelope |
| `-m pytest -q -m 'not integration'` GREEN, 18 ca ban đầu | 43 passed, 3 deselected |
| `-m pytest -q` sau thêm 2 ca | **45 passed, 3 skipped**, 2 warnings, 1.39 s |
| `-m scripts.migrate heads` | 0001 (head) |
| `-m scripts.migrate upgrade head --sql` | SQL generation pass; không kết nối DB |
| `git diff --check` | PASS; có thông báo chuyển LF→CRLF, không lỗi whitespace |

Hai warnings vẫn là Starlette/httpx/AnyIO deprecation; không che warnings.
Ba PG tests skip theo opt-in hiện hữu, không được tính pass. Không chạy lại các
test UI hoặc nhận kết quả frontend cũ là kết quả mới.

### Security/Scope Verification

- HTTP contract test chạy qua FastAPI TestClient, injected Mock Database;
  đã kiểm không rò payload/path/query/exception giả nhạy cảm trong những ca được test.
- 401/403 và ERR-SCOPE-NOTFOUND được phát bởi route probe **chỉ trong test**.
  Không gọi chúng là authentication/RBAC/cross-site acceptance.
- Production OpenAPI chỉ có `/api/v1/health`; `/health` alias vẫn public.
- Không lấy hoặc sử dụng credential Aiven, không ghi fixture lên shared DB.
- Không chứng minh runtime role least-privilege, RLS, durable audit hoặc IDOR isolation.

### Remaining Issues

**Pre-R1; Gate B NOT PASS; R1 NOT PASS** không thay đổi sau patch.
Thiếu role roster/owner đã chốt, central policy, pagination/UTC/VND/version
contract domain, lifecycle acceptance pack, seed, auth/me, Unit 360°,
audit và PostgreSQL migration/seed/concurrency harness cô lập.
Xem OD-ROLE/OWNER/RELEASE/PMP trong baseline; không âm thầm chọn quyền từ UI.

### Next Recommended Step

P1 tiếp theo: test harness PostgreSQL cô lập cho migration từ DB trống,
đối chiếu đúng head/schema và constraints, không mặc định dùng tài nguyên Aiven.
Song song về mặt chuẩn bị nghiệp vụ (chưa triển khai quyền): owner chốt
OD-ROLE/OWNER rồi khóa lifecycle/policy/contract và seed hai site để qua Gate B.
Chưa mở R1 endpoint hay R2–R5 trước khi gate đủ bằng chứng.

## Phase 1 — bằng chứng lịch sử 09/09/2026

Ngày chạy: 09/09/2026, Windows, Python 3.12.14, repo `_pttkpm`.

| Kiểm tra đã chạy | Kết quả |
|---|---|
| `pytest -q -m 'not integration'` | 25 passed, 3 integration deselected |
| `RUN_DB_INTEGRATION=1` + `pytest -q --tb=short` | 28 passed, gồm 3 test Aiven thật |
| `pip check` | No broken requirements found |
| Aiven preflight trước migration | Không có bảng người dùng; TLS true, timezone UTC |
| Alembic revision --autogenerate | Sinh `0001_initial_foundation.py`; đã đọc trước upgrade, chỉ CREATE tenants trong schema greencity |
| Alembic upgrade head | Exit 0 |
| Alembic current | `0001 (head)` |
| Alembic check | `No new upgrade operations detected.` |
| Uvicorn local 127.0.0.1:8000 | Startup complete |
| HTTP GET /health | 200, `{"status":"ok","database":"connected"}` |
| HTTP GET /docs, /redoc, /openapi.json | Cả 3 trả 200 |
| Correlation + CORS live | Trả đúng UUID gửi lên và origin localhost:3000 |
| Frontend npm test | 40 passed, 0 failed |
| Frontend npm run build | Vite 6.4.3, 1615 modules, build thành công |
| `git diff --check` | Không có lỗi whitespace ở tracked diff |
| Quét secret nguồn với URI/key/password lấy trong bộ nhớ | Không có khớp trong 31 file được kiểm tra; không in giá trị secret |
| Git ignore | Hai file Tài_nguyên và backend/.env bị ignore; .env.example không bị ignore |

## Giới hạn và lỗi môi trường đã xử lý

- Lần tải pip và kết nối Aiven trong sandbox bị chặn mạng; đã chạy lại qua quyền được duyệt.
- Runner PowerShell ban đầu nhận sai tham số vị trí; sửa PositionalBinding và dùng PythonArgs tường minh, migration chạy lại thành công.
- Bản frontend trong repo chưa có node_modules; `npm ci` theo lockfile rồi build. Vite bị chặn đọc thư mục cha trong sandbox; build lại với quyền được duyệt đã đạt. Không sửa source frontend hoặc lockfile.
- Có 2 deprecation warnings từ Starlette/httpx/AnyIO test client; integration còn có PytestCacheWarning do quyền cache giữa tài khoản sandbox và tài khoản chạy được duyệt. Đây không phải test fail; không che warnings.
- Không chạy lại UX browser suites vì source/UI không thay đổi. Kết quả 40 tests và build không được diễn đạt thành toàn bộ E2E UI đã pass.
- Health chứng minh kết nối DB, không chứng minh API domain/auth đã hoàn tất. 9 test nghiệp vụ trong yêu cầu thuộc Phase 2–8, chưa được đánh dấu pass.
- Aiven hiện có schema greencity, tenants và alembic_version. Test insert Tenant dùng transaction rollback; không nạp seed hay tạo account.
- TLS require ở development không tương đương xác minh CA/hostname verify-full. Role hiện có create_role/create_db/bypass_rls; phải tách role trước production.
- Chưa gọi Gemini. Nên thay khóa Gemini trước Phase 8 vì bộ lọc output đầu phiên đã bỏ sót đoạn đuôi có escape Markdown; không lặp lại khóa trong source/tài liệu.
- Không commit, push, xóa dữ liệu hay sửa nội dung secret gốc.

Theo karpathy-guidelines, chỉ tạo model Tenant và foundation cần kiểm chứng, không scaffold các module domain rỗng. Hướng dẫn PostgreSQL được áp dụng cho pool và ghi rõ giới hạn least-privilege/TLS; không cài thêm Supabase.
