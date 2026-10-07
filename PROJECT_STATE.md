# PROJECT_STATE — FireEyes — Phần cơ sở dữ liệu

Cập nhật: 07/10/2026.
Múi giờ: Asia/Bangkok.
Schema hiện tại: SQLite user_version=1.

## 1. Bối cảnh dự án

- Demo giữa kỳ môn Trí tuệ nhân tạo tại VKU.
- Nhóm gồm 3 sinh viên năm 3 ngành Công nghệ thông tin.
- Đề tài: FireEyes — Hệ thống cảnh báo cháy và phát hiện khói
  từ camera giám sát sẵn có.

Phân công nhóm:

1. Thành viên AI: nhận diện lửa/khói, xử lý camera/video.
2. Người dùng: thiết kế và lập trình cơ sở dữ liệu.
3. Thành viên giao diện: xây dựng web hiển thị dữ liệu và cảnh báo.

File này theo dõi phần việc CSDL của người dùng.
Không đại diện cho tiến độ hoàn thành toàn bộ hệ thống.

## 2. Phạm vi phần CSDL

### Công việc phụ trách

- Phân tích yêu cầu lưu trữ.
- Xác định thực thể, thuộc tính và quan hệ.
- Vẽ ERD.
- Viết từ điển dữ liệu.
- Tạo bảng, khóa, ràng buộc, index và trigger.
- Viết Python lưu, truy vấn và cập nhật dữ liệu.
- Quy định cấu trúc dữ liệu trao đổi với thành viên AI và web.
- Kiểm thử tính toàn vẹn dữ liệu.
- Chuẩn bị dữ liệu giả lập để demo CSDL.
- Viết hướng dẫn tích hợp và bàn giao.

### Ngoài phạm vi

- Huấn luyện và đánh giá YOLO.
- Đọc camera/video để thực hiện nhận diện.
- Xây dựng giao diện web.
- Lập trình dịch vụ gửi SMS hoặc gọi điện thật.
- Đo accuracy, mAP, FPS hoặc độ trễ nhận diện.

Các bảng nhận diện vẫn thuộc phần thiết kế CSDL vì chúng lưu
kết quả do thành viên AI cung cấp.

## 3. Môi trường đã xác nhận

- Hệ điều hành: Windows.
- IDE: Visual Studio Code.
- Terminal: PowerShell.
- Python trong .venv: 3.11.8.
- CSDL: SQLite.
- Thư viện truy cập CSDL: sqlite3.
- Đã cài Pillow 12.3.0 phục vụ công cụ kiểm tra dataset.
- Phần CSDL cốt lõi không cần Pillow.

Thư mục dự án:

D:\Nam_Hoc\Nam_3\Tri_tue_nhan_tao\demo\FireEyes

File CSDL:

data/fireeyes.db

Lệnh chạy Python:

    .\.venv\Scripts\python.exe

## 4. Quyết định thiết kế

- Giữ schema v1 gồm 11 bảng đang hoạt động.
- Chưa cần xóa bảng hoặc tạo lại CSDL.
- Dữ liệu ảnh/video/weights lưu ngoài CSDL.
- CSDL lưu đường dẫn, metadata và kết quả xử lý.
- Quy ước nhãn nội bộ: 0=smoke, 1=fire.
- Thành viên AI phải chuyển mapping model về quy ước nội bộ
  trước khi ghi dữ liệu.
- Bounding box dùng tọa độ chuẩn hóa xc, yc, w, h.
- Timestamp có múi giờ và lưu theo UTC.
- SQL nhận dữ liệu đầu vào phải dùng tham số.
- Các thao tác ghi liên quan dùng transaction.
- Khi đổi schema đã triển khai, phải có migration với version mới.

SQLite hiện phục vụ demo.
Cách triển khai chung với AI và web cần được thống nhất khi tích hợp.

## 5. Các bảng dữ liệu

| Bảng | Chức năng |
|---|---|
| locations | Lưu địa điểm giám sát |
| cameras | Lưu camera và nguồn hình ảnh |
| contacts | Lưu người nhận và kênh thông báo theo địa điểm |
| dataset_versions | Lưu phiên bản, nguồn và mapping dataset |
| dataset_samples | Lưu metadata ảnh và tập train/val/test |
| annotations | Lưu bounding box nhãn của dataset |
| model_versions | Lưu thông tin phiên bản model |
| frames | Lưu lần ghi nhận frame cùng camera và model xử lý |
| detections | Lưu các dự đoán của AI trong frame |
| incidents | Lưu sự kiện cảnh báo và trạng thái xử lý |
| notifications | Lưu bản ghi thông báo và kết quả gửi |

