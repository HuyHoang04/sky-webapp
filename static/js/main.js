/**
 * File JavaScript chính cho Sky WebApp
 * Khởi tạo các kết nối và xử lý sự kiện
 */

// Khởi tạo kết nối Socket.IO khi trang được tải
document.addEventListener('DOMContentLoaded', function() {
    // Khởi tạo kết nối Socket.IO
    const socket = io();
    
    // Xử lý khi kết nối thành công
    socket.on('connect', function() {
        console.log('Đã kết nối đến server');
        updateConnectionStatus('connected');
    });
    
    // Xử lý khi mất kết nối
    socket.on('disconnect', function() {
        console.log('Đã ngắt kết nối từ server');
        updateConnectionStatus('disconnected');
    });
    
    // Xử lý khi có lỗi kết nối
    socket.on('connect_error', function(error) {
        console.error('Lỗi kết nối:', error);
        updateConnectionStatus('error');
    });
    
    // Cập nhật trạng thái kết nối trên giao diện
    function updateConnectionStatus(status) {
        const statusElement = document.getElementById('connectionStatus');
        if (!statusElement) return;
        
        switch (status) {
            case 'connected':
                statusElement.textContent = 'Đã kết nối';
                statusElement.className = 'badge bg-success';
                break;
            case 'disconnected':
                statusElement.textContent = 'Mất kết nối';
                statusElement.className = 'badge bg-danger';
                break;
            case 'error':
                statusElement.textContent = 'Lỗi kết nối';
                statusElement.className = 'badge bg-warning';
                break;
            default:
                statusElement.textContent = 'Không xác định';
                statusElement.className = 'badge bg-secondary';
        }
    }
    
    // Khởi tạo các thành phần tùy thuộc vào trang hiện tại
    initCurrentPage(socket);
});

/**
 * Khởi tạo các thành phần tùy thuộc vào trang hiện tại
 */
function initCurrentPage(socket) {
    // Xác định trang hiện tại dựa trên URL
    const currentPath = window.location.pathname;
    
    if (currentPath === '/dashboard') {
        // Khởi tạo trang Dashboard
        initDashboard(socket);
    } else if (currentPath.startsWith('/webrtc/')) {
        // Khởi tạo trang WebRTC
        initWebRTCPage(socket);
    }
}

/**
 * Khởi tạo trang Dashboard
 */
function initDashboard(socket) {
    console.log('Khởi tạo trang Dashboard');
    
    // Khởi tạo bản đồ GPS nếu có
    const mapElement = document.getElementById('map');
    if (mapElement) {
        // Khởi tạo GPSClient nếu đã tải thư viện
        if (typeof GPSClient !== 'undefined') {
            const gpsClient = new GPSClient(socket, mapElement, updateGPSData);
            
            // Xử lý các nút hiển thị/ẩn thiết bị
            const showDroneCheckbox = document.getElementById('showDrone');
            const showLifebuoyCheckbox = document.getElementById('showLifebuoy');
            
            if (showDroneCheckbox) {
                showDroneCheckbox.addEventListener('change', function() {
                    const droneIds = Object.keys(gpsClient.getAllDevices()).filter(id => id.includes('drone'));
                    droneIds.forEach(id => gpsClient.toggleDevice(id, this.checked));
                });
            }
            
            if (showLifebuoyCheckbox) {
                showLifebuoyCheckbox.addEventListener('change', function() {
                    const lifebuoyIds = Object.keys(gpsClient.getAllDevices()).filter(id => !id.includes('drone'));
                    lifebuoyIds.forEach(id => gpsClient.toggleDevice(id, this.checked));
                });
            }
        }
    }
    
    // Khởi tạo video stream nếu có
    const videoElement = document.getElementById('videoStream');
    if (videoElement) {
        // Khởi tạo WebRTCClient nếu đã tải thư viện
        if (typeof WebRTCClient !== 'undefined') {
            const startStreamButton = document.getElementById('startStream');
            const stopStreamButton = document.getElementById('stopStream');
            const streamStatus = document.getElementById('streamStatus');
            
            // Xác định thiết bị mặc định
            const defaultDeviceId = 'drone1';
            
            // Tạo client WebRTC
            const webrtcClient = new WebRTCClient(defaultDeviceId, videoElement, socket, function(status, data) {
                // Cập nhật trạng thái stream
                if (streamStatus) {
                    switch (status) {
                        case 'connecting':
                            streamStatus.textContent = 'Đang kết nối...';
                            streamStatus.className = 'badge bg-warning';
                            break;
                        case 'connected':
                            streamStatus.textContent = 'Đang phát';
                            streamStatus.className = 'badge bg-success';
                            break;
                        case 'disconnected':
                        case 'stopped':
                            streamStatus.textContent = 'Đã dừng';
                            streamStatus.className = 'badge bg-secondary';
                            break;
                        case 'error':
                            streamStatus.textContent = 'Lỗi: ' + (data || 'Không xác định');
                            streamStatus.className = 'badge bg-danger';
                            break;
                    }
                }
            });
            
            // Xử lý sự kiện nút bắt đầu stream
            if (startStreamButton) {
                startStreamButton.addEventListener('click', function() {
                    webrtcClient.start();
                });
            }
            
            // Xử lý sự kiện nút dừng stream
            if (stopStreamButton) {
                stopStreamButton.addEventListener('click', function() {
                    webrtcClient.stop();
                });
            }
            
            // Xử lý sự kiện chọn nguồn video
            document.querySelectorAll('#videoSourceList a').forEach(item => {
                item.addEventListener('click', function(e) {
                    e.preventDefault();
                    const deviceId = this.getAttribute('data-device-id');
                    document.getElementById('videoSourceDropdown').textContent = this.textContent;
                    
                    // Dừng stream hiện tại
                    webrtcClient.stop();
                    
                    // Tạo client WebRTC mới với thiết bị đã chọn
                    const newWebrtcClient = new WebRTCClient(deviceId, videoElement, socket, function(status, data) {
                        // Cập nhật trạng thái stream
                        if (streamStatus) {
                            switch (status) {
                                case 'connecting':
                                    streamStatus.textContent = 'Đang kết nối...';
                                    streamStatus.className = 'badge bg-warning';
                                    break;
                                case 'connected':
                                    streamStatus.textContent = 'Đang phát';
                                    streamStatus.className = 'badge bg-success';
                                    break;
                                case 'disconnected':
                                case 'stopped':
                                    streamStatus.textContent = 'Đã dừng';
                                    streamStatus.className = 'badge bg-secondary';
                                    break;
                                case 'error':
                                    streamStatus.textContent = 'Lỗi: ' + (data || 'Không xác định');
                                    streamStatus.className = 'badge bg-danger';
                                    break;
                            }
                        }
                    });
                    
                    // Bắt đầu stream mới
                    newWebrtcClient.start();
                });
            });
        }
    }
}

