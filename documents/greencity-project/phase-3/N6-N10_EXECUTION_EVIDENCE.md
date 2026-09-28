# N6–N10 — Evidence thực hiện 5 task tiếp theo

**Ngày kiểm tra:** 2026-09-26
**Checkout:** `_pttkpm` (working tree có thay đổi chưa commit)
**Phạm vi:** local verification trên dữ liệu giả, PostgreSQL disposable và frontend browser fixture.

Tài liệu này nối tiếp [N1-N5_EXECUTION_EVIDENCE.md](N1-N5_EXECUTION_EVIDENCE.md).
Nó không phải formal Gate approval, owner sign-off, pilot approval hoặc production
readiness.

## 1. Kết quả thực hiện

| Task | Kết quả | Bằng chứng và giới hạn |
|---|---|---|
| **N6 — Docker Compose bring-up (Task 1–2)** | **PASS local container** | Đã khôi phục Docker Desktop và tắt Model Runner/Inference. `docker compose build` đạt cho backend, migrate, role-setup, db và frontend; `docker compose up -d --wait` đạt. `db` và `backend` healthy; frontend/proxy đang chạy; role-setup và migrate thoát **0**. Migration đạt revision `0017` trong schema `greencity` với **60 bảng**; backend health trả `status=ok`, `database=connected`. HTTPS smoke và scheduled-backup worker chưa chạy trong task này. |
| **N7 — HTTPS và recovery (Task 3)** | **PASS local container** | HTTP health trả `308` sang HTTPS; HTTPS health trả `200` với HSTS, `nosniff`, `DENY`, Referrer-Policy và Permissions-Policy. Scheduled-backup chạy một chu kỳ với retention **7 ngày**, interval **60 giây**; dump **323,503 bytes** và private-evidence archive **253 bytes** có manifest/checksum. Dump khớp checksum manifest; restore database disposable khớp shape **60 bảng / 0 account**; archive marker khôi phục đúng checksum. Đây là Caddy local CA và dữ liệu giả, chưa phải production/pilot approval. |
| **N8 — real-browser GF-03..GF-05** | **PASS local backend thật** | Playwright qua HTTPS Compose và PostgreSQL thật đạt GF-03 **10**, GF-04 **14**, GF-05 **17** checks; mỗi flow có `errors=0`, `apiFailures=0`. Scripts và ảnh: [n8-real-browser](evidence/n8-real-browser/). Đây là evidence local controlled rehearsal, chưa phải formal Gate/pilot approval. |
| **N9 — real-browser GF-06..GF-08** | **PASS local backend thật** | Playwright qua HTTPS Compose và PostgreSQL thật đạt GF-06 **13**, GF-07 **15**, GF-08 **20** checks; mỗi flow có `errors=0`, `apiFailures=0`. GF-06 bao gồm PIN sai/version reconciliation, private evidence và mobile overflow; GF-07 bao gồm invoice/payment/unmatched/credit/resident billing; GF-08 bao gồm đủ 5 KPI, drill-down, audit và notification `as_of`. Scripts và ảnh: [n9-real-browser](evidence/n9-real-browser/). Đây là evidence local controlled rehearsal, chưa phải formal Gate/pilot approval. |
| **N10 — controlled-pilot readiness** | **NO-GO** | Đã hoàn thành baseline reconciliation, fake-data/internal-user UAT matrix, runbook/recovery evidence và pilot evidence pack ở [N10_CONTROLLED_PILOT_PACK.md](N10_CONTROLLED_PILOT_PACK.md). Quyết định vẫn **NO-GO** vì chưa có owner/PO sign-off, formal Gate C/D và deployment-target controls (CA, backup encryption/RPO/RTO, monitoring). |

## 2. Kết quả chạy lại trong lượt này

| Lớp | Lệnh | Kết quả |
|---|---|---|
| Docker config | `docker compose -f deploy/compose.yml config` | **PASS** |
| Docker Engine access | `docker version`; `docker info --format '{{.ServerVersion}}'` (elevated token) | **PASS**, Docker Desktop **4.55.0**, Engine **29.1.3**, Linux `amd64` |
| Docker Model Runner / Inference | Kiểm tra cấu hình sau khi sửa và khởi động lại Docker Desktop | **DISABLED**, engine khởi động ổn định |
| Local Compose secrets | `deploy/secrets/README.txt`; sáu file được tạo local và kiểm tra `.gitignore` | **PASS**, mỗi file một dòng; không ghi giá trị vào log/Git |
| Compose build | `docker compose -f deploy/compose.yml build --progress plain` | **PASS**, backend/migrate/role-setup/db/frontend image built |
| Compose up và service state | `docker compose -f deploy/compose.yml up -d --remove-orphans --wait --wait-timeout 180` | **PASS**, db/backend healthy; frontend/proxy running; role-setup/migrate exited `0` |
| Migration và backend health | `greencity.alembic_version`; `/api/v1/health` trong backend container | **PASS**, revision `0017`, **60 bảng**, `status=ok`, `database=connected` |
| HTTPS smoke và security headers | `curl http://localhost/api/v1/health`; `curl -k https://localhost/api/v1/health` | **PASS**, HTTP `308`, HTTPS `200`, health database connected; headers đạt — log local `https-recovery.result` |
| Scheduled backup và restore | Compose profile `scheduled-backup`; manifest; restore disposable DB/private-evidence archive | **PASS local container**, dump **323,503 bytes**, archive **253 bytes**, restore shape **60 bảng / 0 account**, artifact/marker checksum khớp — log local `https-recovery.result` |
| Frontend unit | `cd greencity-app; npm test` | **55 passed, 0 failed** |
| Frontend build | `npm run build -- --configLoader runner` | **PASS**, 1.625 modules |
| Browser fixture Golden Flow | `npm run test:golden-flows` | **PASS**, GF-01..GF-08; không có suite thất bại |
| Real-browser GF-03..GF-05 | `real-browser-gf03.cjs` … `real-browser-gf05.cjs` | **PASS**, 10 + 14 + 17 checks, backend Compose/PostgreSQL thật — [n8-real-browser](evidence/n8-real-browser/) |
| Real-browser GF-06..GF-08 | `real-browser-gf06.cjs` … `real-browser-gf08.cjs` | **PASS**, 13 + 15 + 20 checks, backend Compose/PostgreSQL thật — [n9-real-browser](evidence/n9-real-browser/) |
| Backend isolated PostgreSQL/TLS | `cd backend; .venv\Scripts\python.exe scripts\test_isolated.py ...` | **295 passed, 1 skipped, 2 known deprecation warnings** |
| Disposable Phase 3 recovery | `python -m scripts.phase3_local_rehearsal ...` | **PASS**, 61 bảng/2 dòng, 2 private objects |

