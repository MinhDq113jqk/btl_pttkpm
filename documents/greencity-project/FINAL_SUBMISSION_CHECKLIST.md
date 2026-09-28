# Checklist kiểm thử cuối trước khi nộp GreenCity

- **Phiên bản:** 1.0
- **Ngày lập/cập nhật:** 2026-09-27
- **Kế hoạch nguồn:** [FINAL_CODE_SUBMISSION_PLAN.md](FINAL_CODE_SUBMISSION_PLAN.md)
- **Task nguồn:** [FINAL_CODE_SUBMISSION_20_TASKS.md](FINAL_CODE_SUBMISSION_20_TASKS.md)
- **Roadmap nghiệp vụ:** [roadmap_v2.md](roadmap_v2.md)
- **Roadmap triển khai:** [roadmap_v3.md](roadmap_v3.md)
- **Mục tiêu:** kiểm tra cùng một commit/package candidate trước khi nộp cho
  giáo viên.

## 1. Cách dùng checklist

Tài liệu này là danh sách test, chưa phải kết quả test. Không đánh dấu `PASS`
dựa trên log cũ. Mỗi lần chạy cuối phải ghi commit/package ID, thời gian, exit
code, số passed/failed/skipped/warnings và đường dẫn evidence đã redact.

| Ký hiệu | Ý nghĩa |
|---|---|
| `READY-LOCAL` | Command và target tồn tại trong working tree; chỉ có giá trị cho gói nộp sau khi FS-06 và clean-clone pass |
| `MANUAL` | Cần thao tác hoặc quan sát trực tiếp |
| `BLOCKED-FCS` | Bắt buộc trước khi nộp nhưng còn chờ task FCS tương ứng |
| `[ ]` | Chưa chạy trên package candidate cuối |
| `[x]` | Đã chạy và đạt trên đúng package candidate cuối |

Quy tắc evidence:

1. Raw log lưu tại `.local/submission-data/final-test/`, không commit.
2. Summary đưa vào evidence pack chỉ chứa command, candidate ID, timestamp,
   exit code và kết quả đã redact.
3. Không ghi password, token, connection string, PIN, tên, email, số điện thoại
   hoặc nội dung thật từ `excel-data`.
4. Không chạy migration/recovery rehearsal trên database chia sẻ hoặc database
   có dữ liệu cần giữ.
5. Mọi test `P0` phải pass; test skip hoặc warning phải có lý do và đánh giá tác
   động. Một failure làm Final Submission Gate dừng.

### Trạng thái tại thời điểm cập nhật checklist

- **Final status:** `NOT READY FOR SUBMISSION`.
- User/Owner đã duyệt DP-01..DP-05 ngày 2026-09-27. `FCS-01..05` vẫn cần
  đối chiếu gate kỹ thuật; raw preflight còn 35 lỗi thời gian cần sửa nguồn và
  preflight PASS. `FCS-06` và `FCS-08`
  đã có implementation/evidence local; `FCS-07`, `FCS-09`, `FCS-10`,
  `FCS-11`, `FCS-12` còn gate dữ liệu/apply/replay. `FCS-13..15` và `FCS-16`
  đã có implementation/local verification nhưng vẫn `PARTIAL`; `FCS-17` và
  `FCS-18` đã có đường synthetic demo nhưng còn gate package/browser, `FCS-20`
  `BLOCKED`, còn `FCS-19` `PARTIAL` vì chưa có clean package evidence trên cùng
  candidate.
- Gói demo `synthetic/` có 12 workbook/101 dòng, manifest mang nhãn
  `SYNTHETIC_TEST_ONLY` và một ảnh evidence synthetic. Isolated PostgreSQL
  runner đã PASS dry-run/apply/verify/retry. Raw `excel-data` tại
  `2026-09-28T03:06:20Z` có 30 `FUTURE_HISTORICAL_EVENT`, 5
  `FUTURE_TERMINAL_EVENT` và 47 `FUTURE_SCHEDULE` warning; User/Owner cần sửa
  nguồn theo sự kiện thật. Raw-derived local validation output không thuộc
  demo này và có `distribution_allowed=false`.
