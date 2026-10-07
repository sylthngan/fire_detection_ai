# Dataset rõ ràng cho FireEyes

Ngày kiểm tra nguồn: 30/09/2026 (Asia/Bangkok).

## 1. Nguồn chính: D-Fire

- Chủ nguồn: GAIA — Gaia, solutions on demand.
- Trang gốc và liên kết tải: https://github.com/gaia-solutions-on-demand/DFireDataset
- Tại phần Download links, chọn **D-Fire dataset (only images and labels)**.
- Nếu dùng phân chia do tác giả cung cấp, chọn **Training, validation and test sets**.
- Trang gốc cũng liên kết bản Kaggle: https://www.kaggle.com/datasets/sayedgamal99/smoke-fire-detection-yolo
- Giấy phép nguồn công bố: **CC0 1.0**, xem https://github.com/gaia-solutions-on-demand/DFireDataset/blob/master/LICENSE
- Bài nghiên cứu nguồn đề nghị trích dẫn: *An automatic fire detection system based on deep convolutional neural networks for low-power, resource-constrained devices*, Venâncio, Lisboa và Barbosa, 2022.

| Nhóm ảnh theo công bố | Số ảnh |
|---|---:|
| Chỉ lửa | 1.164 |
| Chỉ khói | 5.867 |
| Cả lửa và khói | 4.658 |
| Không có cả hai | 9.838 |
| **Tổng cộng từ bảng công bố** | **21.527** |

Nguồn công bố nhãn bounding box định dạng YOLO. Đây là số liệu của nguồn,
**chưa phải số lượng đã tải/kiểm đếm trong dự án**. Bản bàn giao Phase 1 chưa chứa ảnh thật.
Không sử dụng file demo trong CSDL làm dataset huấn luyện.

## 2. Đối tượng AI

| class_id chuẩn nội bộ FireEyes | Nhãn | Ý nghĩa |
|---|---|---|
| 0 | smoke | Vùng khói nhìn thấy được |
| 1 | fire | Vùng ngọn lửa nhìn thấy được |

Đây là mapping do dự án quy định. **Phải đọc YAML/classes của bản tải về và đối chiếu
trực quan để xác nhận mapping nguồn trước khi nhập.** Nếu nguồn ngược thứ tự thì chuyển
ID khi chuẩn hóa; không chỉ đổi tên trong YAML. Khi inference, kiểm tra `model.names`.

Ảnh không có lửa/khói là ảnh âm tính: file nhãn `.txt` rỗng, không thêm lớp `normal`.
Khói và lửa có thể đồng thời xuất hiện, mỗi vùng có một dòng nhãn.

Ví dụ định dạng nhãn (số liệu minh họa, không phải nhãn trích từ D-Fire):

```text
0 0.50 0.45 0.20 0.30
1 0.65 0.70 0.10 0.15
```

Các cột là `class_id x_center y_center width height`; tọa độ được chuẩn hóa 0–1.
Với ảnh W×H và box pixel `(xmin,ymin,xmax,ymax)`:

```text
xc = (xmin + xmax) / (2 * W)
yc = (ymin + ymax) / (2 * H)
w  = (xmax - xmin) / W
h  = (ymax - ymin) / H
```

Tài liệu định dạng chính thức: https://docs.ultralytics.com/datasets/detect/

## 3. Quy trình Phase 2

1. Tải từ liên kết trang gốc; ghi URL, ngày tải, tên archive và SHA-256 archive.
2. Giữ nguyên bản gốc ở `datasets/raw/dfire/`; không sửa đè.
3. Đếm ảnh thực tế, kiểm tra ảnh đọc được và ghép ảnh–nhãn theo tên.
4. Kiểm tra mỗi dòng có đúng 5 cột; lớp hợp lệ; số hữu hạn; box nằm trong ảnh.
   Nhãn thiếu phải được xem xét, không tự coi mọi nhãn thiếu là ảnh âm tính.
