# Thiết kế cơ sở dữ liệu FireEyes

Cập nhật: 07/10/2026.
Hệ quản trị: SQLite.
Thư viện truy cập: Python sqlite3.
Phiên bản schema: 1.

## 1. Phạm vi công việc

Phần CSDL phụ trách:

- Thiết kế bảng, thuộc tính và quan hệ.
- Xây dựng khóa chính, khóa ngoại và ràng buộc.
- Lưu, truy vấn và cập nhật dữ liệu.
- Lưu kết quả nhận diện do thành viên AI cung cấp.
- Cung cấp dữ liệu để thành viên web xây dựng giao diện.
- Kiểm thử tính toàn vẹn dữ liệu.
- Chuẩn bị dữ liệu giả lập để demo.

Phần CSDL không thực hiện huấn luyện model, đọc camera để nhận diện,
xây dựng giao diện hoặc gửi SMS/cuộc gọi thật.

Chưa có chức năng đăng nhập. Bảng contacts lưu người nhận cảnh báo,
không phải tài khoản đăng nhập.

## 2. Các file liên quan

| Đường dẫn | Vai trò |
|---|---|
| CSDL/models/schema.sql | Định nghĩa bảng, index và trigger |
| CSDL/models/database.py | Lớp FireEyesDB truy cập CSDL |
| data/fireeyes.db | File SQLite của chương trình |
| tests/test_database.py | Kiểm thử CSDL |
| main.py | Điểm chạy CLI theo phương án thu gọn |
| docs/ERD.puml | Mã sơ đồ quan hệ thực thể |

Ảnh, video và trọng số model lưu ngoài CSDL.
CSDL chỉ lưu đường dẫn, metadata và kết quả xử lý.

## 3. Các nhóm dữ liệu

| Nhóm | Bảng |
|---|---|
| Địa điểm và thiết bị | locations, cameras, contacts |
| Metadata dataset và model | dataset_versions, dataset_samples, annotations, model_versions |
| Kết quả xử lý | frames, detections |
| Sự kiện và thông báo | incidents, notifications |

Giữ nhóm bảng dataset để tương thích schema hiện tại và hỗ trợ truy vết.
Không bắt buộc nhập toàn bộ dataset để demo phần CSDL.

## 4. Từ điển dữ liệu

Quy ước:

- PK: khóa chính.
- FK: khóa ngoại.
- NN: NOT NULL.
- UQ: UNIQUE.
- Các cột không ghi NN hoặc PK được phép NULL.
- Tất cả id là INTEGER PRIMARY KEY.
- Thời gian được ứng dụng lưu dưới dạng TEXT ISO 8601 theo UTC.

### 4.1. locations — Địa điểm giám sát

| Cột | Kiểu | Ràng buộc | Ý nghĩa |
|---|---|---|---|
| id | INTEGER | PK | Mã địa điểm |
| name | TEXT | NN, UQ | Tên địa điểm |
| address | TEXT | NN | Địa chỉ |

### 4.2. cameras — Camera hoặc nguồn hình ảnh

| Cột | Kiểu | Ràng buộc | Ý nghĩa |
|---|---|---|---|
| id | INTEGER | PK | Mã camera |
| location_id | INTEGER | NN, FK → locations.id | Địa điểm đặt camera |
| name | TEXT | NN | Tên camera |
| source_ref | TEXT | NN | Tham chiếu nguồn hình ảnh |
| enabled | INTEGER | NN, mặc định 1, chỉ 0 hoặc 1 | Trạng thái bật/tắt |

Khóa duy nhất kết hợp: (location_id, name).

source_ref dùng đường dẫn hoặc tên biến môi trường tham chiếu cấu hình camera.
Không đưa URL chứa mật khẩu camera vào dữ liệu chia sẻ.

### 4.3. contacts — Người nhận cảnh báo

| Cột | Kiểu | Ràng buộc | Ý nghĩa |
|---|---|---|---|
| id | INTEGER | PK | Mã liên hệ |
| location_id | INTEGER | NN, FK → locations.id | Địa điểm phụ trách |
| name | TEXT | NN | Tên người nhận |
| destination | TEXT | NN | Địa chỉ nhận, số điện thoại hoặc giá trị demo |
| channel | TEXT | NN, CHECK | sms, call, email hoặc console |

