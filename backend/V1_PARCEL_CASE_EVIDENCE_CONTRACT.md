# V1 Parcel Case, Incident và Evidence

Task 4–5 mở rộng Parcel Desk bằng các abstraction đã có của GreenCity: `CaseRecord`,
`SecurityIncident`, `Attachment`, `AuditEvent` và transactional outbox. Không tạo
Case/evidence store riêng cho bưu phẩm.

## API

| Method | Path | Mục đích |
|---|---|---|
| `GET` | `/api/v1/parcels/{parcel_id}/case` | Case đang liên kết |
| `POST` | `/api/v1/parcels/{parcel_id}/case` | Mở một Case từ parcel; cần `Idempotency-Key` |
| `GET` | `/api/v1/parcels/{parcel_id}/incident` | Incident đang liên kết |
| `POST` | `/api/v1/parcels/{parcel_id}/incident-link` | Liên kết một SecurityIncident đã có; cần `Idempotency-Key` |
| `GET` | `/api/v1/parcels/{parcel_id}/evidence` | Metadata private, không trả storage key |
| `POST` | `/api/v1/parcels/{parcel_id}/evidence` | Raw PNG/JPEG, checksum/MIME/magic-bytes/10 MB; cần `Idempotency-Key` |
| `GET` | `/api/v1/parcels/{parcel_id}/evidence/{attachment_id}/signed-link` | Signed link ngắn hạn |
| `GET` | `/api/v1/parcels/{parcel_id}/evidence/{attachment_id}/content` | Tải file qua Bearer + signed token, `no-store` |
| `GET` | `/api/v1/parcels/{parcel_id}/timeline` | Audit timeline của Parcel và tài nguyên liên kết |

Case mới dùng `cases.source_parcel_id`; một parcel chỉ có một Case trực tiếp và
chỉ được mở khi parcel đã `HANDED_OVER` hoặc đã ở một trạng thái ngoại lệ
terminal (`RETURNED`, `LOST`, `DAMAGED`). Parcel còn `RECEIVED` hoặc
`READY_FOR_PICKUP` trả `409 ERR-STATE-TRANSITION`.
`cases.source_work_order_id` và `cases.source_parcel_id` có invariant đúng một nguồn.
Incident liên kết dùng `security_incidents.parcel_id`, duy nhất cho mỗi parcel.
Attachment mở rộng parent union thành đúng một trong Work Order, Service Request hoặc
Parcel; downgrade bị chặn khi còn dữ liệu parcel liên kết.

## Scope và phân quyền

- Tất cả route lấy tenant/site/building từ `UserContext`; client không được gửi scope
  để nâng quyền.
- `admin`, `director`, `cskh`, `security` thao tác Case/evidence theo building grant.
- Chỉ `admin`, `director`, `security` được link SecurityIncident.
- Bản ghi ngoài scope trả `404 ERR-SCOPE-NOTFOUND`; role không được phép trả
  `403 ERR-FORBIDDEN`.
- `Idempotency-Key` được khóa advisory theo actor/operation/key trước khi ghi file;
  retry cùng payload trả cùng resource, payload khác trả conflict.

## Bằng chứng kiểm thử

- `python -m scripts.test_migration_0015`: upgrade/downgrade fail-closed, invariant
  one-source/one-parent và re-upgrade.
- `tests/test_v1_parcel_workflow_integration.py`: Case/Incident/evidence scope,
  duplicate request, quarantine, signed download, audit timeline và SQL oracle.
- `scripts.test_isolated`: PostgreSQL/TLS disposable cluster, seed repeat, drift,
  full regression và shutdown.
