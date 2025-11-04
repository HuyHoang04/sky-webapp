/**
 * Detection Client cho Sky WebApp
 * Xử lý hiển thị dữ liệu detection từ AI model
 */

class DetectionClient {
    constructor(socketIo, updateCallback) {
        this.socket = socketIo;
        this.updateCallback = updateCallback || function() {};
        this.devices = {};
        this.detectionHistory = [];
        this.maxHistorySize = 100;
        
        // Thiết lập các event handlers cho socket
        this.setupSocketHandlers();
    }
    
    /**
     * Thiết lập các event handlers cho socket
     */
    setupSocketHandlers() {
        // Xử lý khi nhận được dữ liệu detection mới
        this.socket.on('detection_update', (data) => {
            this.updateDetectionData(data);
        });
        
        // Xử lý khi có snapshot được lưu
        this.socket.on('snapshot_saved', (data) => {
            this.onSnapshotSaved(data);
        });
        
        // Xử lý status của report request
        this.socket.on('report_status', (data) => {
            this.onReportStatus(data);
        });
        
        // Xử lý khi config được update
        this.socket.on('report_config_updated', (data) => {
            this.onConfigUpdated(data);
        });
    }
    
    /**
     * Cập nhật dữ liệu detection
     */
    updateDetectionData(data) {
        const deviceId = data.device_id;
        
        // Lưu trữ dữ liệu thiết bị
        this.devices[deviceId] = data;
        
        // Thêm vào history
        this.detectionHistory.push({
            ...data,
            receivedAt: new Date().toISOString()
        });
        
        // Giới hạn history size
        if (this.detectionHistory.length > this.maxHistorySize) {
            this.detectionHistory.shift();
        }
        
        // Gọi callback để cập nhật UI
        this.updateCallback(deviceId, data);
        
        console.log(`[Detection] Device ${deviceId}: Earth=${data.earth_person}, Sea=${data.sea_person}, Total=${data.total}`);
    }
    
    /**
     * Xử lý khi snapshot được lưu
     */
    onSnapshotSaved(data) {
        console.log(`[Detection] Snapshot saved for device ${data.device_id} at ${data.timestamp}`);
        
        // Trigger event để UI có thể phản hồi
        const event = new CustomEvent('detectionSnapshotSaved', { detail: data });
        document.dispatchEvent(event);
    }
    
    /**
     * Xử lý report status
     */
    onReportStatus(data) {
        console.log(`[Detection] Report status for ${data.device_id}: ${data.status}`);
        
        if (data.status === 'success') {
            this.showNotification('Report generated successfully', 'success');
        } else {
            this.showNotification(`Report failed: ${data.error || 'Unknown error'}`, 'error');
        }
    }
    
    /**
     * Xử lý khi config được update
     */
    onConfigUpdated(data) {
        console.log(`[Detection] Config updated:`, data);
        
        if (data.status === 'success') {
            const intervalMin = Math.floor(data.interval / 60);
            const enabledText = data.enabled ? 'enabled' : 'disabled';
            this.showNotification(`Periodic report ${enabledText} (${intervalMin} min interval)`, 'success');
            
            // Trigger event để UI có thể update
            const event = new CustomEvent('detectionConfigUpdated', { detail: data });
            document.dispatchEvent(event);
        } else {
            this.showNotification(`Config update failed: ${data.error}`, 'error');
        }
    }
    
    /**
     * Set report interval
     */
    setReportInterval(deviceId, intervalMinutes) {
        const intervalSeconds = intervalMinutes * 60;
        console.log(`[Detection] Setting report interval to ${intervalMinutes} minutes for device ${deviceId}`);
        this.socket.emit('set_report_interval_event', {
            device_id: deviceId,
            interval: intervalSeconds
        });
    }
    
    /**
     * Toggle periodic report on/off
     */
    togglePeriodicReport(deviceId, enabled) {
        console.log(`[Detection] ${enabled ? 'Enabling' : 'Disabling'} periodic report for device ${deviceId}`);
        this.socket.emit('toggle_periodic_report', {
            device_id: deviceId,
            enabled: enabled
        });
    }
    
    /**
     * Request detection report từ device
     */
    requestReport(deviceId) {
        console.log(`[Detection] Requesting report from device ${deviceId}`);
        this.socket.emit('request_detection_report', { device_id: deviceId });
    }
    
    /**
     * Lấy dữ liệu detection mới nhất cho device
     */
    getLatestDetection(deviceId) {
        return this.devices[deviceId] || null;
    }
    
    /**
     * Lấy tất cả devices có dữ liệu detection
     */
    getAllDevices() {
        return Object.keys(this.devices);
    }
    
    /**
     * Lấy detection history
     */
    getHistory(limit = null) {
        if (limit) {
            return this.detectionHistory.slice(-limit);
        }
        return this.detectionHistory;
    }
    
    /**
     * Load detection reports từ server
     */
    async loadReports(limit = 50, deviceId = null) {
        try {
            let url = `/api/detection/reports?limit=${limit}`;
            if (deviceId) {
                url += `&device_id=${deviceId}`;
            }
            
            const response = await fetch(url);
            const data = await response.json();
            
            if (data.status === 'success') {
                return data.reports;
            } else {
                console.error('[Detection] Error loading reports:', data.message);
                return [];
            }
        } catch (error) {
            console.error('[Detection] Error loading reports:', error);
            return [];
        }
    }
    
