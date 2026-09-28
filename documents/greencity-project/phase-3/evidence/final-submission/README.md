# FCS-19 — Kiểm chứng gói code nộp

Ngày cập nhật: 2026-09-28. Đây là hướng dẫn và chỉ mục evidence cho working
tree chưa commit; verdict cuối nằm ở [FINAL_SUBMISSION_CHECKLIST.md](../../../FINAL_SUBMISSION_CHECKLIST.md).
Gói demo hiện dùng dữ liệu synthetic, có manifest mang nhãn
`SYNTHETIC_TEST_ONLY`. Raw `excel-data`, raw-derived local validation output và
reverse mapping không thuộc gói.

## Xuất candidate

Từ repository root, dùng một đường dẫn `.local` mới mỗi lần:

```powershell
$candidate = Join-Path '.local' ('fcs19-' + [guid]::NewGuid().ToString('N'))
.\backend\.venv\Scripts\python.exe backend\scripts\export_submission_candidate.py `
  --destination $candidate
```

Exporter lấy danh sách bằng `git ls-files --cached --others --exclude-standard
-z`, chỉ chép file hiện hữu, từ chối symlink, `.env`, bytecode, raw data, cache,
`node_modules`, `dist` và thư mục tạm pytest. Log `.log`/`.result` cùng file
`.txt` trong thư mục historical evidence chỉ giữ local vì có thể chứa đường dẫn
máy; Markdown summary vẫn thuộc candidate. Chỉ đúng 12 tên XLSX canonical
theo `WORKBOOK_CONTRACTS` ở `synthetic/` và CSV scale synthetic được phép có
phần mở rộng bảng tính/CSV trong package. SHA-256
được tính theo thứ tự
đường dẫn, tên file và SHA-256 nội dung. Ghi digest ở evidence local **ngoài**
candidate để tránh một tài liệu tự chứa chính digest của nó. Không thay file
nguồn sau export nếu muốn dùng cùng digest cho mọi gate.

Gói phải có `synthetic/` 12 XLSX, `synthetic_manifest.json`, ảnh
`synthetic_evidence/`, README, scripts, lockfiles và các test. Nó không có
`approved_pack` suy ra từ dữ liệu thật. Raw preflight hiện bị chặn bởi 35 lỗi
thời gian nguồn và không là điều kiện cho demo synthetic mà User/Owner
đã chọn.

## Bản sao bị loại trong quá trình rehearsal

Candidate đầu ngày 2026-09-28 chứa `backend/.pytest-temp-fcs/` do quy tắc
ignore thiếu và có tám link tới screenshot browser local đã bị Git ignore.
Candidate đó bị loại, không dùng làm gói nộp. `.gitignore`, exporter và
`V3-16_PRESENTATION_EVIDENCE.md` đã được sửa; candidate kế tiếp phải chạy lại
link checker và package-content scan. FS-04 còn phát hiện 26 dòng có whitespace
cuối dòng trên chín file; đã bỏ đúng phần whitespace đó và quét lại toàn bộ
candidate text cho kết quả 0 lỗi.

## Kiểm tra trên candidate mới

1. Trước khi cài dependency, scan file list và nội dung package; chỉ log
   rule/file/count, không ghi giá trị PII/secret. Phân loại mọi kết quả dạng
   test literal và synthetic trước khi đánh dấu FS-03.
2. Tạo Python 3.12 venv sạch, cài `backend/requirements.lock.txt`, chạy
   `pip check` và backend `pytest -q --basetemp=.pytest-temp-<id>`.
3. Trong `greencity-app`, chạy `npm ci`, `npm test`, `npm run check:links` và
   `npm run build`. Checker dùng `marked@17.0.5` để kiểm file, image, reference
   và fragment; mỗi lỗi chỉ in SHA-256 rút gọn của target.
4. Chạy PostgreSQL isolated regression, synthetic dry-run/apply/verify/retry,
   browser Golden Flow trên backend thật, restart readback và backup/restore
   trên cùng candidate. Ghi passed, failed, skipped, warnings và giới hạn.
5. Đối chiếu [FCS-16-20_EXECUTION_EVIDENCE.md](../FCS-16-20_EXECUTION_EVIDENCE.md),
   final checklist và owner/reviewer sign-off trước verdict.

Kiểm thử trên candidate giữa chừng sau khi sửa ignore/link: Python 3.14.3
venv cài từ lockfile và `pip check` PASS; backend `194 passed, 158 skipped,
0 warnings` với pytest temp trong candidate; `npm ci` cài 141 package, frontend
`58 passed`; FS-05 kiểm 51 Markdown/180 target bằng `marked@17.0.5` và 0 lỗi.
Production build đã PASS 1.625 module trên candidate trước đó; cần lặp lại
trên candidate cuối. Full isolated PostgreSQL trên working tree trước sửa
manifest/preflight gần nhất đạt `334 passed, 1 skipped, 2 warnings`, synthetic
12/101 dry-run/apply/verify/retry PASS. Đây là bằng chứng trước final package
digest; không tự thay thế các gate trong checklist.

Clean Git clone từ HEAD hiện không chứa các thay đổi chưa commit. Exporter chứng
minh bản sao working tree sạch, còn clean clone/package cuối cần xác nhận sau
khi nội dung được chốt. FCS-19 giữ `PARTIAL` đến lúc các gate trên cùng candidate
đạt.