> Hai warning còn lại đến từ `fastapi.testclient`/Starlette dùng API `httpx` và
> `anyio` đã deprecated. Chúng không làm test fail; không được ghi là “0 warning”
> cho full regression nếu chưa thay đổi harness phụ thuộc.

## 3. Checklist controlled pilot

| Điều kiện | Trạng thái | Evidence/owner cần bổ sung |
|---|---:|---|
| Roadmap v2 tiếp tục là capability source of truth; v3 là implementation supplement | **PASS** | `roadmap_v2.md`, `roadmap_v3.md` |
| DB trống → migrate → seed lặp lại, không sửa bảng thủ công | **PASS local** | isolated runner và Phase 3 rehearsal |
| GF-01/GF-02 trên browser với backend/PostgreSQL thật | **PASS** | `N1-N5_EXECUTION_EVIDENCE.md` |
| GF-03..GF-08 trên browser với backend/PostgreSQL thật | **PASS local rehearsal** | GF-03..05: 10/14/17; GF-06..08: 13/15/20; chưa thay thế formal Gate |
| Container image build/start, migration và health checks | **PASS local container** | Compose build/up đạt; migration revision `0017`, db/backend healthy; chưa phải formal deployment gate |
| Caddy HTTPS smoke, headers và scheduled backup worker | **PASS local container** | HTTP→HTTPS, headers và một chu kỳ scheduled backup đạt; local Caddy CA |
| Backup/restore biên bản đo được | **PASS local container** | manifest/checksum, database restore và private-evidence restore đạt; chưa là production RPO/RTO |
| `AC-38..45`, `INV-01..02`, cùng `as_of` và audit correlation | **PASS API/local / OPEN real-browser** | isolated integration đã chạy; cần browser evidence |
| Baseline reconciliation và dữ liệu demo được owner duyệt | **EVIDENCE READY / SIGN-OFF OPEN** | Ma trận đối chiếu trong [N10_CONTROLLED_PILOT_PACK.md](N10_CONTROLLED_PILOT_PACK.md); owner/PO chưa ký |
| UAT nội bộ bằng fake data và runbook recovery | **EVIDENCE READY / SIGN-OFF OPEN** | UAT matrix, runbook và recovery artifacts đã lập; cần người sở hữu xác nhận |
| Formal Gate C/D, owner sign-off và quyết định pilot | **OPEN** | không tự suy ra từ local test |

## 4. Quyết định bàn giao

- **GO có điều kiện:** trình diễn local disposable, với dữ liệu giả và PostgreSQL
  dùng một lần.
- **NO-GO:** controlled pilot và production readiness cho đến khi các mục
  `OPEN` ở trên có evidence và owner sign-off; local HTTPS/recovery chưa phải
  bằng chứng production.
- Không đưa credential, token, DSN hoặc signed link vào evidence/log.

## 5. Final Roadmap Checklist verification (2026-09-26)

Sau khi đọc phần bổ sung mục 11–20 của `roadmap_v3.md`, đã tạo
[FINAL_ROADMAP_AUDIT.md](FINAL_ROADMAP_AUDIT.md) với bảng trạng thái 17 task,
missing/remove tasks, dependency order, checkpoints và Final Submission Gate.

Lượt xác nhận lại sau audit:

| Lớp | Kết quả |
|---|---|
| Frontend unit | **55 passed, 0 failed** |
| Frontend build | **PASS**, 1,625 modules |
| Browser Golden Flow | **PASS**, GF-01..GF-08; `errors=0` theo từng suite |
| Backend isolated PostgreSQL/TLS | **295 passed, 1 skipped, 3 warnings**; 2 warning tương thích FastAPI/Starlette/AnyIO và 1 warning Pydantic field metadata; regression exit `0` |
| Final status | **CODE READY FOR TEACHER SUBMISSION** trong phạm vi local teacher submission |

Controlled pilot vẫn **NO-GO** vì owner/PO sign-off, formal Gate C/D và
deployment-target controls vẫn mở. Các mục này không được coi là blocker của
code nộp cho giáo viên.
