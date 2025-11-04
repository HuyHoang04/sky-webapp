/**
 * WebRTC Client cho Sky WebApp
 * Xử lý kết nối WebRTC giữa client và drone
 */

class WebRTCClient {
    constructor(deviceId, videoElement, socketIo, statusCallback) {
        this.deviceId = deviceId;
        this.videoElement = videoElement;
        this.socket = socketIo;
        this.statusCallback = statusCallback || function() {};
        this.peerConnection = null;
        this.startTime = null;
        this.iceCandidates = [];
        this.isConnected = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 999; // Không giới hạn thực tế
        this.reconnectDelay = 500; // Giảm từ 2000ms xuống 500ms
        this.connectionTimeout = 15000; // ms
        this.connectionTimer = null;
        this.reconnectTimer = null;
        this.heartbeatInterval = null;
        this.isPageVisible = true;
        this.shouldAutoReconnect = true; // Flag để điều khiển auto-reconnect
        
        // Thiết lập các event handlers cho socket
        this.setupSocketHandlers();
        
        // Thiết lập Page Visibility API để giữ kết nối khi chuyển tab
        this.setupVisibilityHandler();
        
        // Thiết lập beforeunload handler
        this.setupBeforeUnloadHandler();
    }
    
    /**
     * Thiết lập các event handlers cho socket
     */
    setupSocketHandlers() {
        // Xử lý khi nhận được offer từ drone qua server
        this.socket.on('webrtc_offer', async (data) => {
            if (data.device_id !== this.deviceId) return;
            
            try {
                console.log('Nhận WebRTC offer từ drone');
                this.statusCallback('offer_received');
                
                // Đảm bảo peer connection đã được khởi tạo
                if (!this.peerConnection || this.peerConnection.connectionState === 'closed') {
                    await this.createPeerConnection();
                }
                
                // Nhận offer từ drone và tạo answer
                const remoteDesc = new RTCSessionDescription({
                    sdp: data.sdp,
                    type: data.type
                });
                
                await this.peerConnection.setRemoteDescription(remoteDesc);
                console.log('Đã thiết lập remote description từ offer');
                
                // Thêm các ICE candidates đã lưu trữ (nếu có)
                await this.addStoredIceCandidates();
                
                // Tạo answer
                const answer = await this.peerConnection.createAnswer();
                await this.peerConnection.setLocalDescription(answer);
                
                // Gửi answer về server để chuyển đến drone
                this.socket.emit('webrtc_answer', {
                    device_id: this.deviceId,
                    sdp: this.peerConnection.localDescription.sdp,
                    type: this.peerConnection.localDescription.type
                });
                
                console.log('Đã gửi WebRTC answer đến drone');
                this.statusCallback('answer_sent');
                
                // Thiết lập timeout cho kết nối
                this.setConnectionTimeout();
            } catch (error) {
                console.error('Lỗi khi xử lý offer:', error);
                this.statusCallback('error', error.message);
                this.handleConnectionFailure();
            }
        });
        
        // Xử lý khi nhận được ICE candidate từ drone qua server
        this.socket.on('webrtc_ice_candidate', async (data) => {
            if (data.device_id !== this.deviceId) return;
            
            try {
                console.log('Nhận ICE candidate từ drone');
                
                if (this.peerConnection && this.peerConnection.remoteDescription) {
                    await this.peerConnection.addIceCandidate(data.candidate);
                    console.log('Đã thêm ICE candidate');
                } else {
                    // Lưu trữ ICE candidate để thêm sau
                    this.iceCandidates.push(data.candidate);
                    console.log('Đã lưu ICE candidate để xử lý sau');
                }
            } catch (error) {
                console.error('Lỗi khi xử lý ICE candidate:', error);
            }
        });
    }
    
    /**
     * Thêm các ICE candidates đã lưu trữ vào peer connection
     */
    async addStoredIceCandidates() {
        if (this.peerConnection && this.peerConnection.remoteDescription) {
            for (const candidate of this.iceCandidates) {
                try {
                    await this.peerConnection.addIceCandidate(candidate);
                } catch (error) {
                    console.error('Lỗi khi thêm ICE candidate đã lưu trữ:', error);
                }
            }
            this.iceCandidates = [];
        }
    }
    
