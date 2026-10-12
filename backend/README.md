# FireEyes backend

Backend Person 2 dùng SQLite làm CSDL SQL cục bộ và FastAPI làm HTTP API. Không
cần cài hay khởi động MySQL/PostgreSQL. SQLite là thư viện đi kèm Python; API
tạo file DB và schema khi khởi động lần đầu.

## 1. Cài môi trường

Chạy lệnh từ thư mục gốc `fire_detection_ai`, với Python 3.12:

```bash
python -m venv .venv
source .venv/bin/activate       # macOS/Linux
# .\.venv\Scripts\Activate.ps1  # Windows PowerShell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 2. Khởi tạo SQL database

Mặc định, DB được tạo tại `backend/data/fireeyes.db`. Không cần tạo file trước:

```bash
python -m backend.main init
```

File `.db`, WAL và thư mục dữ liệu đã được Git ignore. Có thể chọn đường dẫn
khác bằng biến môi trường trước khi chạy API:

```bash
export FIREEYES_DB_PATH="$PWD/backend/data/fireeyes.db"  # macOS/Linux
# PowerShell: $env:FIREEYES_DB_PATH = "$PWD\backend\data\fireeyes.db"
```

Không đặt file SQLite trong thư mục đồng bộ mạng hoặc để nhiều máy ghi trực
tiếp cùng lúc. Với ứng dụng chạy cục bộ, SQLite không cần user/password, port
hay dịch vụ CSDL riêng.

## 3. Chạy backend API

```bash
python -m uvicorn backend.api:app --host 127.0.0.1 --port 8000
```

Giữ cửa sổ terminal này mở. Mở <http://127.0.0.1:8000/> để dùng dashboard,
hoặc <http://127.0.0.1:8000/docs> để xem và thử API. Dashboard phục vụ cùng
FastAPI origin, tự làm mới dữ liệu mỗi 5 giây và không cần cài thêm package
frontend. Có thể bật dữ liệu giả lập để thử các luồng popup/acknowledge/resolve:
<http://127.0.0.1:8000/?demo=1>. Dữ liệu demo chỉ nằm trong trình duyệt và
không ghi vào SQLite/backend thật.

Trên dashboard thật, bấm **Thêm camera** để đăng ký tên camera và chọn nhà/vị
trí đã có, hoặc tạo nhà/vị trí mới kèm địa chỉ. Thao tác này ghi vào SQLite
qua `POST /api/locations` và `POST /api/cameras`; ở chế độ demo, dữ liệu chỉ
tồn tại trong phiên trình duyệt và sẽ mất khi tải lại trang. Đăng ký camera
chỉ lưu metadata, không tự mở webcam hay kết nối luồng RTSP. `source_ref` là
nhãn nội bộ; không đưa mật khẩu hoặc URL RTSP có thông tin đăng nhập vào đó.

Để thử âm thanh, bấm **Bật âm thanh** một lần sau khi mở trang; trình duyệt
chặn phát âm thanh tự động trước thao tác người dùng. Popup âm thanh chỉ phát
khi backend ghi nhận một alert mới trong lúc dashboard đang mở; alert cũ vẫn
hiện trong danh sách nhưng không phát lại mỗi lần polling.

Các endpoint:

| Method | Endpoint | Chức năng |
|---|---|---|
| GET | `/health` | Kiểm tra API |
| GET/POST | `/api/locations` | Xem/tạo địa điểm |
| GET/POST | `/api/cameras` | Xem/đăng ký camera |
| GET | `/api/cameras/{id}/status` | Xem trạng thái active/disconnected/stopped |
| PATCH | `/api/cameras/{id}/status` | Bật/tắt camera ở backend |
| POST | `/api/cameras/{id}/heartbeat` | Ghi nhận camera còn kết nối |
| GET/POST | `/api/datasets` | Xem/ghi metadata dataset |
| GET/POST | `/api/models` | Xem/đăng ký model |
| POST | `/api/frames`, `/api/detections` | Ghi frame/detections và mở alert đã xác nhận |
| GET | `/api/detections/history` | Lịch sử detections, hỗ trợ lọc camera và phân trang |
| GET | `/api/alerts` | Danh sách alert, lọc theo đã xác nhận/xem |
| GET | `/api/alerts/latest` | Alert mới nhất hoặc `null` nếu chưa có |
| GET | `/api/alerts/{id}/snapshot` | Tải ảnh snapshot của alert |
| PATCH | `/api/alerts/{id}/acknowledge` | Đánh dấu alert đã được người dùng xem |
| PATCH | `/api/alerts/{id}/resolve` | Đóng alert là `resolved` hoặc `false_alarm` |
| GET | `/api/incidents` | Tương thích ngược: danh sách incidents |
| GET | `/api/stats` | Thống kê số bản ghi |

Trạng thái camera được xác định như sau: `stopped` nếu camera bị tắt trong
backend; `active` nếu backend nhận heartbeat trong 45 giây gần nhất; nếu không
thì là `disconnected`. AI gửi heartbeat mỗi 15 giây khi đang đọc frame và đã
cấu hình cả camera ID lẫn model ID. Gửi heartbeat thủ công:

```http
POST /api/cameras/1/heartbeat
```

Bật/tắt một camera qua API:

```http
PATCH /api/cameras/1/status
Content-Type: application/json

