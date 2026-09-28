# Evidence FCS-13 đến FCS-15 — operational replay và billing reconciliation

- **Ngày kiểm tra:** 2026-09-27; **cập nhật regression:** 2026-09-28
- **Checkout:** `_pttkpm` working tree; chưa commit/push
- **Phạm vi:** implementation local, state/idempotency tests và synthetic
  dry-run/apply/verify/retry trên PostgreSQL cô lập. Raw `excel-data` không
  được chép vào evidence, log nộp hoặc database dùng chung.
- **Final status:** `NOT READY FOR SUBMISSION`

## Kết quả theo task

| Task | Implementation local | Evidence local | Trạng thái |
|---|---|---|---|
| FCS-13 | `submission_data_operational_replay.py` replay maintenance plan → occurrence → Work Order và cleaning shift/task/checklist; giữ lịch sử khi `REWORK`. Đối soát chỉ đọc kiểm occurrence, Work Order và shift/task theo scope | Targeted replay/reconcile tests pass; synthetic pack 12 workbook/101 dòng PASS `all` dry-run → apply → verify → retry trên PostgreSQL cô lập; full isolated regression mới `334 passed, 1 skipped, 2 warnings` | `PARTIAL` — chưa có approved-pack apply/retry/API readback sau restart trên database sạch |
| FCS-14 | Replay patrol window/log/handoff, incident transition/escalation/acknowledge và parcel `RECEIVED` → `READY_FOR_PICKUP` → handover/exception/case; PIN dùng local HMAC secret, chỉ đối chiếu hash. Đối soát đọc lại window/incident/parcel theo từng source key | Negative-path tests và 5 focused reconciliation tests pass; synthetic `stage=all` rehearsal và full isolated regression mới PASS trên PostgreSQL cô lập | `PARTIAL` — raw source vẫn bị preflight chặn; dòng missed patrol thiếu `missed_reason` cần owner xử lý; chưa có approved-pack DB/API readback |
| FCS-15 | Dùng policy/period từ file 09 và oracle từ file 10; gọi `billing.execute_run`, không insert invoice/ledger trực tiếp. Date-only `issued_on`/`due_on` nay giữ ngày lịch nguồn; đối soát đọc lại invoice/item/snapshot | Date-only regression đã thêm; synthetic `stage=all` dry-run/apply/verify/retry PASS trên PostgreSQL cô lập; full isolated regression sau sửa ngày `334 passed, 1 skipped, 2 warnings` | `PARTIAL` — invoice/payment final status và approved-pack finance report còn chờ FCS-16/17; chưa apply/readback approved pack |

## Kiểm tra đã chạy

```text
pytest tests/test_submission_data_maintenance_replay.py \
  tests/test_submission_data_security_parcel_replay.py \
  tests/test_submission_data_billing_replay.py -q
  12 passed, 5 skipped, 3 warnings

python scripts/test_isolated.py ...
  312 passed, 1 skipped, 3 warnings; disposable PostgreSQL shutdown PASS

python scripts/test_isolated.py --pg-bin <local-pg-bin> --openssl <local-openssl>
  scripts.test_submission_pack_isolated chạy trong cùng disposable cluster
  SUBMISSION_REHEARSAL=PASS stage=all workbooks=12 rows=101 dry_run=PASS apply=PASS verify=PASS retry=PASS
  pytest: 334 passed, 1 skipped, 2 warnings (72.06s)
  migration 0018/empty DB/repeat, seed/repeat, schema drift, forced password rotation, PostgreSQL shutdown: PASS
```

Ba warning là deprecation warning từ test client/runtime; không phải failure.
Các test skip được giữ lại để chờ điều kiện dữ liệu hoặc gate tiếp theo, không
được tính là DoD hoàn tất.

## Giới hạn và gate còn mở

Ngày 2026-09-27, module đối soát read-only bổ sung `5 passed` trong
`tests/test_submission_data_reconcile.py`; `py_compile` của module/replay/test
pass. Đây là kết quả focused synthetic, không cộng vào số `312 passed` của
isolated PostgreSQL regression lịch sử. Diễn tập synthetic xác nhận đường import
DB cho candidate mới; full isolated PostgreSQL regression sau sửa date-only và
scope assertion FCS-13 đã pass `334 passed, 1 skipped, 2 warnings`. Chưa có
approved-pack readback. User chọn synthetic pack để demo local; raw onboarding
vẫn bị chặn bởi sáu terminal timestamp tương lai.

1. DP-01..DP-05/timezone đã có User/Owner approval trong
   `DATA_PROVENANCE.md`, nhưng sáu terminal timestamp của raw source còn chờ
   User/Owner sửa. Chưa có approved pack cụ thể vượt PII/secret scan và
   preflight; không dùng raw workbook để lách gate này.
2. Preflight vẫn fail-closed vì raw source có terminal timestamp tương lai.
3. File security có missed patrol nhưng contract không cung cấp
   `missed_reason`; loader không tự tạo giá trị giả để vượt invariant.
4. File billing có trạng thái `PAID`/`PARTIALLY_PAID`; payment, allocation,
   credit và AR reconciliation thuộc FCS-16.
5. Vì vậy FCS-13..15 mới đạt implementation/local verification, chưa đạt
   approved-pack/apply gate và không thay đổi `Final status: NOT READY FOR
   SUBMISSION`.

