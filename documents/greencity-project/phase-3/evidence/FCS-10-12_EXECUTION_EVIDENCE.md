# Evidence FCS-10 đến FCS-12 — reference và domain replay

- **Ngày kiểm tra:** 2026-09-27; **cập nhật regression:** 2026-09-28
- **Checkout:** `_pttkpm` working tree; chưa commit/push
- **Phạm vi:** implementation local, raw dry-run chỉ đọc và synthetic
  dry-run/apply/verify/retry trên PostgreSQL cô lập. Raw `excel-data` không
  được chép vào evidence hoặc ghi vào database dùng chung.
- **Final status:** `NOT READY FOR SUBMISSION`

## Kết quả

| Task | Implementation local | Evidence | Trạng thái |
|---|---|---|---|
| FCS-10 | Reference loader kiểm tra scope/conflict và idempotency cho category/SLA, asset/plan, fee policy/version/period; scheduler/reference không dùng default ngầm | `--stage references --dry-run` → `PASS`, `12 workbook`, `101 rows`, `database_write=False`; isolated PostgreSQL regression `307 passed, 1 skipped, 2 warnings` | `PARTIAL` — chưa apply/verify approved pack trên DB sạch |
| FCS-11 | Tạo reference initial-state cho cleaning route/area/stop/shift/task/checklist, security shift/patrol point/window/incident và parcel RECEIVED; source terminal state chỉ giữ để replay | Contract test xác nhận target entities; references dry-run pass; missing scope/role/incident/parcel/PIN-secret có error code riêng | `PARTIAL` — chưa có reference count readback trên DB sạch; replay security/parcel thuộc FCS-14 |
| FCS-12 | `submission_data_replay.py` replay create → triage → assign → start → checklist/cost → submit/accept/close; stage `all` nay gọi cùng replay. `submission_data_reconcile.py` kiểm từng `work_code`, scope, Service Request, Work Order, CostLine, không chỉ import-run status/count | Synthetic pack 12 workbook/101 dòng đã PASS `all` dry-run → apply → verify → retry trên PostgreSQL cô lập; full isolated regression mới `334 passed, 1 skipped, 2 warnings`; 5 focused reconciliation tests pass. Raw `--stage replay/all --dry-run` vẫn trả `PREFLIGHT_BLOCKED` | `PARTIAL` — chưa apply/retry/verify approved pack, chưa có API readback sau restart; CLOSED từ raw vẫn cần binary evidence hợp lệ |

## Lệnh đã chạy

```text
python -m scripts.load_submission_data --source <raw-excel-data> --stage references --dry-run
  FCS09_LOADER=PASS stage=references workbooks=12 rows=101 database_write=False

python backend/scripts/load_submission_data.py --source <raw-excel-data> --stage references --dry-run
  FCS09_LOADER=PASS stage=references workbooks=12 rows=101 database_write=False

python -m scripts.load_submission_data --source <raw-excel-data> --stage all --dry-run
  FCS09_LOADER=FAIL code=PREFLIGHT_BLOCKED (kiểm tra lại 2026-09-27; exit=1)

python -m scripts.load_submission_data --source <raw-excel-data> --stage replay --dry-run
  FCS09_LOADER=FAIL code=PREFLIGHT_BLOCKED

python backend/scripts/load_submission_data.py --source <raw-excel-data> --stage replay --dry-run
  FCS09_LOADER=FAIL code=PREFLIGHT_BLOCKED (exit=1)

pytest tests/test_submission_data_preflight.py tests/test_submission_data_references.py tests/test_submission_data_service_request_replay.py -q
  12 passed

python scripts/test_isolated.py ...
  307 passed, 1 skipped, 2 warnings; migration/seed-repeat/drift/shutdown PASS

python scripts/test_isolated.py --pg-bin <local-pg-bin> --openssl <local-openssl>
  scripts.test_submission_pack_isolated chạy trong cùng disposable cluster
  SUBMISSION_REHEARSAL=PASS stage=all workbooks=12 rows=101 dry_run=PASS apply=PASS verify=PASS retry=PASS
  pytest: 334 passed, 1 skipped, 2 warnings (72.06s)
  migration 0018/empty DB/repeat, seed/repeat, schema drift, forced password rotation, PostgreSQL shutdown: PASS
```

Hai warning là deprecation warning từ FastAPI/Starlette TestClient và anyio;
không phải failure. `PREFLIGHT_BLOCKED` của replay là safety gate hiện hành:
raw source có sự kiện/timestamp tương lai và không được sửa trực tiếp để làm
test pass.

Dòng `--stage all --dry-run` từng được ghi PASS ở bản evidence trước không còn
đúng với loader hiện tại: stage `all` nay bắt buộc thực hiện FCS-12 và chặn
terminal event tương lai. Kết quả FAIL ở trên là từ lần chạy chỉ đọc, không
ghi raw workbook vào log hoặc database. `5 passed` của reconciliation chỉ chứng
minh các nhánh synthetic tập trung. Diễn tập `stage=all` kiểm tra đường import
trên PostgreSQL cô lập với synthetic pack; vẫn chưa thay thế apply/verify trên
cùng approved pack. Full isolated regression sau các sửa đổi hiện tại đã pass
`334 passed, 1 skipped, 2 warnings`; số `307 passed` là kết quả lịch sử.

User chọn synthetic pack để demo khi binary evidence của dòng `CLOSED` trong
raw chưa đủ. Lựa chọn này giúp kiểm thử luồng local có dữ liệu tổng hợp; raw
onboarding vẫn bị chặn bởi sáu terminal timestamp tương lai và chưa có
approved-pack evidence theo DoD gốc.

## Gate còn mở

1. User/Owner đã duyệt DP-01..DP-05 và timezone tại `DATA_PROVENANCE.md`;
   sáu terminal timestamp của raw source vẫn chờ User/Owner sửa theo sự kiện
   thật, rồi mới chạy lại preflight và tạo approved pack đủ điều kiện.
2. Chưa chạy `apply`/`verify` trên dữ liệu thật; reference count và API scope
   readback trên DB sạch chưa được xác nhận.
3. Dòng Service Request `CLOSED` chỉ được replay khi approved pack cung cấp
   evidence binary hợp lệ; loader không tạo placeholder để vượt state machine.
4. FCS-13..16 đã có implementation/local verification trong
   [FCS-13-15_EXECUTION_EVIDENCE.md](FCS-13-15_EXECUTION_EVIDENCE.md) và
   [FCS-16-20_EXECUTION_EVIDENCE.md](FCS-16-20_EXECUTION_EVIDENCE.md), nhưng
   vẫn chưa đạt approved-pack/apply gate; FCS-17..20 chưa hoàn tất. Giữ
   `NOT READY FOR SUBMISSION`.