    /**
     * Load specific report with image
     */
    async loadReport(reportId) {
        try {
            const response = await fetch(`/api/detection/report/${reportId}`);
            const data = await response.json();
            
            if (data.status === 'success') {
                return data.report;
            } else {
                console.error('[Detection] Error loading report:', data.message);
                return null;
            }
        } catch (error) {
            console.error('[Detection] Error loading report:', error);
            return null;
        }
    }
    
    /**
     * Load detection statistics
     */
    async loadStatistics(deviceId = null) {
        try {
            let url = '/api/detection/stats';
            if (deviceId) {
                url += `?device_id=${deviceId}`;
            }
            
            const response = await fetch(url);
            const data = await response.json();
            
            if (data.status === 'success') {
                return data.stats;
            } else {
                console.error('[Detection] Error loading statistics:', data.message);
                return null;
            }
        } catch (error) {
            console.error('[Detection] Error loading statistics:', error);
            return null;
        }
    }
    
    /**
     * Hiển thị notification
     */
    showNotification(message, type = 'info') {
        // Tạo notification element
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.textContent = message;
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 15px 20px;
            background-color: ${type === 'success' ? '#28a745' : type === 'error' ? '#dc3545' : '#17a2b8'};
            color: white;
            border-radius: 5px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.2);
            z-index: 10000;
            animation: slideIn 0.3s ease-out;
        `;
        
        document.body.appendChild(notification);
        
        // Auto remove sau 3 giây
        setTimeout(() => {
            notification.style.animation = 'slideOut 0.3s ease-in';
            setTimeout(() => {
                document.body.removeChild(notification);
            }, 300);
        }, 3000);
    }
    
    /**
     * Tạo HTML cho detection card
     */
    createDetectionCard(data) {
        const card = document.createElement('div');
        card.className = 'detection-card';
        card.innerHTML = `
            <div class="detection-header">
                <h4>${data.device_name || data.device_id}</h4>
                <span class="detection-time">${new Date(data.timestamp).toLocaleTimeString()}</span>
            </div>
            <div class="detection-stats">
                <div class="stat-item earth-person">
                    <span class="stat-icon">🏃</span>
                    <span class="stat-label">Earth Person</span>
                    <span class="stat-value">${data.earth_person}</span>
                </div>
                <div class="stat-item sea-person">
                    <span class="stat-icon">🏊</span>
                    <span class="stat-label">Sea Person</span>
                    <span class="stat-value">${data.sea_person}</span>
                </div>
                <div class="stat-item total">
                    <span class="stat-icon">👥</span>
                    <span class="stat-label">Total</span>
                    <span class="stat-value">${data.total}</span>
                </div>
            </div>
        `;
        
        return card;
    }
    
    /**
     * Tạo HTML cho report item với thumbnail
     */
    createReportItem(report) {
        const item = document.createElement('div');
        item.className = 'report-item';
        item.innerHTML = `
            <div class="report-thumbnail">
                <img src="data:image/jpeg;base64,${report.image_data || ''}" 
                     alt="Detection snapshot" 
                     onerror="this.src='/static/images/no-image.png'">
            </div>
            <div class="report-info">
                <div class="report-header">
                    <h5>${report.device_name || report.device_id}</h5>
                    <span class="report-time">${new Date(report.timestamp).toLocaleString()}</span>
                </div>
                <div class="report-stats">
                    <span class="stat-badge earth">🏃 ${report.earth_person_count}</span>
                    <span class="stat-badge sea">🏊 ${report.sea_person_count}</span>
                    <span class="stat-badge total">👥 ${report.total_count}</span>
                </div>
            </div>
        `;
        
        // Click to view full report
        item.addEventListener('click', () => {
            this.showReportModal(report);
        });
        
        return item;
    }
    
    /**
     * Hiển thị modal với full report details
     */
    async showReportModal(report) {
        // Load full report if needed
        if (!report.image_data && report.id) {
            report = await this.loadReport(report.id);
            if (!report) {
                this.showNotification('Failed to load report details', 'error');
                return;
            }
        }
        
        // Create modal
        const modal = document.createElement('div');
        modal.className = 'report-modal';
        modal.innerHTML = `
            <div class="modal-overlay"></div>
            <div class="modal-content">
                <div class="modal-header">
                    <h3>Detection Report</h3>
                    <button class="modal-close">&times;</button>
                </div>
                <div class="modal-body">
                    <img src="data:image/jpeg;base64,${report.image_data}" 
                         alt="Detection snapshot" 
                         class="report-image">
                    <div class="report-details">
                        <p><strong>Device:</strong> ${report.device_name || report.device_id}</p>
                        <p><strong>Time:</strong> ${new Date(report.timestamp).toLocaleString()}</p>
                        <p><strong>Earth Person:</strong> ${report.earth_person_count}</p>
                        <p><strong>Sea Person:</strong> ${report.sea_person_count}</p>
                        <p><strong>Total:</strong> ${report.total_count}</p>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        
        // Close handlers
        modal.querySelector('.modal-close').addEventListener('click', () => {
            document.body.removeChild(modal);
        });
        
        modal.querySelector('.modal-overlay').addEventListener('click', () => {
            document.body.removeChild(modal);
        });
    }
}

// Export for use
window.DetectionClient = DetectionClient;