Khóa duy nhất kết hợp: (location_id, destination, channel).

### 4.4. dataset_versions — Phiên bản dataset

| Cột | Kiểu | Ràng buộc | Ý nghĩa |
|---|---|---|---|
| id | INTEGER | PK | Mã phiên bản dataset |
| name | TEXT | NN | Tên dataset |
| version | TEXT | NN | Phiên bản |
| source_url | TEXT | NN | Nguồn dữ liệu |
| license_name | TEXT | NN | Thông tin giấy phép |
| class_map | TEXT | NN | Mapping nhãn dạng JSON theo quy ước ứng dụng |
| manifest_sha256 | TEXT | Cho phép NULL | Hash manifest |
| status | TEXT | NN, CHECK | planned hoặc verified |

Khóa duy nhất kết hợp: (name, version).

SQL chưa kiểm tra class_map là JSON hợp lệ hoặc manifest_sha256 đúng định dạng.
Không đặt verified chỉ vì đã tạo bản ghi nguồn.

### 4.5. dataset_samples — Metadata ảnh dataset

| Cột | Kiểu | Ràng buộc | Ý nghĩa |
|---|---|---|---|
| id | INTEGER | PK | Mã ảnh |
| dataset_id | INTEGER | NN, FK → dataset_versions.id | Dataset chứa ảnh |
| image_path | TEXT | NN | Đường dẫn ảnh |
| label_path | TEXT | NN | Đường dẫn nhãn |
| sha256 | TEXT | NN, độ dài 64 | Hash ảnh |
| split | TEXT | NN, CHECK | train, val hoặc test |
| source_group | TEXT | NN | Nhóm nguồn, ví dụ cùng video |

Khóa duy nhất kết hợp:

- (dataset_id, image_path).
- (dataset_id, sha256).

Trigger ngăn cùng source_group xuất hiện ở nhiều split trong một dataset.
Bên nhập dữ liệu phải cung cấp source_group đúng; trigger không tự nhận biết
ảnh cùng video hoặc ảnh gần giống nhau.

CHECK độ dài hash chưa xác nhận chuỗi là hexadecimal hay hash khớp file.

### 4.6. annotations — Nhãn của ảnh dataset

| Cột | Kiểu | Ràng buộc | Ý nghĩa |
|---|---|---|---|
| id | INTEGER | PK | Mã annotation |
| sample_id | INTEGER | NN, FK → dataset_samples.id | Ảnh chứa đối tượng |
| class_id | INTEGER | NN, chỉ 0 hoặc 1 | 0: smoke; 1: fire |
| xc | REAL | NN | Tọa độ tâm ngang chuẩn hóa |
| yc | REAL | NN | Tọa độ tâm dọc chuẩn hóa |
| w | REAL | NN, lớn hơn 0 | Chiều rộng chuẩn hóa |
| h | REAL | NN, lớn hơn 0 | Chiều cao chuẩn hóa |

CHECK yêu cầu bounding box nằm trong biên ảnh với sai số cho phép 0.000001.
Annotation không có confidence.

### 4.7. model_versions — Metadata model

| Cột | Kiểu | Ràng buộc | Ý nghĩa |
|---|---|---|---|
| id | INTEGER | PK | Mã model |
| name | TEXT | NN, UQ | Tên định danh phiên bản model |
| dataset_id | INTEGER | FK → dataset_versions.id | Dataset liên quan |
| weights_path | TEXT | Cho phép NULL có điều kiện | Đường dẫn trọng số |
| weights_sha256 | TEXT | Cho phép NULL có điều kiện | Hash trọng số |
| class_map | TEXT | NN | Mapping nhãn dạng JSON |
| is_demo | INTEGER | NN, chỉ 0 hoặc 1 | Đánh dấu model demo |

Khi is_demo = 0, schema yêu cầu dataset_id, weights_path và
weights_sha256 khác NULL; weights_sha256 phải có độ dài 64.

Khi is_demo = 1, các trường trên được phép NULL.
SQL chưa xác minh file trọng số tồn tại hoặc hash đúng với nội dung file.

### 4.8. frames — Bản ghi khung hình

