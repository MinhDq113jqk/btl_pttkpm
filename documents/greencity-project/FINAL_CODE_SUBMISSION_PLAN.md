# Kế hoạch hoàn tất code GreenCity để nộp

Tài liệu này là điểm vào cho quy trình hoàn tất và kiểm chứng gói code GreenCity.
Chi tiết implementation và evidence không được sao chép lại ở đây để tránh lệch
nguồn; các tài liệu bên dưới là source of truth.

## Mục tiêu

Tạo một candidate có thể dựng lại từ checkout sạch, migrate database sạch, chạy
regression, chạy frontend build/UX, kiểm tra dữ liệu demo tổng hợp và thực hiện
Golden Flow mà không cần file hoặc bước ngầm trên máy phát triển.

## Thứ tự thực hiện

1. Hoàn tất implementation theo dependency trong
   [FINAL_CODE_SUBMISSION_20_TASKS.md](FINAL_CODE_SUBMISSION_20_TASKS.md).
2. Chạy toàn bộ gate của
   [FINAL_SUBMISSION_CHECKLIST.md](FINAL_SUBMISSION_CHECKLIST.md) trên cùng một
   commit/package candidate.
3. Dùng `backend/tests/fixtures/submission_data/synthetic/` cho demo/nộp; dữ liệu
   raw trong `excel-data` và `data_that` là local-only, không thuộc package.
4. Chỉ kết luận candidate đạt khi migration từ database sạch, migration/seed
   repeat, schema drift, backend PostgreSQL regression, frontend test/build,
   dependency audit và secret scan đều pass.
5. Golden Flow/browser rehearsal phải dùng database disposable hoặc database
   development/test được phép dùng; không chạy rehearsal phá hủy trên database
   chia sẻ.

## Tài liệu liên quan

- [README dự án](../../README.md): setup và chạy local.
- [Roadmap nghiệp vụ](roadmap_v2.md).
- [Roadmap triển khai](roadmap_v3.md).
- [Traceability matrix](V3-00_TRACEABILITY_MATRIX.md).
- [Data provenance](DATA_PROVENANCE.md).
- [Data onboarding contract](DATA_ONBOARDING_CONTRACT.md).

## Nguyên tắc evidence

Một trạng thái `PASS` chỉ có giá trị cho commit/candidate đã thực sự chạy gate.
Không dùng số test hoặc log của commit cũ để chứng minh candidate mới. Không đưa
credential, token, PIN, connection string hoặc raw dữ liệu thật vào log/evidence
được commit.
