# R5 Task 4 — Migration / release rehearsal evidence pack

## Kết luận và ranh giới

Ngày 15/09/2026, rehearsed migration R5 trên PostgreSQL 18/TLS **cô lập**
đã PASS. Runner tạo cluster localhost mới, không kế thừa biến `PG*`,
`DATABASE_*` hoặc `RUN_DB_*`, và tự dừng/xóa workspace sau khi kết thúc.

Đây là bằng chứng **Implemented & Verified Local**. Nó không là phê duyệt
release, Gate B/C, deployment Aiven/production, backup/restore rehearsal,
hay independent review. Không chạy các lệnh bên dưới trên DB vận hành.

## Lệnh tái lập authoritative

Chạy từ thư mục `backend` trên Windows. Lệnh này không dùng `.env` hoặc URI
được copy vào terminal; password, TLS certificate và port đều được tạo ngẫu
nhiên cho process test.

```powershell
.\.venv\Scripts\python.exe -m scripts.test_isolated --pg-bin 'C:\Program Files\PostgreSQL\18\bin' --openssl 'C:\Program Files\Git\usr\bin\openssl.exe'
```

Pass chỉ hợp lệ khi có cả `Isolated PostgreSQL regression: PASS` và
`Test PostgreSQL shutdown: PASS`. Nếu runner bị ngắt giữa chừng, không dùng
output từng phần làm release evidence; chạy lại từ đầu với một cluster mới.

## Ma trận diễn tập

| Hạng mục | Cơ chế / revision | Verdict ngày 15/09 | Điều được chứng minh |
|---|---|---:|---|
| Cluster sạch + TLS | `initdb`, SCRAM, cert localhost, port ngẫu nhiên | PASS | Không đụng DB/credential kế thừa; backend kết nối TLS vào cluster mới. |
| Upgrade/downgrade R5 | `0010 -> 0011 -> 0010 -> 0011` trong `scripts.test_migration_0011` | PASS | Có delivery state + `notification_read_models` sau upgrade; downgrade bị từ chối khi còn delivery state/read model, revision không bị đổi; khi dữ liệu guard đã sạch, downgrade và re-upgrade thành công. |
| Regression migration trước R5 | path `0005`, `0007`, `0008`, `0009`, `0010` | PASS | R5 không phá các migration path được runner hỗ trợ. |
| DB trống + upgrade repeat | `migrate upgrade head` hai lần | PASS | Head hiện tại có thể tạo từ DB rỗng và lệnh upgrade lặp không sinh thay đổi. |
| Seed repeat | `scripts.seed` hai lần | PASS | Seed local chạy lặp an toàn trên schema head. Đây là repeat tuần tự, không phải bằng chứng concurrent seed. |
| Schema drift | `scripts.migrate check` | PASS — `No new upgrade operations detected.` | Không có operation Alembic autogenerate mới từ models hiện tại. Không thay thế review migration bằng tay. |
| Regression API/domain | `pytest -q --tb=short` dưới biến isolated | PASS — **223 passed**, **2 warnings**, **0 skipped**, 82.83s | Contract/API, data scope, concurrency, ledger/audit controls và năm Golden Flows trong suite. |
| Shutdown/cleanup | `pg_ctl ... stop`, kiểm port đóng | PASS | Cluster mà runner tạo đã dừng. |

Hai warnings là deprecation của Starlette `TestClient`/AnyIO. Không có warning
nào được bỏ qua hoặc diễn giải thành pass production.

## Checklist release rehearsal có thể ký nhận

1. Review revision `0011_r5_outbox_notifications.py`, đặc biệt downgrade
   fail-closed; không sửa revision đã áp dụng để “sửa nhanh”.
2. Chạy đúng runner ở trên từ checkout cần release; lưu output redacted gồm
   revision path, test count/warnings và shutdown verdict.
3. Chạy frontend independently, không tính browser mock smoke là live API:

   ```powershell
   Set-Location ..\greencity-app
   npm test
   npm run build
   npm run test:dashboard
   npm run test:notifications
   ```

   Snapshot cùng ngày: Node **62/62**, Vite build PASS, Dashboard **24** checks
   và Notifications **17** checks. Hai suite browser intercept transport có
   chủ đích; chúng kiểm state/keyboard/request shape, không thay HTTP
   acceptance trên PostgreSQL disposable.
4. Chỉ sau khi có owner review, kế hoạch backup/restore riêng, role migration
   least-privilege và change approval thì mới lập kế hoạch rollout môi trường
   khác. Không chạy downgrade trên DB có dữ liệu thật để “test”.

## Artifacts liên quan

- `scripts/test_isolated.py`: runner disposable, cả cleanup/shutdown.
- `scripts/test_migration_0011.py`: oracle upgrade/downgrade R5 fail-closed.
- `R5_CONTRACT.md`: contract outbox, dashboard/audit và giới hạn R5.
- `R5_EXIT_EVIDENCE.md`: ma trận AC/invariant và Five Golden Flows local.