{"enabled": false}
```

API lịch sử hỗ trợ `camera_id`, `limit` (1-200) và `offset`, ví dụ
`GET /api/detections/history?camera_id=1&limit=50&offset=0`. API alert nhận
`acknowledged=true|false`, `limit` và `offset`. Đánh dấu đã xem:

```http
PATCH /api/alerts/1/acknowledge
Content-Type: application/json

{"acknowledged_by": "Operator"}
```

Thao tác acknowledge lưu người ghi nhận và thời điểm, không đóng incident.
Đóng/xử lý alert là thao tác riêng:

```http
PATCH /api/alerts/1/resolve
Content-Type: application/json

{"status": "resolved", "note": "Fire was extinguished"}
```

`status` chỉ nhận `resolved` hoặc `false_alarm`; cần ghi chú giải quyết.
Incident đã đóng không thể được đóng lần nữa. Trạng thái acknowledged không
phải danh tính đã xác thực; backend hiện chưa có đăng nhập/ủy quyền.

## Phục vụ ảnh bằng chứng

Ảnh alert được tải qua `GET /api/alerts/{id}/snapshot`. Vì backend và AI hiện
chạy trên cùng máy, API chỉ phục vụ file nằm trong `output/screenshots` của
project; file phải có đuôi `.jpg`, `.jpeg`, `.png` hoặc `.webp`. File không tồn
tại, nằm ngoài thư mục cho phép hoặc không phải định dạng ảnh được hỗ trợ sẽ
trả `404`. Có thể cấu hình thư mục khác qua `FIREEYES_SNAPSHOT_ROOT`; chỉ trỏ
tới thư mục ảnh đáng tin cậy do ứng dụng quản lý.

Khi chuyển AI và backend sang hai máy khác nhau, đường dẫn local không dùng
được; khi đó cần upload ảnh có xác thực hoặc storage dùng chung có kiểm soát.

## 4. Đăng ký location, camera, dataset, model

Trước khi ingest prediction thật, cần có ID trong DB. Tạo theo thứ tự này trong
Swagger UI:

1. `POST /api/locations`

   ```json
   {"name": "Lab", "address": "Building A"}
   ```

   Ghi lại `id` trả về.

2. `POST /api/cameras`, thay `location_id` bằng ID vừa nhận:

   ```json
   {
     "location_id": 1,
     "name": "Camera 1",
     "source_ref": "camera-index:0"
   }
   ```

   Không ghi mật khẩu hoặc URL RTSP có credentials vào `source_ref`.

3. `POST /api/datasets`:

   ```json
   {
     "name": "D-Fire",
     "version": "local-v1",
     "source_url": "URL nguồn dataset",
     "license_name": "Điều khoản đã xác minh",
     "class_map": {"0": "fire", "1": "smoke"}
   }
   ```

   `class_map` phải phản ánh nhãn gốc đã xác minh; ví dụ D-Fire dùng 0=Fire,
   1=Smoke. Dataset bắt đầu ở trạng thái `planned`, không đánh dấu đã xác minh
   chỉ vì đã thêm metadata.

4. Đăng ký model đã train với `POST /api/models`. Lấy SHA-256 file weights:

   ```bash
   shasum -a 256 runs/detect/fire_ai/weights/best.pt
   ```

   PowerShell:

   ```powershell
   (Get-FileHash runs/detect/fire_ai/weights/best.pt -Algorithm SHA256).Hash
   ```

   Gửi body với dataset ID và hash thực tế:

   ```json
   {
     "name": "fire-model-v1",
     "dataset_id": 1,
     "weights_path": "runs/detect/fire_ai/weights/best.pt",
     "weights_sha256": "THAY_BANG_64_KY_TU_SHA256"
   }
   ```

Ghi lại location, camera, dataset và model IDs. Có thể gọi `GET /api/cameras`,
`GET /api/datasets`, `GET /api/models` để xem các bản ghi đã tạo. Tên trùng sẽ
trả HTTP 409; hãy dùng ID hiện hữu thay vì tạo lại.

## 5. Gửi frame từ AI

`POST /api/frames` cần camera/model ID đã đăng ký, request ID duy nhất theo
camera, timestamp có timezone và các box đã chuẩn hóa:

```json
{
  "camera_id": 1,
  "model_id": 1,
  "request_id": "camera-1:session-1:frame-120",
  "captured_at": "2026-10-11T09:30:00+07:00",
  "confirmed_classes": ["fire"],
  "snapshot_path": null,
  "detections": [
    {
      "class_id": 1,
      "confidence": 0.87,
      "xc": 0.50,
      "yc": 0.45,
      "w": 0.20,
      "h": 0.30
    }
  ]
}
```

Box coordinates phải ở khoảng 0..1; width/height lớn hơn 0. Gửi lại cùng
request ID và payload sẽ trả lại cùng frame ID mà không ghi lặp; dùng lại ID
với payload khác trả HTTP 409. Payload sai trả HTTP 422. Timestamp không có
timezone bị từ chối.

Mapping lưu trong CSDL là `0=smoke`, `1=fire`, trong khi nhãn YOLO D-Fire là
`0=Fire`, `1=Smoke`. Adapter phải đổi ID theo tên lớp trước khi gửi:

```python
fireeyes_class_id = 1 if class_name.strip().lower() == "fire" else 0
```

Chỉ gửi `confirmed_classes` cho lớp đã được xác nhận qua nhiều frame. Mỗi lớp
được xác nhận phải có ít nhất một box cùng lớp trong `detections`. Backend sẽ
lưu frame/box, mở incident theo box confidence cao nhất và trả `incident_id`.
`GET /api/incidents` trả trạng thái, lớp cảnh báo, confidence và đường dẫn
local của ảnh bằng chứng để app poll danh sách cảnh báo. API hiện chưa phục vụ
file ảnh qua HTTP; app chỉ mở được ảnh nếu chạy trên cùng máy và có quyền đọc
đường dẫn đó.

`weights_path` hiện được lưu làm metadata; backend chưa tự mở hoặc xác minh file
weights qua đường dẫn đó. Tính và gửi SHA-256 chính xác.

## 6. Chạy AI gửi cảnh báo vào backend

Giữ Uvicorn đang chạy ở Terminal 1. Sau khi đã tạo và ghi lại camera/model ID,
mở Terminal 2, vào thư mục gốc project, kích hoạt cùng `.venv`, rồi chạy:

```bash
python -m detection.webcam \
  --source 0 \
  --model models/best.pt \
  --backend-camera-id 1 \
  --backend-model-id 1