| Cột | Kiểu | Ràng buộc | Ý nghĩa |
|---|---|---|---|
| id | INTEGER | PK | Mã frame |
| camera_id | INTEGER | NN, FK → cameras.id | Camera nguồn |
| model_id | INTEGER | NN, FK → model_versions.id | Model tạo kết quả |
| request_id | TEXT | NN | Mã yêu cầu chống lưu lặp |
| payload_sha256 | TEXT | NN | Hash dữ liệu đầu vào |
| captured_at | TEXT | NN | Thời điểm ghi nhận |
| snapshot_path | TEXT | Cho phép NULL | Đường dẫn ảnh bằng chứng |

Khóa duy nhất kết hợp: (camera_id, request_id).

Python chuẩn hóa captured_at về UTC và tính payload_sha256.
SQL chưa kiểm tra định dạng thời gian hoặc độ dài payload_sha256.

### 4.9. detections — Kết quả nhận diện

| Cột | Kiểu | Ràng buộc | Ý nghĩa |
|---|---|---|---|
| id | INTEGER | PK | Mã detection |
| frame_id | INTEGER | NN, FK → frames.id | Frame chứa kết quả |
| class_id | INTEGER | NN, chỉ 0 hoặc 1 | 0: smoke; 1: fire |
| confidence | REAL | NN, từ 0 đến 1 | Độ tin cậy |
| xc | REAL | NN | Tâm ngang chuẩn hóa |
| yc | REAL | NN | Tâm dọc chuẩn hóa |
| w | REAL | NN, lớn hơn 0 | Chiều rộng chuẩn hóa |
| h | REAL | NN, lớn hơn 0 | Chiều cao chuẩn hóa |

CHECK yêu cầu bounding box nằm trong biên ảnh với sai số cho phép 0.000001.

annotations lưu nhãn dataset; detections lưu dự đoán do AI cung cấp.
Phần CSDL không tự tạo dự đoán nhận diện thật.

### 4.10. incidents — Sự kiện cảnh báo

| Cột | Kiểu | Ràng buộc | Ý nghĩa |
|---|---|---|---|
| id | INTEGER | PK | Mã sự kiện |
| camera_id | INTEGER | NN, FK → cameras.id | Camera liên quan |
| trigger_detection_id | INTEGER | NN, FK → detections.id | Detection kích hoạt |
| started_at | TEXT | NN | Thời điểm bắt đầu |
| status | TEXT | NN, mặc định open | open, resolved hoặc false_alarm |
| rule_description | TEXT | NN | Mô tả lý do mở sự kiện |
| closed_at | TEXT | Cho phép NULL có điều kiện | Thời điểm đóng |
| resolution_note | TEXT | Cho phép NULL | Ghi chú xử lý |

Ràng buộc SQL:

- Mỗi camera chỉ có tối đa một incident có status = open.
- Sự kiện open phải có closed_at = NULL.
- Sự kiện resolved hoặc false_alarm phải có closed_at khác NULL.
- Khi thêm incident hoặc sửa camera/bằng chứng của incident,
  trigger kiểm tra detection thuộc đúng camera.

Hàm close_incident yêu cầu ghi chú không rỗng.
SQL chưa bắt buộc resolution_note khi đóng sự kiện.

Trigger hiện tại không kiểm tra lại quan hệ camera nếu sửa trực tiếp
frames.camera_id hoặc detections.frame_id. Luồng Python hiện chưa cung cấp
chức năng đổi các liên kết này.

### 4.11. notifications — Bản ghi thông báo

| Cột | Kiểu | Ràng buộc | Ý nghĩa |
|---|---|---|---|
| id | INTEGER | PK | Mã thông báo |
| incident_id | INTEGER | NN, FK → incidents.id | Sự kiện cần thông báo |
| contact_id | INTEGER | NN, FK → contacts.id | Người nhận |
| channel | TEXT | NN | Kênh tại thời điểm tạo |
| destination | TEXT | NN | Địa chỉ nhận tại thời điểm tạo |
| status | TEXT | NN, CHECK | pending, sent, failed hoặc simulated |
| attempted_at | TEXT | NN | Thời điểm ghi nhận lần thử |
| provider_message_id | TEXT | Cho phép NULL | Mã từ nhà cung cấp |
| error_message | TEXT | Cho phép NULL | Nội dung lỗi |

Khóa duy nhất kết hợp: (incident_id, contact_id).

