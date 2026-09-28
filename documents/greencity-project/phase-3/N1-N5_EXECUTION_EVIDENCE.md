# N1–N5 — Evidence thực hiện các công việc tiếp theo

**Ngày kiểm tra:** 2026-09-25
**Checkout:** `_pttkpm` (working tree có thay đổi chưa commit)
**Phạm vi:** rehearsal local trên dữ liệu giả, database PostgreSQL dùng một lần và loopback Windows.

Tài liệu này bổ sung cho [V3-16_PRESENTATION_EVIDENCE.md](V3-16_PRESENTATION_EVIDENCE.md). Nó không phải formal Gate approval, production approval, owner sign-off hoặc pilot approval.

## 1. Kết quả N1–N5

| Task | Kết quả | Evidence |
|---|---|---|
| **N1 — Clone sạch và reproducibility** | **PASS**. Bản sao working tree được tạo ngoài checkout, loại `.git`, dependency/cache và `.env`; `npm ci` hoàn tất; venv mới cài toàn bộ `requirements.lock.txt`; frontend **55 passed** và build **1.625 modules**. Lượt kiểm tra mục tiêu trước đó không có warning; full regression chạy lại ở N6–N10 đạt **295 passed, 1 skipped, 2 known deprecation warnings**. Lần chạy sandbox đầu bị `pg_ctl` Windows restricted-token nên được chạy lại trên loopback ngoài sandbox; cluster đã shutdown và dọn. | Log `evidence/n1-clean-clone` chỉ giữ local; [N6-N10_EXECUTION_EVIDENCE.md](N6-N10_EXECUTION_EVIDENCE.md) |
| **N2 — Browser Golden Flow với backend thật** | **PASS cho GF-01/GF-02 slice**. Uvicorn, Vite và PostgreSQL/TLS disposable chạy thật; Playwright đạt **13 checks**: login, first-login password change, `/auth/me`, resident scope, tạo request, double-submit/idempotency, reload/re-auth persistence, timeline/audit và browser error check. GF-03..08 vẫn có evidence fixture/integration riêng, chưa được tuyên bố là real-browser pass. | [n2-real-backend](evidence/n2-real-backend/), [phase3_real_backend_browser.py](../../../backend/scripts/phase3_real_backend_browser.py), [real-backend-golden-flow.cjs](../../../greencity-app/tests/real-backend-golden-flow.cjs) |
| **N3 — Warning dependency** | **PASS cho dependency health**. Thêm `httpx2==2.13.1`, `httpcore2==2.13.1`, `truststore==0.10.4`, nâng `starlette` lock lên `1.7.0`, vẫn giữ `httpx==0.28.1` cho Gemini. `pip check` không có dependency lỗi; 48 test mục tiêu không warning. Full regression ở N6–N10 vẫn ghi nhận 2 deprecation warnings từ FastAPI/Starlette TestClient và anyio, không phải lỗi dependency. | Log `evidence/n3-dependency` chỉ giữ local; [requirements.txt](../../../backend/requirements.txt), [requirements.lock.txt](../../../backend/requirements.lock.txt), [N6-N10_EXECUTION_EVIDENCE.md](N6-N10_EXECUTION_EVIDENCE.md) |
| **N4 — Docker, HTTPS, backup/restore** | **PARTIAL**. `docker compose config` và scheduled-backup profile config **PASS**; local disposable Phase 3 rehearsal **PASS** với migration/role boundary, **61 tables / 2 rows** database dump-restore và **2 private evidence objects** checksum/path isolation. Docker daemon không khởi động được trên Windows host; compose image build và container HTTPS smoke vì vậy **chưa xác nhận**. | Log `evidence/n4-docker-recovery` chỉ giữ local; [PHASE_3_IMPLEMENTATION.md](PHASE_3_IMPLEMENTATION.md), [compose.yml](../../../deploy/compose.yml) |
| **N5 — Demo gate và bàn giao** | **GO có điều kiện cho demo local disposable**; **NO-GO cho containerized HTTPS/pilot/production** cho đến khi Docker daemon chạy và real-browser coverage mở rộng GF-03..08. Checklist bên dưới ghi rõ phạm vi và lỗ hổng còn mở. | Phần 2–4 của tài liệu này |