```

Thay `1` bằng ID trả về từ `POST /api/cameras` và `POST /api/models`. Để xử lý
video thay webcam, đổi `--source 0` thành đường dẫn video, ví dụ
`--source D-Fire/test/example.mp4`. Cảnh báo được lưu local vào JSON như trước,
đồng thời gửi frame xác nhận và box lên API. Nếu backend từ chối request hoặc
không kết nối được, terminal báo lỗi; bản ghi local vẫn được giữ. Không cần
chạy hai lần `pip install`; cả hai Terminal dùng cùng `.venv`.

Từ app UI, gọi/poll `GET http://127.0.0.1:8000/api/alerts` để đọc cảnh báo,
`GET /api/alerts/latest` để lấy alert mới nhất, và PATCH endpoint acknowledge
khi người dùng đã xem. Sau khi xử lý, gọi PATCH
`/api/alerts/{id}/resolve` với `status` và `note`. Lịch sử box có tại
`GET /api/detections/history`. Camera có thể theo dõi qua
`GET /api/cameras/{id}/status`; tải ảnh bằng chứng qua
`GET /api/alerts/{id}/snapshot`. Chưa có push/WebSocket hoặc UI frontend.

## 7. Kiểm thử và giới hạn hiện tại

```bash
python -m unittest discover -s backend/tests -v
python -m unittest detection.test_fire_logic -v
python -m backend.main stats
python -m backend.main incidents
```

`python -m backend.main demo` và `seed_demo()` chỉ tạo dữ liệu giả lập
`DEMO-NO-AI`, không phải camera/model thật. Backend nhận cảnh báo từ vòng lặp
webcam/video, lưu lịch sử, quản lý heartbeat camera và cho phép app acknowledge
alert. Chưa gửi SMS/cuộc gọi/email, chưa có đăng nhập/xác thực. Chỉ bind
`127.0.0.1`; không mở API ra mạng
công cộng hoặc mạng dùng chung.
