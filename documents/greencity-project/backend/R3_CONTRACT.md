# R3 — nền tảng dữ liệu vệ sinh và an ninh

## Trạng thái

Revision `0007` kế thừa `0006`. Task 2 mở vertical slice vệ sinh cho AC-40 và
AC-41; Task 3 mở vertical slice an ninh/PCCC cho AC-42 và AC-43.

## Scope, audit và replay

Mọi aggregate R3 có `tenant_id`, `site_id`, `building_id` cùng foreign-key scope
chain. Route tương lai phải lấy scope từ `UserContext`, không từ payload. Các
command phải tái sử dụng `idempotency_records` theo tenant/site/actor/operation/key
và ghi `audit_events` trong cùng transaction.

`audit_events` đã append-only. Revision `0007` thêm trigger cấm update/delete trên
timeline bàn giao, log khách, patrol log, escalation, acknowledgement và incident evidence;
sửa sai phải tạo bản ghi mới có lý do.

## Vệ sinh

`cleaning_routes`, `cleaning_areas`, `cleaning_route_stops` xác định catalog
route/khu vực/checklist. Một stop là duy nhất theo route/khu vực và theo vị trí.
`cleaning_shifts` là duy nhất theo route/thời điểm bắt đầu; `cleaning_tasks` là duy
nhất theo shift/stop và có tối đa một rework child để replay không tạo bản ghi song
song. Task 2 không tự sinh child: rework được điều phối qua Case/Work Order liên
kết với task gốc. Kết quả checklist giữ theo vị trí với `PENDING`, `PASS`, `FAIL`,
`NOT_APPLICABLE`.

State task: `PLANNED → ASSIGNED → IN_PROGRESS → SUBMITTED → ACCEPTED`; nhánh
`MISSED`, `REWORK_REQUIRED`, `CANCELLED`. Khi Task 2 đánh giá không đạt, nó sẽ tạo
Work Order với `work_orders.cleaning_task_id` duy nhất, rồi tạo Case qua
`cases.source_work_order_id`. Constraint Work Order yêu cầu đúng một nguồn: Service
Request, Maintenance Occurrence hoặc Cleaning Task.

### API Task 2

- `GET /api/v1/cleaning/routes`, `GET /api/v1/cleaning/assignees?building_id=`:
  `admin`/`director` chỉ nhận catalog và nhân viên vệ sinh trong active site/tòa
  họ được cấp thật.
- `POST /api/v1/cleaning/shifts`: manager tạo ca từ route; mỗi route stop tạo đúng
  một task và snapshot checklist. Bắt buộc `Idempotency-Key`; cùng key + payload
  replay cùng ca, khác payload trả `409 ERR-CONFLICT`.
- `GET /api/v1/cleaning/tasks`, `GET /api/v1/cleaning/tasks/{id}`: manager thấy
  task thuộc building grant; `cleaning` chỉ thấy task có `assigned_to_id` là chính
  account. Bản ghi ngoài assignment/scope trả `404 ERR-SCOPE-NOTFOUND`.
- `POST /assign`, `/start`, `PATCH /checklist/{item}`, `POST /submit`, `/accept`,
  `/missed`, `/cancel` thực thi state machine. `start` và checklist chỉ dành cho
  cleaner được phân công; `assign`, accept và exception branch chỉ dành cho manager.
  Version stale trả `409 ERR-CONFLICT`.
- `submit` yêu cầu mọi mục bắt buộc có `PASS` hoặc `FAIL`. Một `FAIL` chuyển task
  sang `REWORK_REQUIRED`, tạo một Work Order `DRAFT` và một Case trong cùng
  transaction; re-submit cùng idempotency key không tạo thêm record. Checklist của
  task lỗi không thể sửa sau khi task rời `IN_PROGRESS`, nên lịch sử `FAIL` được giữ.
- `accept` chỉ nhận task `SUBMITTED` mà toàn bộ checklist bắt buộc `PASS`. Khi mọi
  task của ca đạt trạng thái cuối (`ACCEPTED`, `MISSED`, `REWORK_REQUIRED`,
  `CANCELLED`), ca chuyển `COMPLETED`.

## An ninh/PCCC

`security_shifts` và `security_shift_handoffs` lưu ca/bàn giao; một shift có thể
có nhiều bản ghi bàn giao để tạo timeline append-only. `security_visitor_logs`
ghi khách theo ca, cũng append-only. Patrol dùng
`patrol_points`, `patrol_windows`, `patrol_logs`; window là duy nhất theo
shift/point/start, và `MISSED` bắt buộc lý do. Incident có type `SECURITY` hoặc
`FIRE`, severity `LOW`/`MEDIUM`/`HIGH`/`CRITICAL`, state
`NEW → TRIAGED → IN_PROGRESS → RESOLVED → CLOSED`.

Escalation tới `security`/`director`, acknowledgement và evidence được lưu thành
bản ghi riêng. `HIGH` và `CRITICAL` tự tạo cả hai escalation trong cùng transaction.
Chỉ account có đúng `target_role` và visibility của incident mới acknowledgement.
Không được đóng nếu thiếu conclusion hoặc evidence; severity cao còn phải đủ hai
acknowledgement.

### API Task 3

- `GET /api/v1/security/shifts`, `GET /{id}`, `/dashboard`: `security` chỉ nhận
  shift được giao cho chính account; `admin`/`director` chỉ nhận building grant
  trong active site. Dashboard trả `MISSED` theo đúng patrol point/khu vực, không
  tự đổi thành `COMPLETED`.
- `POST /security/shifts` tạo ca, người trực và cửa sổ từng patrol point. Cửa sổ
  phải thuộc ca và unique theo shift/point/start. Manager tạo ca; security roster
  và patrol point cũng chỉ trả trong building grant. Tạo ca yêu cầu `Idempotency-Key`.
- `POST /shifts/{id}/start`, `/handoffs`, `/visitors`, `/patrol-windows/{id}/logs`,
  `/complete`, `/missed` thực hiện nghiệp vụ ca. Handoff/visitor/log append-only
  cần idempotency; `missed` cần reason, không ghi `completed_at` hay CHECK_OUT.
- `POST /security/incidents` tạo sự cố `SECURITY`/`FIRE` từ patrol window đang
  visible; `POST /evidence`, `/acknowledgements` chỉ append. Transition là
  `NEW → TRIAGED → IN_PROGRESS → RESOLVED → CLOSED`; `CLOSED` là manager-only và
  kiểm conclusion, evidence, acknowledgement severity cao.
- Payload không nhận tenant/site/role để nới scope. Resource ngoài scope trả
  `404 ERR-SCOPE-NOTFOUND`, role không đúng trả `403 ERR-FORBIDDEN`, stale version
  trả `409 ERR-CONFLICT`.

## API boundary và evidence

Task 2 giữ error envelope, `X-Correlation-ID` và `ERR-CHECKLIST-INCOMPLETE`.
Task 3 dùng `ERR-INCIDENT-CLOSE-REQUIREMENTS` và
`ERR-ESCALATION-UNACKNOWLEDGED` khi chặn đóng sự cố.

`scripts.test_migration_0007` kiểm `0006 → 0007 → 0006 → 0007` trên PostgreSQL
disposable, gồm table/constraint/trigger/Work Order source. Runner cô lập chạy DB
trống tới head, migration/seed lặp, `alembic check` và regression. Seed chỉ tạo
catalog route/area/stop/patrol point; không tạo lịch sử vận hành giả.
