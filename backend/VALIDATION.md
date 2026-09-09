# Phase 1 — bằng chứng kiểm chứng

Ngày chạy: 09/09/2026, Windows, Python 3.12.14, repo `_pttkpm`.

| Kiểm tra đã chạy | Kết quả |
|---|---|
| `pytest -q -m 'not integration'` | 25 passed, 3 integration deselected |
| `RUN_DB_INTEGRATION=1` + `pytest -q --tb=short` | 28 passed, gồm 3 test Aiven thật |
| `pip check` | No broken requirements found |
| Aiven preflight trước migration | Không có bảng người dùng; TLS true, timezone UTC |
| Alembic revision --autogenerate | Sinh `0001_initial_foundation.py`; đã đọc trước upgrade, chỉ CREATE tenants trong schema greencity |
| Alembic upgrade head | Exit 0 |
| Alembic current | `0001 (head)` |
| Alembic check | `No new upgrade operations detected.` |
| Uvicorn local 127.0.0.1:8000 | Startup complete |
| HTTP GET /health | 200, `{"status":"ok","database":"connected"}` |
| HTTP GET /docs, /redoc, /openapi.json | Cả 3 trả 200 |
| Correlation + CORS live | Trả đúng UUID gửi lên và origin localhost:3000 |
| Frontend npm test | 40 passed, 0 failed |
| Frontend npm run build | Vite 6.4.3, 1615 modules, build thành công |
| `git diff --check` | Không có lỗi whitespace ở tracked diff |
| Quét secret nguồn với URI/key/password lấy trong bộ nhớ | Không có khớp trong 31 file được kiểm tra; không in giá trị secret |
| Git ignore | Hai file Tài_nguyên và backend/.env bị ignore; .env.example không bị ignore |

## Giới hạn và lỗi môi trường đã xử lý

- Lần tải pip và kết nối Aiven trong sandbox bị chặn mạng; đã chạy lại qua quyền được duyệt.
- Runner PowerShell ban đầu nhận sai tham số vị trí; sửa PositionalBinding và dùng PythonArgs tường minh, migration chạy lại thành công.
- Bản frontend trong repo chưa có node_modules; `npm ci` theo lockfile rồi build. Vite bị chặn đọc thư mục cha trong sandbox; build lại với quyền được duyệt đã đạt. Không sửa source frontend hoặc lockfile.
- Có 2 deprecation warnings từ Starlette/httpx/AnyIO test client; integration còn có PytestCacheWarning do quyền cache giữa tài khoản sandbox và tài khoản chạy được duyệt. Đây không phải test fail; không che warnings.
- Không chạy lại UX browser suites vì source/UI không thay đổi. Kết quả 40 tests và build không được diễn đạt thành toàn bộ E2E UI đã pass.
- Health chứng minh kết nối DB, không chứng minh API domain/auth đã hoàn tất. 9 test nghiệp vụ trong yêu cầu thuộc Phase 2–8, chưa được đánh dấu pass.
- Aiven hiện có schema greencity, tenants và alembic_version. Test insert Tenant dùng transaction rollback; không nạp seed hay tạo account.
- TLS require ở development không tương đương xác minh CA/hostname verify-full. Role hiện có create_role/create_db/bypass_rls; phải tách role trước production.
- Chưa gọi Gemini. Nên thay khóa Gemini trước Phase 8 vì bộ lọc output đầu phiên đã bỏ sót đoạn đuôi có escape Markdown; không lặp lại khóa trong source/tài liệu.
- Không commit, push, xóa dữ liệu hay sửa nội dung secret gốc.

Theo karpathy-guidelines, chỉ tạo model Tenant và foundation cần kiểm chứng, không scaffold các module domain rỗng. Hướng dẫn PostgreSQL được áp dụng cho pool và ghi rõ giới hạn least-privilege/TLS; không cài thêm Supabase.
