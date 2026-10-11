# Kế hoạch theo phase

## Phân công nhóm 3 người

| Thành viên | Phụ trách | Sản phẩm bàn giao |
|---|---|---|
| Bạn | Thiết kế CSDL, metadata dataset, API Python lưu/truy vấn, kiểm tra tính toàn vẹn | ERD, schema, database.py, báo cáo dữ liệu, test |
| Thành viên 2 | Kiểm tra nhãn, huấn luyện YOLOv8n, đánh giá AI | dataset đã kiểm tra, best.pt, metrics, adapter dự đoán |
| Thành viên 3 | Đọc video/camera, giao diện và dịch vụ thông báo | màn hình demo, lịch sử cảnh báo, cấu hình người nhận |

Cả nhóm chốt mapping nhãn trước khi bắt đầu. Chọn YOLOv8n làm baseline theo phạm vi
đề tài; chỉ so sánh YOLOv10 khi đã có baseline và còn thời gian. Chưa cần triển khai
nhiều camera hoặc cuộc gọi thật để hoàn thành demo nền tảng.

## Phase và tiêu chí hoàn thành

| Phase | Công việc | Điều kiện hoàn thành | Trạng thái |
|---|---|---|---|
| 1 — CSDL nền tảng | Đối tượng, ERD, schema, Python lưu frame/detection/incident, demo và test | Tạo được DB, demo lưu/truy vấn được, test đạt | Đã hoàn thành trong môi trường tạo mã |
| 2 — Dataset thật | Tải D-Fire, xác nhận mapping nguồn, kiểm tra ảnh/nhãn, chống trùng, chia split và nhập metadata | Có file ảnh thật, manifest và báo cáo số lượng thực tế; không rò rỉ nhóm nguồn đã biết | Chưa thực hiện |
| 3 — Huấn luyện | YOLOv8n, lưu cấu hình, seed, phiên bản gói, checkpoint và metric validation | Có best.pt, đường dẫn/hash, kết quả validation tái hiện được | Chưa thực hiện |
| 4 — Tích hợp camera và CSDL | Video trước, webcam/RTSP sau; chuyển box; luật cảnh báo theo thời gian | Dự đoán thật được lưu, không lưu/gửi lặp sự kiện liên tục, xử lý mất camera | Chưa thực hiện |
| 5 — Giao diện và thông báo | Xem camera, lịch sử, ảnh bằng chứng, đóng/cảnh báo sai; tích hợp một kênh trước | Demo đủ luồng, phân biệt simulated/sent/failed; cấu hình bí mật ngoài code | Chưa thực hiện |
| 6 — Đánh giá và báo cáo | Đánh giá tập test, video mới; đo tốc độ và false alarms; chuẩn bị slide | Có bảng kết quả thật, video demo, giới hạn và hướng phát triển | Chưa thực hiện |

## Quy trình kết thúc mỗi phase

1. Chạy các kiểm tra thuộc phase đó, ghi rõ lệnh và kết quả.
2. Liệt kê các file đã tạo/sửa, schema/version và quy ước tích hợp mới.
3. Cập nhật **`PROJECT_STATE.md` ở thư mục gốc** làm nguồn trạng thái hiện tại.
4. Lưu bản chụp vào `phaseN/PROJECT_STATE.md` để giữ lịch sử từng phase.
5. Tách rõ: đã kiểm thử trong môi trường tạo mã / người dùng đã chạy trên máy.
6. Chỉ ghi hoàn thành khi tiêu chí đạt; ghi blocker và phần còn lại nếu chưa đạt.

## Phạm vi cảnh báo dự kiến ở Phase 4

Tham số khởi đầu để thử nghiệm: xét điểm confidence theo lớp, số frame dương tính
trong cửa sổ thời gian, duy trì cùng camera và gom thành một incident.
Không chốt 0.5 hay 0.7 thành ngưỡng đúng trước khi đo validation.
Luật cần xử lý camera mất kết nối, khoảng thời gian giữa frame, reset khi gián đoạn,
và cooldown sau khi đóng sự kiện. Một box confidence cao chưa đủ chứng minh cháy.

## Chỉ tiêu báo cáo ở Phase 6

- Precision/recall và mAP50, mAP50–95, tách lớp fire và smoke.
- False alarms/giờ trên video không cháy; số sự kiện bỏ sót trên video có cháy/khói.
- Độ trễ từ mốc khói/lửa nhìn thấy trong video đến lúc cảnh báo.
- FPS và độ trễ xử lý trên phần cứng nhóm sử dụng, kèm độ phân giải đầu vào.
- Các tình huống khó: hơi nước, mây/sương, đèn vàng/đỏ, hoàng hôn, khói nhỏ, ban đêm.
- Tập test giữ nguyên đến đánh giá cuối, không dùng để chọn ngưỡng hoặc checkpoint.
