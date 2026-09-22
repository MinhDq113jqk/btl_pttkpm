# OR-01 — Đối chiếu roadmap với implementation hiện tại

## Nguồn baseline

| Nguồn | Vai trò |
| --- | --- |
| `C:\Users\LEGION\btl\documents\greencity-project\5phase.md` | Kế hoạch thực thi Phase 1; SHA-256 `38C784A2AE86DA90FC5E4B9E1B517F12E761DD9E775D670BB5FA01909F326CE7` |
| `documents/greencity-project/roadmap_v2.md` | Baseline sản phẩm/SRS và Decision Register |
| `main` tại `de67c48` | Implementation được kiểm tra trong lần đối chiếu này |
| `backend/alembic/versions/0015_v1_parcel_case_evidence.py` | Migration hiện ở head `0015` |

Các bằng chứng cũ trong `BACKEND_BASELINE.md` và `checklist.md` được giữ nguyên
để truy vết lịch sử. Chúng không được dùng thay cho kết quả chạy hiện tại hoặc
phê duyệt governance này.

## Chênh lệch cần quyết định

| ID | Bằng chứng | Tác động | Quyết định cần PO + Tech Lead | Trạng thái |
| --- | --- | --- | --- | --- |
| DEC-P1-01 | Roadmap `DEC-12` đặt toàn bộ CAP-AI là `SPEC-ONLY`; mã hiện có endpoint assistant và cấu hình Gemini backend. | Nếu không chốt, pilot có thể vô tình đưa AI vào phạm vi dù chưa qua Gate C. | Xác nhận CAP-AI chỉ là code/demo nội bộ, không là capability pilot hay cam kết vận hành; mọi thay đổi phạm vi phải qua decision record mới. | `PENDING` |
| DEC-P1-02 | SRS liệt kê 10 tác nhân người; `RoleEnum` hiện có 9 role (có `resident`, không có `auditor`), trong khi plan cũ từng dùng roster 8 staff role. | Ma trận quyền, seed và UAT có thể dùng các tập role khác nhau. | Chốt roster pilot, các role bị loại trừ và owner cho mỗi role; sau đó cập nhật seed/test matrix theo quyết định. | `PENDING` |
| DEC-P1-03 | Roadmap mục 15.4 định nghĩa 5 Golden Flow `BUILD`: CSKH-to-cash, Maintenance-to-history, Cleaning-to-case, Patrol-to-incident, Control-and-audit. | Tài liệu cũ có thể nói bốn flow hoặc các tranche khác. | Dùng đúng năm flow này làm baseline Pilot/UAT; Parcel-to-case và Ask-to-escalate AI vẫn `SPEC-ONLY`. | `PENDING` |
| DEC-P1-04 | Phase 5 yêu cầu khoảng 10 account riêng và dữ liệu giả; roadmap giới hạn demo chính ở một site, site thứ hai chỉ cho isolation test. | Không có quyết định thì có nguy cơ dùng account dùng chung hoặc dữ liệu thật. | Xác nhận pilot chỉ dùng dữ liệu giả, account riêng, một site demo, và stop rules trước khi provision. | `PENDING` |

## Bằng chứng implementation hiện tại

| Hạng mục | Quan sát kiểm tra được | Cách diễn giải đúng |
| --- | --- | --- |
| Migration | Có `0001` đến `0015`; runner cô lập migration DB trống, migrate lặp, seed lặp và drift check đều PASS. | Chứng minh được regression cục bộ cho schema hiện tại, không phải phê duyệt release. |
| Backend | `scripts/test_isolated.py` PASS `262 passed, 2 warnings` trên PostgreSQL/TLS disposable. | Đây là local evidence tái lập bằng command ghi ở evidence pack. |
| Frontend | `npm.cmd test` PASS `67/67`. | Đây là local evidence; vẫn cần CI clean clone và build. |
| Legacy documentation | `BACKEND_BASELINE.md` còn ghi Pre-R1/Gate B NOT PASS; `checklist.md` ghi 253 backend và 68 frontend test. | Không xóa history; evidence pack Phase 1 thay thế các con số này cho baseline hiện tại. |

## Bản ghi phê duyệt

Không tự điền tên hoặc ngày. Khi quyết định được duyệt, PO và Tech Lead điền
vào bảng này, liên kết biên bản/issue và cập nhật trạng thái của đúng dòng ở
trên.

| Decision | Người duyệt PO | Người duyệt Tech Lead | Ngày hiệu lực | Link biên bản | Trạng thái |
| --- | --- | --- | --- | --- | --- |
| DEC-P1-01 |  |  |  |  | PENDING |
| DEC-P1-02 |  |  |  |  | PENDING |
| DEC-P1-03 |  |  |  |  | PENDING |
| DEC-P1-04 |  |  |  |  | PENDING |