## 2. Checklist demo local đã chốt

- [x] Bản sao sạch cài dependency từ lock và chạy regression.
- [x] GF-01/GF-02 browser chạy với backend/PostgreSQL thật, không mock API.
- [x] Credential demo được sinh ngẫu nhiên trong workspace tạm; không in hoặc ghi vào Git.
- [x] Request resident tồn tại sau reload và re-auth; replay cùng Idempotency-Key không tạo bản ghi thứ hai.
- [x] Timeline/audit và server-owned site/unit scope được kiểm tra từ API thật.
- [x] Migration, role DML/DDL boundary, dump/restore và private-evidence checksum/path isolation đã rehearsal.
- [ ] Container build/start, Caddy HTTPS browser smoke và scheduled backup worker: chờ Docker daemon.
- [ ] Real-browser GF-03..08 trên backend thật: cần lượt chạy riêng sau khi chốt dữ liệu reset và thời gian rehearsal.

## 3. Lệnh tái chạy

Từ checkout `_pttkpm`:

```powershell
# Frontend clean install / regression
cd greencity-app
npm ci
npm test
npm run build -- --configLoader runner

# Backend isolated regression
cd ..\backend
.\.venv\Scripts\python.exe scripts\test_isolated.py `
  --pg-bin "C:\Program Files\PostgreSQL\18\bin" `
  --openssl "C:\Program Files\Git\usr\bin\openssl.exe"

# Real-browser GF-01/GF-02 (requires disposable loopback and opt-in)
cd ..
$env:PHASE3_REAL_BROWSER = '1'
& backend\.venv\Scripts\python.exe backend\scripts\phase3_real_backend_browser.py `
  --pg-bin "C:\Program Files\PostgreSQL\18\bin" `
  --openssl "C:\Program Files\Git\usr\bin\openssl.exe" `
  --python "C:\path\to\rehearsal\.venv\Scripts\python.exe" `
  --node "C:\Program Files\nodejs\node.exe" `
  --evidence-dir documents\greencity-project\phase-3\evidence\n2-real-backend
Remove-Item Env:PHASE3_REAL_BROWSER -ErrorAction SilentlyContinue

# Phase 3 migration/role/backup/recovery rehearsal
cd backend
.\.venv\Scripts\python.exe -m scripts.phase3_local_rehearsal `
  --pg-bin "C:\Program Files\PostgreSQL\18\bin" `
  --openssl "C:\Program Files\Git\usr\bin\openssl.exe"
```

Các lệnh trên phải dùng database dùng một lần. Không đưa `.env`, DSN hoặc credential vào evidence/log.

## 4. Known limitations và điều kiện mở lại gate

1. Docker Desktop CLI có nhưng server pipe `dockerDesktopLinuxEngine` không sẵn sàng; cần khởi động Docker Desktop thành công rồi chạy `docker compose build`, `up`, Caddy HTTPS smoke và backup profile.
2. Real-browser evidence mới bao phủ GF-01/GF-02; GF-03..08 hiện dựa trên fixture browser + PostgreSQL integration, nên không được trình bày như một browser run với backend thật.
3. Self-signed TLS trong rehearsal chỉ kiểm tra đường kết nối local; production/pilot vẫn cần CA được phê duyệt, `sslmode=verify-full`, image digest và encrypted volume.
4. GO ở đây chỉ là quyết định demo local disposable có điều kiện. Formal Gate, pilot Go/No-Go và production readiness cần owner sign-off, baseline reconciliation, runbook/recovery evidence và review độc lập.