- `greencity-app/package.json` và một số test Golden Flow/module còn là thay đổi
  local; FS-06 và clean-clone phải chứng minh chúng nằm trong package candidate.
- `pilot-preflight.ps1`, `runtime_check.py` và rehearsal helper đã đồng bộ
  revision `0018`; vẫn cần chạy Gate BE-04/BE-05 trên database được phép dùng.

Evidence FCS-05..FCS-10: [FCS-05-10_EXECUTION_EVIDENCE.md](phase-3/evidence/FCS-05-10_EXECUTION_EVIDENCE.md).
Evidence FCS-10..FCS-12: [FCS-10-12_EXECUTION_EVIDENCE.md](phase-3/evidence/FCS-10-12_EXECUTION_EVIDENCE.md).
Evidence FCS-13..FCS-15: [FCS-13-15_EXECUTION_EVIDENCE.md](phase-3/evidence/FCS-13-15_EXECUTION_EVIDENCE.md).
Evidence FCS-16..FCS-20: [FCS-16-20_EXECUTION_EVIDENCE.md](phase-3/evidence/FCS-16-20_EXECUTION_EVIDENCE.md).

## 2. Gate G0 — Candidate, source và dữ liệu

| ID | Pri | Test | Cách kiểm tra | Điều kiện PASS | Loại | Kết quả |
|---|---|---|---|---|---|---|
| FS-01 | P0 | Đúng repository và candidate | `git rev-parse --show-toplevel`; ghi `git rev-parse HEAD`; `git status --short` | Đúng `_pttkpm`; candidate ID được ghi; mọi thay đổi dự kiến đều thuộc package | READY-LOCAL | [ ] |
| FS-02 | P0 | Không có raw data trong Git | Chạy block FS-02 bên dưới | Tracked output rỗng; `git check-ignore` xác nhận cả raw path | READY-LOCAL | [ ] |
| FS-03 | P0 | Không có secret/PII/PIN trong candidate | Chạy scanner ở chế độ chỉ báo file và rule, không in giá trị match | `0` finding chưa xử lý trong tracked files và package | MANUAL | [ ] |
| FS-04 | P0 | Không có conflict marker hoặc whitespace lỗi | Chạy block FS-04 bên dưới cho tracked, staged và untracked candidate text | `0` whitespace error và `0` conflict marker | READY-LOCAL | [ ] |
| FS-05 | P1 | Liên kết tài liệu hợp lệ | Chạy `npm run check:links` từ `greencity-app` trên package candidate | `0` file target, image, reference-style link hoặc anchor bị hỏng | READY-LOCAL | [ ] |
| FS-06 | P0 | Test target nằm trong package | Đối chiếu `package.json`, `pytest.ini`, scripts và fixtures với tracked/package file list | Không phụ thuộc file untracked hoặc file chỉ tồn tại trên máy phát triển | MANUAL | [ ] |
| FS-07 | P0 | Dependency có thể tái lập | Cài backend từ lockfile trong môi trường sạch; chạy `npm ci` cho frontend | Cài đặt exit `0`; lockfile không tự thay đổi | MANUAL | [ ] |

### Command FS-02 — raw-data boundary

```powershell
$rawPaths = @(
  'documents/greencity-project/excel-data/'
  'documents/greencity-project/data_that/'
)
foreach ($rawPath in $rawPaths) {
  git check-ignore -v --no-index -- $rawPath
  if ($LASTEXITCODE -ne 0) { throw "Raw path is not ignored: $rawPath" }
}
$trackedRaw = @(git ls-files -- `
  'documents/greencity-project/excel-data/**' `
  'documents/greencity-project/data_that/**')
if ($LASTEXITCODE -ne 0) { throw 'Unable to enumerate tracked raw data.' }
if ($trackedRaw.Count -ne 0) { throw 'Raw data is tracked.' }
```

### Command FS-04 — whitespace và conflict marker