channel và destination là bản chụp thông tin người nhận khi tạo thông báo.
Khác contacts.channel, notifications.channel chưa có CHECK giới hạn giá trị.

Hàm simulate_notification kiểm tra người nhận thuộc cùng địa điểm với camera.
SQL chưa có trigger thực hiện kiểm tra này.

Hiện chương trình chỉ ghi thông báo simulated, không gửi thông báo thật.
Schema chưa có bảng lịch sử nhiều lần thử gửi.

## 5. Các quan hệ

| Bảng cha | Bảng con | Quan hệ |
|---|---|---|
| locations | cameras | Một địa điểm có 0..n camera |
| locations | contacts | Một địa điểm có 0..n liên hệ |
| dataset_versions | dataset_samples | Một dataset có 0..n ảnh |
| dataset_samples | annotations | Một ảnh có 0..n annotation |
| dataset_versions | model_versions | Một dataset có 0..n model; model có thể không liên kết dataset |
| cameras | frames | Một camera có 0..n frame |
| model_versions | frames | Một model có 0..n frame |
| frames | detections | Một frame có 0..n detection |
| cameras | incidents | Một camera có 0..n sự kiện theo thời gian |
| detections | incidents | Một detection có thể được tham chiếu bởi 0..n sự kiện theo schema |
| incidents | notifications | Một sự kiện có 0..n thông báo |
| contacts | notifications | Một liên hệ có 0..n thông báo |

Các FK đều không khai báo ON DELETE CASCADE hoặc ON UPDATE CASCADE.
Khi bật khóa ngoại, không được xóa bản ghi cha còn được tham chiếu.

Liên kết dataset của model là tùy chọn ở cấp FK; CHECK bổ sung yêu cầu
model thật phải có dataset.

## 6. Index và trigger

### Index khai báo tường minh

| Tên | Mục đích |
|---|---|
| idx_frames_camera_time | Hỗ trợ tìm frame theo camera và thời gian |
| idx_detections_frame | Hỗ trợ tìm detections của frame |
| idx_one_open_incident | UNIQUE có điều kiện: tối đa một sự kiện open/camera |
| idx_incident_status_time | Hỗ trợ tìm sự kiện theo trạng thái và thời gian |

Các ràng buộc UNIQUE còn bảo đảm không trùng các bộ thuộc tính đã mô tả.

### Trigger

| Tên | Thời điểm | Kiểm tra |
|---|---|---|
| sample_group_insert | Trước INSERT dataset_samples | Nhóm nguồn không nằm ở nhiều split |
| sample_group_update | Trước UPDATE dataset_samples | Nhóm nguồn không nằm ở nhiều split |
| incident_camera_insert | Trước INSERT incidents | Bằng chứng thuộc đúng camera |
| incident_camera_update | Trước UPDATE camera_id hoặc trigger_detection_id của incidents | Bằng chứng thuộc đúng camera |

## 7. Quy tắc ở lớp Python

- Bật PRAGMA foreign_keys = ON cho từng kết nối.
- Nhãn nội bộ: 0 = smoke, 1 = fire.
- Kiểm tra dữ liệu số hữu hạn; từ chối NaN và infinity trong bbox/confidence.
- captured_at phải có múi giờ và được chuẩn hóa về UTC.
- request_id phải là chuỗi không rỗng.
- Retry cùng camera, request_id và payload trả lại frame đã lưu.
- Retry cùng camera và request_id nhưng payload khác bị từ chối.
- Ghi frame và detections trong cùng transaction.
- Model dùng khi ghi frame phải có mapping đúng quy ước FireEyes.
- Bên gọi quyết định mở sự kiện; CSDL không tự quyết định có cháy thật.
- Khi camera đã có sự kiện open, open_incident trả ID sự kiện đó.
- Dữ liệu đầu vào được truyền bằng tham số SQL.

Những quy tắc chỉ có ở Python không được bảo đảm nếu bên khác ghi SQL trực tiếp.
Ưu tiên tích hợp qua các hàm đã thống nhất.

## 8. Vì sao tách frames, detections và incidents?

Một frame có thể chứa nhiều đối tượng, nên có nhiều detections.

Một sự kiện có thể kéo dài qua nhiều frame. incidents lưu trạng thái sự kiện
và detection kích hoạt đầu tiên; schema hiện chưa có bảng liên kết đầy đủ
mọi frame/detection thuộc cùng sự kiện.

