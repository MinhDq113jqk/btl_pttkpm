# OR-05 — Release và change control

## Trạng thái phát hành

Không có tag, release hay deployment nào được tạo bởi Phase 1. Một tag `vX.Y.Z`
chỉ là ứng viên release khi toàn bộ điều kiện bên dưới được ký; workflow
`release-evidence.yml` chỉ tạo evidence artifact, không publish hoặc deploy.

## Điều kiện tạo release candidate

| Điều kiện | Bằng chứng bắt buộc | Owner |
| --- | --- | --- |
| Baseline scope | DEC-P1-01..04 đã duyệt | PO + Tech Lead |
| Security | `SECURITY.md` chính thức, five findings có owner/SLA/status, không P0/P1 chưa xử lý | Security |
| CI | Link run clean clone xanh: backend migration/regression, frontend test/build, secret scan, dependency scan; phải cùng commit với tag | DevOps + QA |
| Version | Annotated tag `vX.Y.Z` khớp `greencity-app/package.json`, nằm trên `main` và commit SHA | Release Owner |
| Protected approval | GitHub Environment `release-candidate` có required reviewers trước khi chạy manual evidence workflow | Release Owner + repository admin |
| Artifact integrity | Source archive SHA-256, workflow artifact digest, SBOM SPDX JSON | Release Owner + DevOps |
| Change control | Checklist, impact/AC, migration note, rollback reference, approver | Release Owner |

## Change record tối thiểu

| Trường | Nội dung bắt buộc |
| --- | --- |
| Change ID và mục tiêu | Một ID, phạm vi, AC/NFR/DEC bị ảnh hưởng |
| Ref và version | Branch/commit SHA, annotated tag dự kiến, lockfile thay đổi |
| Rủi ro | Link finding/risk, impact tenant/PII/ledger/availability, owner và SLA |
| Evidence | Link workflow run, test output, scan, SBOM, `SHA256SUMS.txt` |
| Migration | Upgrade path, schema head, compatibility; ghi rõ nếu rollback DB chưa được diễn tập |
| Rollback | Tag/commit an toàn để revert, trigger, owner, bước xác minh và communication |
| Phê duyệt | PO, Tech Lead, Security, QA, Release Owner; ngày/giờ |

## Rollback policy

- Chỉ rollback code về tag/commit đã được xác minh; không dùng `reset --hard` hay
  force-push làm thủ tục release.
- Migration rollback chỉ được ghi là khả dụng khi có evidence rehearsal. Phase 1
  không tuyên bố downgrade/restore production; Phase 3 phải chứng minh điều đó.
- Khi có dấu hiệu leak cross-scope, secret, ledger mismatch hoặc artifact digest
  không khớp: dừng release/pilot, revoke access phù hợp, giữ audit evidence và
  mở incident/change record.

## Evidence retention

CI artifact được giữ tối thiểu 30 ngày; bản evidence được chọn cho pilot/release
được lưu theo policy storage của Phase 3. Không đưa `.env`, credential, PII
hoặc private attachment vào artifact/SBOM/checklist.

## Thiết lập ngoài repository bắt buộc

Repository admin phải bảo vệ `main` và pattern tag `v*`, đồng thời cấu hình
Environment `release-candidate` có required reviewers phù hợp với bảng approval.
Workflow `Release evidence` chỉ được dispatch thủ công với tag đã tồn tại và
link change record HTTPS; nó tự từ chối tag không annotated, không nằm trên
`main`, không khớp version hoặc không có Quality and security gates PASS ở
cùng commit. Nếu environment/rule chưa được cấu hình, Exit Phase 1 vẫn `NOT PASS`.