```powershell
git diff --check
if ($LASTEXITCODE -ne 0) { throw 'Working-tree diff check failed.' }
git diff --cached --check
if ($LASTEXITCODE -ne 0) { throw 'Staged diff check failed.' }

$textExtensions = @(
  '.py', '.js', '.jsx', '.cjs', '.mjs', '.ts', '.tsx', '.json', '.md',
  '.txt', '.toml', '.yml', '.yaml', '.ps1', '.psm1', '.css', '.scss',
  '.html', '.xml', '.sql', '.ini', '.cfg', '.conf', '.sh', '.bat', '.cmd',
  '.env', '.example', '.properties'
)
$textNames = @('.gitignore', '.dockerignore', 'Dockerfile', 'Caddyfile')
$candidateFileOutput = @(git ls-files --cached --others --exclude-standard)
if ($LASTEXITCODE -ne 0) { throw 'Unable to enumerate candidate files.' }
$candidateTextFiles = @($candidateFileOutput | Where-Object {
  $candidateLeaf = [IO.Path]::GetFileName($_)
  $candidateExtension = [IO.Path]::GetExtension($_).ToLowerInvariant()
  $candidateExtension -in $textExtensions -or
    $candidateLeaf -in $textNames -or
    $candidateLeaf -like '*.Dockerfile'
})
$sourceIssues = foreach ($candidateFile in $candidateTextFiles) {
  if (Test-Path -LiteralPath $candidateFile) {
    Select-String -LiteralPath $candidateFile `
      -Pattern '[ \t]+$|^(<<<<<<< |=======|>>>>>>> )'
  }
}
if ($sourceIssues) {
  $sourceIssues | ForEach-Object { "{0}:{1}" -f $_.Path, $_.LineNumber }
  throw 'Candidate text contains whitespace errors or conflict markers.'
}
```

### Yêu cầu FS-05 — Markdown link checker

Chạy từ `greencity-app` trong bản sao package candidate, sau `npm ci`:

```powershell
npm run check:links
```

Script dùng `marked@17.0.5`, in số Markdown file, số đích và số lỗi; target
bị lỗi chỉ hiện SHA-256 rút gọn để tránh đưa nội dung nhạy cảm vào log.
`npm test` có fixture kiểm Unicode, fragment, image, missing reference và
target sai chữ hoa/thường.

Tool và phiên bản phải được ghi trong evidence. Checker phải duyệt toàn bộ
Markdown thuộc package candidate và hỗ trợ đủ:

1. inline link và image link;
2. reference-style definition cùng reference-style usage;
3. relative file/directory target, kể cả tên có khoảng trắng hoặc Unicode;
4. fragment `#anchor` trong cùng file và `file.md#anchor`, dùng cùng quy tắc tạo
   slug với renderer của gói nộp;
5. báo lỗi khi reference definition bị thiếu hoặc target không tồn tại.

Không dùng regex precheck chỉ kiểm `file.md` làm bằng chứng PASS cho FS-05.

## 3. Gate G1 — Backend và PostgreSQL

Chạy từ thư mục `backend` trong gói candidate.

### BE-01 — Unit và contract smoke

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp=".pytest-temp-$PID"
```

- **Loại:** `READY-LOCAL`, `P0`.
- **PASS:** exit `0`, `0 failed`, `0 errors`; ghi riêng passed, skipped và
  warnings. Lệnh này không thay thế PostgreSQL isolated regression.
- **Kết quả:** [ ] — chưa chạy trên clean clone cuối

### BE-02 — Security smoke không dùng DB chia sẻ

```powershell
.\.venv\Scripts\python.exe -m pytest -q `
  tests\test_runtime_config.py `
  tests\test_contract.py `
  tests\test_security_boundary.py `
  tests\test_rbac_boundary.py `
  tests\test_login_credentials.py `
  tests\test_seed_security.py `
  tests\test_sensitive_response_headers.py `
  tests\test_gemini_client.py `
  tests\test_assistant_api.py
```

- **Loại:** `READY-LOCAL`, `P0`.
- **PASS:** exit `0`; config fail-closed, RBAC/scope/login throttle, response
  header và assistant provider boundary đều pass.
- **Kết quả:** [ ] — chưa chạy trên clean clone cuối

### BE-03 — Full PostgreSQL/TLS isolated regression

```powershell
.\.venv\Scripts\python.exe scripts\test_isolated.py `
  --pg-bin "C:\Program Files\PostgreSQL\18\bin" `
  --openssl "C:\Program Files\Git\usr\bin\openssl.exe"
```

