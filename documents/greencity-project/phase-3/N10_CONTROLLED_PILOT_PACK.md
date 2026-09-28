# N10 — Controlled Pilot Evidence Pack

**Ngày lập:** 2026-09-26
**Phạm vi:** GreenCity local controlled rehearsal trên dữ liệu giả, tài khoản nội bộ và
PostgreSQL trong Docker Compose.  `roadmap_v2.md` vẫn là baseline nghiệp vụ; `roadmap_v3.md`
chỉ là supplement triển khai local.

Tài liệu này gom evidence để một owner/PO có thể review và ký. Nó không tự tạo
formal Gate C/D, không thay thế deployment target, và không tuyên bố production
readiness.

## 1. Baseline reconciliation

| Baseline `roadmap_v2.md` | Bằng chứng local đã đối chiếu | Trạng thái review |
|---|---|---|
| Quyền và phạm vi tenant/site/building (`OUT-04`, `PRM-*`) | `/auth/me`, role-scoped menu, backend scope checks; GF-01..08 request shape không nhận tenant/site/role từ frontend | **EVIDENCE READY** |
| CSKH → Work Order và SLA (`OUT-02`) | GF-02 real-browser; backend isolated regression | **EVIDENCE READY** |
| Kỹ thuật, vệ sinh, an ninh (`OUT-08..10`) | GF-03/GF-04/GF-05 real-browser với persistence, checklist, evidence, transition và audit | **EVIDENCE READY** |
| Bưu phẩm/cổng cư dân (`CAP` parcel/resident) | GF-06 và GF-07 resident billing; PIN hash, private evidence, invoice snapshot | **EVIDENCE READY** |
| Công nợ và thanh toán (`OUT-03`, `INV-01..02`) | GF-07 Fee Policy → Period → Billing Run → Invoice → Payment → unmatched/match → credit | **EVIDENCE READY** |
| Dashboard và kiểm toán (`OUT-05`, `AC-25`) | GF-08 đủ 5 KPI, 5 drill-down, audit timeline, notification/outbox dùng chung `as_of` | **EVIDENCE READY** |
| Hạ tầng local và recovery | N6/N7: Compose health, HTTPS headers, backup manifest/checksum, disposable restore | **LOCAL ONLY** |
| Hạng mục `SPEC-ONLY`/ngoài scope | Không đưa SSO, ERP, IoT, FaceID/ANPR, refund/chargeback, AI tự trị vào claim | **EVIDENCE READY** |

**Kết luận reconciliation:** implementation local hiện khớp lát cắt capability đã
chọn trong baseline. Owner/PO vẫn phải xác nhận mã AC/Gate và dữ liệu demo trước khi
cho phép pilot; trạng thái ký là **OPEN**.

## 2. Fake-data / internal-user UAT matrix

Các tài khoản dùng trong rehearsal là role nội bộ được seed trong local Compose;
không phải người dùng thật. Mỗi flow đi qua HTTPS proxy, API backend và PostgreSQL
đang chạy, không dùng API fixture.

| UAT | Người thực hiện | Luồng và tiêu chí chấp nhận | Evidence | Kết quả |
|---|---|---|---|---|
| UAT-GF03 | `techlead_west`, `technician_west` | Asset → plan → occurrence/WO → assign → checklist → evidence → nghiệm thu → reload | [n8-real-browser](evidence/n8-real-browser/), `gf03-real-browser.json` | **PASS 10 checks** |
| UAT-GF04 | `cleaning_west` + manager | Ca vệ sinh đạt; checklist fail sinh rework; manager accept | [n8-real-browser](evidence/n8-real-browser/), `gf04-real-browser.json` | **PASS 14 checks** |
| UAT-GF05 | `security_west`, `director_west` | Handoff → visitor/patrol → HIGH incident → ack/evidence → guard close | [n8-real-browser](evidence/n8-real-browser/), `gf05-real-browser.json` | **PASS 17 checks** |
| UAT-GF06 | `cskh_west` | Intake → ready → correct/wrong PIN → exception LOST → Case → private evidence → mobile | [n9-real-browser](evidence/n9-real-browser/), `gf06-real-browser.json` | **PASS 13 checks** |
| UAT-GF07 | `accountant_west`, `resident_west` | Policy → period → run/invoice → payment/allocation → unmatched/match → credit → resident view | [n9-real-browser](evidence/n9-real-browser/), `gf07-real-browser.json` | **PASS 15 checks** |
| UAT-GF08 | `director_west` | 5 KPI → 5 drill-down → audit resource/global → notifications/outbox, one `as_of` | [n9-real-browser](evidence/n9-real-browser/), `gf08-real-browser.json` | **PASS 20 checks** |