    /**
     * Tạo peer connection mới
     */
    async createPeerConnection() {
        // Tạo peer connection với nhiều STUN servers để tăng khả năng kết nối
        this.peerConnection = new RTCPeerConnection({
            iceServers: [
                {'urls': 'stun:stun.l.google.com:19302'}, 
                {'urls': 'turn:relay1.expressturn.com:3480', 'username': '000000002076929768', 'credential': 'glxmCqGZVm2WqKrB/EXZsf2SZGc='}  
            ],
            iceCandidatePoolSize: 10,
            bundlePolicy: 'max-bundle',
            rtcpMuxPolicy: 'require'
        });
        
        // Thiết lập các event handlers cho peer connection
        this.setupPeerConnectionHandlers();
        console.log('Đã tạo peer connection mới');
        return this.peerConnection;
    }
    
    /**
     * Thiết lập các event handlers cho peer connection
     */
    setupPeerConnectionHandlers() {
        // Xử lý khi nhận được track từ drone
        this.peerConnection.ontrack = (event) => {
            if (event.streams && event.streams[0]) {
                console.log('Đã nhận video track từ drone');
                this.videoElement.srcObject = event.streams[0];
                
                // Đảm bảo video sẽ tự động play
                this.videoElement.onloadedmetadata = () => {
                    this.videoElement.play().catch(e => {
                        console.warn('Không thể tự động phát video:', e);
                    });
                };
                
                this.statusCallback('track_received');
                
                // Xóa timeout khi đã nhận được track
                this.clearConnectionTimeout();
            }
        };
        
        // Xử lý khi trạng thái kết nối thay đổi
        this.peerConnection.onconnectionstatechange = () => {
            console.log('Trạng thái kết nối:', this.peerConnection.connectionState);
            
            if (this.peerConnection.connectionState === 'connected') {
                this.isConnected = true;
                this.reconnectAttempts = 0; // Reset số lần thử kết nối lại
                this.statusCallback('connected');
                this.clearConnectionTimeout();
                this.startHeartbeat(); // Bắt đầu heartbeat để giữ kết nối
            } else if (this.peerConnection.connectionState === 'disconnected') {
                this.isConnected = false;
                this.statusCallback('disconnected');
                this.stopHeartbeat();
                // Kết nối lại ngay lập tức nếu đang hiển thị trang
                if (this.isPageVisible && this.shouldAutoReconnect) {
                    this.scheduleReconnect(this.reconnectDelay);
                }
            } else if (this.peerConnection.connectionState === 'failed' ||
                       this.peerConnection.connectionState === 'closed') {
                this.isConnected = false;
                this.statusCallback('connection_failed');
                this.stopHeartbeat();
                if (this.shouldAutoReconnect) {
                    this.scheduleReconnect(this.reconnectDelay);
                }
            }
        };
        
        // Xử lý khi ICE connection state thay đổi
        this.peerConnection.oniceconnectionstatechange = () => {
            console.log('ICE connection state:', this.peerConnection.iceConnectionState);
            
            if (this.peerConnection.iceConnectionState === 'disconnected' ||
                this.peerConnection.iceConnectionState === 'failed') {
                // Kết nối lại nhanh nếu ICE connection thất bại
                if (this.shouldAutoReconnect) {
                    this.scheduleReconnect(this.reconnectDelay);
                }
            }
        };
        
        // Xử lý khi ICE gathering state thay đổi
        this.peerConnection.onicegatheringstatechange = () => {
            console.log('ICE gathering state:', this.peerConnection.iceGatheringState);
        };
        
        // Xử lý khi tạo ICE candidate
        this.peerConnection.onicecandidate = (event) => {
            if (event.candidate) {
                // Gửi ICE candidate đến server để chuyển đến drone
                this.socket.emit('webrtc_ice_candidate', {
                    device_id: this.deviceId,
                    candidate: event.candidate
                });
                console.log('Đã gửi ICE candidate đến drone');
            }
        };
    }
    
    /**
     * Khởi tạo kết nối WebRTC
     */
    async start() {
        try {
            // Đóng kết nối cũ nếu có
            if (this.peerConnection) {
                await this.stop();
            }
            
            // Tạo peer connection mới
            await this.createPeerConnection();
            
            // Gửi yêu cầu bắt đầu đến drone (drone sẽ là offerer)
            this.socket.emit('start_webrtc', {
                device_id: this.deviceId
            });
            
            console.log('Đã gửi yêu cầu bắt đầu WebRTC đến drone');
            this.startTime = new Date();
            this.statusCallback('start_request_sent');
            
            // Thiết lập timeout cho kết nối
            this.setConnectionTimeout();
        } catch (error) {
            console.error('Lỗi khi khởi tạo kết nối WebRTC:', error);
            this.statusCallback('error', error.message);
            this.handleConnectionFailure();
        }
    }
    