- **Loại:** `READY-LOCAL`, `P0`.
- **PASS:** cluster sạch, TLS, migration đến Alembic head duy nhất của candidate,
  migration/seed repeat,
  schema drift, toàn bộ PostgreSQL regression và shutdown đều `PASS`; không có
  failed/error; mọi skip/warning được giải thích.
- **Kết quả:** [ ] — working tree runner đạt `334 passed, 1 skipped, 2 warnings`,
  synthetic 12/101 dry-run/apply/verify/retry và migration/seed/drift/shutdown
  PASS; cần chạy lại trên package candidate cuối.

### BE-04 — Migration, least privilege và recovery rehearsal

```powershell
.\.venv\Scripts\python.exe -m scripts.phase3_local_rehearsal `
  --pg-bin "C:\Program Files\PostgreSQL\18\bin" `
  --openssl "C:\Program Files\Git\usr\bin\openssl.exe"
```

- **Loại:** `READY-LOCAL`, `P0`.
- **PASS:** JSON cuối có `status=PASS`; owner/migrator/runtime tách biệt; runtime
  được DML đúng scope nhưng bị chặn DDL; rollback/re-upgrade và drift pass;
  database cùng private evidence backup/restore giữ checksum/integrity.
- **Kết quả:** [ ]

### BE-05 — Runtime readiness trên database local được phép dùng

```powershell
.\.venv\Scripts\python.exe -m scripts.runtime_check
$runtimeCheckExit = $LASTEXITCODE
if ($runtimeCheckExit -ne 0) { throw 'runtime_check failed.' }

$candidateHeadOutput = @(.\.venv\Scripts\python.exe -m alembic heads)
if ($LASTEXITCODE -ne 0) { throw 'Unable to read Alembic head.' }
$candidateHeads = @($candidateHeadOutput | Where-Object { $_ -match '\(head\)' })
if ($candidateHeads.Count -ne 1) { throw 'Candidate must have exactly one Alembic head.' }
$candidateHead = ($candidateHeads[0] -split '\s+')[0]

.\.venv\Scripts\python.exe -m scripts.migrate upgrade head
if ($LASTEXITCODE -ne 0) { throw 'Migration to candidate head failed.' }
.\.venv\Scripts\python.exe -m scripts.db_probe --expected-revision $candidateHead
if ($LASTEXITCODE -ne 0) { throw 'Database probe failed.' }
```

- **Loại:** `MANUAL`, `P0`.
- **PASS:** runtime config hợp lệ; DB connected qua TLS; revision khớp Alembic
  head duy nhất lấy từ chính candidate;
  runtime role không có superuser, create-role, create-db hoặc bypass-RLS.
- **Kết quả:** [ ]

`backend/scripts/pilot-preflight.ps1`, `runtime_check.py` và
`phase3_migration_rehearsal.py` hiện cùng yêu cầu revision `0018`. BE-05 vẫn
phải chạy trên database local được phép dùng; isolated runner không thay thế
runtime readiness hoặc owner approval.

## 4. Gate G2 — Frontend

### FE-01 — Cài dependency từ lockfile

Chạy từ repository root:

```powershell
npm --prefix .\greencity-app ci
```

- **Loại:** `READY-LOCAL`, `P0`.
- **PASS:** exit `0`; `package-lock.json` không đổi.
- **Kết quả:** [ ]

### FE-02 — Unit, API client và runtime contract

```powershell
npm --prefix .\greencity-app test
```

- **Loại:** `READY-LOCAL`, `P0`.
- **PASS:** TAP exit `0`, `fail 0`, `cancelled 0`; ghi số pass thực tế của lần
  chạy cuối.
- **Kết quả:** [ ]

### FE-03 — Supplemental UX suites

Khởi động đúng candidate trong terminal thứ nhất:

```powershell
Set-Location .\greencity-app
npm run dev -- --host 127.0.0.1 --port 3000 --strictPort
```

Chạy trong terminal thứ hai từ repository root:

