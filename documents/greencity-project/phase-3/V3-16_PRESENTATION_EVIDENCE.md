# V3-16 — Evidence pack trình bày và recovery local

**Ngày kiểm tra:** 2026-09-26
**Checkout:** _pttkpm (working tree có thay đổi chưa commit)
**Phạm vi:** bằng chứng local cho V3-12..V3-16 theo [roadmap_v3.md](../roadmap_v3.md).

Rehearsal tiếp theo N1–N5 được ghi riêng tại
[N1-N5_EXECUTION_EVIDENCE.md](N1-N5_EXECUTION_EVIDENCE.md); không gộp real-browser
GF-01/GF-02 với các browser fixture GF-03..08.

Lượt thực hiện tiếp theo N6–N10, real-browser GF-03..08 và quyết định pilot được ghi tại
[N6-N10_EXECUTION_EVIDENCE.md](N6-N10_EXECUTION_EVIDENCE.md).

Evidence pack này xác nhận khả năng tái chạy trên máy local với dữ liệu giả và database dùng một lần. Nó không phải phê duyệt production, Go/No-Go, owner sign-off hoặc kết quả review độc lập.

## 1. Kết quả 5 task

| Task | Kết quả local | Bằng chứng |
|---|---|---|
| **V3-12 — Dọn legacy/dead code** | Đã loại prototype Media, Amenities, refund payout, StaffDashboard/mock-role và mobile shell khỏi active frontend path; fixtures chỉ còn trong test scope. Import/source scan active src không còn legacy prototype, fake metric, debug log hoặc TODO/FIXME; provider-key scan không có match. | Log local `frontend-source-scan.log`, `frontend-assistant-security.log` |
| **V3-13 — Golden Flow và contract** | GF-01..08 chạy pass bằng runner tổng hợp. Suite dùng API fixture deterministic cho UI/request contract; persistence, scope, audit, idempotency và state transition được kiểm tra trong isolated PostgreSQL. | Log local `frontend-golden-flows.log` |
| **V3-14 — Error/empty/loading/focus** | GF-01..08 pass các path mạng lỗi, 401/404/409/422, retry, empty state, aria-busy, error summary và focus/field linking đã giữ trong UI. | Log local `frontend-golden-flows.log`, `frontend-unit.log` |
| **V3-15 — Local demo kit** | README root là hướng dẫn chạy/reset/test; credential provision sinh 10 credential khác nhau ngoài repo, không in password; walkthrough GF-01..08 và giới hạn local đã ghi rõ. | [README.md](../../../README.md), [new_demo_credentials.ps1](../../../backend/scripts/new_demo_credentials.ps1), log local `credential-script-check.log` |
| **V3-16 — Regression/evidence/recovery** | Frontend unit, build, assistant security, browser Golden Flow, backend isolated regression, source scan và Phase 3 disposable rehearsal đều có output lưu dưới đây. | Bảng kết quả trong tài liệu này; log máy local ở `evidence/v3-16` |

## 2. Kết quả kiểm thử cuối

| Lớp | Lệnh | Kết quả |
|---|---|---|
| Frontend unit/contract | cd greencity-app; npm test | **55 passed, 0 failed** |
| Frontend production build | node ./node_modules/vite/bin/vite.js build --configLoader runner | **PASS**, 1,625 modules; main JS 490.14 kB |
| Assistant security | npm run test:assistant:security | **PASS**, quét 13 source và 9 bundle files |
| Browser GF-01..08 | npm run test:golden-flows | **PASS**: GF-01 40; GF-02 18 + 7; GF-03 7; GF-04 8 + 8; GF-05 7 + 7; GF-06 13; GF-07 10 + 14; GF-08 25 + 17 checks |
| Real-browser GF-03..08 với Docker/PostgreSQL thật | `real-browser-gf03.cjs` … `real-browser-gf08.cjs` | **PASS**: GF-03 10; GF-04 14; GF-05 17; GF-06 13; GF-07 15; GF-08 20; `errors=0`, `apiFailures=0` — [N6-N10_EXECUTION_EVIDENCE.md](N6-N10_EXECUTION_EVIDENCE.md) |
| Backend isolated PostgreSQL/TLS | cd backend; python scripts/test_isolated.py --pg-bin ... --openssl ... | **295 passed, 1 skipped, 2 warnings**; migration/seed-repeat/drift và shutdown pass |
| Phase 3 disposable rehearsal | cd backend; python -m scripts.phase3_local_rehearsal --pg-bin ... --openssl ... | **PASS**; role/migration/rollback/drift, DML/DDL boundary, dump/restore 61 bảng/2 dòng fixture, private evidence 2 object |
| Credential bootstrap | scripts/new_demo_credentials.ps1 -OutputPath <đường_dẫn_ngoài_repo> | **PASS**; 10 credential khác nhau, giá trị không in |
| Active source scan | rg trên greencity-app/src | **PASS**; không thấy prototype legacy/fake metric, debug/TODO hoặc provider key |
| Tracked-source secret scan | git grep trên backend app/scripts và greencity-app/src | **PASS**; không có provider-key/private-key pattern |

