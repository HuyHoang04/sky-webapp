# Tính năng mới: Điều khiển Report từ UI

## 🎛️ UI Controls mới trên Dashboard

### 1. **Toggle Tự động chụp**
- Switch để bật/tắt chế độ chụp báo cáo tự động
- Mặc định: **BẬT**
- Tắt: Drone sẽ không tự chụp, chỉ chụp khi user yêu cầu

### 2. **Dropdown chọn Interval**
Các options:
- ✅ **1 phút** (mặc định)
- 2 phút
- 3 phút
- 5 phút
- 10 phút
- 15 phút
- 30 phút

### 3. **Button "Chụp ngay"**
- Chụp snapshot ngay lập tức không cần đợi interval
- Hoạt động bất kể auto report bật hay tắt

## 🔄 Luồng hoạt động

```
User thay đổi setting trên UI
    ↓
Socket.IO emit event
    ↓
Server forward đến Drone
    ↓
Drone update global config
    ↓
Periodic task check config
    ↓
Apply changes real-time
    ↓
Notify user qua notification
```

## 📝 Code changes

### Files updated:
1. **drone-app/detection_utils.py**
   - Thêm global variables: `periodic_report_enabled`, `report_interval`
   - Functions: `set_report_interval()`, `enable/disable_periodic_report()`
   - Task check enabled flag trước khi chụp

2. **drone-app/main.py**
   - Socket handlers: `set_report_interval_event`, `toggle_periodic_report`
   - Emit `report_config_updated` để notify

3. **static/js/detection_client.js**
   - Methods: `setReportInterval()`, `togglePeriodicReport()`
   - Handler: `onConfigUpdated()` với notification

4. **templates/dashboard.html**
   - UI controls: Toggle switch + Dropdown + Button
   - Event listeners cho controls
   - Listen for config update events

5. **static/css/style.css**
   - Styling cho controls mới

## ✅ Testing

### Test Toggle:
1. Mở dashboard
2. Tắt "Tự động chụp"
3. ➡️ Drone sẽ không chụp tự động
4. Bật lại ➡️ Resume chụp

### Test Interval:
1. Chọn "1 phút"
2. ➡️ Sau 1 phút sẽ có báo cáo mới
3. Đổi sang "5 phút"
4. ➡️ Interval thay đổi ngay

### Test Chụp ngay:
1. Click "Chụp ngay"
2. ➡️ Snapshot được lưu ngay lập tức
3. Thông báo hiện ra

## 🎯 User Experience

**Trước đây:**
- Chỉ có thể chụp tự động mỗi 5 phút (fixed)
- Không thể tắt auto report
- Không có control từ UI

**Bây giờ:**
- ✅ Chọn interval từ 1-30 phút
- ✅ Bật/tắt auto report bất cứ lúc nào
- ✅ Chụp on-demand
- ✅ Thay đổi áp dụng real-time
- ✅ Notifications khi config thay đổi

## 🚀 Ví dụ sử dụng

### Scenario 1: Giám sát tích cực
```
Toggle: BẬT
Interval: 1 phút
➡️ Báo cáo mỗi phút với hình ảnh
```

### Scenario 2: Tiết kiệm storage
```
Toggle: BẬT
Interval: 30 phút
➡️ Báo cáo mỗi 30 phút
```

### Scenario 3: Chỉ chụp khi cần
```
Toggle: TẮT
➡️ Click "Chụp ngay" khi thấy cần thiết
```

### Scenario 4: Mix
```
Toggle: BẬT
Interval: 5 phút
+ Click "Chụp ngay" khi muốn
➡️ Vừa có auto report, vừa có manual capture
```

## 📊 Performance Impact

- **Minimum interval**: 1 phút (tránh overload)
- **Default**: 1 phút (thay vì 5 phút cũ)
- **Disabled mode**: Không chạy detection cho snapshot
- **On-demand**: Chỉ 1 snapshot, không ảnh hưởng stream

## 🔐 Validation

- Interval < 60s → tự động set về 60s
- Empty/invalid values → use default (60s)
- Toggle state → boolean check
- Device ID → required cho mọi events