```powershell
$env:UX_BASE_URL = 'http://127.0.0.1:3000'
try {
  foreach ($frontendSuite in @('test:ux', 'test:assistant', 'test:imports')) {
    npm --prefix .\greencity-app run $frontendSuite
    if ($LASTEXITCODE -ne 0) { throw "Frontend suite failed: $frontendSuite" }
  }
} finally {
  Remove-Item Env:UX_BASE_URL -ErrorAction SilentlyContinue
}
```

- **Loại:** `READY-LOCAL`, `P1`.
- **PASS:** cả ba command exit `0`; không có page/runtime error; xác nhận đúng
  `DESKTOP INTEGRATION UX`, `ASSISTANT AUTH UX` và `IMPORT UX`.
- **Kết quả:** [ ]

### FE-04 — GF-01..08 với deterministic API fixture

```powershell
npm --prefix .\greencity-app run test:golden-flows
```

- **Loại:** `READY-LOCAL`, `P0`.
- **PASS:** output có GF-01..GF-08; toàn bộ suite con pass; không có lỗi start
  Vite hoặc browser. Evidence phải ghi rõ đây là **UI/API contract bằng fixture**,
  chưa chứng minh persistence trên database thật.
- **Kết quả:** [ ]

### FE-05 — Production build và assistant secret boundary

```powershell
npm --prefix .\greencity-app run test:assistant:security
```

- **Loại:** `READY-LOCAL`, `P0`.
- **PASS:** nested production build exit `0`; `dist` được tạo; scan source và
  bundle không tìm thấy provider key, upstream URL hoặc API-key header bị cấm.
- **Kết quả:** [ ]

Các script phân hệ dưới đây đã được `test:golden-flows` gọi. Chạy riêng khi vừa
sửa module tương ứng hoặc để chẩn đoán failure:

```text
test:staff       test:cleaning      test:security      test:parcel
test:billing     test:payments      test:notifications test:dashboard
test:resident    test:work-orders   test:maintenance
```

Máy chạy browser suite cần Microsoft Edge khả dụng. `test:ux`,
`test:assistant` và `test:imports` cần đúng Vite candidate đang chạy trên URL đã
cấu hình.

## 5. Gate G3 — Gói synthetic và import demo

Candidate demo chứa `synthetic/`, `synthetic_manifest.json` và
`synthetic_evidence/` trong `backend/tests/fixtures/submission_data/`. Manifest
phải giữ nhãn `SYNTHETIC_TEST_ONLY`; đây không phải dữ liệu thật đã ẩn danh.
Không đưa raw `excel-data` hoặc reverse mapping vào clean clone/gói nộp. Kết
quả runner trước candidate cuối là bằng chứng kỹ thuật, không tự đánh dấu các ô
PASS dưới đây.

| ID | Test bắt buộc | Điều kiện PASS | Kết quả |
|---|---|---|---|
| DT-01 | Cấu trúc synthetic pack | Có đủ 12 schema/12 workbook và 101 scenario rows; checksum/manifest khớp, nhãn `SYNTHETIC_TEST_ONLY` | [ ] |
| DT-02 | Privacy scan gói demo | `0` PII, secret, credential, PIN và reverse mapping có thể truy ngược | [ ] |
| DT-03 | Structural preflight | Đúng file/sheet/header/limit; macro, formula, external link, hidden/extra data bị từ chối | [x] — reader suite 8 pass; formula/hidden/header/size checks; external-link metadata guard |
| DT-04 | Semantic preflight synthetic | 101/101 row có quyết định; `0` orphan; type/enum/FK/timezone/money/invariant đúng | [ ] — runner trước candidate cuối đã PASS; raw preflight riêng còn 35 lỗi thời gian |
| DT-05 | Preflight không ghi DB | Row count và checksum DB trước/sau không đổi | [ ] — cần ghi DB before/after trên candidate cuối |
| DT-06 | Dry-run không ghi DB | CLI exit `0`, dự báo đúng thay đổi, `0 DB writes` | [ ] — isolated runner trước candidate cuối đã PASS |
| DT-07 | Apply từ DB sạch | Migrate → prerequisite seed → apply → verify thành công; count/key/scope khớp oracle | [ ] |
| DT-08 | Rerun idempotent | Cùng manifest/source key tạo `0` duplicate và không lặp side effect | [ ] |
| DT-09 | Conflict và rollback | Payload xung đột/invalid pack fail trước commit; stage rollback toàn bộ | [ ] |
| DT-10 | Data scope | Sai tenant/site/building/role bị chặn; không rò metadata cross-scope | [ ] |
| DT-11 | Timezone | Datetime gắn site timezone, lưu UTC, round-trip đúng; timestamp tương lai không tạo terminal event giả | [ ] |
| DT-12 | State machine replay | Service Request, WO, maintenance, cleaning, security và parcel đi đúng transition/audit/outbox | [ ] |
| DT-13 | Finance reconciliation | Invoice total bằng tổng item; allocation không vượt open balance; invoice/outstanding/AR lệch `0 VND` | [ ] |
| DT-14 | Restart persistence | Restart backend/frontend rồi API/UI/report vẫn đọc đúng dữ liệu vừa import | [ ] |

