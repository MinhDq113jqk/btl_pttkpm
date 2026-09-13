# R1 Unit CSV ImportRun — AC-02 / AC-24

## Trạng thái và ranh giới

Đây là contract thực thi hiện tại cho import Unit CSV bền vững: upload →
preview → apply. Bằng chứng PostgreSQL local ngày 13/09/2026: migration
`0005 -> 0006 -> 0005`, DB trống/seed lặp, `alembic check` và toàn suite
**184 passed, 2 warning deprecation**.

Antigravity Review #1 và Verification #2 của lát AC-02/24 đều trả
`STATUS: NEEDS_REVISION`. Các sửa sau Verification #2 đã được test lại, nhưng
quy trình chỉ cho phép hai lượt nên không có `PASS` cuối. Vì vậy AC-02/AC-24
vẫn là `[-]`: đã kiểm chứng local, không phải Gate B/C, release hay production
readiness.

`POST /api/v1/units/import` JSON cũ là compatibility slice lịch sử, không phải
contract dùng để đóng AC-02.

## Phạm vi và quyền

- Session Bearer hợp lệ phải có `purpose=session`; `tenant_id`, role, site và
  building được đọc lại từ database. Client không được truyền/chọn các scope đó.
- Chỉ `admin` hoặc `cskh` có active site và building grant hợp lệ được import.
  `building_code` là khóa nghiệp vụ được resolve bên trong scope server.
- Missing/out-of-scope trả `404 ERR-SCOPE-NOTFOUND`; thiếu role trả 403.
- `Idempotency-Key` là bắt buộc cho mọi command, dài 8--128 ký tự an toàn.

## API

| Route | Mục đích |
|---|---|
| `GET /api/v1/import-runs/template` | Tải mẫu CSV Unit; cần session trong active site. |
| `POST /api/v1/import-runs?building_code=&mode=PARTIAL|ALL_OR_NOTHING` | Upload CSV với `Content-Type` allowlist, `X-File-Name`, `Idempotency-Key`. |
| `POST /api/v1/import-runs/{run_id}/preview` | Nhận `{expected_version, mapping}`; mapping chỉ map bốn trường Unit vào header CSV khác nhau. |
| `POST /api/v1/import-runs/{run_id}/apply` | Nhận `{expected_version}`; ghi Unit sau preview hợp lệ. |
| `GET /api/v1/import-runs/{run_id}` | Xem trạng thái/count/version của run trong scope. |
| `GET /api/v1/import-runs/{run_id}/rows?page=&page_size=` | Xem row result có phân trang. |
| `GET /api/v1/import-runs/{run_id}/error-file/signed-link` | Phát URL tạm thời cho error CSV private. |
| `GET /api/v1/import-runs/{run_id}/error-file?signed_token=` | Tải error CSV sau khi kiểm session, scope, token và checksum. |

`ImportRunView` chứa `id`, mode/status, metadata source an toàn, checksum,
count theo row, `error_file_available`, failure code/timestamps và `version`.
`rows` trả `items`, `page`, `page_size`, `total`; một item có row number, status
và danh sách issue mã/cột/message.

## Toàn vẹn, file và đồng thời

- CSV tối đa 10 MiB, 10.000 dòng, 32 cột; tên file, MIME và cấu trúc được kiểm
  trước khi run được đưa vào trạng thái có thể preview. Tệp không hợp lệ được
  ghi private vào quarantine và trả `ERR-FILE-QUARANTINED`.
- Source/error file được checksum. Source/error đã mất hoặc sai checksum trả
  `ERR-FILE-INTEGRITY`; error download dùng `Cache-Control: private, no-store`.
- Error-file signed token ràng `sub`, tenant, active site, building và run, có
  `purpose=import-error-download`/expiry. Token này không xác thực `/auth/me`
  hay bất kỳ API Bearer nào khác.
- Receipt idempotency được atomically claim bằng PostgreSQL. Preview/apply dùng
  optimistic `expected_version`, row lock và building lock; cùng key/payload trả
  response đã lưu, key cùng scope nhưng payload khác trả conflict.
- `PARTIAL` ghi candidate hợp lệ; `ALL_OR_NOTHING` không ghi Unit nếu có row
  ERROR/SKIPPED. Audit và DomainEvent được ghi cùng transaction nghiệp vụ.

## Điều không được suy diễn

Contract này chỉ import bốn trường Unit: `unit_number`, `floor`, `area_m2`,
`status`. Nó không import Person hoặc Unit--Person relationship; AC-03 có
migration/contract và evidence độc lập. Không khẳng định Aiven/production,
worker publish outbox, R3--R5 hay toàn bộ R1 đã hoàn tất.
