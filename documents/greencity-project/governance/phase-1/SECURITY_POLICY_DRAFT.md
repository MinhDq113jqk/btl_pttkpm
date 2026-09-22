# Dự thảo SECURITY.md cho GreenCity

> Đây là **bản xem trước**, chưa phải policy có hiệu lực. Sau khi PO + Security
> xác nhận phạm vi, severity và không có accepted risk mới, nội dung này sẽ được
> công bố nguyên văn tại `SECURITY.md` ở gốc repository.

## System and Scope

GreenCity là hệ thống quản lý vận hành khu đô thị gồm desktop frontend,
FastAPI backend, PostgreSQL migrations, private evidence và workflow CI.
Policy bao phủ toàn bộ source, workflow, dependency lockfile, migration và
tài liệu governance trong repository. Owner vận hành là Tech Lead; PO và
Security chịu trách nhiệm phê duyệt thay đổi phạm vi/rủi ro.

## Threat Model and Trust Boundaries

Mọi input từ browser, token claim, request body/query, attachment, event
provider và pull request được coi là không tin cậy. Tài sản chính gồm dữ liệu
tenant/site/building, PII, ledger, evidence private, session và credential.
Ranh giới quan trọng là browser→API, API→database/storage/provider và
source→CI/release artifact.

## Security Invariants

- Server suy ra identity, role và data scope; client không mở rộng quyền bằng
  payload, query hoặc token claim.
- Authorization fail closed, scope áp dụng cho API, export, file, cache và
  dashboard; record ngoài scope không lộ tồn tại.
- Credential chỉ nằm trong secret store hoặc backend `.env` bị ignore; không
  có trong frontend, source, log, artifact, SBOM hay tài liệu.
- Evidence private được kiểm type/size/MIME/checksum và chỉ cung cấp trong
  scope hợp lệ.
- Provider failure, retry hoặc thao tác CI không được làm rollback nghiệp vụ
  lõi hay tự bypass release approval.

## Reportable Findings and Severity Context

Các lỗi bypass tenant/scope/auth, lộ secret/PII/evidence, sai ledger/audit,
upload/download private file không đúng quyền, migration gây mất/ghi chéo dữ
liệu, hoặc CI/release provenance có thể bị thay thế là reportable. Severity
được đánh giá theo reachability, khả năng khai thác và tác động thực tế;
không giảm severity chỉ vì một control chưa được kiểm chứng được dự kiến có.

## Out of Scope, Exclusions, and Accepted Risk

Không có accepted risk trong policy này. Các tích hợp V1/`SPEC-ONLY` vẫn là
reportable nếu mã hiện diện hoặc có thể được kích hoạt từ artifact hiện tại.
Không đánh giá hạ tầng/provider mà repository không quản lý, nhưng missing
boundary, secret handling hoặc assumption không được xác minh vẫn là finding.

## Known Limitations and Compensating Controls

Phase 1 chưa chứng minh production deployment, backup/restore, monitoring,
provider contract hoặc data retention thực tế. CI mới phải chạy từ clean clone;
mọi failure/exemption cần vào risk register, có owner và ngày review. CAP-AI,
role roster và pilot scope chờ các decision `DEC-P1-01..04`.