Output máy local nằm ở `evidence/v3-16` và không thuộc gói nộp vì có thể chứa đường dẫn người dùng. Lần chạy đầu của browser/backend được giữ lại trên máy để truy nguyên lỗi đã sửa: `frontend-golden-flows-attempt-1.log`, `backend-isolated-attempt-1.log`.

## 3. Checklist trình diễn và recovery

- [ ] Tạo backend/.env từ .env.example, điền DATABASE_URL/SECRET_KEY local; không commit .env.
- [ ] Chạy backend/scripts/new_demo_credentials.ps1 với output ở %LOCALAPPDATA%/GreenCity hoặc đường dẫn riêng ngoài checkout.
- [ ] Trên database disposable: migrate upgrade head, seed với DEMO_SEED_ENABLED=true và DEMO_SEED_CREDENTIALS_JSON; không sửa bảng thủ công.
- [ ] Khởi động backend 127.0.0.1:8000, frontend 127.0.0.1:3000, rồi mở walkthrough GF-01..08 theo README root.
- [ ] Chụp trạng thái và URL, không chụp password, token, signed link hoặc dữ liệu cá nhân thật.
- [ ] Khi cần làm lại demo, tạo database disposable mới, migrate upgrade head rồi seed lại bằng cùng file credential riêng. Một số downgrade có chủ đích từ chối dữ liệu hiện hữu.
- [ ] Chạy lại npm test, npm run test:golden-flows và scripts/test_isolated.py trước buổi trình bày nếu checkout hoặc môi trường thay đổi.

## 4. Screenshot đại diện

Ảnh do browser suite tạo trong `greencity-app/artifacts/` là output local đã
được Git ignore, nên không thuộc gói code nộp. Chạy lại browser suite tương
ứng để tạo ảnh. Các trạng thái UI đã quan sát dưới đây dùng fixture browser và
không phải bằng chứng persistence trực tiếp:

- GF-01: service list và forced password change.
- GF-02: resident portal.
- GF-04: cleaning worker submitted.
- GF-05: security worker completed.
- GF-06: parcel handover mobile.
- GF-07: payment Golden Flow.
- GF-08: director KPI dashboard.

## 5. Giới hạn và lỗi còn mở

1. N1–N5 đã chạy real-browser GF-01/GF-02; N8–N9 đã bổ sung GF-03..08 trên backend PostgreSQL thật trong Docker Compose. Browser evidence này vẫn là controlled local rehearsal, không phải formal Gate/pilot approval.
2. HTTPS, backup và restore mới được xác nhận trên local Caddy CA/dữ liệu disposable; deployment target vẫn cần CA, encryption, RPO/RTO, monitoring và quyền restore được owner duyệt.
3. Dependency warning target đã được xử lý bằng `httpx2` và Starlette 1.7.0;
   lượt full regression mới nhất vẫn ghi nhận **2 deprecation warnings** từ
   FastAPI/Starlette TestClient và anyio. Không gọi kết quả này là 0 warning.
4. Bằng chứng này là local verification cho đồ án. Chưa tuyên bố production readiness, formal Gate approval, deployment approval hoặc independent external review.
5. frontend-golden-flows-attempt-1.log và backend-isolated-attempt-1.log là lịch sử lỗi đã sửa trong lượt này; log cuối là các file không có hậu tố attempt-1.

**Trạng thái bàn giao:** V3-12..V3-16 đạt bằng chứng local theo acceptance criteria có thể kiểm tra lại; các giới hạn trên phải được giữ nguyên khi trình bày.
