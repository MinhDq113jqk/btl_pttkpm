# R1 closeout — Implemented & Verified Local

**Ngày kiểm chứng:** 13/09/2026
**Phạm vi đóng local:** `AC-01`, `AC-02`, `AC-03`, `AC-24`, `AC-35`.

Trạng thái này có nghĩa source, contract và kiểm thử cục bộ cho năm AC dưới đây
đã khớp nhau tại checkout hiện tại. Nó **không** là Gate B/Gate C, không xác
nhận Aiven/production, không mở R3--R5, và không thay thế một verdict review
độc lập. Không tạo Antigravity review lần 3 trong closeout này.

## Lần chạy dùng làm bằng chứng

Từ `backend/`:

```powershell
.\.venv\Scripts\python.exe -m scripts.test_isolated --pg-bin 'C:\Program Files\PostgreSQL\18\bin' --openssl 'C:\Program Files\Git\usr\bin\openssl.exe'
```

- PostgreSQL 18.4/TLS disposable: migration DB trống đến head `0006`, kiểm
  path `0005 -> 0006 -> 0005`, upgrade/seed lặp, `alembic check` và shutdown:
  PASS.
- Regression toàn checkout hiện tại: **185 passed, 2 warning deprecation in
  46.58s**. Đây là regression suite chung (có cả thay đổi R2 có sẵn trong
  working tree), không được diễn giải là số test R1 riêng lẻ.
- Frontend: `npm test` **51/51 PASS**; `npm run test:staff` **30 checks PASS**
  với API response được kiểm soát; `npm run build` PASS trong **12.93s**.
  Browser smoke không phải browser-to-live-PostgreSQL E2E.

## Ma trận AC → implementation → evidence

| AC | Contract và implementation | Test local trực tiếp | Kết luận giới hạn |
|---|---|---|---|
| **AC-01** — cross-site UI/API/export/file bị chặn, không lộ metadata | `API_CONTRACT.md`; `app/core/policy.py` dựng tenant/site/building từ DB; `app/api/auth.py`, `app/api/units.py`, `app/api/persons.py`, `app/api/import_runs.py` không nhận scope do client tự chọn. | `test_security_postgres.py::test_admin_cannot_read_foreign_tenant_or_inactive_site`, `::test_switch_requires_real_tenant_membership_and_refreshes_roles`; `test_r1_integration.py::test_unit_360_cross_site_isolation_strictly_returns_404`; `test_import_runs_postgres.py::test_import_run_scope_and_client_scope_spoofing_are_denied`, `::test_all_or_nothing_error_file_link_is_private_and_expiring`; frontend test kiểm body/query không gửi tenant/site/role. | Các bề mặt R1 đã liệt kê trả `ERR-SCOPE-NOTFOUND`/404 và link file site cũ không tải được. Không suy diễn coverage cho route ngoài scope R1. |
| **AC-02** — import 1.000 dòng, kết quả dòng/retry/concurrency | `API_CONTRACT.md`; `app/api/import_runs.py`, `app/services/import_runs.py`, migration `0006_r1_import_runs.py`. Receipt PostgreSQL, `expected_version`, row lock và building lock là cơ chế thực thi. | `test_import_runs_postgres.py::test_csv_import_run_1000_rows_preview_apply_and_replay`: 1.000 dòng = 950 importable, 50 warning chuẩn hóa, 25 duplicate `SKIPPED`, 25 `ERROR`; replay không tăng Unit. `::test_concurrent_upload_replay_and_apply_are_serialized`: engine riêng xác nhận upload cùng key cùng receipt; hai apply khác key cho một run chỉ 200 + 409 và chỉ một apply receipt. | `PARTIAL` đã ghi đúng 950 Unit trong scenario 1.000 dòng; không khẳng định throughput hay concurrency benchmark production. |
| **AC-03** — một Person sở hữu 2 Unit và thuê Unit thứ 3 | `API_CONTRACT.md`; `app/api/persons.py`, `app/api/units.py`, `app/models/person.py`, migration `0005_r1_person_unit_relationship.py`. | `test_r1_integration.py::test_ac03_person_owns_two_units_and_rents_a_third_bidirectionally`, `::test_ac03_person_lookup_enforces_role_and_site_scope`, `::test_ac03_postgres_rejects_ownership_overflow_and_cross_tenant`, `::test_ac03_temporal_scope_hides_expired_and_other_building_relationships`; runner gọi `scripts.test_migration_0005`. | Tra cứu hai chiều, ratio, interval hiệu lực và tenant/site scope đã được kiểm local; không phải approval release. |
| **AC-24** — quarantine/checksum/signed link | `API_CONTRACT.md`; `app/services/import_runs.py` private storage, SHA-256, token `purpose=import-error-download`; `app/api/import_runs.py` kiểm session + scope + token khi download; migration `0006`. File quarantine phát outbox event **`AttachmentQuarantined`** theo `EVT-23`. | `test_import_runs_postgres.py::test_csv_validation_quarantines_bad_files_and_rejects_bad_mapping`, `::test_tampered_private_source_fails_closed_without_creating_a_receipt`, `::test_all_or_nothing_error_file_link_is_private_and_expiring`. | Sai tên/MIME/nội dung bị quarantine; source/error checksum sai trả `ERR-FILE-INTEGRITY`; token bị ràng actor/site/building/run, hết hạn 410 và không dùng làm Bearer. Không tuyên bố antivirus engine ngoài allowlist hiện có. |
| **AC-35** — đổi site xóa trạng thái/cản response cũ | `greencity-app/src/services/apiClient.js` giữ token in-memory + `sessionRevision`; `greencity-app/src/App.jsx` remount `workspaceKey` sau `/auth/switch-site` rồi `/auth/me`; `app/api/auth.py` ký lại active site từ DB. | `frontend-integration.test.js`: `site switch sends only site_id...`, `a 401 response from the previous site cannot clear the switched session`, workspace key đổi; `staff-ux.cjs`: 30 checks gồm reset Unit360, stale data, switch token và 401. | UI cache/filter/state đang mount được reset, response cũ bị bỏ, 401 current session logout. Không phải E2E browser với PostgreSQL sống. |

## Ràng buộc closeout

- Không tạo migration mới; head vẫn `0006`.
- Không stage `plan1.md`/`plan2.md`, không dùng `git add .`, không stage thay đổi
  R2/frontend có sẵn ngoài phần evidence R1.
- `API_CONTRACT.md` và tài liệu này là index contract/evidence hiện hành cho
  closeout R1.
