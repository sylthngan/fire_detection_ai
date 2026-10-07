# FireEyes — Demo giữa kỳ môn Trí tuệ nhân tạo

Dành cho nhóm 3 sinh viên năm 3, Trường Đại học CNTT & TT Việt–Hàn.
Tên dùng thống nhất: **FireEyes**. Bạn phụ trách thiết kế CSDL và lớp truy cập dữ liệu bằng Python.

## Bản bàn giao này

Hoàn thành **Phase 1: thiết kế và xây dựng nền tảng cơ sở dữ liệu**.
Đã chọn nguồn dataset thật và viết kế hoạch chuẩn bị dữ liệu. Chưa tải ảnh D-Fire,
chưa huấn luyện YOLO, chưa kết nối camera, chưa gửi SMS/cuộc gọi.
`main.py demo` dùng một dự đoán giả lập, được đánh dấu `DEMO-NO-AI`.

## Chạy trên Windows

Giải nén, mở terminal ngay trong thư mục `FireEyes` chứa `main.py`.
Dùng Python 3.10 trở lên; code đã kiểm thử với Python 3.12.14.
Phase 1 chỉ dùng thư viện chuẩn, không cần `pip install`, MySQL hay GPU.

```powershell
python --version
python main.py init
python main.py demo
python main.py stats
python main.py incidents
python -m unittest discover -s tests -v
```

Nếu Windows chỉ nhận lệnh `py`, thay `python` bằng `py`.
File CSDL sẽ được tạo tại `data/fireeyes.db`; các lệnh chạy lại không xóa dữ liệu.
Demo chạy lại trên CSDL chưa đóng sự kiện sẽ dùng lại khung hình/sự kiện/thông báo cũ.
Nếu đã đóng sự kiện, gọi demo tiếp sẽ có thể mở sự kiện demo mới.

Kết quả lần demo đầu: 1 địa điểm, camera, liên hệ, nguồn dataset dự kiến,
model giả lập, khung hình, detection, incident và notification giả lập;
0 ảnh dataset và 0 nhãn huấn luyện.

## Đọc theo thứ tự

1. `docs/ROADMAP.md`: phase, phân công, điều kiện hoàn thành.
2. `docs/DATASET.md`: nguồn dữ liệu cụ thể, nhãn, quy trình tải và kiểm tra.
3. `docs/DATABASE_DESIGN.md`: ERD, từ điển dữ liệu, quy tắc lưu trữ.
4. `phase1/schema.sql`: SQL tạo bảng, khóa ngoại, ràng buộc, index.
5. `phase1/database.py`: API Python cho hai bạn còn lại tích hợp.
6. `main.py`: ví dụ chạy từ đầu đến cuối.
7. `PROJECT_STATE.md`: trạng thái hiện tại; luôn cập nhật khi hoàn thành phase.

## Giao tiếp với bạn làm AI

Sau khi có mô hình đã huấn luyện và đăng ký model thật ở Phase 3–4:

```python
from phase1.database import FireEyesDB

db = FireEyesDB('data/fireeyes.db')
db.initialize()
# camera_id/model_id phải tồn tại. Ví dụ này minh họa hợp đồng dữ liệu.
frame_id = db.record_frame(
    camera_id=1,
    model_id=1,
    request_id='session-A:frame-120',
    captured_at='2026-09-30T09:30:00+07:00',
    snapshot_path=None,
    detections=[{
        'class_id': 0,          # FireEyes: smoke
        'confidence': 0.87,     # điểm của model, không phải độ chính xác toàn hệ thống
        'xc': 0.50, 'yc': 0.45,
        'w': 0.20, 'h': 0.30,  # chuẩn hóa theo kích thước ảnh
    }],
)
```

Một frame có thể có nhiều box hoặc danh sách rỗng. `request_id` phải duy nhất
theo camera, gồm ID phiên chạy và số frame. Retry giữ nguyên toàn bộ payload;
dùng lại ID với payload khác sẽ bị từ chối. Adapter YOLO ở Phase 4 phải đối chiếu
`model.names` rồi chuyển class ID về mapping FireEyes.

`open_incident()` chỉ lưu quyết định đã có; nó chưa triển khai luật xét nhiều frame.
`simulate_notification()` chỉ ghi `simulated`, không gọi dịch vụ bên ngoài.

## Giới hạn demo

SQLite phù hợp một ứng dụng demo cục bộ. Mỗi thao tác mở kết nối riêng, bật khóa ngoại,
có transaction và thời gian chờ khóa. Chưa có đăng nhập/phân quyền hay API mạng.
Ảnh, video và trọng số lưu ngoài CSDL; CSDL giữ đường dẫn và metadata.
Chưa có số đo độ chính xác, độ trễ hoặc khả năng phát hiện cháy sớm trên camera thực.
Các số liệu đánh giá phải được đo ở Phase 6 trước khi đưa vào báo cáo.