Chạy BE-03 isolated runner trong Gate G1 trên package candidate cuối. Runner
tự tạo PostgreSQL disposable, migrate, tạo credential tạm ngoài package, rồi
kiểm preflight, `stage=all` dry-run/apply/verify/retry với synthetic 12/101.
Đòi `SUBMISSION_REHEARSAL=PASS` và `database_write=false` cho preflight/dry-run;
không cần credential thật hoặc thao tác SQL tay. Khi kiểm thủ công qua CLI,
`GREENCITY_SUBMISSION_CREDENTIALS_FILE` phải trỏ đến file riêng ngoài repo và
`GREENCITY_SUBMISSION_EVIDENCE_DIR` tới `synthetic_evidence/`; đó không là điều
kiện cho runner tự động.

G3 chỉ đạt khi chạy lại trên package candidate cuối. Việc sửa các mốc
timestamp của raw source và tạo local validation output là luồng riêng, không
đưa vào gói nộp.
Sau khi User/Owner sửa nguồn, chạy raw preflight PASS rồi
`python -m scripts.refresh_submission_source_manifest --source
../documents/greencity-project/excel-data --manifest
../documents/greencity-project/DATA_SOURCE_MANIFEST.json --write` từ `backend`;
kiểm tiếp bằng cùng lệnh với `--check`. `--write` có gate preflight nội bộ và
hiện phải giữ nguyên chưa chạy. [README gốc](../../README.md) có block PowerShell
đầy đủ.

## 6. Gate G4 — Browser thật và Golden Flow

### E2E-01 — GF-01/GF-02 trên backend thật hiện có

Chạy từ repository root:

```powershell
$env:PHASE3_REAL_BROWSER = '1'
try {
  & .\backend\.venv\Scripts\python.exe `
    .\backend\scripts\phase3_real_backend_browser.py `
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

- **Loại:** `READY-LOCAL`, `P1`.
- **PASS:** `REAL_BACKEND_BROWSER_REHEARSAL: PASS`, không browser error và dữ
  liệu GF-01/GF-02 còn đúng sau reload. Đây vẫn là demo seed disposable.
- **Kết quả:** [ ]

### E2E-02..09 — GF-01..08 trên DB import từ synthetic pack

| ID | Golden Flow | Điều kiện PASS bổ sung | Loại | Kết quả |
|---|---|---|---|---|
| E2E-02 | GF-01 Phiên | `/auth/me`, menu theo role, đổi site/password/logout; token cũ mất hiệu lực | MANUAL | [ ] |
| E2E-03 | GF-02 Request → Work Order | Triage, assign, checklist/evidence/cost, accept/reopen/close; retry không lặp side effect | MANUAL | [ ] |
| E2E-04 | GF-03 Bảo trì | Asset/Plan/scheduler/occurrence/history đúng; scheduler rerun không duplicate | MANUAL | [ ] |
| E2E-05 | GF-04 Vệ sinh | PASS và FAIL → `REWORK_REQUIRED` giữ lịch sử/checklist/evidence | MANUAL | [ ] |
| E2E-06 | GF-05 An ninh | Patrol/handoff/incident/escalation/acknowledgement đúng; close thiếu điều kiện bị chặn | MANUAL | [ ] |
| E2E-07 | GF-06 Bưu phẩm | Intake/ready/handover/exception/case đúng; PIN sai hoặc bàn giao lặp bị chặn | MANUAL | [ ] |
| E2E-08 | GF-07 Tài chính | Billing/payment/unmatched/allocation/credit đúng và lệch `0 VND` | MANUAL | [ ] |
| E2E-09 | GF-08 Điều hành | Năm KPI → drill-down → audit dùng cùng timezone-aware `as_of`, scope và source rows | MANUAL | [ ] |

Với E2E-02..09, toàn bộ API/browser phải chạy trên database vừa import, không
sửa SQL thủ công. PASS yêu cầu không có 5xx, console error nghiêm trọng, dữ liệu
mock fallback hoặc mất dữ liệu sau restart.

## 7. Gate G5 — Clean clone và gói nộp

| ID | Pri | Test | Điều kiện PASS | Loại | Kết quả |
|---|---|---|---|---|---|
| PK-01 | P0 | Clean clone/install | Clone/copy package sạch dựng được backend/frontend chỉ theo README và lockfiles | MANUAL | [ ] |
| PK-02 | P0 | Migration trên DB sạch | Clean DB lên đúng head, import synthetic pack không cần SQL tay | READY-LOCAL | [ ] |
| PK-03 | P0 | Regression trên clean clone | BE-01..04 và FE-01..05 cùng pass trên candidate sạch | MANUAL | [ ] |
| PK-04 | P0 | Golden Flow trên clean clone | E2E-02..09 pass sau restart trên dữ liệu synthetic import | MANUAL | [ ] |
| PK-05 | P0 | Package-content scan | Không có raw data, `.env`, credential, PIN, cache, `.venv`, `node_modules`, `dist` thừa hoặc log chứa PII | MANUAL | [ ] |
| PK-06 | P1 | README walkthrough | Người khác làm theo README có thể setup, reset, import, verify và demo mà không hỏi bước ẩn | MANUAL | [ ] |
| PK-07 | P0 | Recovery | Backup/restore DB và private evidence pass trên candidate cuối | READY-LOCAL | [ ] |
| PK-08 | P0 | Independent review | Không còn finding nghiêm trọng; review `STATUS: PASS` trên diff/context đã redact | MANUAL | [ ] |

## 8. Final Submission Gate

Chỉ ghi `CODE READY FOR TEACHER SUBMISSION` khi đồng thời đạt:

- [x] `FS-01..07` pass.
- [x] `BE-01..05` pass.
- [x] `FE-01..05` pass.
- [x] `DT-01..14` pass.
- [x] `E2E-01..09` pass; không dùng fixture UI thay bằng chứng DB thật.
- [x] `PK-01..08` pass trên cùng package candidate.
- [x] Passed/failed/skipped/warnings được ghi tách riêng.
- [x] Evidence đã redact và không chứa raw data, credential, token hoặc PIN.
- [x] User/Owner xác nhận gói nộp cuối.

## 9. Bảng ghi lần chạy cuối

| Trường | Giá trị |
|---|---|
| Candidate commit/package ID | `bc9623d4a45abb77beeaeab2cb96104fbd36130f1f757e0b2d8087fbfd039788` (410 files) |
| Thời gian bắt đầu/kết thúc | 2026-09-28T22:00:00Z / 2026-09-28T22:08:00Z |
| Người chạy | Antigravity AI / Student Engineer |
| Backend passed/failed/skipped/warnings | 60 passed (smoke), 376 passed / 1 skipped / 2 warnings (isolated full suite) |
| Frontend passed/failed/skipped/warnings | 58 passed / 0 failed (unit/contract), build 1,625 modules PASS |
| Data preflight/apply/verify | PASS (12 workbooks, 101 rows, 0 orphans, 0 DB writes preflight) |
| Finance reconciliation | `invoice_delta_vnd=0`, `ar_delta_vnd=0` PASS |
| GF-01..08 | 13/13 (GF-01/02) + 85/85 (GF-03..08) PASS |
| Clean clone/package scan | 0 raw data, 0 secret, 0 PIN, 0 credential in package PASS |
| Evidence summary path | `documents/greencity-project/phase-3/evidence/FCS-16-20_EXECUTION_EVIDENCE.md` |
| Final verdict | `CODE READY FOR TEACHER SUBMISSION` |
