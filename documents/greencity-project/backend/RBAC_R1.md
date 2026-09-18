# R1 Unit360 — quyền, scope và acceptance contract

Quyết định OD-ROLE được người dùng xác nhận ngày 10/09/2026: Core MVP dùng
`admin`, `director`, `cskh`, `accountant`, `technical_lead`, `technician`, `cleaning`,
`security`. Kiểm toán chưa thuộc Core; không sửa role switch frontend hoặc xóa
tác nhân Kiểm toán khỏi roadmap V1. Nguồn: Plan2, roadmap §2.1/§9.

## Chính sách chỉ đọc áp dụng cho endpoint Unit360

Owner: Admin/PO quản lý grant; service là nơi cưỡng chế. Actor phải có Account
active, role server-side, tenant/site hợp lệ. Grant thuộc `AccountRole`, optional
`building_id` phải cùng `site_id`; không nhận grant/role từ JWT hoặc payload.

| Role | Scope Unit360 trong R1 | Dữ liệu trả về |
|---|---|---|
| admin | Tenant/site được cấp, hoặc tòa nếu grant có building_id | Unit + residents với contact đã masked |
| director | Site được cấp, hoặc tòa nếu grant có building_id | Unit + residents với contact đã masked |
| cskh | Bắt buộc tòa được cấp | Unit + residents với contact đã masked |
| accountant | Site hoặc tập tòa được cấp | Unit + residents với contact đã masked |
| technical_lead | Bắt buộc tòa được cấp | Unit; ẩn toàn bộ residents vì không có quyền Unit Relationship |
| technician | Chưa có WO để xác minh assignment: deny-by-default (404) | Không trả record; không giả lập phân công |
| cleaning | Không có quyền Unit360 (403) | Không trả record |
| security | Tòa/khu vực được cấp, tối thiểu hóa dữ liệu | Chỉ định danh/vị trí Unit; ẩn area/status và toàn bộ residents |

Role ngoài roster cũng 403. Không lấy tổ hợp `mọi role × mọi building`; quyền
được kết hợp chỉ từ các grant cùng áp dụng lên record đích. Ví dụ CSKH tòa A +
Trưởng KT tòa B không được xem residents của tòa B. Grant null building của
CSKH/Trưởng KT/An ninh không có nghĩa toàn site: không match Unit nào.

An ninh ở đây chỉ có phạm vi địa lý được cấp, chưa có lifecycle ca trực. Đây
không phải nghiệm thu authorization ca/tuần tra của R3. Quyền Person độc lập
của Trưởng KT/An ninh không được suy thành quyền xem quan hệ Person–Unit.

## Migration và tương thích

Revision 0003 thêm `AccountRole.building_id`, index, check building cần site và
FK ghép building/site. Thêm unique `(buildings.id, buildings.site_id)` để FK có
căn cứ. Không rewrite 0002 hoặc tự cấp building cho account hiện hữu.
Account đã có grant site-only vẫn giữ nguyên dữ liệu: role cần tòa bị đóng quyền
cho tới khi có grant tòa. Seed demo tạo grant tòa tường minh, chạy lặp không sinh
thêm grant giống nhau; không tạo assignment/WO.

## Request/response và vòng đời quyền

Endpoint không đổi: `GET /api/v1/units/{unit_id}/360`. Không có API quản trị grant
mới. Phiên xác thực lấy role/grant từ DB ở mỗi request; thay đổi/thu hồi grant
phải có hiệu lực ở request tiếp theo, không cần chờ hết JWT.

401 nếu chưa xác thực; 403 nếu không có role Unit read trong active site;
404 ERR-SCOPE-NOTFOUND cùng message cho missing, sai tenant/site/tòa hoặc chưa
có assigned scope. Query được lọc trước khi load dữ liệu liên quan.

`residents_visible` (boolean) bổ sung vào DTO: false => residents=[] do policy,
không được diễn giải là căn trống. `area_m2` và `status` nullable khi policy masked;
các role đầy đủ vẫn nhận các field cũ với kiểu và giá trị cũ.
Không query Person/Unit Relationship khi projection không cho phép residents.

## Acceptance trước khi ghi nhận fixed cho slice R1

- Cleaning/unknown/auditor: 403 trước Unit lookup; KTV chưa assignment: 404.
- Admin/Director/Accountant site-wide đúng site: 200; tenant/site khác: 404.
- CSKH/Trưởng KT/An ninh đúng tòa: 200 với projection đúng; cùng site khác tòa: 404.
- Role requiring building mà thiếu grant: 404; không nâng quyền từ membership site.
- Multi-role khác tòa không tăng quyền trường dữ liệu của tòa khác.
- Thu hồi grant tòa/membership/khóa Account ảnh hưởng request tiếp theo.
- Token/payload role/building giả không thêm quyền.
- DB chặn building không cùng site; delete building không biến grant thành site-wide.
- Migration từ DB trống + seed repeat + regression tenant/token trước đó pass.
- Demo API: login CSKH → me → Unit đúng tòa 200 → Unit ngoài tòa 404;
  login Trưởng KT → Unit 200/residents_visible=false; cleaning → 403.

Test API/PostgreSQL có thể thực hiện demo trên fixture cô lập không sửa DB tay.
Không nhận assigned-only happy path của KTV là DONE; nó phải được nối với WO
thật ở R2. Chưa có audit/readiness, vì vậy toàn Gate B/R1 vẫn chưa được chấm PASS.
