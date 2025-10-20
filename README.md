# Sky WebApp - Hệ thống giám sát video và GPS thời gian thực

Hệ thống web cho phép hiển thị video thời gian thực từ Raspberry Pi sử dụng WebRTC và nhận dữ liệu GPS từ drone và phao cứu hộ qua WebSocket.

## Tính năng chính

- **Video streaming thời gian thực**: Sử dụng WebRTC để truyền video từ Raspberry Pi với độ trễ thấp
- **Theo dõi GPS**: Hiển thị vị trí thiết bị trên bản đồ và cập nhật theo thời gian thực
- **Dashboard tích hợp**: Giao diện người dùng trực quan hiển thị cả video và dữ liệu GPS
- **Kiến trúc MVC**: Tổ chức code rõ ràng, dễ bảo trì và mở rộng

## Yêu cầu hệ thống

- Python 3.7+
- Raspberry Pi với camera (cho video streaming)
- Thiết bị có GPS (drone, phao cứu hộ)
- Trình duyệt web hiện đại hỗ trợ WebRTC và WebSocket

## Cài đặt

1. Clone repository:
```
git clone https://github.com/your-username/sky-webapp.git
cd sky-webapp
```

2. Cài đặt các thư viện cần thiết:
```
pip install -r requirements.txt
```

3. Khởi động ứng dụng:
```
python app.py
```

4. Truy cập ứng dụng tại địa chỉ:
```
http://localhost:5000
```

## Cấu hình Raspberry Pi

1. Cài đặt các thư viện cần thiết trên Raspberry Pi:
```
pip install aiortc opencv-python numpy websockets
```

2. Chạy script khởi động trên Raspberry Pi:
```
python raspberry_client.py --server-url ws://your-server-ip:5000 --device-id raspberry-01
```

## Cấu trúc dự án

```
sky_webapp/
├── app.py                  # Điểm khởi đầu ứng dụng
├── requirements.txt        # Danh sách thư viện cần thiết
├── raspberry_client.py     # Script chạy trên Raspberry Pi
├── controller/             # Các controller xử lý logic
│   ├── main_controller.py  # Controller chính
│   ├── gps_controller.py   # Xử lý dữ liệu GPS
│   └── video_controller.py # Xử lý video streaming
├── model/                  # Các model dữ liệu
│   ├── gps_model.py        # Model dữ liệu GPS
│   └── video_model.py      # Model dữ liệu video
├── static/                 # Tài nguyên tĩnh
│   ├── css/                # Style sheets
│   │   └── style.css       # CSS chính
│   └── js/                 # JavaScript
│       ├── main.js         # JS chính
│       ├── gps_client.js   # Xử lý dữ liệu GPS
│       └── webrtc_client.js # Xử lý kết nối WebRTC
└── templates/              # Templates HTML
    ├── layout.html         # Layout chung
    ├── index.html          # Trang chủ
    ├── dashboard.html      # Dashboard
    └── webrtc.html         # Trang xem video WebRTC
```

## API Endpoints

### Video API
- `GET /api/video/streams` - Lấy danh sách các video stream
- `GET /api/video/stream/<device_id>` - Lấy thông tin về một video stream cụ thể
- `GET /webrtc/<device_id>` - Trang xem video WebRTC cho thiết bị cụ thể

### GPS API
- `GET /api/gps` - Lấy dữ liệu GPS của tất cả thiết bị
- `GET /api/gps/<device_id>` - Lấy dữ liệu GPS của một thiết bị cụ thể
- `POST /api/gps` - Gửi dữ liệu GPS mới

## WebSocket Events

### GPS Events
- `connect` - Kết nối WebSocket
- `disconnect` - Ngắt kết nối WebSocket
- `gps_data` - Nhận dữ liệu GPS mới

### WebRTC Events
- `webrtc_offer` - Nhận SDP offer từ client
- `webrtc_answer` - Nhận SDP answer từ server
- `webrtc_ice_candidate` - Nhận ICE candidate
- `register_video_device` - Đăng ký thiết bị video mới

## Đóng góp

Vui lòng gửi pull request hoặc báo cáo lỗi qua mục Issues.

## Giấy phép

[MIT License](LICENSE)