### Nhóm trọng tâm cho demo tích hợp

- locations
- cameras
- contacts
- model_versions
- frames
- detections
- incidents
- notifications

### Nhóm quản lý dataset mở rộng

- dataset_versions
- dataset_samples
- annotations

Chưa bắt buộc nhập toàn bộ ảnh huấn luyện vào CSDL để demo
luồng lưu kết quả nhận diện.

Nếu đăng ký model thật theo schema hiện tại, cần có bản ghi
dataset_versions và thông tin weights phù hợp.

## 6. Các quan hệ chính

- Một location có nhiều cameras.
- Một location có nhiều contacts.
- Một dataset_version có nhiều dataset_samples.
- Một dataset_sample có nhiều annotations hoặc không có annotation.
- Một dataset_version có thể liên kết nhiều model_versions.
- Model demo được phép không liên kết dataset.
- Một camera có nhiều frames.
- Một model_version được sử dụng cho nhiều frames.
- Một frame có nhiều detections hoặc không có detection.
- Một camera có nhiều incidents theo thời gian.
- Mỗi incident có một detection làm bằng chứng kích hoạt.
- Một incident có nhiều notifications.
- Một contact có thể nhận nhiều notifications.

Không đồng nhất annotations với detections:
- annotations: nhãn dữ liệu huấn luyện.
- detections: kết quả dự đoán do AI cung cấp.

## 7. Ràng buộc nghiệp vụ hiện có

- Bật khóa ngoại khi mở kết nối CSDL.
- Không trùng tên camera trong cùng địa điểm.
- Không trùng bộ địa điểm, địa chỉ nhận và kênh thông báo.
- Không trùng tên và phiên bản dataset.
- Không trùng đường dẫn hoặc hash ảnh trong cùng dataset.
- Một source_group không được xuất hiện ở nhiều split
  trong cùng dataset.
- Class nội bộ chỉ nhận 0 hoặc 1.
- Confidence nằm trong khoảng 0 đến 1.
- Bounding box có kích thước dương và nằm trong biên cho phép.
- Không trùng request_id trên cùng camera.
- Retry cùng request_id và payload trả lại dữ liệu đã ghi.
- Retry cùng request_id nhưng payload khác bị từ chối.
- Mỗi camera chỉ có tối đa một incident đang mở.
- Detection kích hoạt incident phải thuộc đúng camera.
- Incident đã đóng phải có thời điểm đóng.
- Không trùng notification cho cùng incident và contact.

Việc kiểm tra contact cùng địa điểm được thực hiện trong
hàm notification giả lập hiện có.

Trigger source_group không tự nhận biết ảnh cùng video;
thông tin nhóm nguồn phải được cung cấp đúng từ bên nhập dữ liệu.

## 8. Trạng thái theo phase — phần CSDL

| Phase | Trạng thái | Nội dung |
|---|---|---|
| 1 — Thiết kế và tạo CSDL | HOÀN THÀNH | Schema v1, CLI demo và 8 tests đã chạy trên Windows |
| 2 — Hoàn thiện tài liệu thiết kế | ĐANG THỰC HIỆN | Đã cung cấp mã ERD; cần rà soát từ điển dữ liệu và đồng bộ tài liệu |
| 3 — Hoàn thiện hàm truy cập dữ liệu | ĐÃ CÓ MỘT PHẦN | Có các hàm lưu dữ liệu và sự kiện; cần bổ sung theo nhu cầu tích hợp |
| 4 — Tích hợp với AI và web | CHƯA HOÀN THÀNH | Chưa xác nhận chạy chung với hai thành viên |
| 5 — Kiểm thử và bàn giao | ĐÃ CÓ TEST NỀN | 8 tests đạt; còn kiểm thử tích hợp và tài liệu bàn giao |

Không tạo thư mục phase1, phase2 hoặc bản sao PROJECT_STATE.md mới
khi chuyển phase.

## 9. Chức năng Python đã có

Lớp FireEyesDB có các chức năng:

- initialize: khởi tạo schema.
- seed_demo: tạo dữ liệu mẫu.
- record_frame: lưu frame và detections bằng transaction.
- frame_detections: đọc detections của frame.
- open_incident: mở sự kiện từ detection được chọn.
- close_incident: đóng sự kiện.
- simulate_notification: ghi thông báo giả lập.
- counts: thống kê số bản ghi.
- list_incidents: truy vấn danh sách sự kiện.

open_incident nhận quyết định từ bên gọi.
Phần CSDL không tự suy luận rằng một detection là cháy thật.

Chưa triển khai đầy đủ:
- Các hàm thêm/sửa địa điểm, camera, contact và model cho tích hợp.
- Các truy vấn lọc, phân trang và thống kê theo nhu cầu web.
- Cập nhật kết quả gửi từ dịch vụ thông báo thật.
- Lịch sử nhiều lần thử gửi thông báo.

## 10. Kiểm chứng đã chạy trên Windows

Các lệnh người dùng đã chạy thành công:

    .\.venv\Scripts\python.exe main.py init
    .\.venv\Scripts\python.exe main.py demo
    .\.venv\Scripts\python.exe main.py stats
    .\.venv\Scripts\python.exe -m unittest discover -s tests -v

Kết quả:

- Khởi tạo schema thành công.
- Demo chạy thành công.
- 8/8 tests đạt.
- Đã chạy lại tests thành công sau khi chuyển cấu trúc mã nguồn.

Phạm vi kiểm thử:

- Persistence và seed lặp.
- Transaction và khóa ngoại.
- Retry và payload xung đột.
- Nhãn, bounding box không hợp lệ và NaN.
- Frame không có phát hiện và timestamp có múi giờ.
- Incident đóng/mở và chống trùng.
- Notification giả lập, chống trùng và kiểm tra địa điểm.
- Dataset trùng hash và source_group ở nhiều split.

Thống kê DB gần nhất được cung cấp:

| Bảng | Số bản ghi |
|---|---:|
| locations | 1 |
| cameras | 1 |
| contacts | 1 |
| dataset_versions | 1 |
| dataset_samples | 0 |
| annotations | 0 |
| model_versions | 1 |
| frames | 1 |
| detections | 1 |
| incidents | 1 |
| notifications | 1 |

Demo dùng model DEMO-NO-AI và dự đoán tổng hợp.
Không có YOLO, SMS hoặc cuộc gọi thật được thực thi.

## 11. Cấu trúc file hiện tại

### Phần CSDL

- CSDL/__init__.py
- CSDL/models/__init__.py
- CSDL/models/database.py
- CSDL/models/schema.sql
- CSDL/controllers/__init__.py
- CSDL/controllers/app_controller.py
- CSDL/tools/__init__.py
- CSDL/tools/check_labels.py
- main.py
- tests/test_database.py

### Tài liệu

- README.md
- docs/ROADMAP.md
- docs/DATASET.md
- docs/DATABASE_DESIGN.md
- PROJECT_STATE.md

Mã sơ đồ đã được cung cấp trong chat để lưu tại:
- docs/ERD.puml
- docs/CLASS_DIAGRAM.puml

Chưa xác nhận người dùng đã lưu hoặc xuất hình các sơ đồ.

### Giao diện demo đã cung cấp trước đây

- FE/__init__.py
- FE/views/__init__.py
- FE/views/main_view.py

Đây là giao diện Tkinter demo.
Không tiếp tục phát triển UI trong phạm vi cá nhân.
Chưa xóa FE vì main.py có thể vẫn tham chiếu đến giao diện này.

Class Diagram MVC trước đây mô tả phần demo đã cung cấp.
Khi lập báo cáo cá nhân, tập trung ERD và lớp truy cập CSDL.

### Dữ liệu

- data/fireeyes.db
- datasets/raw/dfire/
- datasets/prepared/dfire_v1/
- datasets/reports/

Không xóa dữ liệu khi dọn các thư mục code phase cũ.

## 12. Dataset đã hỗ trợ — bàn giao cho thành viên AI

Nguồn D-Fire:

https://github.com/gaia-solutions-on-demand/DFireDataset

Dataset gốc đã tải:

- Train: 17.221 ảnh.
- Test: 4.306 ảnh.
- Tổng: 21.527 ảnh.

Bản prepared:

- Train: 16.979 ảnh.
- Test: 4.254 ảnh.
- Tổng: 21.233 ảnh.
- 294 ảnh không đưa vào prepared, cần xem xét.
- 46 bounding box đã được cắt về biên ảnh.