    /**
     * Dừng kết nối WebRTC
     */
    stop() {
        this.shouldAutoReconnect = false; // Tắt auto-reconnect
        this.clearConnectionTimeout();
        this.stopHeartbeat();
        
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
        
        if (this.peerConnection) {
            this.peerConnection.close();
            this.peerConnection = null;
        }
        
        if (this.videoElement.srcObject) {
            const tracks = this.videoElement.srcObject.getTracks();
            tracks.forEach(track => track.stop());
            this.videoElement.srcObject = null;
        }
        
        this.isConnected = false;
        this.statusCallback('stopped');
        console.log('Đã dừng kết nối WebRTC');
    }
    
    /**
     * Kiểm tra xem kết nối có đang hoạt động không
     */
    isActive() {
        return this.isConnected;
    }
    
    /**
     * Lấy thông tin thống kê về kết nối
     */
    async getStats() {
        if (!this.peerConnection) {
            return null;
        }
        
        try {
            const stats = await this.peerConnection.getStats();
            return stats;
        } catch (error) {
            console.error('Lỗi khi lấy thống kê:', error);
            return null;
        }
    }
    
    /**
     * Thiết lập timeout cho kết nối
     */
    setConnectionTimeout() {
        this.clearConnectionTimeout();
        
        this.connectionTimer = setTimeout(() => {
            console.warn('Kết nối WebRTC timeout sau', this.connectionTimeout, 'ms');
            this.statusCallback('connection_timeout');
            this.handleConnectionFailure();
        }, this.connectionTimeout);
    }
    
    /**
     * Xóa timeout cho kết nối
     */
    clearConnectionTimeout() {
        if (this.connectionTimer) {
            clearTimeout(this.connectionTimer);
            this.connectionTimer = null;
        }
    }
    
    /**
     * Xử lý khi kết nối thất bại
     */
    handleConnectionFailure() {
        this.reconnectAttempts++;
        console.log(`Thử kết nối lại lần ${this.reconnectAttempts}`);
        this.statusCallback('reconnecting', { attempt: this.reconnectAttempts });
        
        // Thử kết nối lại với delay ngắn hơn
        this.scheduleReconnect(this.reconnectDelay);
    }
    
    /**
     * Lên lịch kết nối lại
     */
    scheduleReconnect(delay) {
        // Hủy timer cũ nếu có
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
        }
        
        // Chỉ reconnect nếu chưa connected và shouldAutoReconnect = true
        if (!this.isConnected && this.shouldAutoReconnect) {
            this.reconnectTimer = setTimeout(() => {
                console.log('Đang kết nối lại...');
                this.start();
            }, delay);
        }
    }
    
    /**
     * Thiết lập handler cho Page Visibility API
     * Giữ kết nối khi chuyển tab
     */
    setupVisibilityHandler() {
        document.addEventListener('visibilitychange', () => {
            this.isPageVisible = !document.hidden;
            
            if (this.isPageVisible) {
                console.log('Trang đã hiển thị lại');
                // Kiểm tra kết nối khi quay lại trang
                if (!this.isConnected && this.shouldAutoReconnect) {
                    console.log('Kết nối lại khi quay lại trang...');
                    this.start();
                }
            } else {
                console.log('Trang đã bị ẩn');
                // Giữ kết nối ngay cả khi chuyển tab
                // Không dừng kết nối
            }
        });
    }
    
    /**
     * Thiết lập handler cho beforeunload
     * Cleanup đúng cách khi đóng trang
     */
    setupBeforeUnloadHandler() {
        window.addEventListener('beforeunload', () => {
            console.log('Trang sắp được unload');
            // Tắt auto-reconnect khi user đóng trang
            this.shouldAutoReconnect = false;
            this.stopHeartbeat();
            // Không gọi stop() để tránh cleanup quá sớm
        });
    }
    
    /**
     * Bắt đầu heartbeat để giữ kết nối active
     */
    startHeartbeat() {
        this.stopHeartbeat();
        
        // Gửi ping mỗi 30 giây để giữ kết nối
        this.heartbeatInterval = setInterval(() => {
            if (this.isConnected && this.socket.connected) {
                this.socket.emit('webrtc_ping', {
                    device_id: this.deviceId,
                    timestamp: Date.now()
                });
                console.log('Gửi heartbeat ping');
            }
        }, 30000); // 30 giây
    }
    
    /**
     * Dừng heartbeat
     */
    stopHeartbeat() {
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
            this.heartbeatInterval = null;
        }
    }
}