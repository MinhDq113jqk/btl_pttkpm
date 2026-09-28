# Evidence FCS-05 đến FCS-10 — submission data onboarding

- **Ngày kiểm tra:** 2026-09-27
- **Checkout:** `_pttkpm` working tree; chưa commit/push
- **Phạm vi:** kiểm chứng local cho mapping, reader, preflight, import ledger và
  dry-run loader. Raw `excel-data` không được chép vào evidence và không được
  ghi vào database dùng chung.
- **Final status:** `NOT READY FOR SUBMISSION`

## Kết quả theo task

| Task | Kết quả local | Bằng chứng đã ghi nhận | Trạng thái bàn giao |
|---|---|---|---|
| FCS-05 | 13 quyết định mapping ở `fcs05-r2`; `open=0`; suy dẫn `fee_policy_code` và `period_key` fail-closed, không join bằng PII; incident enum đã khóa trong contract `fcs05-r3` | `FCS05_MAPPING=PASS`; preflight raw không phát sinh enum error | DONE; owner đã duyệt provenance và timezone |
| FCS-06 | Reader chỉ đọc, giới hạn size/row/column/cell, đúng 12 workbook/2 sheet; chặn formula, hidden sheet, header sai và external link metadata | `FCS06_READER=PASS workbooks=12 rows=101`; targeted suite `8 passed` | Pass local |
| FCS-07 | Preflight quyết định `101/101`, `0` orphan và `database_write=false`; lỗi tương lai được redact và fail-closed | Raw: `future_terminal_candidates=6`, `FUTURE_SCHEDULE=78` chỉ là warning, checksum verified; warning-only focused test PASS | Safety gate đang chặn replay terminal; chưa thể gọi nguồn hiện tại là apply-ready |
| FCS-08 | Migration `0018` tạo import run/external reference; manifest và payload hash ổn định; conflict bị chặn trong service | `alembic heads` → `0018 (head)`; migration rehearsal PASS; full isolated regression `307 passed, 1 skipped, 2 warnings` | Pass local |
| FCS-09 | Loader master đã có dependency order, credential ngoài repo, transaction và idempotency path | `--stage master --dry-run` PASS, `database_write=False`; synthetic `stage=all` dry-run/apply/verify/retry PASS trên PostgreSQL cô lập | Apply/verify dữ liệu thật còn chờ approved pack và credential file local |
| FCS-10 | Loader reference có category/SLA, asset/maintenance, cleaning/security/parcel initial-state, fee policy/version và accounting period; conflict/idempotency được kiểm tra | `--stage references --dry-run` PASS, `database_write=False`; isolated regression `307 passed, 1 skipped, 2 warnings` | Apply/reference count trên approved pack và DB sạch chưa chạy; chi tiết FCS-10..12 ở [evidence mới](FCS-10-12_EXECUTION_EVIDENCE.md) |

## Lệnh và kết quả đã chạy

Các lệnh dưới đây chạy từ `backend` bằng `.venv` local; đường dẫn raw chỉ xuất
hiện trong command của máy phát triển, không đưa vào log nộp:

```text
python -m app.services.submission_data_contract
  FCS03_CONTRACT=PASS workbooks=12
python -m app.services.submission_data_mapping
  FCS05_MAPPING=PASS version=fcs05-r2 open=0
python -m app.services.submission_data_normalization
  FCS04_NORMALIZATION=PASS version=fcs04-r1 external_key_specs=12
python -m app.services.submission_data_reader <raw-source>
  FCS06_READER=PASS workbooks=12 rows=101 version=fcs06-r1
pytest tests/test_submission_data_preflight.py tests/test_submission_data_references.py -q
  8 passed
python -m scripts.load_submission_data --stage master --dry-run
  FCS09_LOADER=PASS ... rows=101 database_write=False
python -m scripts.load_submission_data --stage references --dry-run
  FCS09_LOADER=PASS ... rows=101 database_write=False
python scripts/test_isolated.py ...
  307 passed, 1 skipped, 2 warnings; migration/seed-repeat/drift/shutdown PASS
```

Hai warning là deprecation warning từ FastAPI/Starlette TestClient và anyio;
không phải failure của FCS-08.

## Gate còn mở

1. FCS-01 đã được User/Owner phê duyệt ngày 2026-09-27 cho mục đích, retention
   và timezone `Asia/Ho_Chi_Minh`; contract fingerprint hiện tại là
   `4d749f7377335c49a6b3159e0d1e12bfb5480cd95f158bca2fe7f52a5ce16147`.
2. User/Owner sẽ sửa sáu terminal timestamp theo thời điểm sự kiện thật tại
   nguồn; sau đó phải chạy lại manifest và preflight. Không suy diễn hoặc tự
   sửa giá trị thời gian để làm test pass.
3. Chưa tạo `approved_pack` ẩn danh; vì vậy chưa chạy `apply`, `verify`,
   reference count trên DB sạch, state-machine replay hay Golden Flow trên dữ
   liệu import.
4. Giữ nguyên `FINAL STATUS: NOT READY FOR SUBMISSION` cho đến khi các gate trên
   và FCS-11..20 hoàn tất.
