# R7 Task 1 — Runtime guidance index

Tài liệu này khôi phục đường dẫn lịch sử `R7_TASK1_RUNTIME.md` từng được tham
chiếu trong tài liệu backend. Không dùng file này như bằng chứng rằng một lần
rehearsal lịch sử đã được chạy.

Hướng dẫn runtime hiện hành được duy trì ở các nguồn sau:

- [README repository](../../../README.md) cho setup backend/frontend local.
- [Final submission checklist](../FINAL_SUBMISSION_CHECKLIST.md) cho runtime
  readiness, migration, database probe, browser rehearsal và package gate.
- [Final submission plan](../FINAL_CODE_SUBMISSION_PLAN.md) cho thứ tự hoàn tất
  candidate.

Các nguyên tắc vẫn áp dụng:

1. Không tự migrate database khi ứng dụng khởi động; migration là bước vận hành
   riêng và phải đưa database đến Alembic head của candidate.
2. Runtime chỉ dùng credential/quyền cần thiết; rehearsal phá hủy phải chạy trên
   database disposable hoặc development/test được phép dùng.
3. Health/readiness không thay thế schema drift, PostgreSQL regression hoặc
   Golden Flow.
4. Secret, connection URI và credential không được ghi vào evidence commit.
