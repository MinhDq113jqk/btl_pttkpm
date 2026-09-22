# OR-03 — Threat model và risk register

## Threat model tóm tắt

| Trust boundary | Input không tin cậy | Tài sản cần bảo vệ | Bất biến bắt buộc |
| --- | --- | --- | --- |
| Browser → API | Body, query, route parameter, correlation header, token cũ | Session, role, scope, dữ liệu tenant | Backend tự suy ra identity/scope; deny by default; lỗi không lộ path/body/secret. |
| API → PostgreSQL | Query từ service/migration | Tenant/site/building data, ledger, audit | Scope trước truy vấn/mutation; migration repeatable; role runtime không DDL ở Phase 3. |
| API → private evidence | Upload/download request | Attachment, ảnh, PII | Allowlist, checksum, scoped/signed access và audit. |
| API → provider | Prompt/event/retry | Key, dữ liệu đúng quyền, availability Core | Key chỉ server-side; provider failure không rollback Core; Phase 2 đặt quota/circuit breaker. |
| Source → CI/release artifact | Pull request, lock file, action/tool dependency | Source integrity, SBOM, digest, release evidence | Clean clone, secret/dependency scan, immutable evidence và approval trước tag. |

## Security invariants dùng để review

1. Tenant, site, building và role được suy ra trên server; frontend payload hoặc token claim không được mở rộng quyền.
2. Không có row trong policy matrix nghĩa là deny; out-of-scope record không được lộ tồn tại.
3. Secret, token, database URL và private evidence không xuất hiện trong source, log, bundle hay evidence pack.
4. Tệp private chỉ được truy cập trong scope hợp lệ và có audit/correlation khi nghiệp vụ yêu cầu.
5. Release evidence chỉ được tạo qua protected `release-candidate` environment khi annotated tag nằm trên `main`, có Quality and security gates xanh cùng commit, SHA-256 digest, SBOM, scan, test evidence và approval cùng tham chiếu một baseline.

## Risk register Phase 1

SLA bắt đầu khi finding được PO/Security ghi nhận. `Not accepted` không có ngày hết
hạn vì finding chưa được phép suppress; khi chuyển sang `Accepted`, phải ghi
expiry bắt buộc và mitigation bù trừ.

| ID | Finding / rủi ro | Severity | Owner | SLA | Trạng thái | Acceptance expiry | Mitigation / điều kiện đóng |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SEC-P1-01 | CAP-AI trong mã hiện tại mâu thuẫn với roadmap `SPEC-ONLY`; chưa có quyết định pilot. | High | PO + Tech Lead | 7 ngày | Open | Not accepted | PO/Tech Lead duyệt DEC-P1-01; giới hạn rõ capability trước pilot. |
| SEC-P1-02 | SRS, enum và roster demo không cùng một tập role; policy/seed/UAT có thể cấp sai quyền. | High | Tech Lead + PO | 7 ngày | Open | Not accepted | Chốt DEC-P1-02, cập nhật role matrix/seed/negative tests. |
| SEC-P1-03 | Repository trước Phase 1 không có CI secret/dependency/clean-clone gate. | High | DevOps + QA | 7 ngày | Mitigation implemented, verification pending | Not accepted | Workflow mới phải có run green trên GitHub; scan fail phải tạo finding hoặc approved exception. |
| SEC-P1-04 | Data classification, third-party owner, retention và pilot data boundary chưa có record được duyệt. | High | Security + PO | 14 ngày | Open | Not accepted | Xác nhận inventory, provider register, owner/retention và chỉ dùng fake data. |
| SEC-P1-05 | Chưa có release evidence chuẩn liên kết version/tag, CI xanh, digest, SBOM và rollback reference. | Medium | Release Owner + DevOps | 14 ngày | Mitigation implemented, verification pending | Not accepted | Protected environment phải có required reviewers; manual workflow phải kiểm tag, main ancestry, CI cùng commit và tạo evidence artifact/SBOM/digest. |

### Quy tắc acceptance

- Chỉ PO và Security cùng phê duyệt mới được đổi một finding sang `Accepted`.
- Mỗi acceptance phải ghi lý do, control bù trừ, ngày hết hạn, người review lại và
  liên kết change record.
- P0/P1 hoặc finding chưa hết hạn không được đưa vào pilot chỉ bằng một ghi chú
  trong release checklist.

## Giới hạn hiện biết

- Phase 1 chỉ thiết lập governance và gate. Không tuyên bố provider, production
  deployment, backup/restore hay monitoring đã hoạt động; đó là các phase sau.
- Các test local chứng minh regression cho configuration hiện có, không thay thế
  review độc lập, dữ liệu thật hoặc phê duyệt pháp lý/nghiệp vụ.
