# AGENTS.md - Quy chế làm việc phối hợp Codex & Antigravity

Tài liệu này xác định nguyên tắc phối hợp giữa **Codex** (Implementation Agent) và **Antigravity** (Review Agent) trên môi trường Windows cho dự án hiện tại.

---

## 1. Phân định vai trò (Roles)

| Agent | Vai trò chính | Trách nhiệm |
|---|---|---|
| **Codex** | Triển khai chính (Lead Implementer) | Nhận yêu cầu, kiểm tra git/môi trường, viết mã nguồn, viết test, tự kiểm tra cục bộ, chuẩn bị diff sạch gửi review, sửa lỗi sau review. |
| **Antigravity** | Kiểm thử & Review độc lập (Independent Reviewer) | Rà soát chuyên sâu diff/mã nguồn về logic, bảo mật, race condition, data integrity, cấp quyền (authorization), chỉ xuất kết quả theo định dạng chuẩn. |
| **User (Bạn)** | Phê duyệt & Điều phối (Approver) | Quyết định cuối cùng, cấp credential vào môi trường cục bộ, kiểm tra giao diện và vận hành thực tế. |

---

## 2. Nguyên tắc bảo mật & Tách biệt Secret

1. **Tuyệt đối không lưu Credential vào Code/VCS/AGENTS.md:**
   - Secret thật chỉ lưu ở file cục bộ `.env` (đã nằm trong `.gitignore`) hoặc biến môi trường PowerShell `$env:...`.
   - File mẫu public là `.env.example` (chỉ chứa tên biến, không chứa giá trị).
   - Tuyệt đối không commit, không đưa vào issue, commit message hay prompt trao đổi giữa các agent.

2. **Khử nhạy cảm trước khi truyền Context (Redaction):**
   - Khi chia sẻ log, cấu hình hoặc mẫu kết nối, luôn dùng định dạng ẩn danh:
     - `DATABASE_URL=postgresql://[USER]:[REDACTED]@[HOST]/[DB]`
     - `Authorization: Bearer [REDACTED]`
     - `X-API-Key: [REDACTED]`
   - Nếu cần xác thực API thật, mỗi agent chỉ tự chạy kiểm tra trong terminal cục bộ của chính mình với biến môi trường đã nạp sẵn.

3. **Không ghi đồng thời (Concurrency Safety):**
   - Không bao giờ để Codex và Antigravity cùng chỉnh sửa một file đồng thời.
   - Không chạy lệnh migration hoặc tác vụ ghi dữ liệu nguy hiểm cùng lúc từ hai client.

---

## 3. Quy trình Review & Giới hạn vòng lặp

### Quy trình từng bước:
1. **Codex**: Nhận task $\rightarrow$ Viết code & Test $\rightarrow$ Chạy kiểm thử cục bộ pass $\rightarrow$ Tạo diff sạch (git diff) $\rightarrow$ Gửi yêu cầu review lần 1 (hoặc ghi vào `.review/review-1.md`).
2. **Antigravity**: Đọc diff/context $\rightarrow$ Phân tích chuyên sâu $\rightarrow$ Trả về kết quả theo đúng chuẩn format.
3. **Codex**: Nếu `STATUS: NEEDS_REVISION`, tiến hành khắc phục các điểm nghiêm trọng $\rightarrow$ Chạy lại test $\rightarrow$ Gửi verification lần 2.
4. **Giới hạn vòng lặp (Review Limit):** Tối đa **2 lượt review** cho mỗi nhiệm vụ để tránh tắc nghẽn.
5. **Hoàn tất:** Khi đạt `STATUS: PASS` (hoặc sau vòng 2 đã xử lý xong), Codex tổng kết và báo cáo User để nghiệm thu.

### Định dạng phản hồi bắt buộc của Antigravity:
Chỉ được trả về một trong hai trạng thái:

```
STATUS: PASS
```

hoặc:

```
STATUS: NEEDS_REVISION
- [Tên phân loại]: [Mô tả cụ thể vấn đề nghiêm trọng và đề xuất khắc phục]
- ... (tối đa 3 điểm trọng yếu nhất)
```

**Trọng tâm rà soát:**
- Logic sai, Runtime error, Data corruption
- Lỗ hổng bảo mật (Security vulnerability, Authorization bypass)
- Race condition nghiêm trọng, Deadlock, Treo DB lock
- Lỗi cạn kiệt tài nguyên (OOM, DoS, Buffer overflow)
- API/Type/Schema mismatch hoặc Regression
- *Không phản hồi các vấn đề tiểu tiết về formatting hay style thuần túy.*

---

## 4. Quản lý trạng thái nội bộ (.review/)

Thư mục `.review/` được git bỏ qua (`.gitignore`), dùng để ghi nhận tiến độ trao đổi:
- `.review/task.md`: Thông tin nhiệm vụ hiện tại và số lượt review.
- `.review/review-1.md`: Diff và kết quả review vòng 1.
- `.review/review-2.md`: Diff và kết quả review vòng 2 (nếu có).
- `.review/result.md`: Báo cáo kết thúc trước khi chuyển giao cho User.