/**
 * Khởi tạo trang WebRTC
 */
function initWebRTCPage(socket) {
    console.log('Khởi tạo trang WebRTC');
    
    // Lấy ID thiết bị từ URL
    const pathParts = window.location.pathname.split('/');
    const deviceId = pathParts[pathParts.length - 1];
    
    // Khởi tạo video stream
    const videoElement = document.getElementById('videoStream');
    if (videoElement && deviceId) {
        // Khởi tạo WebRTCClient nếu đã tải thư viện
        if (typeof WebRTCClient !== 'undefined') {
            const startStreamButton = document.getElementById('startStream');
            const stopStreamButton = document.getElementById('stopStream');
            const streamStatus = document.getElementById('streamStatus');
            const connectionState = document.getElementById('connectionState');
            const latencyDisplay = document.getElementById('latency');
            const qualityDisplay = document.getElementById('quality');
            
            // Tạo client WebRTC
            const webrtcClient = new WebRTCClient(deviceId, videoElement, socket, function(status, data) {
                // Cập nhật trạng thái stream
                switch (status) {
                    case 'connecting':
                        streamStatus.textContent = 'Đang kết nối...';
                        streamStatus.className = 'badge bg-warning';
                        if (connectionState) connectionState.textContent = 'Đang thiết lập kết nối';
                        break;
                    case 'connected':
                        streamStatus.textContent = 'Đang phát';
                        streamStatus.className = 'badge bg-success';
                        if (latencyDisplay && data && data.latency) {
                            latencyDisplay.textContent = `${data.latency}ms`;
                        }
                        break;
                    case 'connection_state_change':
                        if (connectionState) connectionState.textContent = data;
                        break;
                    case 'disconnected':
                    case 'stopped':
                        streamStatus.textContent = 'Đã dừng';
                        streamStatus.className = 'badge bg-secondary';
                        if (connectionState) connectionState.textContent = 'Ngắt kết nối';
                        if (latencyDisplay) latencyDisplay.textContent = '--';
                        if (qualityDisplay) qualityDisplay.textContent = '--';
                        break;
                    case 'error':
                        streamStatus.textContent = 'Lỗi';
                        streamStatus.className = 'badge bg-danger';
                        if (connectionState) connectionState.textContent = 'Lỗi: ' + (data || 'Không xác định');
                        break;
                    case 'video_settings':
                        if (qualityDisplay && data) {
                            qualityDisplay.textContent = `${data.width}x${data.height} @ ${data.frameRate || '--'}fps`;
                        }
                        break;
                }
            });
            
            // Xử lý sự kiện nút bắt đầu stream
            if (startStreamButton) {
                startStreamButton.addEventListener('click', function() {
                    webrtcClient.start();
                });
            }
            
            // Xử lý sự kiện nút dừng stream
            if (stopStreamButton) {
                stopStreamButton.addEventListener('click', function() {
                    webrtcClient.stop();
                });
            }
            
            // Tự động bắt đầu stream khi trang được tải
            webrtcClient.start();
        }
    }
}

/**
 * Cập nhật dữ liệu GPS trên giao diện
 */
function updateGPSData(deviceId, data) {
    // Cập nhật bảng dữ liệu GPS
    const latElement = document.getElementById(`${deviceId}-lat`);
    const lngElement = document.getElementById(`${deviceId}-lng`);
    const altElement = document.getElementById(`${deviceId}-alt`);
    const speedElement = document.getElementById(`${deviceId}-speed`);
    const timeElement = document.getElementById(`${deviceId}-time`);
    
    if (latElement) latElement.textContent = data.latitude.toFixed(6);
    if (lngElement) lngElement.textContent = data.longitude.toFixed(6);
    if (altElement) altElement.textContent = `${data.altitude}m`;
    if (speedElement) speedElement.textContent = `${data.speed} km/h`;
    if (timeElement) timeElement.textContent = new Date(data.timestamp).toLocaleTimeString();
    
    // Cập nhật trạng thái thiết bị
    updateDeviceStatus(deviceId, true);
}