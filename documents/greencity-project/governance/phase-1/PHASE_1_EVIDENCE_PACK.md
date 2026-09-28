# Phase 1 Evidence Pack

## Snapshot

| Trường | Giá trị |
| --- | --- |
| Ngày kiểm tra local | 2026-09-22 |
| Checkout | `main` tại `de67c48` trước khi thêm governance artefact |
| Kế hoạch nguồn | `5phase.md`, SHA-256 `38C784A2AE86DA90FC5E4B9E1B517F12E761DD9E775D670BB5FA01909F326CE7` |
| Trạng thái exit | `NOT PASS` — còn approval và remote CI evidence |

## Kết quả đã chạy cục bộ

| Gate | Lệnh | Kết quả |
| --- | --- | --- |
| Backend collect | `backend\\.venv\\Scripts\\python.exe -m pytest --collect-only -q` | `262 tests collected` |
| Backend isolated regression | `backend\\.venv\\Scripts\\python.exe scripts\\test_isolated.py --pg-bin "C:\\Program Files\\PostgreSQL\\18\\bin" --openssl "C:\\Program Files\\Git\\usr\\bin\\openssl.exe"` | `262 passed, 2 warnings`; migration path `0005..0015`, DB trống, seed lặp, drift và shutdown đều PASS |
| Frontend tests | `npm.cmd test` từ `greencity-app` | `67 pass, 0 fail` |
| Frontend production build | `npm.cmd run build` từ `greencity-app` | PASS; Vite build hoàn tất |
| Assistant bundle boundary | `npm.cmd run test:assistant:security` | PASS; quét 12 source files và 3 bundle files |
| Frontend dependency audit | `npm.cmd audit --audit-level=high` | `found 0 vulnerabilities` |
| Backend dependency audit | `python -m pip_audit --no-deps --requirement requirements.lock.txt` | `No known vulnerabilities found`; tool cảnh báo lockfile chưa có hash |

Warnings backend là deprecation từ FastAPI/Starlette TestClient; không bị ghi
nhận là skip hoặc pass của security gate.

## Kết quả CI GitHub

| Trường | Kết quả xác minh |
| --- | --- |
| Commit có Phase 1 | `b1e79f583f4ee64649d521612338d3cd3386409c`; latest `main` kiểm tra lại tại `02463704b3d068defa8702c3361919e00f6b3fb6` |
| Workflow | [run 35731246282](https://github.com/MinhDq113jqk/btl_pttkpm/actions/runs/35731246282) và [run 35732574279](https://github.com/MinhDq113jqk/btl_pttkpm/actions/runs/35732574279) |
| Trạng thái | Cả hai run đều `failure`; đây chưa phải bằng chứng CI green cần cho Exit Phase 1 |
| Job PASS | Secret scan, Dependency audit, Frontend tests and build trong cả hai run |
| Job FAIL | Backend migration and regression; bước `Run migration and isolated regression` fail trong cả hai run; run đầu kết thúc lỗi sau khoảng 32 giây |

Regression cô lập cùng checkout chạy local đã PASS `262 passed, 2 warnings`.
Log step chi tiết trên GitHub yêu cầu quyền repository admin; vì vậy nguyên nhân
Linux cụ thể chưa được khẳng định và không được suy diễn từ kết quả Windows.

## Evidence được tạo trong repository

| OR | Evidence |
| --- | --- |
| OR-01 | `BASELINE_RECONCILIATION.md` với bốn decision chưa ký |
| OR-02 | `SYSTEM_AND_DATA_INVENTORY.md` gồm data flow, register và RACI |
| OR-03 | `THREAT_MODEL_AND_RISK_REGISTER.md` gồm năm finding; `SECURITY_POLICY_DRAFT.md` chờ phê duyệt |
| OR-04 | `.github/workflows/quality-security.yml` chạy test/build/secret/dependency scan từ clean clone |
| OR-05 | `RELEASE_CHANGE_CONTROL.md` và `.github/workflows/release-evidence.yml` tạo source digest/SBOM/evidence artifact sau dispatch thủ công trong environment `release-candidate` với annotated candidate tag và change record HTTPS đã tồn tại |

## Điều kiện còn thiếu trước Exit Phase 1

1. PO + Tech Lead ký DEC-P1-01..04.
2. PO + Security phê duyệt policy draft để công bố root `SECURITY.md`.
3. Sửa lỗi backend regression của run GitHub hiện tại, rồi có một run GitHub
   green từ clean clone gồm secret scan và dependency audit.
4. Release Owner dispatch thủ công workflow trong `release-candidate` đã được
   bảo vệ, dùng annotated candidate tag `vX.Y.Z` và link change record HTTPS;
   workflow phải tạo evidence artifact có digest/SBOM. Việc này không đồng nghĩa
   deployment hay production approval.