5. Hiển thị box trên mẫu ảnh từ cả hai lớp và ảnh âm tính để xác nhận mapping.
6. So SHA-256 để tìm bản sao chính xác; xem ảnh gần giống/khung hình liền kề bằng
   perceptual hash hoặc kiểm tra thủ công. Hash chính xác không bắt được ảnh resize/crop.
7. Giữ ảnh từ cùng video/cảnh/camera hoặc nhóm ảnh gần trùng trong cùng một split.
   `source_group` phải dựa trên nguồn có căn cứ. Nếu thiếu metadata, ghi rõ chưa biết
   và kiểm tra các cụm ảnh gần giống; không tuyên bố đã loại hết rò rỉ dữ liệu.
8. Nếu có split chính thức, ưu tiên bảo toàn và kiểm tra trùng giữa các split.
   Nếu tự chia, dùng nhóm nguồn, seed=42, mục tiêu 70/15/15 (train/val/test).
   Đây là tỷ lệ mục tiêu; sau chia theo nhóm, ghi lại số đếm thực tế.
9. Augmentation chỉ áp dụng train sau chia. Giữ test độc lập đến đánh giá cuối.
10. Xuất manifest, nhập `dataset_samples` + `annotations` bằng transaction, lưu
    báo cáo lỗi và chuyển `dataset_versions.status` sang `verified` khi đã kiểm tra.

Nếu GPU/thời gian hạn chế, tạo subset có version riêng, dự kiến 3.000–5.000 ảnh;
giữ đủ fire-only, smoke-only, both, negative. Không ghi số mục tiêu thành kết quả thật.

## 4. Cấu trúc đầu ra dự kiến

Các thư mục `images/train`, `images/val`, `images/test` và `labels/train`,
`labels/val`, `labels/test` nằm dưới `datasets/fireeyes_v1/`.
Manifest ở `datasets/fireeyes_v1/manifest.csv`.

Ví dụ YAML sau khi chuẩn hóa (tạo ở Phase 2; đường dẫn sửa theo máy chạy):

```yaml
path: D:/FireEyes/datasets/fireeyes_v1
train: images/train
val: images/val
test: images/test
names:
  0: smoke
  1: fire
```

Các cột manifest cần có:

| Cột | Ý nghĩa |
|---|---|
| image_path, label_path | Đường dẫn tương đối từ thư mục dataset |
| sha256 | Hash nội dung ảnh để tìm trùng chính xác |
| source_group | Nhóm nguồn/cảnh/video dùng khi chia tập |
| split | train, val hoặc test |
| width, height | Kích thước ảnh để kiểm tra/hiển thị |
| fire_count, smoke_count | Số box mỗi lớp |
| source_url | Nguồn gốc cụ thể nếu có |

`width`, `height`, số box và `source_url` theo ảnh lưu trong manifest Phase 2;
CSDL Phase 1 lưu metadata cốt lõi, source URL chung tại dataset_versions.

## 5. Dữ liệu bổ sung cho camera

Sau baseline, bổ sung video sẵn có được phép sử dụng hoặc video nhóm tự quay
an toàn để kiểm tra miền dữ liệu camera. Dùng cảnh thường có hơi nước, mây, đèn,
phản chiếu và hoàng hôn làm ví dụ khó; không tạo cháy thật để lấy dữ liệu.
Đánh dấu nguồn, camera/cảnh, ngày thu và quyền sử dụng; tách tập theo video.
Ảnh D-Fire đa dạng không tự chứng minh mô hình hoạt động tốt trên camera của nhóm.

## 6. Phân biệt dữ liệu

- Dataset: ảnh + nhãn người gán, phục vụ train/val/test.
- Dữ liệu chạy ứng dụng: camera, frame, dự đoán, sự kiện và trạng thái gửi.
- Nhãn `annotations` là ground truth; `detections` là dự đoán có confidence.
- Ảnh/video/trọng số để ngoài SQL. DB giữ đường dẫn; hash dùng cho truy vết phiên bản.
