# Sky WebApp - AI Detection System

## Tính năng mới: Phát hiện người qua AI

Hệ thống đã được tích hợp AI detection để phát hiện và đếm số lượng người trong 2 khu vực:
- **Earth Person** (Người trên bờ) 🏃
- **Sea Person** (Người trên biển) 🏊

### Các tính năng chính:

#### 1. **Real-time Detection trên Video Stream**
- Model ONNX (YOLOv8) chạy trực tiếp trên drone
- Vẽ bounding boxes và labels lên video stream
- Hiển thị số lượng người phát hiện được real-time
- Chạy detection mỗi 3 frames để tiết kiệm CPU

#### 2. **Gửi Dữ liệu Detection qua WebSocket**
- Drone tự động gửi dữ liệu detection về server mỗi 2 giây
- Server broadcast dữ liệu đến tất cả web clients
- Hiển thị real-time trên dashboard:
  - Số lượng Earth Person
  - Số lượng Sea Person
  - Tổng số người

#### 3. **Lưu Báo cáo định kỳ với Hình ảnh**
- Tự động chụp snapshot và lưu vào database
- **Có thể điều chỉnh interval từ UI (1-30 phút)**
- **Có thể bật/tắt chế độ tự động chụp**
- Báo cáo bao gồm:
  - Hình ảnh snapshot (Base64 encoded)
  - Số lượng người phát hiện được
  - Timestamp
  - Device ID và tên
- Database: SQLite (`detection_data.db`)
- Mặc định: **1 phút** (có thể chỉnh từ UI)

#### 4. **Xem Báo cáo lịch sử**
- Dashboard hiển thị danh sách báo cáo đã lưu
- Click vào báo cáo để xem chi tiết với hình ảnh đầy đủ
- API endpoints để lấy báo cáo và thống kê

#### 5. **Điều khiển từ UI** ⭐ MỚI
- **Toggle bật/tắt chụp tự động**: Checkbox "Tự động chụp"
- **Chọn interval**: Dropdown từ 1-30 phút
  - 1 phút (mặc định)
  - 2 phút
  - 3 phút
  - 5 phút
  - 10 phút
  - 15 phút
  - 30 phút
- **Chụp ngay**: Button "Chụp ngay" để capture on-demand
- Cấu hình được lưu và áp dụng real-time

### Kiến trúc hệ thống:

```
┌─────────────────────────────────────────────────────────────┐
│                        DRONE CLIENT                          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  video_stream.py                                      │   │
│  │  - Capture frames từ camera                          │   │
│  │  - Run ONNX inference                                │   │
│  │  - Parse output (bounding boxes, classes, scores)    │   │
│  │  - Draw boxes lên frame                              │   │
│  │  - Đếm số lượng earth_person & sea_person           │   │
│  └──────────────────────────────────────────────────────┘   │
│                          ↓                                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  main.py                                              │   │
│  │  - Send detection_data qua WebSocket (mỗi 2s)       │   │
│  │  - Periodic report task (mỗi 5 phút)                │   │
│  │  - Capture snapshot + detection data                 │   │
│  │  - Send detection_snapshot với image (Base64)       │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            ↓ Socket.IO
┌─────────────────────────────────────────────────────────────┐
│                         SERVER                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  detection_controller.py                              │   │
│  │  - Nhận detection_data events                        │   │
│  │  - Broadcast đến web clients                         │   │
│  │  - Nhận detection_snapshot events                    │   │
│  │  - Lưu vào database với hình ảnh                     │   │
│  └──────────────────────────────────────────────────────┘   │
│                          ↓                                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  detection_model.py                                   │   │
│  │  - DetectionData: Real-time data model               │   │
│  │  - DetectionReport: Database model                   │   │
│  │  - SQLite storage với image_data (Base64)           │   │
│  │  - API methods: get_recent_reports, statistics      │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            ↓ Socket.IO + HTTP API
┌─────────────────────────────────────────────────────────────┐
│                      WEB DASHBOARD                           │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  detection_client.js                                  │   │
│  │  - Listen detection_update events                    │   │
│  │  - Update real-time counts display                   │   │
│  │  - Load reports từ API                               │   │
│  │  - Display reports với thumbnails                    │   │
│  │  - Show modal với full image                         │   │
│  └──────────────────────────────────────────────────────┘   │
│                          ↓                                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  dashboard.html                                       │   │
│  │  - Video stream panel                                │   │
│  │  - AI Detection panel                                │   │
│  │  - Real-time stats: Earth/Sea/Total                  │   │
│  │  - Reports list với thumbnails                       │   │
│  │  - Request on-demand report button                   │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Files đã tạo/sửa:

#### Drone Client:
1. **`drone-app/video_stream.py`** - ✅ UPDATED
   - Thêm CLASS_NAMES và CLASS_COLORS
   - Parse YOLOv8 output
   - Vẽ bounding boxes
   - Đếm detections
   - Callback để gửi data

2. **`drone-app/main.py`** - ✅ UPDATED
   - Thêm send_detection_data callback
   - Throttle emissions (mỗi 2s)
   - Start periodic_report_task
   - Handle request_detection_report event

3. **`drone-app/detection_utils.py`** - ✅ NEW
   - periodic_report_task (mỗi 5 phút)
   - on_demand_report
   - Capture frame và encode Base64
   - Send detection_snapshot event

#### Server:
4. **`controller/detection_controller.py`** - ✅ NEW
   - Handle detection_data event
   - Handle detection_snapshot event
   - Broadcast detection_update
   - API endpoints:
     - GET /api/detection/latest
     - GET /api/detection/history
     - GET /api/detection/reports
     - GET /api/detection/report/<id>
     - GET /api/detection/stats

5. **`model/detection_model.py`** - ✅ NEW
   - DetectionData class (real-time)
   - DetectionReport class (database)
   - SQLite schema
   - CRUD operations
   - Statistics methods

6. **`app.py`** - ✅ UPDATED
   - Register detection_blueprint

#### Web Frontend:
7. **`static/js/detection_client.js`** - ✅ NEW
   - DetectionClient class
   - Handle detection_update events
   - Load reports từ API
   - Create detection cards
   - Create report items
   - Show report modal
   - Request on-demand reports

8. **`static/css/style.css`** - ✅ UPDATED
   - Detection card styles
   - Report item styles
   - Modal styles
   - Stat box styles
   - Animations

9. **`templates/dashboard.html`** - ✅ UPDATED
   - AI Detection panel
   - Real-time stats display
   - Reports list
   - Request report button
   - Initialize DetectionClient

10. **`templates/layout.html`** - ✅ UPDATED
    - Include detection_client.js

### API Endpoints:

```
GET /api/detection/latest
- Trả về detection data mới nhất từ tất cả devices

