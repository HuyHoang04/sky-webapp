# SkyAid Drone WebApp - ORM Implementation Guide

## 📁 Cấu trúc dự án đã được tổ chức

```
sky-webapp/
├── app.py                          # Main Flask application (✓ Updated)
├── database.py                     # Database configuration & session management (✓ New)
├── requirements.txt                # Dependencies (✓ Updated)
├── .env                           # Environment variables (✓ Updated)
├── .env.example                   # Example configuration (✓ New)
│
├── model/                         # Database models
│   └── mission_model.py           # Mission, Waypoint, Route, Order models (✓ New)
│
├── services/                      # Business logic layer (✓ New)
│   ├── __init__.py
│   ├── route_optimizer.py         # TSP & delivery route optimization
│   └── mission_service.py         # Mission & order CRUD operations
│
└── controller/
    └── mission_controller.py      # API endpoints (✓ Updated)
```

## 🚀 Hướng dẫn cài đặt

### 1. Cài đặt dependencies

```bash
pip install -r requirements.txt
```

### 2. Cấu hình database

Mở file `.env` và cập nhật connection string:

```env
# Lấy connection string từ Supabase Dashboard
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@db.YOUR_PROJECT.supabase.co:5432/postgres
```

### 3. Khởi động ứng dụng

```bash
python app.py
```

Database tables sẽ tự động được tạo khi khởi động lần đầu.

## 📊 Database Schema

### Tables được tạo tự động:

1. **missions** - Thông tin nhiệm vụ bay
2. **waypoints** - Điểm dừng trong lộ trình
3. **routes** - Đường đi đã tối ưu
4. **orders** - Đơn hàng giao nhận

## 🔧 API Endpoints

### Mission Management

#### Tạo mission mới
```javascript
POST /api/missions
{
    "name": "Medical Delivery Mission",
    "type": "delivery",
    "device_id": "drone1",
    "configuration": {
        "flightHeight": 50,
        "flightSpeed": 10,
        "returnAltitude": 70
    },
    "waypoints": [
        {"lat": 21.0285, "lng": 105.8542, "altitude": 50},
        {"lat": 21.0385, "lng": 105.8642, "altitude": 50}
    ],
    "optimize": true
}
```

#### Lấy danh sách missions
```javascript
GET /api/missions?device_id=drone1&status=planned
```

#### Lấy chi tiết mission
```javascript
GET /api/missions/1
```

#### Cập nhật mission
```javascript
PUT /api/missions/1
{
    "status": "in_progress",
    "notes": "Updated mission notes"
}
```

#### Xóa mission
```javascript
DELETE /api/missions/1
```

#### Bắt đầu mission
```javascript
POST /api/missions/1/start
```

#### Hoàn thành mission
```javascript
POST /api/missions/1/complete
```

#### Tối ưu lộ trình
```javascript
POST /api/missions/1/optimize-route
{
    "start_point": {
        "latitude": 21.0285,
        "longitude": 105.8542
    }
}
```

### Order Management

#### Tạo order mới
```javascript
POST /api/orders
{
    "order_number": "ORD-2024-001",
    "category": "medical",
    "priority": "critical",
    "pickup_location": {"lat": 21.0285, "lng": 105.8542},
    "pickup_address": "123 Hanoi Street",
    "delivery_location": {"lat": 21.0385, "lng": 105.8642},
    "delivery_address": "456 Ho Chi Minh Street",
    "items": [
        {"name": "Emergency Medical Kit", "quantity": 1}
    ],
    "package_weight": 2.5,
    "customer_name": "Nguyễn Văn A",
    "customer_phone": "0901234567",
    "temperature_controlled": true,
    "fragile": true,
    "special_instructions": "Handle with care"
}
```

#### Lấy orders của mission
```javascript
GET /api/orders?mission_id=1
```

#### Cập nhật trạng thái order
```javascript
PUT /api/orders/1
{
    "status": "picked_up",
    "timestamp_field": "actual_pickup"
}
```

## 🎯 Features

### ✅ Đã triển khai

1. **ORM với SQLAlchemy**
   - Không sử dụng thư viện trực tiếp của Supabase
   - Tương thích với PostgreSQL/Supabase
   - Session management và connection pooling

2. **Mission Management**
   - CRUD operations đầy đủ
   - Tự động tính toán khoảng cách, thời gian, pin
   - Real-time updates qua WebSocket

3. **Order Management**
   - Hỗ trợ nhiều loại: food, medical, equipment
   - Priority levels: low, medium, high, critical
   - Tracking đầy đủ từ pickup đến delivery

4. **Route Optimization**
   - TSP (Traveling Salesman Problem) cho waypoints
   - Greedy algorithm cho delivery routes
   - Tính toán khoảng cách Haversine
   - Tối ưu theo priority

5. **Tích hợp bản đồ**
   - Waypoints với tọa độ GPS
   - Route visualization
   - Interactive map controls

## 🧪 Testing

### Test tạo mission với frontend

```javascript
// Trong mission.html hoặc console
const missionData = {
    name: "Test Medical Delivery",
    type: "delivery",
    device_id: "drone1",
    configuration: {
        flightHeight: 50,
        flightSpeed: 10
    },
    waypoints: [
        {lat: 21.0285, lng: 105.8542},
        {lat: 21.0385, lng: 105.8642},
        {lat: 21.0485, lng: 105.8742}
    ],
    optimize: true
};

fetch('/api/missions', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(missionData)
})
.then(res => res.json())
.then(data => console.log('Mission created:', data));
```

### Test tạo order

```javascript
const orderData = {
    order_number: "ORD-" + Date.now(),
    category: "medical",
    priority: "critical",
    pickup_location: {lat: 21.0285, lng: 105.8542},
    delivery_location: {lat: 21.0385, lng: 105.8642},
    items: [{name: "Medical Kit", quantity: 1}],
    customer_name: "Test Customer",
    customer_phone: "0901234567"
};

fetch('/api/orders', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(orderData)
})
.then(res => res.json())
.then(data => console.log('Order created:', data));
```

## 🔍 Troubleshooting

### Database connection failed
- Kiểm tra `DATABASE_URL` trong file `.env`
- Verify Supabase project đang chạy
- Kiểm tra firewall/network access

### Import errors
- Chạy: `pip install -r requirements.txt`
- Restart Python interpreter

### Tables không được tạo
- Kiểm tra logs khi start app
- Manually run: `from database import init_db; init_db()`

## 📚 Tài liệu tham khảo

- **SQLAlchemy**: https://docs.sqlalchemy.org/
- **NetworkX** (route optimization): https://networkx.org/
- **Supabase PostgreSQL**: https://supabase.com/docs/guides/database

## 🎓 Best Practices đã áp dụng

1. **Separation of Concerns**: Models, Services, Controllers tách biệt
2. **Context Managers**: Tự động handle DB transactions
3. **Error Handling**: Try-catch với logging đầy đủ
4. **Type Hints**: Rõ ràng về input/output types
5. **Documentation**: Docstrings cho mọi function
6. **Enums**: Type-safe cho status và categories
7. **Relationships**: Cascade delete và lazy loading
8. **Indexes**: Tối ưu query performance

## 🚀 Next Steps

1. **Frontend Integration**: Cập nhật mission.html để call API mới
2. **Authentication**: Thêm user authentication
3. **File Upload**: Upload photos/documents cho missions
4. **Analytics**: Dashboard với statistics
5. **Testing**: Unit tests cho services
6. **Deployment**: Docker containerization

---

**Phát triển bởi**: SkyAid Team  
**Version**: 1.0.0  
**Date**: 2024