Frame không có detection biểu diễn kết quả đã ghi nhận mà không phát hiện
đối tượng. Việc thiếu frame không đủ kết luận camera mất kết nối.

Theo dõi heartbeat, gom sự kiện theo thời gian và cập nhật bằng chứng
chưa được triển khai trong phần hiện tại.

## 9. Các hàm hiện có

| Hàm | Công dụng |
|---|---|
| initialize | Khởi tạo schema |
| seed_demo | Tạo dữ liệu mẫu |
| record_frame | Lưu frame và detections |
| frame_detections | Đọc detections của frame |
| open_incident | Mở sự kiện theo quyết định bên gọi |
| close_incident | Đóng sự kiện |
| simulate_notification | Ghi thông báo giả lập |
| counts | Đếm bản ghi theo bảng |
| list_incidents | Đọc danh sách sự kiện |

Chưa có đầy đủ hàm thêm/sửa địa điểm, camera, liên hệ và model cho tích hợp.
Bổ sung theo nhu cầu nhóm đã thống nhất.

## 10. Truy vấn minh họa

### Lịch sử sự kiện

```sql
SELECT i.id, l.name AS location, c.name AS camera,
       i.status, i.started_at
FROM incidents AS i
JOIN cameras AS c ON c.id = i.camera_id
JOIN locations AS l ON l.id = c.location_id
ORDER BY i.started_at DESC;
```

### Số bounding box theo nhãn

```sql
SELECT class_id, COUNT(*) AS number_of_boxes
FROM detections
GROUP BY class_id;
```

Đây là số bounding box, không phải số vụ cháy.

### Truy vết model tạo dự đoán

```sql
SELECT d.id, d.confidence, m.name AS model_name,
       m.weights_sha256, f.captured_at
FROM detections AS d
JOIN frames AS f ON f.id = d.frame_id
JOIN model_versions AS m ON m.id = f.model_id;
```

### Lịch sử thông báo

```sql
SELECT n.id, n.incident_id, c.name AS contact_name,
       n.channel, n.destination, n.status, n.attempted_at
FROM notifications AS n
JOIN contacts AS c ON c.id = n.contact_id
ORDER BY n.attempted_at DESC;
```

## 11. Kiểm thử và giới hạn

Bộ tests hiện có gồm 8 bài:

1. Lưu bền vững và seed lặp.
2. Request trùng và retry khác payload.
3. Validation và khóa ngoại khi ghi frame.
4. Nhãn, bbox, NaN và infinity không hợp lệ.
5. Frame không có detection và chuẩn hóa múi giờ.
6. Chống trùng sự kiện đang mở và đóng/mở sự kiện.
7. Thông báo giả lập, chống trùng và kiểm tra địa điểm.
8. Trùng hash dataset và source_group ở nhiều split.

Ngày 07/10/2026, 8/8 tests đạt trong môi trường kiểm tra của trợ lý
với các file schema.sql, database.py và test_database.py người dùng gửi.

Kết quả này chưa xác nhận cấu trúc thư mục sau chỉnh sửa trên máy người dùng,
chưa kiểm tra tích hợp AI/web và không chứng minh mọi ràng buộc đã được kiểm thử.

## 12. Tích hợp và bàn giao

Với thành viên AI, cần thống nhất:

- camera_id và model_id đã đăng ký.
- request_id để chống lưu lặp.
- captured_at có múi giờ.
- class_id theo mapping nội bộ.
- confidence và bbox chuẩn hóa.
- snapshot_path nếu có ảnh bằng chứng.
- Bộ phận quyết định mở/đóng incident.

Với thành viên web, cần thống nhất:

- Danh sách địa điểm và camera.
- Danh sách, chi tiết và trạng thái sự kiện.
- Ảnh bằng chứng và detection kích hoạt.
- Lịch sử thông báo.
- Bộ lọc, phân trang và thống kê.

Chưa triển khai API HTTP. Có thể gọi FireEyesDB từ backend Python phù hợp.
Trình duyệt không đọc trực tiếp file SQLite.

Khi thay đổi schema đã triển khai, cần migration và phiên bản mới.
Không xóa CSDL cũ để thay thế cho migration.