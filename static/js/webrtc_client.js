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
        this.maxReconnectAttempts = 10;
        this.reconnectDelay = 2000; // ms
        this.connectionTimeout = 15000; // ms
        this.connectionTimer = null;
    this.connectedConfirmed = false;
        // connection attempt counter helps avoid stale timers from previous starts
        this.connectionAttempt = 0;
        this.currentAttempt = null;
        
        // Thiết lập các event handlers cho socket
        this.setupSocketHandlers();
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
                // If we're already confirmed connected, ignore duplicate offers
                if (this.connectedConfirmed) {
                    console.debug('Already connectedConfirmed; ignoring incoming offer');
                    return;
                }
                // If signaling state is not stable, reset to avoid "Called in wrong state: stable" errors
                if (this.peerConnection && this.peerConnection.signalingState && this.peerConnection.signalingState !== 'stable') {
                    console.warn('Signaling state not stable (', this.peerConnection.signalingState, '); resetting peer connection before applying offer');
                    try {
                        this.stop();
                    } catch (e) {
                        console.debug('Error while stopping peerConnection during offer handling', e);
                    }
                    await this.createPeerConnection();
                }
                
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
                // Ensure the element is muted to allow autoplay in modern browsers
                try {
                    this.videoElement.muted = true;
                    this.videoElement.setAttribute('muted', '');
                } catch (e) {
                    // ignore
                }

                this.videoElement.srcObject = event.streams[0];

                // Debug: log track info
                try {
                    const tracks = event.streams[0].getVideoTracks();
                    console.log(`Stream video tracks count: ${tracks.length}`);
                    tracks.forEach((t, i) => console.log(`Track[${i}]: id=${t.id}, kind=${t.kind}`));
                } catch (e) {
                    console.debug('Could not enumerate tracks:', e);
                }

                // Attach playback event handlers for debugging
                this.videoElement.onplaying = () => {
                    console.log('Video element playing');
                    // Confirm connection only when playback truly starts
                    this.connectedConfirmed = true;
                    this.isConnected = true;
                    this.reconnectAttempts = 0;
                    // Clear only the timer for this attempt
                    this.clearConnectionTimeout();
                };
                this.videoElement.onpause = () => console.log('Video element paused');
                this.videoElement.onerror = (ev) => console.error('Video element error', ev);

                // Try to play when metadata is loaded; set muted before play to avoid NotAllowedError
                this.videoElement.onloadedmetadata = () => {
                    // Some browsers still block autoplay; ensure we try to play but catch errors
                    this.videoElement.play().then(() => {
                        console.log('play() succeeded');
                    }).catch(e => {
                        console.warn('Không thể tự động phát video:', e);
                    });
                };

                // Make video element visually obvious during debugging
                try {
                    this.videoElement.style.border = '2px solid lime';
                } catch (e) {}
                
                this.statusCallback('track_received');
                
                // Note: final confirmation and clearing of timeout happens in onplaying handler
                // Keep basic state updated here
                this.isConnected = true;
                this.reconnectAttempts = 0;
            }
        };
        
        // Xử lý khi trạng thái kết nối thay đổi
        this.peerConnection.onconnectionstatechange = () => {
            console.log('Trạng thái kết nối:', this.peerConnection.connectionState);
            
            if (this.peerConnection.connectionState === 'connected') {
                this.isConnected = true;
                this.reconnectAttempts = 0; // Reset số lần thử kết nối lại
                this.statusCallback('connected');
                // Mark confirmed when PC reaches connected as a stronger signal
                this.connectedConfirmed = true;
                console.debug('PeerConnection connected; setting connectedConfirmed=true, currentAttempt:', this.currentAttempt);
                this.clearConnectionTimeout();
            } else if (this.peerConnection.connectionState === 'disconnected') {
                this.isConnected = false;
                this.statusCallback('disconnected');
                // Thử kết nối lại sau một khoảng thời gian
                setTimeout(() => this.handleConnectionFailure(), this.reconnectDelay);
            } else if (this.peerConnection.connectionState === 'failed' ||
                       this.peerConnection.connectionState === 'closed') {
                this.isConnected = false;
                this.statusCallback('connection_failed');
                this.handleConnectionFailure();
            }
        };
        
        // Xử lý khi ICE connection state thay đổi
        this.peerConnection.oniceconnectionstatechange = () => {
            console.log('ICE connection state:', this.peerConnection.iceConnectionState);
            
            if (this.peerConnection.iceConnectionState === 'disconnected' ||
                this.peerConnection.iceConnectionState === 'failed') {
                // Thử kết nối lại nếu ICE connection thất bại
                setTimeout(() => this.handleConnectionFailure(), this.reconnectDelay);
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
            // Reset confirmation and guard against concurrent starts
            this.connectedConfirmed = false;
            if (this.starting) {
                console.debug('Start already in progress, skipping duplicate start');
                return;
            }
            this.starting = true;

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
            
            // Thiết lập timeout cho kết nối; increment attempt id to identify this run
            this.connectionAttempt += 1;
            this.currentAttempt = this.connectionAttempt;
            this.setConnectionTimeout(this.currentAttempt);
            this.starting = false;
        } catch (error) {
            console.error('Lỗi khi khởi tạo kết nối WebRTC:', error);
            this.statusCallback('error', error.message);
            this.handleConnectionFailure();
            this.starting = false;
        }
    }
    
    /**
     * Dừng kết nối WebRTC
     */
    stop() {
        this.clearConnectionTimeout();
        
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
        this.connectedConfirmed = false;
        this.starting = false;
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
        // Always clear any previous timer first
        this.clearConnectionTimeout();

        // If already confirmed connected, don't set a timeout
        if (this.connectedConfirmed || (this.peerConnection && this.peerConnection.connectionState === 'connected')) {
            console.debug('Connection already active/confirmed; skipping connection timeout');
            return;
        }

        // If the video element is already playing, skip creating a timeout (avoid false positives)
        try {
            if (this.videoElement && !this.videoElement.paused && this.videoElement.readyState >= 3) {
                console.debug('Video element already playing; skipping connection timeout');
                return;
            }
        } catch (e) {
            // ignore cross-origin or other errors when checking element state
        }

        // Save the timer id and log for debugging races. Capture attempt id to avoid clearing someone else's timer.
        const attemptId = this.currentAttempt;
        const timerId = setTimeout(() => {
            // If this attempt has already been confirmed, skip
            if (this.currentAttempt !== attemptId || this.connectedConfirmed) {
                console.debug('Timeout fired for stale attempt or already confirmed; skipping', {attemptId, currentAttempt: this.currentAttempt, connectedConfirmed: this.connectedConfirmed});
                return;
            }
            console.warn('Kết nối WebRTC timeout sau', this.connectionTimeout, 'ms', 'attemptId:', attemptId);
            this.statusCallback('connection_timeout');
            this.handleConnectionFailure();
        }, this.connectionTimeout);
        this.connectionTimer = timerId;
        console.debug('Connection timeout set (ms):', this.connectionTimeout, 'timerId:', this.connectionTimer, 'attemptId:', attemptId);
    }
    
    /**
     * Xóa timeout cho kết nối
     */
    clearConnectionTimeout() {
        if (this.connectionTimer) {
            console.debug('Clearing connection timeout, timerId:', this.connectionTimer, 'connectedConfirmed:', this.connectedConfirmed, 'currentAttempt:', this.currentAttempt);
            clearTimeout(this.connectionTimer);
            this.connectionTimer = null;
        }
    }
    
    /**
     * Xử lý khi kết nối thất bại
     */
    handleConnectionFailure() {
        // If we're already confirmed connected, do not attempt recovery
        if (this.connectedConfirmed || (this.peerConnection && this.peerConnection.connectionState === 'connected')) {
            console.debug('Connection already confirmed; skipping reconnection');
            return;
        }

        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            console.log(`Thử kết nối lại lần ${this.reconnectAttempts}/${this.maxReconnectAttempts}`);
            this.statusCallback('reconnecting', { attempt: this.reconnectAttempts, max: this.maxReconnectAttempts });
            
            // Thử kết nối lại sau một khoảng delay để tránh race giữa timers và ontrack
            setTimeout(() => {
                try {
                    this.start();
                } catch (e) {
                    console.error('Lỗi khi thử start lại:', e);
                }
            }, this.reconnectDelay);
        } else {
            console.error('Đã vượt quá số lần thử kết nối lại tối đa');
            this.statusCallback('reconnect_failed');
            
            // Dừng kết nối
            this.stop();
        }
    }
}