GET /api/detection/history?limit=100
- Trả về detection history

GET /api/detection/reports?limit=50&device_id=drone-camera
- Trả về danh sách reports đã lưu

GET /api/detection/report/<id>
- Trả về chi tiết report kèm hình ảnh

GET /api/detection/stats?device_id=drone-camera
- Trả về thống kê detection
```

### Socket.IO Events:

#### From Drone to Server:
- `detection_data` - Real-time detection counts
- `detection_snapshot` - Periodic report với image

#### From Server to Web:
- `detection_update` - Broadcast detection data
- `snapshot_saved` - Thông báo có snapshot mới
- `report_config_updated` - Thông báo config đã được update

#### From Web to Drone (via Server):
- `request_detection_report` - Yêu cầu chụp report ngay
- `set_report_interval_event` - Đổi interval (seconds)
- `toggle_periodic_report` - Bật/tắt auto report

### Database Schema:

```sql
CREATE TABLE detection_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    device_name TEXT NOT NULL,
    earth_person_count INTEGER DEFAULT 0,
    sea_person_count INTEGER DEFAULT 0,
    total_count INTEGER DEFAULT 0,
    image_data TEXT,  -- Base64 encoded JPEG
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_device_timestamp ON detection_reports(device_id, timestamp DESC);
CREATE INDEX idx_timestamp ON detection_reports(timestamp DESC);
```

### Cách sử dụng:

#### 1. Chạy Server:
```bash
cd sky-webapp
python app.py
```

#### 2. Chạy Drone Client:
```bash
cd sky-webapp/drone-app
python main.py --model model_fp32.onnx
```

#### 3. Mở Dashboard:
```
http://localhost:5000/dashboard
```

#### 4. Xem Detection Data:
- Panel "AI Detection - Phát hiện người" hiển thị:
  - Số lượng Earth Person (real-time)
  - Số lượng Sea Person (real-time)
  - Tổng số người
  - Danh sách báo cáo đã lưu

#### 5. Điều chỉnh cấu hình:
- **Bật/Tắt tự động chụp**: Toggle switch "Tự động chụp"
- **Chọn interval**: Dropdown từ 1-30 phút
- **Chụp ngay**: Click button "Chụp ngay"
- Thay đổi được áp dụng ngay lập tức

#### 6. Request Report On-demand:
- Click button "Chụp ngay" để capture ngay lập tức
- Báo cáo sẽ được lưu vào database kèm hình ảnh

#### 7. Xem Báo cáo Chi tiết:
- Click vào report item trong danh sách
- Modal hiển thị hình ảnh đầy đủ và thông tin chi tiết

### Tối ưu hóa:

1. **Detection Performance:**
   - Chỉ run inference mỗi 3 frames
   - Confidence threshold: 0.5
   - NMS IoU threshold: 0.45

2. **Network Traffic:**
   - Throttle detection_data emissions (2s)
   - Periodic reports (configurable 1-30 phút)
   - JPEG quality: 85%

3. **Database:**
   - Index trên device_id và timestamp
   - Auto cleanup old reports (có thể config)

### Cấu hình mặc định:

- **Report Interval**: 1 phút (60 seconds)
- **Auto Report**: Bật (enabled)
- **Detection Frequency**: Mỗi 3 frames
- **Confidence Threshold**: 0.5
- **NMS IoU Threshold**: 0.45
- **JPEG Quality**: 85%

Tất cả có thể thay đổi từ UI hoặc code!

### Lưu ý:

- Model ONNX phải có 2 classes: earth_person (index 0) và sea_person (index 1)
- Output shape: (1, 6, 8400) - [x, y, w, h, conf_class0, conf_class1]
- Hình ảnh được lưu dạng Base64 trong database
- Report interval mặc định: **60s (1 phút)** - có thể thay đổi từ UI (1-30 phút)
- Auto report có thể bật/tắt bất cứ lúc nào từ dashboard
- Interval tối thiểu: 1 phút (để tránh overload)

### Troubleshooting:

**1. Model không load được:**
- Kiểm tra path đến model_fp32.onnx
- Đảm bảo onnxruntime đã được cài đặt

**2. Không thấy detection data:**
- Kiểm tra console log xem model có chạy không
- Verify output shape của model

**3. Báo cáo không lưu:**
- Kiểm tra database file `detection_data.db` có được tạo không
- Check logs trong detection_controller.py

**4. Hình ảnh không hiển thị:**
- Kiểm tra Base64 encoding
- Verify image_data trong database không null