GF-01/GF-02 đã có evidence real-browser trước N6–N10 tại
[N1-N5_EXECUTION_EVIDENCE.md](N1-N5_EXECUTION_EVIDENCE.md). UAT sign-off, defect
waiver và dữ liệu baseline owner là các mục **OPEN**.

## 3. Runbook và recovery evidence

| Runbook | Thao tác kiểm soát | Evidence hiện có | Trạng thái |
|---|---|---|---|
| RB-01 — Start/health | `docker compose ... up -d --wait`; kiểm tra `db`, `backend`, `frontend`, `proxy`, Alembic head và `/health` | Log máy local `docker-bringup.result`; tóm tắt trong [N6-N10_EXECUTION_EVIDENCE.md](N6-N10_EXECUTION_EVIDENCE.md) | **PASS local** |
| RB-02 — HTTPS smoke | HTTP phải redirect 308; HTTPS health 200; kiểm tra HSTS và security headers | Log máy local `https-recovery.result`; tóm tắt trong [N6-N10_EXECUTION_EVIDENCE.md](N6-N10_EXECUTION_EVIDENCE.md) | **PASS local CA** |
| RB-03 — Backup/restore | Scheduled-backup tạo dump + private archive + manifest/checksum; restore vào DB disposable; xác nhận shape/marker | Log máy local `https-recovery.result`, `phase3-rehearsal.result`; tóm tắt trong [N6-N10_EXECUTION_EVIDENCE.md](N6-N10_EXECUTION_EVIDENCE.md) | **PASS local disposable** |
| RB-04 — Session/credential | Dùng credential file tạm của rehearsal; không in password/token/DSN; xóa file sau phiên | browser scripts và local credential policy | **PASS rehearsal / owner review OPEN** |
| RB-05 — Private evidence | Upload PNG hợp lệ; signed-link preview; kiểm tra PIN/private storage không lộ UI hoặc request shape | GF-06 evidence | **PASS local** |
| RB-06 — Billing recovery | Idempotency key giữ nguyên khi retry; không tạo duplicate payment/invoice; unmatched phải match trước allocation | GF-07 evidence, backend billing tests | **PASS local** |
| RB-07 — Pilot stop/rollback | Khi health, backup checksum, scope hoặc UAT gate fail: dừng pilot, giữ evidence, khôi phục snapshot đã duyệt và mở incident | Quy trình cần owner phê duyệt trên deployment target | **OPEN** |

Local recovery chỉ chứng minh quy trình kỹ thuật trên dữ liệu giả. Còn thiếu CA,
secret storage, encrypted backup, RPO/RTO, alerting và quyền restore của deployment
target.

## 4. Pilot entry gate và quyết định

| Gate | Điều kiện | Kết quả |
|---|---|---|
| E1 | GF-01..08 real-browser qua backend/PostgreSQL thật | **PASS local rehearsal** |
| E2 | Baseline reconciliation và demo data được owner/PO ký | **OPEN** |
| E3 | UAT internal users có biên bản, defect disposition và người duyệt | **OPEN** |
| E4 | Runbook RB-01..07 được owner vận hành thử trên deployment target | **OPEN** |
| E5 | Formal Gate C/D, deployment-target TLS/backup/monitoring/restore controls | **OPEN** |

### Quyết định hiện tại

```text
LOCAL DISPOSABLE DEMO: GO có điều kiện
CONTROLLED PILOT: NO-GO
PRODUCTION READINESS: NO-GO
```

Để chuyển sang **GO**, owner/PO phải ký E2–E5, ghi rõ target, người chịu trách
nhiệm, thời điểm hết hạn của evidence và kế hoạch rollback. Không suy ra quyết định
đó chỉ từ số lượng test PASS.