Kết quả kiểm tra bản prepared:

- Lỗi định dạng nhãn: 0.
- Giải mã thành công: 21.233 ảnh.
- Ảnh lỗi giải mã: 0.
- Nhóm file trùng chính xác theo SHA-256: 0.
- Nhóm trùng chính xác giữa train và test: 0.

Báo cáo:

- datasets/prepared/dfire_v1/preparation_report.json
- datasets/reports/label_audit.json
- datasets/reports/prepared_label_audit.json
- datasets/reports/image_audit.json

Các việc chưa hoàn thành, chuyển cho thành viên AI:

- Xác minh mapping class_id nguồn.
- Xem lại ảnh bị loại và bounding box đã cắt.
- Kiểm tra ảnh gần giống nhau và rò rỉ theo video/cảnh.
- Tạo validation từ train.
- Huấn luyện và đánh giá mô hình.

Test prepared khác test gốc; cần ghi rõ khi báo cáo kết quả AI.
Dataset chưa được nhập metadata vào CSDL.
Bản prepared chưa được coi là đã xác minh đầy đủ.

## 13. Thỏa thuận tích hợp cần chốt với nhóm

### Với thành viên AI

Thống nhất:

- Camera và model phải được đăng ký trước khi lưu kết quả.
- Quy ước class_id nội bộ.
- Bounding box chuẩn hóa xc, yc, w, h.
- Confidence trong khoảng 0 đến 1.
- Thời điểm ghi nhận có múi giờ.
- request_id dùng để chống lưu lặp.
- Cách cung cấp đường dẫn ảnh bằng chứng.
- Bộ phận nào quyết định mở hoặc đóng incident.

Phần CSDL lưu dữ liệu đã được kiểm tra.
Phần AI chịu trách nhiệm tạo dự đoán và logic nhận diện.

### Với thành viên web

Thống nhất nhu cầu truy vấn:

- Danh sách địa điểm và camera.
- Danh sách sự kiện cảnh báo.
- Chi tiết sự kiện và detection kích hoạt.
- Thời điểm, vị trí và ảnh bằng chứng.
- Trạng thái xử lý sự kiện.
- Lịch sử thông báo.
- Bộ lọc, phân trang và thống kê cần dùng.

### Cách kết nối

- Nếu backend dùng Python trong cùng môi trường phù hợp:
  có thể gọi lớp FireEyesDB.
- Nếu giao tiếp giữa các tiến trình hoặc máy khác nhau:
  cần thống nhất lớp API của backend.
- Trình duyệt không truy cập trực tiếp file SQLite.
- Chưa triển khai hoặc chốt API HTTP trong phần hiện tại.

## 14. Việc tiếp theo

1. Rà soát ERD đúng schema v1.
2. Hoàn thiện từ điển dữ liệu trong docs/DATABASE_DESIGN.md.
3. Đồng bộ README và ROADMAP với phạm vi CSDL.
4. Chốt cấu trúc dữ liệu đầu vào/đầu ra cùng hai thành viên.
5. Bổ sung các hàm truy cập dữ liệu còn thiếu.
6. Kiểm thử bằng dữ liệu giả lập và dữ liệu tích hợp.
7. Bàn giao schema, mã Python, ERD và hướng dẫn sử dụng.

Không cần tiếp tục huấn luyện YOLO hoặc làm giao diện
để hoàn thành phần việc CSDL.

## 15. Quy tắc tiếp tục

- Đọc file trạng thái và mã liên quan trước khi sửa.
- Chỉ mở rộng công việc thuộc phần CSDL hoặc hỗ trợ tích hợp đã chốt.
- Giữ một PROJECT_STATE.md tại thư mục gốc.
- Chỉnh tiếp file theo chức năng, không tạo file theo từng phase.
- Cung cấp code trực tiếp trong chat và ghi rõ đường dẫn cần sửa.
- Không viết lại phần đã chạy tốt nếu không có lý do cụ thể.
- Không đổi schema âm thầm hoặc xóa CSDL để né migration.
- Phân biệt mã đã cung cấp với kết quả người dùng đã kiểm chứng.
- Không đánh dấu tích hợp hoàn thành khi chưa chạy cùng AI và web.
- Không coi demo giả lập là kết quả nhận diện thật.
- Sau mỗi phase, cập nhật file này với thay đổi, kiểm chứng,
  giới hạn và bước tiếp theo.