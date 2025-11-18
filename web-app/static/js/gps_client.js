/**
 * GPS Client cho Sky WebApp
 * Xử lý kết nối WebSocket để nhận dữ liệu GPS từ các thiết bị
 */

class GPSClient {
    constructor(socketIo, mapElement, updateCallback) {
        this.socket = socketIo;
        this.map = null;
        this.mapElement = mapElement;
        this.updateCallback = updateCallback || function() {};
        this.markers = {};
        this.devices = {};
        this.paths = {};
        
        // Khởi tạo bản đồ
        this.initMap();
        
        // Thiết lập các event handlers cho socket
        this.setupSocketHandlers();
    }
    
    /**
     * Khởi tạo bản đồ Leaflet
     */
    initMap() {
        // Vị trí mặc định (Hà Nội)
        const defaultPosition = [21.0285, 105.8542];
        
        // Tạo bản đồ
        this.map = L.map(this.mapElement).setView(defaultPosition, 13);
        
        // Thêm layer bản đồ
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        }).addTo(this.map);
    }
    
    /**
     * Thiết lập các event handlers cho socket
     */
    setupSocketHandlers() {
        // Xử lý khi nhận được dữ liệu GPS mới
        this.socket.on('gps_update', (data) => {
            this.updateGPSData(data);
        });
    }
    
    /**
     * Cập nhật dữ liệu GPS và hiển thị trên bản đồ
     */
    updateGPSData(data) {
        const deviceId = data.device_id;
        const position = [data.latitude, data.longitude];
        
        // Lưu trữ dữ liệu thiết bị
        this.devices[deviceId] = data;
        
        // Gọi callback để cập nhật UI
        this.updateCallback(deviceId, data);
        
        // Cập nhật hoặc tạo marker mới
        if (this.markers[deviceId]) {
            // Cập nhật vị trí marker
            this.markers[deviceId].setLatLng(position);
            
            // Cập nhật nội dung popup
            this.markers[deviceId].getPopup().setContent(this.createPopupContent(deviceId, data));
            
            // Thêm điểm vào đường đi
            if (this.paths[deviceId]) {
                this.paths[deviceId].addLatLng(position);
            }
        } else {
            // Tạo marker mới
            this.createMarker(deviceId, position, data);
            
            // Tạo đường đi mới
            this.createPath(deviceId, position);
        }
    }
    
    /**
     * Tạo marker mới cho thiết bị
     */
    createMarker(deviceId, position, data) {
        // Xác định loại thiết bị và tạo icon phù hợp
        let icon;
        if (deviceId.includes('drone')) {
            icon = L.divIcon({
                className: 'custom-div-icon',
                html: '<div style="background-color: #007bff; width: 15px; height: 15px; border-radius: 50%; border: 2px solid white;"></div>',
                iconSize: [15, 15],
                iconAnchor: [7, 7]
            });
        } else {
            icon = L.divIcon({
                className: 'custom-div-icon',
                html: '<div style="background-color: #dc3545; width: 15px; height: 15px; border-radius: 50%; border: 2px solid white;"></div>',
                iconSize: [15, 15],
                iconAnchor: [7, 7]
            });
        }
        
        // Tạo marker
        const marker = L.marker(position, { icon: icon })
            .addTo(this.map)
            .bindPopup(this.createPopupContent(deviceId, data));
        
        // Lưu trữ marker
        this.markers[deviceId] = marker;
    }
    
    /**
     * Tạo đường đi mới cho thiết bị
     */
    createPath(deviceId, position) {
        // Xác định màu đường đi dựa trên loại thiết bị
        let color = deviceId.includes('drone') ? '#007bff' : '#dc3545';
        
        // Tạo đường đi
        const path = L.polyline([position], {
            color: color,
            weight: 3,
            opacity: 0.7
        }).addTo(this.map);
        
        // Lưu trữ đường đi
        this.paths[deviceId] = path;
    }
    
    /**
     * Tạo nội dung popup cho marker
     */
    createPopupContent(deviceId, data) {
        const timestamp = new Date(data.timestamp).toLocaleTimeString();
        return `
            <div>
                <strong>${deviceId}</strong><br>
                Vĩ độ: ${data.latitude.toFixed(6)}<br>
                Kinh độ: ${data.longitude.toFixed(6)}<br>
                Độ cao: ${data.altitude}m<br>
                Tốc độ: ${data.speed} km/h<br>
                Thời gian: ${timestamp}
            </div>
        `;
    }
    
    /**
     * Hiển thị/ẩn thiết bị trên bản đồ
     */
    toggleDevice(deviceId, show) {
        if (this.markers[deviceId]) {
            if (show) {
                this.map.addLayer(this.markers[deviceId]);
                if (this.paths[deviceId]) {
                    this.map.addLayer(this.paths[deviceId]);
                }
            } else {
                this.map.removeLayer(this.markers[deviceId]);
                if (this.paths[deviceId]) {
                    this.map.removeLayer(this.paths[deviceId]);
                }
            }
        }
    }
    
    /**
     * Lấy tất cả dữ liệu GPS hiện tại
     */
    getAllDevices() {
        return this.devices;
    }
    
    /**
     * Lấy dữ liệu GPS của một thiết bị cụ thể
     */
    getDevice(deviceId) {
        return this.devices[deviceId];
    }
    
    /**
     * Làm mới bản đồ
     */
    refreshMap() {
        this.map.invalidateSize();
    }
    
    /**
     * Di chuyển bản đồ đến vị trí của một thiết bị
     */
    centerOnDevice(deviceId) {
        if (this.markers[deviceId]) {
            this.map.setView(this.markers[deviceId].getLatLng(), 15);
        }
    }
}